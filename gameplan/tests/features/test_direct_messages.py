# Copyright (c) 2026, Frappe Technologies Pvt Ltd and Contributors
# See license.txt

from unittest.mock import patch

import frappe
from frappe.client import get_list as client_get_list
from frappe.desk.reportview import get_list as reportview_get_list

from gameplan import direct_messages as dm
from gameplan.api import search_users
from gameplan.realtime import (
	CONVERSATION_CLEARED,
	CONVERSATION_MUTED,
	MESSAGE_RECEIVED,
	MESSAGE_UPDATED,
	MESSAGES_READ,
	MESSAGES_SEEN,
	NOTIFICATION_CHANGED,
	USERS_CHANGED,
)
from gameplan.tests.base import GameplanTestCase
from gameplan.tests.fixtures import create_member

DM_DOCTYPES = ("GP Conversation", "GP Conversation Member", "GP Message")


def allow_messages(user, enabled=1):
	frappe.db.set_value("GP User Profile", {"user": user.name}, "direct_messages_enabled", enabled)


class DirectMessagesTestCase(GameplanTestCase):
	def setUp(self):
		super().setUp()
		for user in (self.member, self.second_member, self.outsider, self.admin):
			allow_messages(user)

	def person(self, email, name):
		user = create_member(email, name)
		allow_messages(user)
		return user

	def send(self, sender, content="Hello", **target):
		with self.as_user(sender):
			return dm.send_message(content, **target)

	def start(self, sender=None, recipient=None):
		sender, recipient = sender or self.member, recipient or self.second_member
		return self.send(sender, to=recipient.name)["conversation"]

	def published(self, publish):
		return [call for call in publish.call_args_list if call.args[0] != NOTIFICATION_CHANGED]

	def row(self, conversation, user):
		return frappe.db.get_value(
			"GP Conversation Member",
			{"conversation": conversation, "user": user.name},
			["last_message", "last_read_message", "unread_count"],
			as_dict=True,
		)


class TestConversations(DirectMessagesTestCase):
	def test_first_message_starts_one_conversation_used_from_both_sides(self):
		first = self.send(self.member, to=self.second_member.name)
		second = self.send(self.second_member, to=self.member.name)
		self.assertEqual(first["conversation"], second["conversation"])
		self.assertEqual(frappe.db.count("GP Conversation"), 1)
		self.assertEqual(frappe.db.count("GP Conversation Member"), 2)

	def test_looking_up_a_person_creates_nothing(self):
		with self.as_user(self.member):
			self.assertIsNone(dm.get_direct_conversation(self.second_member.name))
		self.assertEqual(frappe.db.count("GP Conversation"), 0)
		conversation = self.start()
		with self.as_user(self.second_member):
			self.assertEqual(dm.get_direct_conversation(self.member.name), conversation)

	def test_a_failed_first_message_leaves_no_empty_conversation(self):
		with self.as_user(self.member), self.assertRaises(frappe.ValidationError):
			dm.send_message("<p> </p>", to=self.second_member.name)
		self.assertEqual(frappe.db.count("GP Conversation"), 0)

	def test_needs_exactly_one_target(self):
		conversation = self.start()
		with self.as_user(self.member):
			with self.assertRaises(frappe.ValidationError):
				dm.send_message("Hi")
			with self.assertRaises(frappe.ValidationError):
				dm.send_message("Hi", conversation=conversation, to=self.second_member.name)

	def test_cannot_message_yourself_guests_disabled_or_unknown_people(self):
		frappe.db.set_value("User", self.outsider.name, "enabled", 0)
		for recipient in (self.member.name, self.guest.name, self.outsider.name, "nobody@example.com"):
			with self.as_user(self.member), self.assertRaises(frappe.ValidationError):
				dm.send_message("Hi", to=recipient)
		self.assertEqual(frappe.db.count("GP Conversation"), 0)

	def test_guests_cannot_send(self):
		with self.as_user(self.guest), self.assertRaises(frappe.PermissionError):
			dm.send_message("Hi", to=self.member.name)


class TestPrivacy(DirectMessagesTestCase):
	def test_only_participants_reach_a_conversation(self):
		conversation = self.start()
		for person in (self.outsider, self.admin, self.guest):
			with self.as_user(person):
				for call in (
					lambda: dm.get_messages(conversation),
					lambda: dm.get_conversation(conversation),
					lambda: dm.mark_read(conversation),
					lambda: dm.send_message("Let me in", conversation=conversation),
					lambda: dm.set_muted(conversation, True),
				):
					with self.assertRaises(frappe.PermissionError):
						call()
				if person != self.guest:
					self.assertEqual(dm.get_conversations()["conversations"], [])
					self.assertEqual(dm.search("Hello")["messages"], [])
		self.assertEqual(frappe.db.count("GP Message"), 1)

	def test_unknown_and_private_conversations_look_the_same(self):
		conversation = self.start()
		with self.as_user(self.outsider):
			for name in (conversation, "999999"):
				with self.assertRaises(frappe.PermissionError):
					dm.get_messages(name)

	def test_generic_apis_read_nothing_even_for_admins_and_participants(self):
		self.start()
		frappe.get_doc("User", self.admin.name).add_roles("System Manager")
		for person in (self.member, self.admin):
			with self.as_user(person):
				for doctype in DM_DOCTYPES:
					self.assertFalse(frappe.has_permission(doctype, "read"))
					with self.assertRaises(frappe.PermissionError):
						client_get_list(doctype, fields=["name"])
					with self.assertRaises(frappe.PermissionError):
						frappe.form_dict.update({"doctype": doctype, "fields": '["name"]'})
						reportview_get_list()

	def test_no_doc_or_list_events_leave_the_server(self):
		with patch("frappe.realtime.publish_realtime") as publish:
			self.start()
		events = {call.args[0] for call in publish.call_args_list}
		self.assertEqual(events, {MESSAGE_RECEIVED, NOTIFICATION_CHANGED})
		notified = {
			call.kwargs["user"] for call in publish.call_args_list if call.args[0] == NOTIFICATION_CHANGED
		}
		self.assertEqual(notified, {self.second_member.name})

	def test_message_events_reach_only_the_people_in_the_conversation(self):
		with patch("frappe.realtime.publish_realtime") as publish:
			conversation = self.start()
		received = {call.kwargs["user"] for call in self.published(publish)}
		self.assertEqual(received, {self.member.name, self.second_member.name})
		for call in self.published(publish):
			self.assertTrue(call.kwargs["after_commit"])
			self.assertEqual(call.kwargs["message"]["conversation"], conversation)

	def test_messages_stay_out_of_search(self):
		# Newer Frappe has no such column, and SQLite would answer with its name.
		if frappe.db.has_column("DocType", "index_web_pages_for_search"):
			self.assertFalse(
				frappe.db.get_value("DocType", "GP Message", "index_web_pages_for_search"),
			)
		self.assertNotIn("GP Message", frappe.get_hooks("sqlite_search"))


class TestMessages(DirectMessagesTestCase):
	def test_content_is_sanitized_and_previewed_as_plain_text(self):
		sent = self.send(
			self.member, "<p>Hi <b>there</b></p><script>alert(1)</script>", to=self.second_member.name
		)
		self.assertNotIn("<script", sent["message"]["content"])
		self.assertEqual(
			frappe.db.get_value("GP Conversation", sent["conversation"], "last_message_preview"), "Hi there"
		)

	def test_leading_blank_lines_are_dropped_but_inner_ones_kept(self):
		cases = {
			"<p><br><br>   hi</p>": "<p>hi</p>",
			"<p></p><p> </p><p>hi</p><p></p><p>there</p>": "<p>hi</p><p></p><p>there</p>",
			"<p>one<br><br>two</p>": "<p>one<br/><br/>two</p>",
			"<p><br></p><ul><li><p>item</p></li></ul>": "<ul><li><p>item</p></li></ul>",
		}
		for content, expected in cases.items():
			sent = self.send(self.member, content, to=self.second_member.name)
			self.assertEqual(sent["message"]["content"], expected, content)

	def test_long_previews_are_cut_and_oversized_messages_refused(self):
		sent = self.send(self.member, f"<p>{'a' * 500}</p>", to=self.second_member.name)
		preview = frappe.db.get_value("GP Conversation", sent["conversation"], "last_message_preview")
		self.assertEqual(len(preview), dm.PREVIEW_LENGTH)
		with self.as_user(self.member), self.assertRaises(frappe.ValidationError):
			dm.send_message(f"<p>{'a' * dm.MAX_MESSAGE_LENGTH}</p>", to=self.second_member.name)

	def test_messages_page_backwards_without_gaps_or_repeats(self):
		conversation = self.start()
		for index in range(6):
			self.send(self.member, f"<p>{index}</p>", conversation=conversation)
		with self.as_user(self.second_member):
			newest = dm.get_messages(conversation, limit=4)
			older = dm.get_messages(conversation, before=newest["messages"][0].name, limit=4)
		self.assertTrue(newest["has_more"])
		self.assertFalse(older["has_more"])
		names = [row.name for row in older["messages"] + newest["messages"]]
		self.assertEqual(names, sorted(set(names)))
		self.assertEqual(len(names), 7)

	def test_page_size_is_capped(self):
		conversation = self.start()
		for _ in range(3):
			self.send(self.member, conversation=conversation)
		with self.as_user(self.member), patch.object(dm, "MAX_PAGE_SIZE", 2):
			self.assertEqual(len(dm.get_messages(conversation, limit=9999)["messages"]), 2)


class TestInbox(DirectMessagesTestCase):
	def test_newest_conversation_comes_first_and_pages_cleanly(self):
		people = [self.person(f"dm{index}@example.com", f"Person {index}") for index in range(3)]
		conversations = [self.start(self.member, person) for person in people]
		self.send(self.member, conversation=conversations[0])
		with self.as_user(self.member):
			first = dm.get_conversations(limit=2)
			second = dm.get_conversations(before=first["conversations"][-1]["last_message"], limit=2)
		listed = [row["name"] for row in first["conversations"] + second["conversations"]]
		self.assertEqual(listed, [conversations[0], conversations[2], conversations[1]])
		self.assertTrue(first["has_more"])
		self.assertFalse(second["has_more"])

	def test_row_names_the_other_person_and_the_last_message(self):
		conversation = self.start()
		with self.as_user(self.second_member):
			[row] = dm.get_conversations()["conversations"]
			self.assertEqual(row, dm.get_conversation(conversation))
		self.assertEqual(row["people"], [self.member.name])
		self.assertEqual(row["last_message_preview"], "Hello")
		self.assertEqual(row["last_message_by"], self.member.name)
		self.assertEqual(row["unread_count"], 1)

	def test_unread_counts_for_the_recipient_only_and_clears_on_read(self):
		conversation = self.start()
		self.send(self.member, conversation=conversation)
		self.assertEqual(self.row(conversation, self.second_member).unread_count, 2)
		self.assertEqual(self.row(conversation, self.member).unread_count, 0)
		with self.as_user(self.second_member):
			self.assertEqual(dm.get_unread_conversation_count(), 1)
			dm.mark_read(conversation)
			self.assertEqual(dm.get_unread_conversation_count(), 0)
		row = self.row(conversation, self.second_member)
		self.assertEqual(row.last_read_message, row.last_message)

	def test_replying_reads_the_conversation(self):
		conversation = self.start()
		self.send(self.second_member, conversation=conversation)
		self.assertEqual(self.row(conversation, self.second_member).unread_count, 0)
		self.assertEqual(self.row(conversation, self.member).unread_count, 1)

	def test_message_event_carries_the_message_and_each_persons_unread_total(self):
		with patch("frappe.realtime.publish_realtime") as publish:
			sent = self.send(self.member, to=self.second_member.name)
		totals = {
			call.kwargs["user"]: call.kwargs["message"]["unread_conversations"]
			for call in self.published(publish)
		}
		self.assertEqual(totals, {self.member.name: 0, self.second_member.name: 1})
		self.assertEqual(self.published(publish)[0].kwargs["message"]["message"], sent["message"])

	def test_reading_tells_your_other_tabs(self):
		conversation = self.start()
		with patch("frappe.realtime.publish_realtime") as publish, self.as_user(self.second_member):
			dm.mark_read(conversation)
		[call] = [call for call in self.published(publish) if call.args[0] == MESSAGES_READ]
		self.assertEqual(call.kwargs["user"], self.second_member.name)
		self.assertEqual(call.kwargs["message"]["unread_conversations"], 0)

	def test_marking_a_read_conversation_writes_nothing(self):
		conversation = self.start()
		with self.as_user(self.member), patch.object(dm, "clear_unread") as clear:
			dm.mark_read(conversation)
		clear.assert_not_called()


class TestScale(DirectMessagesTestCase):
	def count_queries(self, call):
		with patch.object(frappe.db, "sql", wraps=frappe.db.sql) as sql:
			call()
		return sql.call_count

	def test_inbox_queries_do_not_grow_with_conversations(self):
		self.start()
		with self.as_user(self.member):
			small = self.count_queries(dm.get_conversations)
		for index in range(8):
			self.start(self.member, self.person(f"scale{index}@example.com", f"Scale {index}"))
		with self.as_user(self.member):
			large = self.count_queries(dm.get_conversations)
		self.assertEqual(small, large)

	def test_sending_does_not_grow_with_conversation_length_or_other_chats(self):
		conversation = self.start()
		with self.as_user(self.member):
			# Frappe remembers the links it has checked, and the setup below clears that. Send
			# once before each count, so both counts start with the same warm state.
			dm.send_message("Hi", conversation=conversation)
			small = self.count_queries(lambda: dm.send_message("Hi", conversation=conversation))
		for index in range(5):
			self.send(self.member, conversation=conversation)
			self.start(self.member, self.person(f"busy{index}@example.com", f"Busy {index}"))
		with self.as_user(self.member):
			dm.send_message("Hi", conversation=conversation)
			large = self.count_queries(lambda: dm.send_message("Hi", conversation=conversation))
		self.assertEqual(small, large)


class TestRetries(DirectMessagesTestCase):
	def test_a_conflict_is_retried_on_a_fresh_transaction(self):
		calls = []

		def write():
			calls.append(1)
			if len(calls) == 1:
				raise frappe.QueryDeadlockError("Record has changed since last read")
			return "done"

		with patch.object(frappe.db, "rollback") as rollback:
			self.assertEqual(dm.retry_write(write), "done")
		rollback.assert_called_once()

	def test_gives_up_after_the_last_attempt(self):
		write = patch.object(dm, "deliver", side_effect=frappe.QueryDeadlockError("busy"))
		with write as deliver, patch.object(frappe.db, "rollback"), self.as_user(self.member):
			with self.assertRaises(frappe.QueryDeadlockError):
				dm.send_message("Hi", to=self.second_member.name)
		self.assertEqual(deliver.call_count, dm.WRITE_ATTEMPTS)


class TestSetting(DirectMessagesTestCase):
	def test_messages_are_off_until_turned_on(self):
		person = create_member("new@example.com", "New Person")
		with self.as_user(person):
			self.assertEqual(dm.get_unread_conversation_count(), 0)
			for call in (dm.get_conversations, lambda: dm.get_direct_conversation(self.member.name)):
				with self.assertRaises(frappe.PermissionError):
					call()
		with self.as_user(self.member), self.assertRaises(frappe.ValidationError):
			dm.send_message("Hi", to=person.name)

	def test_turning_off_stops_new_messages_but_keeps_the_conversation(self):
		conversation = self.start()
		allow_messages(self.second_member, 0)
		with self.as_user(self.member), self.assertRaises(frappe.ValidationError):
			dm.send_message("Still there?", conversation=conversation)
		with self.as_user(self.second_member), self.assertRaises(frappe.PermissionError):
			dm.get_messages(conversation)
		allow_messages(self.second_member)
		with self.as_user(self.second_member):
			self.assertEqual(len(dm.get_messages(conversation)["messages"]), 1)

	def test_people_search_can_list_only_those_accepting_messages(self):
		self.person("nadia@example.com", "Nadia Open")
		create_member("nadir@example.com", "Nadir Closed")
		with self.as_user(self.member):
			everyone = [row["name"] for row in search_users("n")]
			open_only = [row["name"] for row in search_users("n", direct_messages=True)]
		self.assertIn("nadir@example.com", everyone)
		self.assertIn("nadia@example.com", open_only)
		self.assertNotIn("nadir@example.com", open_only)

	def test_people_search_skips_those_not_accepting_when_most_do(self):
		self.person("nadia@example.com", "Nadia Open")
		closed = create_member("nadir@example.com", "Nadir Closed")
		frappe.db.set_value("GP User Profile", {"direct_messages_enabled": 0}, "direct_messages_enabled", 1)
		allow_messages(closed, 0)
		with self.as_user(self.member):
			open_only = [row["name"] for row in search_users("n", direct_messages=True)]
		self.assertIn("nadia@example.com", open_only)
		self.assertNotIn("nadir@example.com", open_only)

	def test_the_toggle_saves_and_tells_everyone(self):
		person = create_member("toggle@example.com", "Toggle")
		with patch("frappe.realtime.publish_realtime") as publish, self.as_user(person):
			dm.set_direct_messages_enabled(True)
		self.assertTrue(dm.messages_enabled(person.name))
		self.assertEqual({call.args[0] for call in self.published(publish)}, {USERS_CHANGED})
		with self.as_user(person):
			dm.set_direct_messages_enabled(False)
		self.assertFalse(dm.messages_enabled(person.name))

	def test_guests_cannot_turn_messages_on(self):
		with self.as_user(self.guest), self.assertRaises(frappe.PermissionError):
			dm.set_direct_messages_enabled(True)


class TestEditAndDelete(DirectMessagesTestCase):
	def test_editing_changes_the_text_and_marks_it_edited(self):
		sent = self.send(self.member, "<p>Helo</p>", to=self.second_member.name)
		with patch("frappe.realtime.publish_realtime") as publish, self.as_user(self.member):
			edited = dm.edit_message(sent["message"]["name"], "<p>Hello</p>")
		self.assertEqual(edited["content"], "<p>Hello</p>")
		self.assertTrue(edited["edited_at"])
		self.assertEqual(
			frappe.db.get_value("GP Conversation", sent["conversation"], "last_message_preview"), "Hello"
		)
		received = {
			call.kwargs["user"] for call in self.published(publish) if call.args[0] == MESSAGE_UPDATED
		}
		self.assertEqual(received, {self.member.name, self.second_member.name})

	def test_editing_an_older_message_leaves_the_preview_alone(self):
		first = self.send(self.member, "<p>First</p>", to=self.second_member.name)
		self.send(self.member, "<p>Second</p>", conversation=first["conversation"])
		with self.as_user(self.member):
			dm.edit_message(first["message"]["name"], "<p>First, fixed</p>")
		self.assertEqual(
			frappe.db.get_value("GP Conversation", first["conversation"], "last_message_preview"), "Second"
		)

	def test_deleting_the_last_message_previews_the_one_before(self):
		first = self.send(self.second_member, "<p>Earlier</p>", to=self.member.name)
		last = self.send(self.member, "<p>Oops</p>", conversation=first["conversation"])
		with self.as_user(self.member):
			dm.delete_message(last["message"]["name"])
		preview, by = frappe.db.get_value(
			"GP Conversation", first["conversation"], ["last_message_preview", "last_message_by"]
		)
		self.assertEqual((preview, by), ("Earlier", self.second_member.name))

	def test_deleting_wipes_the_text(self):
		sent = self.send(self.member, "<p>Oops</p>", to=self.second_member.name)
		with self.as_user(self.member):
			dm.delete_message(sent["message"]["name"])
		with self.as_user(self.second_member):
			[message] = dm.get_messages(sent["conversation"])["messages"]
		self.assertEqual(message.content, "")
		self.assertTrue(message.deleted_at)
		self.assertEqual(
			frappe.db.get_value("GP Conversation", sent["conversation"], "last_message_preview"), ""
		)
		with self.as_user(self.member):
			for call in (
				lambda: dm.edit_message(sent["message"]["name"], "<p>Back</p>"),
				lambda: dm.delete_message(sent["message"]["name"]),
			):
				with self.assertRaises(frappe.ValidationError):
					call()

	def test_only_the_sender_can_edit_or_delete(self):
		sent = self.send(self.member, to=self.second_member.name)
		name = sent["message"]["name"]
		for person in (self.second_member, self.outsider, self.admin):
			with self.as_user(person):
				for call in (
					lambda: dm.edit_message(name, "<p>Mine now</p>"),
					lambda: dm.delete_message(name),
				):
					with self.assertRaises(frappe.PermissionError):
						call()
		self.assertEqual(frappe.db.get_value("GP Message", name, "content"), "Hello")


class TestMute(DirectMessagesTestCase):
	def test_muted_conversations_stay_out_of_the_unread_total(self):
		conversation = self.start()
		with patch("frappe.realtime.publish_realtime") as publish, self.as_user(self.second_member):
			self.assertEqual(dm.set_muted(conversation, True), 0)
			self.assertEqual(dm.get_unread_conversation_count(), 0)
			[row] = dm.get_conversations()["conversations"]
		self.assertEqual(row["muted"], 1)
		self.assertEqual(row["unread_count"], 1)
		[call] = self.published(publish)
		self.assertEqual(call.args[0], CONVERSATION_MUTED)
		self.assertEqual(call.kwargs["user"], self.second_member.name)
		with patch("frappe.realtime.publish_realtime") as publish:
			self.send(self.member, conversation=conversation)
		totals = {
			call.kwargs["user"]: call.kwargs["message"]["unread_conversations"]
			for call in self.published(publish)
		}
		self.assertEqual(totals[self.second_member.name], 0)
		with self.as_user(self.second_member):
			self.assertEqual(dm.set_muted(conversation, False), 1)


class TestSearch(DirectMessagesTestCase):
	def test_finds_people_and_message_text_in_your_conversations_only(self):
		conversation = self.start()
		self.send(self.member, "<p>The <strong>letterhead</strong> looks off</p>", conversation=conversation)
		self.send(self.outsider, "<p>Letterhead elsewhere</p>", to=self.admin.name)
		with self.as_user(self.second_member):
			by_name = dm.search("membe")
			by_text = dm.search("LETTERHEAD")
			self.assertEqual(dm.search("strong")["messages"], [])
			self.assertEqual(dm.search(" "), {"conversations": [], "messages": []})
			one_letter = dm.search("l")["messages"]
			self.assertEqual(dm.search("etterhead")["messages"], [])
		self.assertIn(conversation, [hit["conversation"] for hit in one_letter])
		self.assertEqual([row["name"] for row in by_name["conversations"]], [conversation])
		[hit] = by_text["messages"]
		self.assertEqual(hit["conversation"], conversation)
		self.assertEqual(hit["people"], [self.member.name])
		self.assertEqual(hit["snippet"], "The letterhead looks off")

	def test_deleted_messages_are_not_found(self):
		sent = self.send(self.member, "<p>Secret plan</p>", to=self.second_member.name)
		with self.as_user(self.member):
			dm.delete_message(sent["message"]["name"])
			self.assertEqual(dm.search("Secret")["messages"], [])


class TestJumpToMessage(DirectMessagesTestCase):
	def test_loads_around_a_message_and_pages_both_ways(self):
		conversation = self.start()
		names = [
			self.send(self.member, f"<p>{index}</p>", conversation=conversation)["message"]["name"]
			for index in range(9)
		]
		with self.as_user(self.second_member):
			middle = dm.get_messages(conversation, around=names[4], limit=4)
			newer = dm.get_messages(conversation, after=middle["messages"][-1].name, limit=4)
			newest = dm.get_messages(conversation, after=newer["messages"][-1].name, limit=4)
		self.assertEqual([row.name for row in middle["messages"]], names[2:6])
		self.assertTrue(middle["has_more"])
		self.assertTrue(middle["has_newer"])
		self.assertEqual([row.name for row in newer["messages"]], names[6:])
		self.assertFalse(newer["has_newer"])
		self.assertEqual(newest["messages"], [])


class TestReplies(DirectMessagesTestCase):
	def test_a_reply_carries_a_preview_of_the_original(self):
		first = self.send(self.member, "<p>Lunch at <b>noon</b>?</p>", to=self.second_member.name)
		conversation = first["conversation"]
		with self.as_user(self.second_member):
			reply = dm.send_message(
				"<p>Sure</p>", conversation=conversation, reply_to=first["message"]["name"]
			)
			messages = dm.get_messages(conversation)["messages"]
		expected = {
			"name": first["message"]["name"],
			"owner": self.member.name,
			"snippet": "Lunch at noon ?",
			"deleted": False,
		}
		self.assertEqual(reply["message"]["reply"], expected)
		self.assertEqual(messages[-1].reply, expected)
		self.assertIsNone(messages[0].reply)

	def test_a_deleted_original_shows_as_deleted(self):
		first = self.send(self.member, "<p>Oops</p>", to=self.second_member.name)
		self.send(
			self.second_member,
			"<p>What?</p>",
			conversation=first["conversation"],
			reply_to=first["message"]["name"],
		)
		with self.as_user(self.member):
			dm.delete_message(first["message"]["name"])
			reply = dm.get_messages(first["conversation"])["messages"][-1]
		self.assertTrue(reply.reply["deleted"])
		self.assertEqual(reply.reply["snippet"], "")

	def test_can_only_reply_to_a_live_message_in_the_same_conversation(self):
		mine = self.send(self.member, to=self.second_member.name)
		elsewhere = self.send(self.outsider, "<p>Private</p>", to=self.admin.name)
		gone = self.send(self.member, conversation=mine["conversation"])
		with self.as_user(self.member):
			dm.delete_message(gone["message"]["name"])
		for target in (
			{"conversation": mine["conversation"], "reply_to": elsewhere["message"]["name"]},
			{"conversation": mine["conversation"], "reply_to": 10**9},
			{"to": self.second_member.name, "reply_to": mine["message"]["name"]},
			{"conversation": mine["conversation"], "reply_to": gone["message"]["name"]},
		):
			with self.subTest(target=target), self.assertRaises(frappe.ValidationError):
				self.send(self.second_member, **target)


class TestReactions(DirectMessagesTestCase):
	def test_reacting_toggles_your_emoji_and_tells_both_people(self):
		sent = self.send(self.member, to=self.second_member.name)
		name = sent["message"]["name"]
		with patch("frappe.realtime.publish_realtime") as publish, self.as_user(self.second_member):
			reacted = dm.react(name, "👍")
		self.assertEqual(reacted.reactions, {"👍": [self.second_member.name]})
		self.assertEqual(
			{call.kwargs["user"] for call in self.published(publish) if call.args[0] == MESSAGE_UPDATED},
			{self.member.name, self.second_member.name},
		)
		with self.as_user(self.member):
			dm.react(name, "👍")
			dm.react(name, "🎉")
		with self.as_user(self.second_member):
			undone = dm.react(name, "👍")
			[message] = dm.get_messages(sent["conversation"])["messages"]
		self.assertEqual(undone.reactions, {"👍": [self.member.name], "🎉": [self.member.name]})
		self.assertEqual(message.reactions, undone.reactions)

	def test_only_participants_react_and_never_on_deleted_messages(self):
		sent = self.send(self.member, to=self.second_member.name)
		name = sent["message"]["name"]
		for person in (self.outsider, self.admin):
			with self.as_user(person), self.assertRaises(frappe.PermissionError):
				dm.react(name, "👍")
		with self.as_user(self.second_member):
			for emoji in ("", "x" * (dm.MAX_EMOJI_LENGTH + 1)):
				with self.assertRaises(frappe.ValidationError):
					dm.react(name, emoji)
			dm.react(name, "👍")
		with self.as_user(self.member):
			dm.delete_message(name)
		self.assertIsNone(frappe.db.get_value("GP Message", name, "reactions"))
		with self.as_user(self.second_member), self.assertRaises(frappe.ValidationError):
			dm.react(name, "👍")

	def test_distinct_reactions_are_capped(self):
		sent = self.send(self.member, to=self.second_member.name)
		name = sent["message"]["name"]
		with self.as_user(self.second_member):
			for index in range(dm.MAX_REACTIONS):
				dm.react(name, f"e{index}")
			with self.assertRaises(frappe.ValidationError):
				dm.react(name, "one more")
			dm.react(name, "e0")


class TestReadReceipts(DirectMessagesTestCase):
	def seen_by(self, viewer, conversation):
		with self.as_user(viewer):
			return dm.get_messages(conversation)["seen"]

	def seen_events(self, publish):
		return [call for call in publish.call_args_list if call.args[0] == MESSAGES_SEEN]

	def test_you_see_how_far_the_other_person_has_read(self):
		sent = self.send(self.member, to=self.second_member.name)
		conversation = sent["conversation"]
		[before] = self.seen_by(self.member, conversation)
		self.assertEqual(before["user"], self.second_member.name)
		self.assertEqual(before["message"], 0)
		self.assertIsNone(before["at"])
		with self.as_user(self.second_member):
			dm.mark_read(conversation)
		[after] = self.seen_by(self.member, conversation)
		self.assertEqual(after["message"], sent["message"]["name"])
		self.assertIsNotNone(after["at"])
		[sender] = self.seen_by(self.second_member, conversation)
		self.assertEqual(sender["user"], self.member.name)
		self.assertEqual(sender["message"], sent["message"]["name"])

	def test_reading_tells_only_the_others_once(self):
		sent = self.send(self.member, to=self.second_member.name)
		conversation = sent["conversation"]
		with patch("frappe.realtime.publish_realtime") as publish, self.as_user(self.second_member):
			dm.mark_read(conversation)
			dm.mark_read(conversation)
		[call] = self.seen_events(publish)
		self.assertEqual(call.kwargs["user"], self.member.name)
		self.assertTrue(call.kwargs["after_commit"])
		message = call.kwargs["message"]
		self.assertEqual(message["conversation"], conversation)
		self.assertEqual(message["user"], self.second_member.name)
		self.assertEqual(message["message"], sent["message"]["name"])
		self.assertIsNotNone(message["at"])

	def test_opening_a_read_chat_keeps_the_seen_time(self):
		conversation = self.start()
		with self.as_user(self.second_member):
			dm.mark_read(conversation)
		member = {"conversation": conversation, "user": self.second_member.name}
		frappe.db.set_value("GP Conversation Member", member, "last_read_at", "2026-01-01 09:00:00")
		with self.as_user(self.second_member):
			dm.mark_read(conversation)
		[seen] = self.seen_by(self.member, conversation)
		self.assertEqual(str(seen["at"]), "2026-01-01 09:00:00")
		newer = self.send(self.member, conversation=conversation)
		with self.as_user(self.second_member):
			dm.mark_read(conversation)
		[seen] = self.seen_by(self.member, conversation)
		self.assertEqual(seen["message"], newer["message"]["name"])
		self.assertGreater(str(seen["at"]), "2026-01-01 09:00:00")

	def test_mark_all_read_records_the_time_without_live_events(self):
		sent = self.send(self.member, to=self.second_member.name)
		with patch("frappe.realtime.publish_realtime") as publish, self.as_user(self.second_member):
			dm.mark_all_read()
		self.assertEqual(self.seen_events(publish), [])
		[seen] = self.seen_by(self.member, sent["conversation"])
		self.assertEqual(seen["message"], sent["message"]["name"])
		self.assertIsNotNone(seen["at"])


class TestClearConversation(DirectMessagesTestCase):
	def test_deleting_a_chat_hides_it_only_for_you_until_a_new_message(self):
		conversation = self.start()
		self.send(self.member, "<p>Old news</p>", conversation=conversation)
		with patch("frappe.realtime.publish_realtime") as publish, self.as_user(self.second_member):
			self.assertEqual(dm.clear_conversation(conversation), 0)
			self.assertEqual(dm.get_conversations()["conversations"], [])
			self.assertEqual(dm.get_messages(conversation)["messages"], [])
			self.assertEqual(dm.search("Old"), {"conversations": [], "messages": []})
			self.assertEqual(dm.search("membe")["conversations"], [])
		[call] = self.published(publish)
		self.assertEqual(call.args[0], CONVERSATION_CLEARED)
		self.assertEqual(call.kwargs["user"], self.second_member.name)
		with self.as_user(self.member):
			self.assertEqual(len(dm.get_messages(conversation)["messages"]), 2)
		self.send(self.member, "<p>Fresh</p>", conversation=conversation)
		with self.as_user(self.second_member):
			[row] = dm.get_conversations()["conversations"]
			[message] = dm.get_messages(conversation)["messages"]
		self.assertEqual(row["unread_count"], 1)
		self.assertEqual(message.content, "<p>Fresh</p>")

	def test_cannot_reply_or_react_to_messages_you_deleted(self):
		sent = self.send(self.member, to=self.second_member.name)
		with self.as_user(self.second_member):
			dm.clear_conversation(sent["conversation"])
			with self.assertRaises(frappe.PermissionError):
				dm.react(sent["message"]["name"], "👍")
			with self.assertRaises(frappe.ValidationError):
				dm.send_message(
					"<p>Hi</p>", conversation=sent["conversation"], reply_to=sent["message"]["name"]
				)


class TestMarkAllRead(DirectMessagesTestCase):
	def test_reads_every_conversation_and_tells_your_other_tabs(self):
		self.start(self.member, self.second_member)
		self.start(self.outsider, self.second_member)
		with self.as_user(self.second_member):
			self.assertEqual(dm.get_unread_conversation_count(), 2)
			with patch("frappe.realtime.publish_realtime") as publish:
				dm.mark_all_read()
			self.assertEqual(dm.get_unread_conversation_count(), 0)
			rows = dm.get_conversations()["conversations"]
		self.assertEqual([row["unread_count"] for row in rows], [0, 0])
		[call] = self.published(publish)
		self.assertEqual(call.args[0], MESSAGES_READ)
		self.assertEqual(call.kwargs["message"], {"conversation": None, "unread_conversations": 0})
		with self.as_user(self.member):
			self.assertEqual(dm.get_unread_conversation_count(), 0)


class TestAttachments(DirectMessagesTestCase):
	def upload(self, user, name="note.txt"):
		with self.as_user(user):
			return frappe.get_doc(doctype="File", file_name=name, content=b"secret", is_private=1).insert(
				ignore_permissions=True
			)

	def link(self, file):
		return f'<p><a data-attachment="" href="{file.file_url}?fid={file.name}">{file.file_name}</a></p>'

	def can_download(self, file, user):
		with self.as_user(user):
			return frappe.get_doc("File", file.name).is_downloadable()

	def test_only_the_people_in_the_chat_can_open_a_file(self):
		file = self.upload(self.member)
		sent = self.send(self.member, self.link(file), to=self.second_member.name)
		attached = frappe.db.get_value("File", file.name, ["attached_to_doctype", "attached_to_name"])
		self.assertEqual(attached, ("GP Message", str(sent["message"]["name"])))
		self.assertTrue(self.can_download(file, self.second_member))
		self.assertFalse(self.can_download(file, self.outsider))

	def test_someone_elses_file_is_not_attached(self):
		file = self.upload(self.outsider)
		self.send(self.member, self.link(file), to=self.second_member.name)
		self.assertIsNone(frappe.db.get_value("File", file.name, "attached_to_name"))
		self.assertFalse(self.can_download(file, self.second_member))

	def test_an_image_on_its_own_is_a_message_and_previews_as_image(self):
		file = self.upload(self.member, "photo.png")
		sent = self.send(
			self.member, f'<img src="{file.file_url}?fid={file.name}">', to=self.second_member.name
		)
		preview = frappe.db.get_value("GP Conversation", sent["conversation"], "last_message_preview")
		self.assertEqual(preview, "Image")

	def test_deleting_a_message_deletes_its_files(self):
		file = self.upload(self.member)
		sent = self.send(self.member, self.link(file), to=self.second_member.name)
		with self.as_user(self.member):
			dm.delete_message(sent["message"]["name"])
		self.assertFalse(frappe.db.exists("File", file.name))

	def test_a_file_added_while_editing_is_attached(self):
		sent = self.send(self.member, to=self.second_member.name)
		file = self.upload(self.member)
		with self.as_user(self.member):
			dm.edit_message(sent["message"]["name"], self.link(file))
		self.assertTrue(self.can_download(file, self.second_member))


class TestSharedFilesAndLinks(DirectMessagesTestCase):
	def shared(self, user, conversation, kind, **filters):
		with self.as_user(user):
			page = dm.get_shared_messages(conversation, kind, **filters)
		return [message["content"] for message in page["messages"]], page["has_more"]

	def test_files_and_links_are_listed_apart_newest_first(self):
		conversation = self.start()
		file = '<p><a data-attachment="" href="/private/files/plan.pdf">plan.pdf</a></p>'
		image = '<img src="/private/files/photo.png">'
		link = '<p>See <a href="https://example.com/doc">the doc</a></p>'
		for content in (file, link, image):
			self.send(self.member, content, conversation=conversation)
		files, _ = self.shared(self.second_member, conversation, "files")
		links, _ = self.shared(self.second_member, conversation, "links")
		self.assertEqual(len(files), 2)
		self.assertIn("photo.png", files[0])
		self.assertIn("plan.pdf", files[1])
		self.assertEqual(len(links), 1)
		self.assertIn("https://example.com/doc", links[0])

	def test_deleted_and_cleared_messages_are_left_out(self):
		conversation = self.start()
		self.send(self.member, '<p><a href="https://example.com/old">old</a></p>', conversation=conversation)
		gone = self.send(
			self.member, '<p><a href="https://example.com/gone">gone</a></p>', conversation=conversation
		)
		with self.as_user(self.member):
			dm.delete_message(gone["message"]["name"])
		self.assertEqual(len(self.shared(self.second_member, conversation, "links")[0]), 1)
		with self.as_user(self.second_member):
			dm.clear_conversation(conversation)
		self.assertEqual(self.shared(self.second_member, conversation, "links")[0], [])
		self.assertIn("example.com/old", self.shared(self.member, conversation, "links")[0][0])

	def test_search_and_paging(self):
		conversation = self.start()
		for word in ("alpha", "beta", "gamma"):
			self.send(
				self.member,
				f'<p><a href="https://example.com/{word}">{word}</a></p>',
				conversation=conversation,
			)
		links, has_more = self.shared(self.member, conversation, "links", query="beta")
		self.assertEqual(len(links), 1)
		self.assertFalse(has_more)
		with self.as_user(self.member):
			first = dm.get_shared_messages(conversation, "links", limit=2)
			rest = dm.get_shared_messages(
				conversation, "links", before=first["messages"][-1]["name"], limit=2
			)
		self.assertTrue(first["has_more"])
		self.assertIn("gamma", first["messages"][0]["content"])
		self.assertEqual(len(rest["messages"]), 1)
		self.assertIn("alpha", rest["messages"][0]["content"])

	def test_only_the_people_in_the_chat_can_list_it(self):
		conversation = self.start()
		with self.as_user(self.outsider), self.assertRaises(frappe.PermissionError):
			dm.get_shared_messages(conversation, "files")
		with self.as_user(self.member), self.assertRaises(frappe.ValidationError):
			dm.get_shared_messages(conversation, "everything")


class TestNotifications(DirectMessagesTestCase):
	def test_turning_dm_notifications_off_keeps_the_unread_count(self):
		from gameplan.gameplan.doctype.gp_user_profile.gp_user_profile import (
			save_my_notification_preferences,
		)

		with self.as_user(self.second_member):
			save_my_notification_preferences({"direct_message_notifications": 0})
		conversation = self.start()
		self.assertEqual(self.notifications(self.second_member), [])
		self.assertEqual(self.row(conversation, self.second_member).unread_count, 1)
		with self.as_user(self.second_member):
			self.assertEqual(dm.get_unread_conversation_count(), 1)
			save_my_notification_preferences({"direct_message_notifications": 1})
		self.send(self.member, conversation=conversation)
		self.assertEqual(len(self.unread(self.second_member)), 1)

	def notifications(self, user, **filters):
		return frappe.get_all(
			"GP Notification",
			filters={"to_user": user.name, "type": dm.NOTIFICATION_TYPE, **filters},
			fields=["conversation", "message", "read", "event_count", "from_user"],
		)

	def unread(self, user):
		return self.notifications(user, read=0)

	def test_messages_in_one_chat_merge_into_one_row(self):
		conversation = self.start()
		self.send(self.member, conversation=conversation)
		self.send(self.member, conversation=conversation)
		[row] = self.unread(self.second_member)
		name = frappe.db.get_value("User", self.member.name, "full_name")
		self.assertEqual(row.conversation, conversation)
		self.assertEqual(row.event_count, 3)
		self.assertEqual(row.message, f"{name} sent you 3 messages")
		self.assertEqual(row.from_user, self.member.name)
		self.assertEqual(self.notifications(self.member), [])

	def test_each_chat_gets_its_own_row(self):
		self.start()
		self.start(self.outsider, self.second_member)
		self.assertEqual(len(self.unread(self.second_member)), 2)

	def test_opening_the_chat_marks_it_read(self):
		conversation = self.start()
		with self.as_user(self.second_member):
			dm.mark_read(conversation)
		self.assertEqual(self.unread(self.second_member), [])
		self.send(self.member, conversation=conversation)
		[row] = self.unread(self.second_member)
		self.assertEqual(row.event_count, 1)

	def test_muted_chats_do_not_notify(self):
		conversation = self.start()
		with self.as_user(self.second_member):
			dm.set_muted(conversation, True)
		self.assertEqual(self.unread(self.second_member), [])
		self.send(self.member, conversation=conversation)
		self.assertEqual(self.unread(self.second_member), [])
		with self.as_user(self.second_member):
			dm.set_muted(conversation, False)
		self.send(self.member, conversation=conversation)
		self.assertEqual(len(self.unread(self.second_member)), 1)

	def test_mark_all_read_and_clearing_a_chat_clear_its_notification(self):
		first = self.start()
		self.start(self.outsider, self.second_member)
		with self.as_user(self.second_member):
			dm.clear_conversation(first)
		[row] = self.unread(self.second_member)
		self.assertNotEqual(row.conversation, first)
		with self.as_user(self.second_member):
			dm.mark_all_read()
		self.assertEqual(self.unread(self.second_member), [])

	def test_reading_a_chat_leaves_other_notifications_alone(self):
		conversation = self.start()
		other = frappe.get_doc(
			doctype="GP Notification", to_user=self.second_member.name, type="Mention", message="Hi"
		).insert(ignore_permissions=True)
		with self.as_user(self.second_member):
			dm.mark_read(conversation)
			dm.mark_all_read()
		self.assertEqual(frappe.db.get_value("GP Notification", other.name, "read"), 0)

	def test_stays_out_of_emails(self):
		from gameplan.email_digest import get_unread_notifications
		from gameplan.notifications.delivery import deliverable_rows

		self.start()
		types = {row.type for row in get_unread_notifications(self.second_member.name)}
		self.assertNotIn(dm.NOTIFICATION_TYPE, types)
		types = {row.type for row in deliverable_rows(self.second_member.name)}
		self.assertNotIn(dm.NOTIFICATION_TYPE, types)
		[row] = self.unread(self.second_member)

	def test_only_the_recipient_can_see_it(self):
		self.start()
		with self.as_user(self.outsider):
			rows = frappe.get_list("GP Notification", filters={"type": dm.NOTIFICATION_TYPE})
		self.assertEqual(rows, [])


class TestBlock(DirectMessagesTestCase):
	def block(self, user, other):
		with self.as_user(user):
			dm.block_user(other.name)

	def info(self, viewer, user):
		from gameplan.api import user_info_rows

		with self.as_user(viewer):
			[row] = user_info_rows([user.name])
		return row

	def test_neither_side_can_message_the_other(self):
		conversation = self.start()
		self.block(self.member, self.second_member)
		with self.as_user(self.member), self.assertRaisesRegex(frappe.ValidationError, "You blocked"):
			dm.send_message("Hi", conversation=conversation)
		with (
			self.as_user(self.second_member),
			self.assertRaisesRegex(frappe.ValidationError, "not accepting"),
		):
			dm.send_message("Hi", conversation=conversation)
		with (
			self.as_user(self.second_member),
			self.assertRaisesRegex(frappe.ValidationError, "not accepting"),
		):
			dm.send_message("Hi", to=self.member.name)

	def test_unblocking_lets_you_message_again(self):
		conversation = self.start()
		self.block(self.member, self.second_member)
		with self.as_user(self.member):
			dm.unblock_user(self.second_member.name)
		self.send(self.second_member, conversation=conversation)
		self.send(self.member, conversation=conversation)

	def test_both_people_can_still_read_the_old_chat(self):
		conversation = self.start()
		self.block(self.member, self.second_member)
		for user in (self.member, self.second_member):
			with self.as_user(user):
				self.assertEqual(len(dm.get_messages(conversation)["messages"]), 1)

	def test_blocking_twice_keeps_one_row_and_lists_newest_first(self):
		third = self.person("third@example.com", "Third")
		self.block(self.member, self.second_member)
		self.block(self.member, self.second_member)
		self.block(self.member, third)
		self.assertEqual(frappe.db.count("GP User Block", {"user": self.member.name}), 2)
		with self.as_user(self.member):
			self.assertEqual(dm.get_blocked_users(), [third.name, self.second_member.name])
		with self.as_user(self.second_member):
			self.assertEqual(dm.get_blocked_users(), [])

	def test_cannot_block_yourself_or_unknown_people_and_guests_cannot_block(self):
		with self.as_user(self.member):
			for user in (self.member.name, "nobody@example.com"):
				with self.assertRaises(frappe.ValidationError):
					dm.block_user(user)
		with self.as_user(self.guest), self.assertRaises(frappe.PermissionError):
			dm.block_user(self.member.name)
		self.assertEqual(frappe.db.count("GP User Block"), 0)

	def test_the_blocked_person_sees_messages_off_not_a_block(self):
		self.block(self.member, self.second_member)
		mine = self.info(self.member, self.second_member)
		self.assertEqual(mine.blocked, 1)
		self.assertEqual(mine.direct_messages_enabled, 1)
		theirs = self.info(self.second_member, self.member)
		self.assertEqual(theirs.blocked, 0)
		self.assertEqual(theirs.direct_messages_enabled, 0)
		self.assertEqual(self.info(self.outsider, self.member).direct_messages_enabled, 1)

	def test_people_search_for_messages_skips_blocks_both_ways(self):
		self.block(self.member, self.second_member)
		for viewer, other in ((self.member, self.second_member), (self.second_member, self.member)):
			with self.as_user(viewer):
				everyone = [row["name"] for row in search_users(other.full_name)]
				open_only = [row["name"] for row in search_users(other.full_name, direct_messages=True)]
			self.assertIn(other.name, everyone)
			self.assertNotIn(other.name, open_only)

	def test_group_chats_are_not_affected(self):
		conversation = self.start()
		frappe.db.set_value("GP Conversation", conversation, "is_group", 1)
		self.block(self.member, self.second_member)
		self.send(self.second_member, conversation=conversation)
		self.send(self.member, conversation=conversation)

	def test_blocking_tells_both_people(self):
		with patch("frappe.realtime.publish_realtime") as publish:
			self.block(self.member, self.second_member)
		self.assertEqual({call.args[0] for call in self.published(publish)}, {USERS_CHANGED})
