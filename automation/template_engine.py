"""
template_engine.py — Keyword match karke reply generate karo
Hit count bhi track karta hai (analytics ke liye)
"""
from typing import Optional, Tuple
from database.db import query_docs, update_doc
from config import COLLECTION_TEMPLATES
from automation.keyword_matcher import find_best_template
from datetime import datetime

def render_template(body: str, lead: dict, client: dict) -> str:
    """Placeholders replace karo: {name}, {business}, {phone}"""
    replacements = {
        "{name}":     lead.get("name") or "there",
        "{phone}":    lead.get("phone", ""),
        "{business}": client.get("business_name", ""),
        "{industry}": client.get("industry", ""),
    }
    for k, v in replacements.items():
        body = body.replace(k, str(v))
    return body

def process_message(
    client_id: str, incoming_text: str, lead: dict, client: dict
) -> Tuple[Optional[str], Optional[str]]:
    """
    Webhook se call hota hai har incoming message pe.
    Returns: (reply_text, template_id) or (None, None)
    """
    templates = query_docs(COLLECTION_TEMPLATES, filters=[
        ("client_id", "==", client_id), ("active", "==", True)
    ])
    if not templates:
        return None, None

    matched = find_best_template(incoming_text, templates)
    if not matched:
        return None, None

    reply = render_template(matched["message_body"], lead, client)

    # Track hit count for analytics
    try:
        current_hits = matched.get("hit_count", 0)
        update_doc(COLLECTION_TEMPLATES, matched["id"], {
            "hit_count":  current_hits + 1,
            "last_used":  datetime.utcnow().isoformat(),
        })
    except Exception:
        pass

    return reply, matched.get("id")
