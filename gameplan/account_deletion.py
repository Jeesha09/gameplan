import frappe
from frappe import _
from frappe.model.naming import append_number_if_name_exists
from frappe.utils import cint

from gameplan.site_settings import settings_doc

REQUEST = "Personal Data Deletion Request"
OPEN_STATUSES = ("Pending Verification", "Pending Approval")


def post_count(user):
	counts = frappe.db.get_value("GP User Profile", {"user": user}, ["discussions_count", "comments_count"])
	return sum(cint(count) for count in counts or ())


@frappe.whitelist(methods=["POST"])
def request_account_deletion():
	"""Email the signed-in member a link that deletes and anonymises their account."""
	user = frappe.session.user
	if user in ("Guest", "Administrator"):
		frappe.throw(_("This account can't be deleted"), frappe.PermissionError)
	limit = cint(settings_doc().account_deletion_max_posts)
	if limit and post_count(user) >= limit:
		frappe.throw(
			_("Accounts with {0} or more posts can't be deleted here. Ask a site admin.").format(limit)
		)
	existing = frappe.db.get_value(REQUEST, {"email": user, "status": ("in", OPEN_STATUSES)})
	if existing:
		frappe.get_doc(REQUEST, existing).send_verification_mail()
		return
	frappe.get_doc(doctype=REQUEST, email=user).insert(ignore_permissions=True)


def anonymise_on_confirmation(doc, method=None):
	if doc.status != "Pending Approval" or not doc.has_value_changed("status"):
		return
	frappe.enqueue(
		anonymise,
		queue="long",
		timeout=3000,
		enqueue_after_commit=True,
		now=frappe.in_test,
		request=doc.name,
		profile=frappe.db.get_value("GP User Profile", {"user": doc.email}),
	)


def anonymise(request, profile=None):
	frappe.set_user("Administrator")
	doc = frappe.get_doc(REQUEST, request)
	doc.validate_data_anonymization()
	doc.disable_user()
	doc._anonymize_data()
	label = _("Deleted user")
	frappe.db.set_value("User", doc.name, {"first_name": label, "last_name": "", "full_name": label})
	if profile:
		clear_profile(profile, label)
	doc.notify_user_after_deletion()


def clear_profile(name, label):
	profile = frappe.get_doc("GP User Profile", name)
	profile.update(
		{
			"full_name": label,
			"bio": "",
			"readme": "",
			"image": "",
			"original_image": "",
			"cover_image": "",
			"bento_cards": [],
		}
	)
	profile.flags.ignore_profile_ownership = True
	profile.save(ignore_permissions=True)
	new_name = append_number_if_name_exists("GP User Profile", "deleted-user")
	frappe.rename_doc("GP User Profile", name, new_name, force=True, show_alert=False)
