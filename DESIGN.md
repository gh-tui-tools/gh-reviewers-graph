# Design: gh-reviewers-graph

## Overview

gh-reviewers-graph is a GitHub CLI extension that generates a static HTML page showing PR reviewer activity for a GitHub repository. It produces a GitHub Contributors-style visualization with monthly review counts, sparkline charts, and period filtering.

The tool runs as a two-phase pipeline: **CLI** (data gathering) **— Static HTML page** (visualization). The CLI fetches data from GitHub’s GraphQL API via `gh api graphql`, caches it locally, and writes a self-contained `index.html` with inlined CSS, JavaScript, and data. The page renders in any browser with no server required.

## Architecture

```
“gh” CLI
   — handles authentication
   — provides `gh api graphql`

gh-reviewers-graph (Python executable)
   — invokes `gh api graphql` via subprocess
   — no separate token management
```

```
+-------------------+     +------------------+     +-----------------+
|   CLI Parser      |---->|  Data Gathering  |---->| Output Generator|
|  (argparse)       |     |  (gh api graphql)|     |  (HTML output)  |
+-------------------+     +------------------+     +-----------------+
                                  |
                 +--------+-------+--------+---------+
                 v        v                v         v
         +-------------+ +---------+ +--------------+ +------------+
         |  Discovery  | | Avatars | |Monthly counts| |Merge counts|
         |  (search)   | | (user)  | |  (search)    | | (search)   |
         +-------------+ +---------+ +--------------+ +------------+
```

### Data flow

**Fresh fetch** (no cache or `--refresh`):

1. **Parse arguments**: Repository, output directory, cache options
2. **Check cache**: Load cached data if available and version matches
3. **Discover reviewers**: Split repo history into time chunks, search each in parallel to find top N reviewers by frequency
4. **Determine date range**: Repository creation month through current month
5. **Concurrently** (avatars + monthly counts + merge counts + period counts):
   a. **Fetch avatars**: Batch-query GitHub user profiles for avatar URLs
   b. **Fetch monthly counts**: Concurrent search queries for per-reviewer per-month review and comment counts
   c. **Fetch merge counts**: Scan all merged PRs (parallel by month via search API), counting merges per reviewer per month
   d. **Fetch period counts**: Per-reviewer per-period review and comment counts via `updated:>=` search queries
6. **Fetch activity snapshot**: Single API call to capture activity signals and repo-wide PR counts for all time periods
7. **Cache results**: Save to local JSON file for future runs
8. **Generate output**: Inline CSS, JS, and data into a self-contained `index.html`

**Incremental update** (valid v8 cache exists):

1. **Activity check** (1 API call): Fetch current activity signals and repo-wide PR counts for all time periods
2. **3-tier skip logic**: Compare against cached activity to determine what work can be skipped (see [Activity-check optimization](#activity-check-optimization) below)
3. **Re-discover or reuse reviewers**: Full discovery or reuse cached list depending on skip tier
4. **Fetch stale months**: Re-fetch review/comment/merge counts only for months that may have changed, plus re-fetch per-reviewer period counts (date window shifts daily)
5. **Backfill new reviewers**: Fetch historical data for any newly discovered reviewers
6. **Merge results**: Combine cached sealed months with fresh stale-month data
7. **Cache and generate output**

### Project structure

```
gh-reviewers-graph/
├── gh-reviewers-graph           # Main CLI (extensionless Python executable)
├── page-template.html            # Page template (HTML + CSS + JS)
├── pyproject.toml                # Package metadata, test config
├── schema.json                   # JSON Schema for data.json cache format
├── .github/workflows/
│   ├── ci.yml                    # CI workflow (lint + test)
│   └── update-pages.yml          # GitHub Pages deployment
├── tests/
│   ├── conftest.py               # importlib loader + shared fixtures
│   ├── test_graphql.py           # _graphql_request (subprocess mocking)
│   ├── test_cli.py               # Argument parsing
│   ├── test_main.py              # Integration tests for main()
│   ├── test_fetch.py             # Data fetching functions
│   ├── test_aggregation.py       # Output data model
│   ├── test_bot_filter.py        # Bot detection
│   ├── test_cache.py             # Cache I/O and versioning
│   ├── test_month_ranges.py      # Date range generation
│   ├── test_output.py            # Output file generation
│   ├── test_rate_limit.py        # Rate limit estimation and countdown
│   ├── test_schema.py            # JSON Schema validation
│   └── e2e/                      # Playwright end-to-end tests
└── repos/                        # Per-repo output + cached data (gitignored)
```

## GitHub CLI extension pattern

gh-reviewers-graph follows the standard GitHub CLI extension pattern:

- The main script is named `gh-reviewers-graph` (no `.py` extension), matching the `gh extension install` convention
- It has a `#!/usr/bin/env python3` shebang and is executable (`chmod +x`)
- All GitHub API access goes through `gh api graphql` via `subprocess.run()`, so the `gh` CLI handles authentication transparently — no token flags or environment variables needed
- Install with `gh extension install .` from the repo directory; invoke with `gh reviewers-graph`

### Why subprocess instead of requests

The previous version used the `requests` library with a `--token` argument. The subprocess approach has two advantages:

1. **No token management**: `gh` handles OAuth tokens, SSH keys, and credential helpers automatically
2. **No runtime dependencies**: The script uses only Python standard library modules (no `pip install` needed)

## GitHub API strategy

### Why reviewer-centric discovery

The naive approach — scan every PR in the repository, extract all reviews — doesn’t scale. A repository like mdn/content has 31K+ PRs. At 100 PRs per GraphQL request, fetching all of them would take 310+ API calls just for discovery, consuming most of the 5,000/hour rate limit before even starting the monthly counts.

**The reviewer-centric approach** flips this: discover *who* reviews by scanning a limited window of recent PRs, then use GitHub’s search API to count each reviewer’s monthly activity. This works because:

1. PR authors and mergers are strong signals for reviewer activity — scanning flat fields (no nested connections) across all months identifies candidates quickly
2. Search queries are cheap and batchable — 25 count-only aliases per GraphQL request
3. The search API returns only counts (`issueCount`), avoiding the cost of fetching full PR data

### Phase 1: Discovery (two-phase)

Discovery identifies the top N reviewers without using any dedicated query constant — it reuses the same lightweight query patterns proven to avoid secondary rate limits elsewhere in the tool.

**Sub-phase 1 — Candidate collection** (flat-field parallel search):
1. Generate month ranges from repo creation to current month
2. Search each month for PRs using `MERGE_SEARCH_QUERY` (flat fields: `author`, `mergedBy`)
3. Dispatch months across 10 workers via `ThreadPoolExecutor` (same pattern as `fetch_merge_counts`)
4. Collect unique author and merger logins, filtering bots via `is_bot()`

**Sub-phase 2 — Activity ranking** (count-only batched aliases):
1. For each candidate login, construct `reviewed-by:{login}` and `commenter:{login}` search queries scoped to the repo
2. Pack 25 count-only search aliases per GraphQL request (same pattern as `fetch_monthly_counts`)
3. Dispatch batches across 30 workers
4. Rank by combined review + comment `issueCount` plus merge frequency from sub-phase 1, return top N

#### Why not nested connections?

The obvious discovery approach — search for PRs and extract `reviews.nodes` and `comments.nodes` inline — triggers GitHub’s secondary rate limits (abuse detection) regardless of how carefully the queries are tuned. This is a separate system from the 5,000/hr primary GraphQL budget and is triggered by query *complexity patterns*, not request volume.

Several approaches were tried and all hit rate limits against mdn/content (66 months, 31K+ PRs):

| Approach | Workers | Nested limits | Result |
|----------|---------|---------------|--------|
| Parallel month chunks | 10 | `reviews(first: 10)`, `comments(first: 20)` | Rate limited at ~12s |
| Same + rate limiter (5 req/s) | 5 | `reviews(first: 10)`, `comments(first: 20)` | Rate limited at ~23s |
| Lighter nested limits | 5 | `reviews(first: 3)`, `comments(first: 5)` | Rate limited at ~23s |
| Batched search aliases (5 months/request) | 5 | `reviews(first: 3)`, `comments(first: 5)` | Server errors (502/503) + rate limited at ~12s |

Key findings:

- Reducing `first:` from 10 to 3 on `reviews()` made no difference — the presence of nested connections in a `search()` query is what triggers abuse detection, not the data volume
- Adding a `_ScrapeRateLimiter` at 5 req/s was a no-op — natural request latency (~4–5s per request) already kept the rate well below 5 req/s
- Packing 5 search aliases with nested connections into one request caused server errors (5 × 100 PR nodes × 8 nested nodes = 4,000 nodes per request)

The two-phase approach avoids nested connections entirely — sub-phase 1 uses only flat PR fields (`author.login`, `mergedBy.login`), sub-phase 2 uses only `issueCount`. Both patterns are proven safe at high concurrency elsewhere in the tool (`fetch_merge_counts` at 10 workers, `fetch_monthly_counts` at 30 workers).

**Private-activity users:** Some GitHub users have their activity marked as private, making them “unsearchable” — the search API returns `issueCount: 0` for all qualifiers. These users get 0 from sub-phase 2’s `reviewed-by:` / `commenter:` queries. To prevent them from being silently dropped, the final ranking folds in merge frequency from sub-phase 1. A user who merges many PRs gets a high score from merge counts alone, ensuring they survive discovery and reach the scrape fallback phase that recovers their real review/comment counts.

**Performance:** Sub-phase 1 takes ~7 seconds (one request per month, 10 workers). Sub-phase 2 takes ~2 seconds (~24 batches of 25 count aliases, 30 workers). Total discovery: ~10 seconds for a 66-month repo.

### Phase 2: Search aliases for monthly counts

For each (reviewer, month) pair, construct two GitHub search queries. The `-author:{login}` qualifier excludes the user’s own PRs, since GitHub’s `reviewed-by:` and `commenter:` qualifiers include self-authored PRs by default:

```
repo:owner/repo is:pr reviewed-by:{login} -author:{login} created:{YYYY-MM-01}..{YYYY-MM-31}
repo:owner/repo is:pr commenter:{login} -author:{login} created:{YYYY-MM-01}..{YYYY-MM-31}
```

Both query types are tagged with a `kind` (“review” or “comment”) and packed into the same batches. Pack up to **25 search aliases** into a single GraphQL request:

```graphql
query {
  rateLimit { remaining resetAt }
  q0: search(query: "...", type: ISSUE, first: 0) { issueCount }
  q1: search(query: "...", type: ISSUE, first: 0) { issueCount }
  ...
}
```

The `first: 0` parameter means GitHub returns only the count, not actual PR data — making each alias essentially free in terms of response payload.

### Avatar batching

Fetch avatar URLs for up to **15 logins per GraphQL request** using user query aliases:

```graphql
query {
  rateLimit { remaining resetAt }
  safe_login_1: user(login: "login1") { avatarUrl login }
  safe_login_2: user(login: "login2") { avatarUrl login }
  ...
}
```

Login strings are sanitized for GraphQL alias names: `-` and `.` are replaced with `_`. The `allow_partial=True` flag handles bot accounts and deleted users gracefully — if a `user()` query fails, the response still contains data for the other aliases, and the failed login gets a fallback avatar URL (`https://github.com/{login}.png`).

### Bot filtering

Bot accounts are excluded at discovery time via two mechanisms:

1. **Heuristic detection** (`is_bot()`): A login is considered a bot if it ends with `bot` or `[bot]` (case-insensitive), or if it appears in the `KNOWN_BOTS` frozenset. `KNOWN_BOTS` covers automation accounts that are registered as `type: "User"` on GitHub and don’t match the naming heuristic (e.g., `webkit-commit-queue`, `webkit-early-warning-system`).

2. **Runtime exclusion** (`--exclude`): Users can pass `--exclude bot1,bot2` to exclude additional logins per-invocation. The exclude set is checked alongside `is_bot()` during Phase 1 candidate collection in `discover_reviewers()`, so excluded logins never enter the candidate pool.

Since filtering happens before any data is cached, excluded accounts never appear in the cache, monthly counts, merge counts, or output. No downstream code needs bot awareness.

### Phase 3: Merge counts (MERGE_SEARCH_QUERY)

GitHub’s search API has no `merged-by:` qualifier, so merge counts cannot use the search-alias approach. Instead, the tool uses **search-based parallel pagination** — splitting the repo’s lifetime into monthly date ranges and paginating each month independently in parallel:

```graphql
query($q: String!, $cursor: String) {
  rateLimit { remaining resetAt }
  search(query: $q, type: ISSUE, first: 100, after: $cursor) {
    pageInfo { hasNextPage endCursor }
    nodes {
      ... on PullRequest {
        createdAt
        author { login }
        mergedBy { login }
      }
    }
  }
}
```

Search query: `repo:{owner}/{name} is:pr is:merged created:{start}..{end}`

- Each month range is paginated independently in parallel (10 workers)
- For each PR: extracts `mergedBy.login` and buckets by `createdAt[:7]` (YYYY-MM)
- Skips PRs where the merger is also the author (self-authored PRs)
- Only counts merges for logins in the discovered set (uses a set for O(1) lookup)
- Each worker accumulates partial results, merged under a lock after completion
- Search API limit: 1000 results per query; monthly granularity keeps each range well under this

A sequential `repository.pullRequests` approach that was tried initially required ~250+ sequential API calls for mdn/content (~25K merged PRs). The parallel search approach completes in a fraction of the time since each month is independent.

## Web scraping fallback for unsearchable users

### The problem

Some GitHub users have their activity marked as private, making them “unsearchable” via the search API  — the API returns `issueCount: 0` for all search qualifiers (`reviewed-by:`, `commenter:`, `author:`, `involves:`) despite the web UI showing real results. The REST API explicitly says "The listed users cannot be searched either because the users do not exist or you do not have permission to view the users.” In practice this affects a small minority of users (e.g., 1 out of 75 in the Ladybird repo).

Since `fetch_reviewer_period_counts()` uses search aliases to count per-reviewer activity, these users show "0 PRs reviewed | 0 commented on" in their cards despite having real activity visible through the hyperlinks.

### Hybrid approach

The fix uses a two-phase strategy:

1. **GraphQL batch** (fast): Fetch all users via search aliases as before — ~40 API calls for 100 users, completes in ~3 seconds
2. **Scrape fallback** (targeted): After all concurrent fetches complete, detect unsearchable users with monthly activity, then scrape GitHub search pages for those users only

Detection: a user is unsearchable if every period’s `reviewed` and `commented` counts are both 0. A user has monthly activity if their `monthly`, `comment_monthly`, or `merge_monthly` data sums to > 0 (meaning they will appear in the output).

Crucially, unsearchable users also get zeros from the monthly search queries (which also use `reviewed-by:` / `commenter:` qualifiers). The only data that works for them is merge counts (fetched via PR node pagination, not search). So unsearchable users without merge data have zero across the board and are filtered out by `build_output_data()` — scraping them would be wasted work.

### `scrape_unsearchable_period_counts(owner, name, period_counts, reviewers_data)`

Called in `main()` and `incremental_update()` after all concurrent fetches complete (where monthly/merge data is available). Filters unsearchable users to only those with monthly activity, then delegates to `_scrape_fallback_period_counts()`.

### `_ScrapeRateLimiter`

Throttles concurrent scrape requests to a target rate using a shared lock and `time.monotonic()`:

```python
class _ScrapeRateLimiter:
    def __init__(self, max_rps):
        self._min_interval = 1.0 / max_rps
        self._lock = threading.Lock()
        self._next_time = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            if now < self._next_time:
                time.sleep(self._next_time - now)
            self._next_time = time.monotonic() + self._min_interval
```

`SCRAPE_MAX_RPS = 4`  — GitHub allows approximately 500 requests/minute (~8.3/s), but secondary rate limits share a budget with the GraphQL API. The early-exit gate keeps total request counts low enough that 4 req/s avoids 429s in practice.

### `_scrape_search_count(url)`

Scrapes a GitHub pull request search page and returns the total count (Open + Closed). Parses the HTML for patterns like `"2 Open"` and `"20 Closed"` using regex.

- **429 handling**: Reads `Retry-After` header (default 10s, capped at 60s), adds random jitter (0–5s), retries up to 3 times
- **Error handling**: Returns 0 on network errors or unparseable HTML
- **Timeout**: 15 seconds per request

### `_scrape_fallback_period_counts(owner, name, logins, results, periods)`

Orchestrates scraping for unsearchable users with early-exit gating:

1. **Gate phase**: Scrape only the broadest period ("24" months) for all users (N × 2 requests)
2. **Gate check**: Users with zero reviewed AND zero commented in 24 months get all shorter periods set to 0 without further scraping
3. **Detail phase**: Scrape remaining periods ("1", "3", "6", "12") only for users that passed the gate (M × 4 × 2 requests, where M ≤ N)

Uses `ThreadPoolExecutor` with up to 10 workers, rate-limited to `SCRAPE_MAX_RPS`. This keeps total requests low — many unsearchable users are PR authors/mergers with zero review/comment activity, so the gate filters them out after just 2 requests each.

### Why not full web scraping?

Full scraping for all users would require 1,000 requests (100 users × 5 periods × 2 metrics) at 4 req/s = ~250 seconds. The hybrid approach is much faster because GraphQL batching handles the vast majority of users in ~3 seconds, and scraping is limited to the small number of private-activity users who have real monthly activity (typically just a handful per repo).

Web scraping doesn’t consume API rate limit quota, but is constrained by GitHub’s secondary rate limits (abuse detection).

## Concurrency

### ThreadPoolExecutor with 30 workers

Monthly count fetching is parallelized across 30 worker threads:

```python
MAX_WORKERS = 30

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
    futures = {
        executor.submit(run_batch, idx): idx
        for idx in range(total_batches)
    }
    for future in as_completed(futures):
        batch_idx, partial, remaining = future.result()
        with lock:
            for (login, label), count in partial.items():
                results[login][label] = count
            completed[0] += 1
```

**Why 30 workers**: GitHub’s secondary rate limits (abuse detection) trigger at ~40+ concurrent requests. 30 is the practical ceiling — the same limit used by [gh-activity-chronicle](https://github.com/gh-tui-tools/gh-activity-chronicle), which was determined through empirical testing.

**Discovery workers**: Candidate collection (sub-phase 1) uses 10 workers, same as merge pagination — each request fetches up to 100 PR nodes with flat fields. Activity ranking (sub-phase 2) uses 30 workers, same as monthly counts — each request is count-only aliases with no PR data.

**Merge count workers**: Merge pagination uses 10 workers instead of 30, since each worker makes multiple sequential requests per month (multi-page pagination), and 10 × ~4 pages keeps burst volume under abuse detection thresholds.

**Thread safety**: A `threading.Lock` protects the shared results dict and `completed` counter. Each batch returns a partial result dict that gets merged under the lock. The `completed` counter uses a mutable list (`[0]`) rather than a plain integer to allow mutation inside the closure.

**Progress reporting**: Status is printed every 20 batches for monthly counts, and every 10 months for merge counts.

### Phase concurrency

After discovery completes, four independent phases run concurrently via an outer `ThreadPoolExecutor(max_workers=4)`:

```python
with ThreadPoolExecutor(max_workers=4) as executor:
    avatar_future = executor.submit(fetch_avatars, ...)
    monthly_future = executor.submit(fetch_monthly_counts, ...)
    merge_future = executor.submit(fetch_merge_counts, ...)
    period_counts_future = executor.submit(fetch_reviewer_period_counts, ...)
```

Monthly counts and period counts each internally spawn a 30-worker pool; merge counts spawns a 10-worker pool. Total wall-clock time for this stage is `max(avatars, monthly, merges, period_counts)` instead of the sum.

## Data model

### Cache format (v8)

Cached at `repos/{owner}/{name}/data.json`. The structure is formally defined in [`schema.json`](schema.json) (JSON Schema draft 2020-12).

```json
{
  "version": 8,
  "start_month": "2024-01",
  "end_month": "2024-06",
  "activity": {
    "last_pr_updated_at": "2024-06-15T10:30:00Z",
    "total_pr_count": 5432,
    "total_merged_prs": 2100,
    "total_reviewed_prs": 3200,
    "total_commented_prs": 4100,
    "repo_totals": {
      "all": {"reviewed": 3200, "commented": 4100, "merged": 2100},
      "1": {"reviewed": 120, "commented": 200, "merged": 85},
      "3": {"reviewed": 350, "commented": 580, "merged": 240},
      "6": {"reviewed": 700, "commented": 1100, "merged": 490},
      "12": {"reviewed": 1500, "commented": 2300, "merged": 1050},
      "24": {"reviewed": 2800, "commented": 3600, "merged": 1900}
    }
  },
  "reviewers": {
    "login": {
      "avatar_url": "https://avatars.githubusercontent.com/...",
      "monthly": {
        "2024-01": 15,
        "2024-02": 8
      },
      "comment_monthly": {
        "2024-01": 3,
        "2024-02": 1
      },
      "merge_monthly": {
        "2024-01": 2
      }
    }
  },
  "reviewer_period_counts": {
    "login": {
      "1": {"reviewed": 22, "commented": 26},
      "3": {"reviewed": 55, "commented": 60},
      "6": {"reviewed": 100, "commented": 110},
      "12": {"reviewed": 180, "commented": 200},
      "24": {"reviewed": 300, "commented": 340}
    }
  }
}
```

The `version` field guards against schema changes — if the cache version doesn’t match 8, it’s treated as stale and re-fetched. Version history: v1 stored raw review events, v2 added monthly aggregation, v3 added `comment_monthly`, v4 added `merge_monthly`, v5 excludes self-authored PRs from all counts, v6 excludes bot accounts from discovery, v7 parallelizes merge phase via search API and runs avatars/monthly/merges concurrently, v8 adds `start_month`/`end_month` for incremental updates and `activity` for dormancy detection.

The `reviewer_period_counts` key is optional — old v8 caches without it work fine. When present, it stores per-reviewer per-period review and comment counts fetched via `updated:>=` search queries, matching the hyperlink date qualifiers in reviewer cards. This avoids the mismatch between `created:` monthly bucketing and `updated:>=` link filters.

The `activity` key is optional for backward compatibility — old v8 caches without it skip the activity-check optimization on the first run and populate it afterward. No version bump is needed when `activity` is absent. The `repo_totals` sub-key stores repo-wide PR counts for each time period, used by the summary line in the page.

### Output format

The output is a self-contained `index.html` with CSS, JS, and data inlined. The data is embedded as a global `DATA` variable:

```javascript
const DATA = {
  "repo": "owner/repo",
  "generated_at": "2026-02-21T13:51:30.090975+00:00",
  "reviewers": [
    {
      "login": "username",
      "avatar_url": "https://avatars.githubusercontent.com/u/123?v=4",
      "html_url": "https://github.com/username",
      "total": 342,
      "total_comments": 87,
      "total_merges": 45,
      "monthly": {
        "2024-01": 15,
        "2024-02": 8
      },
      "comment_monthly": {
        "2024-01": 3,
        "2024-02": 1
      },
      "merge_monthly": {
        "2024-01": 2,
        "2024-02": 1
      },
      "period_counts": {
        "1": {"reviewed": 22, "commented": 26},
        "3": {"reviewed": 55, "commented": 60},
        "6": {"reviewed": 100, "commented": 110},
        "12": {"reviewed": 180, "commented": 200},
        "24": {"reviewed": 300, "commented": 340}
      }
    }
  ],
  "monthly_totals": {
    "2024-01": 1542,
    "2024-02": 1203
  },
  "comment_monthly_totals": {
    "2024-01": 234,
    "2024-02": 198
  },
  "merge_monthly_totals": {
    "2024-01": 45,
    "2024-02": 38
  },
  "repo_totals": {
    "all": {"reviewed": 3200, "commented": 4100, "merged": 2100},
    "1": {"reviewed": 120, "commented": 200, "merged": 85},
    "3": {"reviewed": 350, "commented": 580, "merged": 240},
    "6": {"reviewed": 700, "commented": 1100, "merged": 490},
    "12": {"reviewed": 1500, "commented": 2300, "merged": 1050},
    "24": {"reviewed": 2800, "commented": 3600, "merged": 1900}
  }
};
```

- `reviewers` array sorted by combined activity (`total` + `total_comments` + `total_merges`) descending, so comment-only or merge-only repos produce meaningful rankings
- `monthly`, `comment_monthly`, and `merge_monthly` dicts sorted by month ascending
- Only months with non-zero counts are stored (sparse representation)
- Reviewers with zero total reviews AND zero total comments AND zero total merges are excluded
- `monthly_totals` aggregates review counts across all reviewers for the overview chart
- `comment_monthly_totals` aggregates comment counts across all reviewers
- `merge_monthly_totals` aggregates merge counts across all reviewers
- `period_counts` (optional) contains per-period review and comment counts fetched via `updated:>=` search queries, matching the hyperlink date filters. When present and `currentPeriod` is not “all”, the JS uses these instead of summing monthly data. Merged counts always use summed monthly (no `merged-by:` search qualifier exists)
- `repo_totals` contains repo-wide PR counts (reviewed, commented, merged) for each time period, fetched via the GitHub search API rather than summed from per-reviewer data

## Rate limiting and resilience

All API interaction goes through `_graphql_request()`, which shells out to `gh api graphql` and implements multiple layers of error handling:

### Proactive rate limit pause

Every GraphQL response includes `rateLimit { remaining resetAt }`. When `remaining` drops below 50, the tool pauses proactively — calculating wait time from the `resetAt` timestamp plus a 5-second buffer. This prevents exhausting the budget mid-run.

### Pre-flight budget estimation

Before the expensive Phase 3 (concurrent monthly/merge/period counts), the tool estimates total API calls and prints a budget summary:

```
Rate limit: 3,421 of 5,000 remaining (resets at 14:32)
Estimated API calls: ~1,637 (48% of remaining)
```

If the estimate exceeds remaining budget, a warning is printed — but execution continues (the countdown mechanism handles the actual wait). `estimate_api_calls(n_months, n_logins)` models each fetch phase: discovery, avatars, monthly counts, merge counts, and period counts. `estimate_incremental_calls()` uses the same model but scoped to stale months.

### Reactive rate limit handling

If `gh api graphql` exits with a `CalledProcessError` whose stderr contains “rate limit” or “HTTP 403”, the tool calls `_wait_for_rate_limit_reset()` and retries. If a 200 response contains GraphQL-level rate limit errors (in the `errors` array), the same wait-and-retry applies.

### Rate limit countdown

`_wait_for_rate_limit_reset()` replaces the previous fixed 60-second sleep. It:

1. Queries `gh api rate_limit` (REST, doesn’t count against GraphQL quota) to get the actual reset timestamp
2. If reset is within 60 minutes: counts down in 15-second intervals, updating the progress spinner with time remaining (e.g., “Rate limit reached — resets at 14:32 (12m 45s remaining)”)
3. If reset is >60 minutes or unknown: falls back to a single 60-second sleep

The reset target is cached in a module-level variable protected by `threading.Lock`, so when 30 concurrent workers all hit the limit simultaneously, only the first one queries the reset time; the others reuse the cached target and sleep until the same time.

### Server error retry (502/503/504)

Up to 5 retries with exponential backoff: wait `min(2^retry, 30)` seconds. The 30-second cap prevents excessive delays. After exhausting retries, a `RuntimeError` is raised.

### OS error retry

`OSError` (which covers `FileNotFoundError` if `gh` is not installed) is caught and retried up to 5 times with the same exponential backoff schedule. After exhausting retries, the exception is re-raised.

### Partial GraphQL errors

The `allow_partial=True` flag (used for avatar fetching) allows responses that contain both `errors` and `data` to succeed. This handles bot accounts and deleted users whose `user()` queries fail — the response still contains valid data for other aliases in the batch.

## Activity-check optimization

### The problem

The incremental update previously made ~60 API calls every run, even when nothing had changed in the repo. For CI/automation running daily, most runs hit a dormant repo and waste API budget.

### Activity query (1 API call)

A single GraphQL call fetches three activity signals plus repo-wide PR counts for all six time periods (all, 1, 3, 6, 12, 24 months) — 18 search aliases total, all in one request:

```graphql
query($owner: String!, $name: String!) {
  rateLimit { remaining resetAt }
  repository(owner: $owner, name: $name) {
    pullRequests(first: 1, orderBy: {field: UPDATED_AT, direction: DESC}) {
      totalCount
      nodes { updatedAt }
    }
    mergedPRs: pullRequests(states: [MERGED]) { totalCount }
  }
  reviewed_all: search(query: "repo:o/r is:pr -review:none", type: ISSUE, first: 0) { issueCount }
  commented_all: search(query: "repo:o/r is:pr comments:>=1", type: ISSUE, first: 0) { issueCount }
  merged_all: search(query: "repo:o/r is:pr is:merged", type: ISSUE, first: 0) { issueCount }
  reviewed_3: search(query: "repo:o/r is:pr -review:none created:>=2025-11-01", ...) { issueCount }
  “... 12 more period-qualified aliases ...”
}
```

Returns:
- `last_pr_updated_at`: Timestamp of the most recently updated PR (or `None` for empty repos)
- `total_pr_count`: Total number of PRs in the repo
- `total_merged_prs`: Total number of merged PRs
- `repo_totals`: Dict keyed by period (`all`, `1`, `3`, `6`, `12`, `24`), each containing `reviewed`, `commented`, `merged` counts

The date filters use `created:>=YYYY-MM-01` computed from the current date. Period-qualified counts power the summary line above the overview chart, which updates when the user changes the time period filter.

### 3-tier skip logic

At the start of `incremental_update()`, the activity signals are compared against the cached values:

| Tier | Condition | Effect | Savings |
|------|-----------|--------|---------|
| 1. Full skip | `last_pr_updated_at` unchanged OR `repo_totals["all"]` unchanged | Return cache as-is (advance `end_month`) | ~60 calls |
| 2. Skip discovery | `total_pr_count` unchanged | Reuse cached reviewer list | ~50 calls |
| 3. Skip merges | `total_merged_prs` unchanged | Keep cached merge data as-is | ~1–2 calls |

Each tier gates progressively more work. Review/comment counts are always re-fetched for stale months when there is activity, since no cheap global counter exists for those.

#### Tier 1 dual signals

The Tier 1 full skip has two signals, checked in order:

1. **Primary: `last_pr_updated_at`** — the `updatedAt` timestamp of the most recently updated PR. If unchanged, nothing touched any PR at all. This catches all activity, including a new review on an already-reviewed PR (which wouldn’t change the aggregate count but would change individual reviewer monthly data).

2. **Fallback: `repo_totals["all"]`** — the all-time counts of reviewed, commented, and merged PRs. If unchanged, no new review/comment/merge activity occurred. This handles very active repos (e.g., WebKit/WebKit) where CI, bots, and label changes constantly bump `last_pr_updated_at` even when no actual review activity has occurred.

Both signals come from the same single `fetch_repo_activity` API call, so the fallback adds no cost. The primary signal is more precise (catches per-reviewer changes that don’t affect totals), while the fallback is more stable (immune to non-review PR churn).

### Backward compatibility

The `activity` key in the cache is optional. Old v8 caches without it work fine — they skip the optimization on their first run (all three tier conditions require `cached_activity is not None`) and populate the `activity` key afterward.

## Page rendering

### Chart.js integration

The page uses [Chart.js 4.4.7](https://www.chartjs.org/) loaded from jsDelivr CDN. Two chart types are rendered:

**Overview chart** (line with area fill):
- Full-width, 250px height
- Shows combined activity (reviews + comments + merges merged via `mergeMonthly()`)
- GitHub blue color: `rgb(31, 111, 200)` with 15% opacity fill
- Smooth curves (tension: 0.3), points hidden until hover
- Up to 12 x-axis tick labels, y-axis starts at zero
- Interactive tooltips showing total PR count with review/comment/merge breakdown

Each reviewer card shows: `N PRs reviewed | N commented on | N merged`. “PRs reviewed” and “commented on” are hyperlinks to the corresponding GitHub search results (using `reviewed-by:` and `commenter:` qualifiers with `-author:` exclusion and `updated:>=` date filters). When `period_counts` data is available and the selected period is not “all”, the reviewed and commented counts come from `period_counts` (fetched via `updated:>=` queries), ensuring they match the hyperlink results. Merged counts always use summed monthly data since no `merged-by:` search qualifier exists.

The summary line above the overview chart shows: `N reviewers — N PRs reviewed — N PRs commented on — N PRs merged`. These counts come from repo-wide GitHub search queries (not per-reviewer sums) and update when the period filter changes.

**Sparkline charts** (per-reviewer miniatures):
- Full card width, 60px height
- No animation, no tooltips, no axes
- Same color scheme as overview, 1.5px border

### Dense month generation

Both charts use `buildDenseMonths()` to convert sparse monthly data (only months with activity) into dense arrays suitable for Chart.js:

```javascript
// Input:  {"2024-01": 5, "2024-03": 3}
// Output: {labels: ["2024-01", "2024-02", "2024-03"], values: [5, 0, 3]}
```

This fills gaps with zeros so the time axis is continuous.

### Period filtering

A dropdown allows filtering to recent time windows:

| Period | Value | Filter |
|--------|-------|--------|
| All | `all` | No filtering |
| Last month | `1` | Last 1 month |
| Last 3 months | `3` | Last 3 months |
| Last 6 months | `6` | Last 6 months |
| Last 12 months | `12` | Last 12 months |
| Last 24 months | `24` | Last 24 months |

The dropdown value is the month count as a string (or `all`). Changing the period re-renders the overview chart, all visible sparklines, and the summary counts. Per-reviewer chart filtering is done client-side by computing a cutoff month string from the current date and discarding earlier entries. Summary counts are pre-computed server-side for each period via date-qualified search queries, so the JS simply selects `DATA.repo_totals[currentPeriod]`.

### GitHub-style CSS

The page replicates GitHub’s visual design:
- Font stack: `-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif`
- Max width: 1012px (GitHub’s standard content width)
- Color palette: `#1f2328` text, `#656d76` secondary, `#0969da` links, `#d1d9e0` borders, `#f6f8fa` background accents
- 2-column card grid on desktop, single column below 768px
- 48px circular avatars with subtle borders

## CLI interface

```
gh reviewers-graph OWNER/REPO [options]
```

| Argument | Default | Description |
|----------|---------|-------------|
| `repo` | (required) | Repository in OWNER/REPO format |
| `--output` | `./repos` | Base reports directory |
| `--refresh` | `false` | Force re-fetch, ignoring cache |
| `--top` | `100` | Number of top reviewers to include |
| `--no-open` | `false` | Don’t open the output in a browser |
| `--exclude` | `""` | Comma-separated logins to exclude (e.g., `bot1,bot2`) |

Authentication is handled by the `gh` CLI — no token flags or environment variables needed.

## Performance

Discovery uses a two-phase approach (flat-field candidate collection + count-only ranking) which completes in ~10 seconds even for large repos. An earlier approach using `search()` with nested `reviews()` / `comments()` connections was abandoned because it triggered GitHub’s secondary rate limits regardless of concurrency level or `first:` parameter size. After discovery, avatars, monthly counts, merge counts, and period counts all run concurrently — so the total wall-clock time for the post-discovery phase is determined by whichever sub-phase takes longest, rather than the sum of all four.

A sequential `repository.pullRequests` approach that was tried initially for merge-count data required 370s (283 sequential calls). Using search-based parallel pagination with 10 workers, that now takes just ~25s — which is ~15x faster.

## Testing

Tests are run with pytest:

```bash
python3 -m pytest tests/ -v
```

### Test infrastructure

Since the main script has no `.py` extension, tests use `importlib.machinery.SourceFileLoader` to load it as a Python module. The loaded module is registered as `sys.modules["reviewers"]` and all test files import from `conftest.reviewers`. Patches use `patch.object(reviewers, ...)` rather than string-based `patch("module.func")`.

### Test organization

| File | Tests | Coverage |
|------|-------|----------|
| `test_graphql.py` | 17 | `_graphql_request()`: subprocess success, errors, retries, rate limits, variable passing |
| `test_cli.py` | 6 | Argument parsing: defaults, validation, `--exclude` default and parsing |
| `test_main.py` | 16 | Integration: cache hit, stale cache, refresh, no cache, output summary; incremental update: existing/new/frozen reviewers, historical backfill, period_counts flow; activity-check: full skip (with period_counts), full skip fallback (repo_totals), skip discovery, skip merges, backward compat |
| `test_fetch.py` | 38 | Fetch functions: avatars, discovery, merge counts, monthly counts, repo activity, reviewer period counts, scrape fallback |
| `test_aggregation.py` | 8 | `build_output_data()`: sorting, totals, empty input, inactive filtering, comment-only users, merge-only users, period_counts attachment |
| `test_bot_filter.py` | 7 | `is_bot()`: GitHub App bots, project bots, human logins, case insensitivity, `KNOWN_BOTS` entries, `--exclude` separation |
| `test_cache.py` | 11 | Cache I/O: round-trip, missing files, directory creation, v1—v7 staleness guards, v8 backward compat (no activity key) |
| `test_month_ranges.py` | 5 | `generate_month_ranges()`: standard, single month, leap year, cross-year |
| `test_output.py` | 3 | Output file generation and inlined data content |
| `test_rate_limit.py` | 16 | Rate limit: info parsing, budget estimation (fresh + incremental), budget check output, countdown timer (with cached target reuse, fallback, too-far guard) |
| `test_schema.py` | 9 | JSON Schema validation: sample data, minimal valid, empty reviewers, wrong version rejected, missing/extra fields rejected, bad month format, invalid period keys |

Total: 136 unit tests + 18 e2e tests, 99.4% coverage (99% minimum enforced).
