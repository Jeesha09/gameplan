from unittest.mock import patch

import frappe

from gameplan.approval_policy import set_policy
from gameplan.approvals import submit
from gameplan.author_cleanup import run, run_undo, start, undo
from gameplan.moderation_history import history
from gameplan.tests.base import GameplanTestCase
from gameplan.tests.fixtures import create_comment, create_community, create_discussion, create_space


class TestAuthorCleanup(GameplanTestCase):
	def setUp(self):
		super().setUp()
		self.enqueue = self.enterContext(patch("frappe.enqueue"))
		self.community = create_community(
			"Cleanup", admins=[self.member], members=[self.outsider, self.second_member]
		)
		self.other = create_community("Cleanup elsewhere", members=[self.outsider])
		space = create_space("Cleanup", self.community)
		self.spam = create_discussion("Buy now", space, owner=self.outsider)
		self.thread = create_discussion("A real question", space, owner=self.second_member)
		self.reply = create_comment(self.thread, content="<p>Cheap pills</p>", owner=self.outsider)
		self.elsewhere = create_discussion(
			"Buy here too", create_space("Elsewhere", self.other), owner=self.outsider
		)

	def run_jobs(self, actor):
		jobs = [call for call in self.enqueue.call_args_list if call.args and call.args[0] in (run, run_undo)]
		self.enqueue.reset_mock()
		with self.as_user(actor):
			for job in jobs:
				kwargs = {k: v for k, v in job.kwargs.items() if k not in ("queue", "enqueue_after_commit")}
				job.args[0](**kwargs)

	def removed(self, doc):
		return bool(frappe.db.get_value(doc.doctype, doc.name, "spam_removed_at"))

	def cleanup_rows(self, community=None):
		with self.as_user(self.admin):
			rows = history((community or self.community).name, "user", self.outsider.name)["items"]
		return [row for row in rows if row.action in ("Author Cleanup", "Undo Cleanup")]

	def test_moderator_removes_posts_and_rejects_submissions_in_their_community(self):
		set_policy(self.community.name, 100)
		with self.as_user(self.outsider):
			pending = submit("GP Comment", "held", "More spam", discussion=str(self.thread.name))
		with self.as_user(self.member):
			self.assertEqual(start(self.outsider.name, "Spam wave", self.community.name), 1)
		self.run_jobs(self.member)
		self.assertTrue(self.removed(self.spam))
		self.assertTrue(self.removed(self.reply))
		self.assertFalse(self.removed(self.thread))
		self.assertFalse(self.removed(self.elsewhere))
		self.assertEqual(frappe.db.get_value("GP Submission", pending["name"], "status"), "Rejected")
		[row] = self.cleanup_rows()
		self.assertEqual(row.title, "Removed 2 posts. Rejected 1 pending submissions.")
		self.assertFalse(row.undone)

	def test_undo_restores_only_posts_still_removed_by_that_cleanup(self):
		with self.as_user(self.member):
			start(self.outsider.name, "Spam wave", self.community.name)
		self.run_jobs(self.member)
		with self.as_user(self.member):
			frappe.get_doc("GP Comment", self.reply.name).restore()
			undo(self.cleanup_rows()[0].cleanup)
		self.run_jobs(self.member)
		self.assertFalse(self.removed(self.spam))
		self.assertFalse(self.removed(self.reply))
		undo_row, cleanup_row = self.cleanup_rows()
		self.assertEqual(undo_row.title, "Restored 1 posts. Skipped 1 changed since the cleanup.")
		self.assertTrue(cleanup_row.undone)
		with self.as_user(self.member), self.assertRaisesRegex(frappe.ValidationError, "already undone"):
			undo(cleanup_row.cleanup)

	def test_global_admins_clean_up_every_community(self):
		with self.as_user(self.admin):
			self.assertEqual(start(self.outsider.name, "Spam across the site"), 2)
		self.run_jobs(self.admin)
		self.assertTrue(self.removed(self.spam))
		self.assertTrue(self.removed(self.elsewhere))
		self.assertEqual(len(self.cleanup_rows(self.other)), 1)

	def test_scope_and_staff_protections(self):
		for user, community in (
			(self.outsider, self.community.name),
			(self.member, ""),
			(self.member, self.other.name),
		):
			with self.subTest(user=user.name, community=community), self.as_user(user):
				with self.assertRaises(frappe.PermissionError):
					start(self.second_member.name, "Not allowed", community)
		self.community.set_member_moderator(self.second_member.name, 1)
		with self.as_user(self.member), self.assertRaisesRegex(frappe.ValidationError, "staff role"):
			start(self.second_member.name, "A fellow moderator", self.community.name)
		with self.as_user(self.member), self.assertRaises(frappe.ValidationError):
			start(self.outsider.name, " ", self.community.name)
