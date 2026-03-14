import frappe
from lark_integration.api import handle_file_attach

def run():
    recent_file = frappe.get_last_doc("File", filters={"attached_to_doctype": "Sales Invoice"})
    if recent_file:
        handle_file_attach(recent_file)
    else:
        print("No recent File found attached to a Sales Invoice")

run()
