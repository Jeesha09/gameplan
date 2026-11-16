from unittest.mock import patch

import frappe

from gameplan.auto_hide import get_settings, save_settings
from gameplan.reporting import detail, queue, resolve, submit
from gameplan.tests.base import GameplanTestCase
from gameplan.tests.fixtures import (
	create_comment,
	create_community,
	create_discussion,
	create_member,
	create_space,
)
from gameplan.trust_levels import BASIC, LEADER, MEMBER, NEW, REGULAR, removed
from gameplan.trust_levels import save_settings as save_trust_settings


class AutoHideTestCase(GameplanTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.cache.delete_keys, "gameplan:trust:")
		self.addCleanup(frappe.clear_cache, doctype="GP Trust Settings")
		self.reporters = [
			create_member(f"reporter{index}@example.com", f"Reporter {index}") for index in range(4)
		]
		self.community = create_community(
			"Auto-hide",
			members=[self.member, self.outsider, *self.reporters],
			admins=[self.second_member],
		)
		self.community.set_member_moderator(self.outsider.name, 1)
		self.space = create_space("Auto-hide Space", self.community)
		self.discussion = create_discussion(
			"Buy cheap pills", self.space, content="<p>Spam body</p>", owner=self.member
		)
		self.levels(True)
		self.switch(True)

	def levels(self, enabled):
		with self.as_user(self.admin), patch("frappe.enqueue"):
			save_trust_settings(int(enabled))

	def switch(self, enabled, threshold=6):
		with self.as_user(self.second_member):
			return save_settings(self.community.name, int(enabled), threshold)

	def give_level(self, user, level):
		if frappe.db.exists("GP Trust Level", user.name):
			frappe.db.set_value("GP Trust Level", user.name, "level", level)
		else:
			frappe.get_doc(doctype="GP Trust Level", user=user.name, level=level).insert(
				ignore_permissions=True
			)

	def report(self, user, doc=None, reason="Spam"):
		doc = doc or self.discussion
		with self.as_user(user):
			name = submit(doc.doctype, str(doc.name), reason, "Other note" if reason == "Other" else "")[
				"name"
			]
		return frappe.db.get_value("GP Report", name, ["review", "weight"], as_dict=True)

	def hide_with_regulars(self, doc=None):
		for user in self.reporters[:2]:
			self.give_level(user, REGULAR)
		self.report(self.reporters[0], doc)
		return self.report(self.reporters[1], doc).review

	def post(self, doc=None):
		doc = doc or self.discussion
		return frappe.db.get_value(
			doc.doctype, doc.name, ["hidden_at", "auto_hidden", "spam_removed_at", "content"], as_dict=True
		)

	def decide(self, review, decision, note="Reviewed"):
		with self.as_user(self.outsider):
			version = detail(self.community.name, review)["current"]["version"]
			resolve(self.community.name, review, decision, note, version)

	def moderation_notices(self, user=None):
		return frappe.get_all(
			"GP Notification",
			filters={"to_user": (user or self.member).name, "type": "Moderation"},
			pluck="message",
			order_by="creation asc",
		)


class TestWeights(AutoHideTestCase):
	def test_reports_hide_a_post_when_their_level_weights_reach_the_threshold(self):
		self.give_level(self.reporters[0], MEMBER)
		self.give_level(self.reporters[1], BASIC)
		self.give_level(self.reporters[2], REGULAR)
		weights = [self.report(user).weight for user in self.reporters[:2]]
		self.assertEqual(weights, [2, 1])
		self.assertFalse(self.post().hidden_at)

		review = self.report(self.reporters[2]).review
		post = self.post()
		self.assertTrue(post.hidden_at)
		self.assertEqual(post.auto_hidden, 1)
		self.assertIn("hidden after member reports", post.content)
		row = frappe.db.get_value(
			"GP Review", review, ["report_weight", "auto_hidden", "status"], as_dict=True
		)
		self.assertEqual((row.report_weight, row.auto_hidden, row.status), (6, 1, "Pending"))

	def test_new_and_leader_weights_follow_the_level_table(self):
		self.give_level(self.reporters[0], NEW)
		self.give_level(self.reporters[1], LEADER)
		self.assertEqual(self.report(self.reporters[0]).weight, 1)
		self.assertEqual(self.report(self.reporters[1]).weight, 3)

	def test_a_reporter_without_a_level_row_is_worked_out_when_they_report(self):
		self.assertFalse(frappe.db.exists("GP Trust Level", self.reporters[0].name))
		self.assertEqual(self.report(self.reporters[0]).weight, 1)
		self.assertTrue(frappe.db.exists("GP Trust Level", self.reporters[0].name))

	def test_community_staff_and_global_admins_count_three(self):
		self.assertEqual(self.report(self.outsider).weight, 3)
		self.assertEqual(self.report(self.admin).weight, 3)
		self.assertTrue(self.post().auto_hidden)

	def test_only_spam_and_abuse_reports_count(self):
		self.give_level(self.reporters[0], REGULAR)
		self.give_level(self.reporters[1], REGULAR)
		self.assertEqual(self.report(self.reporters[0], reason="Off-topic").weight, 0)
		self.assertEqual(self.report(self.reporters[1], reason="Other").weight, 0)
		self.assertFalse(self.post().hidden_at)
		self.assertEqual(self.report(self.reporters[2], reason="Abuse/inappropriate").weight, 1)

	def test_a_lower_threshold_applies_from_the_next_report(self):
		self.switch(True, threshold=3)
		self.give_level(self.reporters[0], REGULAR)
		self.report(self.reporters[0])
		self.assertTrue(self.post().auto_hidden)

	def test_replies_hide_at_the_same_threshold(self):
		reply = create_comment(self.discussion, content="<p>Spam reply</p>", owner=self.member)
		self.hide_with_regulars(reply)
		post = self.post(reply)
		self.assertTrue(post.hidden_at and post.auto_hidden)
		self.assertFalse(self.post().hidden_at)


class TestWhenAutoHideIsOff(AutoHideTestCase):
	def test_reports_filed_while_the_switch_is_off_never_count(self):
		self.switch(False)
		self.give_level(self.reporters[0], REGULAR)
		self.give_level(self.reporters[1], REGULAR)
		self.assertEqual(self.report(self.reporters[0]).weight, 0)
		self.switch(True)
		review = self.report(self.reporters[1]).review
		self.assertEqual(frappe.db.get_value("GP Review", review, "report_weight"), 3)
		self.assertFalse(self.post().hidden_at)

	def test_turning_trust_levels_off_pauses_auto_hide_and_keeps_its_setting(self):
		self.levels(False)
		self.assertEqual(self.report(self.reporters[0]).weight, 0)
		with self.as_user(self.outsider):
			settings = get_settings(self.community.name)
		self.assertEqual((settings["enabled"], settings["levels_enabled"]), (1, False))
		# Saving the dialog again keeps the paused switch on.
		self.assertEqual(self.switch(True)["enabled"], 1)

	def test_auto_hide_cannot_be_turned_on_while_levels_are_off(self):
		self.switch(False)
		self.levels(False)
		with self.assertRaisesRegex(frappe.ValidationError, "needs trust levels"):
			self.switch(True)

	def test_posts_by_community_staff_are_never_hidden_automatically(self):
		staff_post = create_discussion("Staff post", self.space, owner=self.outsider)
		review = self.hide_with_regulars(staff_post)
		self.assertFalse(self.post(staff_post).hidden_at)
		self.assertEqual(frappe.db.get_value("GP Review", review, "status"), "Pending")


class TestDecisions(AutoHideTestCase):
	def test_the_system_hides_the_post_and_tells_the_author_without_naming_reporters(self):
		self.hide_with_regulars()
		log = frappe.get_last_doc(
			"GP Moderation Log", filters={"discussion": str(self.discussion.name), "action": "Auto Hide"}
		)
		self.assertEqual(log.owner, "Administrator")
		self.assertEqual(log.title, "Buy cheap pills")
		[notice] = self.moderation_notices()
		self.assertIn("Buy cheap pills", notice)
		self.assertNotIn("Reporter", notice)

	def test_review_detail_shows_the_hidden_original_and_each_weight(self):
		review = self.hide_with_regulars()
		with self.as_user(self.outsider):
			data = detail(self.community.name, review)
		self.assertEqual(data["current"]["content"], "<p>Spam body</p>")
		self.assertEqual(data["current"]["title"], "Buy cheap pills")
		self.assertEqual(data["review"]["report_weight"], 6)
		self.assertEqual(data["auto_hide"], {"active": True, "threshold": 6})
		self.assertEqual([row.weight for row in data["reports"]], [3, 3])

	def test_hidden_posts_come_first_in_the_pending_queue(self):
		other = create_discussion("Later report", self.space, owner=self.member)
		review = self.hide_with_regulars()
		self.report(self.reporters[2], other)
		with self.as_user(self.outsider):
			items = queue(self.community.name)["items"]
		self.assertEqual(items[0].name, review)
		self.assertEqual(items[0].auto_hidden, 1)

	def test_dismiss_restores_the_post_and_it_never_hides_automatically_again(self):
		review = self.hide_with_regulars()
		self.decide(review, "Dismiss", "Not spam")
		post = self.post()
		self.assertFalse(post.hidden_at or post.auto_hidden)
		self.assertEqual(post.content, "<p>Spam body</p>")
		self.assertEqual(frappe.db.get_value("GP Review", review, "decision"), "Dismiss")
		self.assertIn("made it visible again", self.moderation_notices()[-1])

		self.give_level(self.reporters[2], REGULAR)
		self.give_level(self.reporters[3], REGULAR)
		self.report(self.reporters[2])
		self.report(self.reporters[3])
		self.assertFalse(self.post().hidden_at)

	def test_hide_keeps_the_post_hidden_and_then_counts_against_the_author(self):
		review = self.hide_with_regulars()
		since = frappe.utils.add_days(frappe.utils.now(), -1)
		self.assertEqual(removed(self.member.name, 5, since), 0)
		self.decide(review, "Hide", "Spam confirmed")
		post = self.post()
		self.assertTrue(post.hidden_at)
		self.assertEqual(post.auto_hidden, 0)
		self.assertIn("removed by a moderator", post.content)
		self.assertEqual(removed(self.member.name, 5, since), 1)
		self.assertEqual(len(self.moderation_notices()), 1)

	def test_uphold_keeps_the_post_hidden(self):
		review = self.hide_with_regulars()
		self.decide(review, "Uphold")
		self.assertTrue(self.post().hidden_at)
		self.assertEqual(self.post().auto_hidden, 0)

	def test_delete_spam_removes_the_post_as_spam(self):
		review = self.hide_with_regulars()
		self.decide(review, "Delete Spam", "Spam")
		post = self.post()
		self.assertTrue(post.spam_removed_at)
		self.assertFalse(post.hidden_at or post.auto_hidden)
		# The original survives both removals, so a restore brings the real post back.
		with self.as_user(self.outsider):
			frappe.get_doc("GP Discussion", self.discussion.name).restore()
		self.assertEqual(self.post().content, "<p>Spam body</p>")

	def test_restoring_from_the_post_closes_the_review_with_the_reason(self):
		review = self.hide_with_regulars()
		with self.as_user(self.outsider):
			frappe.get_doc("GP Discussion", self.discussion.name).restore("Fine after all")
		row = frappe.db.get_value("GP Review", review, ["status", "decision", "decision_note"], as_dict=True)
		self.assertEqual(
			(row.status, row.decision, row.decision_note), ("Resolved", "Dismiss", "Fine after all")
		)
		self.assertIn("made it visible again", self.moderation_notices()[-1])

	def test_editing_does_not_unhide_the_post(self):
		self.hide_with_regulars()
		with self.as_user(self.member), self.assertRaises(frappe.PermissionError):
			doc = frappe.get_doc("GP Discussion", self.discussion.name)
			doc.content = "<p>Edited</p>"
			doc.save()


class TestSettings(AutoHideTestCase):
	def test_only_community_admins_change_the_switch_and_moderators_read_it(self):
		with self.as_user(self.outsider):
			self.assertFalse(get_settings(self.community.name)["can_edit"])
			with self.assertRaises(frappe.PermissionError):
				save_settings(self.community.name, 0, 6)
		with self.as_user(self.member), self.assertRaises(frappe.PermissionError):
			get_settings(self.community.name)

	def test_the_threshold_stays_between_three_and_thirty(self):
		for value in (2, 31):
			with self.assertRaisesRegex(frappe.ValidationError, "from 3 to 30"):
				self.switch(True, threshold=value)
		self.assertEqual(self.switch(True, threshold=30)["threshold"], 30)


class TestMoves(AutoHideTestCase):
	def test_a_moved_discussion_keeps_its_weight_and_is_checked_in_its_new_community(self):
		self.switch(False)
		self.switch(True)
		self.give_level(self.reporters[0], REGULAR)
		self.give_level(self.reporters[1], REGULAR)
		self.switch(True, threshold=30)
		self.report(self.reporters[0])
		self.report(self.reporters[1])
		self.assertFalse(self.post().hidden_at)

		target = create_community("Strict", members=[self.member], admins=[self.second_member])
		with self.as_user(self.second_member):
			save_settings(target.name, 1, 6)
		space = create_space("Strict Space", target)
		discussion = frappe.get_doc("GP Discussion", self.discussion.name)
		discussion.project = space.name
		discussion.save(ignore_permissions=True)
		self.assertTrue(self.post().auto_hidden)
