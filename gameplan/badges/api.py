"""Badge endpoints. Anyone signed in reads badges. Who holds a badge, settings and manual changes are for admins."""

import frappe
from frappe import _
from frappe.query_builder import functions as fn
from frappe.utils import cint

import gameplan
from gameplan.api import require_admin
from gameplan.badges import catalog, is_enabled
from gameplan.restrictions import utc_now

PAGE = 50
MAX_FAVORITES = 3
BADGE_FIELDS = ["name", "title", "description", "badge_group", "family", "tier"]


def require_signed_in():
	if gameplan.is_anonymous():
		frappe.throw(_("Sign in to see badges"), frappe.PermissionError)


def badge_or_throw(badge):
	if not is_enabled() or not frappe.db.get_value("GP Badge", badge, "enabled"):
		frappe.throw(_("Badge not found"), frappe.DoesNotExistError)
	return frappe.db.get_value("GP Badge", badge, BADGE_FIELDS, as_dict=True)


def resolve_user(user):
	"""A Guest sees other people by handle, so a handle is accepted where a user id is."""
	from gameplan.guest_payload import users_for_handles

	return users_for_handles({user}).get(user, user)


# Reading --------------------------------------------------------------------------------------


@frappe.whitelist(methods=["GET"])
def list_badges():
	"""Return every enabled badge by group and whether you hold it. Admins also get how many people hold each."""
	require_signed_in()
	if not is_enabled():
		return {"enabled": 0, "badges": []}
	Grant = frappe.qb.DocType("GP User Badge")
	# Who holds a badge is for admins. Everyone else sees the badges and their own.
	holders = (
		dict(
			frappe.qb.from_(Grant)
			.select(Grant.badge, fn.Count(Grant.user).distinct())
			.where(Grant.revoked == 0)
			.groupby(Grant.badge)
			.run()
		)
		if gameplan.is_admin()
		else None
	)
	mine = set(
		frappe.get_all("GP User Badge", filters={"user": frappe.session.user, "revoked": 0}, pluck="badge")
	)
	badges = frappe.get_all("GP Badge", filters={"enabled": 1}, fields=BADGE_FIELDS, order_by="position asc")
	for badge in badges:
		if holders is not None:
			badge.holders = cint(holders.get(badge.name))
		badge.held = int(badge.name in mine)
	return {"enabled": 1, "badges": badges}


@frappe.whitelist(methods=["GET"])
def badge_holders(badge: str, before: str = ""):
	"""Return a badge and the people who earned it, newest first, 50 at a time before grant `before`. Admins only."""
	require_admin()
	info = badge_or_throw(badge)
	Grant = frappe.qb.DocType("GP User Badge")
	query = (
		frappe.qb.from_(Grant)
		.select(Grant.name, Grant.user, Grant.granted_at, Grant.reference_doctype, Grant.reference_name)
		.where((Grant.badge == badge) & (Grant.revoked == 0))
	)
	if before:
		cursor = frappe.db.get_value("GP User Badge", before, ["granted_at", "name"], as_dict=True)
		if not cursor:
			frappe.throw(_("Refresh the list"))
		query = query.where(
			(Grant.granted_at < cursor.granted_at)
			| ((Grant.granted_at == cursor.granted_at) & (Grant.name < cursor.name))
		)
	rows = query.orderby(Grant.granted_at, order=frappe.qb.desc).orderby(Grant.name, order=frappe.qb.desc)
	rows = rows.limit(PAGE + 1).run(as_dict=True)
	holders = [with_post(row) for row in rows[:PAGE]]
	return {
		"badge": info,
		"holders": holders,
		"next_cursor": str(rows[PAGE - 1].name) if len(rows) > PAGE else "",
	}


def with_post(row):
	"""Name the post a per-post grant is for, only when the reader can open it."""
	from gameplan.permissions import can_view_content

	holder = {"name": str(row.name), "user": row.user, "granted_at": row.granted_at}
	if row.reference_doctype and row.reference_name:
		if not frappe.db.exists(row.reference_doctype, row.reference_name):
			return holder
		post = frappe.get_doc(row.reference_doctype, row.reference_name)
		if can_view_content(frappe.session.user, post):
			discussion = (
				post
				if post.doctype == "GP Discussion"
				else frappe.get_doc("GP Discussion", post.reference_name)
			)
			holder["post"] = {
				"doctype": post.doctype,
				"name": str(post.name),
				"discussion": str(discussion.name),
				"space": str(discussion.project),
				"title": discussion.title,
			}
	return holder


@frappe.whitelist(methods=["GET"])
def user_badges(user: str):
	"""Return the badges one person holds, each once with how many times, and their favourites first."""
	require_signed_in()
	if not is_enabled():
		return {"enabled": 0, "badges": []}
	user = resolve_user(user)
	Grant, Badge = frappe.qb.DocType("GP User Badge"), frappe.qb.DocType("GP Badge")
	rows = (
		frappe.qb.from_(Grant)
		.join(Badge)
		.on(Badge.name == Grant.badge)
		.select(
			Badge.name,
			Badge.title,
			Badge.description,
			Badge.badge_group,
			Badge.family,
			Badge.tier,
			Badge.position,
			fn.Count("*").as_("count"),
			fn.Max(Grant.granted_at).as_("granted_at"),
			fn.Max(Grant.is_favorite).as_("is_favorite"),
		)
		.where((Grant.user == user) & (Grant.revoked == 0) & (Badge.enabled == 1))
		.groupby(Badge.name)
		.run(as_dict=True)
	)
	rows.sort(key=lambda row: (-cint(row.is_favorite), cint(row.position)))
	for row in rows:
		row.pop("position")
	return {"enabled": 1, "badges": rows}


def favorites(users):
	"""{user: [badge]} with each person's favourites, for the hover card. Empty while badges are off."""
	if not users or not is_enabled():
		return {}
	Grant, Badge = frappe.qb.DocType("GP User Badge"), frappe.qb.DocType("GP Badge")
	rows = (
		frappe.qb.from_(Grant)
		.join(Badge)
		.on(Badge.name == Grant.badge)
		.select(Grant.user, Badge.name, Badge.title, Badge.description, Badge.family, Badge.tier)
		.where(
			Grant.user.isin(users) & (Grant.is_favorite == 1) & (Grant.revoked == 0) & (Badge.enabled == 1)
		)
		.orderby(Badge.position)
		.run(as_dict=True)
	)
	# set_favorites marks one grant per badge, and at most three.
	chosen = {}
	for row in rows:
		chosen.setdefault(row.pop("user"), []).append(row)
	return chosen


@frappe.whitelist(methods=["POST"])
def set_favorites(badges: list[str]):
	"""Choose up to 3 of your own badges to show first on your profile and hover card."""
	require_signed_in()
	chosen = list(dict.fromkeys(frappe.parse_json(badges) or []))
	if len(chosen) > MAX_FAVORITES:
		frappe.throw(_("Choose up to {0} badges").format(MAX_FAVORITES))
	user = frappe.session.user
	held = set(frappe.get_all("GP User Badge", filters={"user": user, "revoked": 0}, pluck="badge"))
	if set(chosen) - held:
		frappe.throw(_("You can only choose badges you hold"))
	frappe.db.set_value("GP User Badge", {"user": user, "is_favorite": 1}, "is_favorite", 0)
	for badge in chosen:
		first = frappe.get_all(
			"GP User Badge",
			filters={"user": user, "badge": badge, "revoked": 0},
			pluck="name",
			order_by="granted_at asc",
			limit=1,
		)
		frappe.db.set_value("GP User Badge", first[0], "is_favorite", 1)
	return user_badges(user)


# Site administration --------------------------------------------------------------------------


@frappe.whitelist(methods=["GET", "POST"])
def get_settings():
	"""Return whether badges are on, and each badge with its switch. Global admins only."""
	require_admin()
	return {
		"enabled": int(is_enabled()),
		"badges": frappe.get_all(
			"GP Badge",
			fields=["name", "title", "description", "badge_group", "family", "tier", "enabled", "per_post"],
			order_by="position asc",
		),
	}


@frappe.whitelist(methods=["POST"])
def save_settings(enabled: int, disabled_badges: list[str] | None = None):
	"""Turn badges on or off, and turn off the badges named in `disabled_badges`. Global admins only."""
	require_admin()
	doc = frappe.get_doc("GP Badge Settings")
	was_enabled = cint(doc.enabled)
	doc.enabled = 1 if cint(enabled) else 0
	doc.save(ignore_permissions=True)
	if disabled_badges is not None:
		off = set(frappe.parse_json(disabled_badges))
		for name in frappe.get_all("GP Badge", pluck="name"):
			frappe.db.set_value("GP Badge", name, "enabled", int(name not in off), update_modified=False)
	if doc.enabled and not was_enabled:
		from gameplan.badges.engine import full_pass

		frappe.enqueue(full_pass, queue="long", notify=False, enqueue_after_commit=True)
	return get_settings()


@frappe.whitelist(methods=["POST"])
def grant_badge(user: str, badge: str, reason: str):
	"""Grant a person a badge by hand, with a reason. Global admins only. Only badges earned once can be."""
	from gameplan.badges.engine import can_earn, tell
	from gameplan.trust_levels import clean_reason

	require_admin()
	reason = clean_reason(reason)
	info = badge_or_throw(badge)
	spec = catalog.BY_KEY.get(badge, frappe._dict())
	if spec.per_post or spec.multiple_grant:
		frappe.throw(_("{0} cannot be granted by hand").format(_(info.title)))
	if not can_earn(user):
		frappe.throw(_("Only people with Gameplan access earn badges"))
	existing = frappe.db.get_value(
		"GP User Badge", {"user": user, "badge": badge}, ["name", "revoked"], as_dict=True
	)
	if existing and not existing.revoked:
		frappe.throw(_("They already hold {0}").format(_(info.title)))
	if existing:
		frappe.db.set_value(
			"GP User Badge",
			existing.name,
			{"revoked": 0, "granted_at": utc_now(), "granted_by": frappe.session.user},
		)
	else:
		frappe.get_doc(
			doctype="GP User Badge",
			badge=badge,
			user=user,
			granted_at=utc_now(),
			reference_doctype="",
			reference_name="",
			seq=0,
			granted_by=frappe.session.user,
		).insert(ignore_permissions=True)
	log(user, "Badge Granted", reason, info.title)
	tell(user, badge)
	return user_badges(user)


@frappe.whitelist(methods=["POST"])
def revoke_badge(user: str, badge: str, reason: str):
	"""Take a badge away from a person, with a reason. Global admins only. It is not re-earned by itself."""
	from gameplan.trust_levels import clean_reason

	require_admin()
	reason = clean_reason(reason)
	title = frappe.db.get_value("GP Badge", badge, "title")
	held = {"user": user, "badge": badge, "revoked": 0}
	if not title or not frappe.db.exists("GP User Badge", held):
		frappe.throw(_("They do not hold this badge"))
	# The rows stay, marked revoked, so the next automatic check does not grant it again.
	frappe.db.set_value("GP User Badge", held, {"revoked": 1, "is_favorite": 0})
	log(user, "Badge Revoked", reason, title)
	return user_badges(user)


def log(user, action, reason, title):
	frappe.get_doc(
		doctype="GP Moderation Log",
		# Site-wide entries have no Community; account history reads them by "".
		community="",
		user=user,
		action=action,
		reason=reason,
		title=title,
	).insert(ignore_permissions=True)
