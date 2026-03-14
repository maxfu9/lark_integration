import frappe
from lark_integration.api import sync_doc_attachments_to_lark_drive, get_lark_token, _get_config, _is_managed_lark_proxy

def test_sync():
    token = get_lark_token()
    config = _get_config()
    
    # Try to find a Sales Invoice that actually has a File attached.
    # Otherwise fallback to get_last_doc
    files = frappe.get_all("File", filters={"attached_to_doctype": "Sales Invoice", "is_folder": 0}, limit=1)
    if files:
        file_doc = frappe.get_doc("File", files[0].name)
        doc = frappe.get_doc("Sales Invoice", file_doc.attached_to_name)
    else:
        doc = frappe.get_last_doc("Sales Invoice")
    
    print(f"--- Doc: {doc.doctype} {doc.name} ---")
    print(f"Token present: {bool(token)}")
    print(f"Drive Upload Enabled: {config.get('drive_upload_enabled')}")
    print(f"Folder Token present: {bool(config.get('drive_folder_token'))}")
    
    attached_files = frappe.get_all(
        "File",
        filters={"attached_to_doctype": doc.doctype, "attached_to_name": doc.name, "is_folder": 0},
        fields=["name"],
    )
    print(f"Found {len(attached_files)} files attached to {doc.doctype} {doc.name}")
    
    for row in attached_files:
        file_doc = frappe.get_doc("File", row.name)
        print(f"\nProcessing File: {file_doc.file_name}")
        
        is_proxy = _is_managed_lark_proxy(file_doc.file_url)
        print(f"  Is Proxy? {is_proxy}")
        
        is_http = bool(file_doc.file_url and str(file_doc.file_url).startswith("http"))
        print(f"  Is HTTP URL? {is_http}")
        
        try:
            content = file_doc.get_content()
            print(f"  Content loaded, {len(content) if content else 0} bytes")
        except Exception as e:
            print(f"  Failed to load content: {str(e)}")
            
test_sync()
