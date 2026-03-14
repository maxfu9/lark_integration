frappe.ui.form.on("Lark Integration Settings", {
	refresh(frm) {
		const webhook_url = `${window.location.origin}/api/method/lark_integration.api.lark_webhook`;

		// Authentication Instructions (Dropbox Style)
		const auth_html = `
			<div style="padding: 12px; background-color: var(--blue-50); border: 1px solid var(--blue-200); border-radius: 6px; margin-bottom: 15px; font-size: 13px;">
				<div style="font-weight: bold; color: var(--blue-700); margin-bottom: 4px;">Lark Setup Instructions</div>
				To get your credentials, create an app in the <a href="https://open.larksuite.com/document/home/index" target="_blank" style="font-weight: bold; text-decoration: underline;">Lark Developer Console</a>. 
				Ensure the app has <b>Contact</b>, <b>Task</b>, and <b>Calendar</b> permissions enabled.
			</div>
		`;
		frm.set_df_property("auth_instructions", "options", auth_html);
		
		frm.add_custom_button(__("Sync Lark IDs"), () => {
			frappe.call({
				method: "lark_integration.api.trigger_user_id_sync",
				freeze: true,
				freeze_message: __("Matching ERPNext users with Lark..."),
				callback: (r) => {
					if (r.message && r.message.status === "success") {
						let msg = __("User Sync Complete.");
						if (r.message.matched_count > 0) {
							msg += `<br><b>${__("Newly Matched")}:</b> ${r.message.matched_count}`;
						}
						if (r.message.already_synced > 0) {
							msg += `<br><b>${__("Already Synced")}:</b> ${r.message.already_synced}`;
						}
						frappe.msgprint(msg);
					}
				}
			});
		}, __("Integration"));

		// ToDo Webhook Instructions
		if (frm.doc.todo_sync_method === "Webhook") {
			const instructions = `
				<div style="background-color: var(--bg-light-gray); padding: 15px; border-radius: 8px; border-left: 5px solid var(--blue-500); margin-bottom: 20px;">
					<h4 style="margin-top: 0;">Lark ToDo Webhook Setup</h4>
					<p>To enable <b>real-time</b> ToDo synchronization, configure the <b>Event Subscription</b> in your Lark Developer Console:</p>
					<ol>
						<li>Set <b>Request URL</b> to: <br><code style="background: white; padding: 2px 5px; border-radius: 4px; border: 1px solid #ddd; display: inline-block; margin: 5px 0;">${webhook_url}</code></li>
						<li>Add events: <code>task.task.updated_v2</code> and <code>task.task.deleted_v2</code></li>
						<li>Lark will verify this URL immediately upon saving.</li>
					</ol>
				</div>
			`;
			frm.set_df_property("webhook_instruction", "options", instructions);
		}

		// Calendar Webhook Instructions
		if (frm.doc.calendar_sync_method === "Webhook") {
			const instructions = `
				<div style="background-color: var(--bg-light-gray); padding: 15px; border-radius: 8px; border-left: 5px solid var(--blue-500); margin-bottom: 20px;">
					<h4 style="margin-top: 0;">Lark Calendar Webhook Setup</h4>
					<p>To enable <b>real-time</b> Calendar synchronization, configure the <b>Event Subscription</b> in your Lark Developer Console:</p>
					<ol>
						<li>Set <b>Request URL</b> to: <br><code style="background: white; padding: 2px 5px; border-radius: 4px; border: 1px solid #ddd; display: inline-block; margin: 5px 0;">${webhook_url}</code></li>
						<li>Add events: <code>calendar.calendar_event.created_v4</code>, <code>calendar.calendar_event.updated_v4</code>, and <code>calendar.calendar_event.deleted_v4</code></li>
						<li>Lark will verify this URL immediately upon saving.</li>
					</ol>
				</div>
			`;
			frm.set_df_property("calendar_webhook_instruction", "options", instructions);
		}



		frm.add_custom_button("Take Backup Now", () => {
			frappe.call({
				method: "lark_integration.api.take_instant_backup",
				freeze: true,
				freeze_message: "Initiating Lark Backup...",
				callback: (r) => {
					if (r.message && r.message.status === "queued") {
						frappe.show_alert({
							message: __("Backup process queued. It will run in the background."),
							indicator: "green"
						});
					}
					frm.reload_doc();
				}
			});
		}, "Backup");

		frm.add_custom_button("Sync Tasks Now", () => {
			frappe.show_alert({ message: __("Starting task synchronization..."), indicator: "blue" });
			frappe.call({
				method: "lark_integration.api.pull_lark_tasks",
				freeze: true,
				freeze_message: __("Syncing tasks with Lark..."),
				args: { publish_progress: 1 },
				callback: (r) => {
					if (!r.exc) {
						frappe.show_alert({ message: __("Task synchronization complete"), indicator: "green" });
						frm.reload_doc();
					}
				},
				error: (r) => {
					frappe.show_alert({ message: __("Sync failed. Check error log."), indicator: "red" });
				},
			});
		}, "ToDo Sync");

		frm.add_custom_button("Fetch Task Lists", () => {
			frappe.call({
				method: "lark_integration.api.fetch_lark_task_lists",
				freeze: true,
				callback: (r) => {
					if (r.message && r.message.status === "success") {
						frappe.show_alert({ 
							message: __("Imported {0} task lists", [r.message.imported]), 
							indicator: "green" 
						});
					}
				}
			});
		}, "ToDo Sync");

		frm.add_custom_button("Sync Calendar Now", () => {
			frappe.show_alert({ message: __("Starting calendar synchronization..."), indicator: "blue" });
			frappe.call({
				method: "lark_integration.api.pull_lark_calendar_events",
				freeze: true,
				args: { publish_progress: true },
				callback: (r) => {
					if (!r.exc) {
						frappe.show_alert({ message: __("Calendar synchronization complete"), indicator: "green" });
						frm.reload_doc();
					}
				},
			});
		}, "Calendar Sync");

		// Realtime progress for backup
		frappe.realtime.on("lark_backup_progress", (data) => {
			frm.trigger("render_backup_progress", data);
		});

		// Force the eye icon to show even when a saved secret already exists.
		// Frappe hides it by default when this.value is truthy (saved ***).
		// We find the .toggle-password div directly in the DOM and remove "hidden".
		setTimeout(() => {
			const ctrl = frm.fields_dict["app_secret"];
			if (ctrl) {
				// Try control property first
				if (ctrl.toggle_password) {
					ctrl.toggle_password.removeClass("hidden");
				}
				// Also try direct DOM lookup as fallback
				ctrl.$wrapper && ctrl.$wrapper.find(".toggle-password").removeClass("hidden");
			}
		}, 500);
	},
	render_backup_progress(frm, data) {
		if (!data || data.percent === undefined) {
			frm.set_df_property("backup_progress", "options", "");
			return;
		}

		const percent = data.percent;
		const message = data.message || "";
		
		const html = `
			<div style="margin-top: 15px; padding: 10px; background: var(--gray-50); border-radius: 8px; border: 1px solid var(--gray-200);">
				<div style="font-size: 11px; font-weight: bold; margin-bottom: 6px; color: var(--text-muted); display: flex; justify-content: space-between;">
					<span>${message}</span>
					<span>${percent}%</span>
				</div>
				<div style="height: 6px; background-color: var(--gray-100); border-radius: 3px; overflow: hidden;">
					<div style="height: 100%; width: ${percent}%; background-color: var(--green-500); transition: width 0.4s ease;"></div>
				</div>
			</div>
		`;
		frm.set_df_property("backup_progress", "options", html);

		if (percent >= 100) {
			setTimeout(() => {
				frm.set_df_property("backup_progress", "options", "");
				frm.reload_doc();
			}, 3000);
		}
	},
	todo_sync_method(frm) {
		frm.trigger("refresh");
	},
	calendar_sync_method(frm) {
		frm.trigger("refresh");
	}
});
