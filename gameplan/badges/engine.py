"""Working out a member's badges, storing the grants and telling the member.

`check_user` runs every family's rule for one person, stores the grants they do not hold yet,
and takes back the per-post badges whose post no longer qualifies. Jobs call it for queued
people every few minutes, and for everyone in the nightly full pass.
"""

import frappe
from frappe import _
from frappe.utils import cint

from gameplan.badges import QUEUE, catalog, is_enabled
from gameplan.badges.rules import RULES
from gameplan.restrictions import utc_now

COMMIT_EVERY = 50
TIME_BUDGET = 240
CONTINUATION_BUDGET = 1200
JOB_BATCH = 500
FIELDS = ["badge", "user", "granted_at", "reference_doctype", "reference_name", "seq"]


def check_user(user, *, notify=True):
	"""Grant `user` every enabled badge they have earned. Returns the keys granted."""
	if not is_enabled() or not can_earn(user):
		return []
	enabled = enabled_badges()
	held = held_grants(user)
	granted = []
	for family, rule in RULES.items():
		keys = [key for key in enabled if catalog.BY_KEY[key].family == family]
		if not keys or all(done(key, held) for key in keys):
			continue
		for key, grants in rule(user).items():
			if key not in keys:
				continue
			granted += store(key, user, grants, held)
			if catalog.BY_KEY[key].revocable:
				take_back(key, user, grants, held)
	if notify:
		for key in dict.fromkeys(granted):
			tell(user, key)
	return granted


def can_earn(user):
	"""Members, Guests and Gameplan admins earn badges. Visitors and system users do not."""
	import gameplan

	if not user or user == "Administrator" or gameplan.is_anonymous(user):
		return False
	return bool(set(frappe.get_roles(user)) & {"Gameplan Member", "Gameplan Guest", "Gameplan Admin"})


def enabled_badges():
	return set(frappe.get_all("GP Badge", filters={"enabled": 1}, pluck="name"))


def held_grants(user):
	"""{badge key: {(reference doctype, reference name, seq)}} for what `user` holds."""
	held = {}
	for row in frappe.get_all(
		"GP User Badge",
		filters={"user": user},
		fields=["badge", "reference_doctype", "reference_name", "seq"],
	):
		held.setdefault(row.badge, set()).add(grant_key(row))
	return held


def done(key, held):
	"""A badge earned once and already held needs no rule run."""
	spec = catalog.BY_KEY[key]
	return key in held and not spec.per_post and not spec.multiple_grant


def grant_key(row):
	return (row.reference_doctype or "", str(row.reference_name or ""), cint(row.seq))


def store(key, user, grants, held):
	new = [row for row in grants if grant_key(row) not in held.get(key, set())]
	if not new:
		return []
	now = utc_now()
	# Duplicates are ignored, so a job racing this one cannot grant a badge twice.
	frappe.db.bulk_insert(
		"GP User Badge",
		["name", *FIELDS, "creation", "modified", "owner", "modified_by"],
		[
			(
				frappe.generate_hash(length=16),
				key,
				user,
				row.granted_at,
				row.reference_doctype,
				row.reference_name,
				row.seq,
				now,
				now,
				"Administrator",
				"Administrator",
			)
			for row in new
		],
		ignore_duplicates=True,
	)
	held.setdefault(key, set()).update(grant_key(row) for row in new)
	return [key] * len(new)


def take_back(key, user, grants, held):
	"""Delete per-post grants whose post fell below the threshold, as Discourse does."""
	keep = {grant_key(row) for row in grants}
	for doctype, name, seq in held.get(key, set()) - keep:
		frappe.db.delete(
			"GP User Badge",
			{"badge": key, "user": user, "reference_doctype": doctype, "reference_name": name, "seq": seq},
		)
	held[key] = held.get(key, set()) & keep


def tell(user, key):
	spec = catalog.BY_KEY[key]
	frappe.get_doc(
		doctype="GP Notification",
		type="Badge",
		to_user=user,
		from_user=user,
		message=_("You earned the {0} badge.").format(_(spec.title)),
	).insert(ignore_permissions=True)
	from gameplan.realtime import notify_notification_counts_refresh

	notify_notification_counts_refresh([user])


# Jobs -----------------------------------------------------------------------------------------


def process_queue(budget=TIME_BUDGET):
	"""Every few minutes: check the people events queued since the last run."""
	if not is_enabled():
		frappe.cache.delete_value(QUEUE)
		return
	started = clock()
	checked = 0
	while (user := pop_queued()) and clock() - started < budget:
		check_user(user)
		checked += 1
		if checked % COMMIT_EVERY == 0:
			frappe.db.commit()  # nosemgrep


def pop_queued():
	user = frappe.cache.spop(QUEUE)
	return user.decode() if isinstance(user, bytes) else user


def full_pass(after="", budget=TIME_BUDGET, notify=True):
	"""Check everyone with a profile, in slices.

	Turning badges on runs it with `notify=False`. That first pass also counts past visit days
	from posts, reactions and visits, as turning trust levels on does, so Enthusiast is not
	empty until people have visited for weeks.
	"""
	if not is_enabled():
		return
	from gameplan.trust_levels import add_visit_days, in_slices, past_visit_days

	def handle(user):
		if not notify and can_earn(user):
			add_visit_days(user, past_visit_days(user))
		check_user(user, notify=notify)

	def people(after):
		return frappe.get_all(
			"GP User Profile",
			filters={"user": [">", after]},
			pluck="user",
			order_by="user asc",
			limit=JOB_BATCH,
		)

	in_slices(
		people,
		handle,
		lambda after: frappe.enqueue(
			full_pass, queue="long", after=after, budget=CONTINUATION_BUDGET, notify=notify
		),
		after,
		budget,
	)


def nightly():
	"""Daily: a full pass, which also grants each new Anniversary."""
	if is_enabled():
		frappe.enqueue(full_pass, queue="long", now=frappe.in_test)


def clock():
	import time

	return time.monotonic()
