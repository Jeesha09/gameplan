import json
import re

import frappe
from frappe.core.api.file import get_max_file_size
from frappe.utils import cint, strip_html

import gameplan
from gameplan.api import require_admin

GP_FIELDS = (
	"logo_dark",
	"blocked_email_domains",
	"default_communities",
	"default_quick_reactions",
	"min_title_length",
	"max_title_length",
	"min_post_length",
	"allow_duplicate_titles",
	"tags_enabled",
	"tag_create_role",
	"polls_enabled",
	"direct_messages_enabled",
	"direct_message_role",
	"everyone_mention_role",
	"search_enabled",
	"unsplash_access_key",
)
WEBSITE_FIELDS = {"logo": "app_logo", "favicon": "favicon"}
CHECKS = {
	"allow_duplicate_titles",
	"tags_enabled",
	"polls_enabled",
	"direct_messages_enabled",
	"search_enabled",
}
INTS = {"min_title_length", "max_title_length", "min_post_length"}
LISTS = {"default_communities", "default_quick_reactions", "allowed_file_types"}
SECRET = "unsplash_access_key"
MASK = "********"
MB = 1024 * 1024
MAX_QUICK_REACTIONS = 20
ALL_MEMBERS = "All members"


def settings_doc():
	return frappe.get_cached_doc("GP Settings")


def feature_enabled(field):
	return bool(cint(settings_doc().get(field)))


def json_list(raw):
	if isinstance(raw, list):
		return raw
	try:
		parsed = json.loads(raw or "[]")
	except ValueError:
		return []
	return parsed if isinstance(parsed, list) else []


def blocked_domains():
	lines = (settings_doc().blocked_email_domains or "").splitlines()
	return [line.strip().lower() for line in lines if line.strip()]


def default_community_names():
	names = [str(name) for name in json_list(settings_doc().default_communities)]
	if not names:
		return []
	return frappe.get_all(
		"GP Team", filters={"name": ("in", names), "archived_at": ("is", "not set")}, pluck="name"
	)


MEMBER_ROLES = {"Gameplan Member", "Gameplan Admin"}


def join_default_communities(doc, method=None):
	"""`on_update` of a User: put someone who just became a member into the default communities."""
	from gameplan.gameplan.doctype.gp_team.gp_team import get_public_team_names

	if skip_checks() or doc.flags.skip_default_communities:
		return
	before = doc.get_doc_before_save()
	had = {row.role for row in before.roles} if before else set()
	has = {row.role for row in doc.roles}
	if had & MEMBER_ROLES or not has & MEMBER_ROLES:
		return
	for team_name in default_community_names() or get_public_team_names():
		team = frappe.get_doc("GP Team", team_name)
		if team.get_member(doc.name):
			continue
		team.add_member(doc.name)
		# Saving the community re-validates every row already in `members`, so one row
		# left pointing at a deleted account would stop anyone new from joining. The row
		# being added here is safe by construction: `doc` is the User being saved.
		team.flags.ignore_links = True
		team.save(ignore_permissions=True)


def drop_memberships(doc, method=None):
	"""`on_trash` of a User: a deleted account leaves every Community and Space it was in."""
	frappe.db.delete("GP Member", {"user": doc.name, "parenttype": ("in", ("GP Team", "GP Project"))})


def unsplash_access_key():
	if not settings_doc().unsplash_access_key:
		return None
	return settings_doc().get_password(SECRET, raise_exception=False) or None


@frappe.whitelist(methods=["POST"])
def get_settings():
	"""Return the Admin settings values this module stores, to global admins."""
	require_admin()
	doc = settings_doc()
	values = {}
	for field in GP_FIELDS:
		raw = doc.get(field)
		if field in LISTS:
			values[field] = json_list(raw)
		elif field in CHECKS:
			values[field] = bool(cint(raw))
		elif field in INTS:
			values[field] = cint(raw)
		elif field == SECRET:
			values[field] = MASK if raw else ""
		else:
			values[field] = raw or ""
	for key, field in WEBSITE_FIELDS.items():
		values[key] = frappe.db.get_single_value("Website Settings", field) or ""
	extensions = frappe.db.get_single_value("System Settings", "allowed_file_extensions") or ""
	values["allowed_file_types"] = [line.strip().lower() for line in extensions.splitlines() if line.strip()]
	values["max_upload_mb"] = get_max_file_size() // MB
	return values


@frappe.whitelist(methods=["POST"])
def save_setting(key: str, value=None):
	"""Save one Admin settings value. Global admins only."""
	save_settings({key: value})


@frappe.whitelist(methods=["POST"])
def save_settings(values: dict):
	"""Save several Admin settings values together, all or nothing. Global admins only."""
	require_admin()
	docs = {}

	def single(doctype):
		if doctype not in docs:
			docs[doctype] = frappe.get_single(doctype)
		return docs[doctype]

	for key, value in (frappe.parse_json(values) or {}).items():
		if key in LISTS and isinstance(value, str):
			value = frappe.parse_json(value)
		if key in WEBSITE_FIELDS:
			single("Website Settings").set(WEBSITE_FIELDS[key], value or "")
		elif key == "allowed_file_types":
			single("System Settings").set("allowed_file_extensions", "\n".join(clean_extensions(value)))
		elif key == "max_upload_mb":
			size = cint(value)
			if not 1 <= size <= 10240:
				frappe.throw("Largest upload must be between 1 and 10240 MB")
			single("System Settings").set("max_file_size", size)
		elif key in GP_FIELDS:
			set_gp_setting(single("GP Settings"), key, value)
		else:
			frappe.throw(f"Unknown setting: {key}")

	for doc in docs.values():
		doc.save(ignore_permissions=True)


def clean_extensions(value):
	extensions = []
	for item in value or []:
		extension = str(item).strip().lstrip(".").upper()
		if not re.fullmatch(r"[A-Z0-9]{1,10}", extension):
			frappe.throw(f"{item} is not a file type")
		if extension not in extensions:
			extensions.append(extension)
	return extensions


def set_gp_setting(doc, key, value):
	if key == SECRET and value == MASK:
		return
	if key in CHECKS:
		value = 1 if value and value not in ("0", "false") else 0
	elif key in INTS:
		value = cint(value)
	elif key == "default_communities":
		names = [str(name) for name in value or []]
		missing = set(names) - set(frappe.get_all("GP Team", filters={"name": ("in", names)}, pluck="name"))
		if missing:
			frappe.throw("Pick communities that exist")
		value = json.dumps(names)
	elif key == "default_quick_reactions":
		emojis = [str(emoji).strip() for emoji in value or [] if str(emoji).strip()]
		if len(emojis) > MAX_QUICK_REACTIONS:
			frappe.throw(f"Pick at most {MAX_QUICK_REACTIONS} quick reactions")
		value = json.dumps(emojis, ensure_ascii=False) if emojis else None
	elif key == "blocked_email_domains":
		domains = [line.strip().lstrip("@").lower() for line in (value or "").splitlines() if line.strip()]
		value = "\n".join(dict.fromkeys(domains))
	doc.set(key, value)


def boot_settings():
	"""What the app needs at load to draw the site's logos and hide features that are off."""
	doc = settings_doc()
	return {
		"logo": frappe.get_website_settings("app_logo") or "",
		"logo_dark": doc.logo_dark or "",
		"favicon": frappe.get_website_settings("favicon") or "",
		"default_quick_reactions": json_list(doc.default_quick_reactions),
		"tags_enabled": feature_enabled("tags_enabled"),
		"polls_enabled": feature_enabled("polls_enabled"),
		"direct_messages_enabled": feature_enabled("direct_messages_enabled"),
		"search_enabled": feature_enabled("search_enabled"),
		"can_start_conversations": can_start_conversations(),
		"min_title_length": cint(doc.min_title_length),
		"max_title_length": cint(doc.max_title_length),
		"min_post_length": cint(doc.min_post_length),
	}


def has_community_role(role, team, user=None):
	"""Whether the user meets one of the "who can" levels in the discussion's community."""
	from gameplan.permissions import is_community_admin, is_community_moderator, is_global_admin

	user = user or frappe.session.user
	if not role or role == ALL_MEMBERS or is_global_admin(user):
		return True
	if role == "Admins only" or not team:
		return False
	if is_community_admin(user, team):
		return True
	return role == "Community staff and up" and is_community_moderator(user, team)


def is_community_staff_anywhere(user):
	return bool(
		frappe.get_all(
			"GP Member",
			filters={"user": user, "parenttype": "GP Team"},
			or_filters={"is_admin": 1, "is_moderator": 1},
			limit=1,
		)
	)


def can_start_conversations(user=None):
	from gameplan.trust_levels import level_of

	user = user or frappe.session.user
	role = settings_doc().direct_message_role or ALL_MEMBERS
	if role == ALL_MEMBERS or gameplan.is_admin(user):
		return True
	if role == "Community staff and up":
		return is_community_staff_anywhere(user)
	level = level_of(user)
	if level is None:
		return True
	return level >= (1 if role == "Basic trust level and up" else 2)


def require_can_start_conversation():
	if not can_start_conversations():
		frappe.throw("You cannot start new conversations yet", frappe.PermissionError)


def content_team(doc):
	project = doc.get("project")
	if not project and doc.get("reference_doctype") and doc.get("reference_name"):
		project = frappe.db.get_value(doc.reference_doctype, doc.reference_name, "project")
	return frappe.db.get_value("GP Project", project, "team") if project else None


def skip_checks():
	flags = frappe.flags
	return bool(flags.in_import or flags.in_migrate or flags.in_install or flags.in_patch)


def check_post(doc, method=None):
	"""`validate` of a discussion or reply: the posting rules and who may mention everyone."""
	if skip_checks():
		return
	is_new = doc.is_new()
	if doc.doctype == "GP Discussion" and (is_new or doc.has_value_changed("title")):
		check_title(doc)
	if is_new or doc.has_value_changed("content"):
		check_length(doc)
		check_everyone_mention(doc)


def check_title(doc):
	settings = settings_doc()
	title = (doc.title or "").strip()
	shortest, longest = cint(settings.min_title_length), cint(settings.max_title_length)
	if shortest and len(title) < shortest:
		frappe.throw(f"Titles need at least {shortest} characters.")
	if longest and len(title) > longest:
		frappe.throw(f"Titles can have up to {longest} characters.")
	if not cint(settings.allow_duplicate_titles):
		filters = {"title": title}
		if doc.name and not doc.is_new():
			filters["name"] = ("!=", doc.name)
		if frappe.db.exists("GP Discussion", filters):
			frappe.throw("A discussion with this title already exists.")


def check_length(doc):
	shortest = cint(settings_doc().min_post_length)
	if shortest and len(strip_html(doc.content or "").strip()) < shortest:
		frappe.throw(f"Posts need at least {shortest} characters.")


def check_everyone_mention(doc):
	from gameplan.new_user_limits import count_post_contents

	role = settings_doc().everyone_mention_role or ALL_MEMBERS
	if role == ALL_MEMBERS or not count_post_contents(doc.content).everyone:
		return
	before = doc.get_doc_before_save()
	if before and count_post_contents(before.content).everyone:
		return
	if not has_community_role(role, content_team(doc)):
		frappe.throw("You cannot mention everyone here.")


def check_poll(doc, method=None):
	if doc.is_new() and not skip_checks() and not feature_enabled("polls_enabled"):
		frappe.throw("Polls are turned off on this site.")


def check_tag_creation(doc):
	if skip_checks():
		return
	if not feature_enabled("tags_enabled"):
		frappe.throw("Tags are turned off on this site.")
	if not has_community_role(settings_doc().tag_create_role, content_team(doc)):
		frappe.throw("You cannot create new tags. Pick an existing one.")


def require_search_enabled():
	if not feature_enabled("search_enabled"):
		frappe.throw("Search is turned off on this site.", frappe.PermissionError)


def check_email_domain(doc, method=None):
	"""`before_insert` of a User: refuse new accounts from a blocked domain, unless an admin adds them."""
	if skip_checks() or gameplan.is_admin() or not doc.email or "@" not in doc.email:
		return
	domain = doc.email.rsplit("@", 1)[1].lower()
	if any(domain == blocked or domain.endswith("." + blocked) for blocked in blocked_domains()):
		frappe.throw("Sign-ups from this email domain are not allowed.")
