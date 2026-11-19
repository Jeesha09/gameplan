# Copyright (c) 2026, Frappe Technologies Pvt Ltd and Contributors
# See license.txt

"""Members delete their own account through Frappe's Personal Data Deletion Request."""

from unittest.mock import patch

import frappe

from gameplan.account_deletion import REQUEST, request_account_deletion
from gameplan.site_settings import save_setting
from gameplan.tests.base import GameplanTestCase


class TestAccountDeletion(GameplanTestCase):
	def setUp(self):
		self.addCleanup(frappe.clear_cache, doctype="GP Settings")
		super().setUp()
		self.enterContext(patch("frappe.sendmail"))

	def request(self, user):
		with self.as_user(user):
			request_account_deletion()
		return frappe.get_last_doc(REQUEST, filters={"email": user.name})

	def set_posts(self, user, count):
		frappe.db.set_value("GP User Profile", {"user": user.name}, "discussions_count", count)

	def test_member_gets_a_verification_request(self):
		self.assertEqual(self.request(self.member).status, "Pending Verification")

	def test_asking_twice_reuses_the_open_request(self):
		self.request(self.member)
		self.request(self.member)
		self.assertEqual(frappe.db.count(REQUEST, {"email": self.member.name}), 1)

	def test_post_limit_refuses_busy_accounts(self):
		self.set_posts(self.member, 10)
		with self.as_user(self.member):
			self.assertRaises(frappe.ValidationError, request_account_deletion)
		with self.as_user(self.admin):
			save_setting("account_deletion_max_posts", 0)
		self.assertEqual(self.request(self.member).status, "Pending Verification")

	def test_guests_cannot_ask(self):
		with self.as_user("Guest"):
			self.assertRaises(frappe.PermissionError, request_account_deletion)

	def test_confirming_deletes_and_anonymises_at_once(self):
		email = self.member.name
		profile = frappe.db.get_value("GP User Profile", {"user": email})
		frappe.db.set_value("GP User Profile", profile, "bio", "Something personal")
		request = self.request(self.member)
		with self.as_user("Guest"):
			request.status = "Pending Approval"
			request.save(ignore_permissions=True)
		self.assertEqual(request.reload().status, "Deleted")
		self.assertFalse(frappe.db.exists("User", email))
		self.assertFalse(frappe.db.exists("GP User Profile", profile))
		cleared = frappe.get_doc("GP User Profile", {"user": request.name})
		self.assertEqual((cleared.full_name, cleared.bio, cleared.enabled), ("Deleted user", "", 0))
		self.assertEqual(frappe.db.get_value("User", request.name, "full_name"), "Deleted user")
