# Copyright (c) 2022, Frappe Technologies Pvt Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from gameplan.realtime import notify_notification_changed


class GPNotification(Document):
	def before_insert(self):
		# A new row is one event, happening now. Writers that merge repeat events into an
		# existing row move this forward themselves (see HasReactions.notify_reactions).
		if not self.last_event_at:
			self.last_event_at = frappe.utils.now()
		if not self.event_count:
			self.event_count = 1

	def before_save(self):
		# `modified` is when the row last had news: its insert, or a reaction re-lighting it.
		# The bell sorts and dates rows by it, so marking a row read must not move it.
		if self.is_marked_read_only():
			self.modified = self.get_doc_before_save().modified

	def is_marked_read_only(self):
		before = self.get_doc_before_save()
		if not before or not (self.read and not before.read):
			return False
		# Compared as text: links to autoincrement doctypes load as int but arrive as str.
		changed = [
			f.fieldname
			for f in self.meta.fields
			if str(before.get(f.fieldname) or "") != str(self.get(f.fieldname) or "")
		]
		return changed == ["read"]

	def on_update(self):
		# Not `after_insert`: a reaction REUSES the existing row and resets `read` to 0
		# (see HasReactions.notify_reactions), and the bell's mark-as-read is a PUT that
		# updates in place. Both are UPDATEs, so an insert-only hook left the unread badge
		# stale in every open tab until a full reload. `has_value_changed` is True when
		# there is no doc-before-save, so inserts still announce themselves.
		#
		# `event_count` too: a repeat event merging into a row that is *already* unread
		# changes neither `read` nor the unread count, yet an open inbox has to move from
		# "1 new comment" to "2 new comments".
		if self.has_value_changed("read") or self.has_value_changed("event_count"):
			notify_notification_changed(self.to_user, self)

	@staticmethod
	def clear_notifications(discussion=None, comment=None, poll=None, task=None, user=None):
		if not user:
			user = frappe.session.user
		filters = {"to_user": user}
		if discussion:
			filters["discussion"] = str(discussion)
		if comment:
			filters["comment"] = str(comment)
		if poll:
			filters["poll"] = str(poll)
		if task:
			filters["task"] = str(task)

		Notification = frappe.qb.DocType("GP Notification")
		query = frappe.qb.update(Notification).set(Notification.read, 1)
		for field, value in filters.items():
			query = query.where(Notification[field] == value)
		query.run()

		notify_notification_changed(user)


def on_doctype_update():
	# The inbox lists one user's rows newest-event-first. `read` is left out on purpose: it is a
	# reserved word in MariaDB and add_index does not quote column names.
	frappe.db.add_index("GP Notification", ["to_user", "last_event_at"])
	# Who has notifications about this discussion or reply: asked when moderation removes it.
	frappe.db.add_index("GP Notification", ["discussion"], "discussion_notifications")
	frappe.db.add_index("GP Notification", ["comment"], "comment_notifications")
