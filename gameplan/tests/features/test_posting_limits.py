from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.utils import now_datetime

from gameplan.approval_policy import set_policy
from gameplan.approvals import decide, submit
from gameplan.gameplan.doctype.gp_draft.gp_draft import get_my_drafts, publish_due_drafts
from gameplan.posting_limits import policy, prune, save_settings, settings, status, utc_now
from gameplan.tests.base import GameplanTestCase
from gameplan.tests.fixtures import (
	create_community,
	create_discussion,
	create_poll,
	create_space,
	create_task,
)


class TestPostingLimits(GameplanTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.clear_cache, doctype="GP Posting Settings")
		self.configure(enabled=0)
		self.community = create_community(
			"Posting limits", members=[self.member, self.second_member, self.outsider]
		)
		self.community.set_member_moderator(self.outsider.name, 1)
		self.space = create_space("Posting limits", self.community)
		self.post = create_discussion("An existing discussion", self.space)
		self.now = utc_now()
		self.enterContext(patch("gameplan.posting_limits.utc_now", side_effect=lambda: self.now))

	def configure(self, **values):
		config = dict(enabled=1, discussions_hour=2, discussions_day=3, replies_hour=2, replies_day=3)
		config.update(values)
		with self.as_user("Administrator"):
			return save_settings(**config)

	def reply(self, user=None):
		with self.as_user(user or self.member):
			return frappe.get_doc(
				doctype="GP Comment",
				reference_doctype="GP Discussion",
				reference_name=str(self.post.name),
				content="A reply",
			).insert()

	def wait(self, kind="reply", user=None):
		with self.as_user(user or self.member):
			return status(kind)["retry_after"]

	def test_rolling_windows_and_separate_account_and_kind_allowances(self):
		self.configure()
		self.reply()
		self.now += timedelta(minutes=10)
		self.reply()
		self.assertEqual(self.wait(), 3000)
		self.assertEqual(self.wait("discussion"), 0)
		self.assertEqual(self.wait(user=self.second_member), 0)
		with self.assertRaises(frappe.RateLimitExceededError):
			self.reply()
		self.now += timedelta(minutes=50)
		self.assertEqual(self.wait(), 0)
		self.reply()
		# The longer daily window wins, even though the hourly window also applies.
		self.assertEqual(self.wait(), 82800)
		self.now += timedelta(hours=23)
		self.assertEqual(self.wait(), 0)

	def test_disabled_tracking_deletion_and_policy_changes_do_not_refund(self):
		self.configure(enabled=0)
		reply = self.reply()
		with self.as_user(self.member):
			reply.delete()
		self.configure(replies_hour=1)
		self.assertEqual(self.wait(), 3600)
		self.configure(enabled=0)
		self.assertEqual(self.wait(), 0)
		self.configure(replies_hour=0, replies_day=1)
		self.assertEqual(self.wait(), 86400)
		self.configure(replies_hour=0, replies_day=0)
		self.reply()
		self.assertEqual(self.wait(), 0)

	def test_cross_community_limits_apply_to_community_staff_but_not_global_admins(self):
		self.configure(replies_hour=1)
		self.reply(self.outsider)
		with self.assertRaises(frappe.RateLimitExceededError):
			self.reply(self.outsider)
		other = create_community("Elsewhere", members=[self.outsider])
		post = create_discussion("Another forum", create_space("Elsewhere", other))
		with self.as_user(self.outsider), self.assertRaises(frappe.RateLimitExceededError):
			submit("GP Comment", "elsewhere", "Another reply", discussion=str(post.name))
		self.reply(self.admin)
		self.reply(self.admin)
		self.assertEqual(self.wait(user=self.admin), 0)

	def test_held_submissions_deduplicate_and_publication_never_charges_twice(self):
		self.configure(replies_hour=1)
		set_policy(self.community.name, 100)
		with self.as_user(self.member):
			first = submit("GP Comment", "one", "Pending", discussion=str(self.post.name))
			self.assertEqual(submit("GP Comment", "one", "Pending", discussion=str(self.post.name)), first)
		self.assertEqual(self.wait(), 3600)
		doc = frappe.get_doc("GP Submission", first["name"])
		with self.as_user(self.outsider):
			decide(doc.name, "Approve", str(doc.modified))
		self.assertEqual(frappe.db.count("GP Posting Event", {"user": self.member.name}), 1)
		self.now += timedelta(hours=1)
		with self.as_user(self.member):
			second = submit("GP Comment", "two", "Withdraw me", discussion=str(self.post.name))
			doc = frappe.get_doc("GP Submission", second["name"])
			decide(doc.name, "Withdraw", str(doc.modified))
		self.assertEqual(self.wait(), 3600)

	def test_discussion_drafts_and_edits_are_not_charged(self):
		self.configure(discussions_hour=1)
		with self.as_user(self.member):
			draft = frappe.get_doc(
				doctype="GP Draft",
				type="Discussion",
				mode="New",
				title="Draft",
				project=self.space.name,
				content="Saved draft",
			).insert()
			self.assertEqual(status("discussion")["retry_after"], 0)
			name = draft.publish()
			post = frappe.get_doc("GP Discussion", name)
			post.content = "Edited"
			post.save()
			self.assertEqual(status("discussion")["retry_after"], 3600)
			with self.assertRaises(frappe.RateLimitExceededError):
				submit("GP Discussion", "new", "Body", project=str(self.space.name), title="Another")

	def test_failed_insert_rolls_back_its_charge(self):
		self.configure(replies_hour=1)
		frappe.db.savepoint("invalid_post")
		with self.assertRaises(frappe.ValidationError):
			with self.as_user(self.member):
				frappe.get_doc(
					doctype="GP Comment",
					reference_doctype="GP Discussion",
					reference_name=str(self.post.name),
					content="",
				).insert()
		frappe.db.rollback(save_point="invalid_post")
		self.assertEqual(self.wait(), 0)
		self.reply()

	def test_scheduled_failure_preserves_draft_and_explains_rescheduling(self):
		self.configure(discussions_hour=1)
		with self.as_user(self.member):
			submit("GP Discussion", "first", "Body", project=str(self.space.name), title="Published")
			draft = frappe.get_doc(
				doctype="GP Draft",
				type="Discussion",
				mode="New",
				title="Scheduled",
				project=self.space.name,
				content="Keep this content",
			).insert()
			draft.db_set("scheduled_at", now_datetime() - timedelta(minutes=1))
		publish_due_drafts()
		draft.reload()
		self.assertIsNone(draft.scheduled_at)
		self.assertIn("Posting limit", draft.publication_error)
		self.assertEqual(draft.content, "Keep this content")
		with self.as_user(self.member):
			rows = get_my_drafts()
			self.assertTrue(next(row for row in rows if row["name"] == draft.name)["publication_error"])
			draft.schedule(now_datetime() + timedelta(hours=2))
		self.assertFalse(draft.publication_error)

	def test_settings_and_private_event_permissions(self):
		self.configure()
		for user in (self.member, self.outsider):
			with self.as_user(user), self.assertRaises(frappe.PermissionError):
				settings()
			with self.as_user(user), self.assertRaises(frappe.PermissionError):
				save_settings(0, 1, 1, 1, 1)
		with self.assertRaises(frappe.ValidationError):
			self.configure(replies_day=-1)
		with self.assertRaises(frappe.ValidationError):
			self.configure(replies_day=10001)
		self.reply()
		name = frappe.db.get_value("GP Posting Event", {"user": self.member.name}, "name")
		with self.as_user(self.member), self.assertRaises(frappe.PermissionError):
			frappe.get_doc("GP Posting Event", name).delete()
		with self.as_user("Guest"), self.assertRaises(frappe.PermissionError):
			status("reply")

	def test_queries_are_bounded_to_the_account_and_expired_rows_are_pruned(self):
		self.configure(replies_hour=1, replies_day=0)
		self.reply()
		with self.as_user(self.member), patch.object(frappe.db, "sql", wraps=frappe.db.sql) as sql:
			status("reply")
		queries = [
			str(call.args[0]) for call in sql.call_args_list if "tabGP Posting Event" in str(call.args[0])
		]
		self.assertEqual(len(queries), 1)
		self.assertIn("LIMIT 1", queries[0])
		self.assertIn("user", queries[0])
		self.now += timedelta(days=1)
		prune()
		self.assertFalse(frappe.db.exists("GP Posting Event", {"user": self.member.name}))

	def test_default_policy_and_clock_do_not_depend_on_viewer_timezone(self):
		self.assertEqual(policy()["enabled"], 0)
		self.configure(replies_hour=1)
		self.reply()
		with patch("frappe.utils.get_system_timezone", return_value="America/New_York"):
			self.assertEqual(self.wait(), 3600)

	def test_task_comments_and_polls_do_not_consume_forum_allowances(self):
		self.configure(replies_hour=1)
		with self.as_user(self.member):
			task = create_task("A task", self.space)
			frappe.get_doc(
				doctype="GP Comment",
				reference_doctype="GP Task",
				reference_name=str(task.name),
				content="Task comment",
			).insert()
			create_poll("A poll", self.post)
		self.assertEqual(self.wait(), 0)
		self.reply()
		self.assertEqual(self.wait(), 3600)

	def test_longer_slow_mode_wait_wins_when_both_limits_apply(self):
		from gameplan.slow_mode import set_mode

		self.configure(replies_hour=1)
		set_mode(str(self.post.name), 86400, "Slow this discussion", 0)
		self.reply()
		with self.assertRaisesRegex(frappe.RateLimitExceededError, "Slow mode"):
			self.reply()
