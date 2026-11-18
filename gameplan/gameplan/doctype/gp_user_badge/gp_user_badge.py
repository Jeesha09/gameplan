# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# MIT License. See license.txt

import frappe
from frappe.model.document import Document


class GPUserBadge(Document):
	pass


def on_doctype_update():
	# One grant per badge, person, post and grant number. Badges earned once store an empty
	# reference and 0, so a second grant from a racing job is a duplicate, not a new row.
	frappe.db.add_unique(
		"GP User Badge", ["badge", "user", "reference_doctype", "reference_name", "seq"], "grant_key"
	)
	frappe.db.add_index("GP User Badge", ["user", "badge"], "user_badge")
	frappe.db.add_index("GP User Badge", ["badge", "granted_at"], "badge_granted")
