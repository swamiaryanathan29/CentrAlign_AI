"""
ERP Simulation — in-memory company accounting system.
Exposes REST endpoints that the AI agent's tools call.
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import uuid

erp_app = FastAPI(title="Simulated ERP System", version="1.0")

erp_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------- In-memory database -----------
_payables: dict[str, dict] = {}
_audit_log: list[dict] = []

class PayableCreate(BaseModel):
    invoice_id: str
    vendor: str
    company: str
    amount: float
    currency: str
    due_date: str
    notes: Optional[str] = ""

class PayableUpdate(BaseModel):
    status: str
    updated_by: Optional[str] = "AI Agent"

def _log(action: str, record_id: str, detail: str):
    _audit_log.append({
        "timestamp": datetime.utcnow().isoformat(),
        "action": action,
        "record_id": record_id,
        "detail": detail,
    })

# ----------- Endpoints -----------
@erp_app.get("/health")
def health():
    return {"status": "ok", "system": "ERP Sim v1.0"}

@erp_app.get("/payables")
def list_payables():
    return {"payables": list(_payables.values()), "count": len(_payables)}

@erp_app.get("/payables/{record_id}")
def get_payable(record_id: str):
    if record_id not in _payables:
        raise HTTPException(status_code=404, detail="Payable not found")
    return _payables[record_id]

@erp_app.post("/payables", status_code=201)
def create_payable(body: PayableCreate):
    # Idempotency: if invoice already exists, return existing
    for p in _payables.values():
        if p["invoice_id"] == body.invoice_id:
            return {"created": False, "record": p, "message": "Invoice already exists"}
    record_id = f"AP-{str(uuid.uuid4())[:8].upper()}"
    record = {
        "record_id": record_id,
        "invoice_id": body.invoice_id,
        "vendor": body.vendor,
        "company": body.company,
        "amount": body.amount,
        "currency": body.currency,
        "due_date": body.due_date,
        "notes": body.notes,
        "status": "pending_approval",
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    _payables[record_id] = record
    _log("CREATE", record_id, f"Invoice {body.invoice_id} entered by AI Agent")
    return {"created": True, "record": record, "message": "Payable created successfully"}

@erp_app.patch("/payables/{record_id}")
def update_payable(record_id: str, body: PayableUpdate):
    if record_id not in _payables:
        raise HTTPException(status_code=404, detail="Payable not found")
    _payables[record_id]["status"] = body.status
    _payables[record_id]["updated_at"] = datetime.utcnow().isoformat()
    _log("UPDATE", record_id, f"Status changed to {body.status} by {body.updated_by}")
    return {"updated": True, "record": _payables[record_id]}

@erp_app.get("/audit-log")
def get_audit_log():
    return {"log": _audit_log}

@erp_app.delete("/payables/{record_id}")
def delete_payable(record_id: str):
    if record_id not in _payables:
        raise HTTPException(status_code=404, detail="Payable not found")
    _log("DELETE", record_id, "Record deleted")
    del _payables[record_id]
    return {"deleted": True}
