import frappe

from gameplan.community_bans import set_ban
from gameplan.moderation_activity import activity, mark_seen
from gameplan.reporting import submit
from gameplan.tests.base import GameplanTestCase
from gameplan.tests.fixtures import create_community, create_discussion, create_space


class TestModerationActivity(GameplanTestCase):
	def setUp(self):
		super().setUp()
		self.community = create_community(
			"Activity", admins=[self.member], members=[self.second_member, self.outsider]
		)
		self.community.set_member_moderator(self.second_member.name, 1)
		self.space = create_space("Watched", self.community)
		self.discussion = create_discussion("Busy thread", self.space, owner=self.outsider)

	def activity_for(self, user):
		with self.as_user(user):
			return activity(self.community.name)

	def test_quiet_community_has_nothing_to_show(self):
		self.assertEqual(
			self.activity_for(self.member),
			{"approvals": 0, "reports": 0, "removed": False, "bans": False, "history": False},
		)

	def test_pending_reports_are_counted(self):
		reported = create_discussion("Reported", self.space, owner=self.second_member)
		with self.as_user(self.outsider):
			submit("GP Discussion", str(reported.name), "Spam")
		self.assertEqual(self.activity_for(self.member)["reports"], 1)

	def test_another_moderators_removal_lights_removed_and_history(self):
		with self.as_user(self.second_member):
			self.discussion.reload().hide("Off topic")
		seen = self.activity_for(self.member)
		self.assertTrue(seen["removed"] and seen["history"])
		self.assertFalse(seen["bans"])
		self.assertFalse(self.activity_for(self.second_member)["removed"])

	def test_another_moderators_ban_lights_bans(self):
		with self.as_user(self.second_member):
			set_ban(self.community.name, self.outsider.name, 1, "Spam")
		self.assertTrue(self.activity_for(self.member)["bans"])

	def test_opening_a_tab_clears_its_dot_until_the_next_change(self):
		with self.as_user(self.second_member):
			self.discussion.reload().hide("Off topic")
		with self.as_user(self.member):
			mark_seen(self.community.name, "removed")
		seen = self.activity_for(self.member)
		self.assertFalse(seen["removed"])
		self.assertTrue(seen["history"])
		with self.as_user(self.second_member):
			other = create_discussion("Another", self.space, owner=self.outsider)
			other.hide("Spam")
		self.assertTrue(self.activity_for(self.member)["removed"])

	def test_site_wide_flag_follows_any_moderated_community(self):
		with self.as_user(self.member):
			self.assertFalse(activity()["attention"])
		with self.as_user(self.second_member):
			set_ban(self.community.name, self.outsider.name, 1, "Spam")
		with self.as_user(self.member):
			self.assertTrue(activity()["attention"])

	def test_only_moderators_can_read_or_mark(self):
		with self.as_user(self.outsider):
			self.assertRaises(frappe.PermissionError, activity, self.community.name)
			self.assertRaises(frappe.PermissionError, mark_seen, self.community.name, "bans")
			self.assertFalse(activity()["attention"])
		with self.as_user(self.member):
			self.assertRaises(frappe.ValidationError, mark_seen, self.community.name, "approvals")
