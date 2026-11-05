"""Remove every post by one author in a Community as spam, and undo exactly that cleanup."""

import frappe

from gameplan.community_bans import can_moderate_community
from gameplan.permissions import is_global_admin
from gameplan.reporting import checked_note

BATCH = 100


@frappe.whitelist(methods=["POST"])
def start(user: str, reason: str, community: str = ""):
	"""Queue removal of a user's posts in one Community, or in every Community for global admins."""
	actor = frappe.session.user
	if not (can_moderate_community(community) if community else is_global_admin(actor)):
		frappe.throw("You cannot clean up posts here", frappe.PermissionError)
	reason = checked_note(reason, required=True)
	if not frappe.db.exists("User", user) or user in ("Guest", "Administrator", actor):
		frappe.throw("Choose another user")
	communities = [community] if community else authored_communities(user)
	if is_global_admin(user) or any(can_moderate_community(c, user) for c in communities):
		frappe.throw("Remove the applicable staff role before cleaning up this user's posts")
	for name in communities:
		frappe.enqueue(
			run,
			queue="long",
			enqueue_after_commit=True,
			cleanup=frappe.generate_hash(length=16),
			community=name,
			user=user,
			reason=reason,
			actor=actor,
		)
	return len(communities)


@frappe.whitelist(methods=["POST"])
def undo(cleanup: str):
	"""Queue restoring the posts one cleanup removed that are still removed by it."""
	community = frappe.db.get_value(
		"GP Moderation Log", {"action": "Author Cleanup", "cleanup": cleanup}, "community"
	)
	if not community or not can_moderate_community(community):
		frappe.throw("You cannot undo this cleanup", frappe.PermissionError)
	if undone(cleanup):
		frappe.throw("This cleanup was already undone")
	frappe.enqueue(
		run_undo, queue="long", enqueue_after_commit=True, cleanup=cleanup, actor=frappe.session.user
	)


def run(cleanup, community, user, reason, actor):
	frappe.set_user(actor)
	if not can_moderate_community(community):
		return
	removed = skipped = 0
	for doctype, name in authored_posts(user, community):
		try:
			frappe.get_doc(doctype, name)._remove_content("Delete Spam", reason, cleanup=cleanup)
			removed += 1
		except frappe.PermissionError:
			skipped += 1
		commit_every_batch(removed + skipped)
	rejected = reject_pending(user, community, reason)
	note = f"Removed {removed} posts. Rejected {rejected} pending submissions."
	if skipped:
		note += f" Skipped {skipped} posts you cannot moderate."
	record("Author Cleanup", cleanup, community, user, note, reason)


def run_undo(cleanup, actor):
	frappe.set_user(actor)
	log = frappe.get_doc("GP Moderation Log", {"action": "Author Cleanup", "cleanup": cleanup})
	if undone(cleanup) or not can_moderate_community(log.community):
		return
	restored = skipped = 0
	for removal in frappe.get_all(
		"GP Moderation Log",
		filters={"cleanup": cleanup, "action": "Delete Spam"},
		fields=["name", "discussion", "comment"],
	):
		doctype, name = (
			("GP Comment", removal.comment) if removal.comment else ("GP Discussion", removal.discussion)
		)
		doc = frappe.get_doc(doctype, name) if frappe.db.exists(doctype, name) else None
		# Skip posts restored, re-removed or hidden since: a newer decision wins.
		if doc and doc.spam_removed_at and doc._original_content().name == removal.name:
			doc.restore()
			restored += 1
		else:
			skipped += 1
		commit_every_batch(restored + skipped)
	note = f"Restored {restored} posts."
	if skipped:
		note += f" Skipped {skipped} changed since the cleanup."
	record("Undo Cleanup", cleanup, log.community, log.user, note)


def undone(cleanup):
	return frappe.db.exists("GP Moderation Log", {"action": "Undo Cleanup", "cleanup": cleanup})


def record(action, cleanup, community, user, note, reason=None):
	frappe.get_doc(
		doctype="GP Moderation Log",
		action=action,
		cleanup=cleanup,
		community=community,
		user=user,
		reason=reason,
		title=note,
	).insert(ignore_permissions=True)


def commit_every_batch(count):
	if count % BATCH == 0:
		# Keep a long cleanup out of one giant transaction; each item is already complete.
		frappe.db.commit()


def community_projects(community):
	return (
		frappe.qb.from_(frappe.qb.DocType("GP Project"))
		.select("name")
		.where(frappe.qb.DocType("GP Project").team == community)
	)


def authored_posts(user, community):
	Discussion, Comment = frappe.qb.DocType("GP Discussion"), frappe.qb.DocType("GP Comment")
	discussions = (
		frappe.qb.from_(Discussion)
		.select(Discussion.name)
		.where(Discussion.project.isin(community_projects(community)))
	)
	replies = (
		frappe.qb.from_(Comment)
		.select(Comment.name)
		.where(
			(Comment.owner == user)
			& (Comment.reference_doctype == "GP Discussion")
			& Comment.reference_name.isin(discussions)
			& Comment.hidden_at.isnull()
			& Comment.spam_removed_at.isnull()
			& Comment.deleted_at.isnull()
		)
		.run(pluck=True)
	)
	own = (
		frappe.qb.from_(Discussion)
		.select(Discussion.name)
		.where(
			(Discussion.owner == user)
			& Discussion.project.isin(community_projects(community))
			& Discussion.hidden_at.isnull()
			& Discussion.spam_removed_at.isnull()
		)
		.run(pluck=True)
	)
	return [("GP Comment", name) for name in replies] + [("GP Discussion", name) for name in own]


def reject_pending(user, community, reason):
	from gameplan.approval_access import submission_project
	from gameplan.approvals import decide

	rejected = 0
	for name in frappe.get_all("GP Submission", filters={"owner": user, "status": "Pending"}, pluck="name"):
		doc = frappe.get_doc("GP Submission", name)
		project = submission_project(doc)
		if project and frappe.db.get_value("GP Project", project, "team") == community:
			decide(doc.name, "Reject", str(doc.modified), note=reason)
			rejected += 1
	return rejected


def authored_communities(user):
	Discussion, Comment, Project = (
		frappe.qb.DocType("GP Discussion"),
		frappe.qb.DocType("GP Comment"),
		frappe.qb.DocType("GP Project"),
	)
	from_discussions = (
		frappe.qb.from_(Discussion)
		.join(Project)
		.on(Project.name == Discussion.project)
		.select(Project.team)
		.where(Discussion.owner == user)
		.distinct()
		.run(pluck=True)
	)
	from_replies = (
		frappe.qb.from_(Comment)
		.join(Discussion)
		.on((Comment.reference_doctype == "GP Discussion") & (Comment.reference_name == Discussion.name))
		.join(Project)
		.on(Project.name == Discussion.project)
		.select(Project.team)
		.where(Comment.owner == user)
		.distinct()
		.run(pluck=True)
	)
	from gameplan.approval_access import submission_project

	pending = {
		frappe.db.get_value("GP Project", submission_project(doc), "team")
		for doc in frappe.get_all(
			"GP Submission",
			filters={"owner": user, "status": "Pending"},
			fields=["name", "project", "discussion", "edit_doctype", "edit_name"],
		)
	}
	return sorted((set(from_discussions) | set(from_replies) | pending) - {None})
