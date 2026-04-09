import frappe
import requests
import json
import time
import re
from frappe import _
from frappe.utils.pdf import get_pdf
from frappe.utils import fmt_money

# --- CONFIGURATION ---
APP_ID = ""
APP_SECRET = ""
APP_TOKEN = ""

# Table IDs
TABLE_SALES_MAIN = ""
TABLE_SALES_ITEMS = ""
TABLE_PAYMENT = ""
TABLE_PURCHASE_MAIN = ""
TABLE_PURCHASE_ITEMS = ""
TABLE_EXPENSE = ""
TABLE_EXPENSE_ITEMS = ""

# --- HELPER FUNCTIONS ---

def clean_html(raw_html):
    if not raw_html: return ""
    cleanr = re.compile('<.*?>')
    cleantext = re.sub(cleanr, '', str(raw_html))
    return cleantext.strip()

def get_lark_token():
    auth_url = "https://open.larksuite.com/open-apis/auth/v3/tenant_access_token/internal"
    res = requests.post(auth_url, json={"app_id": APP_ID, "app_secret": APP_SECRET})
    return res.json().get("tenant_access_token")

def get_erp_link(doctype, docname):
    return f"{frappe.utils.get_url()}/app/{doctype.lower().replace(' ', '-')}/{docname}"

def upload_pdf_to_lark(doc, token):
    try:
        html = frappe.get_print(doc.doctype, doc.name)
        pdf_content = get_pdf(html)
        if not pdf_content: return None
        upload_url = "https://open.larksuite.com/open-apis/drive/v1/medias/upload_all"
        headers = {"Authorization": f"Bearer {token}"}
        params = {"file_name": f"{doc.name}.pdf", "parent_type": "bitable_file", "parent_node": APP_TOKEN, "size": len(pdf_content)}
        files = {'file': (f"{doc.name}.pdf", pdf_content, 'application/pdf')}
        response = requests.post(upload_url, headers=headers, data=params, files=files)
        res_data = response.json()
        return res_data.get("data", {}).get("file_token") if res_data.get("code") == 0 else None
    except Exception: return None

def upsert_lark_record(table_id, field_name, doc_name, fields, token):
    url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    search_query = {"filter": {"conjunction": "and", "conditions": [{"field_name": field_name, "operator": "is", "value": [doc_name]}]}}
    search_res = requests.post(f"{url}/search", json=search_query, headers=headers).json()
    items = search_res.get("data", {}).get("items", [])
    if items:
        record_id = items[0].get("record_id")
        return requests.put(f"{url}/{record_id}", json={"fields": fields}, headers=headers).json()
    return requests.post(url, json={"fields": fields}, headers=headers).json()

def clear_and_sync_items(table_id, parent_field_name, doc_name, item_records, token):
    url = f"https://open.larksuite.com/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{table_id}/records"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    search_query = {"filter": {"conjunction": "and", "conditions": [{"field_name": parent_field_name, "operator": "is", "value": [doc_name]}]}}
    search_res = requests.post(f"{url}/search", json=search_query, headers=headers).json()
    items = search_res.get("data", {}).get("items", [])
    if items:
        record_ids = [i.get("record_id") for i in items]
        requests.post(f"{url}/batch_delete", json={"records": record_ids}, headers=headers)
    if item_records:
        requests.post(f"{url}/batch_create", json={"records": item_records}, headers=headers)

# --- CORE SYNC FUNCTIONS ---

def sync_expense(doc_name, **kwargs):
    time.sleep(1) 
    try:
        doc = frappe.get_doc("Expense Claim", doc_name)
        token = get_lark_token()
        file_token = upload_pdf_to_lark(doc, token)
        lark_status = "Paid" if doc.status == "Paid" else "Unpaid"
        reimbursed = float(doc.get("total_amount_reimbursed") or 0.0)
        advance = float(doc.get("total_advance_amount") or 0.0)
        desc_summary = "\n".join([f"- {d.expense_type}: {clean_html(d.description) or 'No description'} (Rs.{fmt_money(d.amount)})" for d in doc.expenses])
        m_fields = {
            "Claim ID": {"text": str(doc.name), "link": get_erp_link("Expense Claim", doc.name)},
            "Employee": str(doc.employee_name or doc.employee),
            "Expense Date": int(frappe.utils.get_datetime(doc.posting_date).timestamp() * 1000),
            "Description": desc_summary,
            "Total Amount": float(doc.total_claimed_amount),
            "Paid Amount": reimbursed,
            "Advance Amount": advance,
            "Status": lark_status
        }
        if file_token: m_fields["ERP Attachment"] = [{"file_token": file_token}]
        upsert_lark_record(TABLE_EXPENSE, "Claim ID", doc.name, m_fields, token)
        item_records = [{"fields": {"Claim ID": str(doc.name), "Expense Type": str(d.expense_type), "Date": int(frappe.utils.get_datetime(d.expense_date).timestamp() * 1000), "Amount": float(d.amount), "Description": clean_html(d.description)}} for d in doc.expenses]
        clear_and_sync_items(TABLE_EXPENSE_ITEMS, "Claim ID", doc.name, item_records, token)
    except Exception: frappe.log_error(frappe.get_traceback(), f"Lark Expense Fail: {doc_name}")

def sync_invoice(doc_name, **kwargs):
    time.sleep(1)
    try:
        doc = frappe.get_doc("Sales Invoice", doc_name)
        token = get_lark_token()
        file_token = upload_pdf_to_lark(doc, token)
        lark_status = "Paid" if doc.status == "Paid" else "Unpaid"
        items_summary = "\n".join([f"- {i.item_name or i.item_code} ({i.qty} x Rs.{fmt_money(i.rate)} = Rs.{fmt_money(i.amount)})" for i in doc.items])
        fields = {
            "Order ID": {"text": str(doc.name), "link": get_erp_link("Sales Invoice", doc.name)}, 
            "Customer": str(doc.customer), 
            "Total Amount": float(doc.grand_total),
            "Outstanding Amount": float(doc.get("outstanding_amount") or 0.0),
            "Items Detail": items_summary,
            "Date": int(frappe.utils.get_datetime(doc.posting_date).timestamp() * 1000),
            "Status": lark_status
        }
        if file_token: fields["ERP Attachment"] = [{"file_token": file_token}]
        upsert_lark_record(TABLE_SALES_MAIN, "Order ID", doc.name, fields, token)
        item_records = [{"fields": {"Order ID": str(doc.name), "Date": int(frappe.utils.get_datetime(doc.posting_date).timestamp() * 1000), "Item": str(i.item_name or i.item_code), "Qty": float(i.qty), "Rate": float(i.rate), "Amount": float(i.amount)}} for i in doc.items]
        clear_and_sync_items(TABLE_SALES_ITEMS, "Order ID", doc.name, item_records, token)
    except Exception: frappe.log_error(frappe.get_traceback(), f"Lark Sales Fail: {doc_name}")

def sync_purchase(doc_name, **kwargs):
    time.sleep(1)
    try:
        doc = frappe.get_doc("Purchase Invoice", doc_name)
        token = get_lark_token()
        file_token = upload_pdf_to_lark(doc, token)
        lark_status = "Paid" if doc.status == "Paid" else "Unpaid"
        items_summary = "\n".join([f"- {i.item_name or i.item_code} ({i.qty} x Rs.{fmt_money(i.rate)} = Rs.{fmt_money(i.amount)})" for i in doc.items])
        fields = {
            "Purchase ID": {"text": str(doc.name), "link": get_erp_link("Purchase Invoice", doc.name)}, 
            "Supplier": str(doc.supplier), 
            "Grand Total": float(doc.grand_total),
            "Outstanding Amount": float(doc.get("outstanding_amount") or 0.0),
            "Posting Date": int(frappe.utils.get_datetime(doc.posting_date).timestamp() * 1000),
            "Items Detail": items_summary,
            "Status": lark_status
        }
        if file_token: fields["ERP Attachment"] = [{"file_token": file_token}]
        upsert_lark_record(TABLE_PURCHASE_MAIN, "Purchase ID", doc.name, fields, token)
        item_records = [{"fields": {"Purchase ID": str(doc.name), "Date": int(frappe.utils.get_datetime(doc.posting_date).timestamp() * 1000), "Item": str(i.item_name or i.item_code), "Qty": float(i.qty), "Rate": float(i.rate), "Amount": float(i.amount)}} for i in doc.items]
        clear_and_sync_items(TABLE_PURCHASE_ITEMS, "Purchase ID", doc.name, item_records, token)
    except Exception: frappe.log_error(frappe.get_traceback(), f"Lark Purchase Fail: {doc_name}")

def sync_payment(doc_name, **kwargs):
    time.sleep(1)
    try:
        doc = frappe.get_doc("Payment Entry", doc_name)
        token = get_lark_token()
        file_token = upload_pdf_to_lark(doc, token)
        ref_id = doc.references[0].reference_name if doc.references else ""
        fields = {
            "Payment ID": {"text": str(doc.name), "link": get_erp_link("Payment Entry", doc.name)},
            "Party": str(doc.party),
            "Party Type": str(doc.party_type),
            "Amount Paid": float(doc.paid_amount),
            "Payment Date": int(frappe.utils.get_datetime(doc.posting_date).timestamp() * 1000),
            "Mode of Payment": str(doc.mode_of_payment),
            "Reference": str(ref_id),
            "Status": "Submitted"
        }
        if file_token: fields["ERP Attachment"] = [{"file_token": file_token}]
        upsert_lark_record(TABLE_PAYMENT, "Payment ID", doc.name, fields, token)
        for ref in doc.references:
            if ref.reference_doctype == "Sales Invoice": sync_invoice(ref.reference_name)
            elif ref.reference_doctype == "Purchase Invoice": sync_purchase(ref.reference_name)
            elif ref.reference_doctype == "Expense Claim": sync_expense(ref.reference_name)
    except Exception: frappe.log_error(frappe.get_traceback(), f"Lark Payment Fail: {doc_name}")

# --- CANCELLATION & BACKGROUND HANDLERS ---

def handle_cancel(doc, handler=None):
    """Updates Lark status to Cancelled and refreshes linked invoices if it was a payment."""
    try:
        token = get_lark_token()
        mapping = {
            "Sales Invoice": (TABLE_SALES_MAIN, "Order ID"),
            "Payment Entry": (TABLE_PAYMENT, "Payment ID"),
            "Purchase Invoice": (TABLE_PURCHASE_MAIN, "Purchase ID"),
            "Expense Claim": (TABLE_EXPENSE, "Claim ID")
        }
        if doc.doctype in mapping:
            table_id, key_field = mapping[doc.doctype]
            upsert_lark_record(table_id, key_field, doc.name, {"Status": "Cancelled"}, token)
            
            # If a payment is cancelled, invoices go back to 'Unpaid'
            if doc.doctype == "Payment Entry":
                for ref in doc.references:
                    if ref.reference_doctype == "Sales Invoice": sync_invoice(ref.reference_name)
                    elif ref.reference_doctype == "Purchase Invoice": sync_purchase(ref.reference_name)
                    elif ref.reference_doctype == "Expense Claim": sync_expense(ref.reference_name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"Lark Cancel Fail: {doc.name}")

def enqueue_journal_entry_sync(doc, handler=None):
    """Triggers invoice sync when Journal Entries are submitted or cancelled."""
    # Check accounts for references to relevant invoices
    synced_docs = set()
    for row in doc.get("accounts", []):
        if row.reference_type and row.reference_name:
            ref_key = (row.reference_type, row.reference_name)
            if ref_key not in synced_docs:
                if row.reference_type == "Sales Invoice":
                    frappe.enqueue('lark_integration.api.sync_invoice', doc_name=row.reference_name, queue='long', enqueue_after_commit=True)
                elif row.reference_type == "Purchase Invoice":
                    frappe.enqueue('lark_integration.api.sync_purchase', doc_name=row.reference_name, queue='long', enqueue_after_commit=True)
                elif row.reference_type == "Expense Claim":
                    frappe.enqueue('lark_integration.api.sync_expense', doc_name=row.reference_name, queue='long', enqueue_after_commit=True)
                synced_docs.add(ref_key)

# --- HOOKS WRAPPERS ---

def enqueue_lark_sync(doc, handler=None):
    if doc.docstatus == 1: frappe.enqueue('lark_integration.api.sync_invoice', doc_name=doc.name, queue='long', enqueue_after_commit=True)

def enqueue_payment_sync(doc, handler=None):
    if doc.docstatus == 1: frappe.enqueue('lark_integration.api.sync_payment', doc_name=doc.name, queue='long', enqueue_after_commit=True)

def enqueue_purchase_sync(doc, handler=None):
    if doc.docstatus == 1: frappe.enqueue('lark_integration.api.sync_purchase', doc_name=doc.name, queue='long', enqueue_after_commit=True)

def enqueue_expense_sync(doc, handler=None):
    if doc.docstatus == 1: frappe.enqueue('lark_integration.api.sync_expense', doc_name=doc.name, queue='long', enqueue_after_commit=True)

# --- BULK SYNC LOGIC ---

def bulk_sync_from_date(start_date):
    if isinstance(start_date, (list, tuple)): start_date = start_date[0]
    doctypes = {"Sales Invoice": sync_invoice, "Purchase Invoice": sync_purchase, "Expense Claim": sync_expense, "Payment Entry": sync_payment}
    for dt, sync_func in doctypes.items():
        docs = frappe.get_all(dt, filters={"posting_date": [">=", start_date], "docstatus": 1}, pluck="name")
        for name in docs: sync_func(name)
