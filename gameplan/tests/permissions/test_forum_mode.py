# Copyright (c) 2026, Frappe Technologies Pvt Ltd and Contributors
# See license.txt

"""Forum mode: only trusted members manage other people's posts (D136)."""

from unittest.mock import patch

import frappe

from gameplan.tests.base import GameplanTestCase
from gameplan.tests.fixtures import (
	create_comment,
	create_community,
	create_discussion,
	create_page,
	create_space,
)
from gameplan.trust_levels import LEADER, REGULAR, set_level
from gameplan.trust_levels import save_settings as save_trust_settings


class ForumModeTestCase(GameplanTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.clear_cache, doctype="GP Settings")
		self.addCleanup(frappe.clear_cache, doctype="GP Trust Settings")
		self.addCleanup(frappe.cache.delete_keys, "gameplan:trust:")
		self.community = create_community(
			"Forum", members=[self.member, self.second_member, self.outsider, self.guest]
		)
		self.space = create_space("Forum Space", self.community)
		self.other_space = create_space("Other Space", self.community)
		self.thread = create_discussion("Thread", self.space, owner=self.second_member)
		self.forum_mode(True)

	def forum_mode(self, on):
		frappe.db.set_single_value("GP Settings", "restrict_content_management", int(on))
		frappe.clear_cache(doctype="GP Settings")

	def levels(self, **levels):
		with self.as_user(self.admin), patch("frappe.enqueue"):
			save_trust_settings(1)
			for user, level in levels.items():
				set_level(getattr(self, user).name, level, "Test")

	def act(self, user, method, *args, doc=None):
		with self.as_user(user):
			target = frappe.get_doc("GP Discussion", (doc or self.thread).name)
			return getattr(target, method)(*args)

	def edit(self, user, doc=None, **values):
		doc = doc or self.thread
		with self.as_user(user):
			target = frappe.get_doc(doc.doctype, doc.name)
			target.update(values)
			return target.save()

	def reply(self, user):
		with self.as_user(user):
			return frappe.get_doc(
				doctype="GP Comment",
				reference_doctype="GP Discussion",
				reference_name=self.thread.name,
				content="<p>A reply</p>",
			).insert()

	def refused(self, call, *args, **kwargs):
		with self.assertRaises(frappe.PermissionError):
			call(*args, **kwargs)


class TestOff(ForumModeTestCase):
	def test_every_member_manages_every_post(self):
		self.forum_mode(False)
		self.edit(self.member, content="<p>Edited by another member</p>", title="Retitled")
		self.act(self.member, "close_discussion")
		self.act(self.member, "reopen_discussion")
		self.act(self.member, "pin_discussion", "Space")
		self.act(self.member, "move_to_project", self.other_space.name)


class TestMembers(ForumModeTestCase):
	def test_a_member_cannot_manage_someone_elses_discussion(self):
		self.refused(self.edit, self.member, content="<p>Rewritten</p>")
		self.refused(self.edit, self.member, title="Retitled")
		self.refused(self.act, self.member, "close_discussion")
		self.refused(self.act, self.member, "pin_discussion", "Space")
		self.refused(self.act, self.member, "move_to_project", self.other_space.name)

	def test_a_member_can_still_reply_and_react(self):
		self.reply(self.member)
		with self.as_user(self.member):
			frappe.get_doc("GP Discussion", self.thread.name).react(
				operations=[{"emoji": "👍", "operation": "add"}]
			)

	def test_a_member_cannot_edit_someone_elses_reply(self):
		reply = create_comment(self.thread, owner=self.second_member)
		self.refused(self.edit, self.member, doc=reply, content="<p>Rewritten</p>")

	def test_pages_stay_editable_by_every_member(self):
		page = create_page("Notes", self.space, owner=self.second_member)
		self.edit(self.member, doc=page, content="<p>Added a line</p>")


class TestAuthors(ForumModeTestCase):
	def test_the_author_edits_moves_and_closes_their_own_discussion_but_cannot_pin_it(self):
		self.edit(self.second_member, content="<p>Fixed a typo</p>", title="Better title")
		self.act(self.second_member, "close_discussion")
		self.act(self.second_member, "reopen_discussion")
		self.act(self.second_member, "move_to_project", self.other_space.name)
		self.refused(self.act, self.second_member, "pin_discussion", "Space")

	def test_nobody_but_trusted_members_replies_in_a_closed_discussion(self):
		self.act(self.second_member, "close_discussion")
		with self.assertRaisesRegex(frappe.ValidationError, "closed discussion"):
			self.reply(self.second_member)


class TestRegular(ForumModeTestCase):
	def test_a_regular_retitles_and_moves_but_does_not_edit_close_or_pin(self):
		self.levels(member=REGULAR)
		self.edit(self.member, title="Clearer title")
		self.act(self.member, "move_to_project", self.other_space.name)
		self.refused(self.edit, self.member, content="<p>Rewritten</p>")
		self.refused(self.act, self.member, "close_discussion")
		self.refused(self.act, self.member, "pin_discussion", "Space")

	def test_a_regular_retitles_through_the_editor_and_the_body_is_kept(self):
		from gameplan.watched_word_edits import submit

		self.levels(member=REGULAR)
		thread = frappe.get_doc("GP Discussion", self.thread.name)
		with self.as_user(self.member):
			submit("GP Discussion", str(thread.name), str(thread.modified), "<p>Rewritten</p>", "New title")
		saved = frappe.get_doc("GP Discussion", thread.name)
		self.assertEqual((saved.title, saved.content), ("New title", thread.content))

	def test_levels_off_takes_the_regular_powers_away(self):
		self.levels(member=REGULAR)
		with self.as_user(self.admin), patch("frappe.enqueue"):
			save_trust_settings(0)
		self.refused(self.edit, self.member, title="Retitled")


class TestTrusted(ForumModeTestCase):
	def assert_manages(self, user):
		self.edit(user, content="<p>Edited by a trusted member</p>")
		self.act(user, "pin_discussion", "Space")
		self.act(user, "unpin_discussion")
		self.act(user, "close_discussion")
		self.reply(user)
		self.act(user, "reopen_discussion")
		reply = create_comment(self.thread, owner=self.second_member)
		self.edit(user, doc=reply, content="<p>Edited reply</p>")

	def test_a_leader_manages_every_post(self):
		self.levels(member=LEADER)
		self.assert_manages(self.member)

	def test_community_staff_manage_every_post(self):
		self.community.set_member_moderator(self.member.name, 1)
		self.assert_manages(self.member)

	def test_global_admins_manage_every_post(self):
		self.assert_manages(self.admin)

	def test_guests_never_manage_posts(self):
		self.levels(guest=LEADER)
		self.refused(self.act, self.guest, "close_discussion")
