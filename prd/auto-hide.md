# Weighted auto-hide

Decisions D78 to D102 and D121 in [moderation decisions](moderation-decisions.md).

Member reports can hide a post until a moderator reviews it. Each report counts by the reporter's trust level, so auto-hide works only while trust levels are on.

## Settings

- Each Community has a switch and a threshold, in Approval settings. The switch is off by default. The threshold is 6, from 3 to 30.
- Only Community admins and global admins change them. Moderators see the state above the Reports queue.
- While trust levels are off, the switch cannot be turned on. A switch already on stays on and is paused.

## Weights

| Reporter | Weight |
| --- | --- |
| New, Basic | 1 |
| Contributor | 2 |
| Regular, Leader | 3 |
| Community staff, global admins | 3 |

- Only Spam and Abuse/inappropriate reports count. Off-topic, AI-generated, Other, and watched-word reports reach the queue but weigh 0.
- A report filed while auto-hide is off or paused weighs 0.
- The weight is fixed when the report is filed and stored on `GP Report.weight`. The review keeps the running total in `GP Review.report_weight`.
- A reporter whose level is not worked out yet is worked out when they report. A locked level counts as itself.

## Hiding

When a report brings the total to the threshold, the System hides the post:

- The post gets `hidden_at` and `auto_hidden`. Its placeholder reads "hidden after member reports and is waiting for review".
- History records an Auto Hide entry by System. The original stays in that entry.
- The review stays Pending, gets `auto_hidden`, and sits first in the Pending queue with a Hidden automatically badge.
- The author gets an in-app notification that does not name the reporters.

A post is never hidden automatically when:

- its author is Community staff or a global admin,
- a moderator restored it or dismissed its reports before,
- it is already removed, or
- it has public attachments. Its review waits for a moderator, who must make the files private first.

Discussions and replies use the same threshold. Hiding a discussion hides its replies.

## Decisions on an auto-hidden post

| Decision | Result |
| --- | --- |
| Dismiss | Restores the post and closes the review. The author is told. |
| Hide, Uphold | Keep the post hidden with the usual placeholder. History records the moderator's Hide. |
| Delete spam | Removes the post as spam. |

- Restoring the post from anywhere closes its review as Dismiss. The restore reason becomes the decision note.
- Editing does not unhide the post.
- An auto-hide does not count toward the author's removed posts for Regular. A moderator's Hide, Uphold, or Delete spam does.
- Bulk review skips auto-hidden posts. Review them one at a time.

## Moves and changes

- A changed threshold applies from the next report. Pending reviews are not checked again.
- A discussion moved to another Community keeps its totals. Its pending reviews and its replies' pending reviews are checked against the new Community.

## API

- `gameplan.auto_hide.get_settings {"community"}`: the switch, threshold, weights, and whether levels are on. Community moderators.
- `gameplan.auto_hide.save_settings {"community", "enabled", "threshold"}`: Community admins.
- `gameplan.reporting.detail` adds the review's `report_weight`, `auto_hidden`, the Community's `auto_hide` state, each report's `weight`, and the hidden original as the current content.
- GP Discussion and GP Comment `restore` accept an optional `reason`.

## Scale

- Filing a report reads one Community row and, for the reporter, one `GP Trust Level` row by primary key.
- The threshold check runs only when a report adds weight. The never-again check reads the post's Restore entries through the `discussion_history` or `comment_history` index and its resolved reviews through `target_review`.
- New columns: `GP Review.report_weight`, `GP Review.auto_hidden`, `GP Report.weight`, `auto_hidden` on GP Discussion and GP Comment, and the Community settings. All have defaults, so adding them does not rewrite existing rows on MariaDB.
