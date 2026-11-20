# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and Contributors
# MIT License. See license.txt

"""Discourse-style posting safeguards for public-only Gameplan Guests, New and Basic members.

Public-only Guests and New members outside the Communities they help run (D116) get first-day
quotas, a cap on replies in someone else's discussion, and per-post limits. Public-only Guests
also get a 24-hour own-post edit window. Basic members get only higher first-day quotas. Global
admins set every number on the trust levels page (D134). Each limit is checked on its own, so
these stack with the site posting rate and content caps and the strictest wins (D135).
Validation hooks cover every save route.
"""

from datetime import timedelta

import frappe
from bs4 import BeautifulSoup
from frappe.utils import cint, get_datetime, now_datetime

import gameplan

FIRST_DAY = timedelta(hours=24)
EDIT_WINDOW = timedelta(hours=24)
NEW, BASIC = "New", "Basic"

# The doctypes a Gameplan Guest may create (permissions.GUEST_CREATABLE_DOCTYPES), and the
# fields whose change is an edit of the post. Reactions and votes are not edits.
POST_FIELDS = {
	"GP Discussion": ("title", "content"),
	"GP Comment": ("content",),
	"GP Poll": ("title", "options"),
}
POST_COUNTER_FIELDS = {
	"GP Discussion": "first_day_discussions",
	"GP Comment": "first_day_replies",
	"GP Poll": "first_day_replies",
}
# count_post_contents key, setting, singular, plural.
PER_POST_LIMITS = (
	("links", "new_max_links", "link", "links"),
	("media", "new_max_media", "image or video", "images or videos"),
	("files", "new_max_attachments", "file", "files"),
	("mentions", "new_max_mentions", "mention", "mentions"),
)
EVERYONE_MENTION = "_everyone_"


class NewUserLimitError(frappe.ValidationError):
	pass


def check_new_user_limits(doc, method=None):
	"""`validate` for every doctype a Gameplan Guest may create."""
	user = frappe.session.user
	posted = first_day_post_count(user, doc.doctype) if doc.is_new() and is_counted(user) else None
	tier = limited_as(user, doc)
	if not tier:
		return
	limits = settings()
	if doc.is_new():
		check_first_day(posted, doc, tier, limits)
	if tier != NEW:
		return
	if doc.is_new():
		check_replies_in_discussion(user, doc, limits)
	elif (
		gameplan.is_guest(user)
		and (doc.owner or frappe.db.get_value(doc.doctype, doc.name, "owner")) == user
		and post_changed(doc)
	):
		check_edit_window(doc)
	if doc.is_new() or post_changed(doc):
		check_post(doc.get("content") if doc.meta.has_field("content") else None, limits)


def settings():
	from gameplan.trust_levels import config

	return config()


def level(user):
	from gameplan.trust_levels import level_of

	return level_of(user)


def is_counted(user) -> bool:
	"""Whose first-day posts are counted: the counter carries over from New to Basic."""
	from gameplan.trust_levels import BASIC as BASIC_LEVEL

	if gameplan.is_guest(user):
		return True
	found = level(user)
	return found is not None and found <= BASIC_LEVEL


def limited_as(user, doc):
	"""Which limits `user` gets on `doc`: New, Basic, or None."""
	from gameplan.trust_levels import BASIC as BASIC_LEVEL
	from gameplan.trust_levels import NEW as NEW_LEVEL

	# A public-only Guest gets the New limits whatever their level.
	if is_public_only_guest(user, doc):
		return NEW
	found = level(user)
	if found in (NEW_LEVEL, BASIC_LEVEL) and outside_staff(user, doc):
		return NEW if found == NEW_LEVEL else BASIC
	return None


def outside_staff(user, doc) -> bool:
	"""Whether `doc` is in a Community that `user` does not help run."""
	from gameplan.community_bans import can_moderate_community
	from gameplan.permissions import get_content_project

	project = get_content_project(doc)
	community = project and frappe.db.get_value("GP Project", project, "team")
	return bool(community) and not can_moderate_community(community, user)


def is_public_only_guest(user, doc) -> bool:
	"""Whether `user` is a Guest who reaches `doc`'s space only because it is public."""
	from gameplan.permissions import (
		get_content_project,
		get_project_info,
		has_guest_access,
		is_publicly_readable_space,
	)

	if not gameplan.is_guest(user):
		return False
	project = get_content_project(doc)
	if not project or has_guest_access(user, project):
		return False
	project_info = get_project_info(project)
	return bool(project_info and is_publicly_readable_space(project_info))


def first_day_post_count(user, doctype):
	"""Lock the account's durable counter until the posting transaction ends."""
	created = frappe.db.get_value("User", user, "creation")
	if not created or now_datetime() - get_datetime(created) >= FIRST_DAY:
		return None
	posted = frappe.db.get_value(
		"GP User Profile", {"user": user}, POST_COUNTER_FIELDS[doctype], for_update=True
	)
	if posted is None:
		refuse("Your Gameplan profile is unavailable. Contact an administrator before posting.")
	return posted


def record_first_day_post(doc, method=None):
	"""Count successful inserts, including posts later deleted or removed by a cascade."""
	user = doc.owner
	if not is_counted(user) or first_day_post_count(user, doc.doctype) is None:
		return
	Profile = frappe.qb.DocType("GP User Profile")
	field = getattr(Profile, POST_COUNTER_FIELDS[doc.doctype])
	frappe.qb.update(Profile).set(field, field + 1).where(Profile.user == user).run()


def check_first_day(posted, doc, tier, limits):
	if posted is None:
		return
	what = "discussions" if doc.doctype == "GP Discussion" else "replies"
	limit = limits[f"{tier.lower()}_first_day_{what}"]
	if cint(posted) < limit:
		return
	who = "New accounts" if tier == NEW else "Accounts at Basic"
	noun = {"discussions": "discussion", "replies": "reply"}[what] if limit == 1 else what
	allowed = f"cannot post {what}" if not limit else f"can post {limit} {noun}"
	refuse(f"{who} {allowed} on their first day. You can post more once your account is a day old.")


def check_replies_in_discussion(user, doc, limits):
	"""Discourse's newuser_max_replies_per_topic: wait for someone else to reply (D134)."""
	if doc.doctype != "GP Comment" or doc.reference_doctype != "GP Discussion":
		return
	if frappe.db.get_value("GP Discussion", doc.reference_name, "owner") == user:
		return
	limit = limits.new_replies_per_discussion
	if limit and replies_since_someone_else(user, doc.reference_name, limit) < limit:
		return
	if not limit:
		refuse("New accounts cannot reply in other people's discussions.")
	refuse(
		f"New accounts can post {limit} {'reply' if limit == 1 else 'replies'} in a row in a"
		" discussion. You can reply again after someone else does."
	)


def replies_since_someone_else(user, discussion, limit):
	"""The member's replies after the last reply by anyone else, counted up to `limit`."""
	Comment = frappe.qb.DocType("GP Comment")
	in_discussion = (
		(Comment.reference_doctype == "GP Discussion")
		& (Comment.reference_name == discussion)
		& Comment.deleted_at.isnull()
	)
	last_other = (
		frappe.qb.from_(Comment)
		.select(Comment.creation)
		.where(in_discussion & (Comment.owner != user))
		.orderby(Comment.creation, order=frappe.qb.desc)
		.limit(1)
		.run(pluck=True)
	)
	query = frappe.qb.from_(Comment).select(Comment.name).where(in_discussion & (Comment.owner == user))
	if last_other:
		query = query.where(Comment.creation > last_other[0])
	return len(query.limit(limit).run())


def check_edit_window(doc):
	if now_datetime() - get_datetime(doc.creation) > EDIT_WINDOW:
		refuse("Posts from new accounts can be edited for 24 hours after posting.")


def check_post(html, limits):
	"""Refuse a post body that goes over any New per-post limit."""
	counts = count_post_contents(html)
	if counts.everyone:
		refuse("New accounts cannot mention everyone.")
	for key, field, singular, plural in PER_POST_LIMITS:
		limit = limits[field]
		if counts[key] <= limit:
			continue
		if not limit:
			refuse(f"New accounts cannot add {plural} to a post.")
		refuse(f"New accounts can add {limit} {singular if limit == 1 else plural} per post.")


def count_post_contents(html) -> frappe._dict:
	"""How many images, links, files, media and mentions a post body carries.

	The New limits follow Discourse: `media` is images, videos and audio, and `files` is other
	uploaded files. The site content caps keep `images` and `attachments`, where an attachment is
	an uploaded file, a video or audio. A custom emoji is neither. An embedded iframe counts as a
	link, as a Discourse onebox does.
	"""
	from gameplan.utils import file_reference_from_url

	soup = BeautifulSoup(html or "", "html.parser")
	links = soup.find_all("a", href=True)
	mentions = soup.find_all("span", attrs={"data-type": "mention"})
	files = sum(bool(file_reference_from_url(link["href"])) for link in links)
	images = len(soup.select("img:not([data-emoji])"))
	players = len(soup.find_all(["video", "audio"]))
	return frappe._dict(
		images=images,
		links=len(links) - files + len(soup.find_all("iframe")),
		attachments=files + players,
		files=files,
		media=images + players,
		mentions=sum(mention.get("data-id") != EVERYONE_MENTION for mention in mentions),
		everyone=any(mention.get("data-id") == EVERYONE_MENTION for mention in mentions),
	)


def post_changed(doc) -> bool:
	if any(doc.has_value_changed(field) for field in POST_FIELDS[doc.doctype] if field != "options"):
		return True
	before = doc.get_doc_before_save()
	return doc.doctype == "GP Poll" and (
		not before or [row.title for row in doc.options] != [row.title for row in before.options]
	)


def refuse(message):
	frappe.throw(message, NewUserLimitError, title="New account limit")
