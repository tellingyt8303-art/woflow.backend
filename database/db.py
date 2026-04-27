"""
database/db.py — Firebase Firestore CRUD helpers
Saare modules ise use karte hain directly Firestore se baat karne ke liye
"""
import firebase_admin
from firebase_admin import credentials, firestore
from config import FIREBASE_CREDENTIALS_PATH, FIREBASE_DATABASE_URL
from typing import Optional

_db = None

def init_firebase():
    global _db
    if not firebase_admin._apps:
        cred = credentials.Certificate(FIREBASE_CREDENTIALS_PATH)
        firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DATABASE_URL})
    _db = firestore.client()
    return _db

def get_db():
    global _db
    if _db is None:
        init_firebase()
    return _db

def create_doc(collection: str, data: dict, doc_id: str = None) -> str:
    db = get_db()
    if doc_id:
        db.collection(collection).document(doc_id).set(data)
        return doc_id
    ref = db.collection(collection).add(data)
    return ref[1].id

def get_doc(collection: str, doc_id: str) -> Optional[dict]:
    db  = get_db()
    doc = db.collection(collection).document(doc_id).get()
    return {"id": doc.id, **doc.to_dict()} if doc.exists else None

def update_doc(collection: str, doc_id: str, data: dict):
    get_db().collection(collection).document(doc_id).update(data)

def delete_doc(collection: str, doc_id: str):
    get_db().collection(collection).document(doc_id).delete()

def query_docs(collection: str, filters: list = None, limit: int = 200) -> list:
    """
    filters: [("field", "operator", value), ...]
    e.g. [("client_id", "==", "abc"), ("status", "==", "new")]
    """
    db  = get_db()
    ref = db.collection(collection)
    if filters:
        for field, op, value in filters:
            ref = ref.where(field, op, value)
    docs = ref.limit(limit).stream()
    return [{"id": d.id, **d.to_dict()} for d in docs]

def get_all_docs(collection: str) -> list:
    db   = get_db()
    docs = db.collection(collection).stream()
    return [{"id": d.id, **d.to_dict()} for d in docs]
