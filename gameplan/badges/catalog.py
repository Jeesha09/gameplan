"""The badges Gameplan ships, with Discourse's names, tiers, thresholds and ids (prd/badges.md).

`sync` keeps a GP Badge row for each one. It runs after every migrate and leaves a global
admin's choice to turn a badge off alone.
"""

import frappe

GROUPS = ("Getting Started", "Community", "Posting")


def badge(key, title, group, family, tier, description, discourse_id=None, **flags):
	return frappe._dict(
		key=key,
		title=title,
		badge_group=group,
		family=family,
		tier=tier,
		description=description,
		discourse_id=discourse_id or 0,
		per_post=flags.get("per_post", 0),
		multiple_grant=flags.get("multiple_grant", 0),
		revocable=flags.get("revocable", 0),
	)


def tiers(keys, titles, group, family, descriptions, discourse_ids, **flags):
	return [
		badge(key, title, group, family, tier, description, discourse_id, **flags)
		for key, title, tier, description, discourse_id in zip(
			keys, titles, ("Bronze", "Silver", "Gold"), descriptions, discourse_ids, strict=True
		)
	]


GETTING_STARTED = [
	badge(
		"autobiographer",
		"Autobiographer",
		"Getting Started",
		"autobiographer",
		"Bronze",
		"Filled in a bio and added a profile photo",
		9,
	),
	badge("first-like", "First Like", "Getting Started", "first-like", "Bronze", "Liked a post", 11),
	badge(
		"first-mention",
		"First Mention",
		"Getting Started",
		"first-mention",
		"Bronze",
		"Mentioned someone in a post",
		40,
	),
	badge(
		"reader",
		"Reader",
		"Getting Started",
		"reader",
		"Bronze",
		"Read every reply in a discussion with more than 100 replies",
		17,
	),
]

COMMUNITY = [
	badge("welcome", "Welcome", "Community", "welcome", "Bronze", "Received a like", 5),
	*tiers(
		("appreciated", "respected", "admired"),
		("Appreciated", "Respected", "Admired"),
		"Community",
		"appreciated",
		(
			"Received at least 1 like on more than 20 posts",
			"Received at least 2 likes on more than 100 posts",
			"Received at least 5 likes on more than 300 posts",
		),
		(36, 37, 31),
	),
	*tiers(
		("thank-you", "gives-back", "empathetic"),
		("Thank You", "Gives Back", "Empathetic"),
		"Community",
		"thank-you",
		(
			"Has more than 20 liked posts and gave 10 likes",
			"Has more than 100 liked posts and gave 100 likes",
			"Has more than 500 liked posts and gave 1000 likes",
		),
		(38, 32, 39),
	),
	*tiers(
		("enthusiast", "aficionado", "devotee"),
		("Enthusiast", "Aficionado", "Devotee"),
		"Community",
		"enthusiast",
		(
			"Visited 10 days in a row",
			"Visited 100 days in a row",
			"Visited 365 days in a row",
		),
		(45, 46, 47),
	),
	badge(
		"anniversary",
		"Anniversary",
		"Community",
		"anniversary",
		"Silver",
		"A member for a year, with at least one post that year",
		24,
		multiple_grant=1,
	),
	*tiers(
		("helper", "trusted-helper", "community-guide"),
		("Helper", "Trusted Helper", "Community Guide"),
		"Community",
		"helper",
		(
			"Had 10 replies marked as the solution",
			"Had 50 replies marked as the solution",
			"Had 150 replies marked as the solution",
		),
		(None, None, None),
	),
]

POSTING = [
	*tiers(
		("nice-reply", "good-reply", "great-reply"),
		("Nice Reply", "Good Reply", "Great Reply"),
		"Posting",
		"reply",
		("Received 10 likes on a reply", "Received 25 likes on a reply", "Received 50 likes on a reply"),
		(6, 7, 8),
		per_post=1,
		revocable=1,
	),
	*tiers(
		("nice-topic", "good-topic", "great-topic"),
		("Nice Topic", "Good Topic", "Great Topic"),
		"Posting",
		"topic",
		(
			"Received 10 likes on a discussion",
			"Received 25 likes on a discussion",
			"Received 50 likes on a discussion",
		),
		(18, 19, 20),
		per_post=1,
		revocable=1,
	),
]

BADGES = GETTING_STARTED + COMMUNITY + POSTING
BY_KEY = {spec.key: spec for spec in BADGES}
BY_DISCOURSE_ID = {spec.discourse_id: spec.key for spec in BADGES if spec.discourse_id}


def sync():
	"""`after_migrate`: create or update the shipped badges. A global admin's `enabled` is kept."""
	for position, spec in enumerate(BADGES):
		values = {**spec, "position": position, "symbol": spec.family, "system": 1}
		if frappe.db.exists("GP Badge", spec.key):
			frappe.db.set_value("GP Badge", spec.key, values, update_modified=False)
		else:
			frappe.get_doc(doctype="GP Badge", enabled=1, **values).insert(ignore_permissions=True)
