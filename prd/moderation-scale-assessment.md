# Moderation scale assessment

Date: 4 November 2026

## What was measured

This pass used a disposable MariaDB site and a synthetic fixture containing:

- 1,000,000 discussions and 250,000 replies
- 100,000 reviews and 100,000 reports
- 250,000 moderation-history rows
- 10,000 member accounts, 5,000 active restrictions, and 1,000 posting events
- 2,000 watched words per action (8,000 total)

The fixture used one public Community and Space. Timings are local, sequential request measurements; they are useful for finding slow paths, not a production capacity guarantee.

## Measurements

| Operation | Fixture position | Time | Notes |
| --- | --- | ---: | --- |
| Report queue, recent | First page, 40 rows | 17 ms | Three SELECTs; correctly reports another page |
| Report queue, recent | Offset 10,000 | 80 ms | Three SELECTs |
| Report queue, most reported | First page, 40 rows | 664 ms | Sorting/filtering is the main cost |
| Moderation history | First page, 40 rows | 4 ms | Two SELECTs |
| Moderation history | Offset 100,000 | 2.26 s | Deep offset scan dominates |
| Removed discussions | First page, 40 rows | 6 ms | Three SELECTs |
| Removed discussions | Offset 50,000 | 1.37 s | Deep offset scan dominates |
| Removed replies | First page, 40 rows | 14 ms | Three SELECTs |
| Ban candidate picker | First page, 20 of 10,000 accounts | 261 ms | Cold first request; query scans role rows and sorts |
| Ban candidate remote search | One match among 10,000 accounts | 157 ms | One SELECT |
| Active restrictions | 5,000 active rows | 2 ms | One SELECT |
| Slow-mode latest reply lookup | 250,000 replies | 15 ms | Includes first-call metadata/cache queries |
| Watched-word matching | Four actions, 2,000 words each | 393 ms | CPU cost grows with rules and checked text |
| Censoring discussion response | 40 discussions, 2,000 censor words | 221 ms | Censor rules are fetched in a batch |
| Posting allowance check | 1,000 events for one account | 128 ms | First-call request including setup/context queries |
| Bulk report preview | 50 reviews | 5 ms | Two SELECTs after batching |

Measurements came from `/tmp/moderation-scale-final.json` and are not committed as raw benchmark output because the script and site data are disposable validation artifacts.

## Fixes made during this pass

- Report queue pagination now computes `has_more` from the extra row before trimming the page. Previously it always returned false after truncating to 40, preventing readers from loading later pages.
- Bulk report preview now loads reviews, targets, polls, and reason summaries in batches. A 50-item preview fell from 387 SELECTs / about 150 ms to 2 SELECTs / about 5 ms.
- Moderated-file safety checks now batch file and poll-share lookups instead of querying once per reply or poll.
- Restoring a hidden discussion no longer enqueues a job that loads and reindexes every reply individually. Existing reply search entries become visible again through the normal removed-parent filter.

Regression tests cover report pagination, query count for bulk preview, batched file-safety checks, and restored discussion search visibility.

## Bottlenecks and follow-up work

1. **Deep offset pagination:** History at offset 100,000 took 2.26 seconds; removed discussions at offset 50,000 took 1.37 seconds. Replace deep offsets with stable keyset/cursor pagination, using a deterministic tie-breaker such as `(creation, name)` or `(modified, name)`. The API and UI must carry the cursor while preserving filters and sort order.
2. **Most-reported queue sort:** The first page took 664 ms at 100,000 reviews, compared with 17 ms for recent order. Inspect the MariaDB query plan and indexes, then consider a maintained report-count/order field or another query shape if the current plan sorts too many candidate reviews. Benchmark writes and count updates before adding denormalized state.
3. **Ban candidate picker:** At 10,000 accounts, the cold page took 261 ms and remote search 157 ms. The query scans `Has Role` rows and uses a temporary sort. An experimental `(role, parent)` index did not materially improve the full query, so no index was kept. Revisit the role eligibility query and pagination strategy with a larger user fixture and production-like role distribution.
4. **Watched-word work:** Matching four 2,000-rule action lists took 393 ms; censoring 40 discussion responses took 221 ms. Measure warm repeated calls and varied text sizes, then consider a shared compiled matcher/cache or a multi-pattern algorithm. Keep per-Community and action boundaries intact, and account for rule changes invalidating cached matchers.
5. **Posting allowance cold path:** The first measured check took 128 ms. Repeat the measurement across warm requests and concurrent submissions before optimizing; preserve atomic quota enforcement while doing so.

The sampled first-page paths for reports, history, removed content, active restrictions, slow mode, and response censor scope did not show a per-result SQL query pattern in these measurements. The bulk preview and file-safety paths did, and have been changed to bounded query counts.

## Limits of this assessment

This is not sign-off for millions of concurrent forum users or a million-row deployment. The fixture has one public Community/Space, only 10,000 accounts, one local MariaDB instance, and a single sequential request process. This pass did not measure concurrent workers, memory use, realistic private-space visibility distributions, search indexing throughput, full feeds/unread counts, browser rendering, or end-to-end traffic. Those need separate production-like load tests before making capacity claims.

## Concurrent follow-up — 5 November 2026

A disposable site used 1,000,000 discussions, 250,000 replies, 50,000 synthetic members, 20 Communities, 100 Spaces, 100,000 pending reviews, and 300,000 reports. Four synchronous web workers served 48-request bursts at each concurrency level. Requests used one Administrator session on a local machine with 16 logical CPUs and 7.6 GiB RAM.

At 16 concurrent requests, the Community ban picker took 2,803 ms at the 95th percentile. The original query joined all role rows and sorted the results before limiting the page. After changing the role checks to use the indexed user and role lookups, the same workload took 32 ms at the 95th percentile; all 48 responses succeeded and contained 20 candidates. The picker still searches by name or email and excludes Community staff, site admins, and active bans. A search for a rare or absent prefix may still scan many users.

Most-reported sorting took 2,122 ms at the 95th percentile in the same burst. A temporary sort index improved a single database query from about 460 ms to 260 ms, but still scanned reviews across the site. This is not a satisfactory Community-scoped solution and was not retained. A durable improvement needs a current, indexed target scope with correct behavior when content moves between Spaces and Communities.

These bursts are not a sustained capacity test. The fixture does not model realistic private-Space memberships, unread data, writes, search indexing, or background work, and the request mix used only an Administrator account.
