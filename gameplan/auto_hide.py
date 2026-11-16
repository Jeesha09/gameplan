"""Weighted auto-hide (D78 to D102).

Each Spam or Abuse report adds its reporter's weight to the post's review. When the total reaches the
Community's threshold, the System hides the post until a moderator decides. Weights come from trust
levels, so auto-hide works only while levels are on.
"""

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

import gameplan
from gameplan.community_bans import can_moderate_community
from gameplan.mixins.moderation import content_is_removed, parent_discussion, remove_content
from gameplan.permissions import can_manage_community, get_content_project, require_can_manage_community

COUNTED_REASONS = ("Spam", "Abuse/inappropriate")
# Report weight by trust level: New, Basic, Member, Regular, Leader (D116).
WEIGHTS = (1, 1, 2, 3, 3)
STAFF_WEIGHT = 3
DEFAULT_THRESHOLD = 6
THRESHOLD_RANGE = (3, 30)


def settings(community):
	row = (
		frappe.db.get_value("GP Team", community, ["auto_hide_enabled", "auto_hide_threshold"], as_dict=True)
		or frappe._dict()
	)
	return frappe._dict(
		enabled=cint(row.auto_hide_enabled),
		threshold=cint(row.auto_hide_threshold) or DEFAULT_THRESHOLD,
	)


def is_active(community):
	"""Auto-hide runs while the Community's switch and trust levels are both on (D79, D94)."""
	from gameplan.trust_levels import is_enabled

	return bool(community) and is_enabled() and bool(settings(community).enabled)


@frappe.whitelist(methods=["GET", "POST"])
def get_settings(community: str):
	"""Return a Community's auto-hide switch and threshold, and whether trust levels are on."""
	from gameplan.trust_levels import is_enabled

	if not can_moderate_community(community):
		frappe.throw(_("Only Community moderators can perform this action"), frappe.PermissionError)
	return {
		**settings(community),
		"levels_enabled": is_enabled(),
		"can_edit": can_manage_community(frappe.session.user, community),
		"weights": {"levels": WEIGHTS, "staff": STAFF_WEIGHT},
		"range": THRESHOLD_RANGE,
	}


@frappe.whitelist(methods=["POST"])
def save_settings(community: str, enabled: int, threshold: int):
	"""Turn weighted auto-hide on or off for a Community and set its threshold. Community admins."""
	from gameplan.trust_levels import is_enabled

	require_can_manage_community(community)
	enabled, threshold = cint(enabled), cint(threshold)
	if not THRESHOLD_RANGE[0] <= threshold <= THRESHOLD_RANGE[1]:
		frappe.throw(_("Choose a threshold from {0} to {1}").format(*THRESHOLD_RANGE))
	# While levels are off, a switch already on stays on and paused (D94), but cannot be turned on.
	if enabled and not is_enabled() and not settings(community).enabled:
		frappe.throw(_("Auto-hide needs trust levels. A global admin turns them on."))
	if not frappe.db.get_value("GP Team", community, "name", for_update=True):
		raise frappe.DoesNotExistError(f"GP Team {community} not found")
	frappe.db.set_value(
		"GP Team", community, {"auto_hide_enabled": enabled, "auto_hide_threshold": threshold}
	)
	return get_settings(community)


def report_weight(community, reason):
	"""The weight of the session user's new report. It is fixed when the report is filed (D80, D90)."""
	from gameplan.trust_levels import level_of

	if reason not in COUNTED_REASONS or not is_active(community):
		return 0
	user = frappe.session.user
	if gameplan.is_admin(user) or can_moderate_community(community):
		return STAFF_WEIGHT
	# A level not worked out yet is worked out now. A locked level counts as itself (D99).
	level = level_of(user)
	return WEIGHTS[level] if level is not None else 0


def check(review, doc, community):
	"""Hide `doc` as the System once its review's weight reaches the threshold (D80 to D83, D91)."""
	if not is_active(community):
		return
	row = frappe.db.get_value("GP Review", review, ["status", "report_weight", "auto_hidden"], as_dict=True)
	if row.status != "Pending" or row.auto_hidden or cint(row.report_weight) < settings(community).threshold:
		return
	if content_is_removed(doc) or doc.get("deleted_at") or is_exempt(doc.owner, community) or cleared(doc):
		return
	if not files_allow_hiding(doc):
		return
	label = post_label(doc)
	remove_content(doc, "Auto Hide", "Hidden automatically after member reports")
	frappe.db.set_value("GP Review", review, "auto_hidden", 1, update_modified=False)
	notify_author(doc, label, hidden=True)


def is_exempt(author, community):
	"""Posts by Community staff and global admins are never auto-hidden (D83)."""
	return gameplan.is_admin(author) or can_moderate_community(community, author)


def cleared(doc):
	"""A moderator restored this post or dismissed its reports before (D91)."""
	field = "comment" if doc.doctype == "GP Comment" else "discussion"
	if frappe.db.exists("GP Moderation Log", {field: str(doc.name), "action": "Restore"}):
		return True
	return bool(
		frappe.db.exists(
			"GP Review",
			{
				"reference_doctype": doc.doctype,
				"reference_name": str(doc.name),
				"status": "Resolved",
				"decision": "Dismiss",
			},
		)
	)


def files_allow_hiding(doc):
	"""A post with public files waits for a moderator, who must make the files private first."""
	muted = frappe.flags.mute_messages
	frappe.flags.mute_messages = True
	try:
		doc._check_moderated_files()
		return True
	except frappe.ValidationError:
		return False
	finally:
		frappe.flags.mute_messages = muted


def resolve(doc, decision, note):
	"""Apply a moderator's decision to an auto-hidden post (D85)."""
	from gameplan.mixins.moderation import restore_content

	if decision == "Dismiss":
		restore_content(doc, note)
	else:
		remove_content(doc, "Delete Spam" if decision == "Delete Spam" else "Hide", note)


def after_restore(doc, note):
	"""Restoring an auto-hidden post closes its review as Dismiss and tells the author (D95, D96)."""
	Review = frappe.qb.DocType("GP Review")
	(
		frappe.qb.update(Review)
		.set(Review.status, "Resolved")
		.set(Review.decision, "Dismiss")
		.set(Review.decision_note, note or "Restored")
		.set(Review.decided_by, frappe.session.user)
		.set(Review.decided_at, now_datetime())
		.where(
			(Review.reference_doctype == doc.doctype)
			& (Review.reference_name == str(doc.name))
			& (Review.status == "Pending")
		)
		.run()
	)
	notify_author(doc, post_label(doc), hidden=False)


def recheck_moved(doc, method=None):
	"""A moved discussion keeps its reports' weight and is checked against its new Community (D97)."""
	before = doc.get_doc_before_save()
	if not before or not doc.has_value_changed("project"):
		return
	community = frappe.db.get_value("GP Project", doc.project, "team")
	if community == frappe.db.get_value("GP Project", before.project, "team") or not is_active(community):
		return
	Review, Comment = frappe.qb.DocType("GP Review"), frappe.qb.DocType("GP Comment")
	replies = (
		frappe.qb.from_(Comment)
		.select(Comment.name)
		.where((Comment.reference_doctype == "GP Discussion") & (Comment.reference_name == str(doc.name)))
	)
	pending = (
		frappe.qb.from_(Review)
		.select(Review.name, Review.reference_doctype, Review.reference_name)
		.where((Review.status == "Pending") & (Review.auto_hidden == 0) & (Review.report_weight > 0))
		.where(
			((Review.reference_doctype == "GP Discussion") & (Review.reference_name == str(doc.name)))
			| ((Review.reference_doctype == "GP Comment") & Review.reference_name.isin(replies))
		)
		.run(as_dict=True)
	)
	for row in pending:
		target = (
			doc
			if row.reference_doctype == "GP Discussion"
			else frappe.get_doc("GP Comment", row.reference_name)
		)
		check(row.name, target, community)


def post_label(doc):
	"""How the author's notification names the post, read before hiding replaces its title."""
	discussion = parent_discussion(doc)
	title = (
		doc.title
		if doc.doctype == "GP Discussion"
		else frappe.db.get_value("GP Discussion", discussion, "title")
	)
	if doc.doctype == "GP Discussion":
		return _("discussion “{0}”").format(title)
	return _("reply in “{0}”").format(title)


def notify_author(doc, label, hidden):
	"""Tell the author about an auto-hide or its reversal, without naming the reporters (D88, D96)."""
	from gameplan.realtime import notify_notification_counts_refresh

	message = (
		_("Your {0} was hidden after member reports. A moderator will review it.")
		if hidden
		else _("A moderator reviewed your {0} and made it visible again.")
	).format(label)
	links = {}
	if not hidden:
		project = get_content_project(doc)
		links = {
			"discussion": parent_discussion(doc),
			"comment": doc.name if doc.doctype == "GP Comment" else None,
			"project": project,
			"team": frappe.db.get_value("GP Project", project, "team"),
		}
	frappe.get_doc(
		doctype="GP Notification",
		type="Moderation",
		to_user=doc.owner,
		from_user=doc.owner,
		message=message,
		**links,
	).insert(ignore_permissions=True)
	notify_notification_counts_refresh([doc.owner])
