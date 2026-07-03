import frappe


SIDEBAR_ITEMS = [
	{
		"label": "Dashboard",
		"link_type": "Workspace",
		"link_to": "Lark Integration",
		"type": "Link",
		"icon": "home",
	},
	{
		"label": "Settings",
		"link_type": "DocType",
		"link_to": "Lark Integration Settings",
		"type": "Link",
		"icon": "settings",
	},
	{
		"label": "Configuration",
		"link_type": "DocType",
		"type": "Section Break",
		"icon": "git-branch",
		"indent": 1,
	},
	{
		"label": "Sync Documents",
		"link_type": "DocType",
		"link_to": "Lark Sync Document",
		"type": "Link",
		"child": 1,
	},
	{
		"label": "Approval Mappings",
		"link_type": "DocType",
		"link_to": "Lark Approval Mapping",
		"type": "Link",
		"child": 1,
	},
	{
		"label": "Data",
		"link_type": "DocType",
		"type": "Section Break",
		"icon": "database",
		"indent": 1,
	},
	{
		"label": "Task Lists",
		"link_type": "DocType",
		"link_to": "Lark Task List",
		"type": "Link",
		"child": 1,
	},
	{
		"label": "Calendars",
		"link_type": "DocType",
		"link_to": "Lark Calendar",
		"type": "Link",
		"child": 1,
	},
	{
		"label": "Drive Files",
		"link_type": "DocType",
		"link_to": "Lark Drive File",
		"type": "Link",
		"child": 1,
	},
	{
		"label": "Operations",
		"link_type": "DocType",
		"type": "Section Break",
		"icon": "list",
		"indent": 1,
	},
	{
		"label": "Sync Queue",
		"link_type": "DocType",
		"link_to": "Lark Sync Queue",
		"type": "Link",
		"child": 1,
	},
	{
		"label": "Logs & Reports",
		"link_type": "DocType",
		"type": "Section Break",
		"icon": "file-text",
		"indent": 1,
	},
	{
		"label": "API Logs",
		"link_type": "DocType",
		"link_to": "Lark API Log",
		"type": "Link",
		"child": 1,
	},
	{
		"label": "API Usage Summary",
		"link_type": "Report",
		"link_to": "Lark API Usage Summary",
		"type": "Link",
		"child": 1,
	},
	{
		"label": "API Dashboard",
		"link_type": "Dashboard",
		"link_to": "Lark API Dashboard",
		"type": "Link",
		"child": 1,
	},
]


def execute():
	upsert_lark_desktop_icon()
	upsert_lark_workspace_sidebar()
	clear_desk_navigation_cache()


def upsert_lark_desktop_icon():
	if frappe.db.exists("Desktop Icon", "Lark Integration"):
		icon = frappe.get_doc("Desktop Icon", "Lark Integration")
	else:
		icon = frappe.new_doc("Desktop Icon")
		icon.label = "Lark Integration"

	icon.update(
		{
			"icon_type": "Link",
			"link_type": "Workspace Sidebar",
			"link_to": "Lark Integration",
			"icon": "notification",
			"hidden": 0,
			"restrict_removal": 0,
			"standard": 1,
			"app": "lark_integration",
			"idx": icon.idx or 21,
		}
	)
	icon.save(ignore_permissions=True)


def upsert_lark_workspace_sidebar():
	if frappe.db.exists("Workspace Sidebar", "Lark Integration"):
		sidebar = frappe.get_doc("Workspace Sidebar", "Lark Integration")
	else:
		sidebar = frappe.new_doc("Workspace Sidebar")
		sidebar.title = "Lark Integration"

	sidebar.update(
		{
			"title": "Lark Integration",
			"header_icon": "notification",
			"module": "Lark Integration",
			"app": "lark_integration",
			"standard": 1,
		}
	)
	sidebar.set("items", [])
	for item in SIDEBAR_ITEMS:
		sidebar.append("items", normalize_sidebar_item(item))
	sidebar.save(ignore_permissions=True)


def normalize_sidebar_item(item):
	return {
		"label": item.get("label"),
		"link_type": item.get("link_type", "DocType"),
		"link_to": item.get("link_to"),
		"type": item.get("type", "Link"),
		"icon": item.get("icon") or "",
		"child": item.get("child", 0),
		"collapsible": item.get("collapsible", 1),
		"indent": item.get("indent", 0),
		"keep_closed": item.get("keep_closed", 0),
		"show_arrow": item.get("show_arrow", 0),
	}


def clear_desk_navigation_cache():
	frappe.cache.delete_key("desktop_icons")
	frappe.cache.delete_key("bootinfo")
	frappe.clear_cache()
