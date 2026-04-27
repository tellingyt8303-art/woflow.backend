"""
number_manager.py — Client ka WhatsApp number Meta se connect/disconnect karna
Dashboard se user Phone Number ID + Access Token deta hai → yahan verify hota hai
"""
import httpx
from datetime import datetime
from typing import Optional
from database.db import query_docs, create_doc, update_doc, get_doc
from config import COLLECTION_CLIENTS, META_API_BASE

def identify_client_by_phone_id(phone_number_id: str) -> Optional[dict]:
    """Webhook mein Meta phone_number_id se client dhundo."""
    results = query_docs(COLLECTION_CLIENTS, filters=[
        ("meta_phone_number_id", "==", phone_number_id),
        ("active", "==", True),
    ])
    return results[0] if results else None

def get_client(client_id: str) -> Optional[dict]:
    return get_doc(COLLECTION_CLIENTS, client_id)

def register_client(data: dict) -> str:
    """Naya business client register karo (signup pe automatically hota hai)."""
    data["active"]     = True
    data["wa_connected"] = False
    data["created_at"] = datetime.utcnow().isoformat()
    data["updated_at"] = datetime.utcnow().isoformat()
    doc_id = create_doc(COLLECTION_CLIENTS, data)
    print(f"✅ Client registered: {data.get('business_name')} | ID: {doc_id}")
    return doc_id

async def verify_and_connect_whatsapp(
    client_id: str,
    phone_number_id: str,
    access_token: str,
) -> dict:
    """
    Dashboard → 'Connect WhatsApp' button → yeh function call hota hai.
    Meta API se number verify karke Firebase mein save karo.
    """
    url     = f"{META_API_BASE}/{phone_number_id}"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.get(url, headers=headers)
            data = resp.json()

        if resp.status_code != 200 or "error" in data:
            err = data.get("error", {}).get("message", "Invalid credentials")
            return {"success": False, "error": err}

        display_number = data.get("display_phone_number", "")
        verified_name  = data.get("verified_name", "")

        update_doc(COLLECTION_CLIENTS, client_id, {
            "meta_phone_number_id": phone_number_id,
            "meta_access_token":    access_token,
            "whatsapp_number":      display_number,
            "wa_verified_name":     verified_name,
            "wa_connected":         True,
            "wa_connected_at":      datetime.utcnow().isoformat(),
            "updated_at":           datetime.utcnow().isoformat(),
        })
        # Also update users collection
        update_doc("users", client_id, {
            "wa_connected":    True,
            "whatsapp_number": display_number,
            "meta_phone_number_id": phone_number_id,
            "updated_at":      datetime.utcnow().isoformat(),
        })
        print(f"✅ WA connected: {display_number} → client {client_id}")
        return {"success": True, "number": display_number, "name": verified_name}
    except Exception as e:
        return {"success": False, "error": str(e)}

def disconnect_whatsapp(client_id: str):
    """Dashboard → 'Disconnect' button."""
    now = datetime.utcnow().isoformat()
    for col in [COLLECTION_CLIENTS, "users"]:
        update_doc(col, client_id, {
            "meta_phone_number_id": None,
            "meta_access_token":    None,
            "whatsapp_number":      None,
            "wa_connected":         False,
            "updated_at":           now,
        })

def list_all_clients(active_only: bool = True) -> list:
    filters = [("active", "==", True)] if active_only else []
    return query_docs(COLLECTION_CLIENTS, filters=filters)
