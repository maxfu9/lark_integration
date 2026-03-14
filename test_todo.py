import frappe

def run():
    frappe.init(site="site1.local", sites_path="/Users/kashif/erpnext15-bench/sites")
    frappe.connect()
    try:
        t = frappe.get_doc({
            'doctype': 'ToDo',
            'description': 'Automated Test Script test 2'
        })
        t.insert()
        print(f"CREATED: {t.name}, LARK_DUE_TIME: {t.lark_due_time}, DATE: {t.date}")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error: {e}")
    finally:
        frappe.db.rollback()
        frappe.destroy()

if __name__ == "__main__":
    run()
