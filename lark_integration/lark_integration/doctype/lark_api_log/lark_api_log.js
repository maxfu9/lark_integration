frappe.ui.form.on('Lark API Log', {
	refresh: function(frm) {
		frm.set_df_property('request_payload', 'read_only', 1);
		frm.set_df_property('response_payload', 'read_only', 1);
	}
});
