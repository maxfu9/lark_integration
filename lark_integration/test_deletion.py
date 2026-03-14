import frappe
from lark_integration.api import get_lark_token, _get_config, upload_to_lark_drive

def run():
    print("Starting deletion verification...")
    token = get_lark_token()
    config = _get_config()
    folder_token = config.get("drive_folder_token")

    # 1. Create a dummy File doc
    file_name = "test_deletion_hook.txt"
    content = b"Content for deletion test"
    
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": file_name,
        "content": content,
        "is_private": 1
    }).insert()
    
    # 2. Upload to Lark and create link (simulating handle_file_attach)
    lark_token = upload_to_lark_drive(file_name, content, token, folder_token)
    print(f"Uploaded to Lark: {lark_token}")

    link_doc = frappe.get_doc({
        "doctype": "Lark Drive File",
        "attached_to_doctype": "User",
        "attached_to_name": frappe.session.user,
        "file_name": file_name,
        "lark_file_token": lark_token,
        "source_file": file_doc.name
    }).insert(ignore_permissions=True)
    frappe.db.commit()
    print(f"Created link record: {link_doc.name}")

    # 3. Delete the ERPNext File doc
    print(f"Deleting ERPNext File: {file_doc.name}...")
    frappe.delete_doc("File", file_doc.name)
    frappe.db.commit()

    # 4. Verify results
    link_exists = frappe.db.exists("Lark Drive File", link_doc.name)
    if not link_exists:
        print("Success: Lark Drive File record was automatically deleted.")
    else:
        print("Failed: Lark Drive File record still exists.")

if __name__ == "__main__":
    run()
