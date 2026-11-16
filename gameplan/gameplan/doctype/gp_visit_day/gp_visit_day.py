# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# MIT License. See license.txt

import frappe
from frappe.model.document import Document


class GPVisitDay(Document):
	pass


def on_doctype_update():
	frappe.db.add_unique("GP Visit Day", ["user", "day"], "user_day")
	# The nightly job reads who visited yesterday.
	frappe.db.add_index("GP Visit Day", ["day", "user"], "day_user")
