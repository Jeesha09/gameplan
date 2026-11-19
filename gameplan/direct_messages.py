"""Private conversations between people, kept apart from Spaces and everything built on them."""

import hashlib
import json
import re

import frappe
from bs4 import BeautifulSoup
from frappe.query_builder import Order
from frappe.query_builder.functions import Count
from frappe.utils import cint, now_datetime

import gameplan
from gameplan.notifications import records
from gameplan.realtime import (
	notify_conversation_cleared,
	notify_conversation_muted,
	notify_message_received,
	notify_message_updated,
	notify_messages_read,
	notify_messages_seen,
	notify_notification_changed,
	notify_users_changed,
)
from gameplan.roles import has_app_access
from gameplan.utils import remove_empty_leading_lines, remove_empty_trailing_paragraphs
from gameplan.utils.sanitizer import sanitize_content

CONVERSATIONS_PER_PAGE = 30
MESSAGES_PER_PAGE = 50
MAX_PAGE_SIZE = 100
MAX_MESSAGE_LENGTH = 20000
PREVIEW_LENGTH = 140
SEARCH_RESULTS = 20
SEARCH_MIN_LENGTH = 1
SNIPPET_LEAD = 40
WRITE_ATTEMPTS = 3
MAX_EMOJI_LENGTH = 140
MAX_REACTIONS = 20
REPLY_PREVIEW_LENGTH = 100
NOTIFICATION_TYPE = "Direct Message"
MESSAGE_FIELDS = ("name", "owner", "content", "creation", "edited_at", "deleted_at", "reply_to", "reactions")


@frappe.whitelist()
def get_conversations(before: int | None = None, limit: int = CONVERSATIONS_PER_PAGE):
	"""List your conversations, newest first; pass the last row's last_message as before for older ones."""
	require_enabled()
	limit = page_size(limit)
	Member = frappe.qb.DocType("GP Conversation Member")
	query = (
		frappe.qb.from_(Member)
		.select(Member.conversation, Member.last_message, Member.unread_count, Member.muted)
		.where((Member.user == frappe.session.user) & (Member.last_message > Member.cleared_message))
	)
	if before:
		query = query.where(Member.last_message < cint(before))
	rows = query.orderby(Member.last_message, order=Order.desc).limit(limit + 1).run(as_dict=True)
	return {"conversations": with_details(rows[:limit]), "has_more": len(rows) > limit}


@frappe.whitelist()
def get_conversation(conversation: str):
	"""Return one of your conversations with its people, last message and your unread count."""
	row = require_participant(conversation)
	return with_details([row])[0]


@frappe.whitelist()
def get_direct_conversation(user: str):
	"""Return the id of your conversation with a person, or None if you have not talked yet."""
	require_enabled()
	name = frappe.db.get_value("GP Conversation", {"direct_key": direct_key(frappe.session.user, user)})
	return str(name) if name else None


@frappe.whitelist()
def get_messages(
	conversation: str,
	before: int | None = None,
	after: int | None = None,
	around: int | None = None,
	limit: int = MESSAGES_PER_PAGE,
):
	"""Return a page of messages, oldest first, and how far the others have read (seen)."""
	row = require_participant(conversation)
	limit = page_size(limit, MESSAGES_PER_PAGE)
	Message = frappe.qb.DocType("GP Message")
	visible = Message.name > cint(row.cleared_message)
	if around:
		older, has_more = message_page(
			conversation, visible & (Message.name < cint(around)), Order.desc, limit // 2
		)
		newer, has_newer = message_page(
			conversation, visible & (Message.name >= cint(around)), Order.asc, limit - limit // 2
		)
		page = {"messages": present(older + newer), "has_more": has_more, "has_newer": has_newer}
	elif after:
		newer, has_newer = message_page(
			conversation, visible & (Message.name > cint(after)), Order.asc, limit
		)
		page = {"messages": present(newer), "has_more": False, "has_newer": has_newer}
	else:
		condition = visible & (Message.name < cint(before)) if before else visible
		older, has_more = message_page(conversation, condition, Order.desc, limit)
		page = {"messages": present(older), "has_more": has_more, "has_newer": False}
	return page | {"seen": read_cursors(str(conversation))}


@frappe.whitelist()
def get_shared_messages(
	conversation: str,
	kind: str = "files",
	query: str | None = None,
	before: int | None = None,
	limit: int = MESSAGES_PER_PAGE,
):
	"""Return messages sharing files or links (kind), newest first, matching query; before pages back."""
	row = require_participant(conversation)
	Message = frappe.qb.DocType("GP Message")
	if kind == "files":
		shares = (
			Message.content.like("%data-attachment%")
			| Message.content.like("%<img%")
			| Message.content.like("%<video%")
		)
	elif kind == "links":
		shares = Message.content.like('%href="http%')
	else:
		frappe.throw("Ask for files or links")
	condition = (Message.name > cint(row.cleared_message)) & Message.deleted_at.isnull() & shares
	if before:
		condition &= Message.name < cint(before)
	if query := " ".join((query or "").split()):
		condition &= Message.content.like(f"%{query}%")
	rows, has_more = message_page(conversation, condition, Order.desc, page_size(limit, MESSAGES_PER_PAGE))
	messages = [
		{"name": row.name, "owner": row.owner, "creation": str(row.creation), "content": row.content}
		for row in reversed(rows)
	]
	return {"messages": messages, "has_more": has_more}


@frappe.whitelist()
def get_unread_conversation_count():
	"""Return how many of your unmuted conversations have unread messages."""
	require_app_access()
	if not messages_enabled(frappe.session.user):
		return 0
	return unread_conversation_counts([frappe.session.user]).get(frappe.session.user, 0)


@frappe.whitelist()
def search(query: str):
	"""Find your conversations by the other person's name, and your messages by their text."""
	require_enabled()
	query = " ".join((query or "").split())
	if len(query) < SEARCH_MIN_LENGTH:
		return {"conversations": [], "messages": []}
	return {"conversations": search_people(query), "messages": search_messages(query)}


@frappe.whitelist(methods=["POST"])
def send_message(
	content: str, conversation: str | None = None, to: str | None = None, reply_to: int | None = None
):
	"""Send a message to a conversation or a person (to); reply_to quotes a message in that conversation."""
	require_member()
	if bool(conversation) == bool(to):
		frappe.throw("Choose a conversation or a person")
	if conversation:
		row = require_participant(conversation)
		require_others_enabled(conversation)
	else:
		require_recipient(to)
		if not frappe.db.exists("GP Conversation", {"direct_key": direct_key(frappe.session.user, to)}):
			from gameplan.site_settings import require_can_start_conversation

			require_can_start_conversation()
	reply_to = cint(reply_to) or None
	if reply_to:
		original = frappe.db.get_value("GP Message", reply_to, ["conversation", "deleted_at"], as_dict=True)
		if (
			not conversation
			or not original
			or str(original.conversation) != str(conversation)
			or reply_to <= cint(row.cleared_message)
		):
			frappe.throw("You can only reply to a message in this conversation")
		if original.deleted_at:
			frappe.throw("This message was deleted")
	content = clean_content(content)
	sender = frappe.session.user
	return retry_write(lambda: deliver(sender, content, conversation and str(conversation), to, reply_to))


@frappe.whitelist(methods=["POST"])
def edit_message(message: int, content: str):
	"""Change the text of a message you sent."""
	row = require_own_message(message)
	content = clean_content(content)
	return retry_write(lambda: update_message(row, {"content": content, "edited_at": now_datetime()}))


@frappe.whitelist(methods=["POST"])
def delete_message(message: int):
	"""Delete a message you sent; it disappears for everyone in the conversation."""
	row = require_own_message(message)
	return retry_write(
		lambda: update_message(row, {"content": "", "deleted_at": now_datetime(), "reactions": None})
	)


@frappe.whitelist(methods=["POST"])
def react(message: int, emoji: str):
	"""Add your emoji reaction to a message, or take it back if you already reacted with it."""
	require_member()
	emoji = (emoji or "").strip()
	if not emoji or len(emoji) > MAX_EMOJI_LENGTH:
		frappe.throw("Pick an emoji to react with")
	conversation = frappe.db.get_value("GP Message", cint(message), "conversation")
	if not conversation:
		frappe.throw("Not permitted", frappe.PermissionError)
	member = require_participant(conversation)
	return retry_write(lambda: toggle_reaction(cint(message), emoji, member))


@frappe.whitelist(methods=["POST"])
def clear_conversation(conversation: str):
	"""Delete a conversation from your list; the other person keeps it, and new messages bring it back."""
	row = require_participant(conversation)
	Member = frappe.qb.DocType("GP Conversation Member")
	(
		frappe.qb.update(Member)
		.set(Member.cleared_message, cint(row.last_message))
		.set(Member.last_read_message, Member.last_message)
		.set(Member.last_read_at, now_datetime())
		.set(Member.unread_count, 0)
		.where((Member.conversation == str(conversation)) & (Member.user == frappe.session.user))
	).run()
	clear_notifications(frappe.session.user, str(conversation))
	unread = get_unread_conversation_count()
	notify_conversation_cleared(frappe.session.user, str(conversation), unread)
	return unread


@frappe.whitelist(methods=["POST"])
def mark_all_read():
	"""Mark every one of your conversations as read."""
	require_enabled()
	Member = frappe.qb.DocType("GP Conversation Member")
	(
		frappe.qb.update(Member)
		.set(Member.last_read_message, Member.last_message)
		.set(Member.last_read_at, now_datetime())
		.set(Member.unread_count, 0)
		.where((Member.user == frappe.session.user) & (Member.unread_count > 0))
	).run()
	clear_notifications(frappe.session.user)
	notify_messages_read(frappe.session.user, None, 0)


@frappe.whitelist(methods=["POST"])
def mark_read(conversation: str):
	"""Mark a conversation as read up to its latest message; the others see that you have seen it."""
	row = require_participant(conversation)
	if row.unread_count or row.last_read_message != row.last_message:
		retry_write(lambda: clear_unread(str(conversation)))
		[seen] = read_cursors(str(conversation), mine=True)
		others = [user for user in members(str(conversation)) if user != frappe.session.user]
		notify_messages_seen(others, str(conversation), seen)
	clear_notifications(frappe.session.user, str(conversation))
	notify_messages_read(frappe.session.user, str(conversation), get_unread_conversation_count())


@frappe.whitelist(methods=["POST"])
def set_muted(conversation: str, muted: bool):
	"""Mute or unmute a conversation; muted ones stay out of your unread total."""
	require_participant(conversation)
	muted = 1 if cint(muted) else 0
	Member = frappe.qb.DocType("GP Conversation Member")
	(
		frappe.qb.update(Member)
		.set(Member.muted, muted)
		.where((Member.conversation == str(conversation)) & (Member.user == frappe.session.user))
	).run()
	if muted:
		clear_notifications(frappe.session.user, str(conversation))
	unread = get_unread_conversation_count()
	notify_conversation_muted(frappe.session.user, str(conversation), muted, unread)
	return unread


@frappe.whitelist(methods=["POST"])
def set_direct_messages_enabled(enabled: bool):
	"""Turn direct messages on or off for yourself; while off, nobody can message you."""
	require_member()
	profile = frappe.db.get_value("GP User Profile", {"user": frappe.session.user})
	if not profile:
		frappe.throw("Could not find your profile")
	frappe.db.set_value("GP User Profile", profile, "direct_messages_enabled", 1 if cint(enabled) else 0)
	notify_users_changed(profile)
	return get_unread_conversation_count()


@frappe.whitelist(methods=["POST"])
def block_user(user: str):
	"""Block a person: neither of you can message the other until you unblock them."""
	require_member()
	if user == frappe.session.user:
		frappe.throw("You cannot block yourself")
	if not frappe.db.exists("User", user):
		frappe.throw("Could not find this person")
	if not frappe.db.exists("GP User Block", {"user": frappe.session.user, "blocked_user": user}):
		frappe.get_doc(doctype="GP User Block", user=frappe.session.user, blocked_user=user).insert(
			ignore_permissions=True
		)
	notify_block_changed(user)


@frappe.whitelist(methods=["POST"])
def unblock_user(user: str):
	"""Unblock a person you blocked, so you can message each other again."""
	require_member()
	frappe.db.delete("GP User Block", {"user": frappe.session.user, "blocked_user": user})
	notify_block_changed(user)


@frappe.whitelist()
def get_blocked_users():
	"""List the people you have blocked, most recent first."""
	require_member()
	return frappe.get_all(
		"GP User Block", filters={"user": frappe.session.user}, pluck="blocked_user", order_by="name desc"
	)


def deliver(sender, content, conversation, to, reply_to=None):
	conversation = conversation or direct_conversation(sender, to)
	frappe.db.get_value("GP Conversation", conversation, "name", for_update=True)
	message = frappe.get_doc(
		doctype="GP Message", conversation=conversation, content=content, reply_to=reply_to
	).insert(ignore_permissions=True)
	message.attach_files_in_content()
	frappe.db.set_value(
		"GP Conversation",
		conversation,
		{
			"last_message": message.name,
			"last_message_at": message.creation,
			"last_message_by": sender,
			"last_message_preview": preview(content),
		},
		update_modified=False,
	)
	Member = frappe.qb.DocType("GP Conversation Member")
	in_conversation = Member.conversation == conversation
	(
		frappe.qb.update(Member)
		.set(Member.last_message, message.name)
		.set(Member.unread_count, Member.unread_count + 1)
		.where(in_conversation & (Member.user != sender))
	).run()
	(
		frappe.qb.update(Member)
		.set(Member.last_message, message.name)
		.set(Member.last_read_message, message.name)
		.set(Member.last_read_at, message.creation)
		.set(Member.unread_count, 0)
		.where(in_conversation & (Member.user == sender))
	).run()
	notify_recipients(sender, conversation)
	row = present(
		[
			{
				"name": message.name,
				"owner": sender,
				"content": content,
				"creation": message.creation,
				"edited_at": None,
				"deleted_at": None,
				"reply_to": reply_to,
				"reactions": None,
			}
		]
	)[0]
	users = members(conversation)
	notify_message_received(users, conversation, row, unread_conversation_counts(users))
	return {"conversation": conversation, "message": row}


def update_message(row, values):
	conversation = str(row.conversation)
	last_message = frappe.db.get_value("GP Conversation", conversation, "last_message", for_update=True)
	frappe.db.set_value("GP Message", row.name, values, update_modified=False)
	if values.get("deleted_at"):
		delete_attachments(row.name)
	elif values.get("content"):
		frappe.get_doc("GP Message", row.name).attach_files_in_content()
	if cint(last_message) == cint(row.name):
		latest = {"content": values["content"]}
		if values.get("deleted_at"):
			latest = frappe.db.get_value(
				"GP Message",
				{"conversation": conversation, "deleted_at": ["is", "not set"]},
				["content", "owner"],
				order_by="name desc",
				as_dict=True,
			) or {"content": ""}
		frappe.db.set_value(
			"GP Conversation",
			conversation,
			{"last_message_preview": preview(latest["content"])}
			| ({"last_message_by": latest["owner"]} if latest.get("owner") else {}),
			update_modified=False,
		)
	message = present([{field: row.get(field) for field in MESSAGE_FIELDS} | values])[0]
	notify_message_updated(members(conversation), conversation, message)
	return message


def toggle_reaction(message, emoji, member):
	row = frappe.db.get_value(
		"GP Message", message, ["conversation", *MESSAGE_FIELDS], as_dict=True, for_update=True
	)
	if row.deleted_at:
		frappe.throw("This message was deleted")
	if message <= cint(member.cleared_message):
		frappe.throw("Not permitted", frappe.PermissionError)
	reactions = reactions_of(row)
	user = frappe.session.user
	users = reactions.get(emoji, [])
	if user in users:
		users.remove(user)
	else:
		if emoji not in reactions and len(reactions) >= MAX_REACTIONS:
			frappe.throw(f"A message can have up to {MAX_REACTIONS} different reactions")
		users.append(user)
	reactions[emoji] = users
	reactions = {key: value for key, value in reactions.items() if value}
	frappe.db.set_value(
		"GP Message",
		message,
		"reactions",
		json.dumps(reactions, ensure_ascii=False) if reactions else None,
		update_modified=False,
	)
	row.reactions = reactions
	updated = present([row])[0]
	notify_message_updated(members(str(row.conversation)), str(row.conversation), updated)
	return updated


def reactions_of(row):
	reactions = row.get("reactions")
	if isinstance(reactions, str):
		reactions = frappe.parse_json(reactions)
	return dict(reactions or {})


def present(rows):
	replies = {}
	reply_ids = {cint(row.get("reply_to")) for row in rows if row.get("reply_to")}
	if reply_ids:
		for original in frappe.get_all(
			"GP Message",
			filters={"name": ["in", list(reply_ids)]},
			fields=["name", "owner", "content", "deleted_at"],
		):
			replies[cint(original.name)] = {
				"name": cint(original.name),
				"owner": original.owner,
				"snippet": "" if original.deleted_at else summary(original.content)[:REPLY_PREVIEW_LENGTH],
				"deleted": bool(original.deleted_at),
			}
	messages = []
	for row in rows:
		message = frappe._dict({field: row.get(field) for field in MESSAGE_FIELDS})
		for field in ("creation", "edited_at", "deleted_at"):
			if message[field]:
				message[field] = str(message[field])
		message["reactions"] = {} if message["deleted_at"] else reactions_of(message)
		message["reply"] = replies.get(cint(message["reply_to"])) if message["reply_to"] else None
		messages.append(message)
	return messages


def message_page(conversation, condition, order, limit):
	Message = frappe.qb.DocType("GP Message")
	query = frappe.qb.from_(Message).select(*MESSAGE_FIELDS).where(Message.conversation == str(conversation))
	if condition is not None:
		query = query.where(condition)
	rows = query.orderby(Message.name, order=order).limit(limit + 1).run(as_dict=True)
	page = rows[:limit]
	return (page[::-1] if order == Order.desc else page), len(rows) > limit


def search_people(query):
	Me = frappe.qb.DocType("GP Conversation Member").as_("me")
	Other = frappe.qb.DocType("GP Conversation Member").as_("other")
	User = frappe.qb.DocType("User")
	rows = (
		frappe.qb.from_(Me)
		.join(Other)
		.on(Other.conversation == Me.conversation)
		.join(User)
		.on(User.name == Other.user)
		.select(Me.conversation, Me.last_message, Me.unread_count, Me.muted)
		.distinct()
		.where(
			(Me.user == frappe.session.user)
			& (Me.last_message > Me.cleared_message)
			& (Other.user != frappe.session.user)
			& starts_a_word(User.full_name, query)
		)
		.orderby(Me.last_message, order=Order.desc)
		.limit(SEARCH_RESULTS)
	).run(as_dict=True)
	return with_details(rows)


def starts_a_word(field, query):
	return field.like(f"{query}%") | field.like(f"% {query}%") | field.like(f"%>{query}%")


def search_messages(query):
	Member = frappe.qb.DocType("GP Conversation Member")
	Message = frappe.qb.DocType("GP Message")
	rows = (
		frappe.qb.from_(Member)
		.join(Message)
		.on(Message.conversation == Member.conversation)
		.select(Message.name, Message.conversation, Message.owner, Message.content, Message.creation)
		.where(
			(Member.user == frappe.session.user)
			& (Message.name > Member.cleared_message)
			& Message.deleted_at.isnull()
			& starts_a_word(Message.content, query)
		)
		.orderby(Message.name, order=Order.desc)
		.limit(SEARCH_RESULTS * 3)
	).run(as_dict=True)
	word = re.compile(r"(?<!\w)" + re.escape(query), re.IGNORECASE)
	hits = []
	for row in rows:
		text = plain_text(row.content)
		match = word.search(text)
		if not match:
			continue
		start = max(match.start() - SNIPPET_LEAD, 0)
		if start:
			space = text.find(" ", start, match.start())
			start = space + 1 if space >= 0 else match.start()
		hits.append(
			{
				"name": row.name,
				"conversation": str(row.conversation),
				"owner": row.owner,
				"creation": str(row.creation),
				"snippet": ("…" if start else "") + text[start : start + PREVIEW_LENGTH],
			}
		)
		if len(hits) == SEARCH_RESULTS:
			break
	people = people_in({hit["conversation"] for hit in hits})
	for hit in hits:
		hit["people"] = people.get(hit["conversation"], [])
	return hits


def direct_conversation(sender, recipient):
	key = direct_key(sender, recipient)
	existing = frappe.db.get_value("GP Conversation", {"direct_key": key})
	if existing:
		return str(existing)
	conversation = frappe.get_doc(doctype="GP Conversation", direct_key=key).insert(ignore_permissions=True)
	for user in (sender, recipient):
		frappe.get_doc(
			doctype="GP Conversation Member", conversation=str(conversation.name), user=user
		).insert(ignore_permissions=True)
	return str(conversation.name)


def notify_recipients(sender, conversation):
	recipients = frappe.get_all(
		"GP Conversation Member",
		filters={"conversation": conversation, "user": ["!=", sender], "muted": 0},
		pluck="user",
	)
	if recipients:
		recipients = frappe.get_all(
			"GP User Profile",
			filters={"user": ["in", recipients], "direct_message_notifications": 1},
			pluck="user",
		)
	if not recipients:
		return
	name = frappe.db.get_value("User", sender, "full_name") or sender
	for user in recipients:
		records.write_or_merge(
			to_user=user,
			type=NOTIFICATION_TYPE,
			message=f"{name} sent you a message",
			merge=True,
			merged_message=f"{name} sent you {{count}} messages",
			from_user=sender,
			keep_sender=True,
			conversation=conversation,
		)


def clear_notifications(user, conversation=None):
	Notification = frappe.qb.DocType("GP Notification")
	unread = (
		(Notification.to_user == user) & (Notification.type == NOTIFICATION_TYPE) & (Notification.read == 0)
	)
	if conversation:
		unread &= Notification.conversation == conversation
	if not frappe.qb.from_(Notification).select(Notification.name).where(unread).limit(1).run():
		return
	frappe.qb.update(Notification).set(Notification.read, 1).where(unread).run()
	notify_notification_changed(user)


def clear_unread(conversation):
	Member = frappe.qb.DocType("GP Conversation Member")
	(
		frappe.qb.update(Member)
		.set(Member.last_read_message, Member.last_message)
		.set(Member.last_read_at, now_datetime())
		.set(Member.unread_count, 0)
		.where((Member.conversation == conversation) & (Member.user == frappe.session.user))
	).run()


def read_cursors(conversation, mine=False):
	return [
		{"user": row.user, "message": cint(row.last_read_message), "at": row.last_read_at}
		for row in frappe.get_all(
			"GP Conversation Member",
			filters={
				"conversation": conversation,
				"user": frappe.session.user if mine else ["!=", frappe.session.user],
			},
			fields=["user", "last_read_message", "last_read_at"],
		)
	]


def retry_write(write):
	for attempt in range(1, WRITE_ATTEMPTS + 1):
		try:
			return write()
		except (frappe.QueryDeadlockError, frappe.UniqueValidationError):
			if attempt == WRITE_ATTEMPTS:
				raise
			frappe.clear_messages()
			frappe.db.rollback()


def with_details(rows):
	names = [str(row.conversation) for row in rows]
	conversations = {
		str(row.name): row
		for row in frappe.get_all(
			"GP Conversation",
			filters={"name": ["in", names]},
			fields=["name", "is_group", "last_message_at", "last_message_by", "last_message_preview"],
		)
	}
	people = people_in(names)
	return [
		{
			"name": name,
			"is_group": conversations[name].is_group,
			"people": people.get(name, []),
			"last_message": row.last_message,
			"last_message_at": conversations[name].last_message_at,
			"last_message_by": conversations[name].last_message_by,
			"last_message_preview": conversations[name].last_message_preview,
			"unread_count": row.unread_count,
			"muted": row.muted,
		}
		for name, row in zip(names, rows, strict=True)
	]


def people_in(conversations):
	people = {}
	if not conversations:
		return people
	for row in frappe.get_all(
		"GP Conversation Member",
		filters={"conversation": ["in", list(conversations)]},
		fields=["conversation", "user"],
	):
		if row.user != frappe.session.user:
			people.setdefault(str(row.conversation), []).append(row.user)
	return people


def members(conversation):
	return frappe.get_all("GP Conversation Member", filters={"conversation": conversation}, pluck="user")


def unread_conversation_counts(users):
	Member = frappe.qb.DocType("GP Conversation Member")
	rows = (
		frappe.qb.from_(Member)
		.select(Member.user, Count("*"))
		.where(Member.user.isin(users) & (Member.unread_count > 0) & (Member.muted == 0))
		.groupby(Member.user)
	).run()
	return dict(rows)


def messages_enabled(user):
	return bool(frappe.db.get_value("GP User Profile", {"user": user}, "direct_messages_enabled"))


def require_app_access():
	from gameplan.site_settings import feature_enabled

	if not has_app_access():
		frappe.throw("Not permitted", frappe.PermissionError)
	if not feature_enabled("direct_messages_enabled"):
		frappe.throw("Direct messages are turned off on this site", frappe.PermissionError)


def require_enabled():
	require_app_access()
	if not messages_enabled(frappe.session.user):
		frappe.throw("Turn on direct messages in Settings to use Messages", frappe.PermissionError)


def require_member():
	require_app_access()
	if gameplan.is_guest():
		frappe.throw("Guests cannot send direct messages", frappe.PermissionError)


def require_participant(conversation):
	require_enabled()
	row = frappe.db.get_value(
		"GP Conversation Member",
		{"conversation": str(conversation), "user": frappe.session.user},
		["conversation", "last_message", "last_read_message", "unread_count", "muted", "cleared_message"],
		as_dict=True,
	)
	if not row:
		frappe.throw("Not permitted", frappe.PermissionError)
	return row


def require_own_message(message):
	require_member()
	row = frappe.db.get_value("GP Message", cint(message), ["conversation", *MESSAGE_FIELDS], as_dict=True)
	if not row or row.owner != frappe.session.user:
		frappe.throw("Not permitted", frappe.PermissionError)
	require_participant(row.conversation)
	if row.deleted_at:
		frappe.throw("This message was deleted")
	return row


def require_recipient(user):
	if user == frappe.session.user:
		frappe.throw("You cannot message yourself")
	if (
		not frappe.db.get_value("User", user, "enabled")
		or not has_app_access(user)
		or gameplan.is_guest(user)
		or not messages_enabled(user)
	):
		frappe.throw("You cannot message this person")
	require_not_blocked(user)


def require_others_enabled(conversation):
	others = [user for user in members(conversation) if user != frappe.session.user]
	enabled = frappe.get_all(
		"GP User Profile",
		filters={"user": ["in", others], "direct_messages_enabled": 1},
		pluck="user",
	)
	if len(enabled) < len(others):
		frappe.throw("This person is not accepting direct messages")
	if len(others) == 1 and not frappe.db.get_value("GP Conversation", conversation, "is_group"):
		require_not_blocked(others[0])


def require_not_blocked(user):
	blocked, blocked_me = blocks_with(frappe.session.user, [user])
	if blocked:
		frappe.throw("You blocked this person. Unblock them to send a message")
	if blocked_me:
		frappe.throw("This person is not accepting direct messages")


def blocks_with(user, others):
	"""Split others into the people user blocked and the people who blocked user."""
	if not others:
		return set(), set()
	Block = frappe.qb.DocType("GP User Block")
	rows = (
		frappe.qb.from_(Block)
		.select(Block.user, Block.blocked_user)
		.where(
			((Block.user == user) & Block.blocked_user.isin(others))
			| ((Block.blocked_user == user) & Block.user.isin(others))
		)
	).run(as_dict=True)
	blocked = {row.blocked_user for row in rows if row.user == user}
	blocked_me = {row.user for row in rows if row.blocked_user == user}
	return blocked, blocked_me


def notify_block_changed(user):
	profiles = frappe.get_all(
		"GP User Profile", filters={"user": ["in", [frappe.session.user, user]]}, pluck="name"
	)
	for profile in profiles:
		notify_users_changed(profile)


def clean_content(content):
	content = remove_empty_leading_lines(remove_empty_trailing_paragraphs(sanitize_content(content or "")))
	if not summary(content):
		frappe.throw("Write a message first")
	if len(content) > MAX_MESSAGE_LENGTH:
		frappe.throw(f"Messages can be up to {MAX_MESSAGE_LENGTH} characters")
	return content


def plain_text(html):
	return " ".join(BeautifulSoup(html, "html.parser").get_text(" ").split())


def preview(html):
	return summary(html)[:PREVIEW_LENGTH]


def summary(html):
	if text := plain_text(html):
		return text
	soup = BeautifulSoup(html, "html.parser")
	if soup.find("img"):
		return "Image"
	if soup.find("video"):
		return "Video"
	return ""


def can_read_attachment(file, user=None):
	if file.attached_to_doctype != "GP Message" or not file.attached_to_name:
		return False
	conversation = frappe.db.get_value("GP Message", cint(file.attached_to_name), "conversation")
	return bool(
		conversation
		and frappe.db.exists(
			"GP Conversation Member", {"conversation": conversation, "user": user or frappe.session.user}
		)
	)


def delete_attachments(message):
	files = frappe.get_all(
		"File", filters={"attached_to_doctype": "GP Message", "attached_to_name": str(message)}, pluck="name"
	)
	for file in files:
		frappe.delete_doc("File", file, ignore_permissions=True)


def direct_key(first, second):
	return hashlib.sha256("\0".join(sorted((first, second))).encode()).hexdigest()


def page_size(limit, default=CONVERSATIONS_PER_PAGE):
	return min(max(cint(limit) or default, 1), MAX_PAGE_SIZE)
