# Lark Integration for ERPNext

A professional, high-performance two-way synchronization suite connecting ERPNext with Lark (Feishu). This integration enables seamless data flow between your ERP and Lark's Bitable, Drive, Tasks (ToDo), and Calendar, while also providing secure automated offsite backups.

---

## 🚀 1. Installation

Install the app using the standard Frappe Bench CLI:

```bash
# Get the app
bench get-app https://github.com/maxfu9/lark_integration

# Install on your site
bench --site [your-site-name] install-app lark_integration

# Build assets
bench build --app lark_integration

# Run migrations
bench --site [your-site-name] migrate
```

---

## ⚙️ 2. Lark Configuration (Developer Console)

Before configuring ERPNext, set up your app in the [Lark Developer Console](https://open.larksuite.com/app).

### 1. Credentials
- Navigate to **Credentials & Basic Information**.
- Copy your **App ID** and **App Secret**.

### 2. Permisison Administration
Enable the following API scopes to allow ERPNext to communicate with Lark:

| Category | Scopes Required | Feature |
| :--- | :--- | :--- |
| **Bitable** | `bitable:app` | Sync ERPNext records to Bitable cells. |
| **Drive** | `drive:drive` | Upload attachments & back up your site. |
| **Tasks** | `task:task:write`, `task:task:read` | Bidirectional ToDo sync. |
| **Task Lists** | `task:tasklist:read`, `task:tag:read` | Fetch and sync Task Lists & Tags. |
| **Calendar** | `calendar:calendar`, `calendar:calendar:readonly` | Bidirectional Event sync. |
| **Approvals** | `approval:approval:read`, `approval:approval` | Universal Approval sync. |
| **Contact** | `contact:user.email:readonly` | User identification. |

### 3. Event Subscriptions (Optional)
To enable **Real-Time** sync from Lark back to ERPNext:
1.  Go to **Event Subscriptions**.
2.  Set **Request URL** to: `https://[your-site-url]/api/method/lark_integration.api.lark_webhook`
3.  Add events:
    - `task.task.updated_v2`, `task.task.deleted_v2` (for ToDos)
    - `task.tasklist.updated_v2`, `task.tasklist.deleted_v2` (for Task Lists)
    - `calendar.calendar_event.updated_v4`, `calendar.calendar_event.deleted_v4` (for Events)

---

## 🛠️ 3. Integration Features

### 🔐 Security & Identity
- **Native Security Patterns**: App secrets are protected with visibility toggles and real-time complexity meters.
- **Handshake Optimization**: Technical authentication noise is suppressed from your logs, keeping your history clear.

### 📼 Automated Offsite Backups
- **Background Processing**: Manual and scheduled backups run in the background (RQ Jobs) to prevent timeouts.
- **Real-Time Progress**: Watch your backup progress with an inline progress bar showing bench output, upload status, and retention cleanup.
- **Granular Scheduling**: Configure Hourly, Daily (at a specific time), or Weekly backups.
- **Smart Retention**: Automatically keep only the last `N` backups on Lark Drive.

### 📝 Bitable & Document Sync
- **Universal Handler**: Map *any* ERPNext DocType to a Bitable using the **Lark Sync Document** doctype.
- **Item Summaries**: Automatically generate beautiful, readable item summaries inside Lark main tables.
- **Attachment Proxy**: Move heavy local file attachments to Lark Drive and replace them with links in ERPNext to save server disk space.

### 📅 Two-Way Sync (ToDo & Calendar)
- **Periodic or Webhook**: Choose between polling every 5-60 minutes or instant real-time updates via Webhooks.
- **Deep Integration**: Links to ERPNext documents are embedded directly into Lark Tasks and Calendar events.
- **Video Meeting Support**: Create and join Lark Meetings directly from the ERPNext Event form.

#### 📋 Task List Management
Lark Tasks are organized into different Lists. This integration allows you to specify exactly which Lark Task List an ERPNext ToDo should belong to.
- **Lark Task List DocType**: Manages the mapping between ERPNext and Lark's list structure (stores List Name and Token).
- **Fetch Task Lists**: Use the **Fetch Task Lists from Lark** button in the **Lark Integration Settings** (ToDo Sync tab) to automatically pull all your available lists into ERPNext.
- **Custom Allocation**: When creating a ToDo, you can select which **Lark Task List** to sync to. If left blank, it defaults to your primary task list in Lark.

---

## 📊 4. Monitoring & Diagnostics

Keep your integration healthy with built-in monitoring tools:

- **Lark API Log**: A detailed audit trail of every data-carrying request. Technical handshake noise is automatically filtered out.
- **Usage Dashboard**: Visual charts showing API status breakdowns and call trends over time.
- **Backup Metrics**: Track the duration, size, and success status of every backup run.
- **Activity Log Silence**: Automated status updates do not clutter your document timeline; only manual changes are logged.

### 5. Global Approval Synchronization (All DocTypes)
You can now connect **any** ERPNext Workflow to a Lark Approval form without further coding.

1.  **Identity Backup**: Click the **Sync Lark IDs** button in settings. 
    - This automatically matches ERPNext users with Lark users by email address.
    - You can also manually add a Lark User ID in the **User** DocType.
2.  **Create Mapping**: Go to **Lark Approval Mapping** and create a new record.
    - **DocType**: Select any target (e.g., `Purchase Order` or `Leave Application`).
    - **Workflow State**: Specify the name of the state that triggers the sync (e.g., `Pending Approval`).
    - **Approval Code**: Paste your unique code from the Lark Approval Definition.
3.  **Field Mappings**: In the child table, map ERPNext fieldnames to Lark Form IDs.
    - *Example*: `grand_total` → `total_amount_id`.
4.  **Automatic ID Tracking**: Ensure your target DocType has a field called `lark_approval_instance_id`. 
    - *Note: This will be automatically added for standard DocTypes or can be added as a Custom Field.*

---

## 🧹 6. Maintenance
- **Log Cleanup**: API logs are kept for reference but can be cleared periodically using a standard Frappe auto-cleanup policy.
- **Site Updates**: When updating the app, always run `bench migrate` to apply any new DocType schemas.

---

*Built with ❤️ for ERPNext. Ensure your developers have shared your Lark App with your user account within the Lark suite before first sync.*
