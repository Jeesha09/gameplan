"""Badges that mirror Discourse (prd/badges.md).

Events add the people they affect to a Redis set, and `engine.process_queue` checks them every
few minutes. The nightly full pass catches anything the queue missed. Badges are off until a
global admin turns them on.
"""

import frappe
from frappe.utils import cint

QUEUE = "gameplan:badges:queue"


def is_enabled():
	return bool(cint(frappe.get_cached_doc("GP Badge Settings").enabled))


def queue(*users):
	users = [user for user in users if user and user not in ("Guest", "Administrator")]
	if users and is_enabled():
		frappe.cache.sadd(QUEUE, *users)


# Events ---------------------------------------------------------------------------------------


def on_post_change(doc, method=None):
	"""`on_update` of a discussion or reply: mentions, solutions, removals and anniversaries."""
	queue(doc.owner)


def on_reaction_change(doc, method=None):
	"""`after_insert` and `on_trash` of a reaction: the giver and the post's author."""
	if doc.reference_doctype not in ("GP Discussion", "GP Comment"):
		return
	queue(doc.user, frappe.db.get_value(doc.reference_doctype, doc.reference_name, "owner"))


def on_profile_change(doc, method=None):
	queue(doc.user)


def on_discussion_visit(doc, method=None):
	"""`on_update` of a discussion visit: Reader."""
	queue(doc.user)


def on_post_trash(doc, method=None):
	"""`on_trash` of a discussion or reply: grants for that post go with it."""
	frappe.db.delete("GP User Badge", {"reference_doctype": doc.doctype, "reference_name": str(doc.name)})


def on_user_trash(doc, method=None):
	frappe.db.delete("GP User Badge", {"user": doc.name})
