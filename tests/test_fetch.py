# tests/test_fetch.py
"""Tests for fetch_repo_start, fetch_avatars, discover_reviewers,
fetch_merge_counts, and fetch_monthly_counts."""

from unittest.mock import patch

from conftest import reviewers


# ---------- fetch_repo_start ----------


def test_fetch_repo_start(mock_graphql):
    mock_graphql.return_value = {"repository": {"createdAt": "2020-03-15T10:30:00Z"}}
    result = reviewers.fetch_repo_start("owner", "repo")
    assert result == "2020-03"
    mock_graphql.assert_called_once()


# ---------- fetch_repo_activity ----------


def test_fetch_repo_activity_basic(mock_graphql):
    mock_data = {
        "repository": {
            "pullRequests": {
                "totalCount": 5432,
                "nodes": [{"updatedAt": "2026-02-22T15:30:00Z"}],
            },
            "mergedPRs": {"totalCount": 2100},
        },
    }
    # Add all 18 search aliases (6 periods x 3 metrics)
    for period in ["all", "1", "3", "6", "12", "24"]:
        mock_data[f"reviewed_{period}"] = {"issueCount": 3200}
        mock_data[f"commented_{period}"] = {"issueCount": 4100}
        mock_data[f"merged_{period}"] = {"issueCount": 2100}
    mock_graphql.return_value = mock_data
    result = reviewers.fetch_repo_activity("owner", "repo")
    assert result["last_pr_updated_at"] == "2026-02-22T15:30:00Z"
    assert result["total_pr_count"] == 5432
    assert result["total_merged_prs"] == 2100
    assert result["total_reviewed_prs"] == 3200
    assert result["total_commented_prs"] == 4100
    assert result["repo_totals"]["all"]["reviewed"] == 3200
    assert result["repo_totals"]["all"]["commented"] == 4100
    assert result["repo_totals"]["all"]["merged"] == 2100
    assert result["repo_totals"]["6"]["reviewed"] == 3200
    mock_graphql.assert_called_once()


def test_fetch_repo_activity_empty_repo(mock_graphql):
    mock_data = {
        "repository": {
            "pullRequests": {
                "totalCount": 0,
                "nodes": [],
            },
            "mergedPRs": {"totalCount": 0},
        },
    }
    for period in ["all", "1", "3", "6", "12", "24"]:
        mock_data[f"reviewed_{period}"] = {"issueCount": 0}
        mock_data[f"commented_{period}"] = {"issueCount": 0}
        mock_data[f"merged_{period}"] = {"issueCount": 0}
    mock_graphql.return_value = mock_data
    result = reviewers.fetch_repo_activity("owner", "repo")
    assert result["last_pr_updated_at"] is None
    assert result["total_pr_count"] == 0
    assert result["total_merged_prs"] == 0
    assert result["total_reviewed_prs"] == 0
    assert result["total_commented_prs"] == 0
    assert result["repo_totals"]["all"]["merged"] == 0


def test_fetch_repo_activity_day_clamping(mock_graphql):
    """Going back 1 month from March 31 clamps to Feb 28 (not Feb 31)."""
    from unittest.mock import patch
    from datetime import datetime, timezone

    mock_data = {
        "repository": {
            "pullRequests": {
                "totalCount": 10,
                "nodes": [{"updatedAt": "2026-03-31T00:00:00Z"}],
            },
            "mergedPRs": {"totalCount": 5},
        },
    }
    for period in ["all", "1", "3", "6", "12", "24"]:
        mock_data[f"reviewed_{period}"] = {"issueCount": 0}
        mock_data[f"commented_{period}"] = {"issueCount": 0}
        mock_data[f"merged_{period}"] = {"issueCount": 0}
    mock_graphql.return_value = mock_data

    fake_now = datetime(2026, 3, 31, tzinfo=timezone.utc)
    with patch.object(reviewers, "datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.fromisoformat = datetime.fromisoformat
        reviewers.fetch_repo_activity("owner", "repo")

    # Verify the query contains "created:>=2026-02-28" (clamped from 31)
    query_arg = mock_graphql.call_args[0][0]
    assert "updated:>=2026-02-28" in query_arg


# ---------- fetch_avatars ----------


def test_fetch_avatars_basic(mock_graphql):
    mock_graphql.return_value = {
        "u_alice": {"avatarUrl": "https://a.com/alice.png", "login": "alice"},
        "u_bob": {"avatarUrl": "https://a.com/bob.png", "login": "bob"},
        "u_carol": {"avatarUrl": "https://a.com/carol.png", "login": "carol"},
        "rateLimit": {"remaining": 4000, "resetAt": ""},
    }
    result = reviewers.fetch_avatars(["alice", "bob", "carol"])
    assert result["alice"] == "https://a.com/alice.png"
    assert result["bob"] == "https://a.com/bob.png"
    assert result["carol"] == "https://a.com/carol.png"


def test_fetch_avatars_missing_user(mock_graphql):
    mock_graphql.return_value = {
        "u_alice": {"avatarUrl": "https://a.com/alice.png", "login": "alice"},
        "u_gone": None,
        "rateLimit": {"remaining": 4000, "resetAt": ""},
    }
    result = reviewers.fetch_avatars(["alice", "gone"])
    assert result["alice"] == "https://a.com/alice.png"
    assert result["gone"] == "https://github.com/gone.png"


def test_fetch_avatars_batching(mock_graphql):
    # 16 logins should require 2 batches (batch_size=15)
    logins = [f"user{i}" for i in range(16)]

    def side_effect(query, **kwargs):
        data = {"rateLimit": {"remaining": 4000, "resetAt": ""}}
        for login in logins:
            safe = "u_" + login.replace("-", "_").replace(".", "_")
            if safe + ":" in query:
                data[safe] = {
                    "avatarUrl": f"https://a.com/{login}.png",
                    "login": login,
                }
        return data

    mock_graphql.side_effect = side_effect
    result = reviewers.fetch_avatars(logins)
    assert len(result) == 16
    assert mock_graphql.call_count == 2


# ---------- discover_reviewers ----------


def _pr_node(review_authors, comment_authors=None):
    return {
        "reviews": {
            "nodes": [
                {"author": {"login": a} if a else {"login": None}}
                for a in review_authors
            ],
        },
        "comments": {
            "nodes": [
                {"author": {"login": a} if a else {"login": None}}
                for a in (comment_authors or [])
            ],
        },
    }


def _phase1_response(pr_nodes):
    """Build a MERGE_SEARCH_QUERY response for Phase 1 of discovery."""
    return {
        "search": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": pr_nodes,
        },
    }


def _phase1_pr(author, merged_by=None):
    """Build a flat-field PR node for Phase 1."""
    return {
        "createdAt": "2026-02-15T00:00:00Z",
        "author": {"login": author} if author else None,
        "mergedBy": {"login": merged_by} if merged_by else None,
    }


def _phase2_response(**alias_counts):
    """Build a count-alias response for Phase 2 of discovery.

    Usage: _phase2_response(q0=5, q1=3, q2=2, q3=1)
    """
    result = {"rateLimit": {"remaining": 4000}}
    for alias, count in alias_counts.items():
        result[alias] = {"issueCount": count}
    return result


@patch("time.sleep")
def test_discover_reviewers_single_chunk(mock_sleep, mock_graphql):
    """1-month repo, Phase 1 finds candidates, Phase 2 ranks them."""
    from datetime import datetime, timezone

    # Phase 1: alice authored, bob merged
    p1 = _phase1_response([_phase1_pr("alice", "bob")])
    # Phase 2: sorted candidates = [alice, bob]
    # q0=alice reviewed, q1=alice commented, q2=bob reviewed, q3=bob commented
    p2 = _phase2_response(q0=5, q1=3, q2=2, q3=1)

    def route(query, variables=None, allow_partial=False):
        return p1 if variables else p2

    mock_graphql.side_effect = route

    fake_now = datetime(2026, 2, 15, tzinfo=timezone.utc)
    with patch.object(reviewers, "datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.fromisoformat = datetime.fromisoformat
        result = reviewers.discover_reviewers("o", "r", top_n=10, start_month="2026-02")

    assert result[0] == "alice"  # alice: 5+3=8
    assert result[1] == "bob"  # bob: 2+1=3
    # 1 Phase 1 call + 1 Phase 2 batch = 2 API calls
    assert mock_graphql.call_count == 2


@patch("time.sleep")
def test_discover_reviewers_multiple_months(mock_sleep, mock_graphql):
    """Multi-month repo: Phase 1 scans all months, Phase 2 ranks."""
    from datetime import datetime, timezone

    p1 = _phase1_response([_phase1_pr("alice", "bob")])
    p2 = _phase2_response(q0=10, q1=5, q2=3, q3=2)

    def route(query, variables=None, allow_partial=False):
        return p1 if variables else p2

    mock_graphql.side_effect = route

    fake_now = datetime(2026, 6, 15, tzinfo=timezone.utc)
    with patch.object(reviewers, "datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.fromisoformat = datetime.fromisoformat
        result = reviewers.discover_reviewers("o", "r", top_n=10, start_month="2026-01")

    assert result[0] == "alice"
    assert result[1] == "bob"
    # 6 Phase 1 calls + 1 Phase 2 batch = 7 API calls
    assert mock_graphql.call_count == 7


@patch("time.sleep")
def test_discover_reviewers_filters_bots(mock_sleep, mock_graphql):
    from datetime import datetime, timezone

    # Phase 1: alice is human, bots should be excluded from candidates
    p1 = _phase1_response(
        [
            _phase1_pr("alice", "dependabot[bot]"),
            _phase1_pr("renovate-bot"),
        ]
    )
    # Phase 2: only alice as candidate
    p2 = _phase2_response(q0=5, q1=3)

    def route(query, variables=None, allow_partial=False):
        return p1 if variables else p2

    mock_graphql.side_effect = route

    fake_now = datetime(2026, 2, 15, tzinfo=timezone.utc)
    with patch.object(reviewers, "datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.fromisoformat = datetime.fromisoformat
        result = reviewers.discover_reviewers("o", "r", top_n=10, start_month="2026-02")

    assert "alice" in result
    assert "dependabot[bot]" not in result
    assert "renovate-bot" not in result


@patch("time.sleep")
def test_discover_reviewers_respects_top_n(mock_sleep, mock_graphql):
    from datetime import datetime, timezone

    p1 = _phase1_response(
        [
            _phase1_pr("alice", "bob"),
            _phase1_pr("carol", "dave"),
        ]
    )
    # sorted: alice, bob, carol, dave
    # q0=alice_rev, q1=alice_com, q2=bob_rev, q3=bob_com,
    # q4=carol_rev, q5=carol_com, q6=dave_rev, q7=dave_com
    p2 = _phase2_response(q0=10, q1=5, q2=8, q3=3, q4=4, q5=2, q6=1, q7=0)

    def route(query, variables=None, allow_partial=False):
        return p1 if variables else p2

    mock_graphql.side_effect = route

    fake_now = datetime(2026, 2, 15, tzinfo=timezone.utc)
    with patch.object(reviewers, "datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.fromisoformat = datetime.fromisoformat
        result = reviewers.discover_reviewers("o", "r", top_n=2, start_month="2026-02")

    assert len(result) == 2
    assert result[0] == "alice"  # 10+5=15
    assert result[1] == "bob"  # 8+3=11


@patch("time.sleep")
def test_discover_reviewers_no_candidates(mock_sleep, mock_graphql):
    """Empty months produce no candidates and no Phase 2 calls."""
    from datetime import datetime, timezone

    p1 = _phase1_response([])
    mock_graphql.return_value = p1

    fake_now = datetime(2026, 2, 15, tzinfo=timezone.utc)
    with patch.object(reviewers, "datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.fromisoformat = datetime.fromisoformat
        result = reviewers.discover_reviewers("o", "r", top_n=10, start_month="2026-02")

    assert result == []
    # Only Phase 1 call, no Phase 2
    assert mock_graphql.call_count == 1


@patch("time.sleep")
def test_discover_reviewers_unsearchable_merger(mock_sleep, mock_graphql):
    """Unsearchable users who merge many PRs still appear in results."""
    from datetime import datetime, timezone

    # Phase 1: alice authored + reviewed, trflynn merged many PRs
    p1 = _phase1_response(
        [
            _phase1_pr("alice", "trflynn"),
            _phase1_pr("bob", "trflynn"),
            _phase1_pr("carol", "trflynn"),
        ]
    )
    # Phase 2: sorted candidates = [alice, bob, carol, trflynn]
    # trflynn is unsearchable: reviewed-by and commenter both return 0
    p2 = _phase2_response(q0=10, q1=5, q2=3, q3=1, q4=2, q5=1, q6=0, q7=0)

    def route(query, variables=None, allow_partial=False):
        return p1 if variables else p2

    mock_graphql.side_effect = route

    fake_now = datetime(2026, 2, 15, tzinfo=timezone.utc)
    with patch.object(reviewers, "datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.fromisoformat = datetime.fromisoformat
        result = reviewers.discover_reviewers("o", "r", top_n=10, start_month="2026-02")

    assert "alice" in result
    assert "trflynn" in result  # included via merge frequency from Phase 1


@patch("time.sleep")
def test_discover_reviewers_no_start_month(mock_sleep, mock_graphql):
    """When start_month is None, calls fetch_repo_start internally."""
    from datetime import datetime, timezone

    # fetch_repo_start response, then Phase 1, then Phase 2
    repo_start = {"repository": {"createdAt": "2026-02-01T00:00:00Z"}}
    p1 = _phase1_response([_phase1_pr("alice")])
    p2 = _phase2_response(q0=5, q1=3)

    call_count = [0]

    def route(query, variables=None, allow_partial=False):
        call_count[0] += 1
        if variables and "owner" in variables:
            return repo_start
        if variables and "q" in variables:
            return p1
        return p2

    mock_graphql.side_effect = route

    fake_now = datetime(2026, 2, 15, tzinfo=timezone.utc)
    with patch.object(reviewers, "datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.fromisoformat = datetime.fromisoformat
        result = reviewers.discover_reviewers("o", "r", top_n=10)

    assert "alice" in result
    # 1 fetch_repo_start + 1 Phase 1 + 1 Phase 2 = 3
    assert mock_graphql.call_count == 3


# ---------- fetch_merge_counts ----------


@patch("time.sleep")
def test_fetch_merge_counts_basic(mock_sleep, mock_graphql):
    month_ranges = [("2024-01", "2024-01-01", "2024-01-31")]
    mock_graphql.return_value = {
        "search": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [
                {
                    "createdAt": "2024-01-15T00:00:00Z",
                    "author": {"login": "author1"},
                    "mergedBy": {"login": "alice"},
                },
                {
                    "createdAt": "2024-01-20T00:00:00Z",
                    "author": {"login": "author2"},
                    "mergedBy": {"login": "bob"},
                },
            ],
        }
    }
    result = reviewers.fetch_merge_counts("o", "r", ["alice", "bob"], month_ranges)
    assert result["alice"]["2024-01"] == 1
    assert result["bob"]["2024-01"] == 1


@patch("time.sleep")
def test_fetch_merge_counts_skips_self_merges(mock_sleep, mock_graphql):
    month_ranges = [("2024-01", "2024-01-01", "2024-01-31")]
    mock_graphql.return_value = {
        "search": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [
                {
                    "createdAt": "2024-01-15T00:00:00Z",
                    "author": {"login": "alice"},
                    "mergedBy": {"login": "alice"},  # self-merge
                },
            ],
        }
    }
    result = reviewers.fetch_merge_counts("o", "r", ["alice"], month_ranges)
    assert result["alice"] == {}


@patch("time.sleep")
def test_fetch_merge_counts_skips_unknown_logins(mock_sleep, mock_graphql):
    month_ranges = [("2024-01", "2024-01-01", "2024-01-31")]
    mock_graphql.return_value = {
        "search": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [
                {
                    "createdAt": "2024-01-15T00:00:00Z",
                    "author": {"login": "author1"},
                    "mergedBy": {"login": "stranger"},
                },
            ],
        }
    }
    result = reviewers.fetch_merge_counts("o", "r", ["alice"], month_ranges)
    assert result["alice"] == {}


@patch("time.sleep")
def test_fetch_merge_counts_pagination(mock_sleep, mock_graphql):
    month_ranges = [("2024-01", "2024-01-01", "2024-01-31")]
    page1 = {
        "search": {
            "pageInfo": {"hasNextPage": True, "endCursor": "c1"},
            "nodes": [
                {
                    "createdAt": "2024-01-10T00:00:00Z",
                    "author": {"login": "x"},
                    "mergedBy": {"login": "alice"},
                },
            ],
        }
    }
    page2 = {
        "search": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [
                {
                    "createdAt": "2024-01-20T00:00:00Z",
                    "author": {"login": "y"},
                    "mergedBy": {"login": "alice"},
                },
            ],
        }
    }
    mock_graphql.side_effect = [page1, page2]
    result = reviewers.fetch_merge_counts("o", "r", ["alice"], month_ranges)
    assert result["alice"]["2024-01"] == 2
    assert mock_graphql.call_count == 2


@patch("time.sleep")
def test_fetch_merge_counts_null_merged_by(mock_sleep, mock_graphql):
    """PRs with mergedBy: None are skipped."""
    month_ranges = [("2024-01", "2024-01-01", "2024-01-31")]
    mock_graphql.return_value = {
        "search": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "nodes": [
                {
                    "createdAt": "2024-01-15T00:00:00Z",
                    "author": {"login": "author1"},
                    "mergedBy": None,
                },
                {
                    "createdAt": "2024-01-20T00:00:00Z",
                    "author": {"login": "author2"},
                    "mergedBy": {"login": "alice"},
                },
            ],
        }
    }
    result = reviewers.fetch_merge_counts("o", "r", ["alice"], month_ranges)
    assert result["alice"]["2024-01"] == 1


# ---------- fetch_monthly_counts ----------


@patch("time.sleep")
def test_fetch_monthly_counts_basic(mock_sleep, mock_graphql):
    month_ranges = [
        ("2024-01", "2024-01-01", "2024-01-31"),
        ("2024-02", "2024-02-01", "2024-02-29"),
    ]
    logins = ["alice", "bob"]

    def side_effect(query, **kwargs):
        data = {"rateLimit": {"remaining": 4000, "resetAt": ""}}
        # Each alias q0..qN maps to an issueCount
        for i in range(25):
            alias = f"q{i}"
            if alias + ":" in query:
                data[alias] = {"issueCount": 5}
        return data

    mock_graphql.side_effect = side_effect
    reviews, comments = reviewers.fetch_monthly_counts("o", "r", logins, month_ranges)

    # 2 logins * 2 months = 4 review queries + 4 comment queries = 8 tasks
    assert "alice" in reviews
    assert "bob" in reviews
    assert "alice" in comments
    assert "bob" in comments


@patch("time.sleep")
def test_fetch_monthly_counts_batching(mock_sleep, mock_graphql):
    """Enough tasks to require >1 batch (>25 aliases)."""
    month_ranges = [
        ("2024-01", "2024-01-01", "2024-01-31"),
        ("2024-02", "2024-02-01", "2024-02-29"),
        ("2024-03", "2024-03-01", "2024-03-31"),
        ("2024-04", "2024-04-01", "2024-04-30"),
        ("2024-05", "2024-05-01", "2024-05-31"),
        ("2024-06", "2024-06-01", "2024-06-30"),
        ("2024-07", "2024-07-01", "2024-07-31"),
    ]
    logins = ["alice", "bob"]
    # 2 logins * 7 months * 2 kinds = 28 tasks -> ceil(28/25) = 2 batches

    def side_effect(query, **kwargs):
        data = {"rateLimit": {"remaining": 4000, "resetAt": ""}}
        for i in range(25):
            alias = f"q{i}"
            if alias + ":" in query:
                data[alias] = {"issueCount": 1}
        return data

    mock_graphql.side_effect = side_effect
    reviews, comments = reviewers.fetch_monthly_counts("o", "r", logins, month_ranges)
    assert mock_graphql.call_count == 2


@patch("time.sleep")
def test_fetch_monthly_counts_zero_counts_omitted(mock_sleep, mock_graphql):
    month_ranges = [("2024-01", "2024-01-01", "2024-01-31")]
    logins = ["alice"]

    def side_effect(query, **kwargs):
        data = {"rateLimit": {"remaining": 4000, "resetAt": ""}}
        for i in range(25):
            alias = f"q{i}"
            if alias + ":" in query:
                data[alias] = {"issueCount": 0}
        return data

    mock_graphql.side_effect = side_effect
    reviews, comments = reviewers.fetch_monthly_counts("o", "r", logins, month_ranges)
    # Zero counts should not appear in results
    assert reviews["alice"] == {}
    assert comments["alice"] == {}


# ---------- fetch_reviewer_period_counts ----------


@patch("time.sleep")
def test_fetch_reviewer_period_counts_basic(mock_sleep, mock_graphql):
    """Fetches reviewed and commented counts for each period."""
    logins = ["alice"]

    def side_effect(query, **kwargs):
        data = {"rateLimit": {"remaining": 4000, "resetAt": ""}}
        for i in range(25):
            alias = f"q{i}"
            if alias + ":" in query:
                data[alias] = {"issueCount": 10}
        return data

    mock_graphql.side_effect = side_effect
    result = reviewers.fetch_reviewer_period_counts("o", "r", logins)

    assert "alice" in result
    # Should have all 5 periods
    for period in ["1", "3", "6", "12", "24"]:
        assert period in result["alice"]
        assert result["alice"][period]["reviewed"] == 10
        assert result["alice"][period]["commented"] == 10


@patch("time.sleep")
def test_fetch_reviewer_period_counts_empty(mock_sleep, mock_graphql):
    """Empty login list returns empty dict."""
    result = reviewers.fetch_reviewer_period_counts("o", "r", [])
    assert result == {}
    mock_graphql.assert_not_called()


@patch("time.sleep")
def test_fetch_reviewer_period_counts_batching(mock_sleep, mock_graphql):
    """Multiple logins require multiple batches (>25 aliases)."""
    # 3 logins * 5 periods * 2 kinds = 30 tasks -> ceil(30/25) = 2 batches
    logins = ["alice", "bob", "carol"]

    def side_effect(query, **kwargs):
        data = {"rateLimit": {"remaining": 4000, "resetAt": ""}}
        for i in range(25):
            alias = f"q{i}"
            if alias + ":" in query:
                data[alias] = {"issueCount": 5}
        return data

    mock_graphql.side_effect = side_effect
    result = reviewers.fetch_reviewer_period_counts("o", "r", logins)
    assert mock_graphql.call_count == 2
    for login in logins:
        assert login in result


@patch("time.sleep")
def test_fetch_reviewer_period_counts_day_clamping(mock_sleep, mock_graphql):
    """Going back 1 month from March 31 clamps to Feb 28."""
    from datetime import datetime, timezone

    def side_effect(query, **kwargs):
        data = {"rateLimit": {"remaining": 4000, "resetAt": ""}}
        for i in range(25):
            alias = f"q{i}"
            if alias + ":" in query:
                data[alias] = {"issueCount": 1}
        return data

    mock_graphql.side_effect = side_effect

    fake_now = datetime(2026, 3, 31, tzinfo=timezone.utc)
    with patch.object(reviewers, "datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        mock_dt.fromisoformat = datetime.fromisoformat
        reviewers.fetch_reviewer_period_counts("o", "r", ["alice"])

    query_arg = mock_graphql.call_args[0][0]
    assert "updated:>=2026-02-28" in query_arg


# ---------- _scrape_search_count ----------


@patch("time.sleep")
def test_scrape_search_count_basic(mock_sleep):
    """Parses Open + Closed counts from HTML."""
    from unittest.mock import MagicMock

    html = b'<a href="#">2 Open</a> <a href="#">20 Closed</a>'
    mock_resp = MagicMock()
    mock_resp.read.return_value = html
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = reviewers._scrape_search_count("https://example.com")
    assert result == 22


@patch("time.sleep")
def test_scrape_search_count_comma_numbers(mock_sleep):
    """Parses counts with comma separators (e.g. 1,234)."""
    from unittest.mock import MagicMock

    html = b"<a>1,234 Open</a> <a>5,678 Closed</a>"
    mock_resp = MagicMock()
    mock_resp.read.return_value = html
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = reviewers._scrape_search_count("https://example.com")
    assert result == 6912


@patch("time.sleep")
def test_scrape_search_count_429_retry(mock_sleep):
    """HTTP 429 triggers retry; succeeds on second attempt."""
    import urllib.error
    from unittest.mock import MagicMock

    error_429 = urllib.error.HTTPError(
        "url", 429, "Too Many Requests", {"Retry-After": "2"}, None
    )
    html = b"<a>5 Open</a> <a>10 Closed</a>"
    mock_resp = MagicMock()
    mock_resp.read.return_value = html
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", side_effect=[error_429, mock_resp]):
        with patch("random.uniform", return_value=1.0):
            result = reviewers._scrape_search_count("https://example.com")
    assert result == 15
    assert mock_sleep.call_count >= 1


@patch("time.sleep")
def test_scrape_search_count_network_error(mock_sleep):
    """Network errors return 0."""
    import urllib.error

    with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("fail")):
        result = reviewers._scrape_search_count("https://example.com")
    assert result == 0


@patch("time.sleep")
def test_scrape_search_count_no_matches(mock_sleep):
    """HTML without Open/Closed patterns returns 0."""
    from unittest.mock import MagicMock

    html = b"<html><body>No search results</body></html>"
    mock_resp = MagicMock()
    mock_resp.read.return_value = html
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = reviewers._scrape_search_count("https://example.com")
    assert result == 0


@patch("time.sleep")
def test_scrape_search_count_non_429_http_error(mock_sleep):
    """Non-429 HTTP errors return 0 immediately."""
    import urllib.error

    error_500 = urllib.error.HTTPError("url", 500, "Internal Server Error", {}, None)
    with patch("urllib.request.urlopen", side_effect=error_500):
        result = reviewers._scrape_search_count("https://example.com")
    assert result == 0


@patch("time.sleep")
def test_scrape_search_count_429_exhausted(mock_sleep):
    """Exhausting all retries returns 0."""
    import urllib.error

    error_429 = urllib.error.HTTPError(
        "url", 429, "Too Many Requests", {"Retry-After": "1"}, None
    )
    with patch("urllib.request.urlopen", side_effect=error_429):
        with patch("random.uniform", return_value=0.5):
            result = reviewers._scrape_search_count(
                "https://example.com", max_retries=2
            )
    assert result == 0
    # 2 retries on attempts 0 and 1, then attempt 2 is final non-retry
    assert mock_sleep.call_count == 2


# ---------- _ScrapeRateLimiter ----------


@patch("time.sleep")
def test_scrape_rate_limiter_throttles(mock_sleep):
    """Rate limiter enforces minimum interval between requests."""
    limiter = reviewers._ScrapeRateLimiter(10)  # 10 req/s = 0.1s interval
    limiter.wait()  # first call
    limiter.wait()  # second call should trigger sleep
    assert mock_sleep.call_count >= 1


# ---------- scrape_unsearchable_period_counts ----------


@patch("time.sleep")
@patch.object(reviewers, "_scrape_search_count")
def test_scrape_unsearchable_skips_inactive(mock_scrape, mock_sleep):
    """Unsearchable users with no monthly activity are not scraped."""
    period_counts = {
        "alice": {
            "1": {"reviewed": 0, "commented": 0},
            "3": {"reviewed": 0, "commented": 0},
        },
    }
    reviewers_data = {
        "alice": {
            "monthly": {},
            "comment_monthly": {},
            "merge_monthly": {},
        },
    }
    reviewers.scrape_unsearchable_period_counts("o", "r", period_counts, reviewers_data)
    mock_scrape.assert_not_called()
    # Period counts unchanged (still zeros)
    assert period_counts["alice"]["1"]["reviewed"] == 0


@patch("time.sleep")
@patch.object(reviewers, "_scrape_search_count")
def test_scrape_unsearchable_scrapes_active(mock_scrape, mock_sleep):
    """Unsearchable users with monthly activity are scraped."""
    period_counts = {
        "alice": {
            "1": {"reviewed": 10, "commented": 5},
        },
        "bob": {
            "1": {"reviewed": 0, "commented": 0},
            "3": {"reviewed": 0, "commented": 0},
            "6": {"reviewed": 0, "commented": 0},
            "12": {"reviewed": 0, "commented": 0},
            "24": {"reviewed": 0, "commented": 0},
        },
    }
    reviewers_data = {
        "alice": {
            "monthly": {"2024-01": 10},
            "comment_monthly": {},
            "merge_monthly": {},
        },
        "bob": {
            "monthly": {},
            "comment_monthly": {},
            "merge_monthly": {"2024-01": 5},
        },
    }
    mock_scrape.return_value = 7

    reviewers.scrape_unsearchable_period_counts("o", "r", period_counts, reviewers_data)

    # Bob was scraped (5 periods * 2 kinds = 10 calls)
    assert mock_scrape.call_count == 10
    assert period_counts["bob"]["1"]["reviewed"] == 7
    assert period_counts["bob"]["1"]["commented"] == 7
    # Alice was not touched (not unsearchable)
    assert period_counts["alice"]["1"]["reviewed"] == 10


@patch("time.sleep")
@patch.object(reviewers, "_scrape_search_count")
def test_scrape_unsearchable_gate_skips_zero_users(mock_scrape, mock_sleep):
    """Users with zero activity in the 24mo gate period skip shorter periods."""
    period_counts = {
        "alice": {
            "1": {"reviewed": 0, "commented": 0},
            "3": {"reviewed": 0, "commented": 0},
            "6": {"reviewed": 0, "commented": 0},
            "12": {"reviewed": 0, "commented": 0},
            "24": {"reviewed": 0, "commented": 0},
        },
    }
    reviewers_data = {
        "alice": {
            "monthly": {},
            "comment_monthly": {},
            "merge_monthly": {"2024-01": 3},
        },
    }
    mock_scrape.return_value = 0

    reviewers.scrape_unsearchable_period_counts("o", "r", period_counts, reviewers_data)

    # Only 2 calls for the gate (24mo reviewed + commented), not 10
    assert mock_scrape.call_count == 2
    # All periods remain zero
    for key in ("1", "3", "6", "12", "24"):
        assert period_counts["alice"][key]["reviewed"] == 0
        assert period_counts["alice"][key]["commented"] == 0


@patch("time.sleep")
@patch.object(reviewers, "_scrape_search_count")
def test_scrape_unsearchable_no_unsearchable(mock_scrape, mock_sleep):
    """No scraping when all users have nonzero GraphQL results."""
    period_counts = {
        "alice": {"1": {"reviewed": 10, "commented": 5}},
        "bob": {"1": {"reviewed": 3, "commented": 2}},
    }
    reviewers_data = {
        "alice": {
            "monthly": {"2024-01": 10},
            "comment_monthly": {},
            "merge_monthly": {},
        },
        "bob": {"monthly": {"2024-01": 3}, "comment_monthly": {}, "merge_monthly": {}},
    }
    reviewers.scrape_unsearchable_period_counts("o", "r", period_counts, reviewers_data)
    mock_scrape.assert_not_called()
