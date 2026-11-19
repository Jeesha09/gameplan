# Copyright (c) 2026, Frappe Technologies Pvt Ltd and Contributors
# See license.txt

"""Members delete their own account through Frappe's Personal Data Deletion Request."""

from unittest.mock import patch

import frappe

from gameplan.account_deletion import REQUEST, request_account_deletion
from gameplan.tests.base import GameplanTestCase
from gameplan.tests.fixtures import create_community, create_discussion, create_space


class TestAccountDeletion(GameplanTestCase):
	def setUp(self):
		super().setUp()
		self.enterContext(patch("frappe.sendmail"))

	def request(self, user):
		with self.as_user(user):
			request_account_deletion()
		return frappe.get_last_doc(REQUEST, filters={"email": user.name})

	def confirm(self, request):
		with self.as_user("Guest"):
			request.status = "Pending Approval"
			request.save(ignore_permissions=True)
		return request.reload()

	def test_member_gets_a_verification_request(self):
		self.assertEqual(self.request(self.member).status, "Pending Verification")

	def test_asking_twice_reuses_the_open_request(self):
		self.request(self.member)
		self.request(self.member)
		self.assertEqual(frappe.db.count(REQUEST, {"email": self.member.name}), 1)

	def test_busy_accounts_can_delete_too(self):
		frappe.db.set_value("GP User Profile", {"user": self.member.name}, "discussions_count", 500)
		self.assertEqual(self.request(self.member).status, "Pending Verification")

	def test_guests_cannot_ask(self):
		with self.as_user("Guest"):
			self.assertRaises(frappe.PermissionError, request_account_deletion)

	def test_confirming_deletes_and_anonymises_at_once(self):
		email = self.member.name
		profile = frappe.db.get_value("GP User Profile", {"user": email})
		frappe.db.set_value("GP User Profile", profile, "bio", "Something personal")
		request = self.confirm(self.request(self.member))
		self.assertEqual(request.status, "Deleted")
		self.assertFalse(frappe.db.exists("User", email))
		self.assertFalse(frappe.db.exists("GP User Profile", profile))
		cleared = frappe.get_doc("GP User Profile", {"user": request.name})
		self.assertEqual((cleared.full_name, cleared.bio, cleared.enabled), ("Deleted user", "", 0))
		self.assertEqual(frappe.db.get_value("User", request.name, "full_name"), "Deleted user")

	def test_posts_stay_under_the_deleted_account(self):
		community = create_community("Deletion Community", members=[self.member])
		space = create_space("Deletion Space", community)
		with self.as_user(self.member):
			discussion = create_discussion("Still here", space, content="<p>Keep me</p>")
		request = self.confirm(self.request(self.member))
		kept = frappe.get_doc("GP Discussion", discussion.name)
		self.assertEqual((kept.owner, kept.title), (request.name, "Still here"))
		self.assertIn("Keep me", kept.content)
