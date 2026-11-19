import frappe

SETTINGS = "GP Trust Settings"
FIELDS = {
	"member_days": "contributor_days",
	"member_given": "contributor_given",
	"member_received": "contributor_received",
	"member_replied": "contributor_replied",
	"member_entered": "contributor_entered",
}


def execute():
	"""Trust level 2 is called Contributor, not Member. Rename its settings and stored names."""
	# The settings are a Single, so each value is a row in tabSingles keyed by field name.
	for old, new in FIELDS.items():
		# A default may already be stored under the new name. The old row holds the real value.
		if frappe.db.exists("Singles", {"doctype": SETTINGS, "field": old}):
			frappe.db.delete("Singles", {"doctype": SETTINGS, "field": new})
		frappe.db.sql(
			"update `tabSingles` set field = %s where doctype = %s and field = %s",
			(new, SETTINGS, old),
		)
	frappe.clear_cache(doctype=SETTINGS)

	frappe.db.set_value(
		"GP Team", {"approval_min_level": "Member"}, "approval_min_level", "Contributor", update_modified=False
	)
	for field in ("previous_level", "level"):
		frappe.db.set_value(
			"GP Moderation Log", {field: "Member"}, field, "Contributor", update_modified=False
		)
