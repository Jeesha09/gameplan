"""Transactional, per-account forum quotas with UTC elapsed-time windows."""

import math
from datetime import datetime, timedelta, timezone

import frappe
from frappe.utils import cint, get_datetime

import gameplan
from gameplan.api import require_admin
from gameplan.approval_files import publishing_submission

FIELDS = ("discussions_hour", "discussions_day", "replies_hour", "replies_day")
MAX_LIMIT = 10000


@frappe.whitelist(methods=["GET", "POST"])
def settings():
	"""Return site posting settings to global admins."""
	require_admin()
	return policy()


@frappe.whitelist(methods=["POST"])
def save_settings(
	enabled: int, discussions_hour: int, discussions_day: int, replies_hour: int, replies_day: int
):
	"""Save the global-admin posting policy, with zero disabling an individual limit."""
	require_admin()
	doc = frappe.get_doc("GP Posting Settings")
	doc.update(
		dict(
			enabled=enabled,
			discussions_hour=discussions_hour,
			discussions_day=discussions_day,
			replies_hour=replies_hour,
			replies_day=replies_day,
		)
	)
	doc.save()
	return policy()


@frappe.whitelist(methods=["GET", "POST"])
def status(kind: str):
	"""Return only the current account's posting wait and the applicable limit."""
	if kind not in ("discussion", "reply"):
		frappe.throw("Choose discussion or reply")
	if frappe.session.user == "Guest":
		frappe.throw("Sign in to post", frappe.PermissionError)
	return allowance(kind)


def record(doc, method=None):
	kind = kind_for(doc)
	publication = publishing_submission.get()
	if not kind or (publication and publication[0] is doc):
		return
	user = frappe.session.user
	# Share the account-first lock order with approvals and slow mode.
	frappe.db.get_value("User", user, "name", for_update=True)
	wait = allowance(kind, for_update=True)
	if wait["retry_after"]:
		if kind == "reply":
			from gameplan.slow_mode import status as slow_status

			slow = slow_status(str(doc.reference_name))
			if slow["retry_after"] > wait["retry_after"]:
				frappe.throw(
					f"Slow mode: wait {slow['retry_after']} seconds before replying again.",
					frappe.RateLimitExceededError,
				)
		frappe.throw(
			f"Posting limit: {wait['limit']}. Try again in {wait['retry_after']} seconds.",
			frappe.RateLimitExceededError,
		)
	frappe.get_doc(doctype="GP Posting Event", user=user, kind=kind, accepted_at=utc_now()).insert(
		ignore_permissions=True
	)


def policy():
	doc = frappe.get_cached_doc("GP Posting Settings")
	return {"enabled": cint(doc.enabled), **{key: cint(doc.get(key)) for key in FIELDS}}


def allowance(kind, *, for_update=False):
	result = {"retry_after": 0, "limit": ""}
	config = policy()
	if not config["enabled"] or gameplan.is_admin():
		return result
	prefix = "discussions" if kind == "discussion" else "replies"
	limits = [(config[f"{prefix}_hour"], 3600, "hour"), (config[f"{prefix}_day"], 86400, "24 hours")]
	maximum = max(count for count, _, _ in limits)
	if not maximum:
		return result
	now = utc_now()
	Event = frappe.qb.DocType("GP Posting Event")
	query = (
		frappe.qb.from_(Event)
		.select(Event.accepted_at)
		.where(
			(Event.user == frappe.session.user)
			& (Event.kind == kind)
			& (Event.accepted_at > now - timedelta(days=1))
		)
		.orderby(Event.accepted_at, order=frappe.qb.desc)
		.limit(maximum)
	)
	# A locking read sees submissions committed after MariaDB's earlier request snapshot.
	if for_update:
		query = query.for_update()
	times = query.run(pluck=True)
	for count, seconds, label in limits:
		if not count or len(times) < count:
			continue
		retry = max(
			0, math.ceil((get_datetime(times[count - 1]) + timedelta(seconds=seconds) - now).total_seconds())
		)
		if retry > result["retry_after"]:
			noun = kind if count == 1 else prefix
			result = {"retry_after": retry, "limit": f"{count} {noun} per {label}"}
	return result


def kind_for(doc):
	if doc.doctype == "GP Discussion":
		return "discussion"
	if doc.doctype == "GP Comment" and doc.reference_doctype == "GP Discussion":
		return "reply"


def prune():
	"""Delete one indexed batch of expired quota events per scheduler run."""
	Event = frappe.qb.DocType("GP Posting Event")
	names = (
		frappe.qb.from_(Event)
		.select(Event.name)
		.where(Event.accepted_at <= utc_now() - timedelta(days=1))
		.orderby(Event.accepted_at)
		.limit(10000)
		.run(pluck=True)
	)
	if names:
		frappe.db.delete("GP Posting Event", {"name": ["in", names]})


def utc_now():
	# Internal quota timestamps are UTC, independent of site/user time zones and DST.
	return datetime.now(timezone.utc).replace(tzinfo=None)


def clear_user(doc, method=None):
	frappe.db.delete("GP Posting Event", {"user": doc.name})
