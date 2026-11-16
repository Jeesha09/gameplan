import frappe

from gameplan.activity_counts import backfill_activity_counts


def execute():
	frappe.db.add_index("GP Discussion", ["owner"])
	frappe.db.add_index("GP Reaction", ["user"])
	backfill_activity_counts()
