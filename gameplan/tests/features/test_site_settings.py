# Copyright (c) 2026, Frappe Technologies Pvt Ltd and Contributors
# See license.txt

"""Admin settings stored in GP Settings: posting rules, feature switches, sign-up and join defaults."""

from unittest.mock import patch

import frappe

from gameplan import direct_messages as dm
from gameplan.api import invite_by_email, search_sqlite
from gameplan.public_access import PUBLIC_ACCESS_CONFIG_KEY
from gameplan.site_settings import check_email_domain, get_settings, save_setting, save_settings
from gameplan.tests.base import GameplanTestCase
from gameplan.tests.fixtures import (
	create_community,
	create_discussion,
	create_poll,
	create_space,
	create_user,
)


class SiteSettingsTestCase(GameplanTestCase):
	def setUp(self):
		self.addCleanup(frappe.clear_cache, doctype="GP Settings")
		super().setUp()
		self.community = create_community("Settings Community", members=[self.member])
		self.space = create_space("Settings Space", self.community)

	def configure(self, **values):
		with self.as_user(self.admin):
			for key, value in values.items():
				save_setting(key, value)


class TestSavingSettings(SiteSettingsTestCase):
	def test_only_global_admins_read_or_save(self):
		with self.as_user(self.member):
			self.assertRaises(frappe.PermissionError, get_settings)
			self.assertRaises(frappe.PermissionError, save_setting, "polls_enabled", 0)

	def test_saved_values_come_back_typed(self):
		self.configure(min_title_length="12", polls_enabled=0, default_quick_reactions='["👍", "🎉"]')
		with self.as_user(self.admin):
			settings = get_settings()
		self.assertEqual(settings["min_title_length"], 12)
		self.assertIs(settings["polls_enabled"], False)
		self.assertEqual(settings["default_quick_reactions"], ["👍", "🎉"])

	def test_minimum_title_cannot_exceed_maximum(self):
		self.configure(max_title_length=20)
		with self.as_user(self.admin):
			self.assertRaises(frappe.ValidationError, save_setting, "min_title_length", 30)

	def test_saving_together_checks_the_final_values(self):
		with self.as_user(self.admin):
			save_settings({"max_title_length": 20})
			save_settings({"min_title_length": 30, "max_title_length": 50})
			settings = get_settings()
		self.assertEqual((settings["min_title_length"], settings["max_title_length"]), (30, 50))

	def test_one_bad_value_saves_nothing(self):
		with self.as_user(self.admin):
			self.assertRaises(frappe.ValidationError, save_settings, {"polls_enabled": 0, "not_a_setting": 1})
			self.assertIs(get_settings()["polls_enabled"], True)

	def test_secret_is_masked_and_the_mask_never_overwrites_it(self):
		self.configure(unsplash_access_key="real-key")
		self.configure(unsplash_access_key="********")
		with self.as_user(self.admin):
			self.assertEqual(get_settings()["unsplash_access_key"], "********")
		self.assertEqual(frappe.get_cached_doc("GP Settings").get_password("unsplash_access_key"), "real-key")


class TestPublicAccess(SiteSettingsTestCase):
	def setUp(self):
		super().setUp()
		self.write = self.enterContext(patch("frappe.installer.update_site_config"))
		self.audit = self.enterContext(patch("gameplan.public_access_audit.public_access_audit"))
		self.audit.return_value = frappe._dict(problems=[])

	def test_reads_the_site_config_switch(self):
		with self.as_user(self.admin):
			with patch.dict(frappe.conf, {PUBLIC_ACCESS_CONFIG_KEY: 1}):
				self.assertIs(get_settings()["public_access"], True)
			with patch.dict(frappe.conf, {PUBLIC_ACCESS_CONFIG_KEY: 0}):
				self.assertIs(get_settings()["public_access"], False)

	def test_turning_on_writes_the_site_config_switch(self):
		self.configure(public_access=1)
		self.write.assert_called_once_with(PUBLIC_ACCESS_CONFIG_KEY, 1)

	def test_audit_problems_refuse_turning_on_and_save_nothing(self):
		self.audit.return_value = frappe._dict(problems=["Signup gives new accounts the Member role."])
		with self.as_user(self.admin):
			self.assertRaises(frappe.ValidationError, save_settings, {"public_access": 1, "polls_enabled": 0})
			self.assertIs(get_settings()["polls_enabled"], True)
		self.write.assert_not_called()

	def test_turning_off_skips_the_audit(self):
		self.audit.return_value = frappe._dict(problems=["Anything"])
		self.configure(public_access=0)
		self.audit.assert_not_called()
		self.write.assert_called_once_with(PUBLIC_ACCESS_CONFIG_KEY, 0)

	def test_only_global_admins_switch_it(self):
		with self.as_user(self.member):
			self.assertRaises(frappe.PermissionError, save_setting, "public_access", 1)
		self.write.assert_not_called()


class TestInviting(SiteSettingsTestCase):
	def invite(self, email, role="Gameplan Member"):
		with patch("frappe.sendmail"):
			return invite_by_email(email, role)

	def test_only_site_admins_invite_by_default(self):
		with self.as_user(self.member):
			self.assertRaises(frappe.PermissionError, self.invite, "by-default@invite.test")
		with self.as_user(self.admin):
			self.assertEqual(self.invite("by-admin@invite.test")["invited"], ["by-admin@invite.test"])

	def test_all_members_invite_members_but_not_admins(self):
		self.configure(invite_role="All members")
		with self.as_user(self.member):
			self.assertEqual(self.invite("by-member@invite.test")["invited"], ["by-member@invite.test"])
			self.assertRaises(frappe.PermissionError, self.invite, "as-admin@invite.test", "Gameplan Admin")

	def test_community_admins_invite_when_allowed(self):
		self.configure(invite_role="Community and site admins")
		create_community("Inviting Community", admins=[self.second_member])
		with self.as_user(self.member):
			self.assertRaises(frappe.PermissionError, self.invite, "plain-member@invite.test")
		with self.as_user(self.second_member):
			self.assertEqual(self.invite("by-staff@invite.test")["invited"], ["by-staff@invite.test"])


class TestPostingRules(SiteSettingsTestCase):
	def test_defaults_keep_todays_behaviour(self):
		create_discussion("Hi", self.space, content="<p>x</p>")
		create_discussion("Hi", self.space, content="<p>y</p>")

	def test_title_length_limits(self):
		self.configure(min_title_length=5, max_title_length=10)
		self.assertRaises(frappe.ValidationError, create_discussion, "Tiny", self.space)
		self.assertRaises(frappe.ValidationError, create_discussion, "Far too long a title", self.space)
		create_discussion("Just right", self.space)

	def test_post_length_ignores_markup(self):
		self.configure(min_post_length=5)
		self.assertRaises(
			frappe.ValidationError, create_discussion, "Short post", self.space, content="<p><b>hey</b></p>"
		)
		create_discussion("Long enough", self.space, content="<p>hello there</p>")


class TestFeatureSwitches(SiteSettingsTestCase):
	def test_polls_off_refuses_new_polls(self):
		discussion = create_discussion("Poll home", self.space)
		self.configure(polls_enabled=0)
		self.assertRaises(frappe.ValidationError, create_poll, "Lunch?", discussion)

	def test_tags_off_refuses_new_tags(self):
		self.configure(tags_enabled=0)
		self.assertRaises(
			frappe.ValidationError,
			create_discussion,
			"Tagged",
			self.space,
			content='<p><span class="tag-item" data-tag-label="brand-new">#brand-new</span></p>',
		)

	def test_tag_creation_role_still_lets_members_reuse_existing_tags(self):
		tag = '<p><span class="tag-item" data-tag-label="shared-tag">#shared-tag</span></p>'
		create_discussion("Admin tagged", self.space, content=tag)
		self.configure(tag_create_role="Admins only")
		new_tag = '<p><span class="tag-item" data-tag-label="member-tag">#member-tag</span></p>'
		with self.as_user(self.member):
			create_discussion("Member reuses", self.space, content=tag)
			self.assertRaises(
				frappe.ValidationError, create_discussion, "Member invents", self.space, content=new_tag
			)

	def test_direct_messages_off(self):
		for user in (self.member, self.second_member):
			frappe.db.set_value("GP User Profile", {"user": user.name}, "direct_messages_enabled", 1)
		self.configure(direct_messages_enabled=0)
		with self.as_user(self.member):
			self.assertRaises(frappe.PermissionError, dm.send_message, "Hi", to=self.second_member.name)

	def test_search_off(self):
		self.configure(search_enabled=0)
		with self.as_user(self.member):
			self.assertRaises(frappe.PermissionError, search_sqlite, "anything")


class TestSignupAndJoining(SiteSettingsTestCase):
	def test_blocked_domain_and_its_subdomains_are_refused(self):
		self.configure(blocked_email_domains="spam.test")
		for email in ("a@spam.test", "b@mail.spam.test"):
			user = frappe.get_doc(doctype="User", email=email, first_name="Blocked")
			with self.as_user("Guest"):
				self.assertRaises(frappe.ValidationError, check_email_domain, user)
		with self.as_user("Guest"):
			check_email_domain(frappe.get_doc(doctype="User", email="c@notspam.test", first_name="Ok"))

	def test_default_communities_replace_joining_every_public_one(self):
		chosen = create_community("Chosen Community")
		other = create_community("Other Community")
		self.configure(default_communities=[chosen.name])
		create_user("joiner@example.com", "Joiner")
		with patch("frappe.sendmail"):
			invitation = frappe.get_doc(
				doctype="GP Invitation", email="joiner@example.com", role="Gameplan Member"
			).insert(ignore_permissions=True)
			invitation.accept()

		def joined(community):
			return frappe.db.exists(
				"GP Member", {"parenttype": "GP Team", "parent": community.name, "user": "joiner@example.com"}
			)

		self.assertTrue(joined(chosen))
		self.assertFalse(joined(other))

	def joined(self, community, email):
		return bool(
			frappe.db.exists("GP Member", {"parenttype": "GP Team", "parent": community.name, "user": email})
		)

	def new_account(self, email, role):
		user = frappe.get_doc(doctype="User", email=email, first_name="New", send_welcome_email=0)
		user.insert(ignore_permissions=True)
		user.add_roles(role)
		return user

	def test_a_member_made_outside_invitations_still_joins_the_defaults(self):
		chosen = create_community("Desk Chosen Community")
		self.configure(default_communities=[chosen.name])
		self.new_account("desk-made@example.com", "Gameplan Member")
		self.assertTrue(self.joined(chosen, "desk-made@example.com"))

	def test_joining_happens_once_when_the_role_is_first_given(self):
		chosen = create_community("Once Chosen Community")
		self.configure(default_communities=[chosen.name])
		user = create_user("later-member@example.com", "Later Member")
		self.assertFalse(self.joined(chosen, user.name))
		user.reload().add_roles("Gameplan Member")
		self.assertTrue(self.joined(chosen, user.name))
		chosen.reload().remove_member(user.name)
		user.reload().add_roles("Gameplan Admin")
		self.assertFalse(self.joined(chosen, user.name))

	def test_guests_do_not_join_the_defaults(self):
		chosen = create_community("Guest Chosen Community")
		self.configure(default_communities=[chosen.name])
		self.new_account("new-guest@example.com", "Gameplan Guest")
		self.assertFalse(self.joined(chosen, "new-guest@example.com"))

	def test_deleting_an_account_leaves_its_communities(self):
		chosen = create_community("Leaving Chosen Community")
		self.configure(default_communities=[chosen.name])
		user = self.new_account("leaving@example.com", "Gameplan Member")
		self.assertTrue(self.joined(chosen, user.name))
		frappe.delete_doc("User", user.name, ignore_permissions=True)
		self.assertFalse(self.joined(chosen, user.name))
		chosen.reload().save(ignore_permissions=True)
