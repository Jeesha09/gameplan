import frappe

from gameplan.trust_levels import LIMITS


def execute():
	"""Store the default for each New and Basic limit a site has not saved yet (D134)."""
	for field, (default, _, _) in LIMITS.items():
		# get_single_value reads a missing Int as 0, which would refuse every post.
		if not frappe.db.exists("Singles", {"doctype": "GP Trust Settings", "field": field}):
			frappe.db.set_single_value("GP Trust Settings", field, default)
	frappe.clear_cache(doctype="GP Trust Settings")
