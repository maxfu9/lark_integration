frappe.ui.form.on("Event", {
	refresh(frm) {
		if (frm.doc.lark_meeting_url) {
			frm.add_custom_button(__("Join Lark Meeting"), () => {
				window.open(frm.doc.lark_meeting_url, "_blank");
			}, __("Lark Integration"));
			
			frm.set_df_property("lark_meeting_url", "description", 
				`<a href="${frm.doc.lark_meeting_url}" target="_blank">Click here to join meeting</a>`);
		}
	}
});
