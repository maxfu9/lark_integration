frappe.ui.form.on("Lark Calendar", {
	refresh(frm) {
		if (!frm.doc.lark_calendar_id) {
			frm.add_custom_button(__("Create in Lark"), () => {
				frappe.call({
					method: "lark_integration.api.create_lark_calendar",
					args: { doc_name: frm.doc.name },
					freeze: true,
					callback: (r) => {
						if (!r.exc) {
							frappe.show_alert({ message: __("Calendar created in Lark"), indicator: "green" });
							frm.reload_doc();
						}
					}
				});
			});
		}
	}
});
