import frappe
import json

def run():
    logs = frappe.db.get_all('Error Log', filters={'title': ['like', 'Lark%']}, fields=['title', 'message', 'creation'], order_by='creation desc', limit=10)
    output = json.dumps(logs, indent=2, default=str)
    # Raising an error to force output display
    raise Exception(f"LOGS_DATA_START\n{output}\nLOGS_DATA_END")

if __name__ == "__main__":
    run()
