

frappe.ui.form.on('ToDo', {
    refresh: function(frm) {
        if (frm.doc.lark_remind_at_due && !frm.doc.lark_reminder_offset) {
            frm.trigger('lark_remind_at_due');
        }
    },
    onload: function(frm) {
        if (frm.is_new()) {
            if (frm.doc.date === frappe.datetime.get_today() || !frm.doc.date) {
                frm.set_value('date', null);
            }
            if (frm.doc.lark_due_time) {
                frm.set_value('lark_due_time', null);
            }
        }
    },
    validate: function(frm) {
        if (!frm.doc.lark_due_time) {
            frm.doc.lark_due_time = null;
        }
    },
    lark_remind_at_due: function(frm) {
        if (frm.doc.lark_remind_at_due) {
            if (!frm.doc.lark_reminder_offset) {
                frappe.call({
                    method: 'frappe.client.get_value',
                    args: {
                        doctype: 'Lark Integration Settings',
                        fieldname: 'default_reminder_offset',
                    },
                    callback: function(r) {
                        let val = 'At due time';
                        if (r.message && r.message.default_reminder_offset) {
                            val = r.message.default_reminder_offset;
                        }
                        frm.set_value('lark_reminder_offset', val);
                        frm.refresh_field('lark_reminder_offset');
                    }
                });
            }
        } else {
            frm.set_value('lark_reminder_offset', null);
            frm.refresh_field('lark_reminder_offset');
        }
    }
});
