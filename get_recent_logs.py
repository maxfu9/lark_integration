import frappe
from lark_integration.lark_integration.api import _build_doc_item_summary

def test():
    try:
        doc = frappe.get_doc("Sales Invoice", frappe.get_all("Sales Invoice", limit=1)[0].name)
        mapping = {
            "enable_item_summary": 1,
            "summary_child_table": "items",
            "summary_row_template": "- {item_name} {qty} x {rate} = {net_amount}",
            "summary_lark_field": "Item Details"
        }
        print("Testing template formatting:")
        summary = _build_doc_item_summary(doc, mapping)
        print(f"Summary generated:\n{summary}")
    except Exception as e:
        import traceback
        traceback.print_exc()
