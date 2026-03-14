app_name = "lark_integration"
app_title = "Lark Integration"
app_publisher = "Your Name"
app_description = "Syncs ERPNext documents to Lark Bitable"
app_email = "your@email.com"
app_license = "mit"

doc_events = {
    "*": {
        "on_update": "lark_integration.api.handle_universal_update",
        "on_submit": "lark_integration.api.enqueue_universal_sync",
        "on_cancel": "lark_integration.api.handle_cancel",
        "on_update_after_submit": "lark_integration.api.enqueue_universal_sync"
    },
    "Journal Entry": {
        "on_submit": "lark_integration.api.enqueue_journal_entry_sync",
        "on_cancel": "lark_integration.api.enqueue_journal_entry_sync"
    },
    "Purchase Order": {
        "on_update": "lark_integration.api.create_lark_approval_instance",
        "on_submit": "lark_integration.api.create_lark_approval_instance"
    },
    "File": {
        "on_update": "lark_integration.api.handle_file_attach",
        "on_trash": "lark_integration.api.handle_file_delete"
    },
    "ToDo": {
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
    }
}

scheduler_events = {
    "all": [
        "lark_integration.api.pull_lark_tasks",
        "lark_integration.api.pull_lark_calendar_events"
    ],
    "hourly": [
        "lark_integration.api.run_backup_scheduler"
    ],
    "daily": [
        "lark_integration.api.sync_overdue_documents"
    ]
}

doctype_js = {
    "Event": "public/js/event.js",
    "ToDo": "public/js/todo.js"
}
