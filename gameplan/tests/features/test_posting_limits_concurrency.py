import threading

import frappe
from frappe.tests.utils import FrappeTestCase

from gameplan.approval_policy import set_policy
from gameplan.approvals import submit
from gameplan.posting_limits import policy, save_settings
from gameplan.tests.fixtures import create_community, create_member, create_space
from gameplan.tests.search_isolation import guard_real_index


class TestPostingLimitsConcurrency(FrappeTestCase):
	def test_simultaneous_public_and_pending_submissions_share_one_allowance(self):
		if frappe.db.db_type != "mariadb":
			self.skipTest("Tests MariaDB row locks")
		frappe.set_user("Administrator")
		guard_real_index(self)
		previous = policy()
		user = create_member(f"posting_{frappe.generate_hash()}@example.com", "Posting author")
		communities = [create_community("Posting race", members=[user]) for _ in range(2)]
		spaces = [create_space("Posting race", community) for community in communities]
		set_policy(communities[0].name, 100)
		save_settings(1, 1, 0, 0, 0)
		frappe.db.commit()

		def cleanup():
			frappe.set_user("Administrator")
			frappe.db.rollback()
			frappe.db.delete("GP Submission", {"owner": user.name})
			for community in communities:
				frappe.delete_doc("GP Team", community.name, ignore_permissions=True, force=True)
			frappe.delete_doc("User", user.name, ignore_permissions=True, force=True)
			save_settings(**previous)
			frappe.db.commit()

		self.addCleanup(cleanup)
		site, sites_path = frappe.local.site, frappe.local.sites_path
		barrier, successes, errors = threading.Barrier(2), [], []

		def run(index):
			frappe.init(site, sites_path=sites_path)
			try:
				frappe.connect()
				frappe.set_user(user.name)
				# Establish an old snapshot before competing for the account lock.
				frappe.get_doc("GP Project", spaces[index].name)
				barrier.wait(timeout=20)
				successes.append(
					submit(
						"GP Discussion",
						str(index),
						"Concurrent post",
						project=str(spaces[index].name),
						title="Posting race",
					)
				)
				frappe.db.commit()
			except Exception as error:
				errors.append(error)
				frappe.db.rollback()
			finally:
				frappe.destroy()

		threads = [threading.Thread(target=run, args=(index,)) for index in range(2)]
		for thread in threads:
			thread.start()
		for thread in threads:
			thread.join(timeout=40)
		self.assertFalse(any(thread.is_alive() for thread in threads))
		frappe.db.rollback()
		self.assertEqual(len(successes), 1)
		self.assertEqual(len(errors), 1)
		self.assertIsInstance(errors[0], frappe.RateLimitExceededError)
		self.assertEqual(frappe.db.count("GP Posting Event", {"user": user.name}), 1)
