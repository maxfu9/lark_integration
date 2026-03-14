import frappe

def test():
    print("Checking Lark Sync Document configurations:")
    mappings = frappe.get_all("Lark Sync Document", fields=["name", "document_type", "enabled"])
    for m in mappings:
        print(f" - {m.document_type} (Enabled: {m.enabled})")

    print("\nChecking recent Error Logs:")
    logs = frappe.get_all("Error Log", fields=["method", "error", "creation"], order_by="creation desc", limit=5)
    for log in logs:
        if "Lark" in str(log.method) or "Lark" in str(log.error):
            print(f"[{log.creation}] {log.method}")
            print(log.error[:500])
            print("-" * 50)
            
    print("\nChecking recent background jobs:")
    jobs = frappe.get_all("RQ Job", fields=["job_name", "status", "exc_info", "creation"], order_by="creation desc", limit=10)
    for job in jobs:
        if "lark" in str(job.job_name) or "failed" in str(job.status):
            print(f"[{job.creation}] {job.job_name} - {job.status}")
            if job.exc_info:
                print(job.exc_info[:500])
