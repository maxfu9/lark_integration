import frappe
import json

def check_meta():
    meta = frappe.get_meta("Lark Drive File")
    res = []
    for f in meta.fields:
        res.append({
            "fieldname": f.fieldname,
            "fieldtype": f.fieldtype,
            "options": f.options
        })
    print(json.dumps(res, indent=2))

if __name__ == "__main__":
    check_meta()
