app_name = "lark_integration"
app_title = "Lark Integration"
app_publisher = "Maxfu"
app_description = "Seamless integration between ERPNext and Lark Suite (Bitable, Tasks, Calendar, Drive, and Approvals)."
app_email = "hello@europlast.pk"
app_license = "mit"

doc_events = {
    "*": {
        "on_update": [
            "lark_integration.api.handle_universal_update",
            "lark_integration.api.trigger_lark_approval_globally"
        ],
        "on_submit": [
            "lark_integration.api.enqueue_universal_sync",
            "lark_integration.api.trigger_lark_approval_globally"
        ],
        "on_cancel": "lark_integration.api.handle_cancel",
        "on_update_after_submit": "lark_integration.api.handle_update_after_submit"
    },
    "Journal Entry": {
        "on_submit": "lark_integration.api.enqueue_journal_entry_sync",
        "on_cancel": "lark_integration.api.enqueue_journal_entry_sync"
    },
    "File": {
        "on_update": "lark_integration.api.handle_file_attach",
        "on_trash": "lark_integration.api.handle_file_delete"
    },
    "ToDo": {
        "before_insert": "lark_integration.api.handle_todo_before_insert",
        "on_update": "lark_integration.api.sync_todo_to_lark",
        "on_trash": "lark_integration.api.delete_lark_task"
    },
    "Event": {
        "on_update": "lark_integration.api.sync_event_to_lark",
        "on_trash": "lark_integration.api.delete_lark_event"
    },
    "Lark Integration Settings": {
        "on_update": "lark_integration.api.clear_lark_cache"
    },
    "Lark Sync Document": {
        "on_update": "lark_integration.api.clear_lark_cache",
        "on_trash": "lark_integration.api.clear_lark_cache"
    },
    "Lark Task List": {
        "on_update": "lark_integration.api.clear_lark_cache",
        "on_trash": "lark_integration.api.delete_lark_task_list"
    },
    "Lark Notification": {
        "on_update": "lark_integration.api.clear_lark_cache",
        "on_trash": "lark_integration.api.clear_lark_cache"
    },
    "Lark Approval Mapping": {
        "on_update": "lark_integration.api.clear_lark_cache",
        "on_trash": "lark_integration.api.clear_lark_cache"
    }
}

scheduler_events = {
    "all": [
        "lark_integration.api.pull_lark_tasks",
        "lark_integration.api.pull_lark_calendar_events",
        "lark_integration.api.process_lark_sync_batches"
    ],
    "hourly": [
        "lark_integration.api.run_backup_scheduler"
    ],
    "daily": [
        "lark_integration.api.sync_overdue_documents",
        "lark_integration.api.lark_scheduled_notifications",
        "lark_integration.api.clear_old_lark_logs",
        "lark_integration.api.clear_old_sync_queue_records"
    ]
}

doctype_js = {
    "Event": "public/js/event.js",
    "ToDo": "public/js/todo.js"
}

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
			"insert_after": "data",
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


after_install = "lark_integration.setup.after_install"
after_migrate = "lark_integration.setup.after_migrate"
