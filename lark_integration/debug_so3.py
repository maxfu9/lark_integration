import frappe
from lark_integration.lark_integration.api import sync_universal, _get_sync_mapping

def test():
    try:
        # Assuming there is a Purchase Invoice, Sales Invoice, or Expense Claim
        docs = frappe.get_all("Sales Order", fields=["name", "docstatus"], limit=1, order_by="creation desc")
        if docs:
            doc_name = docs[0].name
            print(f"Testing Sync for Sales Order: {doc_name} (Status: {docs[0].docstatus})")
            
            mapping = _get_sync_mapping("Sales Order")
            if not mapping:
                print("Missing mapping for Sales Order!")
            else:
                print(f"Mapping found: {mapping}")
                
            sync_universal("Sales Order", doc_name)
            print("Successfully executed sync_universal for Sales Order.")
        else:
            print("No Sales Orders found to test.")
    except Exception as e:
        import traceback
        traceback.print_exc()
