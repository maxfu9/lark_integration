import frappe
from frappe.model.document import Document

class LarkNotification(Document):
	def on_update(self):
		frappe.cache().delete_keys(f"lark_notifications:{self.document_type}:*")

	def on_trash(self):
		frappe.cache().delete_keys(f"lark_notifications:{self.document_type}:*")
