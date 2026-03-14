import frappe
def run():
    print("Checking File with Lark proxy...")
    file_recs = frappe.db.get_all('File', filters={'file_url': ['like', '%download_lark_drive_file%']}, fields=['name', 'file_url', 'is_private', 'attached_to_doctype', 'attached_to_name'], limit=1)
    if not file_recs:
        print("No proxied files found.")
        return
    
    file_rec = file_recs[0]
    print(f"File: {file_rec.name}")
    print(f"  URL: {file_rec.file_url}")
    print(f"  Private: {file_rec.is_private}")
    print(f"  Attached To: {file_rec.attached_to_doctype} / {file_rec.attached_to_name}")
    
    # Try to find the record param from URL
    if 'record=' in file_rec.file_url:
        record_id = file_rec.file_url.split('record=')[1]
        print(f"Lark Drive File record ID: {record_id}")
        lark_file = frappe.db.get_value('Lark Drive File', record_id, ['name', 'attached_to_doctype', 'attached_to_name'], as_dict=1)
        if lark_file:
            print(f"Lark File Record found: {lark_file.name}")
            print(f"  Lark Attached To: {lark_file.attached_to_doctype} / {lark_file.attached_to_name}")
            print(f"  Permission on parent for Current User {frappe.session.user}: {frappe.has_permission(lark_file.attached_to_doctype, 'read', lark_file.attached_to_name)}")
        else:
            print("Lark File Record NOT found in DB.")

if __name__ == "__main__":
    run()
