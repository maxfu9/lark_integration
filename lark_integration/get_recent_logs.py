import frappe
def test():
    logs = frappe.get_all("Error Log", fields=["method", "error", "creation"], order_by="creation desc", limit=10)
    for log in logs:
        if "Lark Drive" in str(log.method) or "Lark Drive" in str(log.error):
            print(f"[{log.creation}] {log.method}")
            print(log.error[:1000])
            print("-" * 50)
