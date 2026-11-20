import frappe
from frappe.query_builder.functions import Count
from pypika.terms import Criterion

from gameplan.approvals import community_submissions
from gameplan.community_bans import can_moderate_community
from gameplan.moderation_history import history_sources
from gameplan.permissions import moderatable_project_names
from gameplan.reporting import community_reviews

SEEN_TABS = ("removed", "bans", "history")
REMOVAL_LOGS = ["Hide", "Delete Spam", "Auto Hide"]
BAN_LOGS = ["Ban", "Ban Changed", "Unban", "Restriction Expired"]


def seen_key(community, tab):
	return f"gameplan_moderation_seen:{community}:{tab}"


def require_moderator(community):
	if not can_moderate_community(community):
		frappe.throw("Only community moderators can perform this action", frappe.PermissionError)


def changed_since_seen(criterion, community, tab):
	Log = frappe.qb.DocType("GP Moderation Log")
	query = frappe.qb.from_(Log).select(Log.name).where(criterion & (Log.owner != frappe.session.user))
	seen = frappe.defaults.get_user_default(seen_key(community, tab))
	if seen:
		query = query.where(Log.creation > seen)
	return bool(query.limit(1).run())


def community_activity(community):
	Submission = frappe.qb.DocType("GP Submission")
	Review = frappe.qb.DocType("GP Review")
	Log = frappe.qb.DocType("GP Moderation Log")
	approvals = (
		community_submissions(moderatable_project_names(community))
		.select(Count("*"))
		.where(Submission.status == "Pending")
		.run()[0][0]
	)
	reports = (
		frappe.qb.from_(Review)
		.select(Count("*"))
		.where(community_reviews(community) & (Review.status == "Pending"))
		.run()[0][0]
	)
	sources = history_sources(community)
	posts = sources["discussion"][0] | sources["reply"][0]
	return {
		"approvals": approvals,
		"reports": reports,
		"removed": changed_since_seen(posts & Log.action.isin(REMOVAL_LOGS), community, "removed"),
		"bans": changed_since_seen(sources["user"][0] & Log.action.isin(BAN_LOGS), community, "bans"),
		"history": changed_since_seen(
			Criterion.any(source[0] for source in sources.values()), community, "history"
		),
	}


def needs_attention(activity):
	return any(activity.values())


@frappe.whitelist(methods=["GET", "POST"])
def activity(community: str = ""):
	"""Count pending queues and flag tabs others changed since you opened them, per Community or overall."""
	if community:
		require_moderator(community)
		return community_activity(community)
	communities = (name for name in frappe.get_all("GP Team", pluck="name") if can_moderate_community(name))
	return {"attention": any(needs_attention(community_activity(name)) for name in communities)}


@frappe.whitelist(methods=["POST"])
def mark_seen(community: str, tab: str):
	"""Record that you opened a moderation tab (removed, bans or history), clearing its activity dot."""
	require_moderator(community)
	if tab not in SEEN_TABS:
		frappe.throw("Unsupported moderation tab")
	frappe.defaults.set_user_default(seen_key(community, tab), frappe.utils.now())
