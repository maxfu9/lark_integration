import frappe

def get_logs():
    logs = frappe.get_all("Error Log", fields=["method", "error", "creation"], order_by="creation desc", limit=10)
    for log in logs:
        print(f"[{log.creation}] {log.method}")
        print(log.error)
        print("-" * 50)
