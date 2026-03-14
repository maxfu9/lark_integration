frappe.ui.form.on("Lark Approval Mapping", {
	refresh(frm) {
		// Force visibility of the naming field
		frm.set_df_property("document_type", "hidden", 0);
	},
});
