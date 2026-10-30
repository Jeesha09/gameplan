import frappe
from frappe.query_builder.functions import Cast, Count
from frappe.utils import create_batch

ACTIVITY_COUNT_FIELDS = ("discussions_count", "comments_count", "reactions_received", "reactions_given")


def activity_counts(users):
	Discussion = frappe.qb.DocType("GP Discussion")
	Comment = frappe.qb.DocType("GP Comment")
	Reaction = frappe.qb.DocType("GP Reaction")
	counts = {user: dict.fromkeys(ACTIVITY_COUNT_FIELDS, 0) for user in users}

	def add(field, query):
		for user, count in query.run():
			if user in counts:
				counts[user][field] += count

	live_replies = Comment.owner.isin(users) & Comment.deleted_at.isnull()
	add(
		"discussions_count",
		frappe.qb.from_(Discussion)
		.select(Discussion.owner, Count("*"))
		.where(Discussion.owner.isin(users))
		.groupby(Discussion.owner),
	)
	add(
		"comments_count",
		frappe.qb.from_(Comment).select(Comment.owner, Count("*")).where(live_replies).groupby(Comment.owner),
	)
	add(
		"reactions_given",
		frappe.qb.from_(Reaction)
		.select(Reaction.user, Count("*"))
		.where(Reaction.user.isin(users))
		.groupby(Reaction.user),
	)
	for doctype, Post, condition in (
		("GP Discussion", Discussion, Discussion.owner.isin(users)),
		("GP Comment", Comment, live_replies),
	):
		add(
			"reactions_received",
			frappe.qb.from_(Post)
			.join(Reaction)
			.on(
				(Reaction.reference_doctype == doctype) & (Reaction.reference_name == Cast(Post.name, "char"))
			)
			.select(Post.owner, Count("*"))
			.where(condition)
			.groupby(Post.owner),
		)
	return counts


def refresh_activity_counts(users):
	for user, values in activity_counts(users).items():
		frappe.db.set_value("GP User Profile", {"user": user}, values, update_modified=False)


def queue_activity_counts(users):
	users = sorted({user for user in users if user})
	if users and not frappe.flags.in_import:
		frappe.enqueue(
			"gameplan.activity_counts.refresh_activity_counts",
			users=users,
			enqueue_after_commit=True,
			now=frappe.in_test,
		)


def refresh_owner_counts(doc, method=None):
	queue_activity_counts([doc.owner])


def refresh_reply_counts(doc, method=None):
	if doc.has_value_changed("deleted_at"):
		queue_activity_counts([doc.owner])


def backfill_activity_counts():
	frappe.db.add_index("GP Discussion", ["owner"])
	frappe.db.add_index("GP Reaction", ["user"])
	Profile = frappe.qb.DocType("GP User Profile")
	query = frappe.qb.update(Profile)
	for field in ACTIVITY_COUNT_FIELDS:
		query = query.set(Profile[field], 0)
	query.run()
	users = frappe.get_all("GP User Profile", pluck="user")
	for batch in create_batch(users, 1000):
		for user, values in activity_counts(batch).items():
			if any(values.values()):
				frappe.db.set_value("GP User Profile", {"user": user}, values, update_modified=False)
