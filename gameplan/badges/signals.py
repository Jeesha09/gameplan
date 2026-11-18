"""What badges count, read from Gameplan's own tables.

A like is a reaction from someone other than the post's author, counted once per person and
post. Reactions are Gameplan's likes until likes replace them; only `liked_posts`,
`likes_given` and `first_like` read GP Reaction, so only they change then.

A post counts while it is published: a discussion, or a reply on one, not deleted, hidden or
removed as spam.
"""

import frappe
from frappe.query_builder import functions as fn

POSTS = ("GP Discussion", "GP Comment")


def visible(Post, doctype):
	condition = Post.hidden_at.isnull() & Post.spam_removed_at.isnull()
	if doctype == "GP Comment":
		condition &= Post.deleted_at.isnull() & (Post.reference_doctype == "GP Discussion")
	return condition


def reaction_join(Reaction, Post, doctype):
	# Reaction names are text: a number here would stop the index being used.
	return (Reaction.reference_doctype == doctype) & (
		Reaction.reference_name == fn.Cast_(Post.name, "varchar")
	)


def liked_posts(user, min_likes, doctypes=POSTS):
	"""The member's posts with at least `min_likes` likes: (doctype, name, likes) rows."""
	Reaction = frappe.qb.DocType("GP Reaction")
	rows = []
	for doctype in doctypes:
		Post = frappe.qb.DocType(doctype)
		likes = fn.Count(Reaction.user).distinct()
		rows += [
			(doctype, str(name), count)
			for name, count in frappe.qb.from_(Post)
			.join(Reaction)
			.on(reaction_join(Reaction, Post, doctype))
			.select(Post.name, likes)
			.where((Post.owner == user) & (Reaction.user != user) & visible(Post, doctype))
			.groupby(Post.name)
			.having(likes >= min_likes)
			.run()
		]
	return rows


def likes_given(user, limit):
	"""Posts by others the member liked, at most `limit`, so a count stops at what a badge needs."""
	Reaction = frappe.qb.DocType("GP Reaction")
	found = 0
	for doctype in POSTS:
		Post = frappe.qb.DocType(doctype)
		found += len(
			frappe.qb.from_(Reaction)
			.join(Post)
			.on(reaction_join(Reaction, Post, doctype))
			.select(Reaction.reference_name)
			.distinct()
			.where((Reaction.user == user) & (Post.owner != user) & visible(Post, doctype))
			.limit(limit - found)
			.run()
		)
		if found >= limit:
			break
	return found


def first_like(user, *, given):
	"""The first like the member gave, or with `given=False` received: a dict or None."""
	Reaction = frappe.qb.DocType("GP Reaction")
	found = []
	for doctype in POSTS:
		Post = frappe.qb.DocType(doctype)
		mine = (Reaction.user == user) if given else (Post.owner == user)
		found += (
			frappe.qb.from_(Reaction)
			.join(Post)
			.on(reaction_join(Reaction, Post, doctype))
			.select(
				Reaction.creation.as_("granted_at"),
				Reaction.reference_doctype,
				Reaction.reference_name,
			)
			.where(mine & (Reaction.user != Post.owner) & visible(Post, doctype))
			.orderby(Reaction.creation)
			.limit(1)
			.run(as_dict=True)
		)
	return min(found, key=lambda row: row.granted_at, default=None)


def first_mention(user):
	"""The first post in which the member mentioned someone else, from mention notifications."""
	Notification = frappe.qb.DocType("GP Notification")
	row = (
		frappe.qb.from_(Notification)
		.select(Notification.creation, Notification.comment, Notification.discussion)
		.where(
			(Notification.type == "Mention")
			& (Notification.from_user == user)
			& (Notification.to_user != user)
			& (Notification.discussion.isnotnull() | Notification.comment.isnotnull())
		)
		.orderby(Notification.creation)
		.limit(1)
		.run(as_dict=True)
	)
	if not row:
		return None
	row = row[0]
	if row.comment:
		return frappe._dict(
			granted_at=row.creation, reference_doctype="GP Comment", reference_name=row.comment
		)
	return frappe._dict(
		granted_at=row.creation, reference_doctype="GP Discussion", reference_name=row.discussion
	)


def long_discussion_read(user, min_replies):
	"""A discussion with more than `min_replies` replies the member visited after its last one."""
	Visit, Discussion = frappe.qb.DocType("GP Discussion Visit"), frappe.qb.DocType("GP Discussion")
	row = (
		frappe.qb.from_(Visit)
		.join(Discussion)
		.on(Discussion.name == Visit.discussion)
		.select(Visit.last_visit, Discussion.name)
		.where(
			(Visit.user == user)
			& (Discussion.comments_count > min_replies)
			& (Visit.last_visit >= Discussion.last_post_at)
			& visible(Discussion, "GP Discussion")
		)
		.orderby(Visit.last_visit)
		.limit(1)
		.run()
	)
	if not row:
		return None
	return frappe._dict(
		granted_at=row[0][0], reference_doctype="GP Discussion", reference_name=str(row[0][1])
	)


def visit_days(user):
	Day = frappe.qb.DocType("GP Visit Day")
	return frappe.qb.from_(Day).select(Day.day).where(Day.user == user).orderby(Day.day).run(pluck=True)


def solutions(user):
	"""When each of the member's replies was marked as the solution, oldest first."""
	Comment = frappe.qb.DocType("GP Comment")
	return (
		frappe.qb.from_(Comment)
		.select(Comment.highlighted_at)
		.where((Comment.owner == user) & Comment.highlighted_at.isnotnull() & visible(Comment, "GP Comment"))
		.orderby(Comment.highlighted_at)
		.run(pluck=True)
	)


def posted_between(user, start, end):
	for doctype in POSTS:
		Post = frappe.qb.DocType(doctype)
		if (
			frappe.qb.from_(Post)
			.select(Post.name)
			.where(
				(Post.owner == user)
				& (Post.creation >= start)
				& (Post.creation < end)
				& visible(Post, doctype)
			)
			.limit(1)
			.run()
		):
			return True
	return False
