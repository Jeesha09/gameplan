# Copyright (c) 2026, Frappe Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class GPUserBlock(Document):
	def notify_update(self):
		pass


def on_doctype_update():
	frappe.db.add_unique("GP User Block", ["user", "blocked_user"])
	frappe.db.add_index("GP User Block", ["blocked_user"])
