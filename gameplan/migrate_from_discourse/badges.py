"""The `badges` step: bring over Discourse badge grants for the badges Gameplan ports.

Runs after users, topics and trust levels, because it maps people and posts through the
Discourse ID Map those steps wrote. Grants are inserted in bulk with no notifications. Helper
badges have no Discourse grants: the silent full pass that runs when badges are turned on
works them out from the imported solutions, along with any badge Discourse missed.
"""

import frappe
from frappe.utils import cint, now

from gameplan.badges import catalog
from gameplan.badges.engine import FIELDS

from . import config, get_mapped, load_id_map, local_time, log, outcomes, run_query, slice_filter, writes


def migrate_badges():
	load_id_map("users")
	ids = list(catalog.BY_DISCOURSE_ID)
	last_id = 0
	while rows := get_grants(ids, last_id, config.batch_size):
		last_id = rows[-1].id
		grants = [grant for row in rows if (grant := to_grant(row))]
		outcomes["badges", "skipped"] += len(rows) - len(grants)
		outcomes["badges", "done"] += len(grants)
		writes["GP User Badge"] += len(grants)
		if not config.dry_run and grants:
			insert(grants)
			frappe.db.commit()
		log(f"[badges] up to id {last_id} · {len(grants)} grants")
	if frappe.db.get_single_value("GP Badge Settings", "enabled"):
		log("[badges] badges are on: run gameplan.badges.engine.full_pass with notify=False")
	else:
		log("[badges] turning badges on works out Helper and anything Discourse missed")


def get_grants(discourse_ids, last_id, limit):
	user_filter, user_values = slice_filter("user_badges.user_id", config.user_ids)
	return run_query(
		f"""
		select user_badges.id, user_badges.badge_id, user_badges.user_id, user_badges.seq,
			user_badges.is_favorite, {local_time("user_badges.granted_at")} as granted_at,
			posts.id as post_id, posts.topic_id, posts.post_number
		from user_badges
		left join posts on posts.id = user_badges.post_id
		where user_badges.id > %s and user_badges.badge_id = any(%s) {user_filter}
		order by user_badges.id asc
		limit %s
	""",
		(last_id, discourse_ids, *user_values, limit),
	)


def to_grant(row):
	"""The Gameplan grant for one Discourse grant, or None when its person or post is not here."""
	key = catalog.BY_DISCOURSE_ID[row.badge_id]
	spec = catalog.BY_KEY[key]
	user = get_mapped("users", row.user_id)
	if not user:
		return None
	reference = ("", "")
	if spec.per_post:
		reference = post_reference(row)
		if not reference:
			return None
	# Discourse numbers repeat grants from 0; Gameplan numbers Anniversary by the year.
	seq = cint(row.seq) + 1 if spec.multiple_grant else 0
	return (key, user, row.granted_at, *reference, seq, cint(row.is_favorite))


def post_reference(row):
	if not row.post_id:
		return None
	if cint(row.post_number) == 1:
		name = get_mapped("topics", row.topic_id)
		return ("GP Discussion", str(name)) if name else None
	name = get_mapped("posts", row.post_id)
	return ("GP Comment", str(name)) if name else None


def insert(grants):
	stamp = now()
	frappe.db.bulk_insert(
		"GP User Badge",
		["name", *FIELDS, "is_favorite", "creation", "modified", "owner", "modified_by"],
		[
			(frappe.generate_hash(length=16), *grant, stamp, stamp, "Administrator", "Administrator")
			for grant in grants
		],
		ignore_duplicates=True,
	)
