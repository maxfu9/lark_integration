import frappe
from lark_integration.lark_integration.api import sync_universal

def test():
    try:
        # Assuming there is a Purchase Invoice, Sales Invoice, or Expense Claim
        docs = frappe.get_all("Sales Invoice", filters={"docstatus": 1}, limit=1, order_by="creation desc")
        if docs:
            print(f"Testing Sync for Sales Invoice: {docs[0].name}")
            sync_universal("Sales Invoice", docs[0].name)
            print("Successfully executed sync_universal for Sales Invoice.")
        else:
            print("No submitted Sales Invoices found to test.")
    except Exception as e:
        import traceback
        traceback.print_exc()
