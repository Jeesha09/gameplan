# Forum features presentation branch

`forum-features` combines 13 open PRs for a presentation on Ebrahim’s fork.
It starts from upstream `develop` at `2ab4ca6d` on October 27, 2026.

## Included PRs

| PR | Feature | Merged head |
| --- | --- | --- |
| [#606](https://github.com/frappe/gameplan/pull/606) | Anonymous Community access and visibility tiers | `09ac7df0` |
| [#621](https://github.com/frappe/gameplan/pull/621) | Moderators, content removal, and Community bans | `39eacf0a` |
| [#637](https://github.com/frappe/gameplan/pull/637) | Moderation history | `7ed984bb` |
| [#638](https://github.com/frappe/gameplan/pull/638) | Content reports and review queue | `4170ccbe` |
| [#639](https://github.com/frappe/gameplan/pull/639) | Bulk report review | `4cbfa44d` |
| [#642](https://github.com/frappe/gameplan/pull/642) | First-post approval policy and review queue | `ade5a85b` |
| [#647](https://github.com/frappe/gameplan/pull/647) | Discussion slow mode | `1829a941` |
| [#610](https://github.com/frappe/gameplan/pull/610) | Unified local and server draft identity | `f75d283d` |
| [#571](https://github.com/frappe/gameplan/pull/571) | Offline reading and discussion downloads | `7a2c5102` |
| [#596](https://github.com/frappe/gameplan/pull/596) | Discussion, Space, and away notifications | `4fee6a59` |
| [#602](https://github.com/frappe/gameplan/pull/602) | Search sorting and filter-only queries | `e3ad0e82` |
| [#607](https://github.com/frappe/gameplan/pull/607) | Discussion references and link previews | `785c7c42` |
| [#640](https://github.com/frappe/gameplan/pull/640) | Accepted answers | `ed7ddcbe` |

Jeesha09’s previously merged PRs remain included through `develop`.
Closed, unmerged PRs are excluded.

## Excluded PR

[Profile and invitation fix #622](https://github.com/frappe/gameplan/pull/622) is not merged.
Previously released changes in `develop`, including #619, remain in the base.

## Integration fixes

- Keep approval submission when draft identity changes.
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
