from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum

class LeadStatus(str, Enum):
    new       = "new"
    contacted = "contacted"
    qualified = "qualified"
    converted = "converted"
    lost      = "lost"

class FollowupStatus(str, Enum):
    pending   = "pending"
    sent      = "sent"
    failed    = "failed"
    cancelled = "cancelled"

class MessageDirection(str, Enum):
    inbound  = "inbound"
    outbound = "outbound"

# ── Client / Business ─────────────────────────────────────────
class Client(BaseModel):
    id: Optional[str]               = None
    name: str
    email: str
    business_name: str
    industry: Optional[str]         = None
    phone: Optional[str]            = None
    active: bool                    = True
    # Meta Cloud API
    meta_phone_number_id: Optional[str] = None
    meta_access_token: Optional[str]    = None
    whatsapp_number: Optional[str]      = None
    wa_verified_name: Optional[str]     = None
    wa_connected: bool                  = False
    wa_connected_at: Optional[str]      = None
    # Plan
    plan: str                       = "trial"
    plan_expires: Optional[str]     = None
    firebase_uid: Optional[str]     = None
    created_at: str                 = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str                 = Field(default_factory=lambda: datetime.utcnow().isoformat())

# ── Lead ──────────────────────────────────────────────────────
class Lead(BaseModel):
    id: Optional[str]      = None
    client_id: str
    phone: str              # Meta format: "919876543210" (no +)
    name: Optional[str]    = None
    email: Optional[str]   = None
    status: LeadStatus      = LeadStatus.new
    source: str             = "whatsapp"
    notes: Optional[str]   = None
    tags: List[str]         = []
    created_at: str         = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str         = Field(default_factory=lambda: datetime.utcnow().isoformat())

# ── Message Log ───────────────────────────────────────────────
class MessageLog(BaseModel):
    id: Optional[str]              = None
    client_id: str
    lead_phone: str
    direction: MessageDirection
    body: str
    template_id: Optional[str]     = None
    meta_message_id: Optional[str] = None
    timestamp: str                  = Field(default_factory=lambda: datetime.utcnow().isoformat())

# ── Template ──────────────────────────────────────────────────
class Template(BaseModel):
    id: Optional[str]          = None
    client_id: str
    name: str
    trigger_keywords: List[str] = []
    message_body: str
    is_default: bool            = False
    active: bool                = True
    hit_count: int              = 0
    created_at: str             = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str             = Field(default_factory=lambda: datetime.utcnow().isoformat())

# ── Follow-up ─────────────────────────────────────────────────
class Followup(BaseModel):
    id: Optional[str]          = None
    client_id: str
    lead_phone: str
    template_id: Optional[str] = None
    message_body: str
    scheduled_at: str
    status: FollowupStatus      = FollowupStatus.pending
    attempt: int                = 1
    sent_at: Optional[str]     = None
    meta_message_id: Optional[str] = None
    created_at: str             = Field(default_factory=lambda: datetime.utcnow().isoformat())

# ── Auth ──────────────────────────────────────────────────────
class UserCreate(BaseModel):
    email: str
    password: str
    name: str
    business_name: str

class UserLogin(BaseModel):
    email: str
    password: str

# ── WhatsApp Connect ──────────────────────────────────────────
class WhatsAppConnectRequest(BaseModel):
    phone_number_id: str
    access_token: str

# ── Send Message ──────────────────────────────────────────────
class SendMessageRequest(BaseModel):
    to: str
    body: str

# ── Lead Status Update ────────────────────────────────────────
class LeadStatusUpdate(BaseModel):
    status: LeadStatus
    notes: Optional[str] = None

# ── Template Create/Update ────────────────────────────────────
class TemplateCreate(BaseModel):
    name: str
    trigger_keywords: List[str] = []
    message_body: str
    is_default: bool = False
    active: bool = True

# ── Follow-up Cancel ─────────────────────────────────────────
class FollowupAction(BaseModel):
    lead_phone: str
