import frappe
from lark_integration.api import _build_fields_payload, _get_sync_mapping, upsert_lark_record, get_lark_token
import json

def diagnostic():
    inv_name = "ACC-SINV-2026-00035" # Example from earlier
    doc = frappe.get_doc("Sales Invoice", inv_name)
    print(f"Invoice: {doc.name}")
    print(f"Status: {doc.status}")
    print(f"Outstanding: {doc.outstanding_amount}")
    print(f"Docstatus: {doc.docstatus}")
    
    mapping = _get_sync_mapping(doc.doctype)
    if not mapping:
        print("No mapping found")
        return
        
    fields = _build_fields_payload(doc, mapping)
    print("\nGenerated Fields Payload for Lark:")
    print(json.dumps(fields, indent=2))
    
    # Check if 'Outstanding Amount' is in fields
    lark_outstanding_field = None
    for f in mapping.get("custom_fields", []):
        if f.get("erp_field_path") == "outstanding_amount":
            lark_outstanding_field = f.get("lark_field")
            break
    
    print(f"\nLark Outstanding Field: {lark_outstanding_field}")
    if lark_outstanding_field:
        print(f"Value in payload: {fields.get(lark_outstanding_field)}")
    
    # Try the upsert manually and see what happens
    token = get_lark_token()
    print("\nAttempting Upsert...")
    res = upsert_lark_record(mapping["main_table_id"], mapping["key_field"], doc.name, fields, token, mapping["app_token"])
    print("Upsert Result:", res)

diagnostic()
