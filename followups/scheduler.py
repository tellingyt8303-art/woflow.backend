"""
scheduler.py — Follow-up schedule + process + cancel
Dashboard ke follow-ups tab se yeh sab use hota hai
"""
from datetime import datetime, timedelta
from typing import Optional
from database.db import query_docs, create_doc, update_doc
from database.models import Followup, FollowupStatus
from config import COLLECTION_FOLLOWUPS, COLLECTION_TEMPLATES, DEFAULT_FOLLOWUP_INTERVALS

async def schedule_followups(client_id: str, lead_phone: str):
    """Naye lead ke liye Day 1/3/7 follow-ups schedule karo."""
    templates = query_docs(COLLECTION_TEMPLATES, filters=[
        ("client_id", "==", client_id), ("active", "==", True)
    ])
    fu_templates = [t for t in templates if not t.get("is_default", False)]
    now = datetime.utcnow()

    for i, days in enumerate(DEFAULT_FOLLOWUP_INTERVALS):
        scheduled = now + timedelta(days=days)
        tmpl_id   = None
        body      = f"Hi! Just following up — kya hum kuch help kar sakte hain? 😊"
        if fu_templates:
            tmpl     = fu_templates[i % len(fu_templates)]
            tmpl_id  = tmpl.get("id")
            body     = tmpl.get("message_body", body)

        fu = Followup(
            client_id=client_id, lead_phone=lead_phone,
            template_id=tmpl_id, message_body=body,
            scheduled_at=scheduled.isoformat(),
            status=FollowupStatus.pending, attempt=i + 1,
        )
        create_doc(COLLECTION_FOLLOWUPS, fu.dict(exclude={"id"}))
    print(f"📅 {len(DEFAULT_FOLLOWUP_INTERVALS)} follow-ups scheduled for {lead_phone}")

async def process_due_followups() -> int:
    """APScheduler se har 15 min call hota hai — due follow-ups bhejo."""
    from messaging.sender import send_whatsapp_message
    from onboarding.number_manager import get_client

    now_iso = datetime.utcnow().isoformat()
    pending = query_docs(COLLECTION_FOLLOWUPS, filters=[
        ("status", "==", FollowupStatus.pending.value)
    ])
    sent = 0
    for fu in pending:
        if fu["scheduled_at"] <= now_iso:
            client = get_client(fu["client_id"])
            if not client or not client.get("wa_connected"):
                continue
            msg_id = await send_whatsapp_message(
                to=fu["lead_phone"], body=fu["message_body"],
                phone_number_id=client["meta_phone_number_id"],
                access_token=client["meta_access_token"],
            )
            new_status = FollowupStatus.sent if msg_id else FollowupStatus.failed
            update_doc(COLLECTION_FOLLOWUPS, fu["id"], {
                "status":          new_status.value,
                "sent_at":         datetime.utcnow().isoformat(),
                "meta_message_id": msg_id,
            })
            sent += 1
    print(f"✅ Follow-up batch: {sent} sent")
    return sent

async def send_followup_now(followup_id: str) -> bool:
    """Dashboard → 'Send Now' button."""
    from messaging.sender import send_whatsapp_message
    from onboarding.number_manager import get_client
    from database.db import get_doc

    fu = get_doc(COLLECTION_FOLLOWUPS, followup_id)
    if not fu:
        return False
    client = get_client(fu["client_id"])
    if not client or not client.get("wa_connected"):
        return False
    msg_id = await send_whatsapp_message(
        to=fu["lead_phone"], body=fu["message_body"],
        phone_number_id=client["meta_phone_number_id"],
        access_token=client["meta_access_token"],
    )
    update_doc(COLLECTION_FOLLOWUPS, followup_id, {
        "status":          (FollowupStatus.sent if msg_id else FollowupStatus.failed).value,
        "sent_at":         datetime.utcnow().isoformat(),
        "meta_message_id": msg_id,
    })
    return bool(msg_id)

def cancel_followup(followup_id: str):
    """Dashboard → 'Cancel' button (single)."""
    update_doc(COLLECTION_FOLLOWUPS, followup_id, {
        "status": FollowupStatus.cancelled.value
    })

def cancel_all_followups(client_id: str, lead_phone: str):
    """Lead convert ho gayi — sab cancel karo."""
    pending = query_docs(COLLECTION_FOLLOWUPS, filters=[
        ("client_id",  "==", client_id),
        ("lead_phone", "==", lead_phone),
        ("status",     "==", FollowupStatus.pending.value),
    ])
    for f in pending:
        update_doc(COLLECTION_FOLLOWUPS, f["id"], {"status": FollowupStatus.cancelled.value})
    print(f"🚫 {len(pending)} follow-ups cancelled for {lead_phone}")
    return len(pending)

def get_followup_stats(client_id: str) -> dict:
    """Analytics page ke liye follow-up breakdown."""
    fus = query_docs(COLLECTION_FOLLOWUPS, filters=[("client_id", "==", client_id)])
    return {
        "total":     len(fus),
        "sent":      sum(1 for f in fus if f.get("status") == "sent"),
        "pending":   sum(1 for f in fus if f.get("status") == "pending"),
        "failed":    sum(1 for f in fus if f.get("status") == "failed"),
        "cancelled": sum(1 for f in fus if f.get("status") == "cancelled"),
        "day1":      [f for f in fus if f.get("attempt") == 1],
        "day3":      [f for f in fus if f.get("attempt") == 2],
        "day7":      [f for f in fus if f.get("attempt") == 3],
    }
