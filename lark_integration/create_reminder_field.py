import frappe

def run():
    try:
        if frappe.db.exists("Custom Field", "ToDo-lark_reminder_offset"):
            frappe.delete_doc("Custom Field", "ToDo-lark_reminder_offset")
            
        custom_field = frappe.get_doc({
            "doctype": "Custom Field",
            "dt": "ToDo",
            "fieldname": "lark_reminder_offset",
            "label": "Lark Reminder Offset",
            "fieldtype": "Select",
            "options": "0\n5\n10\n15\n30\n60\n120\n1440",
            "insert_after": "lark_remind_at_due",
            "depends_on": "eval:doc.lark_remind_at_due == 1",
            "description": "Minutes before due time to remind (0 = At due time, 1440 = 1 day before)",
            "default": "0"
        })
        custom_field.insert(ignore_permissions=True)
        print("Custom Field 'lark_reminder_offset' recreated successfully.")
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Error: {e}")
    finally:
        frappe.db.commit()
