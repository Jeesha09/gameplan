import frappe
from frappe.utils import cint

from gameplan.approval_files import publishing_submission
from gameplan.community_bans import can_moderate_community
from gameplan.permissions import get_content_project, require_can_manage_community

# Levels a Community can require before posts skip approval; "" holds nobody (D113).
LEVEL_POLICIES = ("", "Basic", "Member")


@frappe.whitelist(methods=["GET", "POST"])
def get_policy(community: str):
	require_can_manage_community(community)
	return cint(frappe.db.get_value("GP Team", community, "approval_post_count"))


@frappe.whitelist(methods=["POST"])
def set_policy(community: str, count: int):
	require_can_manage_community(community)
	if not 0 <= count <= 100:
		frappe.throw("Choose an approval threshold between 0 and 100")
	# Lock and update the Community row only: loading the document would read every member.
	if not frappe.db.get_value("GP Team", community, "name", for_update=True):
		raise frappe.DoesNotExistError(f"GP Team {community} not found")
	frappe.db.set_value("GP Team", community, "approval_post_count", count)
	return count


@frappe.whitelist(methods=["GET", "POST"])
def get_level_policy(community: str):
	"""Return the level below which a Community holds posts for approval, and whether levels are on."""
	from gameplan.trust_levels import is_enabled

	require_can_manage_community(community)
	return {
		"levels_enabled": is_enabled(),
		"min_level": frappe.db.get_value("GP Team", community, "approval_min_level") or "",
	}


@frappe.whitelist(methods=["POST"])
def set_level_policy(community: str, min_level: str):
	"""Hold posts from members below Basic or Member for approval, or none with "". Community admins."""
	require_can_manage_community(community)
	if min_level not in LEVEL_POLICIES:
		frappe.throw("Choose no approval, Basic or Member")
	if not frappe.db.get_value("GP Team", community, "name", for_update=True):
		raise frappe.DoesNotExistError(f"GP Team {community} not found")
	frappe.db.set_value("GP Team", community, "approval_min_level", min_level)
	return get_level_policy(community)


def needs_approval(doc):
	project = get_content_project(doc)
	if not project:
		return False
	community = frappe.db.get_value("GP Project", project, "team")
	from gameplan.watched_word_actions import requires_approval

	if requires_approval(doc):
		return True
	from gameplan.trust_levels import LEVELS, is_enabled, level_of

	if is_enabled():
		# While levels are on, they replace the first-N rule (D113, D124).
		minimum = frappe.db.get_value("GP Team", community, "approval_min_level")
		if not minimum or can_moderate_community(community):
			return False
		level = level_of()
		return level is not None and level < LEVELS.index(minimum)
	threshold = cint(frappe.db.get_value("GP Team", community, "approval_post_count"))
	if not threshold or can_moderate_community(community):
		return False
	return counter(community).accepted < threshold


def guard_publication(doc, method=None):
	if not supports_approval(doc):
		return
	publication = publishing_submission.get()
	if publication and publication[0] is doc:
		return
	if needs_approval(doc):
		frappe.throw("Submit this content through the approval queue", frappe.PermissionError)


def record_accepted(doc, method=None):
	if not supports_approval(doc):
		return
	community = frappe.db.get_value("GP Project", get_content_project(doc), "team")
	if not community:
		return
	# Existing counters keep earning contributions even while the policy is disabled.
	if not frappe.db.exists("GP Approval Counter", {"community": community, "user": frappe.session.user}):
		return
	row = counter(community)
	frappe.db.set_value("GP Approval Counter", row.name, "accepted", row.accepted + 1)


def supports_approval(doc):
	return doc.doctype == "GP Discussion" or (
		doc.doctype == "GP Comment" and doc.reference_doctype == "GP Discussion"
	)


def counter(community):
	user = frappe.session.user
	frappe.db.get_value("User", user, "name", for_update=True)
	row = frappe.db.get_value(
		"GP Approval Counter",
		{"community": community, "user": user},
		["name", "accepted"],
		as_dict=True,
		for_update=True,
	)
	if row:
		return row
	Project, Discussion, Comment = [
		frappe.qb.DocType(dt) for dt in ("GP Project", "GP Discussion", "GP Comment")
	]
	projects = frappe.qb.from_(Project).select(Project.name).where(Project.team == community)
	discussions = (
		frappe.qb.from_(Discussion)
		.where(Discussion.project.isin(projects))
		.where(Discussion.hidden_at.isnull() & Discussion.spam_removed_at.isnull())
	)
	# Thresholds cannot exceed 100; older contributions need no full-history count.
	accepted = len(
		discussions.select(Discussion.name).where(Discussion.owner == user).limit(100).for_update().run()
	)
	if accepted < 100:
		accepted += len(
			frappe.qb.from_(Comment)
			.select(Comment.name)
			.where(
				(Comment.reference_doctype == "GP Discussion")
				& Comment.reference_name.isin(discussions.select(Discussion.name))
			)
			.where(
				(Comment.owner == user)
				& Comment.deleted_at.isnull()
				& Comment.hidden_at.isnull()
				& Comment.spam_removed_at.isnull()
			)
			.limit(100 - accepted)
			.for_update()
			.run()
		)
	row = frappe.get_doc(doctype="GP Approval Counter", community=community, user=user, accepted=accepted)
	row.insert(ignore_permissions=True)
	return frappe._dict(name=row.name, accepted=accepted)


def delete_counters(doc, method=None):
	field = "community" if doc.doctype == "GP Team" else "user"
	frappe.db.delete("GP Approval Counter", {field: doc.name})
