import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def after_install():
    pass

def after_migrate():
    from lark_integration.api import warmup_lark_cache
    warmup_lark_cache()

def create_custom_fields_if_missing():
    """Ensure all required custom fields for Lark Integration exist."""
    custom_fields = {
        "User": [
            {
                "fieldname": "lark_user_id",
                "label": "Lark User ID",
                "fieldtype": "Data",
                "insert_after": "email",
                "print_hide": 1
            },
            {
                "fieldname": "lark_sync_token",
                "label": "Lark Sync Token",
                "fieldtype": "Data",
                "insert_after": "lark_user_id",
                "read_only": 1,
                "hidden": 1
            },
            {
                "fieldname": "lark_user_access_token",
                "label": "Lark User Access Token",
                "fieldtype": "Data",
                "insert_after": "lark_sync_token",
                "read_only": 1,
                "hidden": 1
            },
            {
                "fieldname": "lark_user_refresh_token",
                "label": "Lark User Refresh Token",
                "fieldtype": "Data",
                "insert_after": "lark_user_access_token",
                "read_only": 1,
                "hidden": 1
            },
            {
                "fieldname": "lark_user_token_expires_at",
                "label": "Lark User Token Expires At",
                "fieldtype": "Datetime",
                "insert_after": "lark_user_refresh_token",
                "read_only": 1,
                "hidden": 1
            }
        ],
        "ToDo": [
            {
                "fieldname": "lark_task_guid",
                "label": "Lark Task GUID",
                "fieldtype": "Data",
                "insert_after": "description",
                "read_only": 1,
                "print_hide": 1
            },
            {
                "fieldname": "lark_last_modified",
                "label": "Lark Last Modified",
                "fieldtype": "Data",
                "insert_after": "lark_task_guid",
                "read_only": 1,
                "hidden": 1
            },
            {
                "fieldname": "lark_remind_at_due",
                "label": "Alert",
                "fieldtype": "Check",
                "insert_after": "date",
                "default": "0"
            },
            {
                "fieldname": "lark_reminder_offset",
                "label": "Lark Reminder",
                "fieldtype": "Select",
                "options": "At due time\n5 minutes before\n15 minutes before\n30 minutes before\n1 hour before\n2 hours before\n1 day before\n2 days before\n1 week before",
                "insert_after": "lark_remind_at_due",
                "depends_on": "eval:doc.lark_remind_at_due"
            },
            {
                "fieldname": "lark_due_time",
                "label": "Lark Due Time",
                "fieldtype": "Time",
                "insert_after": "date",
                "print_hide": 1
            },
            {
                "fieldname": "lark_task_list",
                "label": "Lark Task List",
                "fieldtype": "Link",
                "options": "Lark Task List",
                "insert_after": "description"
            },
            {
                "fieldname": "lark_last_sync_hash",
                "label": "Lark Last Sync Hash",
                "fieldtype": "Data",
                "insert_after": "lark_task_list",
                "read_only": 1,
                "print_hide": 1,
                "hidden": 1
            }
        ],
        "Event": [
            {
                "fieldname": "lark_event_id",
                "label": "Lark Event ID",
                "fieldtype": "Data",
                "insert_after": "ends_on",
                "read_only": 1,
                "print_hide": 1
            },
            {
                "fieldname": "lark_calendar_id",
                "label": "Lark Calendar ID",
                "fieldtype": "Data",
                "insert_after": "lark_event_id",
                "read_only": 1,
                "print_hide": 1
            },
            {
                "fieldname": "lark_calendar",
                "label": "Lark Calendar",
                "fieldtype": "Link",
                "options": "Lark Calendar",
                "insert_after": "ends_on"
            },
            {
                "fieldname": "add_lark_meeting",
                "label": "Add Lark Meeting",
                "fieldtype": "Check",
                "insert_after": "lark_calendar",
                "default": "0"
            },
            {
                "fieldname": "lark_meeting_url",
                "label": "Lark Meeting URL",
                "fieldtype": "Data",
                "insert_after": "add_lark_meeting",
                "read_only": 1,
                "read_only_ones": 1
            },
            {
                "fieldname": "lark_sync_token",
                "label": "Lark Sync Token",
                "fieldtype": "Data",
                "insert_after": "lark_event_id",
                "read_only": 1,
                "hidden": 1
            },
            {
                "fieldname": "lark_last_sync_hash",
                "label": "Lark Last Sync Hash",
                "fieldtype": "Data",
                "insert_after": "lark_sync_token",
                "read_only": 1,
                "print_hide": 1,
                "hidden": 1
            }
        ]
    }
    
    # Dynamic Lark Record ID for all synced DocTypes
    try:
        if frappe.db.table_exists("Lark Sync Document"):
            synced_doctypes = frappe.get_all("Lark Sync Document", fields=["reference_doctype"])
            for sync_doc in synced_doctypes:
                dt = sync_doc.reference_doctype
                if dt not in custom_fields:
                    custom_fields[dt] = []
                
                # Check if it already has it or is in the list
                if not any(f.get("fieldname") == "lark_record_id" for f in custom_fields[dt]):
                    custom_fields[dt].append({
                        "fieldname": "lark_record_id",
                        "label": "Lark Record ID",
                        "fieldtype": "Data",
                        "insert_after": "status",
                        "read_only": 1,
                        "print_hide": 1,
                        "hidden": 1
                    })
                
                if not any(f.get("fieldname") == "lark_last_sync_hash" for f in custom_fields[dt]):
                    custom_fields[dt].append({
                        "fieldname": "lark_last_sync_hash",
                        "label": "Lark Last Sync Hash",
                        "fieldtype": "Data",
                        "insert_after": "lark_record_id",
                        "read_only": 1,
                        "print_hide": 1,
                        "hidden": 1
                    })
    except Exception:
        pass

    create_custom_fields(custom_fields, ignore_validate=True)
    frappe.db.commit()
