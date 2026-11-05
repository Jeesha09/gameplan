import frappe


def execute():
	# Single doctypes do not store defaults for fields added after install.
	stored = frappe.db.get_singles_dict("GP Posting Settings")
	for field in frappe.get_meta("GP Posting Settings").fields:
		if field.default is not None and field.fieldname not in stored:
			frappe.db.set_single_value("GP Posting Settings", field.fieldname, field.default)
