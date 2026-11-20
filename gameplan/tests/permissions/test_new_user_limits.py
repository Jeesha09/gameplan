# Copyright (c) 2026, Frappe Technologies Pvt Ltd and Contributors
# See license.txt

"""Discourse-style limits on Gameplan Guests posting in a space only because it is public."""

from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.utils import now_datetime

from gameplan.new_user_limits import POST_FIELDS, NewUserLimitError
from gameplan.permissions import GUEST_CREATABLE_DOCTYPES
from gameplan.public_access import PUBLIC_ACCESS_CONFIG_KEY
from gameplan.tests.base import GameplanTestCase
from gameplan.tests.fixtures import (
	create_comment,
	create_community,
	create_discussion,
	create_space,
	grant_guest_access,
)
from gameplan.trust_levels import LIMITS
from gameplan.visibility import VISIBILITY_ANONYMOUS

MAX_DISCUSSIONS_IN_FIRST_DAY = LIMITS["new_first_day_discussions"][0]
MAX_REPLIES_IN_FIRST_DAY = LIMITS["new_first_day_replies"][0]
MAX_MEDIA = LIMITS["new_max_media"][0]

IMAGE = '<img src="/files/a.png">'
VIDEO = '<video src="/files/clip.mp4"></video>'
EMOJI = '<img data-emoji="" src="/files/party.png" alt="party">'
LINK = '<a href="https://example.org/{n}">link</a>'
FILE = '<a href="/private/files/report.pdf">report.pdf</a>'
MENTION = '<span data-type="mention" data-id="m{n}@example.com" data-label="M{n}">@M{n}</span>'
EVERYONE = '<span data-type="mention" data-id="_everyone_" data-label="everyone">@everyone</span>'


class NewUserLimitsTestCase(GameplanTestCase):
	def setUp(self):
		super().setUp()
		self.enterContext(patch.dict(frappe.conf, {PUBLIC_ACCESS_CONFIG_KEY: 1}))
		community = create_community("Limits Community", visibility=VISIBILITY_ANONYMOUS)
		self.public_space = create_space("Limits Public", community, visibility=VISIBILITY_ANONYMOUS)
		self.invited_space = create_space("Limits Invited", community, visibility=VISIBILITY_ANONYMOUS)
		grant_guest_access(self.guest, self.invited_space)
		self.thread = create_discussion("Limits Thread", self.public_space, owner=self.member)
		self.account_age(hours=1)
		self.addCleanup(frappe.clear_cache, doctype="GP Trust Settings")

	def set_limits(self, **values):
		for field, value in values.items():
			frappe.db.set_single_value("GP Trust Settings", field, value)
		frappe.clear_cache(doctype="GP Trust Settings")

	def account_age(self, hours):
		created = now_datetime() - timedelta(hours=hours)
		frappe.db.set_value("User", self.guest.name, "creation", created, update_modified=False)

	def post(self, content="<p>Hello</p>", *, space=None, user=None):
		with self.as_user(user or self.guest.name):
			return frappe.get_doc(
				doctype="GP Discussion",
				title="A post",
				project=(space or self.public_space).name,
				content=content,
			).insert()

	def reply(self, content="<p>Hi</p>", *, user=None, thread=None):
		with self.as_user(user or self.guest.name):
			return frappe.get_doc(
				doctype="GP Comment",
				reference_doctype="GP Discussion",
				reference_name=(thread or self.thread).name,
				content=content,
			).insert()

	def poll(self):
		with self.as_user(self.guest.name):
			return frappe.get_doc(
				doctype="GP Poll",
				title="A poll",
				discussion=self.thread.name,
				options=[{"title": "Yes"}, {"title": "No"}],
			).insert()


class TestFirstDay(NewUserLimitsTestCase):
	def setUp(self):
		super().setUp()
		# These tests post many replies in one discussion: only the first-day quota is under test.
		self.set_limits(new_replies_per_discussion=1000)

	def test_configured_quotas_apply(self):
		self.set_limits(new_first_day_discussions=1)
		self.post()
		with self.assertRaisesRegex(NewUserLimitError, "can post 1 discussion on"):
			self.post()

	def test_a_zero_quota_allows_none(self):
		self.set_limits(new_first_day_replies=0)
		with self.assertRaisesRegex(NewUserLimitError, "cannot post replies"):
			self.reply()

	def test_posting_counters_cannot_be_reset_by_deleting_the_profile(self):
		self.post()
		profile = frappe.db.get_value("GP User Profile", {"user": self.guest.name}, "name")
		with self.as_user(self.guest.name), self.assertRaises(frappe.PermissionError):
			frappe.delete_doc("GP User Profile", profile)
		self.assertEqual(frappe.db.get_value("GP User Profile", profile, "first_day_discussions"), 1)

	def test_posting_counters_cannot_be_reset_through_profile_edits(self):
		self.post()
		profile = frappe.get_doc("GP User Profile", {"user": self.guest.name})
		with self.as_user(self.guest.name), self.assertRaises(frappe.PermissionError):
			profile.first_day_discussions = 0
			profile.save()
		self.assertEqual(frappe.db.get_value("GP User Profile", profile.name, "first_day_discussions"), 1)

	def test_migration_backfills_existing_posts_and_never_lowers_a_counter(self):
		from gameplan.gameplan.doctype.gp_user_profile.patches.backfill_first_day_post_counts import execute

		post = self.post()
		self.post()
		self.reply()
		self.poll()
		profile = frappe.db.get_value("GP User Profile", {"user": self.guest.name}, "name")
		frappe.db.set_value("GP User Profile", profile, {"first_day_discussions": 0, "first_day_replies": 0})
		execute()
		with self.as_user(self.guest.name):
			frappe.delete_doc(post.doctype, post.name)
		execute()
		counts = frappe.db.get_value(
			"GP User Profile", profile, ["first_day_discussions", "first_day_replies"]
		)
		self.assertEqual(tuple(counts), (2, 2))

	def test_deleting_discussions_does_not_reset_the_cap(self):
		for _ in range(MAX_DISCUSSIONS_IN_FIRST_DAY):
			post = self.post()
			with self.as_user(self.guest.name):
				frappe.delete_doc(post.doctype, post.name)
		with self.assertRaises(NewUserLimitError):
			self.post()

	def test_deleting_replies_and_polls_does_not_reset_the_shared_cap(self):
		for index in range(MAX_REPLIES_IN_FIRST_DAY):
			post = self.reply() if index % 2 else self.poll()
			with self.as_user(self.guest.name):
				frappe.delete_doc(post.doctype, post.name)
		with self.assertRaises(NewUserLimitError):
			self.reply()
		with self.assertRaises(NewUserLimitError):
			self.poll()

	def test_a_refused_post_does_not_use_the_posting_allowance(self):
		with self.assertRaises(NewUserLimitError):
			self.post(IMAGE * (MAX_MEDIA + 1))
		for _ in range(MAX_DISCUSSIONS_IN_FIRST_DAY):
			self.post()

	def test_three_discussions_on_the_first_day(self):
		for _ in range(MAX_DISCUSSIONS_IN_FIRST_DAY):
			self.post()
		with self.assertRaises(NewUserLimitError):
			self.post()

	def test_ten_replies_on_the_first_day_polls_included(self):
		for _ in range(MAX_REPLIES_IN_FIRST_DAY - 1):
			self.reply()
		self.poll()
		with self.assertRaises(NewUserLimitError):
			self.reply()
		with self.assertRaises(NewUserLimitError):
			self.poll()

	def test_no_daily_cap_once_the_account_is_a_day_old(self):
		self.account_age(hours=25)
		for _ in range(MAX_DISCUSSIONS_IN_FIRST_DAY + 1):
			self.post()


class TestPerPost(NewUserLimitsTestCase):
	def assert_refused(self, content):
		with self.assertRaises(NewUserLimitError):
			self.reply(content)

	def test_images_and_videos_share_the_media_limit_custom_emoji_aside(self):
		self.reply(IMAGE * MAX_MEDIA + EMOJI + EMOJI)
		self.assert_refused(IMAGE * (MAX_MEDIA + 1))
		self.assert_refused(IMAGE * MAX_MEDIA + VIDEO)

	def test_two_links_embeds_included(self):
		self.reply(LINK.format(n=1) + LINK.format(n=2))
		self.assert_refused(LINK.format(n=1) + LINK.format(n=2) + LINK.format(n=3))
		self.assert_refused(
			LINK.format(n=1) + LINK.format(n=2) + '<iframe src="https://www.youtube.com/embed/x"></iframe>'
		)

	def test_no_files_but_videos_are_media(self):
		self.assert_refused(FILE)
		self.reply("<p>Clip</p>" + VIDEO)

	def test_configured_limits_apply(self):
		self.set_limits(new_max_links=1, new_max_attachments=1)
		self.reply(LINK.format(n=1) + FILE)
		with self.assertRaisesRegex(NewUserLimitError, "can add 1 link per post"):
			self.reply(LINK.format(n=1) + LINK.format(n=2))

	def test_a_zero_limit_allows_none(self):
		self.set_limits(new_max_mentions=0)
		with self.assertRaisesRegex(NewUserLimitError, "cannot add mentions"):
			self.reply(MENTION.format(n=1))

	def test_the_site_content_caps_also_apply_and_the_lower_wins(self):
		from gameplan.posting_limits import save_settings

		self.addCleanup(frappe.clear_cache, doctype="GP Posting Settings")
		with self.as_user(self.admin):
			save_settings(0, 0, 0, 0, 0, caps_enabled=1, max_images=2)
		with self.assertRaisesRegex(frappe.ValidationError, "up to 2 images"):
			self.reply(IMAGE * 3)

	def test_two_mentions_and_never_everyone(self):
		self.reply(MENTION.format(n=1) + MENTION.format(n=2))
		self.assert_refused(MENTION.format(n=1) + MENTION.format(n=2) + MENTION.format(n=3))
		self.assert_refused(EVERYONE)

	def test_a_discussion_body_is_checked_too(self):
		with self.assertRaises(NewUserLimitError):
			self.post(IMAGE * (MAX_MEDIA + 1))

	def test_an_edit_is_checked_too(self):
		comment = self.reply()
		with self.as_user(self.guest.name), self.assertRaises(NewUserLimitError):
			comment.content = IMAGE * (MAX_MEDIA + 1)
			comment.save()


class TestRepliesInARow(NewUserLimitsTestCase):
	def test_wait_for_someone_else_to_reply(self):
		limit = LIMITS["new_replies_per_discussion"][0]
		for _ in range(limit):
			self.reply()
		with self.assertRaisesRegex(NewUserLimitError, "after someone else does"):
			self.reply()
		self.reply(user=self.member.name)
		self.reply()

	def test_no_limit_in_their_own_discussion(self):
		own = self.post()
		for _ in range(LIMITS["new_replies_per_discussion"][0] + 1):
			self.reply(thread=own)

	def test_a_zero_limit_allows_no_replies_in_other_discussions(self):
		self.set_limits(new_replies_per_discussion=0)
		with self.assertRaisesRegex(NewUserLimitError, "cannot reply"):
			self.reply()


class TestSettings(NewUserLimitsTestCase):
	def test_the_patch_stores_defaults_without_overwriting_saved_values(self):
		from gameplan.gameplan.doctype.gp_trust_settings.patches.set_new_user_limit_defaults import execute

		frappe.db.delete("Singles", {"doctype": "GP Trust Settings", "field": ["in", list(LIMITS)]})
		frappe.db.set_single_value("GP Trust Settings", "new_max_links", 7)
		execute()
		self.assertEqual(frappe.db.get_single_value("GP Trust Settings", "new_max_links"), 7)
		self.assertEqual(frappe.db.get_single_value("GP Trust Settings", "new_max_media"), MAX_MEDIA)

	def test_basic_first_day_quotas_cannot_be_lower_than_new(self):
		from gameplan.trust_levels import save_settings

		with self.as_user(self.admin), self.assertRaisesRegex(frappe.ValidationError, "fewer than"):
			save_settings(0, new_first_day_replies=10, basic_first_day_replies=9)

	def test_limits_are_validated_against_their_range(self):
		from gameplan.trust_levels import save_settings

		with self.as_user(self.admin), self.assertRaises(frappe.ValidationError):
			save_settings(0, new_max_links=101)


class TestEditWindow(NewUserLimitsTestCase):
	def test_old_poll_option_text_cannot_be_changed_but_votes_can(self):
		poll = self.age(self.poll(), hours=25)
		with self.as_user(self.guest.name), self.assertRaises(NewUserLimitError):
			poll.options[0].title = "Changed answer"
			poll.save()
		with self.as_user(self.guest.name):
			poll = frappe.get_doc("GP Poll", poll.name)
			poll.submit_vote("Yes")
			poll.submit_vote("No")
			poll.retract_vote()

	def age(self, doc, hours):
		created = now_datetime() - timedelta(hours=hours)
		frappe.db.set_value(doc.doctype, doc.name, "creation", created, update_modified=False)
		return frappe.get_doc(doc.doctype, doc.name)

	def test_own_posts_are_editable_for_a_day(self):
		comment = self.age(self.reply(), hours=23)
		with self.as_user(self.guest.name):
			comment.content = "<p>Fixed a typo</p>"
			comment.save()
		comment = self.age(comment, hours=25)
		with self.as_user(self.guest.name), self.assertRaises(NewUserLimitError):
			comment.content = "<p>Too late</p>"
			comment.save()

	def test_reacting_is_not_editing(self):
		own = self.age(self.reply(), hours=48)
		with self.as_user(self.guest.name):
			reactions = own.react(operations=[{"emoji": "👍", "operation": "add"}])
		self.assertEqual([row.emoji for row in reactions], ["👍"])

	def test_others_editing_an_old_guest_post_are_not_limited(self):
		comment = self.age(self.reply(), hours=48)
		with self.as_user(self.member.name):
			comment.content = "<p>Edited by a member</p>" + IMAGE * 3
			comment.save()


class TestWhoIsLimited(NewUserLimitsTestCase):
	def test_not_in_a_space_the_guest_was_invited_to(self):
		for _ in range(MAX_DISCUSSIONS_IN_FIRST_DAY + 1):
			self.post(IMAGE * 3, space=self.invited_space)

	def test_not_members(self):
		for _ in range(MAX_DISCUSSIONS_IN_FIRST_DAY + 1):
			self.post(IMAGE * 3 + EVERYONE, user=self.member.name)

	def test_not_existing_content_saved_by_the_system(self):
		comment = create_comment(self.thread, content=IMAGE * 3, owner=self.guest)
		self.assertTrue(comment.name)


class TestCoverage(GameplanTestCase):
	def test_every_doctype_a_guest_may_create_is_limited(self):
		self.assertEqual(set(POST_FIELDS), GUEST_CREATABLE_DOCTYPES)
		for doctype in GUEST_CREATABLE_DOCTYPES:
			with self.subTest(doctype=doctype):
				hooks = frappe.get_hooks("doc_events").get(doctype, {}).get("validate", [])
				self.assertIn("gameplan.new_user_limits.check_new_user_limits", hooks)
