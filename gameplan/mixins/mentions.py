# Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and Contributors
# MIT License. See license.txt


import frappe
from frappe.utils import get_fullname

from gameplan.notifications import records
from gameplan.notifications.resolver import bulk_discussion_states, discussion_of, is_muted
from gameplan.permissions import _guest_users, _member_users, get_content_project, users_who_can_view_space
from gameplan.utils import extract_mentions, extract_rich_quote_authors


class HasMentions:
	def notify_mentions(self):
		mentions_field = getattr(self, "mentions_field", None)
		if not mentions_field:
			return set()

		mentions = extract_mentions(self.get(mentions_field))
		authors = extract_rich_quote_authors(self.get(mentions_field))
		from gameplan.guest_payload import users_for_handles

		users = users_for_handles({mention.email for mention in mentions} | set(authors))
		notified_users = set()
		reached = set()
		for mention in mentions:
			# Handle special "everyone" mention
			if mention.email == "_everyone_":
				reached.update(self._notify_everyone_mention())
				continue

			user = users.get(mention.email, mention.email)
			if self._notify_user(user, is_everyone=False):
				reached.add(user)
			notified_users.add(user)
		reached.update(self._notify_rich_quote_authors(authors, notified_users, users))
		return reached

	def _notify_rich_quote_authors(self, authors, notified_users, users):
		reached = set()
		for author in authors:
			author = users.get(author, author)
			if author in notified_users:
				continue
			if self._notify_user(author, is_everyone=False, notification_type="Rich Quote"):
				reached.add(author)
		return reached

	def _notify_everyone_mention(self):
		"""Notify the people who joined this post's space, writing the rows in a background job.

		The audience is resolved in a fixed handful of set-based queries instead of
		asking can_view_content once per user: that form costs 2-3 queries each, so an
		@everyone on a 500-member site added ~1,500 synchronous queries inline in the
		request that created the discussion.

		@everyone is a mention, so a user who muted this discussion is left out, resolved in
		bulk the same way.
		"""
		audience = self._everyone_audience()
		discussion = discussion_of(self)
		if discussion:
			states = bulk_discussion_states(audience, discussion)
			audience = [user for user in audience if states.get(user) != "Mute"]
		if audience:
			frappe.enqueue(
				"gameplan.mixins.mentions.write_everyone_notifications",
				doctype=self.doctype,
				name=self.name,
				users=audience,
				enqueue_after_commit=True,
				now=frappe.in_test,
			)
		return set(audience)

	def _everyone_audience(self):
		"""The enabled users who joined this post's space, plus its guests, who can view it.

		Same rule as _can_notify (author excluded, no one who cannot view the content),
		resolved in bulk. The author is filtered out here, before the permission call:
		users_who_can_view_space answers only "who can see it", and the author
		trivially can.
		"""
		project = get_content_project(self)
		if not project:
			return []
		joined = _member_users("GP Project", project) | _guest_users(project)
		joined.discard(self.owner)
		if not joined:
			return []
		users = frappe.get_all("User", filters={"name": ["in", list(joined)], "enabled": 1}, pluck="name")
		return users_who_can_view_space(sorted(users), project)

	def _can_notify(self, user_email):
		"""Nobody gets notified about their own post, about content they cannot open, or
		about a discussion they muted.

		The mention autocomplete offers every active user and @everyone fans out to all
		of them, so both can address people outside the space. A notification row links
		the discussion/task and the bell shows its title, so notifying someone without
		access would leak that title and hand them a dead link.

		Mute is the last check and applies only inside a discussion: a muted discussion is
		the one place a mention does not get through, because muting a specific thread is
		the most pointed signal a user can give. Task mentions have no discussion and are
		unaffected.
		"""
		from gameplan.permissions import can_view_content

		if user_email == self.owner:
			return False
		# A mention or rich quote outlives the account it points at: delete the user (or
		# paste content quoting one) and the email stays in the HTML forever. None of the
		# permission checks below require the User row to exist, and GP Notification.to_user
		# is a Link — so without this the notification insert raises LinkValidationError and
		# takes the whole post save down with it.
		if not frappe.db.exists("User", user_email):
			return False
		if not can_view_content(user_email, self):
			return False
		discussion = discussion_of(self)
		if discussion and is_muted(user_email, discussion):
			return False
		return True

	def _notify_user(self, user_email, is_everyone=False, notification_type="Mention"):
		if not self._can_notify(user_email):
			return False
		self._create_notification(user_email, is_everyone, notification_type)
		return True

	def _create_notification(self, user_email, is_everyone=False, notification_type="Mention"):
		"""Write the notification row. Callers must have cleared `user_email` first."""
		values = frappe._dict(
			from_user=self.owner,
			to_user=user_email,
			type=notification_type,
			**records.target_fields(self),
		)

		if frappe.db.exists("GP Notification", values):
			return

		records.write_or_merge(
			message=self._get_notification_message(is_everyone, notification_type),
			merge=False,
			**values,
		)

	def _get_notification_message(self, is_everyone, notification_type):
		author = get_fullname(self.owner)
		post_label = "task" if self._is_task_context() else "post"
		if notification_type == "Rich Quote":
			return f"{author} quoted you in a {post_label}"
		if is_everyone:
			return f"{author} mentioned everyone in a {post_label}"
		return f"{author} mentioned you in a {post_label}"

	def _is_task_context(self):
		return "GP Task" in [self.doctype, self.get("reference_doctype")]


def write_everyone_notifications(doctype, name, users):
	if not frappe.db.exists(doctype, name):
		return
	doc = frappe.get_doc(doctype, name)
	for user in users:
		doc._create_notification(user, is_everyone=True)
