import frappe

def find_links():
    links = frappe.get_all("DocField", filters={"fieldtype": "Link", "options": "Sales Invoice"}, fields=["parent", "fieldname"])
    custom_links = frappe.get_all("Custom Field", filters={"fieldtype": "Link", "options": "Sales Invoice"}, fields=["parent", "fieldname"])
    
    print("Standard Links:")
    for l in links:
        print(f"{l.parent}.{l.fieldname}")
        
    print("\nCustom Links:")
    for l in custom_links:
        print(f"{l.parent}.{l.fieldname}")

if __name__ == "__main__":
    find_links()
