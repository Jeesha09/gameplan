# Copyright (c) 2026, Frappe Technologies Pvt Ltd and Contributors
# See license.txt

import threading

import frappe
from frappe.tests.utils import FrappeTestCase

from gameplan import direct_messages as dm
from gameplan.tests.fixtures import create_member


class TestDirectMessageConcurrency(FrappeTestCase):
	def setUp(self):
		if frappe.db.db_type != "mariadb":
			self.skipTest("Tests MariaDB row locks")
		frappe.set_user("Administrator")
		token = frappe.generate_hash(length=8)
		self.people = [
			create_member(f"dm_{index}_{token}@example.com", f"Race {index}") for index in range(2)
		]
		for person in self.people:
			frappe.db.set_value("GP User Profile", {"user": person.name}, "direct_messages_enabled", 1)
		frappe.db.commit()
		self.addCleanup(self.cleanup)

	def cleanup(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		names = [person.name for person in self.people]
		conversations = frappe.get_all(
			"GP Conversation Member", filters={"user": ["in", names]}, pluck="conversation"
		)
		for doctype, field in (("GP Message", "conversation"), ("GP Conversation Member", "conversation")):
			frappe.db.delete(doctype, {field: ["in", conversations]})
		frappe.db.delete("GP Conversation", {"name": ["in", conversations]})
		for name in names:
			frappe.delete_doc("User", name, ignore_permissions=True, force=True)
		frappe.db.commit()

	def race(self, calls_for):
		site, sites_path = frappe.local.site, frappe.local.sites_path
		barrier, errors = threading.Barrier(len(self.people)), []

		def run(index):
			frappe.init(site, sites_path=sites_path)
			try:
				frappe.connect()
				frappe.set_user(self.people[index].name)
				frappe.db.get_value("User", self.people[index].name, "name")
				barrier.wait(timeout=20)
				for call in calls_for(index):
					call()
					frappe.db.commit()
					frappe.db.get_value("User", self.people[index].name, "name")
			except Exception as error:
				errors.append(error)
				frappe.db.rollback()
			finally:
				frappe.destroy()

		threads = [threading.Thread(target=run, args=(index,)) for index in range(len(self.people))]
		for thread in threads:
			thread.start()
		for thread in threads:
			thread.join(timeout=60)
		self.assertFalse(any(thread.is_alive() for thread in threads))
		frappe.db.rollback()
		self.assertEqual(errors, [])

	def other(self, index):
		return self.people[1 - index].name

	def test_two_first_messages_land_in_one_conversation(self):
		self.race(lambda index: [lambda: dm.send_message(f"First {index}", to=self.other(index))])
		key = dm.direct_key(*[person.name for person in self.people])
		conversations = frappe.get_all("GP Conversation", filters={"direct_key": key}, pluck="name")
		self.assertEqual(len(conversations), 1)
		self.assertEqual(frappe.db.count("GP Message", {"conversation": str(conversations[0])}), 2)
		self.assertEqual(
			frappe.db.count("GP Conversation Member", {"conversation": str(conversations[0])}), 2
		)

	def test_people_typing_at_once_lose_nothing_and_stay_in_order(self):
		frappe.set_user(self.people[0].name)
		conversation = dm.send_message("Start", to=self.people[1].name)["conversation"]
		frappe.set_user("Administrator")
		frappe.db.commit()
		rounds = 10

		self.race(
			lambda index: [
				lambda number=number: dm.send_message(f"{index}-{number}", conversation=conversation)
				for number in range(rounds)
			]
		)
		names = frappe.get_all(
			"GP Message", filters={"conversation": conversation}, pluck="name", order_by="name desc"
		)
		self.assertEqual(len(names), 1 + 2 * rounds)
		last = frappe.db.get_value("GP Conversation", conversation, "last_message")
		self.assertEqual(last, names[0])
		rows = frappe.get_all(
			"GP Conversation Member", filters={"conversation": conversation}, pluck="last_message"
		)
		self.assertEqual(set(rows), {names[0]})
