"""
lead_manager.py — Lead capture, update, stats
Dashboard ke leads tab se yeh sab API endpoints use hote hain
"""
from datetime import datetime
from typing import Optional
from database.db import query_docs, create_doc, update_doc, get_doc, delete_doc
from database.models import Lead, LeadStatus
from config import COLLECTION_LEADS

async def capture_or_update_lead(client_id: str, phone: str, name: Optional[str] = None) -> dict:
    """
    Har incoming WhatsApp message pe call hota hai.
    Naya lead → create + follow-up schedule
    Existing → update name/timestamp
    """
    existing = query_docs(COLLECTION_LEADS, filters=[
        ("client_id", "==", client_id),
        ("phone", "==", phone),
    ])
    now = datetime.utcnow().isoformat()

    if existing:
        lead = existing[0]
        updates = {"updated_at": now}
        if name and not lead.get("name"):
            updates["name"] = name
        update_doc(COLLECTION_LEADS, lead["id"], updates)
        lead.update(updates)
        return lead
    else:
        # New lead
        new_lead = Lead(
            client_id=client_id, phone=phone,
            name=name, status=LeadStatus.new,
            created_at=now, updated_at=now,
        )
        data   = new_lead.dict(exclude={"id"})
        lead_id = create_doc(COLLECTION_LEADS, data)
        data["id"] = lead_id
        print(f"🆕 New lead: {phone} → client {client_id}")

        # Schedule follow-ups
        from followups.scheduler import schedule_followups
        await schedule_followups(client_id=client_id, lead_phone=phone)
        return data

def get_leads_for_client(client_id: str, status: Optional[str] = None) -> list:
    filters = [("client_id", "==", client_id)]
    if status:
        filters.append(("status", "==", status))
    return query_docs(COLLECTION_LEADS, filters=filters)

def update_lead_status(lead_id: str, status: str, notes: Optional[str] = None):
    updates = {"status": status, "updated_at": datetime.utcnow().isoformat()}
    if notes:
        updates["notes"] = notes
    update_doc(COLLECTION_LEADS, lead_id, updates)

def delete_lead(lead_id: str):
    delete_doc(COLLECTION_LEADS, lead_id)

def delete_all_leads(client_id: str) -> int:
    leads = query_docs(COLLECTION_LEADS, filters=[("client_id", "==", client_id)])
    for l in leads:
        delete_doc(COLLECTION_LEADS, l["id"])
    return len(leads)

def get_lead_stats(client_id: str) -> dict:
    leads = query_docs(COLLECTION_LEADS, filters=[("client_id", "==", client_id)])
    stats = {"total": len(leads)}
    for s in LeadStatus:
        stats[s.value] = sum(1 for l in leads if l.get("status") == s.value)
    return stats
