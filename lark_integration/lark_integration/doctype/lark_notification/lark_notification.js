frappe.ui.form.on('Lark Notification', {
	refresh: function(frm) {
		frm.trigger('setup_field_options');
	},
	document_type: function(frm) {
		frm.trigger('setup_field_options');
	},
	setup_field_options: function(frm) {
		if (frm.doc.document_type) {
			frappe.model.with_doctype(frm.doc.document_type, () => {
				let fields = frappe.get_meta(frm.doc.document_type).fields;
				
				// 1. All fields for "Value Change"
				let all_fields = fields.map(f => ({ label: f.label || f.fieldname, value: f.fieldname }))
					.sort((a, b) => a.label.localeCompare(b.label));
				
				frm.set_df_property('changed_field', 'options', [""].concat(all_fields));

				// 2. Date/Datetime fields for "Days Before/After"
				let date_fields = fields
					.filter(f => ['Date', 'Datetime'].includes(f.fieldtype))
					.map(f => ({ label: f.label || f.fieldname, value: f.fieldname }))
					.sort((a, b) => a.label.localeCompare(b.label));
				
				frm.set_df_property('date_changed', 'options', [""].concat(date_fields));

				// 3. Print Formats for the chosen DocType
				frappe.db.get_list('Print Format', {
					filters: { doc_type: frm.doc.document_type },
					fields: ['name']
				}).then(formats => {
					let options = [""].concat(formats.map(f => f.name));
					frm.set_df_property('print_format', 'options', options);
				});
				
				frm.refresh_field('changed_field');
				frm.refresh_field('date_changed');
				frm.refresh_field('print_format');
			});
		}
	}
});
