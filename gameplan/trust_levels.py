"""Site-wide trust levels that mirror Discourse: New, Basic, Member, Regular and Leader.

Decisions D103 to D132. A member earns Basic and Member from visits, discussions entered,
reactions and replies, Regular from the same signals over a rolling window, and Leader only by
hand. Levels are stored on GP Trust Level, one row a person, so the posting path reads one row
by primary key. Requirements are checked once a day per member, when a post is accepted, and
in a nightly job that reads only candidate rows. Every count stops at the number it needs.
"""

import math
from datetime import timedelta

import frappe
from frappe import _
from frappe.query_builder import functions as fn
from frappe.utils import cint, get_datetime

import gameplan
from gameplan.api import require_admin
from gameplan.restrictions import active_condition, utc_now

LEVELS = ("New", "Basic", "Member", "Regular", "Leader")
NEW, BASIC, MEMBER, REGULAR, LEADER = range(5)
LEVEL_ACTIONS = ("Level Changed", "Level Locked", "Level Unlocked", "Regular Promotion", "Regular Demotion")
REMOVAL_ACTIONS = ("Ban", "Suspend", "Silence")
# Setting: (default, smallest, largest).
REQUIREMENTS = {
	"basic_entered": (5, 0, 1000),
	"basic_days": (2, 0, 1000),
	"basic_accepted": (1, 0, 1000),
	"member_days": (15, 0, 1000),
	"member_given": (1, 0, 1000),
	"member_received": (1, 0, 1000),
	"member_replied": (3, 0, 1000),
	"member_entered": (20, 0, 1000),
	"regular_window": (100, 30, 365),
	"regular_days": (50, 0, 365),
	"regular_replied": (10, 0, 1000),
	"regular_entered_percent": (25, 0, 100),
	"regular_entered_max": (500, 0, 5000),
	"regular_given": (30, 0, 1000),
	"regular_received": (20, 0, 1000),
	"regular_received_users": (5, 0, 1000),
	"regular_max_removed": (5, 0, 1000),
	"regular_restriction_days": (180, 0, 3650),
	"regular_grace_days": (14, 0, 365),
}
JOB_BATCH = 500
COMMIT_EVERY = 50
TIME_BUDGET = 240
CONTINUATION_BUDGET = 1200
VISIT_CACHE_SECONDS = 26 * 3600


def clock():
	import time

	return time.monotonic()


def config():
	doc = frappe.get_cached_doc("GP Trust Settings")
	return frappe._dict(
		enabled=cint(doc.enabled),
		**{field: cint(doc.get(field)) for field in REQUIREMENTS},
	)


def is_enabled():
	return bool(config().enabled)


def has_level(user):
	"""Members and invited Guests have a level. Global admins and visitors do not (D114, D115)."""
	if not user or gameplan.is_anonymous(user) or gameplan.is_admin(user):
		return False
	roles = set(frappe.get_roles(user))
	return bool(roles & {"Gameplan Member", "Gameplan Guest"})


def level_of(user=None):
	"""The member's level, or None while levels are off or for someone outside levels."""
	user = user or frappe.session.user
	if not is_enabled() or not has_level(user):
		return None
	return ensure_row(user).level


def stored_row(user):
	return frappe.db.get_value(
		"GP Trust Level", user, ["name", "user", "level", "locked", "grace_until"], as_dict=True
	)


def ensure_row(user):
	"""The member's row, worked out from their activity the first time it is needed (D125)."""
	row = stored_row(user)
	if row:
		row.level = cint(row.level)
		return row
	level = early_level(user, config())
	try:
		frappe.get_doc(doctype="GP Trust Level", user=user, level=level).insert(ignore_permissions=True)
	except frappe.DuplicateEntryError:
		# Another request created it first.
		pass
	row = stored_row(user)
	row.level = cint(row.level)
	return row


# Signals --------------------------------------------------------------------------------------
# Each count reads at most `limit` rows through an index on the member's own rows.


def entered(user, limit, since=None):
	Visit = frappe.qb.DocType("GP Discussion Visit")
	query = frappe.qb.from_(Visit).select(Visit.name).where(Visit.user == user)
	if since:
		query = query.where(Visit.last_visit >= since)
	return len(query.limit(limit).run()) if limit else 0


def visit_days(user, limit, since=None):
	Day = frappe.qb.DocType("GP Visit Day")
	query = frappe.qb.from_(Day).select(Day.name).where(Day.user == user)
	if since:
		query = query.where(Day.day >= since.date())
	return len(query.limit(limit).run()) if limit else 0


def accepted(user, limit):
	if not limit:
		return 0
	Discussion, Comment = frappe.qb.DocType("GP Discussion"), frappe.qb.DocType("GP Comment")
	found = len(
		frappe.qb.from_(Discussion)
		.select(Discussion.name)
		.where(
			(Discussion.owner == user) & Discussion.hidden_at.isnull() & Discussion.spam_removed_at.isnull()
		)
		.limit(limit)
		.run()
	)
	if found < limit:
		found += len(
			frappe.qb.from_(Comment)
			.select(Comment.name)
			.where((Comment.owner == user) & (Comment.reference_doctype == "GP Discussion"))
			.where(
				Comment.deleted_at.isnull() & Comment.hidden_at.isnull() & Comment.spam_removed_at.isnull()
			)
			.limit(limit - found)
			.run()
		)
	return found


def given(user, limit, since=None):
	Reaction = frappe.qb.DocType("GP Reaction")
	query = frappe.qb.from_(Reaction).select(Reaction.name).where(Reaction.user == user)
	if since:
		query = query.where(Reaction.creation >= since)
	return len(query.limit(limit).run()) if limit else 0


def received(user, limit, since=None, *, distinct=False):
	"""Reactions other people gave the member's posts, or with `distinct` the people who gave them."""
	if not limit:
		return 0
	Reaction = frappe.qb.DocType("GP Reaction")
	found = set() if distinct else []
	for doctype in ("GP Discussion", "GP Comment"):
		Post = frappe.qb.DocType(doctype)
		query = (
			frappe.qb.from_(Post)
			.join(Reaction)
			# Reaction names are text: a number here would stop the index being used.
			.on(
				(Reaction.reference_doctype == doctype)
				& (Reaction.reference_name == fn.Cast_(Post.name, "varchar"))
			)
			.select(Reaction.user)
			.where((Post.owner == user) & (Reaction.user != user))
		)
		if since:
			query = query.where(Reaction.creation >= since)
		if distinct:
			query = query.distinct()
		rows = query.limit(limit - len(found)).run(pluck=True)
		if distinct:
			found.update(rows)
		else:
			found.extend(rows)
		if len(found) >= limit:
			break
	return len(found)


def replied(user, limit, since=None):
	Comment = frappe.qb.DocType("GP Comment")
	query = (
		frappe.qb.from_(Comment)
		.select(Comment.reference_name)
		.distinct()
		.where(
			(Comment.owner == user)
			& (Comment.reference_doctype == "GP Discussion")
			& Comment.deleted_at.isnull()
		)
	)
	if since:
		query = query.where(Comment.creation >= since)
	return len(query.limit(limit).run()) if limit else 0


def removed(user, limit, since):
	"""Posts of the member that a moderator hid or removed as spam since `since`."""
	found = 0
	for doctype in ("GP Discussion", "GP Comment"):
		Post = frappe.qb.DocType(doctype)
		found += len(
			frappe.qb.from_(Post)
			.select(Post.name)
			.where((Post.owner == user) & ((Post.hidden_at >= since) | (Post.spam_removed_at >= since)))
			.limit(limit - found)
			.run()
		)
		if found >= limit:
			break
	return found


def restricted(user, since=None):
	"""A ban, suspension or silence in force now, or with `since` one that started after it."""
	Restriction = frappe.qb.DocType("GP User Restriction")
	if (
		frappe.qb.from_(Restriction)
		.select(Restriction.name)
		.where((Restriction.user == user) & active_condition(Restriction))
		.limit(1)
		.run()
	):
		return True
	if not since:
		return False
	Log = frappe.qb.DocType("GP Moderation Log")
	return bool(
		frappe.qb.from_(Log)
		.select(Log.name)
		.where((Log.user == user) & Log.action.isin(REMOVAL_ACTIONS) & (Log.creation >= since))
		.limit(1)
		.run()
	)


def entered_needed(cfg, since):
	"""Regular needs a share of the discussions started site-wide in the window, up to a cap."""
	key = f"gameplan:trust:discussions_since:{since.date()}"
	started = frappe.cache.get_value(key)
	if started is None:
		Discussion = frappe.qb.DocType("GP Discussion")
		started = (
			frappe.qb.from_(Discussion)
			.select(fn.Count("*"))
			.where(
				(Discussion.creation >= since)
				& Discussion.hidden_at.isnull()
				& Discussion.spam_removed_at.isnull()
			)
			.run()[0][0]
		)
		frappe.cache.set_value(key, started, expires_in_sec=3600)
	return min(math.ceil(cint(started) * cfg.regular_entered_percent / 100), cfg.regular_entered_max)


# Requirements ---------------------------------------------------------------------------------


def requirements(user, level, cfg, *, now=None):
	"""Yield each requirement of `level` as a dict: key, required, actual, met.

	Each actual stops at what the requirement needs, so a generator lets callers stop early.
	"""

	def at_least(key, required, count):
		actual = count(required)
		return {"key": key, "required": required, "actual": actual, "met": actual >= required}

	if level == BASIC:
		yield at_least("entered", cfg.basic_entered, lambda n: entered(user, n))
		yield at_least("days", cfg.basic_days, lambda n: visit_days(user, n))
		yield at_least("accepted", cfg.basic_accepted, lambda n: accepted(user, n))
	elif level == MEMBER:
		yield at_least("days", cfg.member_days, lambda n: visit_days(user, n))
		yield at_least("given", cfg.member_given, lambda n: given(user, n))
		yield at_least("received", cfg.member_received, lambda n: received(user, n))
		yield at_least("replied", cfg.member_replied, lambda n: replied(user, n))
		yield at_least("entered", cfg.member_entered, lambda n: entered(user, n))
	elif level == REGULAR:
		now = now or utc_now()
		since = now - timedelta(days=cfg.regular_window)
		yield at_least("days", cfg.regular_days, lambda n: visit_days(user, n, since))
		yield at_least("replied", cfg.regular_replied, lambda n: replied(user, n, since))
		yield at_least("entered", entered_needed(cfg, since), lambda n: entered(user, n, since))
		yield at_least("given", cfg.regular_given, lambda n: given(user, n, since))
		yield at_least("received", cfg.regular_received, lambda n: received(user, n, since))
		yield at_least(
			"received_users",
			cfg.regular_received_users,
			lambda n: received(user, n, since, distinct=True),
		)
		most = cfg.regular_max_removed
		actual = removed(user, most + 1, since)
		yield {"key": "removed", "required": most, "actual": actual, "met": actual <= most}
		clean_since = now - timedelta(days=cfg.regular_restriction_days)
		hit = restricted(user, clean_since)
		yield {"key": "restrictions", "required": 0, "actual": int(hit), "met": not hit}


def meets(user, level, cfg, *, now=None):
	return all(requirement["met"] for requirement in requirements(user, level, cfg, now=now))


def early_level(user, cfg):
	"""New, Basic or Member from what the member has done. Regular comes from the nightly job."""
	if not meets(user, BASIC, cfg):
		return NEW
	return MEMBER if meets(user, MEMBER, cfg) else BASIC


# Changing a level -----------------------------------------------------------------------------


def apply_level(row, level, cfg, *, notify=True):
	"""Store a level, start the Regular grace period, and tell the member."""
	previous = cint(row.level)
	values = {"level": level, "grace_until": None}
	if level == REGULAR:
		values["grace_until"] = utc_now() + timedelta(days=cfg.regular_grace_days)
	frappe.db.set_value("GP Trust Level", row.name, values, update_modified=False)
	row.update(values)
	if notify and level != previous:
		notify_change(row.user, previous, level)


MESSAGES = {
	BASIC: "You are now Basic. You can add more links, images, files and mentions to your posts.",
	MEMBER: "You are now a Member. You can post more often.",
	REGULAR: "You are now a Regular. Your posts skip the content caps.",
	LEADER: "You are now a Leader.",
}


def notify_change(user, previous, level):
	if level > previous:
		message = _(MESSAGES[level])
	elif previous == REGULAR and level == MEMBER:
		message = _("You are now a Member. Keep visiting and taking part to become a Regular again.")
	else:
		message = _("Your trust level is now {0}.").format(_(LEVELS[level]))
	frappe.get_doc(
		doctype="GP Notification", type="Trust Level", to_user=user, from_user=user, message=message
	).insert(ignore_permissions=True)
	from gameplan.realtime import notify_notification_counts_refresh

	notify_notification_counts_refresh([user])


def log_level(user, action, reason="", previous=None, level=None):
	frappe.get_doc(
		doctype="GP Moderation Log",
		# Site-wide entries have no Community; account history reads them by "".
		community="",
		user=user,
		action=action,
		reason=reason,
		previous_level="" if previous is None else LEVELS[previous],
		level="" if level is None else LEVELS[level],
	).insert(ignore_permissions=True)


def check_user(user):
	"""Move a New or Basic member up as far as Member when they qualify (D123)."""
	if not is_enabled() or not has_level(user):
		return
	cfg = config()
	row = stored_row(user)
	if not row:
		ensure_row(user)
		return
	if row.locked or cint(row.level) >= MEMBER or restricted(user):
		return
	level = early_level(user, cfg)
	if level > cint(row.level):
		apply_level(row, level, cfg)


def check_after_post(doc, method=None):
	"""`after_insert` of a published discussion or reply: an accepted post can earn Basic."""
	from gameplan.approval_policy import supports_approval

	if not supports_approval(doc) or not is_enabled() or not has_level(doc.owner):
		return
	row = stored_row(doc.owner)
	if row and (row.locked or cint(row.level) >= MEMBER):
		return
	frappe.enqueue(check_user, queue="short", user=doc.owner, enqueue_after_commit=True, now=frappe.in_test)


# Visits ---------------------------------------------------------------------------------------


def record_visit():
	"""`before_request`: count today as a visit day, once per member per UTC day (D122).

	A cache key answers every later request of the day, so this costs one cache read.
	"""
	user = frappe.session.user
	if gameplan.is_anonymous(user) or not is_enabled():
		return
	day = utc_now().date().isoformat()
	key = f"gameplan:trust:visit:{user}:{day}"
	if frappe.cache.get_value(key):
		return
	frappe.cache.set_value(key, 1, expires_in_sec=VISIT_CACHE_SECONDS)
	if has_level(user):
		# GET requests roll back their writes, so a job records the day.
		frappe.enqueue(
			record_visit_day,
			queue="short",
			user=user,
			day=day,
			job_id=key,
			deduplicate=True,
			now=frappe.in_test,
		)


def record_visit_day(user, day):
	if frappe.db.exists("GP Visit Day", {"user": user, "day": day}):
		return
	add_visit_days(user, [day])
	check_user(user)


def add_visit_days(user, days):
	frappe.db.bulk_insert(
		"GP Visit Day",
		["name", "user", "day", "creation", "modified", "owner", "modified_by"],
		[(frappe.generate_hash(length=16), user, day, utc_now(), utc_now(), user, user) for day in days],
		ignore_duplicates=True,
	)


def past_visit_days(user):
	"""Days with posts, reactions or discussion visits, for the first calculation (D125)."""
	Discussion, Comment, Reaction, Visit = (
		frappe.qb.DocType(dt) for dt in ("GP Discussion", "GP Comment", "GP Reaction", "GP Discussion Visit")
	)
	days = set()
	for table, column, owner in (
		(Discussion, Discussion.creation, Discussion.owner),
		(Comment, Comment.creation, Comment.owner),
		(Reaction, Reaction.creation, Reaction.user),
		(Visit, Visit.creation, Visit.user),
		(Visit, Visit.last_visit, Visit.user),
	):
		days.update(
			str(day)
			for day in frappe.qb.from_(table)
			.select(fn.Date(column))
			.distinct()
			.where(owner == user)
			.run(pluck=True)
			if day
		)
	return sorted(days)


# Settings -------------------------------------------------------------------------------------


@frappe.whitelist(methods=["GET", "POST"])
def get_settings():
	"""Return the trust level switch and requirements to global admins."""
	require_admin()
	return {
		**config(),
		"defaults": {field: default for field, (default, _, _) in REQUIREMENTS.items()},
		"ranges": {field: [smallest, largest] for field, (_, smallest, largest) in REQUIREMENTS.items()},
	}


@frappe.whitelist(methods=["POST"])
def save_settings(enabled: int, **values):
	"""Turn site-wide trust levels on or off and set every requirement. Global admins only."""
	require_admin()
	doc = frappe.get_doc("GP Trust Settings")
	was_enabled = cint(doc.enabled)
	for field, (_default, smallest, largest) in REQUIREMENTS.items():
		if field not in values:
			continue
		value = cint(values[field])
		if not smallest <= value <= largest:
			frappe.throw(
				_("{0} must be between {1} and {2}").format(_(doc.meta.get_label(field)), smallest, largest)
			)
		doc.set(field, value)
	if cint(doc.regular_days) > cint(doc.regular_window):
		frappe.throw(_("Days visited cannot be more than the Regular window"))
	doc.enabled = 1 if cint(enabled) else 0
	doc.save(ignore_permissions=True)
	if doc.enabled and not was_enabled:
		frappe.enqueue(backfill, queue="long", enqueue_after_commit=True)
	return get_settings()


# Manual changes -------------------------------------------------------------------------------


def check_target(user):
	require_admin()
	if not frappe.db.exists("User", user) or not has_level(user):
		frappe.throw(_("Global admins and people without Gameplan access do not have a level"))
	if not is_enabled():
		frappe.throw(_("Trust levels are not turned on"))


def clean_reason(reason):
	reason = (reason or "").strip()
	if not reason or len(reason) > 500:
		frappe.throw(_("Give a reason of up to 500 characters"))
	return reason


@frappe.whitelist(methods=["POST"])
def set_level(user: str, level: int, reason: str):
	"""Set a member's level, 0 New to 4 Leader, with a reason. Global admins only."""
	level = cint(level)
	if not NEW <= level <= LEADER:
		frappe.throw(_("Choose a level from 0 New to 4 Leader"))
	reason = clean_reason(reason)
	check_target(user)
	row = ensure_row(user)
	previous = cint(row.level)
	if previous != level:
		apply_level(row, level, config())
		log_level(user, "Level Changed", reason, previous, level)
	return {"level": level, "locked": cint(row.locked)}


@frappe.whitelist(methods=["POST"])
def set_lock(user: str, locked: int, reason: str):
	"""Lock a member's level so no rule changes it, or unlock it, with a reason. Global admins only."""
	reason = clean_reason(reason)
	check_target(user)
	row = ensure_row(user)
	locked = 1 if cint(locked) else 0
	if cint(row.locked) != locked:
		frappe.db.set_value("GP Trust Level", row.name, "locked", locked, update_modified=False)
		log_level(user, "Level Locked" if locked else "Level Unlocked", reason, row.level, row.level)
	return {"level": cint(row.level), "locked": locked}


# Reading --------------------------------------------------------------------------------------

PAGE = 50
# The level a member works toward. A Regular works to keep Regular. Leader has nothing next.
NEXT = {NEW: BASIC, BASIC: MEMBER, MEMBER: REGULAR, REGULAR: REGULAR}


def progress(user, row, cfg):
	level = cint(row.level)
	target = NEXT.get(level)
	return {
		"level": level,
		"locked": cint(row.locked),
		"grace_until": row.grace_until,
		"target": target,
		"window": cfg.regular_window,
		"restriction_days": cfg.regular_restriction_days,
		"requirements": [] if target is None else list(requirements(user, target, cfg)),
	}


@frappe.whitelist(methods=["POST"])
def my_level():
	"""Return the caller's own level and each requirement of the next one, or of keeping Regular."""
	user = frappe.session.user
	if gameplan.is_anonymous(user):
		frappe.throw(_("Sign in to see your level"), frappe.PermissionError)
	if not is_enabled() or not has_level(user):
		return {"enabled": 0}
	# POST: the first read can store the member's level, and a GET would discard it.
	return {"enabled": 1, **progress(user, ensure_row(user), config())}


@frappe.whitelist(methods=["POST"])
def member_progress(user: str):
	"""Return one person's level and each requirement of their next one. Global admins only."""
	check_target(user)
	return progress(user, ensure_row(user), config())


@frappe.whitelist(methods=["GET", "POST"])
def member_levels(level: str = "", query: str = "", start: int = 0):
	"""List people with their stored levels, 50 at a time, newest name first. Global admins only.

	`level` is a number, "pending" for people the first calculation has not reached, or "" for all.
	"""
	from gameplan.paging import page_start

	require_admin()
	Profile, User, Level, Role = (
		frappe.qb.DocType(dt) for dt in ("GP User Profile", "User", "GP Trust Level", "Has Role")
	)
	admins = (
		frappe.qb.from_(Role)
		.select(Role.parent)
		.where((Role.parenttype == "User") & Role.role.isin(["Gameplan Admin", "System Manager"]))
	)
	rows = (
		frappe.qb.from_(Profile)
		.join(User)
		.on(User.name == Profile.user)
		.left_join(Level)
		.on(Level.name == Profile.user)
		.select(User.name.as_("user"), User.full_name, Level.level, Level.locked, Level.grace_until)
		.where((User.enabled == 1) & (User.name != "Administrator") & User.name.notin(admins))
	)
	if level == "pending":
		rows = rows.where(Level.name.isnull())
	elif level != "":
		if not str(level).isdigit() or int(level) >= len(LEVELS):
			frappe.throw(_("Choose a level from 0 New to 4 Leader"))
		rows = rows.where(Level.level == cint(level))
	query = (query or "").strip()
	if query:
		rows = rows.where(User.full_name.like(f"{query}%") | User.name.like(f"{query}%"))
	rows = (
		rows.orderby(User.full_name)
		.orderby(User.name)
		.limit(PAGE + 1)
		.offset(page_start(start))
		.run(as_dict=True)
	)
	members = [
		{
			"user": row.user,
			"full_name": row.full_name,
			"level": cint(row.level),
			"locked": cint(row.locked),
			"grace_until": row.grace_until,
			"pending": int(row.level is None),
		}
		for row in rows[:PAGE]
	]
	return {"enabled": int(is_enabled()), "members": members, "more": len(rows) > PAGE}


@frappe.whitelist(methods=["GET", "POST"])
def community_levels(community: str):
	"""Return each member's stored level for a Community's staff to read. Changes are global-admin only."""
	from gameplan.community_bans import can_moderate_community

	if not can_moderate_community(community):
		frappe.throw(_("Only Community moderators can see levels"), frappe.PermissionError)
	if not is_enabled():
		return {"enabled": 0, "levels": {}}
	Member, Level = frappe.qb.DocType("GP Member"), frappe.qb.DocType("GP Trust Level")
	rows = (
		frappe.qb.from_(Member)
		.join(Level)
		.on(Level.name == Member.user)
		.select(Member.user, Level.level)
		.where((Member.parenttype == "GP Team") & (Member.parent == str(community)))
		.run(as_dict=True)
	)
	return {"enabled": 1, "levels": {row.user: cint(row.level) for row in rows}}


# Jobs -----------------------------------------------------------------------------------------


def nightly():
	"""Daily: promote Members to Regular and recheck Regulars (D106, D119)."""
	if not is_enabled():
		return
	frappe.enqueue(promote_regulars, queue="long", now=frappe.in_test)
	frappe.enqueue(recheck_regulars, queue="long", now=frappe.in_test)


def promote_regulars(after="", budget=TIME_BUDGET):
	"""Promote Members who visited since yesterday and now meet every Regular requirement."""
	cfg = config()
	if not cfg.enabled:
		return
	since = (utc_now() - timedelta(days=1)).date()
	Level, Day = frappe.qb.DocType("GP Trust Level"), frappe.qb.DocType("GP Visit Day")

	def candidates(after):
		return (
			frappe.qb.from_(Level)
			.join(Day)
			.on(Day.user == Level.user)
			.select(Level.user)
			.distinct()
			.where((Level.level == MEMBER) & (Level.locked == 0) & (Level.user > after) & (Day.day >= since))
			.orderby(Level.user)
			.limit(JOB_BATCH)
			.run(pluck=True)
		)

	def promote(user):
		row = stored_row(user)
		if (
			row
			and not row.locked
			and cint(row.level) == MEMBER
			and not restricted(user)
			and meets(user, REGULAR, cfg)
		):
			apply_level(row, REGULAR, cfg)
			log_level(user, "Regular Promotion", "", MEMBER, REGULAR)

	in_slices(
		candidates,
		promote,
		lambda after: frappe.enqueue(promote_regulars, queue="long", after=after, budget=CONTINUATION_BUDGET),
		after,
		budget,
	)


def recheck_regulars(after="", budget=TIME_BUDGET):
	"""Move a Regular who no longer meets the requirements to Member, after the grace period."""
	cfg = config()
	if not cfg.enabled:
		return
	now = utc_now()
	Level = frappe.qb.DocType("GP Trust Level")

	def candidates(after):
		return (
			frappe.qb.from_(Level)
			.select(Level.user)
			.where((Level.level == REGULAR) & (Level.locked == 0) & (Level.user > after))
			.where(Level.grace_until.isnull() | (Level.grace_until <= now))
			.orderby(Level.user)
			.limit(JOB_BATCH)
			.run(pluck=True)
		)

	def recheck(user):
		row = stored_row(user)
		if not row or row.locked or cint(row.level) != REGULAR:
			return
		if row.grace_until and get_datetime(row.grace_until) > now:
			return
		if not meets(user, REGULAR, cfg, now=now):
			apply_level(row, MEMBER, cfg)
			log_level(user, "Regular Demotion", "", REGULAR, MEMBER)

	in_slices(
		candidates,
		recheck,
		lambda after: frappe.enqueue(recheck_regulars, queue="long", after=after, budget=CONTINUATION_BUDGET),
		after,
		budget,
	)


def backfill(after="", budget=TIME_BUDGET):
	"""Work out every member's level from their past activity after levels are turned on (D125).

	Nobody is told. Stored levels never drop here. Until the job reaches a member, their level is
	worked out the first time it is needed.
	"""
	cfg = config()
	if not cfg.enabled:
		return

	def people(after):
		return frappe.get_all(
			"GP User Profile",
			filters={"user": [">", after]},
			pluck="user",
			order_by="user asc",
			limit=JOB_BATCH,
		)

	def work_out(user):
		if not has_level(user):
			return
		add_visit_days(user, past_visit_days(user))
		row = stored_row(user)
		if not row:
			ensure_row(user)
			return
		if row.locked:
			return
		level = early_level(user, cfg)
		if level > cint(row.level):
			apply_level(row, level, cfg, notify=False)

	in_slices(
		people,
		work_out,
		lambda after: frappe.enqueue(backfill, queue="long", after=after, budget=CONTINUATION_BUDGET),
		after,
		budget,
	)


def in_slices(fetch, handle, resume, after, budget):
	"""Handle each key `fetch(after)` returns, a page at a time, committing as it goes.

	After `budget` seconds it commits, calls `resume(last key)` to queue the rest as a new job, and stops.
	"""
	started = clock()
	while keys := fetch(after):
		for number, key in enumerate(keys, 1):
			after = key
			handle(key)
			if number % COMMIT_EVERY == 0:
				frappe.db.commit()  # nosemgrep
			if clock() - started > budget:
				frappe.db.commit()  # nosemgrep
				resume(after)
				return
		frappe.db.commit()  # nosemgrep


def delete_user_rows(doc, method=None):
	"""`on_trash` of User: a deleted account takes its level and visit days with it."""
	frappe.db.delete("GP Trust Level", {"user": doc.name})
	frappe.db.delete("GP Visit Day", {"user": doc.name})
