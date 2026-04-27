"""
api/routes.py — Complete REST API
Frontend Dashboard + Admin se yeh sab endpoints use hote hain

Auth: Firebase ID Token → Authorization: Bearer <token>
"""
from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional
from firebase_admin import auth as firebase_auth
from datetime import datetime

from database.models import (
    Client, Lead, Template, Followup,
    UserCreate, LeadStatusUpdate, WhatsAppConnectRequest,
    SendMessageRequest, TemplateCreate, FollowupAction,
)
from database.db import (
    create_doc, get_doc, update_doc, query_docs, delete_doc, get_all_docs
)
from config import (
    COLLECTION_CLIENTS, COLLECTION_LEADS, COLLECTION_MESSAGES,
    COLLECTION_TEMPLATES, COLLECTION_FOLLOWUPS, COLLECTION_USERS,
)
from onboarding.number_manager import (
    register_client, list_all_clients,
    verify_and_connect_whatsapp, disconnect_whatsapp, get_client,
)
from leads.lead_manager import (
    get_leads_for_client, update_lead_status,
    get_lead_stats, delete_lead, delete_all_leads,
)
from followups.scheduler import (
    process_due_followups, cancel_followup,
    cancel_all_followups, get_followup_stats, send_followup_now,
)
from messaging.sender import send_whatsapp_message

router = APIRouter()

# ── Firebase Auth Dependency ──────────────────────────────────
async def verify_token(authorization: str = Header(...)) -> dict:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid auth header")
    try:
        return firebase_auth.verify_id_token(authorization.split(" ")[1])
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

# ════════════════════════════════════════════════════════════
#  AUTH
# ════════════════════════════════════════════════════════════

@router.post("/auth/register")
async def register_user(user: UserCreate):
    """
    Signup pe call hota hai.
    Firebase Auth mein user banao + Firestore mein users + clients document.
    """
    try:
        fb_user = firebase_auth.create_user(
            email=user.email, password=user.password, display_name=user.name
        )
        now = datetime.utcnow().isoformat()
        from datetime import timedelta
        exp = (datetime.utcnow() + timedelta(days=14)).isoformat()

        # users collection
        create_doc(COLLECTION_USERS, {
            "uid": fb_user.uid, "name": user.name, "email": user.email,
            "business_name": user.business_name, "role": "user",
            "plan": "trial", "plan_expires": exp,
            "wa_connected": False, "created_at": now, "updated_at": now,
        }, doc_id=fb_user.uid)

        # clients collection
        client_id = register_client({
            "firebase_uid": fb_user.uid, "name": user.name, "email": user.email,
            "business_name": user.business_name, "plan": "trial",
        })
        return {"uid": fb_user.uid, "client_id": client_id, "message": "Registered"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# ════════════════════════════════════════════════════════════
#  WHATSAPP — Dashboard → WhatsApp Tab
# ════════════════════════════════════════════════════════════

@router.post("/whatsapp/connect/{client_id}")
async def connect_whatsapp(
    client_id: str,
    req: WhatsAppConnectRequest,
    user=Depends(verify_token),
):
    """Dashboard → 'Connect & Verify' button."""
    result = await verify_and_connect_whatsapp(
        client_id=client_id,
        phone_number_id=req.phone_number_id,
        access_token=req.access_token,
    )
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.post("/whatsapp/disconnect/{client_id}")
async def disconnect_wa(client_id: str, user=Depends(verify_token)):
    """Dashboard → 'Disconnect' button."""
    disconnect_whatsapp(client_id)
    return {"message": "WhatsApp disconnected"}

@router.get("/whatsapp/status/{client_id}")
async def wa_status(client_id: str, user=Depends(verify_token)):
    """Dashboard sidebar WA status dot ke liye."""
    c = get_client(client_id)
    if not c:
        raise HTTPException(status_code=404, detail="Client not found")
    return {
        "connected":     c.get("wa_connected", False),
        "number":        c.get("whatsapp_number"),
        "verified_name": c.get("wa_verified_name"),
        "connected_at":  c.get("wa_connected_at"),
    }

# ════════════════════════════════════════════════════════════
#  TEMPLATES — Dashboard → Templates Tab
# ════════════════════════════════════════════════════════════

@router.post("/templates")
async def create_template(tmpl: TemplateCreate, client_id: str, user=Depends(verify_token)):
    """Dashboard → 'Save Template' button."""
    data = {
        "client_id": client_id, "name": tmpl.name,
        "message_body": tmpl.message_body,
        "trigger_keywords": tmpl.trigger_keywords,
        "is_default": tmpl.is_default, "active": tmpl.active,
        "hit_count": 0, "last_used": None,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    tid = create_doc(COLLECTION_TEMPLATES, data)
    return {"id": tid, "message": "Template created"}

@router.get("/templates/{client_id}")
async def list_templates(client_id: str, user=Depends(verify_token)):
    """Dashboard → Templates list."""
    return query_docs(COLLECTION_TEMPLATES, filters=[("client_id", "==", client_id)])

@router.put("/templates/{template_id}")
async def update_template(template_id: str, data: TemplateCreate, user=Depends(verify_token)):
    """Dashboard → Template edit."""
    update_doc(COLLECTION_TEMPLATES, template_id, {
        **data.dict(), "updated_at": datetime.utcnow().isoformat()
    })
    return {"message": "Updated"}

@router.patch("/templates/{template_id}/toggle")
async def toggle_template(template_id: str, active: bool, user=Depends(verify_token)):
    """Dashboard → Enable/Disable template."""
    update_doc(COLLECTION_TEMPLATES, template_id, {
        "active": active, "updated_at": datetime.utcnow().isoformat()
    })
    return {"message": "Toggled"}

@router.delete("/templates/{template_id}")
async def delete_template(template_id: str, user=Depends(verify_token)):
    """Dashboard → Delete template."""
    delete_doc(COLLECTION_TEMPLATES, template_id)
    return {"message": "Deleted"}

# ════════════════════════════════════════════════════════════
#  LEADS — Dashboard → Leads Tab
# ════════════════════════════════════════════════════════════

@router.get("/leads/{client_id}")
async def get_leads(
    client_id: str, status: Optional[str] = None,
    user=Depends(verify_token)
):
    """Dashboard → Leads table."""
    return get_leads_for_client(client_id, status)

@router.put("/leads/{lead_id}/status")
async def set_lead_status(
    lead_id: str, body: LeadStatusUpdate,
    user=Depends(verify_token)
):
    """Dashboard → Lead status dropdown change."""
    update_lead_status(lead_id, body.status.value, body.notes)
    return {"message": "Status updated"}

@router.delete("/leads/{lead_id}")
async def remove_lead(lead_id: str, user=Depends(verify_token)):
    """Dashboard → Delete lead."""
    delete_lead(lead_id)
    return {"message": "Lead deleted"}

@router.delete("/leads/all/{client_id}")
async def remove_all_leads(client_id: str, user=Depends(verify_token)):
    """Dashboard → Settings → Delete All Leads."""
    count = delete_all_leads(client_id)
    return {"message": f"{count} leads deleted"}

@router.get("/leads/{client_id}/stats")
async def lead_stats(client_id: str, user=Depends(verify_token)):
    """Dashboard → Overview stats + Analytics rings."""
    return get_lead_stats(client_id)

# ════════════════════════════════════════════════════════════
#  MESSAGES — Dashboard → Messages Tab
# ════════════════════════════════════════════════════════════

@router.get("/messages/{client_id}")
async def get_messages(
    client_id: str, lead_phone: Optional[str] = None,
    limit: int = 100, user=Depends(verify_token)
):
    """Dashboard → Message logs table."""
    filters = [("client_id", "==", client_id)]
    if lead_phone:
        filters.append(("lead_phone", "==", lead_phone))
    return query_docs(COLLECTION_MESSAGES, filters=filters, limit=limit)

@router.post("/messages/send/{client_id}")
async def send_message(
    client_id: str, req: SendMessageRequest,
    user=Depends(verify_token)
):
    """Dashboard → Manual message send."""
    client = get_client(client_id)
    if not client or not client.get("wa_connected"):
        raise HTTPException(status_code=400, detail="WhatsApp not connected")
    msg_id = await send_whatsapp_message(
        to=req.to, body=req.body,
        phone_number_id=client["meta_phone_number_id"],
        access_token=client["meta_access_token"],
    )
    if not msg_id:
        raise HTTPException(status_code=500, detail="Message send failed")
    # Log outbound
    create_doc(COLLECTION_MESSAGES, {
        "client_id": client_id, "lead_phone": req.to,
        "direction": "outbound", "body": req.body,
        "meta_message_id": msg_id,
        "timestamp": datetime.utcnow().isoformat(),
    })
    return {"message_id": msg_id, "status": "sent"}

# ════════════════════════════════════════════════════════════
#  FOLLOW-UPS — Dashboard → Follow-ups Tab
# ════════════════════════════════════════════════════════════

@router.get("/followups/{client_id}")
async def get_followups(
    client_id: str, status: Optional[str] = None,
    user=Depends(verify_token)
):
    """Dashboard → Follow-ups table."""
    filters = [("client_id", "==", client_id)]
    if status:
        filters.append(("status", "==", status))
    return query_docs(COLLECTION_FOLLOWUPS, filters=filters, limit=200)

@router.get("/followups/{client_id}/stats")
async def followup_stats(client_id: str, user=Depends(verify_token)):
    """Dashboard → Analytics → Follow-up breakdown + Day 1/3/7 cards."""
    stats = get_followup_stats(client_id)
    # Day cards ke liye counts
    stats["day1_count"] = len(stats.pop("day1", []))
    stats["day3_count"] = len(stats.pop("day3", []))
    stats["day7_count"] = len(stats.pop("day7", []))
    return stats

@router.post("/followups/{followup_id}/send-now")
async def send_followup_now_api(followup_id: str, user=Depends(verify_token)):
    """Dashboard → Follow-ups table → 'Send Now' button."""
    success = await send_followup_now(followup_id)
    if not success:
        raise HTTPException(status_code=400, detail="Send failed or client not connected")
    return {"message": "Sent!"}

@router.post("/followups/{followup_id}/cancel")
async def cancel_followup_api(followup_id: str, user=Depends(verify_token)):
    """Dashboard → Follow-ups table → 'Cancel' button."""
    cancel_followup(followup_id)
    return {"message": "Cancelled"}

@router.post("/followups/cancel-all/{client_id}")
async def cancel_all_for_lead(
    client_id: str, body: FollowupAction,
    user=Depends(verify_token)
):
    """Lead convert ho gayi → sab follow-ups cancel."""
    count = cancel_all_followups(client_id, body.lead_phone)
    return {"message": f"{count} follow-ups cancelled"}

@router.post("/followups/process")
async def trigger_followup_batch(user=Depends(verify_token)):
    """Admin → System → 'Run Follow-up Batch' button."""
    count = await process_due_followups()
    return {"processed": count}

# ════════════════════════════════════════════════════════════
#  DASHBOARD SUMMARY — Overview Tab
# ════════════════════════════════════════════════════════════

@router.get("/dashboard/{client_id}")
async def get_dashboard(client_id: str, user=Depends(verify_token)):
    """
    Dashboard → Overview tab → sab stats ek call mein.
    """
    client    = get_client(client_id)
    lead_stats = get_lead_stats(client_id)
    fu_stats   = get_followup_stats(client_id)

    pending_fu = fu_stats.get("pending", 0)
    templates  = query_docs(COLLECTION_TEMPLATES, filters=[
        ("client_id", "==", client_id), ("active", "==", True)
    ])
    recent_msgs = query_docs(COLLECTION_MESSAGES, filters=[
        ("client_id", "==", client_id)
    ], limit=10)

    return {
        "whatsapp": {
            "connected":     client.get("wa_connected", False) if client else False,
            "number":        client.get("whatsapp_number") if client else None,
            "verified_name": client.get("wa_verified_name") if client else None,
        },
        "leads":             lead_stats,
        "followups":         fu_stats,
        "pending_followups": pending_fu,
        "active_templates":  len(templates),
        "template_list":     templates,
        "recent_messages":   recent_msgs,
    }

# ════════════════════════════════════════════════════════════
#  SETTINGS — Dashboard → Settings Tab
# ════════════════════════════════════════════════════════════

@router.put("/settings/{client_id}")
async def update_settings(
    client_id: str, data: dict,
    user=Depends(verify_token)
):
    """Dashboard → Settings → Save profile."""
    allowed = ["name", "business_name", "phone", "industry"]
    clean   = {k: v for k, v in data.items() if k in allowed}
    clean["updated_at"] = datetime.utcnow().isoformat()
    update_doc(COLLECTION_CLIENTS, client_id, clean)
    update_doc(COLLECTION_USERS,   client_id, clean)
    return {"message": "Settings saved"}

# ════════════════════════════════════════════════════════════
#  ADMIN — Admin Dashboard
# ════════════════════════════════════════════════════════════

async def require_admin(user=Depends(verify_token)):
    """Admin-only routes ke liye."""
    uid  = user.get("uid")
    snap = get_doc(COLLECTION_USERS, uid)
    if not snap or snap.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user

@router.get("/admin/overview")
async def admin_overview(user=Depends(require_admin)):
    """Admin → Overview tab — platform-wide stats."""
    users   = get_all_docs(COLLECTION_USERS)
    clients = get_all_docs(COLLECTION_CLIENTS)
    leads   = get_all_docs(COLLECTION_LEADS)
    msgs    = get_all_docs(COLLECTION_MESSAGES)

    plan_prices = {"trial": 0, "starter": 999, "pro": 2499, "enterprise": 5999}
    mrr = sum(plan_prices.get(u.get("plan", "trial"), 0) for u in users)

    return {
        "total_users":     len(users),
        "wa_connected":    sum(1 for u in users if u.get("wa_connected")),
        "total_clients":   len(clients),
        "total_leads":     len(leads),
        "total_messages":  len(msgs),
        "mrr":             mrr,
        "arr":             mrr * 12,
        "paying_users":    sum(1 for u in users if u.get("plan") not in ["trial", None]),
        "plan_breakdown": {
            p: sum(1 for u in users if u.get("plan", "trial") == p)
            for p in ["trial", "starter", "pro", "enterprise"]
        },
    }

@router.get("/admin/clients")
async def admin_list_clients(user=Depends(require_admin)):
    """Admin → Clients table."""
    clients = get_all_docs(COLLECTION_CLIENTS)
    leads   = get_all_docs(COLLECTION_LEADS)
    lc_map  = {}
    for l in leads:
        cid = l.get("client_id")
        lc_map[cid] = lc_map.get(cid, 0) + 1
    for c in clients:
        c["lead_count"] = lc_map.get(c["id"], 0)
        plan_prices = {"trial": 0, "starter": 999, "pro": 2499, "enterprise": 5999}
        c["monthly_revenue"] = plan_prices.get(c.get("plan", "trial"), 0)
    return clients

@router.put("/admin/clients/{client_id}/suspend")
async def admin_suspend(client_id: str, user=Depends(require_admin)):
    """Admin → Clients table → Suspend."""
    now = datetime.utcnow().isoformat()
    update_doc(COLLECTION_CLIENTS, client_id, {"active": False, "updated_at": now})
    update_doc(COLLECTION_USERS,   client_id, {"active": False, "updated_at": now})
    return {"message": "Suspended"}

@router.put("/admin/clients/{client_id}/restore")
async def admin_restore(client_id: str, user=Depends(require_admin)):
    """Admin → Clients table → Restore."""
    now = datetime.utcnow().isoformat()
    update_doc(COLLECTION_CLIENTS, client_id, {"active": True, "updated_at": now})
    update_doc(COLLECTION_USERS,   client_id, {"active": True, "updated_at": now})
    return {"message": "Restored"}

@router.get("/admin/messages")
async def admin_messages(limit: int = 200, user=Depends(require_admin)):
    """Admin → Messages tab."""
    return query_docs(COLLECTION_MESSAGES, limit=limit)

@router.get("/admin/revenue")
async def admin_revenue(user=Depends(require_admin)):
    """Admin → Revenue tab."""
    users = get_all_docs(COLLECTION_USERS)
    plan_prices = {"trial": 0, "starter": 999, "pro": 2499, "enterprise": 5999}
    mrr = sum(plan_prices.get(u.get("plan", "trial"), 0) for u in users)
    return {
        "mrr": mrr, "arr": mrr * 12,
        "paying": sum(1 for u in users if u.get("plan") not in ["trial", None]),
        "by_plan": {
            p: {"count": sum(1 for u in users if u.get("plan", "trial") == p),
                "revenue": plan_prices[p] * sum(1 for u in users if u.get("plan", "trial") == p)}
            for p in plan_prices
        }
    }

@router.post("/admin/followups/process")
async def admin_process_followups(user=Depends(require_admin)):
    """Admin → System → 'Run Follow-up Batch'."""
    count = await process_due_followups()
    return {"processed": count, "message": f"{count} follow-ups sent"}

@router.get("/admin/export/leads")
async def admin_export_leads(user=Depends(require_admin)):
    """Admin → System → Export CSV (raw data)."""
    leads = get_all_docs(COLLECTION_LEADS)
    return {"leads": leads, "total": len(leads)}
