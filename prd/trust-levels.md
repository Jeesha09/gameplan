# Trust levels

Decisions D103 to D132 in [moderation decisions](moderation-decisions.md). They replace the per-Community design (D62 to D77).

Trust levels mirror Discourse. Each person has one site-wide level. Members earn the first three levels from what they do, keep Regular only while they stay active, and get Leader only by hand. Levels are off until a global admin turns them on.

## Levels

| Level | Earned by | Unlocks | Report weight |
| --- | --- | --- | --- |
| 0 New | Joining | Approval in Communities that hold New posts. The new-user limits: 3 discussions and 10 replies on the first day, 1 image, 2 links, no files, 2 mentions, no @everyone. | 1 |
| 1 Basic | 5 discussions entered, visits on 2 days, 1 accepted post | The new-user limits end. The site content caps apply. | 1 |
| 2 Member | Visits on 15 days, 1 reaction given, 1 received, replies in 3 discussions, 20 discussions entered | Twice the posting-rate limits | 2 |
| 3 Regular | In the last 100 days: visits on 50 days, replies in 10 discussions, 25% of new discussions entered (at most 500), 30 reactions given, 20 received from at least 5 people, at most 5 posts removed by moderators. No ban, suspension, or silence in the last 180 days. | Skips the content caps | 3 |
| 4 Leader | A global admin only | Nothing beyond report weight (D132) | 3 |

Global admins edit every number in Site administration. Each has a fixed range.

## Who has a level

- Members and invited Guests have one. Global admins do not.
- Community staff have one and keep their exemptions inside the Communities they help run.
- Only the member, Community staff, and global admins see a level.

## Signals

| Signal | Source |
| --- | --- |
| Discussions entered | `GP Discussion Visit`, by `last_visit` inside the Regular window |
| Visit days | `GP Visit Day`, one row per member per UTC day |
| Accepted posts | Published discussions and replies that are not removed |
| Reactions given | `GP Reaction` by `user` |
| Reactions received | Reactions by other people on the member's posts |
| Replies in distinct discussions | `GP Comment` by owner, one per discussion |
| Removed posts | The member's posts with `hidden_at` or `spam_removed_at` inside the window |
| Restrictions | An active ban, suspension, or silence, or a Ban, Suspend, or Silence log entry inside 180 days |

Reading time and posts read are not tracked.

## When levels change

- **A new visit day.** The first request of a UTC day sets a cache key and queues a job that records the day. A New or Basic member is then checked for Basic and Member.
- **A published post.** A New or Basic author is checked again.
- **The nightly job.** Members who visited since yesterday are checked for Regular. Regulars past their grace period are checked again, and drop to Member if they fall short.
- **Turning levels on.** A job counts past visit days from posts, reactions, and discussion visits, then works out each person's level up to Member. Nobody is told.
- **A first read.** A member the job has not reached yet is worked out the first time their level is needed.

New, Basic, and Member never drop by themselves. A promotion to Regular, automatic or manual, starts a 14-day grace period. A lock stops every automatic change. An active ban, suspension, or silence pauses promotion.

## Approval

While levels are on, each Community admin chooses whether to hold posts from members below Basic or Member, or from nobody. Community staff are never held. While levels are off, the first-N rule (D37) works as before.

## Manual changes

Global admins set or lock a level with a reason. Each change goes to the member's account history.

## Notifications

Members get an in-app notification for each promotion, and when they drop from Regular to Member.

## Scale

- Each count stops at the number its requirement needs, and reads the member's own rows through an index.
- The posting path reads one `GP Trust Level` row by primary key.
- A visit costs one cache read per request and one job per member per day.
- The nightly job reads only Members who visited since yesterday and Regulars past their grace period. Both jobs commit in batches and continue as a new job after a time limit.
- New indexes: `GP Reaction (user, creation)`, `GP Visit Day (user, day)` unique, `GP Visit Day (day, user)`, and `GP Trust Level (level, locked, user)`.

## API

- `gameplan.trust_levels.get_settings` and `save_settings`: the switch and requirements, for global admins.
- `gameplan.trust_levels.set_level` and `set_lock`: manual changes, for global admins.
- `gameplan.approval_policy.get_level_policy` and `set_level_policy`: a Community's approval level, for its admins.

## Leader

Every member who can see a Space can already edit, close, reopen, pin, and move its discussions (`can_edit_content`). That rule stays, so Leader carries only report weight 3 (D132).
