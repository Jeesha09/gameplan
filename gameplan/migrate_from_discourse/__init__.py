# Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and Contributors
# MIT License. See license.txt


import json
import os
import re
import time
from collections import Counter
from functools import partial
from html import escape
from posixpath import splitext
from urllib.parse import unquote

import frappe
import psutil
import psycopg2
from bs4 import BeautifulSoup
from frappe.core.doctype.file.utils import get_content_hash, get_safe_file_name
from frappe.database.sequence import get_next_val, set_next_val
from frappe.model.naming import append_number_if_name_exists
from frappe.utils import (
	get_files_path,
	get_system_timezone,
	now,
	update_progress_bar,
	validate_email_address,
)
from psycopg2.extras import DictCursor

from gameplan.gameplan.doctype.gp_project.gp_project import DEFAULT_SPACE_ICON
from gameplan.search_sqlite import rebuild_index
from gameplan.utils import remove_empty_trailing_paragraphs, url_safe_slug
from gameplan.utils.sanitizer import sanitize_content
from gameplan.visibility import VISIBILITY_GENERAL, VISIBILITY_MEMBER_ACCESS

from .emojis import get_emoji

COMMUNITIES = {
	"ERPNext": [6, 7, 8, 9, 10, 11, 19, 26, 34, 40, 46, 53, 54, 55, 56, 57, 59, 60, 65],
	"Framework & Development": [5, 12, 16, 18, 24, 28, 30, 32, 13, 21, 29, 33, 27, 77],
	"Business Apps": [89, 69, 70, 74, 76, 82, 22, 58, 23],
	"Productivity Suite": [90, 72, 75, 80, 93, 83, 84, 92],
	"Community": [37, 15, 25, 35, 38, 50, 52, 61, 78, 81, 87, 88, 63, 62, 91, 3, 47, 42, 4, 2, 41, 44, 45],
	"Announcements": [20],
	"Events": [79, 85],
}
GENERAL_SPACES = {6, 37, 89, 90}
FOLDED_CATEGORIES = {48: 47, 49: 47}
ADMINS_GROUP = 1
TITLE_LENGTH = 140
FILE_NAME_LENGTH = 140
FILE_NAME_BYTES = 255
FILE_NAME_ATTEMPTS = 5
FORUM_UPLOAD = re.compile(r"^(?:(?:https?:)?//discuss\.frappe\.io)?/uploads/default/([^?#]+)")
OPTIMIZED_UPLOAD = re.compile(r"^optimized/.+/([0-9a-f]{40})_\d+_\d+x\d+\.\w+$")

OPTIONS = {
	"postgres": None,
	"uploads_folder": None,
	"log_folder": None,
	"steps": ["users", "categories", "topics", "backlinks"],
	"category_ids": None,
	"topic_ids": None,
	"user_ids": None,
	"users_from_topics": False,
	"batch_size": 500,
	"dry_run": False,
}

config = frappe._dict()
outcomes = Counter()
writes = Counter()
pending_files = []
id_map = {}
loaded_tables = set()
file_hashes = {}
memory_added = []
spaces = {}
tag_ids = {}
batch = frappe._dict()
DELETED_USER = frappe._dict(
	id="deleted",
	username="",
	full_name="Deleted user",
	email="deleted-user@discourse.invalid",
	active=False,
	suspended_till=None,
	created_at=None,
)
SYSTEM_USER = frappe._dict(
	id=-1,
	username="",
	full_name="System",
	email="system@discourse.invalid",
	active=False,
	suspended_till=None,
	created_at=None,
)
DISCUSSION_META_FIELDS = (
	"comments_count",
	"participants_count",
	"last_post_type",
	"last_post",
	"last_post_at",
	"last_post_by",
)
POST_FILTER = """posts.deleted_at is null and not posts.hidden and posts.post_type = 1
	and coalesce(posts.user_id, 0) <> -2"""


def execute(**options):
	load_config(options)
	frappe.flags.in_import = True
	start_run()
	if not config.dry_run:
		clean_pending_files()
		frappe.db.add_index("Discourse ID Map", ["discourse_table", "discourse_id"])
		clear_data(
			[
				# 'GP Project',
				# 'GP Team',
				# 'GP Discussion'
				# 'User'
			]
		)
	try:
		load_file_hashes()
		if {"users", "topics"} & set(config.steps):
			create_placeholder_users()
		for step, migrate in get_steps().items():
			if step in config.steps:
				migrate()
	except BaseException:
		if not config.dry_run:
			frappe.db.rollback()
			clean_pending_files()
		raise
	finally:
		finish_run()


def get_steps():
	return {
		"users": migrate_users,
		"categories": migrate_categories,
		"topics": migrate_posts,
		"backlinks": migrate_backlinks,
	}


def load_config(options):
	site_options = frappe.conf.get("discourse_migration") or {}
	unknown = (set(site_options) | set(options)) - set(OPTIONS)
	if unknown:
		frappe.throw(f"Unknown discourse_migration options: {', '.join(sorted(unknown))}")

	config.clear()
	config.update(OPTIONS)
	config.update(site_options)
	config.update(options)

	if isinstance(config.steps, str):
		config.steps = [step.strip() for step in config.steps.split(",")]
	unknown_steps = set(config.steps) - set(get_steps())
	if unknown_steps:
		frappe.throw(f"Unknown steps: {', '.join(sorted(unknown_steps))}")

	for key in ("postgres", "uploads_folder", "log_folder"):
		if not config.get(key):
			frappe.throw(f"Set discourse_migration.{key} in site_config.json")

	for key in ("category_ids", "topic_ids", "user_ids"):
		ids = config.get(key)
		if ids and not (isinstance(ids, list | tuple) and all(isinstance(i, int) for i in ids)):
			frappe.throw(f"{key} must be a list of ids")


def start_run():
	outcomes.clear()
	writes.clear()
	for cache in (id_map, loaded_tables, file_hashes, memory_added, spaces, tag_ids, batch):
		cache.clear()
	config.started_at = time.monotonic()
	stamp = now().replace(" ", "_").replace(":", "-").split(".")[0]
	mode = "dry-run" if config.dry_run else "run"
	config.failure_log = os.path.join(config.log_folder, f"{frappe.local.site}-{mode}-{stamp}.jsonl")
	log(f"{mode} started · steps {', '.join(config.steps)} · batch size {config.batch_size}")


def finish_run():
	if config.dry_run:
		frappe.db.rollback()

	minutes = (time.monotonic() - config.started_at) / 60
	log(f"finished in {minutes:.1f} min · rss {get_rss()} MB")
	row_outcomes = ("done", "skipped", "failed")
	steps = dict.fromkeys(step for step, outcome in outcomes if outcome in row_outcomes)
	for step in steps:
		done, skipped, failed = (outcomes[step, outcome] for outcome in row_outcomes)
		log(f"  {step}: done {done} · skipped {skipped} · failed {failed}")
	for (step, outcome), count in outcomes.items():
		if outcome not in row_outcomes:
			log(f"  {step} {outcome}: {count}")

	if config.dry_run:
		for doctype, count in sorted(writes.items()):
			log(f"  would write {doctype}: {count}")

	if any(outcome == "failed" for _, outcome in outcomes):
		log(f"  failures: {config.failure_log}")


def log(message):
	print(message, flush=True)  # nosemgrep: frappe-print-statement-in-init-files


def get_rss():
	return psutil.Process().memory_info().rss // 2**20


def log_failure(step, discourse_id):
	error = frappe.get_traceback()
	with open(config.failure_log, "a") as f:
		f.write(json.dumps({"step": step, "discourse_id": discourse_id, "at": now(), "error": error}) + "\n")
	log(f"  failed {step} {discourse_id}: {error.strip().splitlines()[-1]}")


def run_batches(step, table, fetch_batch, migrate_row, on_mapped=None):
	last_id = 0
	batch_number = 0
	while rows := fetch_batch(last_id, config.batch_size):
		started_at = time.monotonic()
		batch_number += 1
		last_id = rows[-1].id
		mapped = get_mapped_ids(table, {row.id for row in rows})
		for row in rows:
			if row.id in mapped:
				outcomes[step, "skipped"] += 1
				if on_mapped:
					on_mapped(row)
				continue
			run_row(step, row.id, partial(migrate_row, row))

		if not config.dry_run:
			frappe.db.commit()
			clear_pending_files()
		memory_added.clear()

		per_minute = len(rows) / max(time.monotonic() - started_at, 0.001) * 60
		log(
			f"[{step}] batch {batch_number} · up to id {last_id}"
			f" · done {outcomes[step, 'done']} · skipped {outcomes[step, 'skipped']}"
			f" · failed {outcomes[step, 'failed']} · {per_minute:.0f} rows/min · rss {get_rss()} MB"
		)


def run_row(step, discourse_id, migrate):
	savepoint = f"{step}_{discourse_id}"
	first_file = len(pending_files)
	first_memory = len(memory_added)
	frappe.db.savepoint(savepoint)
	try:
		result = migrate()
	except Exception:
		frappe.db.rollback(save_point=savepoint)
		delete_orphan_files(pending_files[first_file:])
		for cache, key in memory_added[first_memory:]:
			cache.pop(key, None)
		del memory_added[first_memory:]
		outcomes[step, "failed"] += 1
		log_failure(step, discourse_id)
	else:
		frappe.db.release_savepoint(savepoint)
		outcomes[step, "done"] += 1
		return result


def get_mapped_ids(table, ids):
	mapped = frappe.get_all(
		"Discourse ID Map",
		filters={"discourse_table": table, "discourse_id": ("in", [str(i) for i in ids])},
		pluck="discourse_id",
	)
	return {int(i) for i in mapped}


def remember(cache, key, value):
	cache[key] = value
	memory_added.append((cache, key))
	return value


def set_defaults(doc):
	doc.update_if_missing(frappe.new_doc(doc.doctype, as_dict=True))


def insert(doc, **kwargs):
	writes[doc.doctype] += 1
	set_defaults(doc)
	if not config.dry_run:
		doc.insert(**kwargs)


def get_pending_files_path():
	return os.path.join(config.log_folder, f"{frappe.local.site}-pending-files.txt")


def track_file(file_url):
	pending_files.append(file_url)
	with open(get_pending_files_path(), "a") as f:
		f.write(file_url + "\n")


def clear_pending_files():
	pending_files.clear()
	open(get_pending_files_path(), "w").close()


def clean_pending_files():
	path = get_pending_files_path()
	if os.path.exists(path):
		with open(path) as f:
			deleted = delete_orphan_files(f.read().splitlines())
		if deleted:
			log(f"deleted {deleted} files left by an uncommitted batch")
	clear_pending_files()


def delete_orphan_files(file_urls):
	file_urls = set(file_urls)
	if not file_urls:
		return 0

	kept = set(frappe.get_all("File", filters={"file_url": ("in", list(file_urls))}, pluck="file_url"))
	deleted = 0
	for file_url in file_urls - kept:
		path = get_files_path(os.path.basename(file_url), is_private=file_url.startswith("/private/"))
		if os.path.exists(path):
			os.remove(path)
			deleted += 1
	return deleted


def db_insert(doc):
	writes[doc.doctype] += 1
	set_defaults(doc)
	if not config.dry_run:
		doc.db_insert()


def db_set(doc, fieldname, value=None, **kwargs):
	if not config.dry_run:
		doc.db_set(fieldname, value, **kwargs)


def bulk_insert(doctype, fields, rows):
	writes[doctype] += len(rows)
	if config.dry_run or not rows:
		return
	rows = [[name, *row] for name, row in zip(next_names(doctype, len(rows)), rows, strict=True)]
	frappe.db.bulk_insert(doctype, ["name", *fields], rows)


def next_names(doctype, count):
	start = get_next_val(doctype)
	if count > 1:
		set_next_val(doctype, start + count - 1, is_val_used=True)
	return range(start, start + count)


def slice_filter(column, ids):
	if not ids:
		return "", ()
	return f"and {column} in %s", (tuple(ids),)


def topics_filter():
	topic_filter, topic_values = slice_filter("topics.id", config.topic_ids)
	category_filter, category_values = slice_filter("topics.category_id", config.category_ids)
	return f"{topic_filter} {category_filter}", topic_values + category_values


def users_from_topics_filter():
	if not config.users_from_topics:
		return "", ()
	topic_filter, topic_values = topics_filter()
	return (
		f"""and users.id in (
		select posts.user_id from posts
		join topics on topics.id = posts.topic_id
		where true {topic_filter}
		union
		select post_actions.user_id from post_actions
		join posts on posts.id = post_actions.post_id
		join topics on topics.id = posts.topic_id
		where post_actions.post_action_type_id = 2 {topic_filter}
		union
		select topic_users.user_id from topic_users
		join topics on topics.id = topic_users.topic_id
		where true {topic_filter}
	)""",
		topic_values * 3,
	)


def migrate_posts():
	load_id_map("users")
	run_batches("topics", "topics", get_topics_batch, migrate_topic, retry_comments)
	if not config.dry_run:
		update_discussions_count()
		frappe.db.commit()
		started_at = time.monotonic()
		rebuild_index()
		log(f"[topics] search index rebuilt in {(time.monotonic() - started_at) / 60:.1f} min")


def migrate_backlinks():
	for doctype, step in (("GP Discussion", "discussion_backlinks"), ("GP Comment", "comment_backlinks")):
		for name in frappe.get_all(doctype, filters={"content": ("like", "%discussion/%")}, pluck="name"):
			run_row(step, name, partial(update_backlinks, doctype, name))
		if not config.dry_run:
			frappe.db.commit()
		log(f"[{step}] done {outcomes[step, 'done']} · failed {outcomes[step, 'failed']}")


def update_backlinks(doctype, name):
	doc = frappe.get_doc(doctype, name)
	stored = sorted(str(row.discussion) for row in doc.backlinks)
	doc.update_backlinks()
	if sorted(str(row.discussion) for row in doc.backlinks) == stored:
		return
	writes["GP Backlink"] += len(doc.backlinks)
	if config.dry_run:
		return
	frappe.db.delete("GP Backlink", {"parenttype": doctype, "parent": name})
	for row in doc.backlinks:
		row.db_insert()


def local_time(column):
	return f"({column} at time zone 'UTC')::timestamp"


def get_topics_batch(last_id, limit):
	batch.clear()
	topics = get_topics(last_id, limit)
	if topics:
		topic_ids = tuple(topic.id for topic in topics)
		comments = get_comments(topic_ids)
		post_ids = tuple([topic.post_id for topic in topics] + [comment.id for comment in comments])
		batch.comments = group_by(comments, "topic_id")
		batch.likes = group_by(get_likes(post_ids), "post_id")
		batch.visits = group_by(get_visits(topic_ids), "topic_id")
		batch.tags = group_by(get_topic_tags(topic_ids), "topic_id")
	return topics


def group_by(rows, key):
	groups = {}
	for row in rows:
		groups.setdefault(row[key], []).append(row)
	return groups


def get_topics(last_id, limit):
	topic_filter, topic_values = topics_filter()
	return run_query(
		f"""
		select topics.id, topics.title, topics.category_id, posts.id as post_id, posts.user_id,
			{local_time("posts.created_at")} as creation, {local_time("posts.updated_at")} as modified,
			posts.cooked as content
		from topics
		join posts on posts.topic_id = topics.id and posts.post_number = 1
		where topics.archetype = 'regular' and topics.deleted_at is null and topics.visible
			and topics.category_id in %s
			and not exists (select 1 from categories where categories.topic_id = topics.id)
			and {POST_FILTER}
			and topics.id > %s {topic_filter}
		order by topics.id asc
		limit %s
	""",
		(tuple(get_category_ids()), last_id, *topic_values, limit),
	)


def get_comments(topic_ids):
	return run_query(
		f"""
		select posts.id, posts.topic_id, posts.user_id, {local_time("posts.created_at")} as creation,
			{local_time("posts.updated_at")} as modified, posts.cooked as content
		from posts
		where posts.topic_id in %s and posts.post_number > 1 and {POST_FILTER}
		order by posts.topic_id asc, posts.post_number asc
	""",
		(topic_ids,),
	)


def get_likes(post_ids):
	return run_query(
		f"""
		select post_actions.post_id, post_actions.user_id,
			{local_time("post_actions.created_at")} as creation
		from post_actions
		where post_actions.post_id in %s and post_actions.post_action_type_id = 2
			and post_actions.deleted_at is null and post_actions.user_id > 0
		order by post_actions.id asc
	""",
		(post_ids,),
	)


def get_visits(topic_ids):
	return run_query(
		f"""
		select topic_users.topic_id, topic_users.user_id,
			{local_time("coalesce(topic_users.first_visited_at, topic_users.last_visited_at)")} as creation,
			{local_time("topic_users.last_visited_at")} as last_visit
		from topic_users
		where topic_users.topic_id in %s and topic_users.user_id > 0
			and topic_users.last_visited_at is not null
	""",
		(topic_ids,),
	)


def get_topic_tags(topic_ids):
	return run_query(
		"""
		select topic_tags.topic_id, tags.name
		from topic_tags
		join tags on tags.id = topic_tags.tag_id
		where topic_tags.topic_id in %s
		order by topic_tags.topic_id asc, topic_tags.id asc
	""",
		(topic_ids,),
	)


def migrate_topic(topic):
	project = get_project(topic.category_id)
	if not project:
		frappe.throw(f"Category {topic.category_id} is not migrated")
	space = get_space(project)
	owner = get_author(topic.user_id)
	full_title = topic.title.strip()
	title = shorten_title(full_title)
	content = topic.content
	if title != full_title:
		content = f"<p><strong>{escape(full_title)}</strong></p>{content}"
	doc = frappe.get_doc(
		doctype="GP Discussion",
		title=title,
		slug=url_safe_slug(title),
		project=project,
		team=space.team,
		creation=topic.creation,
		modified=topic.modified,
		owner=owner,
		modified_by=owner,
	)
	set_new_name(doc)
	doc.content = convert_html(content, doc, space.is_private)
	add_tags(doc, [tag.name for tag in batch.tags.get(topic.id, [])])
	comments = [
		comment_doc
		for comment in batch.comments.get(topic.id, [])
		if (comment_doc := run_row("comments", comment.id, partial(migrate_comment, doc, space, comment)))
	]
	doc.update(get_discussion_meta(doc, comments))
	db_insert(doc)
	for row in doc.tags:
		db_insert(row)
	insert_reactions(doc, topic.post_id)
	insert_visits(doc, topic.id)
	log_discourse_map(doc, "topics", topic.id)


def shorten_title(title):
	if len(title) <= TITLE_LENGTH:
		return title
	return title[: TITLE_LENGTH - 1].rsplit(" ", 1)[0].rstrip(" ,.;:-") + "…"


def add_tags(doc, labels):
	if not labels:
		return
	chips = []
	for label in labels:
		tag = get_tag(label)
		chips.append(
			f'<span data-tag-id="{escape(str(tag))}" data-tag-label="{escape(label)}" class="tag-item">'
			f"#{escape(label)}</span>"
		)
		doc.append(
			"tags",
			{
				"tag": tag,
				"label": label,
				"creation": doc.creation,
				"modified": doc.modified,
				"owner": doc.owner,
				"modified_by": doc.owner,
			},
		)
	doc.content = f"{doc.content}<p>{' '.join(chips)}</p>"


def get_tag(label):
	if label not in tag_ids:
		name = frappe.db.get_value("GP Tag", {"label": label}, "name")
		if not name:
			tag = frappe.get_doc(doctype="GP Tag", label=label)
			insert(tag, ignore_permissions=True)
			name = tag.name or f"dry-run:tag:{label}"
		remember(tag_ids, label, name)
	return tag_ids[label]


def migrate_comment(discussion, space, comment):
	owner = get_author(comment.user_id)
	doc = frappe.get_doc(
		doctype="GP Comment",
		reference_doctype=discussion.doctype,
		reference_name=discussion.name,
		creation=comment.creation,
		modified=comment.modified,
		owner=owner,
		modified_by=owner,
	)
	set_new_name(doc)
	doc.content = convert_html(comment.content, doc, space.is_private)
	db_insert(doc)
	insert_reactions(doc, comment.id)
	log_discourse_map(doc, "posts", comment.id)
	return doc


def retry_comments(topic):
	if "mapped_posts" not in batch:
		comment_ids = {comment.id for comments in batch.comments.values() for comment in comments}
		batch.mapped_posts = get_mapped_ids("posts", comment_ids) if comment_ids else set()
	missing = [
		comment for comment in batch.comments.get(topic.id, []) if comment.id not in batch.mapped_posts
	]
	if not missing:
		return

	doc = frappe.get_doc("GP Discussion", get_mapped("topics", topic.id))
	space = get_space(doc.project)
	for comment in missing:
		run_row("comments", comment.id, partial(migrate_comment, doc, space, comment))
	doc.update_last_post()
	doc.update_post_count()
	doc.update_participants_count()
	db_set(doc, {field: doc.get(field) for field in DISCUSSION_META_FIELDS}, update_modified=False)


def set_new_name(doc):
	if not config.dry_run:
		doc.name = frappe.db.get_next_sequence_val(doc.doctype)


def get_discussion_meta(discussion, comments):
	last = max(comments, key=lambda comment: comment.creation) if comments else None
	values = (
		len(comments),
		len({discussion.owner, *(comment.owner for comment in comments)}),
		last and last.doctype,
		last and last.name,
		(last or discussion).creation,
		(last or discussion).owner,
	)
	return dict(zip(DISCUSSION_META_FIELDS, values, strict=True))


def update_discussions_count():
	frappe.db.sql(
		"""
		update `tabGP Project` set discussions_count = (
			select count(*) from `tabGP Discussion`
			where `tabGP Discussion`.project = `tabGP Project`.name
		)
	"""
	)


def insert_reactions(doc, post_id):
	reactions = [
		[user, "💖", doc.doctype, doc.name, like.creation, like.creation, user, user]
		for like in batch.likes.get(post_id, [])
		if (user := get_user(like.user_id))
	]
	fields = ["user", "emoji", "reference_doctype", "reference_name", "creation", "modified", "owner"]
	bulk_insert("GP Reaction", [*fields, "modified_by"], reactions)


def insert_visits(doc, topic_id):
	visits = [
		[user, doc.name, visit.last_visit, visit.creation, visit.last_visit, user, user]
		for visit in batch.visits.get(topic_id, [])
		if (user := get_user(visit.user_id))
	]
	bulk_insert(
		"GP Discussion Visit",
		["user", "discussion", "last_visit", "creation", "modified", "modified_by", "owner"],
		visits,
	)


def convert_html(html, doc, is_private):
	soup = BeautifulSoup(html, "html.parser")
	for img in soup.find_all("img", attrs={"class": "emoji"}):
		title = img.get("title") or img.get("alt") or ""
		emoji = get_emoji(title.strip(":"))
		if emoji:
			img.replace_with(f" {emoji} ")
		elif title:
			outcomes["emoji", "unknown"] += 1
			img.replace_with(title)

	for link in soup.find_all("a", attrs={"class": "lightbox"}):
		img = link.find("img")
		if img:
			if link.get("href"):
				img["src"] = link["href"]
			link.replace_with(img.extract())
	for wrapper in soup.find_all("div", attrs={"class": "lightbox-wrapper"}):
		wrapper.unwrap()

	for img in soup.find_all("img"):
		for attr in [attr for attr in img.attrs if attr == "srcset" or attr.startswith("data-")]:
			del img[attr]
		file = save_image(img.get("src"), img.get("alt"), doc, is_private)
		if file:
			img["src"] = file.file_url

	return sanitize_content(remove_empty_trailing_paragraphs(str(soup)))


def get_upload_path(src):
	match = src and FORUM_UPLOAD.match(src)
	if not match:
		return
	path = unquote(match.group(1))
	optimized = OPTIMIZED_UPLOAD.match(path)
	if not optimized:
		return f"default/{path}"
	original = run_query("select uploads.url from uploads where uploads.sha1 = %s", (optimized.group(1),))
	if original and not OPTIMIZED_UPLOAD.match(original[0].url):
		return get_upload_path(original[0].url)
	outcomes["uploads", "unknown optimized"] += 1


def save_image(src, filename=None, doc=None, is_private=0):
	path = get_upload_path(src)
	if not path:
		return
	full_path = os.path.join(config.uploads_folder, path)
	try:
		with open(full_path, "rb") as f:
			content = f.read()
	except FileNotFoundError:
		outcomes["uploads", "missing"] += 1
		return

	_, extn = splitext(full_path)
	stem = re.sub(r"[^\w.-]+", "-", splitext(filename or "")[0]).strip("-.")
	return save_file(content, f"{stem or 'image'}{extn}", doc, is_private)


def save_file(content, file_name, doc, is_private):
	content_hash = get_content_hash(content)
	key = (content_hash, is_private)
	file_url = file_hashes.get(key) or remember(file_hashes, key, write_file(content, file_name, is_private))
	file = frappe.get_doc(
		doctype="File",
		file_name=os.path.basename(file_url),
		file_url=file_url,
		is_private=is_private,
		file_size=len(content),
		content_hash=content_hash,
		folder=config.attachments_folder,
		attached_to_doctype=doc.doctype,
		attached_to_name=doc.name,
	)
	db_insert(file)
	return file


def write_file(content, file_name, is_private):
	for _ in range(FILE_NAME_ATTEMPTS):
		name = make_file_name(file_name, frappe.generate_hash(length=6))
		file_url = f"{'/private' if is_private else ''}/files/{name}"
		if config.dry_run:
			return file_url
		try:
			with open(get_files_path(name, is_private=is_private), "xb") as f:
				f.write(content)
		except FileExistsError:
			continue
		track_file(file_url)
		return file_url
	raise FileExistsError(f"No free file name for {file_name} after {FILE_NAME_ATTEMPTS} attempts")


def make_file_name(file_name, suffix):
	stem, extn = splitext(get_safe_file_name(file_name))
	tail = f"-{suffix}{extn}"
	stem = stem[: max(FILE_NAME_LENGTH - len(tail), 0)]
	while stem and len(f"{stem}{tail}".encode()) > FILE_NAME_BYTES:
		stem = stem[:-1]
	return f"{stem.rstrip('-.') or 'image'}{tail}"


def load_file_hashes():
	config.attachments_folder = frappe.db.get_value("File", {"is_attachments_folder": 1})
	for file in frappe.get_all(
		"File",
		filters={"is_folder": 0, "content_hash": ("is", "set")},
		fields=["content_hash", "is_private", "file_url"],
		order_by="creation asc",
	):
		file_hashes.setdefault((file.content_hash, file.is_private), file.file_url)


def get_mapped(table, discourse_id):
	key = (table, str(discourse_id))
	if key not in id_map and table not in loaded_tables:
		id_map[key] = frappe.db.get_value(
			"Discourse ID Map", {"discourse_table": table, "discourse_id": key[1]}, "reference_name"
		)
	return id_map.get(key)


def load_id_map(table):
	for row in frappe.get_all(
		"Discourse ID Map", filters={"discourse_table": table}, fields=["discourse_id", "reference_name"]
	):
		id_map.setdefault((table, row.discourse_id), row.reference_name)
	loaded_tables.add(table)


def get_user(user_id):
	return get_mapped("users", user_id)


def get_author(user_id):
	return get_user(user_id) or config.deleted_user


def get_project(category_id):
	return get_mapped("categories", category_id)


def get_space(project):
	if project not in spaces:
		spaces[project] = frappe.db.get_value("GP Project", project, ["team", "is_private"], as_dict=True)
	return spaces[project]


def clear_data(doctypes=None):
	to_delete = []
	for dt in doctypes:
		for row in frappe.db.get_all(
			"Discourse ID Map", {"reference_doctype": dt}, ["reference_name", "name"]
		):
			to_delete.append((dt, row.reference_name))
			to_delete.append(("Discourse ID Map", row.name))

	for i, d in enumerate(to_delete):
		update_progress_bar("Deleting", i, len(to_delete))
		frappe.delete_doc(d[0], d[1])


def migrate_users():
	run_batches("users", "users", get_users, migrate_user)
	if not config.dry_run:
		frappe.cache.delete_key("users_for_mentions")
		frappe.cache.delete_key("enabled_users")


def get_users(last_id, limit):
	user_filter, user_values = slice_filter("users.id", config.user_ids)
	topic_user_filter, topic_user_values = users_from_topics_filter()
	return run_query(
		f"""
		select users.id, users.username, users.active, users.suspended_till,
			users.name as full_name, user_emails.email as email,
			{local_time("users.created_at")} as created_at, uploads.url as avatar_url
		from users
		join user_emails on user_emails.user_id = users.id and user_emails.primary
		left join user_avatars on user_avatars.user_id = users.id
		left join uploads on uploads.id = user_avatars.custom_upload_id
		where users.id > 0 and not users.staged and users.id > %s {user_filter} {topic_user_filter}
		order by users.id asc
		limit %s
	""",
		(last_id, *user_values, *topic_user_values, limit),
	)


def get_user_names(user):
	full_name = " ".join((user.full_name or "").split()) or user.username
	first_name, _, last_name = full_name.partition(" ")
	return first_name, last_name


def create_placeholder_users():
	system = run_query(
		f"select {local_time('users.created_at')} as created_at from users where users.id = %s",
		(SYSTEM_USER.id,),
	)
	SYSTEM_USER.created_at = system[0].created_at if system else None
	for user in (DELETED_USER, SYSTEM_USER):
		if not get_user(user.id):
			doc = make_user(user)
			insert_user(doc)
			log_discourse_map(doc, "users", user.id)
	config.deleted_user = get_user(DELETED_USER.id)
	if not config.dry_run:
		frappe.db.commit()
	memory_added.clear()


def migrate_user(user):
	doc = make_user(user)
	if user.avatar_url:
		file = save_image(user.avatar_url, user.username, doc)
		if file:
			doc.user_image = file.file_url
	insert_user(doc)
	log_discourse_map(doc, "users", user.id)


def insert_user(doc):
	insert_without_hooks(doc)
	share = frappe.get_doc(
		doctype="DocShare",
		user=doc.name,
		share_doctype="User",
		share_name=doc.name,
		read=1,
		write=1,
		share=1,
	)
	share.flags.ignore_links = True
	insert_without_hooks(share)
	profile = frappe.get_doc(
		doctype="GP User Profile", user=doc.name, full_name=doc.full_name, enabled=doc.enabled
	)
	profile.flags.ignore_profile_ownership = True
	insert(profile, ignore_permissions=True)


def make_user(user):
	email = user.email.strip().lower()
	validate_email_address(email, throw=True)
	first_name, last_name = get_user_names(user)
	enabled = int(user.active and not user.suspended_till)
	username = user.username.strip(" @")
	if frappe.db.exists("User", {"username": username}):
		username = ""

	doc = frappe.new_doc("User")
	doc.update(
		{
			"name": email,
			"email": email,
			"first_name": first_name,
			"last_name": last_name,
			"full_name": " ".join(name for name in (first_name, last_name) if name),
			"username": username,
			"enabled": enabled,
			"user_type": "Website User",
			"send_welcome_email": 0,
			"time_zone": get_system_timezone(),
		}
	)
	if not enabled:
		doc.thread_notify = doc.send_me_a_copy = doc.allowed_in_mentions = 0
	doc.append("roles", {"role": "Gameplan Member"})
	doc.flags.creation = user.created_at
	return doc


def insert_without_hooks(doc):
	writes[doc.doctype] += 1
	doc.set("__islocal", True)
	set_defaults(doc)
	doc.set_user_and_timestamp()
	if doc.flags.creation:
		doc.creation = doc.flags.creation
	doc.set_docstatus()
	doc.check_if_latest()
	doc._validate_links()
	if not config.dry_run:
		doc.set_new_name()
	elif not doc.name:
		doc.name = f"dry-run-{frappe.generate_hash(length=10)}"
	doc.set_parent_in_children()
	doc.flags.in_insert = True
	doc._validate()
	doc.flags.in_insert = False
	if config.dry_run:
		return
	doc.db_insert()
	for child in doc.get_all_children():
		child.db_insert()


def migrate_categories():
	load_id_map("users")
	run_batches("categories", "categories", get_categories, migrate_category)


def get_category_ids():
	return [*(i for ids in COMMUNITIES.values() for i in ids), *FOLDED_CATEGORIES]


def get_categories(last_id, limit):
	category_filter, category_values = slice_filter("categories.id", config.category_ids)
	return run_query(
		f"""
		select categories.id, categories.name, categories.read_restricted as is_private,
			posts.cooked as about, posts.raw ilike '%%Replace this first paragraph%%' as about_is_boilerplate
		from categories
		left join posts on posts.topic_id = categories.topic_id and posts.post_number = 1
			and posts.deleted_at is null
		where categories.id in %s and categories.id > %s {category_filter}
		order by categories.id asc
		limit %s
	""",
		(tuple(get_category_ids()), last_id, *category_values, limit),
	)


def migrate_category(category):
	if category.id in FOLDED_CATEGORIES:
		project = get_project(FOLDED_CATEGORIES[category.id])
		if not project:
			frappe.throw(f"Category {FOLDED_CATEGORIES[category.id]} is not migrated")
		log_discourse_map(frappe._dict(doctype="GP Project", name=project), "categories", category.id)
		return

	doc = frappe.get_doc(
		doctype="GP Project",
		title="General" if category.id in GENERAL_SPACES else category.name.strip(),
		team=get_community(category.id),
		icon=DEFAULT_SPACE_ICON,
		is_private=int(category.is_private),
		visibility=VISIBILITY_MEMBER_ACCESS if category.is_private else VISIBILITY_GENERAL,
	)
	if doc.is_private:
		for user in get_private_members(category.id):
			doc.append("members", {"user": user})
	doc.flags.ignore_links = config.dry_run
	insert_without_hooks(doc)
	project = log_discourse_map(doc, "categories", category.id)
	spaces[project] = frappe._dict(team=doc.team, is_private=doc.is_private)
	if category.about and not category.about_is_boilerplate:
		db_set(doc, "description", convert_html(category.about, doc, doc.is_private), update_modified=False)


def get_community(category_id):
	title = next(title for title, ids in COMMUNITIES.items() if category_id in ids)
	team = get_mapped("communities", title)
	if team:
		return team
	doc = frappe.get_doc(doctype="GP Team", title=title, is_private=0, visibility=VISIBILITY_GENERAL)
	doc.name = append_number_if_name_exists("GP Team", url_safe_slug(title))
	insert_without_hooks(doc)
	return log_discourse_map(doc, "communities", title)


def get_private_members(category_id):
	rows = run_query(
		"""
		select distinct group_users.user_id from group_users
		where group_users.user_id > 0 and group_users.group_id in (
			select category_groups.group_id from category_groups where category_groups.category_id = %s
			union select %s
		)
		order by group_users.user_id
	""",
		(category_id, ADMINS_GROUP),
	)
	members = [get_user(row.user_id) for row in rows]
	outcomes["members", "unmapped"] += members.count(None)
	return [member for member in members if member]


def log_discourse_map(doc, table, id):
	db_insert(
		frappe.get_doc(
			doctype="Discourse ID Map",
			reference_doctype=doc.doctype,
			reference_name=doc.name,
			discourse_table=table,
			discourse_id=str(id),
		)
	)
	return remember(id_map, (table, str(id)), doc.name or f"dry-run:{table}:{id}")


conn = None
cursor = None


def run_query(query, values=None):
	global conn, cursor

	if not conn:
		conn = psycopg2.connect(**config.postgres)
		conn.set_session(readonly=True, autocommit=True)
		cursor = conn.cursor(cursor_factory=DictCursor)
		cursor.execute("set time zone %s", (get_system_timezone(),))

	cursor.execute(query, values)
	result = cursor.fetchall()
	return [frappe._dict(row) for row in result]
