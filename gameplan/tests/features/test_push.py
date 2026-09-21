# Copyright (c) 2026, Frappe Technologies Pvt Ltd and Contributors
# See license.txt

"""The push channel: a mention, quote or comment pushes at once; everything else rides the
batch as one summary; away and the relay switch hold everything. Nothing here talks to a
relay — `PushNotification` is patched throughout."""

from unittest.mock import patch

import frappe
from frappe.utils import now_datetime

from gameplan.notifications import delivery, push
from gameplan.tests.base import GameplanTestCase
from gameplan.tests.features.test_notifications import mention_html
from gameplan.tests.fixtures import _name, create_comment, create_community, create_discussion, create_space


class PushTestCase(GameplanTestCase):
	def setUp(self):
		super().setUp()
		self.community = create_community(
			"Push Community", members=[self.member, self.second_member], admins=[self.admin]
		)
		self.space = create_space("Push Space", self.community)
		with self.as_user(self.member):
			self.discussion = create_discussion("Roadmap", self.space)
		self.set_prefs(self.second_member, notification_channel="Push")
		# The relay is off on a dev site; these tests are about what happens when it is on.
		enabled = patch("gameplan.notifications.push.push_enabled", return_value=True)
		enabled.start()
		self.addCleanup(enabled.stop)
		relay = patch("gameplan.notifications.push.PushNotification")
		self.relay = relay.start()
		self.addCleanup(relay.stop)
		self.sent = self.relay.return_value.send_notification_to_user
		enqueue = patch("gameplan.notifications.push.frappe.enqueue")
		self.enqueue = enqueue.start()
		self.addCleanup(enqueue.stop)

	def set_prefs(self, user, **fields):
		profile = frappe.db.get_value("GP User Profile", {"user": _name(user)}, "name")
		doc = frappe.get_doc("GP User Profile", profile)
		doc.update(fields)
		doc.save(ignore_permissions=True)

	def mention_second_member(self):
		with self.as_user(self.member):
			return create_comment(self.discussion, content=mention_html(self.second_member, "Second Member"))

	def rows_for(self, user):
		return frappe.get_all(
			"GP Notification",
			filters={"to_user": _name(user), "team": self.community.name},
			fields=["name", "type", "read", "push_sent_at", "email_sent_at", "away_period"],
			order_by="creation asc",
		)

	def queued_names(self):
		return [call.kwargs["name"] for call in self.enqueue.call_args_list]


class TestRealtimePush(PushTestCase):
	def test_a_mention_is_queued_and_pushed_with_the_discussion_as_title(self):
		self.mention_second_member()
		row = self.rows_for(self.second_member)[0]
		self.assertEqual(self.queued_names(), [row.name])

		self.assertTrue(push.send_push(row.name))

		self.sent.assert_called_once()
		args, kwargs = self.sent.call_args
		self.assertEqual(args[0], self.second_member.name)
		self.assertEqual(args[1], "Roadmap")
		self.assertIn("mentioned you", args[2])
		self.assertIn(f"/discussion/{self.discussion.name}", kwargs["link"])
		self.assertTrue(self.rows_for(self.second_member)[0].push_sent_at)

	def test_a_comment_on_a_watched_discussion_is_queued(self):
		frappe.get_doc(
			doctype="GP Discussion Subscription",
			user=self.second_member.name,
			discussion=self.discussion.name,
			state="Watch",
		).insert(ignore_permissions=True)
		with self.as_user(self.member):
			create_comment(self.discussion, content="<p>One</p>")
		self.assertEqual(len(self.queued_names()), 1)

	def test_a_new_discussion_is_left_for_the_batch(self):
		frappe.get_doc(
			doctype="GP Space Subscription", user=self.second_member.name, project=self.space.name
		).insert(ignore_permissions=True)
		with self.as_user(self.member):
			create_discussion("Fresh", self.space)
		self.assertEqual(self.queued_names(), [])
		self.assertEqual([r.type for r in self.rows_for(self.second_member)], ["New Discussion"])

	def test_an_in_app_user_gets_no_push(self):
		self.set_prefs(self.second_member, notification_channel="In-app")
		self.mention_second_member()
		self.assertEqual(self.queued_names(), [])

	def test_away_holds_the_push_for_the_card(self):
		self.set_prefs(self.second_member, receive_notifications=0)
		self.mention_second_member()
		self.assertEqual(self.queued_names(), [])
		self.assertTrue(self.rows_for(self.second_member)[0].away_period)

	def test_a_row_read_before_the_job_runs_is_stamped_not_pushed(self):
		self.mention_second_member()
		row = self.rows_for(self.second_member)[0]
		frappe.db.set_value("GP Notification", row.name, "read", 1)

		self.assertFalse(push.send_push(row.name))

		self.sent.assert_not_called()
		self.assertTrue(self.rows_for(self.second_member)[0].push_sent_at)

	def test_outside_active_hours_the_job_leaves_the_row_for_the_closing_batch(self):
		self.mention_second_member()
		row = self.rows_for(self.second_member)[0]
		with patch("gameplan.notifications.push.is_away", return_value="Active hours"):
			self.assertFalse(push.send_push(row.name))
		self.sent.assert_not_called()
		self.assertIsNone(self.rows_for(self.second_member)[0].push_sent_at)

	def test_a_row_is_pushed_once(self):
		self.mention_second_member()
		row = self.rows_for(self.second_member)[0]
		push.send_push(row.name)
		push.send_push(row.name)
		self.sent.assert_called_once()


class TestBatchPush(PushTestCase):
	def top_of_hour(self):
		return now_datetime().replace(minute=0, second=0, microsecond=0)

	def test_the_batch_sends_one_summary_push_and_no_mail(self):
		frappe.get_doc(
			doctype="GP Space Subscription", user=self.second_member.name, project=self.space.name
		).insert(ignore_permissions=True)
		with self.as_user(self.member):
			create_discussion("Fresh", self.space)
			create_discussion("Fresher", self.space)

		with patch("frappe.sendmail") as sendmail:
			delivery.send_batches(self.top_of_hour())

		sendmail.assert_not_called()
		self.sent.assert_called_once()
		self.assertEqual(self.sent.call_args.args[1], "2 new notifications in Gameplan")
		rows = self.rows_for(self.second_member)
		self.assertTrue(all(r.push_sent_at for r in rows))
		self.assertTrue(all(r.email_sent_at is None for r in rows))

	def test_a_row_already_pushed_in_real_time_is_not_pushed_again_by_the_batch(self):
		self.mention_second_member()
		row = self.rows_for(self.second_member)[0]
		push.send_push(row.name)
		self.sent.reset_mock()

		delivery.send_batches(self.top_of_hour())

		self.sent.assert_not_called()

	def test_an_email_user_still_gets_mail_not_push(self):
		self.set_prefs(self.second_member, notification_channel="Email")
		self.mention_second_member()
		with patch("frappe.sendmail") as sendmail:
			delivery.send_batches(self.top_of_hour())
		sendmail.assert_called_once()
		self.sent.assert_not_called()


class TestRelaySwitch(GameplanTestCase):
	def test_push_is_off_without_the_relay(self):
		with patch("gameplan.notifications.push.PushNotification") as relay:
			relay.return_value.is_enabled.return_value = False
			self.assertFalse(push.push_enabled())

	def test_push_is_off_on_a_developer_site_unless_allowed(self):
		with (
			patch("gameplan.notifications.push.PushNotification") as relay,
			patch.dict(frappe.conf, {"developer_mode": 1, "allow_push_in_developer_mode": 0}),
		):
			relay.return_value.is_enabled.return_value = True
			self.assertFalse(push.push_enabled())
			frappe.conf["allow_push_in_developer_mode"] = 1
			self.assertTrue(push.push_enabled())
