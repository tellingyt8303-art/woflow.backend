"""
sender.py — Meta Cloud API se WhatsApp message bhejta hai
Har client ka apna phone_number_id + access_token hota hai (Firebase mein stored)
"""
import httpx
from config import META_API_BASE
from typing import Optional

async def send_whatsapp_message(
    to: str,
    body: str,
    phone_number_id: str,
    access_token: str,
) -> Optional[str]:
    """Text message bhejo. Returns Meta message ID (wamid) or None."""
    to_clean = to.replace("whatsapp:", "").replace("+", "").replace(" ", "")
    url = f"{META_API_BASE}/{phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type":    "individual",
        "to":                to_clean,
        "type":              "text",
        "text":              {"preview_url": False, "body": body},
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(url, json=payload, headers=headers)
            data = resp.json()
            if resp.status_code == 200:
                msg_id = data.get("messages", [{}])[0].get("id")
                print(f"✅ Sent | ID: {msg_id} | To: {to_clean}")
                return msg_id
            print(f"❌ Meta API error: {data}")
            return None
    except Exception as e:
        print(f"❌ Send error: {e}")
        return None

async def mark_as_read(message_id: str, phone_number_id: str, access_token: str):
    """Blue ticks lagao."""
    url = f"{META_API_BASE}/{phone_number_id}/messages"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.post(url, json={
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id,
            }, headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"})
    except Exception:
        pass

async def send_bulk_messages(recipients: list, phone_number_id: str, access_token: str) -> dict:
    """Multiple logon ko message bhejo."""
    sent, failed, results = 0, 0, []
    for r in recipients:
        msg_id = await send_whatsapp_message(r["to"], r["body"], phone_number_id, access_token)
        if msg_id:
            sent += 1; results.append({"to": r["to"], "status": "sent", "id": msg_id})
        else:
            failed += 1; results.append({"to": r["to"], "status": "failed"})
    return {"sent": sent, "failed": failed, "results": results}
