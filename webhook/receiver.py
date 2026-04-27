"""
webhook/receiver.py — Meta Cloud API Webhook handler
GET  /webhook/meta → Meta verification
POST /webhook/meta → Incoming messages
"""
from fastapi import APIRouter, Request, Query, HTTPException
from datetime import datetime
from onboarding.number_manager import identify_client_by_phone_id
from automation.template_engine import process_message
from leads.lead_manager import capture_or_update_lead
from messaging.sender import send_whatsapp_message, mark_as_read
from database.db import create_doc
from database.models import MessageLog, MessageDirection
from config import META_VERIFY_TOKEN, COLLECTION_MESSAGES

router = APIRouter()

@router.get("/meta")
async def verify_webhook(
    hub_mode:         str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge:    str = Query(None, alias="hub.challenge"),
):
    """Meta pehli baar webhook register karte waqt yeh call karta hai."""
    if hub_mode == "subscribe" and hub_verify_token == META_VERIFY_TOKEN:
        print("✅ Meta webhook verified")
        return int(hub_challenge)
    raise HTTPException(status_code=403, detail="Verification failed")

@router.post("/meta")
async def receive_message(request: Request):
    """
    Har incoming WhatsApp message yahan aata hai.
    Flow: parse → identify client → lead capture → reply → log
    """
    body = await request.json()

    try:
        entry   = body["entry"][0]
        changes = entry["changes"][0]["value"]
    except (KeyError, IndexError):
        return {"status": "ignored", "reason": "no_entry"}

    # Status updates (delivered/read) ignore karo
    if "statuses" in changes and "messages" not in changes:
        return {"status": "ignored", "reason": "status_update"}

    if "messages" not in changes:
        return {"status": "ignored", "reason": "no_message"}

    message         = changes["messages"][0]
    phone_number_id = changes["metadata"]["phone_number_id"]
    from_number     = message["from"]
    msg_type        = message.get("type", "")
    message_id      = message["id"]
    contact_name    = changes.get("contacts", [{}])[0].get("profile", {}).get("name", "")

    # Sirf text handle karo
    if msg_type != "text":
        return {"status": "ignored", "reason": f"type_{msg_type}"}

    incoming_text = message["text"]["body"]
    print(f"📩 From: {from_number} | PhoneID: {phone_number_id} | Text: {incoming_text!r}")

    # 1. Client identify
    client = identify_client_by_phone_id(phone_number_id)
    if not client:
        print(f"⚠️ No client for phone_number_id: {phone_number_id}")
        return {"status": "ignored", "reason": "unknown_phone_id"}

    client_id    = client["id"]
    access_token = client.get("meta_access_token", "")

    # 2. Blue ticks
    await mark_as_read(message_id, phone_number_id, access_token)

    # 3. Lead capture/update
    lead = await capture_or_update_lead(
        client_id=client_id, phone=from_number, name=contact_name
    )

    # 4. Log inbound
    create_doc(COLLECTION_MESSAGES, MessageLog(
        client_id=client_id, lead_phone=from_number,
        direction=MessageDirection.inbound,
        body=incoming_text, meta_message_id=message_id,
        timestamp=datetime.utcnow().isoformat(),
    ).dict(exclude={"id"}))

    # 5. Template engine → reply
    reply_text, template_id = process_message(
        client_id=client_id, incoming_text=incoming_text,
        lead=lead, client=client,
    )

    if reply_text:
        # 6. Send reply
        sent_id = await send_whatsapp_message(
            to=from_number, body=reply_text,
            phone_number_id=phone_number_id,
            access_token=access_token,
        )
        # 7. Log outbound
        create_doc(COLLECTION_MESSAGES, MessageLog(
            client_id=client_id, lead_phone=from_number,
            direction=MessageDirection.outbound,
            body=reply_text, template_id=template_id,
            meta_message_id=sent_id,
            timestamp=datetime.utcnow().isoformat(),
        ).dict(exclude={"id"}))

    return {"status": "processed", "client_id": client_id, "from": from_number}

@router.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}
