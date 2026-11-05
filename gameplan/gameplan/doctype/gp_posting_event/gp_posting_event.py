import frappe
from frappe.model.document import Document


class GPPostingEvent(Document):
	def notify_update(self):
		# Posting allowances are private account metadata.
		pass


def on_doctype_update():
	frappe.db.add_index("GP Posting Event", ["user", "kind", "accepted_at"], "account_posting_window")
	frappe.db.add_index("GP Posting Event", ["accepted_at"], "expired_posting_events")
