# Lark Integration for ERPNext

A comprehensive two-way synchronization suite connecting ERPNext with Lark (Feishu). Supports Bitable, Drive, Tasks (ToDo), Calendar, and Automated Backups.

---

## 1. Core Integration Settings
Located in **Lark Integration Settings**.

### Authentication
- **Enabled**: Global master switch for all integration features.
- **App ID**: Your Lark Application ID (from Lark Developer Console).
- **App Secret**: Your Lark App Secret.

---

## 2. Lark Side Configuration
Before configuring ERPNext, you must set up your application in the [Lark Developer Console](https://open.larksuite.com/app).

### 1. Obtain Credentials
1. Log in to the console and select your app.
2. Go to **Credentials & Basic Information** to find your **App ID** and **App Secret**.

### 2. Required API Permissions
In the left sidebar, navigate to **Permission Administration** and enable the following scopes:

| Suite | Scopes Required | Why? |
| :--- | :--- | :--- |
| **Bitable** | `bitable:app` | Sync ERPNext records to Bitable. |
| **Drive** | `drive:drive` | Upload/Remove file attachments. |
| **Tasks** | `task:task:write`, `task:task:read` | Two-way ToDo synchronization. |
| **Calendar** | `calendar:calendar`, `calendar:calendar:readonly` | Two-way Event synchronization. |
| **Contact** | `contact:user.email:readonly`, `contact:contact.base:readonly` | Identify users for sync. |

### 3. Events & Webhooks (Optional)
To enable real-time updates from Lark back to ERPNext (e.g., when a Task is completed in Lark), you should configure the **Event Subscriptions** in the console and point them to your ERPNext site's API hook.

---

## 3. Lark Drive & File Management
Sync ERPNext file attachments directly to Lark Drive folders.

- **Sync ERP PDF Attachments**: If enabled, whenever an ERP document (Invoice, Order, etc.) is submitted, the system automatically generates the PDF and uploads it to the linked Lark Bitable.
- **Request Timeout**: Maximum seconds to wait for Lark API responses (Default: 20s).

- **Upload To Lark Drive**: Transfers all local ERPNext attachments to Lark Drive automatically.
- **Lark Drive Folder Token**: The destination folder ID in Lark. (Find this in the Lark Drive URL; it's the alphanumeric string after `folder/`).
- **Remove ERPNext File Content**: If enabled, the system deletes the file from the ERPNext server *after* successful upload to Lark, replacing it with a "Lark Proxy" link. This saves local disk space while keeping files accessible.
- **Hierarchical Storage**: Files are automatically organized into `DocType/Year/Month` subfolders within Lark Drive.

---

## 3. Bitable Document Sync
Define custom mappings in **Lark Sync Document** to push ERPNext data to Lark Bitables.

### Main Config
- **Document Type**: The ERPNext DocType to sync (e.g., Sales Invoice).
- **Lark Key Field**: The specific field in Lark that holds the ERPNext Name (e.g., `INV-2024-001`). This is used to find and update existing records.
- **Lark App Token**: The unique ID of the Lark Bitable app.
- **Main Table ID**: The ID of the primary table in the Bitable.
- **Items Table ID**: (Optional) The ID of a separate table for child rows (e.g., Invoice Items).

### Advanced Mapping
- **Sync Child Table**: If enabled, child table rows (like Items or Taxes) are pushed to the `Items Table ID`.
- **Attachment Sync Mode**:
    - `Both`: Uploads to both Bitable and Lark Drive.
    - `Base Only`: Syncs only to the Bitable's attachment field.
    - `Drive Only`: Syncs only to Lark Drive.
    - `None`: Disables attachment sync for this DocType.
- **Item Summary**: Generates a beautiful formatted text summary (e.g., `- Item A x 5`) in the main Lark table, allowing you to see item details without following record links.

---

## 4. ToDo & Task Sync
Two-way synchronization between ERPNext ToDos and Lark Tasks.

- **Enable ToDo Sync**: Master toggle for task synchronization.
- **Sync ToDo References**: Adds a direct link (URL) in the Lark Task pointing back to the specific ERPNext document it refers to.
- **Sync Priority**: Maps ERPNext priorities (Low, Medium, High) to Lark's priority levels.
- **Real-time**: ERPNext changes reflect instantly in Lark. Lark changes are pulled hourly or via the manual **Sync Tasks Now** button.

---

## 5. Calendar & Event Sync
Advanced two-way synchronization for Events and Meetings.

- **Enable Calendar Sync**: Master toggle for event synchronization.
- **Multiple Calendars**: Create **Lark Calendar** records to manage different shared or private calendars.
- **Add Lark Meeting**: A checkbox on the Event form that instantly generates a Lark Meeting (video call) link.
- **Join Meeting Button**: Adds a "Join Lark Meeting" button directly in ERPNext for easy access to video calls.
- **Attendee Sync**: ERPNext participants are automatically invited as attendees in Lark.
- **Recurrence Support**: Syncs Daily, Weekly, and Monthly repeating event series.
- **Incremental Sync**: Uses "Sync Tokens" to pull only *changed* events, ensuring high performance.

---

## 6. Automated Backup
Securely backup your entire ERPNext suite to Lark Drive.

- **Enable Automated Backup**: Global switch for backups.
- **Frequency**: Choose between `Hourly`, `Daily`, or `Weekly`.
- **Retention Limit**: Automatically deletes old backups from Lark to save space (e.g., keep the last 5 backups).
- **Backup Site**: Specify which site to backup (defaults to the current site).
- **Backup Files**: Optionally include the `public` and `private` file directories in the backup archive.
- **Notifications**: Configure emails to receive success reports or failure alerts.
- **Take Backup Now**: Manual button for immediate ad-hoc backups.

---

## 7. Troubleshooting
- **Last Sync Status**: Every module (Backup, ToDo, Calendar) has a "Last Sync On" and "Status" field to help identify issues.
- **Error Logs**: Check the standard ERPNext **Error Log** list for detailed tracebacks if a sync fails.
