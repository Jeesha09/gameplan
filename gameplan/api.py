# Copyright (c) 2021, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt


import json

import frappe
from frappe import _
from frappe.query_builder import Case, Order
from frappe.query_builder.functions import Count, Min
from frappe.utils import cint, split_emails, validate_email_address

import gameplan
from gameplan.activity_counts import ACTIVITY_COUNT_FIELDS
from gameplan.gameplan.doctype.gp_invitation.gp_invitation import get_invitation, grant_access
from gameplan.realtime import notify_notification_changed, unread_notification_count
from gameplan.roles import GAMEPLAN_ROLES, has_app_access
from gameplan.utils import validate_type
from gameplan.visibility import (
	VISIBILITY_GENERAL,
	VISIBILITY_MEMBER_ACCESS,
)


def require_admin():
	"""Gate an endpoint to admins only. Raises PermissionError (HTTP 403) otherwise."""
	if not gameplan.is_admin():
		frappe.throw(_("Only admins can perform this action"), frappe.PermissionError)


USER_INFO_BATCH_LIMIT = 100


@frappe.whitelist(allow_guest=True)
def get_user_info(user=None, users=None):
	"""Return Gameplan users with role, profile and 3-month counts: `user` for one, `users` for up to 100."""
	if frappe.session.user == "Guest":
		frappe.throw("Authentication failed", exc=frappe.AuthenticationError)
	if not has_app_access():
		frappe.throw("Not permitted", frappe.PermissionError)

	from gameplan.guest_payload import users_for_handles

	if user:
		if gameplan.is_guest() and user != frappe.session.user:
			user = users_for_handles([user]).get(user)
			if not user:
				frappe.throw("Use a profile handle to look up another user.", frappe.PermissionError)
		names = [user]
	elif users is not None:
		names = frappe.parse_json(users)
		if not isinstance(names, list) or len(names) > USER_INFO_BATCH_LIMIT:
			frappe.throw(_("users must be a list of at most {0}").format(USER_INFO_BATCH_LIMIT))
		if gameplan.is_guest():
			handles = users_for_handles(names)
			names = [
				frappe.session.user if name == frappe.session.user else handles.get(name) for name in names
			]
		names = [name for name in names if name and isinstance(name, str)]
	else:
		frappe.throw(_("Pass user or users"))

	return user_info_rows(names)


def user_info_rows(names):
	if not names:
		return []

	filters = {"roles.role": ["like", "Gameplan %"], "name": ["in", names]}

	users = frappe.qb.get_query(
		"User",
		filters=filters,
		fields=["name", "email", "enabled", "user_image", "full_name", "user_type", "creation", "time_zone"],
		order_by="full_name asc",
		distinct=True,
	).run(as_dict=1)
	if not users:
		return []

	# Get discussion counts for last 3 months
	Discussion = frappe.qb.DocType("GP Discussion")
	discussion_counts = (
		frappe.qb.from_(Discussion)
		.select(Discussion.owner, Count(Discussion.name).as_("count"))
		.where(Discussion.creation >= frappe.utils.add_months(frappe.utils.now(), -3))
		.where(Discussion.owner.isin([u.name for u in users]))
		.groupby(Discussion.owner)
	).run(as_dict=1)
	discussion_count_map = {d.owner: d.count for d in discussion_counts}

	# Get comment counts for last 3 months
	Comment = frappe.qb.DocType("GP Comment")
	comment_counts = (
		frappe.qb.from_(Comment)
		.select(Comment.owner, Count(Comment.name).as_("count"))
		.where(Comment.creation >= frappe.utils.add_months(frappe.utils.now(), -3))
		.where(Comment.owner.isin([u.name for u in users]))
		.groupby(Comment.owner)
	).run(as_dict=1)
	comment_count_map = {c.owner: c.count for c in comment_counts}

	role_filters = {"parenttype": "User", "role": ["in", GAMEPLAN_ROLES]}
	if names is not None:
		role_filters["parent"] = ["in", [u.name for u in users]]
	roles = frappe.db.get_all("Has Role", filters=role_filters, fields=["role", "parent"])
	# GAMEPLAN_ROLES is ordered by privilege, so after sorting the last role per user wins.
	role_map = {r.parent: r.role for r in sorted(roles, key=lambda r: GAMEPLAN_ROLES.index(r.role))}
	user_profiles = frappe.db.get_all(
		"GP User Profile",
		fields=[
			"user",
			"name",
			"image",
			"image_background_color",
			"is_image_background_removed",
			"bio",
			"community_order",
			"pinned_spaces",
			"quick_reaction_emojis",
			"sidebar_badge_style",
			"email_digest_frequency",
			"email_digest_day_of_week",
			"email_digest_last_sent_on",
			"participation_level",
			"notification_channel",
			"receive_notifications",
			"active_hours_enabled",
			"active_hours_start",
			"active_hours_end",
			"active_hours_days",
		],
		filters={"user": ["in", [u.name for u in users]]},
	)
	user_profile_map = {u.user: u for u in user_profiles}
	for user in users:
		if frappe.session.user == user.name:
			user.session_user = True
		user_profile = user_profile_map.get(user.name)
		if user_profile:
			user.user_profile = user_profile.name
			# Fall back to User.user_image when the profile has none, so an account that
			# only ever set an avatar through Frappe keeps it. Email digests already
			# resolve avatars this way (see gameplan.email_digest.get_user_avatar_map).
			user.user_image = user_profile.image or user.user_image
			user.image_background_color = user_profile.image_background_color
			user.is_image_background_removed = user_profile.is_image_background_removed
			user.bio = user_profile.bio
			if frappe.session.user == user.name:
				user.community_order = user_profile.community_order
				user.pinned_spaces = user_profile.pinned_spaces
				user.quick_reaction_emojis = user_profile.quick_reaction_emojis
				user.sidebar_badge_style = user_profile.sidebar_badge_style
				user.email_digest_frequency = user_profile.email_digest_frequency
				user.email_digest_day_of_week = user_profile.email_digest_day_of_week
				user.email_digest_last_sent_on = user_profile.email_digest_last_sent_on
				user.participation_level = user_profile.participation_level
				user.notification_channel = user_profile.notification_channel
				user.receive_notifications = user_profile.receive_notifications
				user.active_hours_enabled = user_profile.active_hours_enabled
				user.active_hours_start = user_profile.active_hours_start
				user.active_hours_end = user_profile.active_hours_end
				user.active_hours_days = user_profile.active_hours_days
		user.role = role_map.get(user.name)

		if user.name == frappe.session.user:
			from gameplan.community_bans import banned_communities

			user.banned_communities = banned_communities(user.name)

		# Add discussion and comment counts
		user.discussions_count_3m = discussion_count_map.get(user.name, 0)
		user.comments_count_3m = comment_count_map.get(user.name, 0)

	if names is not None:
		position = {name: index for index, name in enumerate(names)}
		users.sort(key=lambda user: position.get(user.name, len(position)))

	# Guests get the directory for @-mentions/avatars but not other members' emails.
	if gameplan.is_guest():
		for user in users:
			user.pop("email", None)
		from gameplan.guest_payload import for_guest

		users = for_guest(users)

	return users


USER_SEARCH_ORDER = ("relevance", "full_name", "creation", "role")


@frappe.whitelist()
@validate_type
def search_users(
	query: str = "",
	start: int = 0,
	limit: int = 20,
	order_by: str = "relevance",
	descending: bool = False,
	include_guests: bool = True,
	include_disabled: bool = False,
	community: str | None = None,
	exclude_community: str | None = None,
	exclude_space: str | int | None = None,
):
	"""Page through Gameplan users whose name or email matches `query`, in get_user_info's shape."""
	if not has_app_access():
		frappe.throw("Not permitted", frappe.PermissionError)
	if order_by not in USER_SEARCH_ORDER:
		frappe.throw(_("order_by must be one of {0}").format(", ".join(USER_SEARCH_ORDER)))
	for doctype, name in (
		("GP Team", community),
		("GP Team", exclude_community),
		("GP Project", exclude_space),
	):
		if name:
			frappe.has_permission(doctype, "read", doc=str(name), throw=True)

	User = frappe.qb.DocType("User")
	order = Order.desc if descending else Order.asc
	q = user_search_query(
		query, include_guests, include_disabled, community, exclude_community, exclude_space
	)
	if order_by == "role":
		q = order_by_role(q, order).orderby(User.full_name)
	elif order_by == "relevance":
		if query.strip():
			q = q.orderby(match_rank(User.full_name, query.strip()))
		q = q.orderby(User.full_name)
	else:
		q = q.orderby(User[order_by], order=order)
	q = q.orderby(User.name).offset(max(start, 0)).limit(min(max(limit, 1), USER_INFO_BATCH_LIMIT))
	return user_info_rows([row.name for row in q.run(as_dict=1)])


MEMBER_COUNT_CACHE_KEY = "gameplan:member_count"


@frappe.whitelist()
def get_member_count():
	"""How many enabled people hold a Gameplan Member or Admin role."""
	if not has_app_access():
		frappe.throw("Not permitted", frappe.PermissionError)
	count = frappe.cache.get_value(MEMBER_COUNT_CACHE_KEY)
	if count is None:
		count = frappe.qb.from_(user_search_query(include_guests=False)).select(Count("*")).run()[0][0]
		frappe.cache.set_value(MEMBER_COUNT_CACHE_KEY, count, expires_in_sec=300)
	return count


def clear_member_count():
	frappe.cache.delete_value(MEMBER_COUNT_CACHE_KEY)


PEOPLE_ORDER = ("full_name", "modified", *ACTIVITY_COUNT_FIELDS)


@frappe.whitelist()
def get_people(
	query: str = "",
	order_by: str = "modified",
	descending: bool = True,
	start: int = 0,
	limit: int = 50,
):
	"""Page through members and admins for the People page, with their post, reply and reaction counts."""
	if not has_app_access():
		frappe.throw("Not permitted", frappe.PermissionError)
	if order_by not in PEOPLE_ORDER:
		frappe.throw(_("order_by must be one of {0}").format(", ".join(PEOPLE_ORDER)))
	frappe.has_permission("GP User Profile", "read", throw=True)

	Profile = frappe.qb.DocType("GP User Profile")
	return (
		frappe.qb.from_(Profile)
		.select(
			Profile.name,
			Profile.user,
			Profile.bio,
			Profile.modified,
			*(Profile[field] for field in ACTIVITY_COUNT_FIELDS),
		)
		.where(Profile.user.isin(user_search_query(query, include_guests=False)))
		.orderby(Case().when(Profile.user == frappe.session.user, 0).else_(1))
		.orderby(Profile[order_by], order=Order.desc if descending else Order.asc)
		.orderby(Profile.name)
		.offset(max(start, 0))
		.limit(min(max(limit, 1), USER_INFO_BATCH_LIMIT))
		.run(as_dict=True)
	)


def match_rank(field, query):
	return (
		Case()
		.when(field == query, 0)
		.when(field.like(f"{query}%"), 1)
		.when(field.like(f"% {query}%"), 2)
		.else_(3)
	)


def user_search_query(
	query="",
	include_guests=True,
	include_disabled=False,
	community=None,
	exclude_community=None,
	exclude_space=None,
):
	User = frappe.qb.DocType("User")
	HasRole = frappe.qb.DocType("Has Role")
	Member = frappe.qb.DocType("GP Member")
	roles = [role for role in GAMEPLAN_ROLES if include_guests or role != "Gameplan Guest"]

	q = (
		frappe.qb.from_(User)
		.select(User.name)
		.where(
			User.name.isin(
				frappe.qb.from_(HasRole)
				.select(HasRole.parent)
				.where((HasRole.parenttype == "User") & HasRole.role.isin(roles))
			)
		)
	)
	if not include_disabled:
		q = q.where(User.enabled == 1)
	if query := (query or "").strip():
		pattern = f"%{query}%"
		if gameplan.is_guest():
			q = q.where(User.full_name.like(pattern))
		else:
			q = q.where(User.full_name.like(pattern) | User.name.like(pattern))

	def members_of(doctype, name):
		return (
			frappe.qb.from_(Member)
			.select(Member.user)
			.where((Member.parenttype == doctype) & (Member.parent == name))
		)

	if community:
		q = q.where(User.name.isin(members_of("GP Team", community)))
	if exclude_community:
		q = q.where(User.name.notin(members_of("GP Team", exclude_community)))
	if exclude_space:
		q = q.where(User.name.notin(members_of("GP Project", exclude_space)))
	return q


def order_by_role(q, order):
	User = frappe.qb.DocType("User")
	HasRole = frappe.qb.DocType("Has Role")
	rank = Case()
	for index, role in enumerate(reversed(GAMEPLAN_ROLES)):
		rank = rank.when(HasRole.role == role, index)
	return (
		q.join(HasRole)
		.on((HasRole.parent == User.name) & (HasRole.parenttype == "User"))
		.where(HasRole.role.isin(GAMEPLAN_ROLES))
		.groupby(User.name, User.full_name)
		.orderby(Min(rank), order=order)
	)


@frappe.whitelist(allow_guest=True)
def get_public_user_info(handles=None):
	"""Name and avatar for authors of public content, by profile handle.

	What a person who is not signed in gets in place of get_user_info, which stays closed
	to them: no email, no role, no bio, and only for people whose handle a public page
	already shows. See gameplan.public_payload.public_profiles.
	"""
	from gameplan.public_payload import public_profiles

	handles = frappe.parse_json(handles)
	if not isinstance(handles, list):
		frappe.throw(_("handles must be a list"))
	return public_profiles(handles)


@frappe.whitelist(allow_guest=True, methods=["GET"])
def public_file(fid=None):
	"""Serve a private file attached to something the caller can read, by File name.

	frappe refuses every /private/files/ request with nobody signed in, so an image in a
	public post would not load for the people it is public to. This serves exactly one
	File, named by its `name` (never by a path the caller supplies), when it is attached
	to a Gameplan document the caller may read. That read check is the same one the
	document itself passes, so a space leaving the Anonymous tier closes its images in
	the same moment it closes its posts. Public post bodies point here instead of at
	/private/files/ (see gameplan.public_payload).
	"""
	from frappe.utils.response import send_private_file

	from gameplan.public_access import public_access_enabled
	from gameplan.public_payload import public_doctypes

	file = fid and frappe.db.get_value(
		"File",
		{"name": fid, "is_private": 1},
		["file_url", "file_name", "attached_to_doctype", "attached_to_name"],
		as_dict=True,
	)
	if (
		not public_access_enabled()
		or not file
		or not (file.file_url or "").startswith("/private/files/")
		or ".." in file.file_url
		or file.attached_to_doctype not in public_doctypes()
		or not file.attached_to_name
		or not frappe.has_permission(file.attached_to_doctype, "read", doc=file.attached_to_name)
	):
		frappe.throw(_("You don't have permission to access this file"), frappe.PermissionError)

	response = send_private_file(file.file_url.split("/private", 1)[1], filename=file.file_name)
	# Never in a shared cache: the next reader may not be allowed to see it.
	response.headers["Cache-Control"] = "private, max-age=300"
	return response


@frappe.whitelist(methods=["POST"])
@validate_type
def invite_by_email(emails: str, role: str, projects: list = None):
	"""Invite comma-separated `emails` with a Gameplan `role`, optionally to `projects`. Admin only."""
	require_admin()
	if role not in GAMEPLAN_ROLES:
		frappe.throw(_("Invalid role: {0}").format(role), frappe.ValidationError)
	return _invite_by_email(emails, role, projects)


@frappe.whitelist(methods=["POST"])
@validate_type
def change_user_role(user: str, role: str):
	"""Change `user`'s Gameplan role. Admin only. Returns the updated user info."""
	require_admin()
	if role not in GAMEPLAN_ROLES:
		frappe.throw(_("Invalid role: {0}").format(role), frappe.ValidationError)

	user_doc = frappe.get_doc("User", user)
	for _role in list(user_doc.roles):
		if _role.role in GAMEPLAN_ROLES:
			user_doc.remove(_role)
	user_doc.append_roles(role)
	# Admin-gated by require_admin() above; bypass User's own permission checks so an
	# admin can change another user's roles.
	user_doc.save(ignore_permissions=True)

	return get_user_info(user)[0]


@frappe.whitelist(methods=["POST"])
@validate_type
def disable_user(user: str):
	"""Disable the account of `user`. Admin only."""
	require_admin()

	user_doc = frappe.get_doc("User", user)
	user_doc.enabled = 0
	# Admin-gated by require_admin() above; bypass User's own permission checks so an
	# admin can disable another user.
	user_doc.save(ignore_permissions=True)

	return user


def _invite_by_email(emails: str, role: str, projects: list = None) -> dict:
	"""Core invite logic, callable from trusted server code (e.g. onboarding).

	The public invite_by_email wrapper adds the admin gate + role allowlist; this
	helper assumes the caller has already authorized the invite and validated role.

	Two outcomes, split on whether the person already has an account here:

	No account: send the invitation email. Its link is what mints the User.

	An enabled account with no Gameplan role: grant the role now. The email link would
	create nothing and set no password, and an OAuth account (which is how people reach
	this state) would be sent to /update-password for no reason.

	Returns the three buckets so the caller can tell the admin what happened.
	"""
	result = {"granted": [], "invited": [], "skipped": []}
	if not emails:
		return result
	email_string = validate_email_address(emails, throw=False)
	email_list = split_emails(email_string)
	if not email_list:
		return result
	already_in_gameplan = emails_holding_a_gameplan_role(email_list)
	existing_invites = frappe.db.get_all(
		"GP Invitation",
		filters={
			"email": ["in", email_list],
			"role": ["in", ["Gameplan Admin", "Gameplan Member"]],
		},
		pluck="email",
	)

	if role == "Gameplan Guest":
		to_invite = set(email_list) - set(existing_invites)
	else:
		to_invite = set(email_list) - set(already_in_gameplan) - set(existing_invites)

	accounts = existing_accounts(to_invite)
	grantable = {email for email, enabled in accounts.items() if enabled}
	# A disabled account is neither granted nor invited. The role would change nothing
	# while the account cannot sign in, and mailing it an invite link is worse: accept()
	# would hand the role to an account someone deliberately switched off.
	to_invite -= set(accounts) - grantable

	result["skipped"] = sorted(set(email_list) - to_invite)
	if projects:
		projects = frappe.as_json(projects, indent=None)

	for email in sorted(to_invite):
		if email in grantable:
			grant_access(email, role, projects)
			result["granted"].append(email)
		else:
			frappe.get_doc(doctype="GP Invitation", email=email, role=role, projects=projects).insert(
				ignore_permissions=True
			)
			result["invited"].append(email)

	return result


def existing_accounts(email_list) -> dict:
	"""Map each email that already has a User on this site to whether it is enabled.

	An enabled account can sign in today, so its owner needs a role, not an invitation.
	A disabled one needs neither.
	"""
	email_list = list(email_list)
	if not email_list:
		return {}
	rows = frappe.qb.get_query(
		"User",
		filters={"email": ["in", email_list]},
		fields=["email", "enabled"],
	).run(as_dict=True)
	return {row.email: bool(row.enabled) for row in rows}


def emails_holding_a_gameplan_role(email_list: list) -> list:
	"""The subset of `email_list` whose User already holds a Gameplan role.

	A member invite skips these, because the invitation would grant a role they have.
	It must not skip every existing User: signing in through OAuth mints a Website User
	with no role at all, so an account can exist on the site while its owner has no way
	into Gameplan. Those people need the invite; `accept()` adds the role to the account
	they already have.
	"""
	User = frappe.qb.DocType("User")
	HasRole = frappe.qb.DocType("Has Role")
	return (
		frappe.qb.from_(User)
		.join(HasRole)
		.on((HasRole.parent == User.name) & (HasRole.parenttype == "User"))
		.select(User.email)
		.where(User.email.isin(email_list))
		.where(HasRole.role.isin(GAMEPLAN_ROLES))
		.run(pluck=True)
	)


@frappe.whitelist()
def unread_notifications():
	"""Return the current user's unread notification count."""
	return unread_notification_count(frappe.session.user)


@frappe.whitelist(methods=["GET"])
def get_notifications(fields=None, filters=None, order_by=None, start=0, limit=20):
	filters = frappe.parse_json(filters) or {}
	or_filters = {field: filters.pop(field) for field in ("team", "project") if field in filters}
	return frappe.qb.get_query(
		"GP Notification",
		fields=frappe.parse_json(fields),
		filters=filters,
		or_filters=or_filters,
		order_by=order_by,
		offset=cint(start),
		limit=cint(limit),
		ignore_permissions=False,
	).run(as_dict=True)


# Invitation emails open in a browser navigation, so this endpoint must remain GET-reachable.
@frappe.whitelist(allow_guest=True)
@validate_type
def accept_invitation(key: str = None):
	invitation = get_invitation(key)
	if not invitation or invitation.status not in ("Pending", "Accepted"):
		frappe.respond_as_web_page(
			_("This invitation link is no longer valid"),
			_("Ask the person who invited you to send a new invitation."),
			http_status_code=404,
		)
		return

	if invitation.status == "Pending":
		invitation.accept()
		# An account that was here before the invitation signs in the way it always has.
		location = invitation.get_password_link() if invitation.created_account else "/g"
	elif invitation.created_account_awaits_password():
		# The invitee opened the link again before setting a password, so give them a new
		# password link in place of the first one.
		location = invitation.get_password_link()
	else:
		frappe.respond_as_web_page(
			_("This invitation link is no longer valid"),
			_("This invitation has already been accepted. Sign in to continue."),
			http_status_code=410,
			primary_action="/login",
			primary_label=_("Sign in"),
		)
		return

	frappe.db.commit()  # nosemgrep: frappe-manual-commit

	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = location


@frappe.whitelist()
def get_unsplash_photos(keyword=None):
	"""Return Unsplash photos for `keyword`, or a default set."""
	from gameplan.unsplash import get_by_keyword, get_list

	if keyword:
		return get_by_keyword(keyword)

	return frappe.cache().get_value("unsplash_photos", generator=get_list)


@frappe.whitelist(methods=["POST"])
def set_discussion_read_state(discussion: str, unread: bool = False):
	"""Set the current reader's read/unread state without requiring participation rights."""
	doc = frappe.get_doc("GP Discussion", discussion)
	# Read markers belong to the viewer; they do not require content-write permission.
	getattr(doc, "mark_as_unread" if unread else "track_visit")()


@frappe.whitelist(methods=["POST"])
def mark_all_notifications_as_read():
	"""Mark all of the current user's notifications as read."""
	Notification = frappe.qb.DocType("GP Notification")
	(
		frappe.qb.update(Notification)
		.set(Notification.read, 1)
		.where((Notification.to_user == frappe.session.user) & (Notification.read == 0))
	).run()
	notify_notification_changed(frappe.session.user)


@frappe.whitelist(methods=["POST"])
def onboarding(community, space, icon, emails, *, visibility: str = VISIBILITY_GENERAL):
	"""Create the first Community and Space with a visibility tier, then invite `emails`."""
	# Onboarding sets up a brand-new site. After that, communities and invitations go
	# through their own screens and checks.
	if not gameplan.is_new_site():
		frappe.throw(_("This site is already set up"), frappe.PermissionError)

	# Frappe drops unknown RPC arguments, so reject the old key before creating anything.
	if "is_private" in frappe.form_dict:
		frappe.throw(_("is_private is no longer accepted. Set visibility instead."))
	if visibility not in (VISIBILITY_GENERAL, VISIBILITY_MEMBER_ACCESS):
		frappe.throw(_("Onboarding visibility must be General or Member Access."))
	emails = frappe.parse_json(emails)

	# Create the community. The GP Team after_insert hook auto-creates a public
	# "General" space inside it.
	team = frappe.get_doc(doctype="GP Team", title=community).insert()

	# Join the creator — a freshly inserted GP Team does not add its creator as a
	# member, and the scoped-route guard only sees joined communities.
	team.add_member(frappe.session.user)
	team.save()

	# Create the user-named first space in addition to "General".
	project = frappe.get_doc(
		doctype="GP Project", title=space, icon=icon, team=team.name, visibility=visibility
	).insert()

	# The signup creator invites their first teammates. The creator may not be an admin
	# yet, so this skips invite_by_email's admin check. The guard above limits it to a new
	# site, and the role is fixed to Gameplan Member. GP Invitation's own rule that only
	# admins invite admins still applies to these invitations.
	_invite_by_email(", ".join(emails), role="Gameplan Member")
	return {"team": team.name, "space": project.name}


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@validate_type
def search_sqlite(query: str = "", filters: dict | str | None = None, sort_by: str | None = None):
	"""Search and sort content within the current viewer's access."""
	from gameplan.public_search import search_for_viewer, validate_search_filters

	search = search_for_viewer()
	if not (gameplan.is_anonymous() or gameplan.is_guest()):
		filters = validate_search_filters(filters)
	return search.search(query, filters=filters, sort_by=sort_by)


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
def get_search_filter_options():
	"""Get available filter options for advanced search"""
	from gameplan.public_search import search_for_viewer

	return search_for_viewer().get_filter_options()


def can_access_gameplan():
	"""Check if the app should be shown in /apps"""
	from frappe.utils.modules import get_modules_from_all_apps_for_user

	if frappe.session.user == "Administrator":
		return True

	allowed_modules = [x["module_name"] for x in get_modules_from_all_apps_for_user()]
	if "Gameplan" not in allowed_modules:
		return False

	roles = set(frappe.get_roles())
	allowed_roles = {"System Manager", *GAMEPLAN_ROLES}
	if roles.intersection(allowed_roles):
		return True

	return False


LINK_PREVIEW_QUOTA = 30
LINK_PREVIEW_QUOTA_WINDOW = 60


@frappe.whitelist(methods=["POST"])
@validate_type
def get_link_preview(url: str):
	from gameplan.link_previews import get_or_fetch_preview

	if not has_app_access():
		frappe.throw(_("You are not permitted to fetch link previews"), frappe.PermissionError)

	if _link_preview_quota_spent():
		frappe.throw(
			_("Too many link previews requested. Try again in a minute."), frappe.RateLimitExceededError
		)

	return get_or_fetch_preview(url)


def _link_preview_quota_spent() -> bool:
	key = frappe.cache.make_key(f"gameplan:link-preview-count:{frappe.session.user}")
	count = frappe.cache.incrby(key, 1)
	if count == 1:
		frappe.cache.expire(key, LINK_PREVIEW_QUOTA_WINDOW)
	return count > LINK_PREVIEW_QUOTA


CLIENT_ERROR_QUOTA = 20
CLIENT_ERROR_QUOTA_WINDOW = 60 * 60
CLIENT_ERROR_FIELD_LIMIT = 4000


@frappe.whitelist(methods=["POST"])
@validate_type
def log_client_error(message: str, context: dict = None):
	"""Record a browser-side error in the Error Log.

	The UI catches most request failures and shows a message instead of raising, so a
	report like "it did not post the first time" leaves no trace on the server. The
	frontend sends those caught errors here together with the stack and the action that
	failed, which is what makes them diagnosable after the fact.

	The payload is attacker-controlled: it is truncated, stored as plain text, and each
	user gets an hourly quota so a looping client cannot fill the Error Log.
	"""
	if _client_error_quota_spent():
		return

	action = _error_action(context)
	title = f"Gameplan client error: {action}" if action else "Gameplan client error"

	body = [_truncate(message)]
	if context:
		body.append("Context:\n" + _truncate(json.dumps(context, indent=2, default=str)))
	frappe.log_error(title=title, message="\n\n".join(body))


def _error_action(context: dict | None) -> str:
	"""The action label for the log title. Kept to one short line: frappe.log_error treats a
	multi-line title as a traceback and swaps its arguments."""
	action = context.get("action") if isinstance(context, dict) else None
	if not isinstance(action, str):
		return ""
	return " ".join(action.split())[:100]


def _client_error_quota_spent() -> bool:
	"""Whether this user has already used up their hourly client-error budget.

	Read-then-write rather than an atomic counter: two reports racing can slip one past
	the cap, which is fine for a throttle whose only job is to bound the row count.
	"""
	key = f"gameplan:client-error-count:{frappe.session.user}"
	cache = frappe.cache()
	count = cint(cache.get_value(key))
	if count >= CLIENT_ERROR_QUOTA:
		return True
	cache.set_value(key, count + 1, expires_in_sec=CLIENT_ERROR_QUOTA_WINDOW)
	return False


def _truncate(value: str, limit: int = CLIENT_ERROR_FIELD_LIMIT) -> str:
	value = str(value or "")
	return value if len(value) <= limit else value[:limit] + "… (truncated)"
