import frappe
import json

def dump_logs():
    logs = frappe.get_all("Error Log", fields=["method", "error", "creation"], limit=20, order_by="creation desc")
    for log in logs:
        print(f"--- {log.method} ({log.creation}) ---")
        print(log.error)
        print("-" * 40)

if __name__ == "__main__":
    dump_logs()
