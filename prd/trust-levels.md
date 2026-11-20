# Trust levels

Decisions D103 to D133 in [moderation decisions](moderation-decisions.md). They replace the per-Community design (D62 to D77).

Trust levels mirror Discourse. Each person has one site-wide level. Members earn the first three levels from what they do, keep Regular only while they stay active, and get Leader only by hand. Levels are off until a global admin turns them on.

## Levels

| Level | Earned by | Unlocks | Report weight |
| --- | --- | --- | --- |
| 0 New | Joining | Approval in Communities that hold New posts. The New limits: 3 discussions and 10 replies on the first day, 3 replies in a row in someone else's discussion, and per post 2 links, 5 images or videos, no files, 2 mentions, no @everyone. | 1 |
| 1 Basic | 5 discussions entered, visits on 2 days, 1 accepted post | The New limits end, apart from 6 discussions and 30 replies on the first day. The site content caps apply. | 1 |
| 2 Contributor | Visits on 15 days, 1 reaction given, 1 received, replies in 3 discussions, 20 discussions entered | Twice the posting-rate limits | 2 |
| 3 Regular | In the last 100 days: visits on 50 days, replies in 10 discussions, 25% of new discussions entered (at most 500), 30 reactions given, 20 received from at least 5 people, at most 5 posts removed by moderators. No ban, suspension, or silence in the last 180 days. | Skips the content caps. In forum mode, retitles and moves any discussion (D136). | 3 |
| 4 Leader | A global admin only | In forum mode, edits, closes and pins any post (D136) | 3 |

Global admins edit every number in Site administration. Each has a fixed range.

## New and Basic limits

Each limit matches a Discourse setting (D134). Global admins set them on the trust levels page.

| Limit | Default | Discourse setting |
| --- | --- | --- |
| New: discussions on the first day | 3 | `max_topics_in_first_day` |
| New: replies on the first day, polls included | 10 | `max_replies_in_first_day` |
| New: replies in a row in someone else's discussion | 3 | `newuser_max_replies_per_topic` |
| New: links per post | 2 | `newuser_max_links` |
| New: images, videos and audio per post | 5 | `newuser_max_embedded_media` |
| New: files per post | 0 | `newuser_max_attachments` |
| New: mentions per post | 2 | `newuser_max_mentions_per_post` |
| Basic: discussions on the first day | 6 | `tl1_max_topics_in_first_day` |
| Basic: replies on the first day | 30 | `tl1_max_replies_in_first_day` |

- The first day is the 24 hours after the account is created. The counter carries over from New to Basic.
- A reply in a row counts until someone else replies in that discussion. A member's own discussions have no limit.
- 0 means none allowed. Basic's first-day quotas cannot be lower than New's.
- The New limits also apply to Guests in public Spaces, whatever their level, and while levels are off.

When limits overlap (D135):

1. Global admins, and Community staff in their own Communities, skip every limit.
2. Every other limit that applies is checked on its own. The strictest wins, and no setting loosens another. The New limits stack with the site posting rate, the site content caps and slow mode.
3. The error names the limit that refused the post.

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

- **A new visit day.** The first request of a UTC day sets a cache key and queues a job that records the day. A New or Basic member is then checked for Basic and Contributor.
- **A published post.** A New or Basic author is checked again.
- **The nightly job.** Contributors who visited since yesterday are checked for Regular. Regulars past their grace period are checked again, and drop to Contributor if they fall short.
- **Turning levels on.** A job counts past visit days from posts, reactions, and discussion visits, then works out each person's level up to Contributor. Nobody is told.
- **A first read.** A member the job has not reached yet is worked out the first time their level is needed.

New, Basic, and Contributor never drop by themselves. A promotion to Regular, automatic or manual, starts a 14-day grace period. A lock stops every automatic change. An active ban, suspension, or silence pauses promotion.

## Approval

While levels are on, each Community admin chooses whether to hold posts from members below Basic or Contributor, or from nobody. Community staff are never held. While levels are off, the first-N rule (D37) works as before.

## Manual changes

Global admins set or lock a level with a reason. Each change goes to the member's account history.

## Notifications

Members get an in-app notification for each promotion, and when they drop from Regular to Contributor.

## Scale

- Each count stops at the number its requirement needs, and reads the member's own rows through an index.
- The posting path reads one `GP Trust Level` row by primary key.
- A visit costs one cache read per request and one job per member per day.
- The nightly job reads only Contributors who visited since yesterday and Regulars past their grace period. Both jobs commit in batches and continue as a new job after a time limit.
- New indexes: `GP Reaction (user, creation)`, `GP Visit Day (user, day)` unique, `GP Visit Day (day, user)`, and `GP Trust Level (level, locked, user)`.

## API

- `gameplan.trust_levels.get_settings` and `save_settings`: the switch and requirements, for global admins.
- `gameplan.trust_levels.set_level` and `set_lock`: manual changes, for global admins.
- `gameplan.approval_policy.get_level_policy` and `set_level_policy`: a Community's approval level, for its admins.

## Leader

By default, every member who can see a Space can edit, close, reopen, pin and move its discussions (`can_edit_content`). That suits a team using Gameplan internally.

A forum turns on "Only trusted members manage other people's posts" in Posting rules (D136). Then, for discussions, replies and polls:

| Action on someone else's post | Who |
| --- | --- |
| Edit the body | Leader, Community staff, global admins |
| Change the title, or move it to another Space | Regular, Leader, staff, admins |
| Close, reopen, pin, unpin | Leader, staff, admins |
| Reply in a closed discussion | Leader, staff, admins |

Authors still edit, retitle, move, close and reopen their own posts. Pages and tasks stay editable by every member. Delete rules do not change. While levels are off, only authors, staff and admins take these actions.
