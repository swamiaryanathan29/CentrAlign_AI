"""
Tool definitions for the AI agent.
Each tool is a Python function that the LangGraph agent can call.
Tools are annotated with a clear docstring — this is what the LLM reads.
"""
import json
import os
import glob
import httpx
from langchain_core.tools import tool

ERP_BASE = os.getenv("ERP_BASE_URL", "http://localhost:8001")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data", "invoices")

# ─────────────────────────────────────────────
# TOOL 1: List available invoices
# ─────────────────────────────────────────────
@tool
def list_available_invoices() -> str:
    """
    List all invoice files available in the local data store.
    Returns a JSON list of invoice filenames and their invoice_id + company fields.
    Use this first to discover what invoices exist before reading one.
    """
    results = []
    pattern = os.path.join(DATA_DIR, "*.json")
    files = glob.glob(pattern)
    for f in files:
        try:
            with open(f) as fh:
                data = json.load(fh)
            results.append({
                "filename": os.path.basename(f),
                "invoice_id": data.get("invoice_id"),
                "company": data.get("company"),
                "vendor": data.get("vendor"),
                "amount": data.get("amount"),
                "due_date": data.get("due_date"),
                "status": data.get("status"),
            })
        except Exception as e:
            results.append({"filename": os.path.basename(f), "error": str(e)})
    return json.dumps(results, indent=2)


# ─────────────────────────────────────────────
# TOOL 2: Read a specific invoice
# ─────────────────────────────────────────────
@tool
def read_invoice(filename: str) -> str:
    """
    Read and return the full contents of a specific invoice file.
    
    Args:
        filename: The name of the invoice file (e.g. 'invoice_001.json').
                  Use list_available_invoices() first to discover filenames.

    Returns:
        Full invoice JSON as a string, including amount, due_date, vendor, line items, etc.
    """
    path = os.path.join(DATA_DIR, filename)
    if not os.path.exists(path):
        return json.dumps({"error": f"File not found: {filename}"})
    try:
        with open(path) as f:
            data = json.load(f)
        return json.dumps(data, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─────────────────────────────────────────────
# TOOL 3: Enter invoice into ERP system
# ─────────────────────────────────────────────
@tool
def enter_invoice_into_erp(
    invoice_id: str,
    vendor: str,
    company: str,
    amount: float,
    currency: str,
    due_date: str,
    notes: str = "",
) -> str:
    """
    Enter an invoice into the company's ERP (Accounts Payable) system.
    This creates a new payable record that will go through the approval workflow.

    Args:
        invoice_id: The invoice identifier (e.g. 'INV-2024-001')
        vendor: Name of the vendor/supplier
        company: Company that received the invoice
        amount: Invoice amount as a number (no currency symbols)
        currency: ISO currency code (e.g. 'USD')
        due_date: Payment due date in YYYY-MM-DD format
        notes: Optional notes about the invoice

    Returns:
        JSON with the created ERP record ID and status.
    """
    try:
        resp = httpx.post(
            f"{ERP_BASE}/payables",
            json={
                "invoice_id": invoice_id,
                "vendor": vendor,
                "company": company,
                "amount": amount,
                "currency": currency,
                "due_date": due_date,
                "notes": notes,
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        return json.dumps(resp.json(), indent=2)
    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"ERP returned {e.response.status_code}: {e.response.text}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─────────────────────────────────────────────
# TOOL 4: Verify ERP entry
# ─────────────────────────────────────────────
@tool
def verify_erp_entry(record_id: str) -> str:
    """
    Verify that a payable record exists and is correct in the ERP system.
    Use this after entering an invoice to confirm the data was saved correctly.

    Args:
        record_id: The ERP record ID returned when the payable was created (e.g. 'AP-XXXXXXXX')

    Returns:
        Full payable record JSON, or an error if not found.
    """
    try:
        resp = httpx.get(f"{ERP_BASE}/payables/{record_id}", timeout=10.0)
        resp.raise_for_status()
        return json.dumps(resp.json(), indent=2)
    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"ERP returned {e.response.status_code}: {e.response.text}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─────────────────────────────────────────────
# TOOL 5: List all ERP payables
# ─────────────────────────────────────────────
@tool
def list_erp_payables() -> str:
    """
    List all payable records currently in the ERP system.
    Use this to check what has already been entered and avoid duplicates.

    Returns:
        JSON list of all payables with their status.
    """
    try:
        resp = httpx.get(f"{ERP_BASE}/payables", timeout=10.0)
        resp.raise_for_status()
        return json.dumps(resp.json(), indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─────────────────────────────────────────────
# TOOL 6: Update payable status
# ─────────────────────────────────────────────
@tool
def update_payable_status(record_id: str, status: str) -> str:
    """
    Update the status of a payable record in the ERP system.
    Valid statuses: 'pending_approval', 'approved', 'paid', 'rejected', 'on_hold'

    Args:
        record_id: The ERP record ID (e.g. 'AP-XXXXXXXX')
        status: New status string

    Returns:
        Updated record JSON.
    """
    try:
        resp = httpx.patch(
            f"{ERP_BASE}/payables/{record_id}",
            json={"status": status, "updated_by": "AI Agent"},
            timeout=10.0,
        )
        resp.raise_for_status()
        return json.dumps(resp.json(), indent=2)
    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"ERP returned {e.response.status_code}: {e.response.text}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ─────────────────────────────────────────────
# TOOL 7: Search invoice by company
# ─────────────────────────────────────────────
@tool
def find_invoice_by_company(company_name: str) -> str:
    """
    Search available invoices for a specific company name (case-insensitive partial match).

    Args:
        company_name: Company name or partial name to search for (e.g. 'Acme', 'TechSupplies')

    Returns:
        JSON list of matching invoices.
    """
    results = []
    pattern = os.path.join(DATA_DIR, "*.json")
    files = glob.glob(pattern)
    for f in files:
        try:
            with open(f) as fh:
                data = json.load(fh)
            if company_name.lower() in data.get("company", "").lower() or \
               company_name.lower() in data.get("vendor", "").lower():
                results.append({
                    "filename": os.path.basename(f),
                    **data
                })
        except Exception:
            pass
    if not results:
        return json.dumps({"found": False, "message": f"No invoices found matching '{company_name}'"})
    return json.dumps({"found": True, "matches": results, "count": len(results)}, indent=2)


# ─────────────────────────────────────────────
# All tools exported
# ─────────────────────────────────────────────
ALL_TOOLS = [
    list_available_invoices,
    read_invoice,
    enter_invoice_into_erp,
    verify_erp_entry,
    list_erp_payables,
    update_payable_status,
    find_invoice_by_company,
]
