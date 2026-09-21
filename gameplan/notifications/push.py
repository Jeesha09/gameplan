# Copyright (c) 2026, Frappe Technologies Pvt Ltd and contributors
# For license information, please see license.txt

"""The push channel: a browser or phone notification, delivered through Frappe's Push
Notification Relay (`frappe.push_notification`), for users whose channel is Push.

Two speeds, like the email channel has one:
- A mention, rich quote or comment goes out at once (`queue_realtime_push`, called from
  `records.write_or_merge`) — someone is waiting on the user.
- Everything else (new discussions, reactions, poll votes) rides the five-minute batch as
  one summary push (`send_batch_push`, called from `delivery.send_batch`).

Both respect what the rest of the system already decided: a row written during an away
stretch is never pushed (the card covers it), and the batch only runs inside active hours.
A row is pushed once (`push_sent_at`).
"""

import frappe
from frappe.push_notification import PushNotification
from frappe.utils import get_url

from gameplan.email_digest import html_to_text_preview, notification_path
from gameplan.notifications.away import is_away, user_timezone
from gameplan.notifications.preferences import profile_prefs

PROJECT_NAME = "gameplan"
REALTIME_TYPES = ("Mention", "Rich Quote", "Comment")


def push_enabled() -> bool:
	"""The relay is switched on for this site and this is not a developer's machine.

	Like Raven, a developer-mode or localhost site never pushes: a backup restored
	locally must not ping real devices. `allow_push_in_developer_mode` in site config
	lifts that for a dev site that has its own relay to test against.
	"""
	if not PushNotification(PROJECT_NAME).is_enabled():
		return False
	if frappe.conf.allow_push_in_developer_mode:
		return True
	url = frappe.utils.get_url()
	return not (
		frappe.conf.developer_mode or url.startswith("http://localhost") or url.startswith("http://127.0.0.1")
	)


def wants_push(user: str) -> bool:
	return profile_prefs(user).get("notification_channel") == "Push"


def queue_realtime_push(doc) -> bool:
	"""Called right after a notification row is written. Returns True when a push was
	queued. The send itself runs in a background job after the commit, so a slow relay
	never holds up the comment being posted."""
	if doc.type not in REALTIME_TYPES or doc.away_period:
		return False
	if not wants_push(doc.to_user) or not push_enabled():
		return False
	frappe.enqueue(
		"gameplan.notifications.push.send_push",
		name=doc.name,
		enqueue_after_commit=True,
		queue="short",
	)
	return True


def send_push(name: str) -> bool:
	"""One push for one row. Skipped — and stamped, so it is not looked at again — when
	the row was read meanwhile, already pushed, or the user is away at send time."""
	row = _row(name)
	if not row or row.push_sent_at:
		return False
	if row.read or row.away_period or not wants_push(row.to_user) or not push_enabled():
		_stamp([row])
		return False
	prefs = profile_prefs(row.to_user)
	if is_away(prefs, tz=user_timezone(row.to_user)):
		# Outside the hours now: leave it unstamped for the batch's closing push.
		return False
	_send(row.to_user, title=_title(row), body=_body(row), link=_link(row))
	_stamp([row])
	return True


def send_batch_push(user: str, rows: list) -> None:
	"""The five-minute batch for a Push user: one summary instead of a popup per row."""
	if not rows or not push_enabled():
		return
	count = len(rows)
	if count == 1:
		title, body, link = _title(rows[0]), _body(rows[0]), _link(rows[0])
	else:
		title = f"{count} new notifications in Gameplan"
		body = " · ".join(_body(row) for row in rows[:3])
		link = get_url("/g/notifications")
	_send(user, title=title, body=body, link=link)


def _send(user: str, *, title: str, body: str, link: str) -> None:
	PushNotification(PROJECT_NAME).send_notification_to_user(user, title, body, link=link)


def _title(row) -> str:
	return row.discussion_title or row.task_title or "Gameplan"


def _body(row) -> str:
	return html_to_text_preview(row.message, 160) or row.type


def _link(row) -> str:
	return get_url(notification_path(row) or "/g/notifications")


def _row(name: str):
	rows = frappe.qb.get_query(
		"GP Notification",
		fields=[
			"name",
			"to_user",
			"type",
			"message",
			"read",
			"away_period",
			"push_sent_at",
			"discussion",
			"discussion.title as discussion_title",
			"discussion.slug as discussion_slug",
			"task",
			"task.title as task_title",
			"project",
			"team",
		],
		filters={"name": name},
		ignore_permissions=True,
	).run(as_dict=True)
	return rows[0] if rows else None


def _stamp(rows: list) -> None:
	Notification = frappe.qb.DocType("GP Notification")
	(
		frappe.qb.update(Notification)
		.set(Notification.push_sent_at, frappe.utils.now_datetime())
		.where(Notification.name.isin([row.name for row in rows]))
	).run()
