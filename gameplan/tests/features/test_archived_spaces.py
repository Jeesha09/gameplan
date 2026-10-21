# Copyright (c) 2026, Frappe Technologies Pvt Ltd and Contributors
# See license.txt

"""Archived spaces freeze content mutations while remaining readable."""

import frappe

from gameplan.tests.base import GameplanTestCase
from gameplan.tests.fixtures import (
	create_comment,
	create_community,
	create_discussion,
	create_space,
)


class ArchivedSpaceTestCase(GameplanTestCase):
	def setUp(self):
		super().setUp()
		self.community = create_community(
			"Archived Content Community",
			members=[self.member, self.second_member],
		)
		self.space = create_space("Archived Content Space", self.community)
		self.discussion = create_discussion("Existing Discussion", self.space, owner=self.member)
		self.comment = create_comment(self.discussion, content="Existing comment", owner=self.member)
		self.space.reload()
		self.space.archive()


class TestArchivedCommentMutations(ArchivedSpaceTestCase):
	def test_cannot_add_a_comment_to_a_discussion_in_an_archived_space(self):
		with self.as_user(self.member):
			with self.assertRaisesRegex(
				frappe.ValidationError,
				r"Space Archived Content Space is archived\. Cannot add comments\.",
			):
				frappe.get_doc(
					doctype="GP Comment",
					reference_doctype="GP Discussion",
					reference_name=self.discussion.name,
					content="Blocked discussion comment",
				).insert()

	def test_cannot_edit_a_comment_in_an_archived_space(self):
		with self.as_user(self.member):
			comment = frappe.get_doc("GP Comment", self.comment.name)
			comment.content = "Blocked edit"
			with self.assertRaisesRegex(
				frappe.ValidationError,
				r"Space Archived Content Space is archived\. Cannot edit comments\.",
			):
				comment.save()

		self.comment.reload()
		self.assertEqual(self.comment.content, "Existing comment")

	def test_can_react_to_a_comment_in_an_archived_space(self):
		with self.as_user(self.second_member):
			comment = frappe.get_doc("GP Comment", self.comment.name)
			comment.react(operations=[{"emoji": "\U0001f44d", "operation": "add"}])

		self.comment.reload()
		self.assertTrue(
			any(
				reaction.user == self.second_member.name and reaction.emoji == "\U0001f44d"
				for reaction in self.comment.get_reactions()
			)
		)

	def test_can_comment_in_a_non_archived_space(self):
		live_space = create_space("Live Comment Space", self.community)
		discussion = create_discussion("Live Discussion", live_space, owner=self.member)

		with self.as_user(self.member):
			comment = create_comment(discussion, content="Allowed comment")

		self.assertTrue(comment.name)

	def test_unarchiving_restores_commenting(self):
		self.space.unarchive()

		with self.as_user(self.member):
			comment = create_comment(self.discussion, content="Comment after unarchive")

		self.assertTrue(comment.name)


class TestArchivedContentReadsAndRecovery(ArchivedSpaceTestCase):
	def test_deleting_an_archived_space_cascades_to_its_discussion(self):
		frappe.delete_doc("GP Project", self.space.name)

		self.assertFalse(frappe.db.exists("GP Project", self.space.name))
		self.assertFalse(frappe.db.exists("GP Discussion", self.discussion.name))

	def test_preexisting_discussion_creation_guard_rejects_an_archived_space(self):
		# This behavior predates the archived-content enforcement and does not claim
		# coverage for archived discussion edits or deletes.
		with self.assertRaisesRegex(frappe.ValidationError, "archived"):
			create_discussion("Blocked Discussion", self.space)

	def test_preexisting_discussion_creation_guard_tolerates_a_missing_space(self):
		missing_space = create_space("Deleted Space", self.community)
		frappe.db.delete("GP Project", {"name": missing_space.name})
		discussion = frappe.get_doc(
			doctype="GP Discussion",
			title="Orphaned Discussion",
			project=missing_space.name,
			content="Test content",
		)

		discussion.before_insert()
