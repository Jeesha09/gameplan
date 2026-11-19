from datetime import date, timedelta
from unittest.mock import patch

import frappe

from gameplan.badges import QUEUE, catalog, on_reaction_change
from gameplan.badges.api import (
	badge_holders,
	favorites,
	get_settings,
	grant_badge,
	list_badges,
	revoke_badge,
	save_settings,
	set_favorites,
	user_badges,
)
from gameplan.badges.engine import check_user, full_pass, process_queue
from gameplan.restrictions import utc_now
from gameplan.tests.base import GameplanTestCase
from gameplan.tests.fixtures import create_comment, create_community, create_discussion, create_space
from gameplan.trust_levels import add_visit_days


class BadgeTestCase(GameplanTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.cache.delete_value, QUEUE)
		self.addCleanup(frappe.clear_cache, doctype="GP Badge Settings")
		catalog.sync()
		self.community = create_community("Badges", members=[self.member, self.second_member, self.outsider])
		self.space = create_space("Badge Space", self.community)
		self.discussion = create_discussion("Badge topic", self.space, owner=self.member)
		self.turn_on()

	def turn_on(self, enabled=1, **kwargs):
		with self.as_user(self.admin), patch("frappe.enqueue"):
			save_settings(enabled, **kwargs)

	def react(self, user, post, emoji="👍"):
		doc = frappe.get_doc(
			doctype="GP Reaction",
			reference_doctype=post.doctype,
			reference_name=str(post.name),
			emoji=emoji,
			user=user.name,
		).insert(ignore_permissions=True)
		frappe.db.set_value("GP Reaction", doc.name, "creation", utc_now(), update_modified=False)
		return doc

	def badges(self, user):
		return set(frappe.get_all("GP User Badge", filters={"user": user.name}, pluck="badge"))

	def grants(self, user, badge):
		return frappe.get_all(
			"GP User Badge",
			filters={"user": user.name, "badge": badge},
			fields=["reference_doctype", "reference_name", "seq", "granted_at"],
			order_by="seq asc",
		)

	def notifications(self, user):
		return frappe.get_all(
			"GP Notification", filters={"to_user": user.name, "type": "Badge"}, pluck="message"
		)


class TestCatalog(BadgeTestCase):
	def test_sync_ships_24_badges_in_12_families_and_keeps_an_admins_switch(self):
		self.assertEqual(frappe.db.count("GP Badge", {"system": 1}), 24)
		self.assertEqual(len({spec.family for spec in catalog.BADGES}), 12)
		frappe.db.set_value("GP Badge", "reader", "enabled", 0)
		catalog.sync()
		self.assertEqual(frappe.db.get_value("GP Badge", "reader", "enabled"), 0)

	def test_love_badges_are_not_shipped(self):
		self.assertFalse({33, 34, 35} & set(catalog.BY_DISCOURSE_ID))


class TestSwitch(BadgeTestCase):
	def test_nothing_is_granted_while_badges_are_off(self):
		self.turn_on(0)
		self.react(self.second_member, self.discussion)
		self.assertEqual(check_user(self.second_member.name), [])
		self.assertEqual(self.badges(self.second_member), set())

	def test_only_global_admins_change_the_settings(self):
		with self.as_user(self.member), self.assertRaises(frappe.PermissionError):
			save_settings(1)
		with self.as_user(self.member), self.assertRaises(frappe.PermissionError):
			get_settings()

	def test_turning_on_runs_a_silent_full_pass(self):
		self.turn_on(0)
		with self.as_user(self.admin), patch("frappe.enqueue") as enqueue:
			save_settings(1)
		self.assertEqual(enqueue.call_args.kwargs["notify"], False)
		self.react(self.second_member, self.discussion)
		with patch("frappe.db.commit"):
			full_pass(notify=False)
		self.assertIn("first-like", self.badges(self.second_member))
		self.assertEqual(self.notifications(self.second_member), [])

	def test_a_badge_turned_off_is_not_granted(self):
		self.turn_on(1, disabled_badges=["first-like"])
		self.react(self.second_member, self.discussion)
		check_user(self.second_member.name)
		self.assertNotIn("first-like", self.badges(self.second_member))


class TestLikes(BadgeTestCase):
	def test_a_like_grants_first_like_and_welcome_with_a_notification(self):
		self.react(self.second_member, self.discussion)
		check_user(self.second_member.name)
		check_user(self.member.name)
		self.assertIn("first-like", self.badges(self.second_member))
		self.assertIn("welcome", self.badges(self.member))
		self.assertEqual(self.notifications(self.member), ["You earned the Welcome badge."])
		grant = self.grants(self.member, "welcome")[0]
		self.assertEqual(
			(grant.reference_doctype, grant.reference_name), ("GP Discussion", str(self.discussion.name))
		)

	def test_liking_your_own_post_counts_for_nothing(self):
		self.react(self.member, self.discussion)
		check_user(self.member.name)
		self.assertFalse({"first-like", "welcome"} & self.badges(self.member))

	def test_likes_on_a_hidden_post_do_not_count(self):
		self.react(self.second_member, self.discussion)
		frappe.db.set_value("GP Discussion", self.discussion.name, "hidden_at", utc_now())
		check_user(self.member.name)
		self.assertNotIn("welcome", self.badges(self.member))

	def test_a_badge_is_granted_once(self):
		self.react(self.second_member, self.discussion)
		check_user(self.member.name)
		check_user(self.member.name)
		self.assertEqual(len(self.grants(self.member, "welcome")), 1)

	def test_appreciated_counts_posts_with_enough_likes(self):
		replies = [create_comment(self.discussion, owner=self.member) for _ in range(3)]
		with patch("gameplan.badges.rules.APPRECIATED", (("appreciated", 1, 2), ("respected", 2, 2))):
			for reply in replies[:2]:
				self.react(self.second_member, reply)
			check_user(self.member.name)
			self.assertNotIn("appreciated", self.badges(self.member))
			self.react(self.second_member, replies[2])
			check_user(self.member.name)
		self.assertIn("appreciated", self.badges(self.member))
		self.assertNotIn("respected", self.badges(self.member))

	def test_thank_you_needs_liked_posts_and_likes_given(self):
		replies = [create_comment(self.discussion, owner=self.member) for _ in range(2)]
		for reply in replies:
			self.react(self.second_member, reply)
		with patch("gameplan.badges.rules.THANK_YOU", (("thank-you", 1, 1),)):
			check_user(self.member.name)
			self.assertNotIn("thank-you", self.badges(self.member))
			other = create_discussion("Someone else's", self.space, owner=self.second_member)
			self.react(self.member, other)
			check_user(self.member.name)
		self.assertIn("thank-you", self.badges(self.member))


class TestPerPost(BadgeTestCase):
	def test_nice_reply_is_earned_per_reply_and_taken_back(self):
		reply = create_comment(self.discussion, owner=self.member)
		with patch("gameplan.badges.rules.REPLY", (("nice-reply", 2), ("good-reply", 3))):
			self.react(self.second_member, reply)
			first = self.react(self.outsider, reply)
			check_user(self.member.name)
			[grant] = self.grants(self.member, "nice-reply")
			self.assertEqual(grant.reference_name, str(reply.name))
			self.assertNotIn("good-reply", self.badges(self.member))
			frappe.delete_doc("GP Reaction", first.name, ignore_permissions=True)
			check_user(self.member.name)
		self.assertEqual(self.grants(self.member, "nice-reply"), [])

	def test_nice_topic_counts_the_discussion_not_its_replies(self):
		reply = create_comment(self.discussion, owner=self.member)
		with patch("gameplan.badges.rules.TOPIC", (("nice-topic", 1),)):
			self.react(self.second_member, reply)
			check_user(self.member.name)
			self.assertNotIn("nice-topic", self.badges(self.member))
			self.react(self.second_member, self.discussion)
			check_user(self.member.name)
		self.assertIn("nice-topic", self.badges(self.member))

	def test_deleting_a_post_deletes_its_grants(self):
		reply = create_comment(self.discussion, owner=self.member)
		with patch("gameplan.badges.rules.REPLY", (("nice-reply", 1),)):
			self.react(self.second_member, reply)
			check_user(self.member.name)
		frappe.db.delete("GP Reaction", {"reference_name": str(reply.name)})
		frappe.delete_doc("GP Comment", reply.name, ignore_permissions=True, force=True)
		self.assertEqual(self.grants(self.member, "nice-reply"), [])


class TestOtherBadges(BadgeTestCase):
	def test_autobiographer_needs_a_bio_and_a_photo(self):
		profile = frappe.get_doc("GP User Profile", {"user": self.member.name})
		profile.db_set("bio", "Ten chars!")
		check_user(self.member.name)
		self.assertNotIn("autobiographer", self.badges(self.member))
		profile.db_set({"bio": "I write about forums.", "image": "/files/me.png"})
		check_user(self.member.name)
		self.assertIn("autobiographer", self.badges(self.member))

	def test_first_mention_comes_from_mentioning_someone_else(self):
		frappe.get_doc(
			doctype="GP Notification",
			type="Mention",
			from_user=self.member.name,
			to_user=self.second_member.name,
			discussion=self.discussion.name,
			message="mentioned you",
		).insert(ignore_permissions=True)
		check_user(self.member.name)
		self.assertIn("first-mention", self.badges(self.member))

	def test_enthusiast_needs_days_in_a_row(self):
		start = date(2026, 1, 1)
		gap = [start + timedelta(days=day) for day in (0, 1, 3, 4)]
		add_visit_days(self.member.name, gap)
		with patch("gameplan.badges.rules.ENTHUSIAST", (("enthusiast", 3),)):
			check_user(self.member.name)
			self.assertNotIn("enthusiast", self.badges(self.member))
			add_visit_days(self.member.name, [start + timedelta(days=2)])
			check_user(self.member.name)
		[grant] = self.grants(self.member, "enthusiast")
		self.assertEqual(grant.granted_at.date(), start + timedelta(days=3))

	def test_anniversary_is_earned_for_each_year_with_a_post(self):
		joined = utc_now() - timedelta(days=3 * 365 + 10)
		frappe.db.set_value("User", self.member.name, "creation", joined, update_modified=False)
		frappe.db.set_value(
			"GP Discussion",
			self.discussion.name,
			"creation",
			joined + timedelta(days=400),
			update_modified=False,
		)
		check_user(self.member.name)
		self.assertEqual([grant.seq for grant in self.grants(self.member, "anniversary")], [2])

	def test_helper_counts_replies_marked_as_the_solution(self):
		replies = [create_comment(self.discussion, owner=self.second_member) for _ in range(2)]
		with patch("gameplan.badges.rules.HELPER", (("helper", 2),)):
			replies[0].db_set({"highlighted_at": utc_now(), "highlighted_by": self.member.name})
			check_user(self.second_member.name)
			self.assertNotIn("helper", self.badges(self.second_member))
			replies[1].db_set({"highlighted_at": utc_now(), "highlighted_by": self.member.name})
			check_user(self.second_member.name)
		self.assertIn("helper", self.badges(self.second_member))

	def test_reader_needs_a_visit_after_the_last_reply_of_a_long_discussion(self):
		frappe.db.set_value(
			"GP Discussion",
			self.discussion.name,
			{"comments_count": 101, "last_post_at": utc_now() - timedelta(hours=1)},
			update_modified=False,
		)
		visit = frappe.get_doc(
			doctype="GP Discussion Visit",
			discussion=self.discussion.name,
			user=self.outsider.name,
			last_visit=utc_now() - timedelta(hours=2),
		).insert(ignore_permissions=True)
		check_user(self.outsider.name)
		self.assertNotIn("reader", self.badges(self.outsider))
		visit.db_set("last_visit", utc_now())
		check_user(self.outsider.name)
		self.assertIn("reader", self.badges(self.outsider))


class TestQueue(BadgeTestCase):
	def test_a_reaction_queues_both_people_and_the_job_grants_their_badges(self):
		reaction = self.react(self.second_member, self.discussion)
		on_reaction_change(reaction)
		with patch("frappe.db.commit"):
			process_queue()
		self.assertIn("first-like", self.badges(self.second_member))
		self.assertIn("welcome", self.badges(self.member))
		self.assertFalse(frappe.cache.smembers(QUEUE))

	def test_deleting_a_user_deletes_their_badges(self):
		from gameplan.badges import on_user_trash

		self.react(self.second_member, self.discussion)
		check_user(self.member.name)
		self.assertTrue(self.badges(self.member))
		on_user_trash(self.member)
		self.assertEqual(self.badges(self.member), set())


class TestReading(BadgeTestCase):
	def setUp(self):
		super().setUp()
		self.react(self.second_member, self.discussion)
		check_user(self.member.name)
		check_user(self.second_member.name)

	def test_the_badge_list_counts_holders_and_marks_your_own(self):
		with self.as_user(self.member):
			badges = {badge.name: badge for badge in list_badges()["badges"]}
		self.assertEqual(len(badges), 24)
		self.assertEqual((badges["welcome"].holders, badges["welcome"].held), (1, 1))
		self.assertEqual((badges["first-like"].holders, badges["first-like"].held), (1, 0))

	def test_visitors_cannot_read_badges(self):
		with self.as_user("Guest"), self.assertRaises(frappe.PermissionError):
			list_badges()

	def test_a_holder_shows_the_post_only_to_people_who_can_open_it(self):
		with self.as_user(self.second_member):
			[holder] = badge_holders("welcome")["holders"]
		self.assertEqual(holder["post"]["discussion"], str(self.discussion.name))
		with self.as_user(self.guest):
			[holder] = badge_holders("welcome")["holders"]
		self.assertNotIn("post", holder)

	def test_favourites_are_your_own_badges_and_at_most_three(self):
		with self.as_user(self.member):
			result = set_favorites(["welcome"])
			self.assertEqual((result["badges"][0].name, result["badges"][0].is_favorite), ("welcome", 1))
			# The hover card shows every favourite.
			self.assertEqual([b.name for b in favorites([self.member.name])[self.member.name]], ["welcome"])
			with self.assertRaises(frappe.ValidationError):
				set_favorites(["first-like"])
			with self.assertRaises(frappe.ValidationError):
				set_favorites(["welcome", "reader", "helper", "admired"])

	def test_the_profile_has_a_badges_card_only_while_there_is_a_badge_to_show(self):
		from gameplan.gameplan.doctype.gp_user_profile.gp_user_profile import (
			get_profile_bento_default_cards,
		)

		profile = frappe.get_doc("GP User Profile", {"user": self.member.name})
		frappe.db.delete("GP User Badge", {"user": self.member.name})

		def card_ids():
			with self.as_user(self.second_member):
				return [card["id"] for card in get_profile_bento_default_cards(profile)]

		self.assertNotIn("badges", card_ids())
		check_user(self.member.name)
		self.assertIn("badges", card_ids())
		self.turn_on(0)
		self.assertNotIn("badges", card_ids())

	def test_a_revoked_badge_is_hidden_logged_and_not_earned_again(self):
		with self.as_user(self.member), self.assertRaises(frappe.PermissionError):
			revoke_badge(self.member.name, "welcome", "Spam likes")
		with self.as_user(self.admin):
			revoke_badge(self.member.name, "welcome", "Spam likes")
		check_user(self.member.name)
		with self.as_user(self.member):
			self.assertEqual(user_badges(self.member.name)["badges"], [])
		log = frappe.get_last_doc("GP Moderation Log", {"user": self.member.name})
		self.assertEqual((log.action, log.title, log.reason), ("Badge Revoked", "Welcome", "Spam likes"))

	def test_a_global_admin_grants_a_badge_by_hand_but_not_a_per_post_one(self):
		with self.as_user(self.admin):
			grant_badge(self.outsider.name, "reader", "Read the whole archive")
			with self.assertRaises(frappe.ValidationError):
				grant_badge(self.outsider.name, "nice-reply", "Nice")
			with self.assertRaises(frappe.ValidationError):
				grant_badge(self.outsider.name, "reader", "Twice")
		self.assertIn("reader", self.badges(self.outsider))
		self.assertEqual(self.notifications(self.outsider), ["You earned the Reader badge."])

	def test_a_manual_grant_after_bulk_grants_gets_its_own_name(self):
		# Bulk-inserted grants once used up names the next normal insert would pick.
		with self.as_user(self.admin):
			grant_badge(self.member.name, "reader", "Read the archive")
			grant_badge(self.second_member.name, "reader", "Read the archive")
		self.assertIn("reader", self.badges(self.member))
		self.assertIn("reader", self.badges(self.second_member))


class TestDiscourseImport(BadgeTestCase):
	def test_grants_of_ported_badges_are_mapped_and_the_rest_skipped(self):
		from gameplan import migrate_from_discourse as importer
		from gameplan.migrate_from_discourse import badges as step

		reply = create_comment(self.discussion, owner=self.member)
		granted_at = utc_now() - timedelta(days=30)
		row = frappe._dict(seq=0, is_favorite=False, granted_at=granted_at, post_id=None)
		rows = [
			{**row, "id": 1, "badge_id": 5, "user_id": 10, "is_favorite": True},  # Welcome
			{**row, "id": 2, "badge_id": 6, "user_id": 10, "post_id": 70, "topic_id": 7, "post_number": 2},
			{**row, "id": 3, "badge_id": 18, "user_id": 10, "post_id": 69, "topic_id": 7, "post_number": 1},
			{**row, "id": 4, "badge_id": 24, "user_id": 10, "seq": 1},  # second Anniversary
			{**row, "id": 5, "badge_id": 5, "user_id": 99},  # a person not imported
			{**row, "id": 6, "badge_id": 6, "user_id": 10, "post_id": 71, "topic_id": 7, "post_number": 3},
		]
		mapped = {
			("users", 10): self.member.name,
			("topics", 7): self.discussion.name,
			("posts", 70): reply.name,
		}
		pages = iter([[frappe._dict(r) for r in rows], []])
		importer.config.update(importer.OPTIONS, dry_run=False, batch_size=500)
		with (
			patch.object(step, "run_query", lambda *args: next(pages)),
			patch.object(step, "get_mapped", lambda table, id: mapped.get((table, id))),
			patch.object(step, "load_id_map"),
			patch.object(step, "log"),
			patch("frappe.db.commit"),
		):
			step.migrate_badges()

		self.assertEqual(self.grants(self.member, "welcome")[0].granted_at, granted_at)
		self.assertEqual(
			[(g.reference_doctype, g.reference_name) for g in self.grants(self.member, "nice-reply")],
			[("GP Comment", str(reply.name))],
		)
		self.assertEqual(self.grants(self.member, "nice-topic")[0].reference_name, str(self.discussion.name))
		self.assertEqual([g.seq for g in self.grants(self.member, "anniversary")], [2])
		self.assertEqual(frappe.db.get_value("GP User Badge", {"badge": "welcome"}, "is_favorite"), 1)
		self.assertEqual(self.notifications(self.member), [])
