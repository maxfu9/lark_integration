import frappe
import traceback

def test_delete():
    target = "ACC-SINV-2026-00036"
    try:
        frappe.delete_doc("Sales Invoice", target)
        print(f"SUCCESS: Deleted {target}")
    except Exception:
        err = traceback.format_exc()
        print(f"ERROR: Failed to delete {target}")
        print(err)

if __name__ == "__main__":
    test_delete()
