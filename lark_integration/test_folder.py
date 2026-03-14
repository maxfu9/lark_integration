import frappe
from lark_integration.api import _get_or_create_nested_folder, get_lark_token, _get_config

def run():
    token = get_lark_token()
    config = _get_config()
    parent_token = config.get("drive_folder_token")
    
    if not parent_token:
        print("Error: drive_folder_token not set in config.")
        return

    # Use a unique root for the test
    root_name = "Hierarchy Test " + frappe.utils.now_datetime().strftime('%Y%m%d%H%M%S')
    test_path = [root_name, "2026", "March"]
    
    print(f"Testing hierarchical folder creation: {'/'.join(test_path)} in {parent_token}")
    
    # 1. Test creation
    print("Level 1: Creation...")
    final_token = _get_or_create_nested_folder(test_path, parent_token, token)
    if final_token != parent_token:
        print(f"Success! Final folder token: {final_token}")
    else:
        print("Failed: Returned parent token instead of a new folder token.")
        return

    # 2. Test cached/search (should find without creating new ones)
    print("Level 2: Search (should be cached)...")
    found_token = _get_or_create_nested_folder(test_path, parent_token, token)
    if found_token == final_token:
        print("Success! Found existing token correctly.")
    else:
        print(f"Failed: Search returned {found_token}, expected {final_token}")

if __name__ == "__main__":
    run()
