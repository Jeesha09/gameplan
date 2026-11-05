from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import frappe

from gameplan.approvals import submit
from gameplan.community_bans import banned_communities, is_banned
from gameplan.restriction_queries import account_history, account_suspensions, my_bans
from gameplan.restrictions import require_not_suspended, revoke_sessions, set_restriction, state, utc_now
from gameplan.tests.base import GameplanTestCase
from gameplan.tests.fixtures import create_community, create_discussion, create_space


class TestSiteSilence(GameplanTestCase):
	def setUp(self):
		super().setUp()
		self.enqueue = self.enterContext(patch("frappe.enqueue"))
		self.community = create_community("Silence", members=[self.outsider])
		self.other = create_community("Silence elsewhere", members=[self.outsider])
		self.post = create_discussion("Quiet please", create_space("Silence", self.other))

	def silence(self, **kwargs):
		return set_restriction(self.outsider.name, 1, "Cooling off", kind="Silence", **kwargs)

	def actions(self):
		return frappe.get_all(
			"GP Moderation Log", filters={"user": self.outsider.name}, pluck="action", order_by="creation asc"
		)

	def reply(self):
		with self.as_user(self.outsider):
			return frappe.get_doc(
				doctype="GP Comment",
				reference_doctype="GP Discussion",
				reference_name=str(self.post.name),
				content="Still here",
			).insert()

	def test_silence_blocks_participation_everywhere_but_keeps_sign_in(self):
		self.silence()
		self.assertTrue(is_banned(self.community.name, self.outsider.name))
		self.assertTrue(is_banned(self.other.name, self.outsider.name))
		self.assertEqual(banned_communities(self.outsider.name), [""])
		require_not_suspended(SimpleNamespace(user=self.outsider.name))
		with self.assertRaises(frappe.PermissionError):
			self.reply()
		with self.as_user(self.outsider), self.assertRaises(frappe.PermissionError):
			submit("GP Comment", "silenced", "Let me in", discussion=str(self.post.name))
		with self.as_user(self.outsider):
			self.assertEqual([(row.community, row.reason) for row in my_bans()], [("", "Cooling off")])
		enqueued = [call.args[0] for call in self.enqueue.call_args_list if call.args]
		self.assertNotIn(revoke_sessions, enqueued)
		self.assertEqual(account_suspensions()["items"][0].kind, "Silence")

	def test_one_site_restriction_switches_between_silence_and_suspension(self):
		self.silence()
		set_restriction(self.outsider.name, 1, "Escalated", kind="Suspend")
		with self.assertRaises(frappe.AuthenticationError):
			require_not_suspended(SimpleNamespace(user=self.outsider.name))
		set_restriction(self.outsider.name, 1, "Back to quiet", kind="Silence")
		require_not_suspended(SimpleNamespace(user=self.outsider.name))
		set_restriction(self.outsider.name, 0, "Served")
		self.assertFalse(is_banned(self.community.name, self.outsider.name))
		self.reply()
		self.assertEqual(self.actions(), ["Silence", "Suspend", "Silence", "Lift Silence"])
		history = [row.action for row in account_history(self.outsider.name)["items"]]
		self.assertEqual(history, ["Lift Silence", "Silence", "Suspend", "Silence"])

	def test_silence_expires_on_the_next_check(self):
		self.silence(duration_seconds=3600)
		row = state(self.outsider.name)
		frappe.db.set_value("GP User Restriction", row.name, "expires_at", utc_now() - timedelta(seconds=1))
		frappe.local.request_cache.clear()
		self.assertFalse(is_banned(self.community.name, self.outsider.name))
		self.reply()

	def test_community_staff_and_community_scope_are_refused(self):
		self.community.set_member_moderator(self.outsider.name, 1)
		with self.assertRaisesRegex(frappe.ValidationError, "moderator roles"):
			self.silence()
		self.community.set_member_moderator(self.outsider.name, 0)
		self.silence()
		with self.assertRaisesRegex(frappe.ValidationError, "Silence or Suspend"):
			set_restriction(self.outsider.name, 1, "Wrong scope", self.community.name, kind="Silence")
