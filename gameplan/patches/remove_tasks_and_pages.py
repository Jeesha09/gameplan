import frappe

from gameplan.search_sqlite import GameplanSearch

DOCTYPES = ("GP Task", "GP Page")


def execute():
	if not any(frappe.db.table_exists(doctype) for doctype in DOCTYPES):
		return

	delete_notifications()
	delete_comments()
	delete_rows_referencing("GP Activity", "reference_doctype")
	delete_rows_referencing("GP Reaction", "reference_doctype")
	delete_rows_referencing("GP Draft", "reference_doctype")
	delete_rows_referencing("Version", "ref_doctype")
	delete_attachments()
	remove_from_search_index()

	for doctype in DOCTYPES:
		frappe.delete_doc("DocType", doctype, force=True, ignore_missing=True)
		frappe.db.sql_ddl(f"DROP TABLE IF EXISTS `tab{doctype}`")


def delete_notifications():
	Notification = frappe.qb.DocType("GP Notification")
	Comment = frappe.qb.DocType("GP Comment")
	comments = frappe.qb.from_(Comment).select(Comment.name).where(Comment.reference_doctype.isin(DOCTYPES))
	frappe.qb.from_(Notification).delete().where(Notification.comment.isin(comments)).run()

	if frappe.db.has_column("GP Notification", "task"):
		frappe.qb.from_(Notification).delete().where(Notification.task.isnotnull()).where(
			Notification.task != ""
		).run()


def delete_comments():
	comments = frappe.get_all("GP Comment", filters={"reference_doctype": ("in", DOCTYPES)}, pluck="name")
	for name in comments:
		frappe.delete_doc("GP Comment", name, force=True, ignore_permissions=True)


def delete_rows_referencing(doctype, doctype_field):
	Table = frappe.qb.DocType(doctype)
	frappe.qb.from_(Table).delete().where(Table[doctype_field].isin(DOCTYPES)).run()


def delete_attachments():
	files = frappe.get_all("File", filters={"attached_to_doctype": ("in", DOCTYPES)}, pluck="name")
	if not files:
		return
	File = frappe.qb.DocType("File")
	frappe.qb.update(File).set(File.attached_to_doctype, None).set(File.attached_to_name, None).where(
		File.name.isin(files)
	).run()
	for name in files:
		frappe.delete_doc("File", name, force=True, ignore_permissions=True)


def remove_from_search_index():
	search = GameplanSearch()
	if not search.is_search_enabled() or not search.index_exists():
		return
	for doctype in DOCTYPES:
		pattern = f"{doctype}:%"
		search.sql("DELETE FROM search_fts WHERE doc_id LIKE ?", (pattern,), commit=True)
		search.sql("DELETE FROM search_index_queue WHERE doc_id LIKE ?", (pattern,), commit=True)
