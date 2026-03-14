import frappe

def check_lark_files():
    files = frappe.get_all("Lark Drive File", fields=["attached_to_doctype", "attached_to_name", "file_name"])
    print(f"Total Lark Drive Files: {len(files)}")
    for f in files:
        print(f"{f.attached_to_doctype}: {f.attached_to_name} - {f.file_name}")

if __name__ == "__main__":
    check_lark_files()
