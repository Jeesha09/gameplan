# Badges

Badges mirror Discourse. A badge rewards something a member did, such as a first like, a reply marked as the solution, or a year in the community. Badges are earned automatically, are visible to everyone who can see the member, and are off until a global admin turns them on.

The names, rules, tiers, and thresholds are Discourse's own, so a badge imported from Discourse and a badge earned in Gameplan mean the same thing. They ship on `forum-features`.

## Decisions

| | Decision |
| --- | --- |
| B1 | Reader works as Discourse defines it: read every reply in a discussion with more than 100 replies. |
| B2 | Out of Love, Higher Love, and Crazy in Love are not ported. They need a daily like limit, and Gameplan has none. |
| B3 | Tiers are coloured Bronze, Silver, and Gold, with frappe-ui's orange, gray, and yellow. This is a deliberate exception to the gray-tokens rule. |
| B4 | Each badge family has its own symbol. The tiers of a family share the symbol and differ by medallion colour. |
| B5 | Badges ship on `forum-features`. |

## Badges

| Group | Family | Badges | Tier | Earned by | Discourse ids |
| --- | --- | --- | --- | --- | --- |
| Getting Started | Autobiographer | Autobiographer | Bronze | A bio longer than 10 characters, and an uploaded avatar | 9 |
| | First Like | First Like | Bronze | Giving a like | 11 |
| | First Mention | First Mention | Bronze | Mentioning someone in a discussion or reply | 40 |
| | Reader | Reader | Bronze | Reading every reply in a discussion with more than 100 replies | 17 |
| Community | Welcome | Welcome | Bronze | Receiving a like | 5 |
| | Appreciated | Appreciated, Respected, Admired | B, S, G | 20, 100, and 300 posts with at least 1, 2, and 5 likes each | 36, 37, 31 |
| | Thank You | Thank You, Gives Back, Empathetic | B, S, G | 20, 100, and 500 liked posts, and 10, 100, and 1000 likes given | 38, 32, 39 |
| | Enthusiast | Enthusiast, Aficionado, Devotee | B, S, G | Visits on 10, 100, and 365 days in a row | 45, 46, 47 |
| | Anniversary | Anniversary | Silver | A year as a member, with at least one post in that year. Earned again each year. | 24 |
| | Helper | Helper, Trusted Helper, Community Guide | B, S, G | 10, 50, and 150 replies marked as the solution | none (new) |
| Posting | Reply | Nice Reply, Good Reply, Great Reply | B, S, G | 10, 25, and 50 likes on one reply. Earned once per reply. | 6, 7, 8 |
| | Topic | Nice Topic, Good Topic, Great Topic | B, S, G | 10, 25, and 50 likes on a discussion's first post. Earned once per discussion. | 18, 19, 20 |

That is 24 badges in 12 families. "Post" means a discussion or a reply. Discourse calls the Reply family "Post"; these names follow the list the badges were planned from.

## Not ported

Trust level badges, Editor, Emoji, Flag, Link, Onebox, Quote, Reply by Email, Wiki, Read Guidelines, Certified, Licensed, Promoter, Campaigner, Champion, the Share and Link badges, the Love badges (B2), and the Contributor tiers, which are parked. The import skips their grants, so members lose these badges.

## Signals

| Signal | Source |
| --- | --- |
| Likes | `GP Reaction`, read only through `likes_for()`. When reactions become likes, only that helper changes. |
| Mentions | Mentions in published discussions and replies |
| Profile | `GP User Profile` bio and image |
| Visit days | `GP Visit Day`, one row per member per UTC day |
| Solutions | `GP Comment.highlighted_at` |
| Reading a long discussion | `GP Discussion Visit.last_visit` later than the creation of the discussion's last reply. Gameplan does not record which replies someone read, so a visit after the last reply counts as having read them all. |
| Membership age | The member's `creation`, and their posts |

Removed posts and likes on them do not count. A badge page links a per-post grant to its post only for readers who can open that post.

## Data model

- **`GP Badge`**: title, description, family, group, tier, symbol, `rule`, enabled, `multiple_grant`, and `system` for the shipped badges. System badges cannot be deleted. Global admins can disable them.
- **`GP User Badge`**: badge, user, `granted_at`, the reference doctype and name of the post, `seq` for repeat grants, `is_favorite`, `granted_by` for manual grants, and `revoked`. It is unique per badge, user, post, and `seq`. Names are hashes, because grants are inserted in bulk.
- **Rules are Python.** Each rule is a function that returns the grants for a list of users or posts. Gameplan never runs SQL that an admin writes.

## When badges are granted

- **Events.** These queue the ids they affect:
  - giving or removing a like
  - publishing a post
  - a mention
  - a profile edit
  - a new visit day
  - marking a solution
  - a discussion visit
- **The grant job** runs every few minutes and grants badges for the queued ids.
- **The nightly job** checks Anniversary, and runs a full pass to catch anything the queue missed.
- **Turning badges on** runs one full pass. Nobody is notified for it.

Badges are kept for good, except Nice, Good, and Great Reply and Topic. Those are taken back when the post drops below the threshold, as in Discourse.

## Notifications

A new "Badge" notification for each grant. Grants from the first full pass and from the import send none.

## Interface

- **Badges page** at `/g/badges`: every enabled badge by group, with its tier, how many people hold it, and whether you hold it.
- **Badge page**: the badge's description, and who earned it, newest first. Per-post badges link to the post.
- **Profile**: a Badges tab with every badge the member holds, and up to 3 favourites the member picks. The favourites hang as ribbons from the top edge of the profile's name card, for everyone who can see the profile.
- **Hover card**: the member's favourites, as coins with no names. The tooltip on each names it.
- **Site administration**: turn badges on and off, turn single badges on and off, and grant or revoke a badge by hand with a reason. Each manual change goes to the member's account history. A revoked grant stays as a hidden row, so the next automatic check does not grant it again. Only badges earned once can be granted by hand.

## Medallions

A medallion is a coin: a ring in the tier colour, a face in a tint of it, an engraved dashed rim, and the family's symbol in a dark shade. Every colour is a frappe-ui token, so dark mode follows the theme.

| Tier | frappe-ui colour | Ring | Face | Symbol |
| --- | --- | --- | --- | --- |
| Bronze | orange | `surface-orange-7` | `surface-orange-2` | `ink-orange-8` |
| Silver | gray | `surface-gray-7` | `surface-gray-2` | `ink-gray-7` |
| Gold | yellow | `surface-yellow-7` | `surface-yellow-2` | `ink-yellow-8` |

Hovering or clicking a medallion runs a shine across it. A click never follows a link the medallion sits in. With reduced motion, nothing moves.

On the profile, each favourite is a ribbon instead of a coin: a pennant in the tier colour with the symbol drawn on it, and no coin. Hovering a ribbon swings it from its top edge, and clicking it opens the badge's page. With reduced motion, it does not swing.

A tooltip on every coin and ribbon names the badge, its tier, and what it is for. Where the grant is known, it also says when the member earned it and how many times. The badge name and tier also show as text beside a coin, because the light-theme rings are faint on white.

## Symbols

One symbol per family, 12 in all, drawn by hand as filled shapes on a 24px grid. Details are cut back to the background, so each reads as one shape at 24px.

| Family | Symbol |
| --- | --- |
| Autobiographer | A cameo portrait |
| First Like | A heart with a highlight |
| First Mention | An at sign |
| Reader | An open book with a bookmark |
| Welcome | A waving hand |
| Appreciated | A star with a sparkle |
| Thank You | A hand holding a heart |
| Enthusiast | A flame |
| Anniversary | A cake with a candle |
| Helper | A life buoy |
| Reply | A speech bubble |
| Topic | Two stacked speech bubbles |

## Discourse import

Runs in `migrate_from_discourse`, after trust levels, posts, and likes.

1. Read `user_badges` for the Discourse ids in the badge table.
2. Map users and posts through `Discourse ID Map`. Keep `granted_at`, `seq`, and `is_favorite`. Insert in bulk, with no notifications.
3. Work out the Helper family from the solutions already imported. Discourse has no such badge.
4. Run one silent full pass, which grants any badge that Discourse missed.

## API

Whitelisted methods for the badges page, a badge's holders, a member's badges, setting favourites, and manual grants and revokes. Each gets a one-line docstring, and the guide in `gameplan/mcp.py` names the ones assistants should use.

## Plan

| Phase | Work | Days |
| --- | --- | --- |
| 1 | Doctypes, rules, queue, jobs, notifications | 4 |
| 2 | Badges page, badge page, profile, hover card, Site administration | 4 |
| 3 | Symbols, medallion tokens, `AGENTS.md` exception | 1 to 2 |
| 4 | Discourse import | 2 to 3 |

A "What's new" entry ships with Phase 2.
