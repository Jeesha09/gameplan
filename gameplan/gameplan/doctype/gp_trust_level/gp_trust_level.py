# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# MIT License. See license.txt

import frappe
from frappe.model.document import Document


class GPTrustLevel(Document):
	pass


def on_doctype_update():
	# The nightly job reads Regulars to recheck and Members to promote.
	frappe.db.add_index("GP Trust Level", ["level", "locked", "user"], "level_candidates")
