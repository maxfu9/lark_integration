import frappe
from lark_integration.api import get_lark_token, _get_config, LARK_BASE_URL, SESSION

def run():
    token = get_lark_token()
    config = _get_config()
    
    # Use the file token from the user's traceback if possible, or get latest
    file_token = "RoQwbeR5xoYXYhxsvwWj2uZ4pLU"
    
    # Test the 'files' endpoint
    url = f"{LARK_BASE_URL}/drive/v1/files/{file_token}/download"
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
