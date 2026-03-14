frappe.ui.form.on("Lark Sync Document", {
	setup(frm) {
		frm._set_erp_field_options = () => {
			const doctype = frm.doc.document_type;
			if (!doctype) {
				return;
			}

			frappe.model.with_doctype(doctype, () => {
				const meta = frappe.get_meta(doctype);
				if (!meta || !meta.fields) {
					return;
				}

				const options = meta.fields
					.filter((df) => df.fieldname && !["Section Break", "Column Break", "Tab Break", "HTML"].includes(df.fieldtype))
					.map((df) => df.fieldname)
					.sort();

				const grid = frm.fields_dict.field_mappings.grid;
				grid.update_docfield_property("erp_field", "options", options.join("\n"));
				grid.refresh();
			});
		};
		frm._set_child_field_options = () => {
			const activeField = frm.doc.active_child_table_field;
			if (!activeField || !frm._child_table_map) {
				return;
			}

			const childDoctype = frm._child_table_map[activeField];
			if (!childDoctype) {
				return;
			}

			frappe.model.with_doctype(childDoctype, () => {
				const child_meta = frappe.get_meta(childDoctype);
				if (!child_meta || !child_meta.fields) {
					return;
				}

				const child_options = child_meta.fields
					.filter((df) => df.fieldname && !["Section Break", "Column Break", "Tab Break", "HTML"].includes(df.fieldtype))
					.map((df) => df.fieldname)
					.sort();

				const grid = frm.fields_dict.child_field_mappings?.grid;
				if (grid) {
					grid.update_docfield_property("child_field", "options", child_options.join("\n"));
					grid.refresh();
				}
			});
		};
		frm._set_child_table_options = () => {
			const doctype = frm.doc.document_type;
			if (!doctype) {
				return;
			}

			frappe.model.with_doctype(doctype, () => {
				const meta = frappe.get_meta(doctype);
				if (!meta || !meta.fields) {
					return;
				}

				const table_fields = meta.fields
					.filter((df) => df.fieldtype === "Table" && df.options)
					.map((df) => ({ label: df.label || df.fieldname, value: df.fieldname, doctype: df.options }))
					.sort((a, b) => a.label.localeCompare(b.label));

				frm._child_table_map = {};
				table_fields.forEach((row) => {
					frm._child_table_map[row.value] = row.doctype;
				});

				const childTablesGrid = frm.fields_dict.child_tables?.grid;
				if (childTablesGrid) {
					childTablesGrid.update_docfield_property("child_table_field", "options", table_fields.map((row) => row.value).join("\n"));
					childTablesGrid.refresh();
				}

				const childFieldsGrid = frm.fields_dict.child_field_mappings?.grid;
				if (childFieldsGrid) {
					childFieldsGrid.update_docfield_property("child_table_field", "options", table_fields.map((row) => row.value).join("\n"));
					childFieldsGrid.refresh();
				}

				const configuredChildTables = (frm.doc.child_tables || [])
					.map((row) => row.child_table_field)
					.filter((value) => value);
				const activeOptions = configuredChildTables.length ? configuredChildTables : table_fields.map((row) => row.value);
				frm.set_df_property("active_child_table_field", "options", activeOptions.join("\n"));

				if (!frm.doc.active_child_table_field && activeOptions.length === 1) {
					frm.set_value("active_child_table_field", activeOptions[0]);
				}

				(frm.doc.child_tables || []).forEach((row) => {
					if (row.child_table_field && !row.child_table_doctype && frm._child_table_map[row.child_table_field]) {
						frappe.model.set_value(row.doctype, row.name, "child_table_doctype", frm._child_table_map[row.child_table_field]);
					}
				});

				frm.refresh_field("child_tables");
				frm.refresh_field("active_child_table_field");
				frm._set_child_field_options();
				frm._set_summary_options();
			});
		};
		frm._set_summary_options = () => {
			const doctype = frm.doc.document_type;
			if (!doctype) return;

			frappe.model.with_doctype(doctype, () => {
				const meta = frappe.get_meta(doctype);
				const tables = meta.fields
					.filter(df => df.fieldtype === 'Table')
					.map(df => df.fieldname)
					.sort();
				frm.set_df_property('summary_child_table', 'options', [""].concat(tables).join("\n"));

				const summaryChild = frm.doc.summary_child_table;
				if (summaryChild) {
					const childDf = meta.fields.find(df => df.fieldname === summaryChild);
					if (childDf && childDf.options) {
						frappe.model.with_doctype(childDf.options, () => {
							const childMeta = frappe.get_meta(childDf.options);
							const fields = childMeta.fields
								.filter(df => df.fieldname && !["Section Break", "Column Break", "Tab Break", "HTML"].includes(df.fieldtype))
								.map(df => df.fieldname)
								.sort();

							const helpText = `Available Fields: <b>${fields.join(", ")}</b>`;
							frm.set_df_property('summary_row_template', 'description', helpText);
						});
					}
				}
			});
		};
	},
	refresh(frm) {
		frm.set_df_property("document_type", "hidden", 0);
		frm._set_erp_field_options();
		frm._set_child_table_options();
		frm._set_summary_options();
	},
	document_type(frm) {
		frm.set_value("child_tables", []);
		frm.set_value("active_child_table_field", "");
		frm.set_value("child_field_mappings", []);
		frm._set_erp_field_options();
		frm._set_child_table_options();
		frm._set_summary_options();
	},
	summary_child_table(frm) {
		frm._set_summary_options();
	},
	sync_child_table(frm) {
		frm._set_child_table_options();
	},
	active_child_table_field(frm) {
		frm._set_child_field_options();
	},
});

frappe.ui.form.on("Lark Sync Field", {
	field_mappings_add(frm) {
		if (frm._set_erp_field_options) {
			frm._set_erp_field_options();
		}
	},
});

frappe.ui.form.on("Lark Sync Child Field", {
	child_field_mappings_add(frm, cdt, cdn) {
		const activeField = frm.doc.active_child_table_field;
		if (activeField && cdt && cdn) {
			frappe.model.set_value(cdt, cdn, "child_table_field", activeField);
		}
		frm._set_child_table_options?.();
	},
	child_table_field(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row || !row.child_table_field) {
			return;
		}
		frm.set_value("active_child_table_field", row.child_table_field);
		frm._set_child_field_options?.();
	},
	child_field(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row || !row.child_field) {
			return;
		}
		if (row.child_field && !row.child_field_path) {
			frappe.model.set_value(cdt, cdn, "child_field_path", row.child_field);
		}
	},
});

frappe.ui.form.on("Lark Sync Child Table", {
	child_table_field(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row || !row.child_table_field) {
			return;
		}
		if (frm._child_table_map && frm._child_table_map[row.child_table_field]) {
			frappe.model.set_value(cdt, cdn, "child_table_doctype", frm._child_table_map[row.child_table_field]);
		}
		if (!frm.doc.active_child_table_field) {
			frm.set_value("active_child_table_field", row.child_table_field);
		}
		frm._set_child_table_options?.();
	},
});

frappe.ui.form.on("Lark Sync Field", {
	erp_field(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row || !row.erp_field) {
			return;
		}
		if (row.erp_field && !row.erp_field_path) {
			frappe.model.set_value(cdt, cdn, "erp_field_path", row.erp_field);
		}
	},
});
