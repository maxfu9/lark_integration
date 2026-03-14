import frappe
def run():
    logs = frappe.get_all('Error Log', fields=['message', 'creation', 'title'], order_by='creation desc', limit=10)
    for log in logs:
        print(f"[{log.creation}] {log.title}: {log.message}")

if __name__ == "__main__":
    run()
