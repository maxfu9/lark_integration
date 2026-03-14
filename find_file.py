import frappe
def run():
    fname = "ACC-PAY-2600320.pdf"
    print(f"Searching for {fname}...")
    recs = frappe.db.get_all('File', filters={'file_name': ['like', f'%{fname}%']}, fields=['name', 'file_name', 'file_url', 'is_private'], as_dict=1)
    if not recs:
        print("No file found in tabFile.")
    for r in recs:
        print(f"File: {r.name} | URL: {r.file_url} | Private: {r.is_private}")
        lark_logs = frappe.get_all('Lark Drive File', filters={'source_file': r.name}, fields=['name', 'lark_file_token'])
        for l in lark_logs:
            print(f"  Lark Log: {l.name} | Token: {l.lark_file_token}")

if __name__ == "__main__":
    run()
