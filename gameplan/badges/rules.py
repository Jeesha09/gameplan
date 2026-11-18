"""One rule per badge family. A rule returns every grant a member qualifies for, by badge key.

Thresholds are Discourse's, in lib/badge_queries.rb and db/fixtures/006_badges.rb. Where
Discourse grants "now", so does Gameplan; where it records when the badge was earned, the
grant does too.
"""

from datetime import date, datetime, timedelta

import frappe
from frappe.utils import add_years, get_datetime

from gameplan.badges import signals
from gameplan.restrictions import utc_now

BIO_MIN_LENGTH = 10
READER_MIN_REPLIES = 100
# (badge key, likes on each post, more than this many posts)
APPRECIATED = (("appreciated", 1, 20), ("respected", 2, 100), ("admired", 5, 300))
# (badge key, more than this many liked posts, likes given)
THANK_YOU = (("thank-you", 20, 10), ("gives-back", 100, 100), ("empathetic", 500, 1000))
ENTHUSIAST = (("enthusiast", 10), ("aficionado", 100), ("devotee", 365))
HELPER = (("helper", 10), ("trusted-helper", 50), ("community-guide", 150))
REPLY = (("nice-reply", 10), ("good-reply", 25), ("great-reply", 50))
TOPIC = (("nice-topic", 10), ("good-topic", 25), ("great-topic", 50))


def grant(granted_at=None, reference=None, seq=0):
	reference = reference or {}
	return frappe._dict(
		granted_at=get_datetime(granted_at) if granted_at else utc_now(),
		reference_doctype=reference.get("reference_doctype") or "",
		reference_name=str(reference.get("reference_name") or ""),
		seq=seq,
	)


def autobiographer(user):
	bio, image = frappe.db.get_value("GP User Profile", {"user": user}, ["bio", "image"]) or (None, None)
	qualifies = len((bio or "").strip()) > BIO_MIN_LENGTH and bool(image)
	return {"autobiographer": [grant()] if qualifies else []}


def from_row(key, row):
	return {key: [grant(row.granted_at, row)] if row else []}


def first_like(user):
	return from_row("first-like", signals.first_like(user, given=True))


def welcome(user):
	return from_row("welcome", signals.first_like(user, given=False))


def first_mention(user):
	return from_row("first-mention", signals.first_mention(user))


def reader(user):
	return from_row("reader", signals.long_discussion_read(user, READER_MIN_REPLIES))


def appreciated(user):
	grants = {}
	for key, likes, more_than in APPRECIATED:
		grants[key] = [grant()] if len(signals.liked_posts(user, likes)) > more_than else []
	return grants


def thank_you(user):
	liked = len(signals.liked_posts(user, 1))
	grants = {}
	for key, more_than, given in THANK_YOU:
		earned = liked > more_than and signals.likes_given(user, given) >= given
		grants[key] = [grant()] if earned else []
	return grants


def enthusiast(user):
	runs = visit_runs(signals.visit_days(user))
	grants = {}
	for key, days in ENTHUSIAST:
		start = next((start for start, length in runs if length >= days), None)
		# Discourse dates the badge at the end of the first run long enough.
		grants[key] = (
			[grant(datetime.combine(start + timedelta(days=days), datetime.min.time()))] if start else []
		)
	return grants


def anniversary(user):
	"""One grant for each full year as a member with a post in it, numbered by the year."""
	joined = get_datetime(frappe.db.get_value("User", user, "creation"))
	now, grants, year = utc_now(), [], 1
	while (anniversary_at := add_years(joined, year)) <= now:
		if signals.posted_between(user, add_years(joined, year - 1), anniversary_at):
			grants.append(grant(anniversary_at, seq=year))
		year += 1
	return {"anniversary": grants}


def helper(user):
	marked = signals.solutions(user)
	return {key: [grant(marked[count - 1])] if len(marked) >= count else [] for key, count in HELPER}


def reply(user):
	return per_post(user, REPLY, "GP Comment")


def topic(user):
	return per_post(user, TOPIC, "GP Discussion")


def per_post(user, tiers, doctype):
	"""One grant for each of the member's posts with enough likes. Each tier keeps its own."""
	posts = signals.liked_posts(user, min(likes for _, likes in tiers), (doctype,))
	return {
		key: [
			grant(reference={"reference_doctype": post_doctype, "reference_name": name})
			for post_doctype, name, count in posts
			if count >= likes
		]
		for key, likes in tiers
	}


def visit_runs(days):
	"""(first day, length) of each run of days in a row, oldest first."""
	runs = []
	for day in sorted({as_date(day) for day in days}):
		if runs and runs[-1][0] + timedelta(days=runs[-1][1]) == day:
			runs[-1] = (runs[-1][0], runs[-1][1] + 1)
		else:
			runs.append((day, 1))
	return runs


def as_date(value):
	return (
		value if isinstance(value, date) and not isinstance(value, datetime) else get_datetime(value).date()
	)


RULES = {
	"autobiographer": autobiographer,
	"first-like": first_like,
	"first-mention": first_mention,
	"reader": reader,
	"welcome": welcome,
	"appreciated": appreciated,
	"thank-you": thank_you,
	"enthusiast": enthusiast,
	"anniversary": anniversary,
	"helper": helper,
	"reply": reply,
	"topic": topic,
}
