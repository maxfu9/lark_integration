app_name = "lark_integration"
app_title = "Lark Integration"
app_publisher = "Your Name"
app_description = "Syncs ERPNext documents to Lark Bitable"
app_email = "your@email.com"
app_license = "mit"

doc_events = {
    "Sales Invoice": {
        "on_submit": "lark_integration.api.enqueue_lark_sync",
        "on_cancel": "lark_integration.api.handle_cancel"
    },
    "Payment Entry": {
        "on_submit": "lark_integration.api.enqueue_payment_sync",
        "on_cancel": "lark_integration.api.handle_cancel"
    },
    "Purchase Invoice": {
        "on_submit": "lark_integration.api.enqueue_purchase_sync",
        "on_cancel": "lark_integration.api.handle_cancel"
    },
    "Expense Claim": {
        "on_submit": "lark_integration.api.enqueue_expense_sync",
        "on_cancel": "lark_integration.api.handle_cancel"
    },
    "Journal Entry": {
        "on_submit": "lark_integration.api.enqueue_journal_entry_sync",
        "on_cancel": "lark_integration.api.enqueue_journal_entry_sync"
    }
}