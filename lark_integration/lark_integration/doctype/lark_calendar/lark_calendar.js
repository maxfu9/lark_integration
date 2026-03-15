frappe.ui.form.on("Lark Calendar", {
	refresh(frm) {
		frappe.call({
			method: "lark_integration.api.get_lark_oauth_status",
			callback: (r) => {
				const connected = r.message && r.message.connected;
				if (connected) {
					frm.set_intro(__("Lark account connected for this user."), "green");
					frm.add_custom_button(__("Lark Connected"), () => {
						frappe.show_alert({ message: __("Lark account is already connected."), indicator: "green" });
					});
				} else {
					frm.set_intro(__("Connect your Lark account to create calendars under Managing."), "orange");
					frm.add_custom_button(__("Connect Lark Account"), () => {
						frappe.call({
							method: "lark_integration.api.get_lark_oauth_url",
							callback: (res) => {
								if (res.message && res.message.status === "success") {
									window.open(res.message.url, "_blank");
								} else {
									frappe.show_alert({ message: __("Failed to get OAuth URL."), indicator: "red" });
								}
							}
						});
					});
				}
			}
		});

		if (!frm.doc.lark_calendar_id) {
			frm.add_custom_button(__("Create in Lark"), () => {
				frappe.call({
					method: "lark_integration.api.create_lark_calendar",
					args: { doc_name: frm.doc.name },
					freeze: true,
					callback: (r) => {
						if (r.message && r.message.status === "success") {
							frappe.show_alert({ message: __("Calendar created in Lark"), indicator: "green" });
							frm.reload_doc();
						} else {
							frappe.show_alert({ message: __(r.message && r.message.message ? r.message.message : "Failed to create calendar in Lark"), indicator: "red" });
						}
					}
				});
			});
		} else {
			frm.add_custom_button(__("Re-join in Lark"), () => {
				frappe.call({
					method: "lark_integration.api.join_lark_calendar",
					args: { doc_name: frm.doc.name },
					callback: (r) => {
						if (r.message && r.message.status === "success") {
							frappe.show_alert({ message: __("App re-joined the calendar in Lark"), indicator: "green" });
						} else {
							frappe.show_alert({ message: __(r.message && r.message.message ? r.message.message : "Failed to re-join calendar"), indicator: "red" });
						}
					}
				});
			});
		}
	}
});
