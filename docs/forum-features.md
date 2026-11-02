# Forum features presentation branch

`forum-features` combines 13 open PRs and watched-word moderation on Ebrahim’s fork.
It starts from upstream `develop` at `2ab4ca6d` on October 27, 2026.
The November 2 update includes upstream `develop` at `9459e355`.

## Included PRs

| PR | Feature | Merged head |
| --- | --- | --- |
| [#606](https://github.com/frappe/gameplan/pull/606) | Anonymous Community access and visibility tiers | `be558803` |
| [#621](https://github.com/frappe/gameplan/pull/621) | Moderators, content removal, and Community bans | `8b0a6b91` |
| [#637](https://github.com/frappe/gameplan/pull/637) | Moderation history | `b1f837c7` |
| [#638](https://github.com/frappe/gameplan/pull/638) | Content reports and review queue | `f433fde1` |
| [#639](https://github.com/frappe/gameplan/pull/639) | Bulk report review | `d7d0c4c5` |
| [#642](https://github.com/frappe/gameplan/pull/642) | First-post approval policy and review queue | `5d607c09` |
| [#647](https://github.com/frappe/gameplan/pull/647) | Discussion slow mode | `5a35e540` |
| [#610](https://github.com/frappe/gameplan/pull/610) | Unified local and server draft identity | `f75d283d` |
| [#571](https://github.com/frappe/gameplan/pull/571) | Offline reading and discussion downloads | `62306e28` |
| [#596](https://github.com/frappe/gameplan/pull/596) | Discussion, Space, and away notifications | `4fee6a59` |
| [#602](https://github.com/frappe/gameplan/pull/602) | Search sorting and filter-only queries | `e3ad0e82` |
| [#607](https://github.com/frappe/gameplan/pull/607) | Discussion references and link previews | `785c7c42` |
| [#640](https://github.com/frappe/gameplan/pull/640) | Accepted answers | `ed7ddcbe` |

Watched words are included from `feat/watched-words` at `d3611505`.
They include all four actions, CSV controls, manual rules, and private approval of edits.

Jeesha09’s previously merged PRs remain included through `develop`.
Closed, unmerged PRs are excluded.

## Excluded PR

[Profile and invitation fix #622](https://github.com/frappe/gameplan/pull/622) is not merged.
Previously released changes in `develop`, including #619, remain in the base.

## Integration fixes

- Keep approval submission when draft identity changes. Use the current draft API for watched-word discussion and reply edits.
- Keep offline write guards when edits enter watched-word approval.
- Keep network and server reconnect refreshes alongside row-aware notifications.
- Censor notification messages and email titles from the combined notification feature.
- Keep moderation prompts available through the offline dialog wrapper.
- Keep notification refresh events and moderation-aware unread counts.
- Use visibility tiers when clearing subscriptions after membership changes.
- Omit hidden replies from accepted answers, references, and reference activity.
- Convert accepted-answer authors to profile handles for anonymous readers.
- Limit discussion-link interception to authored editor content.
- Keep public pagination and embedded polls on their requested page.
- Preserve the named Drafts route when adding My submissions.
- Replay historical Moonhollow participation without changing final membership.

## Run checks

Use a disposable site. Browser tests delete the responding site’s Gameplan data.

```sh
bench --site forum-check.localhost run-tests --app gameplan
cd apps/gameplan/frontend
yarn build
yarn test:offline-worker
CYPRESS_BASE_URL=http://localhost:8016 yarn test
```

Use the pinned `frappe-ui` 1.0.2 release.
Use MariaDB for the presentation and concurrency checks.

The local bench runbook contains demo accounts, addresses, service commands, and test results.
It is stored outside the repository because it contains local credentials.

## Validation snapshot

The production frontend build and 14 offline-worker tests pass. All six failures
from the 172-test browser run have passing superseding runs after integration fixes.
The final focused browser run passes all 19 tests.

The full MariaDB run completes 8 integration tests, 1956 main tests, and 142 legacy tests.
Six linked-user field-permission subtests still fail because the framework returns
`api_key: None` where they expect the field to be absent. The same failures reproduce
on the original moderation branch. Two main tests are skipped. The existing
TypeScript type check is not clean; the production build passes.

The local Moonhollow presentation has a verified 20-minute video in ten chapters,
with 30 individual feature parts. Its runbook, accounts, recordings, backups, and
resume checkpoint remain outside Git.

## November 2 update validation

Updated all 13 included PR heads and merged watched words without rewriting the source branches.
The production build, lint, 14 offline-worker tests, and 255 focused backend tests pass.
All 38 selected browser tests have passing runs, including follow-up runs after integration fixes.
The full backend and browser suites were not rerun for this update.
Presentation data was not reset or reseeded.

The portable draft-ID and notification-censor fixes also live on the watched-word source branch.
The standalone branch passed 45 backend tests and six browser tests after the backport.

Approval PR #642 uses the draft API return value for reply submission. The same fix is included in slow mode and watched words.
Moonhollow was backed up and migrated on November 2. Content counts stayed unchanged. All three test roles passed live login and page checks.

## Access audience fixes

The visibility preview loads permission roles once for all affected Spaces and both visibility states.
Unread recipients now follow Community access, including General Spaces inside restricted Communities.
Removed-content audiences exclude ordinary readers and follow the moderator's current Space access.
Removed-content and history queues resolve the moderator's Space scope with a single filtered query.
Space-move notifications use the same batched audience resolver.

The 32,149-candidate, 19-Space regression uses a simulated roster, not a migrated production database.
It records zero per-recipient role reads and one batch role lookup for the preview.
The focused combined-branch run passes 234 backend tests and five browser access-control tests.
The full backend suite and the full browser suite were not rerun.

The Space-move fix is included here. Source PR #596 belongs to another contributor and cannot be pushed from this account.
