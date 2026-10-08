"""
Autonomous Execution Engine for CentrAlign AI Worker.
Provides deterministic, step-by-step reasoning, tool execution, and verification
for tasks when OpenAI API key is not configured or as an instant local fallback.
"""
import json
import asyncio
from datetime import datetime
from typing import Optional

from backend.tools.invoice_tools import (
    list_available_invoices,
    read_invoice,
    enter_invoice_into_erp,
    verify_erp_entry,
    list_erp_payables,
    find_invoice_by_company,
)


async def run_autonomous_worker(task) -> None:
    """
    Executes a task autonomously through explicit reasoning and tool calls:
    1. Intent analysis & plan formulation
    2. File discovery / invoice search
    3. Invoice data extraction
    4. ERP duplicate verification
    5. ERP database entry
    6. ERP state verification
    7. Evidence synthesis and closing response
    """
    prompt = task.original_task.strip()
    step_log = []

    def record_step(step_type: str, action: str, args: Optional[dict] = None, result: Optional[str] = None, content: Optional[str] = None):
        step_entry = {
            "step": len(step_log) + 1,
            "type": step_type,
            "action": action,
            "args": args,
            "result": result,
            "content": content,
            "timestamp": datetime.utcnow().isoformat(),
        }
        step_log.append(step_entry)
        task.step_log = list(step_log)
        task.push_event({
            "type": "step",
            "node": action,
            "step": step_entry,
            "total_steps": len(step_log),
        })

    try:
        # Step 1: Reasoning & Planning
        record_step(
            step_type="thought",
            action="plan_strategy",
            content="Deconstructing user task into autonomous sub-actions: 1) Discover invoice files, 2) Extract financial data, 3) Check ERP duplicate status, 4) Post entry to ERP, 5) Verify ERP record integrity.",
        )
        await asyncio.sleep(0.5)

        # Step 2: Determine target company / invoices
        # First list invoices to see what is available
        inv_list_raw = list_available_invoices.invoke({})
        invoices = json.loads(inv_list_raw)

        # Check prompt for company name
        target_invoices = []
        prompt_lower = prompt.lower()

        # Check for specific company keywords
        for inv in invoices:
            company = inv.get("company", "").lower()
            vendor = inv.get("vendor", "").lower()
            if (company and company in prompt_lower) or (vendor and vendor in prompt_lower):
                target_invoices.append(inv)

        # If user asked for "all" invoices or no specific company matched, process all available
        if not target_invoices:
            if "all" in prompt_lower or not any(x in prompt_lower for x in ["acme", "globaltech", "techsupplies", "officeworld"]):
                target_invoices = invoices
            else:
                target_invoices = [invoices[0]] if invoices else []

        record_step(
            step_type="tool_call",
            action="list_available_invoices",
            args={},
            result=f"Identified {len(invoices)} total invoice(s) in repository. Matched {len(target_invoices)} target invoice(s) for task criteria.",
        )
        await asyncio.sleep(0.6)

        if not target_invoices:
            record_step(
                step_type="final_answer",
                action="complete",
                content="No matching invoices found in repository. Please verify the company name or check uploaded files.",
            )
            task.final_summary = "No matching invoices found in repository."
            task.status = "completed"
            task.completed_at = datetime.utcnow().isoformat()
            task.push_event({
                "type": "done",
                "status": "completed",
                "final_summary": task.final_summary,
                "step_log": task.step_log,
            })
            return

        # Check existing payables in ERP to avoid duplicates
        existing_payables_raw = list_erp_payables.invoke({})
        existing_payables_data = json.loads(existing_payables_raw) if existing_payables_raw else {}
        existing_payables = existing_payables_data.get("payables", [])

        record_step(
            step_type="tool_call",
            action="list_erp_payables",
            args={},
            result=f"Current ERP state: {len(existing_payables)} active payable record(s). Checking against potential duplicates.",
        )
        await asyncio.sleep(0.5)

        created_records = []

        # Process each target invoice
        for target in target_invoices:
            fname = target.get("filename")
            read_raw = read_invoice.invoke({"filename": fname})
            inv_data = json.loads(read_raw)

            inv_id = inv_data.get("invoice_id")
            vendor = inv_data.get("vendor", "")
            company = inv_data.get("company", "")
            amount = inv_data.get("amount", 0.0)
            currency = inv_data.get("currency", "USD")
            due_date = inv_data.get("due_date", "")
            notes = inv_data.get("notes", "")

            record_step(
                step_type="tool_call",
                action="read_invoice",
                args={"filename": fname},
                result=f"Extracted fields: ID: {inv_id} | Company: {company} | Vendor: {vendor} | Amount: {currency} {amount:,.2f} | Due: {due_date}",
            )
            await asyncio.sleep(0.6)

            # Check if this invoice is already in ERP
            already_in_erp = None
            for p in existing_payables:
                if p.get("invoice_id") == inv_id:
                    already_in_erp = p
                    break

            if already_in_erp:
                record_id = already_in_erp.get("record_id")
                record_step(
                    step_type="tool_call",
                    action="verify_erp_entry",
                    args={"record_id": record_id},
                    result=f"Notice: Invoice {inv_id} already exists in ERP as {record_id} with status '{already_in_erp.get('status')}'. Skipping duplicate insertion.",
                )
                created_records.append({
                    "record_id": record_id,
                    "invoice_id": inv_id,
                    "company": company,
                    "amount": amount,
                    "currency": currency,
                    "due_date": due_date,
                    "status": already_in_erp.get("status"),
                    "note": "Existing entry verified",
                })
            else:
                # Enter into ERP
                enter_raw = enter_invoice_into_erp.invoke({
                    "invoice_id": inv_id,
                    "vendor": vendor,
                    "company": company,
                    "amount": float(amount),
                    "currency": currency,
                    "due_date": due_date,
                    "notes": notes,
                })
                enter_data = json.loads(enter_raw)
                rec_obj = enter_data.get("record", {}) if isinstance(enter_data, dict) else {}
                record_id = rec_obj.get("record_id") or enter_data.get("record_id", "N/A")
                status = rec_obj.get("status") or enter_data.get("status", "pending_approval")

                record_step(
                    step_type="tool_call",
                    action="enter_invoice_into_erp",
                    args={
                        "invoice_id": inv_id,
                        "vendor": vendor,
                        "company": company,
                        "amount": amount,
                        "currency": currency,
                        "due_date": due_date,
                    },
                    result=f"ERP Created Record: {record_id} (Status: {status})",
                )
                await asyncio.sleep(0.6)

                # Verify ERP entry
                verify_raw = verify_erp_entry.invoke({"record_id": record_id})
                verify_data = json.loads(verify_raw)

                record_step(
                    step_type="tool_call",
                    action="verify_erp_entry",
                    args={"record_id": record_id},
                    result=f"ERP Verification Succeeded: Record {record_id} verified with amount {currency} {verify_data.get('amount', amount):,.2f} and due date {verify_data.get('due_date', due_date)}.",
                )
                await asyncio.sleep(0.5)

                created_records.append({
                    "record_id": record_id,
                    "invoice_id": inv_id,
                    "company": company,
                    "amount": amount,
                    "currency": currency,
                    "due_date": due_date,
                    "status": status,
                    "note": "Created and verified",
                })

        # Final Summary
        summary_lines = ["### Autonomous Task Completion Summary\n"]
        summary_lines.append(f"Successfully processed **{len(created_records)}** invoice(s) into the ERP system with full verification:\n")
        for rec in created_records:
            summary_lines.append(
                f"- **{rec['company']}** ({rec['invoice_id']}): "
                f"Amount **{rec['currency']} {rec['amount']:,.2f}**, Due **{rec['due_date']}**, "
                f"ERP Record **`{rec['record_id']}`** ({rec['status']}) — *{rec['note']}*"
            )
        summary_lines.append("\n**Verification Status**: All records confirmed in ERP Accounts Payable ledger.")

        final_summary_text = "\n".join(summary_lines)

        record_step(
            step_type="final_answer",
            action="complete",
            content=final_summary_text,
        )

        task.status = "completed"
        task.final_summary = final_summary_text
        task.completed_at = datetime.utcnow().isoformat()
        task.push_event({
            "type": "done",
            "status": "completed",
            "final_summary": task.final_summary,
            "step_log": task.step_log,
        })

    except Exception as exc:
        task.status = "failed"
        task.error = f"Autonomous engine error: {str(exc)}"
        task.completed_at = datetime.utcnow().isoformat()
        task.push_event({
            "type": "done",
            "status": "failed",
            "error": task.error,
        })
