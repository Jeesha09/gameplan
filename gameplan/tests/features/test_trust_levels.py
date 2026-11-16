from datetime import timedelta
from unittest.mock import patch

import frappe

from gameplan.approval_policy import needs_approval, set_level_policy, set_policy
from gameplan.new_user_limits import NewUserLimitError
from gameplan.posting_limits import allowance, check_caps
from gameplan.posting_limits import save_settings as save_posting_settings
from gameplan.restriction_queries import account_history
from gameplan.restrictions import set_restriction, utc_now
from gameplan.tests.base import GameplanTestCase
from gameplan.tests.fixtures import create_comment, create_community, create_discussion, create_space
from gameplan.trust_levels import (
	BASIC,
	LEADER,
	MEMBER,
	NEW,
	REGULAR,
	add_visit_days,
	backfill,
	check_user,
	get_settings,
	level_of,
	nightly,
	record_visit,
	requirements,
	save_settings,
	set_level,
	set_lock,
)

SMALL = {
	"basic_entered": 2,
	"basic_days": 2,
	"basic_accepted": 1,
	"member_days": 3,
	"member_given": 1,
	"member_received": 1,
	"member_replied": 2,
	"member_entered": 3,
	"regular_days": 3,
	"regular_replied": 2,
	"regular_entered_percent": 50,
	"regular_given": 1,
	"regular_received": 2,
	"regular_received_users": 2,
	"regular_max_removed": 0,
}


class TrustLevelTestCase(GameplanTestCase):
	def setUp(self):
		super().setUp()
		self.addCleanup(frappe.cache.delete_keys, "gameplan:trust:")
		self.addCleanup(frappe.clear_cache, doctype="GP Trust Settings")
		self.community = create_community(
			"Trust levels", members=[self.member, self.second_member, self.outsider, self.guest]
		)
		self.community.set_member_moderator(self.second_member.name, 1)
		self.space = create_space("Trust Space", self.community)
		self.discussions = [
			create_discussion(f"Topic {index}", self.space, owner=self.outsider) for index in range(4)
		]

	def turn_on(self, **values):
		with self.as_user(self.admin), patch("frappe.enqueue"):
			save_settings(1, **{**SMALL, **values})

	def run_jobs(self, job, **kwargs):
		# The jobs commit as they go; a test must not keep its data.
		with patch("frappe.db.commit"):
			job(**kwargs)

	def level(self, user=None):
		return frappe.db.get_value("GP Trust Level", (user or self.member).name, "level")

	def visit(self, user, count, when=None):
		for discussion in self.discussions[:count]:
			frappe.get_doc(
				doctype="GP Discussion Visit",
				user=user.name,
				discussion=discussion.name,
				last_visit=when or frappe.utils.now(),
			).insert(ignore_permissions=True)

	def visit_days(self, user, count):
		today = utc_now().date()
		add_visit_days(user.name, [str(today - timedelta(days=offset)) for offset in range(count)])

	def react(self, user, doc):
		frappe.get_doc(
			doctype="GP Reaction",
			reference_doctype=doc.doctype,
			reference_name=doc.name,
			emoji="👍",
			user=user.name,
		).insert(ignore_permissions=True)

	def earn_basic(self, user=None):
		user = user or self.member
		self.visit(user, 2)
		self.visit_days(user, 2)
		return create_discussion("Mine", self.space, owner=user)

	def earn_member(self, user=None):
		user = user or self.member
		mine = self.earn_basic(user)
		self.visit_more(user, 3)
		self.visit_days(user, 3)
		self.react(user, self.discussions[0])
		self.react(self.outsider, mine)
		create_comment(self.discussions[0], owner=user)
		create_comment(self.discussions[1], owner=user)
		return mine

	def visit_more(self, user, count):
		have = frappe.db.count("GP Discussion Visit", {"user": user.name})
		self.visit_from(user, have, count)

	def visit_from(self, user, start, end):
		for discussion in self.discussions[start:end]:
			frappe.get_doc(
				doctype="GP Discussion Visit",
				user=user.name,
				discussion=discussion.name,
				last_visit=frappe.utils.now(),
			).insert(ignore_permissions=True)

	def logs(self, action, user=None):
		return frappe.get_all(
			"GP Moderation Log", filters={"user": (user or self.member).name, "action": action}, fields=["*"]
		)

	def notifications(self, user=None):
		return frappe.get_all(
			"GP Notification",
			filters={"to_user": (user or self.member).name, "type": "Trust Level"},
			pluck="message",
		)


class TestSettings(TrustLevelTestCase):
	def test_levels_are_off_until_a_global_admin_turns_them_on(self):
		self.assertIsNone(level_of(self.member.name))
		for user in (self.member, self.second_member):
			with self.as_user(user), self.assertRaises(frappe.PermissionError):
				save_settings(1)
		self.turn_on()
		self.assertEqual(level_of(self.member.name), NEW)
		with self.as_user(self.admin):
			self.assertEqual(get_settings()["defaults"]["regular_window"], 100)

	def test_requirements_stay_inside_their_ranges(self):
		for values in ({"regular_window": 10}, {"basic_days": -1}, {"regular_days": 200}):
			with (
				self.subTest(values=values),
				self.as_user(self.admin),
				self.assertRaises(frappe.ValidationError),
			):
				save_settings(1, **values)

	def test_turning_levels_on_queues_the_first_calculation(self):
		with self.as_user(self.admin), patch("frappe.enqueue") as enqueue:
			save_settings(1)
			save_settings(1)
		self.assertEqual(enqueue.call_count, 1)

	def test_global_admins_have_no_level(self):
		self.turn_on()
		self.assertIsNone(level_of(self.admin.name))
		self.assertIsNone(level_of("Administrator"))


class TestEarlyLevels(TrustLevelTestCase):
	def setUp(self):
		super().setUp()
		self.turn_on()

	def test_basic_needs_entered_discussions_visit_days_and_an_accepted_post(self):
		self.visit(self.member, 2)
		self.visit_days(self.member, 2)
		check_user(self.member.name)
		self.assertEqual(self.level(), NEW)
		create_discussion("Mine", self.space, owner=self.member)
		check_user(self.member.name)
		self.assertEqual(self.level(), BASIC)
		self.assertIn("You are now Basic", self.notifications()[0])

	def test_a_removed_post_does_not_count_as_accepted(self):
		self.visit(self.member, 2)
		self.visit_days(self.member, 2)
		mine = create_discussion("Mine", self.space, owner=self.member)
		mine.db_set("hidden_at", frappe.utils.now())
		check_user(self.member.name)
		self.assertEqual(self.level(), NEW)

	def test_member_needs_every_requirement_and_own_reactions_do_not_count(self):
		mine = self.earn_basic()
		self.visit_more(self.member, 3)
		self.visit_days(self.member, 3)
		self.react(self.member, self.discussions[0])
		self.react(self.member, mine)
		create_comment(self.discussions[0], owner=self.member)
		create_comment(self.discussions[1], owner=self.member)
		check_user(self.member.name)
		self.assertEqual(self.level(), BASIC)
		self.react(self.outsider, mine)
		check_user(self.member.name)
		self.assertEqual(self.level(), MEMBER)

	def test_replies_count_once_per_discussion(self):
		self.earn_member()
		self.assertEqual(level_of(self.member.name), MEMBER)
		cfg = frappe._dict(get_settings())
		replied = next(r for r in requirements(self.member.name, MEMBER, cfg) if r["key"] == "replied")
		self.assertEqual(replied["actual"], 2)
		create_comment(self.discussions[0], owner=self.member)
		replied = next(r for r in requirements(self.member.name, MEMBER, cfg) if r["key"] == "replied")
		self.assertEqual(replied["actual"], 2)

	def test_an_accepted_post_checks_the_author_again(self):
		self.visit(self.member, 2)
		self.visit_days(self.member, 2)
		level_of(self.member.name)
		with self.as_user(self.member):
			create_discussion("Published", self.space)
		self.assertEqual(self.level(), BASIC)

	def test_the_first_visit_of_a_day_is_recorded_once(self):
		with self.as_user(self.member), patch("gameplan.trust_levels.record_visit_day") as record:
			record_visit()
			record_visit()
		self.assertEqual(record.call_count, 1)

	def test_a_visit_day_can_earn_basic(self):
		self.visit(self.member, 2)
		self.visit_days(self.member, 1)
		frappe.db.delete("GP Visit Day", {"user": self.member.name, "day": str(utc_now().date())})
		add_visit_days(self.member.name, [str(utc_now().date() - timedelta(days=1))])
		create_discussion("Mine", self.space, owner=self.member)
		level_of(self.member.name)
		with self.as_user(self.member):
			record_visit()
		self.assertEqual(frappe.db.count("GP Visit Day", {"user": self.member.name}), 2)
		self.assertEqual(self.level(), BASIC)

	def test_a_silenced_member_is_not_promoted(self):
		level_of(self.member.name)
		with self.as_user(self.admin):
			set_restriction(self.member.name, 1, "Spam", kind="Silence", duration_seconds=3600)
		self.earn_basic()
		check_user(self.member.name)
		self.assertEqual(self.level(), NEW)


class TestRegular(TrustLevelTestCase):
	def setUp(self):
		super().setUp()
		self.turn_on()
		mine = self.earn_member()
		self.react(self.second_member, mine)
		self.assertEqual(level_of(self.member.name), MEMBER)

	def test_the_nightly_job_promotes_a_member_who_meets_every_requirement(self):
		self.run_jobs(nightly)
		self.assertEqual(self.level(), REGULAR)
		self.assertTrue(frappe.db.get_value("GP Trust Level", self.member.name, "grace_until"))
		self.assertEqual(len(self.logs("Regular Promotion")), 1)
		self.assertIn("You are now a Regular", self.notifications()[0])

	def test_a_recent_ban_or_a_removed_post_blocks_regular(self):
		frappe.get_doc(
			doctype="GP Moderation Log", user=self.member.name, action="Ban", community=self.community.name
		).insert(ignore_permissions=True)
		self.run_jobs(nightly)
		self.assertEqual(self.level(), MEMBER)
		frappe.db.delete("GP Moderation Log", {"user": self.member.name})
		comment = create_comment(self.discussions[2], owner=self.member)
		comment.db_set("hidden_at", frappe.utils.now())
		self.run_jobs(nightly)
		self.assertEqual(self.level(), MEMBER)

	def test_only_members_who_visited_since_yesterday_are_candidates(self):
		frappe.db.delete("GP Visit Day", {"user": self.member.name})
		old = utc_now().date() - timedelta(days=10)
		add_visit_days(self.member.name, [str(old - timedelta(days=offset)) for offset in range(3)])
		self.run_jobs(nightly)
		self.assertEqual(self.level(), MEMBER)

	def test_a_regular_drops_to_member_only_after_the_grace_period(self):
		self.run_jobs(nightly)
		frappe.db.delete("GP Reaction", {"user": self.member.name})
		self.run_jobs(nightly)
		self.assertEqual(self.level(), REGULAR)
		frappe.db.set_value("GP Trust Level", self.member.name, "grace_until", utc_now() - timedelta(days=1))
		self.run_jobs(nightly)
		self.assertEqual(self.level(), MEMBER)
		self.assertEqual(len(self.logs("Regular Demotion")), 1)
		self.assertIn("become a Regular again", self.notifications()[0])

	def test_a_lock_keeps_the_level(self):
		with self.as_user(self.admin):
			set_lock(self.member.name, 1, "Keep for now")
		self.run_jobs(nightly)
		self.assertEqual(self.level(), MEMBER)

	def test_a_job_past_its_time_budget_continues_as_a_new_job(self):
		from gameplan.trust_levels import promote_regulars

		with patch("frappe.db.commit"), patch("frappe.enqueue") as enqueue:
			promote_regulars(budget=-1)
		self.assertEqual(enqueue.call_args.kwargs["after"], self.member.name)
		self.assertEqual(self.level(), REGULAR)


class TestManualChanges(TrustLevelTestCase):
	def setUp(self):
		super().setUp()
		self.turn_on()

	def test_only_global_admins_change_or_lock_a_level_with_a_reason(self):
		with self.as_user(self.second_member), self.assertRaises(frappe.PermissionError):
			set_level(self.member.name, LEADER, "Helps a lot")
		with self.as_user(self.admin):
			with self.assertRaises(frappe.ValidationError):
				set_level(self.member.name, LEADER, "")
			set_level(self.member.name, LEADER, "Helps a lot")
			set_lock(self.member.name, 1, "Keep it")
		self.assertEqual(self.level(), LEADER)
		self.assertEqual(
			[log.level for log in self.logs("Level Changed")]
			+ [log.action for log in self.logs("Level Locked")],
			["Leader", "Level Locked"],
		)
		with self.as_user(self.admin):
			history = account_history(self.member.name)
		self.assertIn("Level Changed", [row.action for row in history["items"]])

	def test_global_admins_cannot_be_given_a_level(self):
		with self.as_user(self.admin), self.assertRaises(frappe.ValidationError):
			set_level(self.admin.name, BASIC, "Test")

	def test_a_lock_stops_the_daily_check(self):
		with self.as_user(self.admin):
			set_lock(self.member.name, 1, "Hold")
		self.earn_basic()
		check_user(self.member.name)
		self.assertEqual(self.level(), NEW)

	def test_deleting_an_account_deletes_its_level_and_visit_days(self):
		self.earn_basic(self.outsider)
		level_of(self.outsider.name)
		frappe.delete_doc("User", self.outsider.name, force=True, ignore_permissions=True)
		self.assertFalse(frappe.db.exists("GP Trust Level", self.outsider.name))
		self.assertFalse(frappe.db.exists("GP Visit Day", {"user": self.outsider.name}))


class TestBackfill(TrustLevelTestCase):
	def test_the_first_calculation_counts_past_days_and_tells_nobody(self):
		mine = create_discussion("Old", self.space, owner=self.member)
		frappe.db.set_value("GP Discussion", mine.name, "creation", utc_now() - timedelta(days=3))
		self.visit(self.member, 2)
		self.turn_on()
		self.run_jobs(backfill)
		self.assertGreaterEqual(frappe.db.count("GP Visit Day", {"user": self.member.name}), 2)
		self.assertEqual(self.level(), BASIC)
		self.assertEqual(self.notifications(), [])
		self.assertIsNone(self.level(self.admin))

	def test_the_first_calculation_never_lowers_a_level(self):
		self.turn_on()
		with self.as_user(self.admin):
			set_level(self.member.name, MEMBER, "Known contributor")
		self.run_jobs(backfill)
		self.assertEqual(self.level(), MEMBER)


class TestPrivileges(TrustLevelTestCase):
	def setUp(self):
		super().setUp()
		self.turn_on()

	def submission(self):
		return frappe._dict(doctype="GP Discussion", project=self.space.name, content="")

	def test_a_community_holds_posts_from_members_below_its_level(self):
		with self.as_user(self.admin):
			set_level_policy(self.community.name, "Basic")
		with self.as_user(self.member):
			self.assertTrue(needs_approval(self.submission()))
		with self.as_user(self.second_member):
			self.assertFalse(needs_approval(self.submission()))
		with self.as_user(self.admin):
			set_level(self.member.name, BASIC, "Known")
		with self.as_user(self.member):
			self.assertFalse(needs_approval(self.submission()))

	def test_levels_replace_the_first_posts_rule_while_on(self):
		with self.as_user(self.admin):
			set_policy(self.community.name, 3)
		with self.as_user(self.member):
			self.assertFalse(needs_approval(self.submission()))
		with self.as_user(self.admin), patch("frappe.enqueue"):
			save_settings(0)
		with self.as_user(self.member):
			self.assertTrue(needs_approval(self.submission()))

	def test_new_members_get_the_new_user_limits_outside_their_staff_role(self):
		links = "".join(f'<a href="https://example.com/{n}">{n}</a>' for n in range(3))
		for user, refused in ((self.member, True), (self.second_member, False)):
			with self.subTest(user=user.name), self.as_user(user):
				doc = frappe.get_doc(
					doctype="GP Discussion", title="Links", project=self.space.name, content=links
				)
				if refused:
					with self.assertRaises(NewUserLimitError):
						doc.insert()
				else:
					doc.insert()
		with self.as_user(self.admin):
			set_level(self.member.name, BASIC, "Known")
		with self.as_user(self.member):
			frappe.get_doc(
				doctype="GP Discussion", title="Links", project=self.space.name, content=links
			).insert()

	def test_regulars_skip_the_content_caps(self):
		with self.as_user(self.admin):
			save_posting_settings(0, 0, 0, 0, 0, caps_enabled=1, max_links=1)
			set_level(self.member.name, MEMBER, "Known")
		self.addCleanup(frappe.clear_cache, doctype="GP Posting Settings")
		post = frappe._dict(content='<a href="https://a.example">a</a><a href="https://b.example">b</a>')
		with self.as_user(self.member), self.assertRaises(frappe.ValidationError):
			check_caps(post)
		with self.as_user(self.admin):
			set_level(self.member.name, REGULAR, "Known")
		with self.as_user(self.member):
			check_caps(post)

	def test_members_may_post_twice_as_often(self):
		with self.as_user(self.admin):
			save_posting_settings(1, 1, 0, 0, 0)
			set_level(self.member.name, BASIC, "Known")
		self.addCleanup(frappe.clear_cache, doctype="GP Posting Settings")
		frappe.get_doc(
			doctype="GP Posting Event", user=self.member.name, kind="discussion", accepted_at=utc_now()
		).insert(ignore_permissions=True)
		with self.as_user(self.member):
			self.assertGreater(allowance("discussion")["retry_after"], 0)
		with self.as_user(self.admin):
			set_level(self.member.name, MEMBER, "Known")
		with self.as_user(self.member):
			self.assertEqual(allowance("discussion")["retry_after"], 0)


class TestReading(TrustLevelTestCase):
	def setUp(self):
		super().setUp()
		self.turn_on()

	def test_a_member_sees_their_level_and_the_next_requirements(self):
		from gameplan.trust_levels import my_level

		self.visit(self.member, 2)
		with self.as_user(self.member):
			result = my_level()
		self.assertEqual((result["level"], result["target"]), (NEW, BASIC))
		steps = {step["key"]: step for step in result["requirements"]}
		self.assertEqual(steps["entered"], {"key": "entered", "required": 2, "actual": 2, "met": True})
		self.assertFalse(steps["accepted"]["met"])
		with self.as_user(self.admin):
			self.assertEqual(my_level(), {"enabled": 0})

	def test_a_regular_sees_what_keeps_regular(self):
		from gameplan.trust_levels import my_level

		with self.as_user(self.admin):
			set_level(self.member.name, REGULAR, "Known")
		with self.as_user(self.member):
			self.assertEqual(my_level()["target"], REGULAR)

	def test_global_admins_list_levels_and_people_not_worked_out_yet(self):
		from gameplan.trust_levels import member_levels, member_progress

		with self.as_user(self.admin):
			set_level(self.member.name, MEMBER, "Known")
			everyone = member_levels()
			members = member_levels(level="2")
			pending = member_levels(level="pending")
			found = member_levels(query="Second")
			detail = member_progress(self.member.name)
			with self.assertRaises(frappe.ValidationError):
				member_levels(level="9")
		users = [row["user"] for row in everyone["members"]]
		self.assertIn(self.member.name, users)
		self.assertNotIn(self.admin.name, users)
		self.assertEqual([row["user"] for row in members["members"]], [self.member.name])
		self.assertNotIn(self.member.name, [row["user"] for row in pending["members"]])
		self.assertIn(self.second_member.name, [row["user"] for row in pending["members"]])
		self.assertEqual([row["user"] for row in found["members"]], [self.second_member.name])
		self.assertEqual(detail["target"], REGULAR)
		with self.as_user(self.second_member), self.assertRaises(frappe.PermissionError):
			member_levels()

	def test_community_staff_read_their_members_levels(self):
		from gameplan.trust_levels import community_levels

		with self.as_user(self.admin):
			set_level(self.member.name, BASIC, "Known")
		with self.as_user(self.second_member):
			self.assertEqual(community_levels(self.community.name)["levels"].get(self.member.name), BASIC)
		with self.as_user(self.member), self.assertRaises(frappe.PermissionError):
			community_levels(self.community.name)
