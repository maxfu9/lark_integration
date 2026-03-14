
frappe.ui.form.on("Lark Task List", {
	refresh(frm) {
		if (!frm.doc.lark_list_guid) {
			// Option 1: Create new in Lark
			frm.add_custom_button(__("Create in Lark"), () => {
				frappe.call({
					method: "lark_integration.api.create_lark_task_list",
					args: { doc_name: frm.doc.name },
					callback: (r) => {
						if (r.message && r.message.status === "success") {
							frappe.show_alert({ message: __("Task List created in Lark"), indicator: "green" });
							frm.reload_doc();
						}
					}
				});
			});

			// Option 2: Link an existing Lark Task List by GUID
			frm.add_custom_button(__("Link Existing Lark List"), () => {
				frappe.prompt([
					{
						fieldtype: "Data",
						label: "Lark Task List GUID",
						fieldname: "guid",
						reqd: 1,
						description: __("Open Lark → Tasks → Select your list → copy the list ID from the URL (e.g. the part after /tasklists/)"),
					}
				], (values) => {
					frappe.call({
						method: "lark_integration.api.link_lark_task_list",
						args: { doc_name: frm.doc.name, guid: values.guid },
						freeze: true,
						freeze_message: __("Linking and joining Lark task list..."),
						callback: (r) => {
							if (r.message && r.message.status === "success") {
								frappe.show_alert({ message: __("Linked! Tasks from this list will sync automatically."), indicator: "green" });
								frm.reload_doc();
							} else {
								frappe.show_alert({ message: __("Failed to link. Check the GUID and try again."), indicator: "red" });
							}
						}
					});
				}, __("Link Existing Lark Task List"), __("Link"));
			});
		} else {
			// Already linked — show a join button in case the app lost membership
			frm.add_custom_button(__("Re-join in Lark"), () => {
				frappe.call({
					method: "lark_integration.api.link_lark_task_list",
					args: { doc_name: frm.doc.name, guid: frm.doc.lark_list_guid },
					callback: (r) => {
						frappe.show_alert({ message: __("App re-joined the task list in Lark"), indicator: "green" });
					}
				});
			});
		}
	}
});
