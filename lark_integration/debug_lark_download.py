import frappe
from lark_integration.api import get_lark_token, _get_config, LARK_BASE_URL, SESSION

def run(record_id=None):
    token = get_lark_token()
    config = _get_config()
    
    if record_id is None:
        res = frappe.get_all("Lark Drive File", order_by="creation desc", limit=1)
        if res:
            record_id = res[0].name
        else:
            print("No Lark Drive File records found.")
            return

    print(f"Using record: {record_id}")
    link_doc = frappe.get_doc("Lark Drive File", record_id)
    file_token = link_doc.lark_file_token
    
    endpoints = [
        f"{LARK_BASE_URL}/drive/v1/medias/{file_token}/download",
        f"{LARK_BASE_URL}/drive/v1/files/{file_token}/download"
    ]
    
    for url in endpoints:
        print(f"Testing URL: {url}")
        try:
            response = SESSION.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=config["request_timeout"])
            print(f"  Status Code: {response.status_code}")
            if response.status_code >= 400:
                print(f"  Error Body: {response.text}")
            else:
                print(f"  Success! Result size: {len(response.content)}")
        except Exception as e:
            print(f"  Requests Exception: {e}")

if __name__ == "__main__":
    run()
