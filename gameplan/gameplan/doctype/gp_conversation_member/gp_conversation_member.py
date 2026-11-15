# Copyright (c) 2026, Frappe Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class GPConversationMember(Document):
	def notify_update(self):
		pass


def on_doctype_update():
	frappe.db.add_unique("GP Conversation Member", ["conversation", "user"])
	frappe.db.add_index("GP Conversation Member", ["user", "last_message"])
	frappe.db.add_index("GP Conversation Member", ["user", "unread_count"])
