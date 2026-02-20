# Lark Integration for ERPNext

This app synchronizes ERPNext transactions (Sales Invoices, Purchase Invoices, Payment Entries, Expense Claims, and Journal Entries) to a Lark Bitable in real-time using Frappe Hooks and background workers.

## Features

- **Automated Sync**: Triggers on document submission (`on_submit`).
- **Cancellation Handling**: Automatically updates Lark records to "Cancelled" when a document is cancelled in ERPNext.
- **Journal Entry Support**: Detects invoice references within Journal Entries and updates the corresponding Invoice status/outstanding amount in Lark.
- **PDF Attachments**: Generates and uploads the ERPNext Print Format PDF directly to the Lark record.
- **Background Processing**: Uses `frappe.enqueue` to ensure the user interface remains fast.

## Configuration

Open `api.py` and update the following constants with your Lark App credentials:

* `APP_ID`: Your Lark App ID.
* `APP_SECRET`: Your Lark App Secret.
* `APP_TOKEN`: The Token/ID of your Lark Bitable.
* `TABLE_IDs`: Ensure the Table IDs match your specific Bitable tabs.

## Installation

1. Push this code to your GitHub repository.
2. In your bench environment:
   ```bash
   bench get-app [https://github.com/maxfu9/lark_integration.git](https://github.com/maxfu9/lark_integration.git)
   bench install-app lark_integration
   bench migrate
   bench restart