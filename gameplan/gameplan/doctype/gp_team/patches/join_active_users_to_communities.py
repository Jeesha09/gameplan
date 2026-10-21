import frappe

VALID_ROLES = ["Gameplan Member", "Gameplan Admin", "System Manager"]


def execute():
	activity = get_activity_memberships()
	if not activity:
		return

	valid_users = get_valid_users()
	existing_memberships = get_existing_memberships()
	missing_memberships = activity - existing_memberships

	members_by_team = {}
	for team, user in missing_memberships:
		if user in valid_users:
			members_by_team.setdefault(team, []).append(user)

	for team, users in members_by_team.items():
		team_doc = frappe.get_doc("GP Team", team)
		for user in sorted(users):
			team_doc.add_member(user)
		team_doc.save(ignore_permissions=True)


def get_activity_memberships():
	return get_discussion_author_memberships() | get_discussion_comment_memberships()


def get_discussion_author_memberships():
	Discussion = frappe.qb.DocType("GP Discussion")
	rows = (
		frappe.qb.from_(Discussion)
		.select(Discussion.team, Discussion.owner)
		.where(Discussion.team.isnotnull())
		.where(Discussion.team != "")
		.where(Discussion.owner.isnotnull())
		.where(Discussion.owner.notin(["", "Guest"]))
	).run(as_dict=True)

	return memberships_from_rows(rows, "team", "owner")


def get_discussion_comment_memberships():
	Comment = frappe.qb.DocType("GP Comment")
	Discussion = frappe.qb.DocType("GP Discussion")
	rows = (
		frappe.qb.from_(Comment)
		.inner_join(Discussion)
		.on(Discussion.name == Comment.reference_name)
		.select(Discussion.team, Comment.owner)
		.where(Comment.reference_doctype == "GP Discussion")
		.where(Discussion.team.isnotnull())
		.where(Discussion.team != "")
		.where(Comment.owner.isnotnull())
		.where(Comment.owner.notin(["", "Guest"]))
	).run(as_dict=True)

	return memberships_from_rows(rows, "team", "owner")


def get_valid_users():
	HasRole = frappe.qb.DocType("Has Role")
	rows = (
		frappe.qb.from_(HasRole)
		.select(HasRole.parent)
		.distinct()
		.where(HasRole.parenttype == "User")
		.where(HasRole.role.isin(VALID_ROLES))
	).run(as_dict=True)

	return {row.parent for row in rows}


def get_existing_memberships():
	Member = frappe.qb.DocType("GP Member")
	rows = (
		frappe.qb.from_(Member)
		.select(Member.parent, Member.user)
		.where(Member.parenttype == "GP Team")
		.where(Member.parent.isnotnull())
		.where(Member.user.isnotnull())
	).run(as_dict=True)

	return memberships_from_rows(rows, "parent", "user")


def memberships_from_rows(rows, team_field, user_field):
	return {
		(str(row[team_field]), row[user_field]) for row in rows if row.get(team_field) and row.get(user_field)
	}
