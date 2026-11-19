import hashlib
from collections import Counter

import frappe
from frappe.utils import cint
from frappe.utils.csvutils import build_csv_response, read_csv_content

from gameplan.paging import page_start
from gameplan.permissions import require_can_manage_community
from gameplan.watched_word_matching import matches

ACTIONS = ("Block", "Censor", "Require approval", "Flag")
MAX_RULES_PER_ACTION = 2000
CSV_HEADER = ["word", "rule", "case_sensitive"]
# What a CSV may say in the case_sensitive column. Blank means no.
CSV_YES = {"yes", "true", "1"}
CSV_NO = {"", "no", "false", "0"}
# Rows of the sample file, one for each rule, so the file shows what each column takes.
CSV_SAMPLE = [
	["darn", "Censor", "no"],
	["buy now*", "Block", "no"],
	["free money", "Require approval", "no"],
	["Acme", "Flag", "yes"],
]


def validate_rule(doc):
	require_can_manage_community(doc.community)
	before = doc.get_doc_before_save()
	if before:
		require_can_manage_community(before.community)
	normalize_rule(doc)
	frappe.db.get_value("GP Team", doc.community, "name", for_update=True)
	if (
		doc.is_new()
		and not frappe.db.exists("GP Watched Word", {"rule_key": doc.rule_key})
		and frappe.db.count("GP Watched Word", {"community": doc.community, "action": doc.action}) >= 2000
	):
		frappe.throw("A Community can have at most 2,000 rules per action")
	frappe.local.request_cache.clear()


def normalize_rule(doc):
	if doc.action not in ACTIONS:
		frappe.throw("Choose a watched-word action")
	doc.word = (doc.word or "").strip()
	if not doc.word.strip("* ") or len(doc.word) > 100 or "\n" in doc.word or "\r" in doc.word:
		frappe.throw("Enter a word or phrase of 1–100 characters; wildcards need a word")
	doc.case_sensitive = cint(doc.case_sensitive)
	word = doc.word if doc.case_sensitive else doc.word.casefold()
	doc.rule_key = hashlib.sha256(
		frappe.as_json([doc.community, doc.action, word, doc.case_sensitive]).encode()
	).hexdigest()


@frappe.whitelist(methods=["GET", "POST"])
def rules(community: str, action: str = "", query: str = "", start: int = 0):
	"""List one Community's watched words for its admins, all rules or one, newest first."""
	require_can_manage_community(community)
	filters = {"community": community}
	if action:
		if action not in ACTIONS:
			frappe.throw("Choose a watched-word action")
		filters["action"] = action
	query = (query or "").strip()
	if query:
		filters["word"] = ["like", f"%{query}%"]
	rows = frappe.get_all(
		"GP Watched Word",
		filters=filters,
		fields=["name", "word", "action", "case_sensitive"],
		order_by="creation desc, name desc",
		limit_start=page_start(start),
		limit_page_length=41,
	)
	return {"items": rows[:40], "has_more": len(rows) > 40}


@frappe.whitelist(methods=["POST"])
def add(community: str, action: str, word: str, case_sensitive: bool = False):
	"""Add a word or phrase to a Community's moderation rules."""
	doc = frappe.get_doc(
		doctype="GP Watched Word",
		community=community,
		action=action,
		word=word,
		case_sensitive=case_sensitive,
	)
	validate_rule(doc)
	if not frappe.db.exists("GP Watched Word", {"rule_key": doc.rule_key}):
		doc.insert(ignore_permissions=True)
	return {"added": bool(doc.name)}


@frappe.whitelist(methods=["POST"])
def remove(community: str, name: str):
	"""Delete one watched-word rule within the admin's Community."""
	require_can_manage_community(community)
	doc = frappe.get_doc("GP Watched Word", name)
	if doc.community != community:
		frappe.throw("This rule is unavailable", frappe.PermissionError)
	doc.delete(ignore_permissions=True)
	frappe.local.request_cache.clear()


@frappe.whitelist(methods=["POST"])
def set_action(community: str, name: str, action: str):
	"""Change the rule one watched word uses, within the admin's Community."""
	require_can_manage_community(community)
	doc = frappe.get_doc("GP Watched Word", name)
	if doc.community != community:
		frappe.throw("This rule is unavailable", frappe.PermissionError)
	if doc.action == action:
		return {"changed": False}
	doc.action = action
	# Checks the action, and works out the key the word has under it.
	normalize_rule(doc)
	frappe.db.get_value("GP Team", community, "name", for_update=True)
	if frappe.db.exists("GP Watched Word", {"rule_key": doc.rule_key}):
		frappe.throw(f"“{doc.word}” already has the {action} rule")
	if frappe.db.count("GP Watched Word", {"community": community, "action": action}) >= MAX_RULES_PER_ACTION:
		frappe.throw("A Community can have at most 2,000 rules per action")
	doc.save(ignore_permissions=True)
	frappe.local.request_cache.clear()
	return {"changed": True}


@frappe.whitelist(methods=["GET"])
def download(community: str, action: str = "", sample: bool = False):
	"""Download the watched words, or a sample, as a CSV with a header row.

	The columns are word, rule and case_sensitive. Every rule is in one file unless `action`
	names one.
	"""
	require_can_manage_community(community)
	if action and action not in ACTIONS:
		frappe.throw("Choose a watched-word action")
	if sample:
		rows = CSV_SAMPLE
	else:
		filters = {"community": community}
		if action:
			filters["action"] = action
		rows = [
			[row.word, row.action, "yes" if row.case_sensitive else "no"]
			for row in frappe.get_all(
				"GP Watched Word",
				filters=filters,
				fields=["word", "action", "case_sensitive"],
				order_by="action asc, word asc",
				limit=MAX_RULES_PER_ACTION * len(ACTIONS),
			)
		]
	build_csv_response([CSV_HEADER, *rows], "watched-words")


@frappe.whitelist(methods=["POST"])
def upload(community: str, file: str, expected: str = "", action: str = ""):
	"""Preview a private CSV, or atomically import it after its preview is confirmed.

	Each row is word, rule, case_sensitive, and a first row of those names is skipped. A row with
	no rule gets `action`, when one is given.
	"""
	require_can_manage_community(community)
	if action and action not in ACTIONS:
		frappe.throw("Choose a watched-word action")
	rows = read_upload(file)
	frappe.db.get_value("GP Team", community, "name", for_update=True)
	existing = frappe.get_all(
		"GP Watched Word",
		filters={"community": community},
		fields=["rule_key", "action"],
		limit=MAX_RULES_PER_ACTION * len(ACTIONS),
	)
	pending, duplicates, seen = [], 0, {row.rule_key for row in existing}
	for number, row in rows:
		doc = rule_from_row(community, action, number, row)
		if doc.rule_key in seen:
			duplicates += 1
		else:
			seen.add(doc.rule_key)
			pending.append(doc)
	totals = Counter(row.action for row in existing) + Counter(doc.action for doc in pending)
	for name, total in totals.items():
		if total > MAX_RULES_PER_ACTION:
			frappe.throw(f"This import would exceed 2,000 {name} rules")
	digest = hashlib.sha256(frappe.as_json([community, sorted(seen)]).encode()).hexdigest()
	if expected:
		if expected != digest:
			frappe.throw(
				"The file or rules changed. Preview the import again.", frappe.TimestampMismatchError
			)
		from frappe.model.document import bulk_insert

		# Every row and the Community limit were validated under the same parent lock.
		for doc in pending:
			doc.name = frappe.generate_hash(length=10)
		bulk_insert("GP Watched Word", pending)
		frappe.local.request_cache.clear()
	return {
		"expected": digest,
		"added": len(pending),
		"duplicates": duplicates,
		"words": [f"{doc.word} · {doc.action}" for doc in pending[:40]],
		"applied": bool(expected),
	}


def read_upload(file):
	"""The numbered data rows of one of the user's own private CSV uploads."""
	file_doc = frappe.get_doc("File", file)
	file_doc.check_permission("read")
	if (
		not (file_doc.file_url or "").startswith("/private/files/")
		or file_doc.owner != frappe.session.user
		or not file_doc.get("is_private")
		or file_doc.attached_to_doctype
	):
		frappe.throw("Choose your own unattached private CSV upload", frappe.PermissionError)
	if file_doc.file_size > 1024 * 1024:
		frappe.throw("CSV uploads must be at most 1 MB")
	content = file_doc.get_content()
	if len(content.encode() if isinstance(content, str) else content) > 1024 * 1024:
		frappe.throw("CSV uploads must be at most 1 MB")
	if isinstance(content, str):
		content = content.lstrip("\ufeff")
	else:
		content = content.removeprefix(b"\xef\xbb\xbf")
	try:
		rows = read_csv_content(content)
	except Exception:
		frappe.throw("Upload a valid comma-separated CSV")
	if len(rows) > MAX_RULES_PER_ACTION * len(ACTIONS):
		frappe.throw("Upload at most 8,000 CSV rows")
	numbered = [(number, row) for number, row in enumerate(rows, 1) if row and any(row)]
	if numbered and is_header(numbered[0][1]):
		numbered = numbered[1:]
	return numbered


def is_header(row):
	return [cell.strip().lower() for cell in row[:2]] == CSV_HEADER[:2]


def rule_from_row(community, default_action, number, row):
	"""One validated, unsaved rule from a CSV row of word, rule and case_sensitive."""
	if len(row) > 3 or not (row[0] or "").strip():
		frappe.throw(f"Row {number}: expected word, rule, case_sensitive")
	# An empty cell can come back as None.
	rule = ((row[1] if len(row) > 1 else "") or "").strip()
	chosen = {name.casefold(): name for name in ACTIONS}.get(rule.casefold()) if rule else default_action
	if not chosen:
		frappe.throw(f"Row {number}: rule must be Block, Censor, Require approval or Flag")
	case = ((row[2] if len(row) > 2 else "") or "").strip().lower()
	if case not in CSV_YES | CSV_NO:
		frappe.throw(f"Row {number}: case_sensitive must be yes or no")
	doc = frappe.get_doc(
		doctype="GP Watched Word",
		community=community,
		action=chosen,
		word=row[0],
		case_sensitive=case in CSV_YES,
	)
	try:
		normalize_rule(doc)
	except frappe.ValidationError as error:
		frappe.throw(f"Row {number}: {error}")
	return doc


@frappe.whitelist(methods=["POST"])
def test(community: str, title: str = "", content: str = ""):
	"""Test content against the Community's four watched-word actions without publishing."""
	require_can_manage_community(community)
	return {action: matches(community, action, title, content) for action in ACTIONS}


def delete_rules(doc, method=None):
	frappe.db.delete("GP Watched Word", {"community": doc.name})
