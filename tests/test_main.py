# tests/test_main.py
"""Integration tests for main()."""

import json
from unittest.mock import patch

from conftest import reviewers


def _write_cache(tmp_path, data):
    cache_dir = tmp_path / "owner" / "repo"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "data.json").write_text(json.dumps(data))


@patch.object(reviewers, "webbrowser")
@patch.object(reviewers, "generate_output")
def test_main_with_cache(mock_output, mock_wb, sample_cached_data, tmp_path, capsys):
    """Valid v8 cache triggers incremental update, not full fetch."""
    _write_cache(tmp_path, sample_cached_data)

    with (
        patch.object(
            reviewers, "incremental_update", return_value=sample_cached_data
        ) as mock_inc,
        patch.object(reviewers, "fetch_repo_start") as mock_start,
    ):
        reviewers.main(
            [
                "--output",
                str(tmp_path),
                "owner/repo",
            ]
        )

        mock_inc.assert_called_once_with(
            sample_cached_data, "owner", "repo", 100, exclude=frozenset()
        )
        mock_start.assert_not_called()

    mock_output.assert_called_once()
    assert mock_output.call_args[0][1] == str(tmp_path / "owner" / "repo")
    data_arg = mock_output.call_args[0][0]
    assert data_arg["repo"] == "owner/repo"
    assert len(data_arg["reviewers"]) == 2


@patch.object(reviewers, "get_rate_limit_info", return_value=(None, None))
@patch.object(reviewers, "webbrowser")
@patch.object(reviewers, "generate_output")
def test_main_stale_cache(mock_output, mock_wb, mock_rl, tmp_path, capsys):
    """v7 cache triggers re-fetch."""
    stale = {
        "version": 7,
        "reviewers": {
            "alice": {
                "avatar_url": "x",
                "monthly": {},
                "comment_monthly": {},
                "merge_monthly": {},
            }
        },
    }
    _write_cache(tmp_path, stale)

    with (
        patch.object(
            reviewers, "discover_reviewers", return_value=["alice"]
        ) as mock_disc,
        patch.object(reviewers, "fetch_repo_start", return_value="2024-01"),
        patch.object(reviewers, "fetch_avatars", return_value={"alice": "url"}),
        patch.object(
            reviewers,
            "fetch_monthly_counts",
            return_value=({"alice": {}}, {"alice": {}}),
        ),
        patch.object(reviewers, "fetch_merge_counts", return_value={"alice": {}}),
        patch.object(
            reviewers, "fetch_reviewer_period_counts", return_value={"alice": {}}
        ),
        patch.object(
            reviewers,
            "fetch_repo_activity",
            return_value={
                "last_pr_updated_at": "2024-01-15T00:00:00Z",
                "total_pr_count": 50,
                "total_merged_prs": 20,
                "total_reviewed_prs": 30,
                "total_commented_prs": 15,
                "repo_totals": {
                    "all": {"reviewed": 30, "commented": 15, "merged": 20},
                    "1": {"reviewed": 30, "commented": 15, "merged": 20},
                    "3": {"reviewed": 30, "commented": 15, "merged": 20},
                    "6": {"reviewed": 30, "commented": 15, "merged": 20},
                    "12": {"reviewed": 30, "commented": 15, "merged": 20},
                    "24": {"reviewed": 30, "commented": 15, "merged": 20},
                },
            },
        ),
    ):
        reviewers.main(
            [
                "--output",
                str(tmp_path),
                "owner/repo",
            ]
        )
        mock_disc.assert_called_once()


@patch.object(reviewers, "get_rate_limit_info", return_value=(None, None))
@patch.object(reviewers, "webbrowser")
@patch.object(reviewers, "generate_output")
def test_main_refresh_flag(
    mock_output, mock_wb, mock_rl, sample_cached_data, tmp_path, capsys
):
    """--refresh forces re-fetch even with valid v8 cache."""
    _write_cache(tmp_path, sample_cached_data)

    with (
        patch.object(
            reviewers, "discover_reviewers", return_value=["alice"]
        ) as mock_disc,
        patch.object(reviewers, "fetch_repo_start", return_value="2024-01"),
        patch.object(reviewers, "fetch_avatars", return_value={"alice": "url"}),
        patch.object(
            reviewers,
            "fetch_monthly_counts",
            return_value=({"alice": {}}, {"alice": {}}),
        ),
        patch.object(reviewers, "fetch_merge_counts", return_value={"alice": {}}),
        patch.object(
            reviewers, "fetch_reviewer_period_counts", return_value={"alice": {}}
        ),
        patch.object(
            reviewers,
            "fetch_repo_activity",
            return_value={
                "last_pr_updated_at": "2024-01-15T00:00:00Z",
                "total_pr_count": 50,
                "total_merged_prs": 20,
                "total_reviewed_prs": 30,
                "total_commented_prs": 15,
                "repo_totals": {
                    "all": {"reviewed": 30, "commented": 15, "merged": 20},
                    "1": {"reviewed": 30, "commented": 15, "merged": 20},
                    "3": {"reviewed": 30, "commented": 15, "merged": 20},
                    "6": {"reviewed": 30, "commented": 15, "merged": 20},
                    "12": {"reviewed": 30, "commented": 15, "merged": 20},
                    "24": {"reviewed": 30, "commented": 15, "merged": 20},
                },
            },
        ),
    ):
        reviewers.main(
            [
                "--output",
                str(tmp_path),
                "--refresh",
                "owner/repo",
            ]
        )
        mock_disc.assert_called_once()


@patch.object(reviewers, "get_rate_limit_info", return_value=(None, None))
@patch.object(reviewers, "webbrowser")
@patch.object(reviewers, "generate_output")
def test_main_no_cache(mock_output, mock_wb, mock_rl, tmp_path, capsys):
    """No cache file triggers full fetch pipeline."""
    with (
        patch.object(reviewers, "discover_reviewers", return_value=["alice", "bob"]),
        patch.object(reviewers, "fetch_repo_start", return_value="2024-01"),
        patch.object(
            reviewers,
            "fetch_avatars",
            return_value={
                "alice": "https://a.com/alice.png",
                "bob": "https://a.com/bob.png",
            },
        ),
        patch.object(
            reviewers,
            "fetch_monthly_counts",
            return_value=(
                {"alice": {"2024-01": 10}, "bob": {"2024-01": 5}},
                {"alice": {"2024-01": 2}, "bob": {}},
            ),
        ),
        patch.object(
            reviewers,
            "fetch_merge_counts",
            return_value={
                "alice": {"2024-01": 3},
                "bob": {"2024-01": 1},
            },
        ),
        patch.object(
            reviewers,
            "fetch_reviewer_period_counts",
            return_value={
                "alice": {"1": {"reviewed": 10, "commented": 2}},
                "bob": {"1": {"reviewed": 5, "commented": 0}},
            },
        ),
        patch.object(
            reviewers,
            "fetch_repo_activity",
            return_value={
                "last_pr_updated_at": "2024-01-15T00:00:00Z",
                "total_pr_count": 50,
                "total_merged_prs": 20,
                "total_reviewed_prs": 30,
                "total_commented_prs": 15,
                "repo_totals": {
                    "all": {"reviewed": 30, "commented": 15, "merged": 20},
                    "1": {"reviewed": 30, "commented": 15, "merged": 20},
                    "3": {"reviewed": 30, "commented": 15, "merged": 20},
                    "6": {"reviewed": 30, "commented": 15, "merged": 20},
                    "12": {"reviewed": 30, "commented": 15, "merged": 20},
                    "24": {"reviewed": 30, "commented": 15, "merged": 20},
                },
            },
        ),
    ):
        reviewers.main(
            [
                "--output",
                str(tmp_path),
                "owner/repo",
            ]
        )

    mock_output.assert_called_once()
    assert mock_output.call_args[0][1] == str(tmp_path / "owner" / "repo")
    data_arg = mock_output.call_args[0][0]
    assert data_arg["repo"] == "owner/repo"
    logins = [r["login"] for r in data_arg["reviewers"]]
    assert "alice" in logins
    assert "bob" in logins


@patch.object(reviewers, "webbrowser")
@patch.object(reviewers, "generate_output")
def test_main_output_summary(
    mock_output, mock_wb, sample_cached_data, tmp_path, capsys
):
    """Stdout contains summary with reviewer counts."""
    _write_cache(tmp_path, sample_cached_data)

    with patch.object(reviewers, "incremental_update", return_value=sample_cached_data):
        reviewers.main(
            [
                "--output",
                str(tmp_path),
                "owner/repo",
            ]
        )

    captured = capsys.readouterr()
    assert "2 reviewers" in captured.out
    assert "owner/repo" in captured.out


# --- _prev_month tests ---


def test_prev_month_normal():
    assert reviewers._prev_month("2024-06") == "2024-05"


def test_prev_month_january_wraps_to_december():
    assert reviewers._prev_month("2024-01") == "2023-12"


# --- incremental_update() unit tests ---


@patch.object(reviewers, "get_rate_limit_info", return_value=(None, None))
@patch.object(reviewers, "datetime")
@patch.object(reviewers, "fetch_merge_counts")
@patch.object(reviewers, "fetch_monthly_counts")
@patch.object(reviewers, "fetch_reviewer_period_counts")
@patch.object(reviewers, "fetch_avatars")
@patch.object(reviewers, "discover_reviewers")
@patch.object(reviewers, "fetch_repo_activity")
def test_incremental_update_existing_reviewers(
    mock_activity, mock_disc, mock_av, mock_rpc, mock_mc, mock_merge, mock_dt, mock_rl
):
    """Existing reviewers: sealed months kept, stale months replaced."""
    from datetime import datetime, timezone

    mock_dt.now.return_value = datetime(2024, 5, 15, tzinfo=timezone.utc)
    mock_activity.return_value = {
        "last_pr_updated_at": "2024-05-15T00:00:00Z",
        "total_pr_count": 200,
        "total_merged_prs": 100,
        "total_reviewed_prs": 150,
        "total_commented_prs": 80,
        "repo_totals": {
            "all": {"reviewed": 150, "commented": 80, "merged": 100},
            "1": {"reviewed": 150, "commented": 80, "merged": 100},
            "3": {"reviewed": 150, "commented": 80, "merged": 100},
            "6": {"reviewed": 150, "commented": 80, "merged": 100},
            "12": {"reviewed": 150, "commented": 80, "merged": 100},
            "24": {"reviewed": 150, "commented": 80, "merged": 100},
        },
    }

    cached = {
        "version": 8,
        "start_month": "2024-01",
        "end_month": "2024-03",
        "reviewers": {
            "alice": {
                "avatar_url": "https://a.com/alice.png",
                "monthly": {"2024-01": 10, "2024-02": 5, "2024-03": 3},
                "comment_monthly": {"2024-01": 2, "2024-03": 1},
                "merge_monthly": {"2024-02": 1},
            },
        },
    }

    mock_disc.return_value = ["alice"]
    mock_rpc.return_value = {"alice": {"1": {"reviewed": 3, "commented": 1}}}
    # Stale months: 2024-03 through 2024-05
    # fetch_monthly_counts returns (reviews, comments)
    mock_mc.return_value = (
        {"alice": {"2024-03": 7, "2024-04": 4}},
        {"alice": {"2024-04": 2}},
    )
    mock_merge.return_value = {"alice": {"2024-05": 1}}

    result = reviewers.incremental_update(cached, "owner", "repo", 100)

    assert result["version"] == 8
    assert result["start_month"] == "2024-01"
    assert result["end_month"] == "2024-05"
    alice = result["reviewers"]["alice"]
    # Sealed months (2024-01, 2024-02) kept from cache
    assert alice["monthly"]["2024-01"] == 10
    assert alice["monthly"]["2024-02"] == 5
    # Stale month 2024-03 replaced with new value
    assert alice["monthly"]["2024-03"] == 7
    # New months from stale fetch
    assert alice["monthly"]["2024-04"] == 4
    assert alice["comment_monthly"]["2024-04"] == 2
    assert alice["merge_monthly"]["2024-05"] == 1
    # Sealed comment_monthly 2024-01 preserved, stale 2024-03 cleared (not in new data)
    assert alice["comment_monthly"]["2024-01"] == 2
    assert "2024-03" not in alice["comment_monthly"]
    # Avatar preserved
    assert alice["avatar_url"] == "https://a.com/alice.png"
    # No avatar fetch for existing reviewers
    mock_av.assert_not_called()
    # Activity stored in result
    assert result["activity"] == mock_activity.return_value
    # Period counts stored in result
    assert result["reviewer_period_counts"]["alice"]["1"]["reviewed"] == 3


@patch.object(reviewers, "get_rate_limit_info", return_value=(None, None))
@patch.object(reviewers, "_scrape_fallback_period_counts")
@patch.object(reviewers, "datetime")
@patch.object(reviewers, "fetch_merge_counts")
@patch.object(reviewers, "fetch_monthly_counts")
@patch.object(reviewers, "fetch_reviewer_period_counts")
@patch.object(reviewers, "fetch_avatars")
@patch.object(reviewers, "discover_reviewers")
@patch.object(reviewers, "fetch_repo_activity")
def test_incremental_update_new_reviewer(
    mock_activity,
    mock_disc,
    mock_av,
    mock_rpc,
    mock_mc,
    mock_merge,
    mock_dt,
    mock_scrape,
    mock_rl,
):
    """New reviewer gets historical backfill + stale months + avatar fetch."""
    from datetime import datetime, timezone

    mock_dt.now.return_value = datetime(2024, 5, 15, tzinfo=timezone.utc)
    mock_activity.return_value = {
        "last_pr_updated_at": "2024-05-15T00:00:00Z",
        "total_pr_count": 200,
        "total_merged_prs": 100,
        "total_reviewed_prs": 150,
        "total_commented_prs": 80,
        "repo_totals": {
            "all": {"reviewed": 150, "commented": 80, "merged": 100},
            "1": {"reviewed": 150, "commented": 80, "merged": 100},
            "3": {"reviewed": 150, "commented": 80, "merged": 100},
            "6": {"reviewed": 150, "commented": 80, "merged": 100},
            "12": {"reviewed": 150, "commented": 80, "merged": 100},
            "24": {"reviewed": 150, "commented": 80, "merged": 100},
        },
    }

    cached = {
        "version": 8,
        "start_month": "2024-01",
        "end_month": "2024-03",
        "reviewers": {
            "alice": {
                "avatar_url": "https://a.com/alice.png",
                "monthly": {"2024-01": 10},
                "comment_monthly": {},
                "merge_monthly": {},
            },
        },
    }

    mock_disc.return_value = ["alice", "charlie"]
    mock_av.return_value = {"charlie": "https://a.com/charlie.png"}
    mock_rpc.return_value = {
        "alice": {"1": {"reviewed": 0, "commented": 0}},
        "charlie": {"1": {"reviewed": 3, "commented": 1}},
    }

    # fetch_monthly_counts is called twice: stale (all discovered) + historical (new only)
    # Call order: stale first, historical second
    mock_mc.side_effect = [
        # Stale fetch (alice + charlie, months 2024-03 to 2024-05)
        (
            {"alice": {}, "charlie": {"2024-04": 3}},
            {"alice": {}, "charlie": {"2024-04": 1}},
        ),
        # Historical fetch (charlie only, months 2024-01 to 2024-02)
        (
            {"charlie": {"2024-01": 5, "2024-02": 2}},
            {"charlie": {"2024-01": 1}},
        ),
    ]
    mock_merge.side_effect = [
        # Stale merge fetch
        {"alice": {}, "charlie": {"2024-05": 1}},
        # Historical merge fetch
        {"charlie": {"2024-01": 2}},
    ]

    result = reviewers.incremental_update(cached, "owner", "repo", 100)

    charlie = result["reviewers"]["charlie"]
    assert charlie["avatar_url"] == "https://a.com/charlie.png"
    # Historical + stale combined
    assert charlie["monthly"]["2024-01"] == 5
    assert charlie["monthly"]["2024-02"] == 2
    assert charlie["monthly"]["2024-04"] == 3
    assert charlie["comment_monthly"]["2024-01"] == 1
    assert charlie["comment_monthly"]["2024-04"] == 1
    assert charlie["merge_monthly"]["2024-01"] == 2
    assert charlie["merge_monthly"]["2024-05"] == 1


@patch.object(reviewers, "get_rate_limit_info", return_value=(None, None))
@patch.object(reviewers, "_scrape_fallback_period_counts")
@patch.object(reviewers, "datetime")
@patch.object(reviewers, "fetch_merge_counts")
@patch.object(reviewers, "fetch_monthly_counts")
@patch.object(reviewers, "fetch_reviewer_period_counts")
@patch.object(reviewers, "fetch_avatars")
@patch.object(reviewers, "discover_reviewers")
@patch.object(reviewers, "fetch_repo_activity")
def test_incremental_update_frozen_reviewer(
    mock_activity,
    mock_disc,
    mock_av,
    mock_rpc,
    mock_mc,
    mock_merge,
    mock_dt,
    mock_scrape,
    mock_rl,
):
    """Cached reviewer not re-discovered is kept frozen."""
    from datetime import datetime, timezone

    mock_dt.now.return_value = datetime(2024, 5, 15, tzinfo=timezone.utc)
    mock_activity.return_value = {
        "last_pr_updated_at": "2024-05-15T00:00:00Z",
        "total_pr_count": 200,
        "total_merged_prs": 100,
        "total_reviewed_prs": 150,
        "total_commented_prs": 80,
        "repo_totals": {
            "all": {"reviewed": 150, "commented": 80, "merged": 100},
            "1": {"reviewed": 150, "commented": 80, "merged": 100},
            "3": {"reviewed": 150, "commented": 80, "merged": 100},
            "6": {"reviewed": 150, "commented": 80, "merged": 100},
            "12": {"reviewed": 150, "commented": 80, "merged": 100},
            "24": {"reviewed": 150, "commented": 80, "merged": 100},
        },
    }

    cached = {
        "version": 8,
        "start_month": "2024-01",
        "end_month": "2024-03",
        "reviewers": {
            "alice": {
                "avatar_url": "https://a.com/alice.png",
                "monthly": {"2024-01": 10},
                "comment_monthly": {"2024-01": 2},
                "merge_monthly": {},
            },
            "bob": {
                "avatar_url": "https://a.com/bob.png",
                "monthly": {"2024-02": 7},
                "comment_monthly": {},
                "merge_monthly": {"2024-02": 1},
            },
        },
    }

    # Only alice re-discovered; bob is frozen
    mock_disc.return_value = ["alice"]
    mock_rpc.return_value = {"alice": {"1": {"reviewed": 0, "commented": 0}}}
    mock_mc.return_value = ({"alice": {}}, {"alice": {}})
    mock_merge.return_value = {"alice": {}}

    result = reviewers.incremental_update(cached, "owner", "repo", 100)

    # Bob kept as-is
    assert result["reviewers"]["bob"] == cached["reviewers"]["bob"]
    # Alice still present
    assert "alice" in result["reviewers"]


@patch.object(reviewers, "get_rate_limit_info", return_value=(None, None))
@patch.object(reviewers, "datetime")
@patch.object(reviewers, "fetch_merge_counts")
@patch.object(reviewers, "fetch_monthly_counts")
@patch.object(reviewers, "fetch_reviewer_period_counts")
@patch.object(reviewers, "fetch_avatars")
@patch.object(reviewers, "discover_reviewers")
@patch.object(reviewers, "fetch_repo_activity")
def test_incremental_update_new_reviewer_no_historical(
    mock_activity, mock_disc, mock_av, mock_rpc, mock_mc, mock_merge, mock_dt, mock_rl
):
    """New reviewer when start_month == end_month skips historical fetch."""
    from datetime import datetime, timezone

    mock_dt.now.return_value = datetime(2024, 3, 15, tzinfo=timezone.utc)
    mock_activity.return_value = {
        "last_pr_updated_at": "2024-03-15T00:00:00Z",
        "total_pr_count": 200,
        "total_merged_prs": 100,
        "total_reviewed_prs": 150,
        "total_commented_prs": 80,
        "repo_totals": {
            "all": {"reviewed": 150, "commented": 80, "merged": 100},
            "1": {"reviewed": 150, "commented": 80, "merged": 100},
            "3": {"reviewed": 150, "commented": 80, "merged": 100},
            "6": {"reviewed": 150, "commented": 80, "merged": 100},
            "12": {"reviewed": 150, "commented": 80, "merged": 100},
            "24": {"reviewed": 150, "commented": 80, "merged": 100},
        },
    }

    # start_month equals end_month, so prev_month(end_month) < start_month
    cached = {
        "version": 8,
        "start_month": "2024-01",
        "end_month": "2024-01",
        "reviewers": {},
    }

    mock_disc.return_value = ["dave"]
    mock_av.return_value = {"dave": "https://a.com/dave.png"}
    mock_rpc.return_value = {"dave": {"1": {"reviewed": 3, "commented": 0}}}
    # Only stale fetch (2024-01 to 2024-03), no historical
    mock_mc.return_value = (
        {"dave": {"2024-02": 3}},
        {"dave": {}},
    )
    mock_merge.return_value = {"dave": {}}

    result = reviewers.incremental_update(cached, "owner", "repo", 100)

    dave = result["reviewers"]["dave"]
    assert dave["monthly"]["2024-02"] == 3
    assert dave["avatar_url"] == "https://a.com/dave.png"
    # fetch_monthly_counts called only once (stale), not twice
    assert mock_mc.call_count == 1
    assert mock_merge.call_count == 1


# --- activity-check skip-logic tests ---


@patch.object(reviewers, "datetime")
@patch.object(reviewers, "fetch_repo_activity")
def test_incremental_update_full_skip(mock_activity, mock_dt):
    """Tier 1: last_pr_updated_at unchanged returns cache as-is."""
    from datetime import datetime, timezone

    mock_dt.now.return_value = datetime(2024, 5, 15, tzinfo=timezone.utc)

    activity = {
        "last_pr_updated_at": "2024-03-01T12:00:00Z",
        "total_pr_count": 100,
        "total_merged_prs": 50,
        "total_reviewed_prs": 70,
        "total_commented_prs": 40,
        "repo_totals": {
            "all": {"reviewed": 70, "commented": 40, "merged": 50},
            "1": {"reviewed": 70, "commented": 40, "merged": 50},
            "3": {"reviewed": 70, "commented": 40, "merged": 50},
            "6": {"reviewed": 70, "commented": 40, "merged": 50},
            "12": {"reviewed": 70, "commented": 40, "merged": 50},
            "24": {"reviewed": 70, "commented": 40, "merged": 50},
        },
    }
    mock_activity.return_value = activity

    cached = {
        "version": 8,
        "start_month": "2024-01",
        "end_month": "2024-03",
        "activity": activity,
        "reviewers": {
            "alice": {
                "avatar_url": "https://a.com/alice.png",
                "monthly": {"2024-01": 10},
                "comment_monthly": {},
                "merge_monthly": {},
            },
        },
    }

    result = reviewers.incremental_update(cached, "owner", "repo", 100)

    assert result["reviewers"] == cached["reviewers"]
    assert result["end_month"] == "2024-05"
    assert result["activity"] == activity
    # Only 1 API call (fetch_repo_activity), no discover/fetch calls
    mock_activity.assert_called_once_with("owner", "repo")


@patch.object(reviewers, "datetime")
@patch.object(reviewers, "fetch_repo_activity")
def test_incremental_update_full_skip_fallback(mock_activity, mock_dt):
    """Tier 1 fallback: last_pr_updated_at changed but repo_totals identical."""
    from datetime import datetime, timezone

    mock_dt.now.return_value = datetime(2024, 5, 15, tzinfo=timezone.utc)

    totals = {
        "all": {"reviewed": 70, "commented": 40, "merged": 50},
        "1": {"reviewed": 10, "commented": 5, "merged": 3},
        "3": {"reviewed": 30, "commented": 15, "merged": 12},
        "6": {"reviewed": 50, "commented": 30, "merged": 25},
        "12": {"reviewed": 70, "commented": 40, "merged": 50},
        "24": {"reviewed": 70, "commented": 40, "merged": 50},
    }
    # Fresh activity has a DIFFERENT last_pr_updated_at
    fresh_activity = {
        "last_pr_updated_at": "2024-03-02T08:00:00Z",
        "total_pr_count": 100,
        "total_merged_prs": 50,
        "total_reviewed_prs": 70,
        "total_commented_prs": 40,
        "repo_totals": totals,
    }
    mock_activity.return_value = fresh_activity

    cached = {
        "version": 8,
        "start_month": "2024-01",
        "end_month": "2024-03",
        "activity": {
            "last_pr_updated_at": "2024-03-01T12:00:00Z",
            "total_pr_count": 100,
            "total_merged_prs": 50,
            "total_reviewed_prs": 70,
            "total_commented_prs": 40,
            "repo_totals": totals,
        },
        "reviewers": {
            "alice": {
                "avatar_url": "https://a.com/alice.png",
                "monthly": {"2024-01": 10},
                "comment_monthly": {},
                "merge_monthly": {},
            },
        },
    }

    result = reviewers.incremental_update(cached, "owner", "repo", 100)

    assert result["reviewers"] == cached["reviewers"]
    assert result["end_month"] == "2024-05"
    # Only 1 API call (fetch_repo_activity), no further fetching
    mock_activity.assert_called_once_with("owner", "repo")


@patch.object(reviewers, "get_rate_limit_info", return_value=(None, None))
@patch.object(reviewers, "datetime")
@patch.object(reviewers, "fetch_merge_counts")
@patch.object(reviewers, "fetch_monthly_counts")
@patch.object(reviewers, "fetch_reviewer_period_counts")
@patch.object(reviewers, "fetch_repo_activity")
def test_incremental_update_skip_discovery(
    mock_activity, mock_rpc, mock_mc, mock_merge, mock_dt, mock_rl
):
    """Tier 2: total_pr_count unchanged skips discover_reviewers."""
    from datetime import datetime, timezone

    mock_dt.now.return_value = datetime(2024, 5, 15, tzinfo=timezone.utc)

    cached_activity = {
        "last_pr_updated_at": "2024-03-01T12:00:00Z",
        "total_pr_count": 100,
        "total_merged_prs": 50,
        "total_reviewed_prs": 70,
        "total_commented_prs": 40,
        "repo_totals": {
            "all": {"reviewed": 70, "commented": 40, "merged": 50},
            "1": {"reviewed": 70, "commented": 40, "merged": 50},
            "3": {"reviewed": 70, "commented": 40, "merged": 50},
            "6": {"reviewed": 70, "commented": 40, "merged": 50},
            "12": {"reviewed": 70, "commented": 40, "merged": 50},
            "24": {"reviewed": 70, "commented": 40, "merged": 50},
        },
    }
    new_activity = {
        "last_pr_updated_at": "2024-05-10T09:00:00Z",  # changed
        "total_pr_count": 100,  # unchanged
        "total_merged_prs": 55,  # changed
        "total_reviewed_prs": 75,
        "total_commented_prs": 45,
        "repo_totals": {
            "all": {"reviewed": 75, "commented": 45, "merged": 55},
            "1": {"reviewed": 75, "commented": 45, "merged": 55},
            "3": {"reviewed": 75, "commented": 45, "merged": 55},
            "6": {"reviewed": 75, "commented": 45, "merged": 55},
            "12": {"reviewed": 75, "commented": 45, "merged": 55},
            "24": {"reviewed": 75, "commented": 45, "merged": 55},
        },
    }
    mock_activity.return_value = new_activity

    cached = {
        "version": 8,
        "start_month": "2024-01",
        "end_month": "2024-03",
        "activity": cached_activity,
        "reviewers": {
            "alice": {
                "avatar_url": "https://a.com/alice.png",
                "monthly": {"2024-01": 10},
                "comment_monthly": {},
                "merge_monthly": {"2024-02": 3},
            },
        },
    }

    mock_rpc.return_value = {"alice": {"1": {"reviewed": 2, "commented": 0}}}
    mock_mc.return_value = ({"alice": {"2024-04": 2}}, {"alice": {}})
    mock_merge.return_value = {"alice": {"2024-04": 1}}

    result = reviewers.incremental_update(cached, "owner", "repo", 100)

    # discover_reviewers should NOT have been called (it is not mocked, so
    # calling it would raise)
    assert "alice" in result["reviewers"]
    assert result["reviewers"]["alice"]["monthly"]["2024-04"] == 2
    assert result["activity"] == new_activity


@patch.object(reviewers, "get_rate_limit_info", return_value=(None, None))
@patch.object(reviewers, "datetime")
@patch.object(reviewers, "fetch_monthly_counts")
@patch.object(reviewers, "fetch_reviewer_period_counts")
@patch.object(reviewers, "discover_reviewers")
@patch.object(reviewers, "fetch_repo_activity")
def test_incremental_update_skip_merges(
    mock_activity, mock_disc, mock_rpc, mock_mc, mock_dt, mock_rl
):
    """Tier 3: total_merged_prs unchanged keeps cached merge data."""
    from datetime import datetime, timezone

    mock_dt.now.return_value = datetime(2024, 5, 15, tzinfo=timezone.utc)

    cached_activity = {
        "last_pr_updated_at": "2024-03-01T12:00:00Z",
        "total_pr_count": 100,
        "total_merged_prs": 50,
        "total_reviewed_prs": 70,
        "total_commented_prs": 40,
        "repo_totals": {
            "all": {"reviewed": 70, "commented": 40, "merged": 50},
            "1": {"reviewed": 70, "commented": 40, "merged": 50},
            "3": {"reviewed": 70, "commented": 40, "merged": 50},
            "6": {"reviewed": 70, "commented": 40, "merged": 50},
            "12": {"reviewed": 70, "commented": 40, "merged": 50},
            "24": {"reviewed": 70, "commented": 40, "merged": 50},
        },
    }
    new_activity = {
        "last_pr_updated_at": "2024-05-10T09:00:00Z",  # changed
        "total_pr_count": 105,  # changed
        "total_merged_prs": 50,  # unchanged
        "total_reviewed_prs": 75,
        "total_commented_prs": 45,
        "repo_totals": {
            "all": {"reviewed": 75, "commented": 45, "merged": 50},
            "1": {"reviewed": 75, "commented": 45, "merged": 50},
            "3": {"reviewed": 75, "commented": 45, "merged": 50},
            "6": {"reviewed": 75, "commented": 45, "merged": 50},
            "12": {"reviewed": 75, "commented": 45, "merged": 50},
            "24": {"reviewed": 75, "commented": 45, "merged": 50},
        },
    }
    mock_activity.return_value = new_activity

    cached = {
        "version": 8,
        "start_month": "2024-01",
        "end_month": "2024-03",
        "activity": cached_activity,
        "reviewers": {
            "alice": {
                "avatar_url": "https://a.com/alice.png",
                "monthly": {"2024-01": 10},
                "comment_monthly": {},
                "merge_monthly": {"2024-02": 3},
            },
        },
    }

    mock_disc.return_value = ["alice"]
    mock_rpc.return_value = {"alice": {"1": {"reviewed": 2, "commented": 0}}}
    mock_mc.return_value = ({"alice": {"2024-04": 2}}, {"alice": {}})
    # fetch_merge_counts is NOT mocked — calling it would raise

    result = reviewers.incremental_update(cached, "owner", "repo", 100)

    alice = result["reviewers"]["alice"]
    # Merge data preserved as-is from cache (not cleared for stale months)
    assert alice["merge_monthly"] == {"2024-02": 3}
    # But review counts were re-fetched
    assert alice["monthly"]["2024-04"] == 2


@patch.object(reviewers, "get_rate_limit_info", return_value=(None, None))
@patch.object(reviewers, "_scrape_fallback_period_counts")
@patch.object(reviewers, "datetime")
@patch.object(reviewers, "fetch_merge_counts")
@patch.object(reviewers, "fetch_monthly_counts")
@patch.object(reviewers, "fetch_reviewer_period_counts")
@patch.object(reviewers, "fetch_avatars")
@patch.object(reviewers, "discover_reviewers")
@patch.object(reviewers, "fetch_repo_activity")
def test_incremental_update_no_cached_activity(
    mock_activity,
    mock_disc,
    mock_av,
    mock_rpc,
    mock_mc,
    mock_merge,
    mock_dt,
    mock_scrape,
    mock_rl,
):
    """Backward compat: cache without activity key does full update."""
    from datetime import datetime, timezone

    mock_dt.now.return_value = datetime(2024, 5, 15, tzinfo=timezone.utc)
    mock_activity.return_value = {
        "last_pr_updated_at": "2024-05-15T00:00:00Z",
        "total_pr_count": 200,
        "total_merged_prs": 100,
        "total_reviewed_prs": 150,
        "total_commented_prs": 80,
        "repo_totals": {
            "all": {"reviewed": 150, "commented": 80, "merged": 100},
            "1": {"reviewed": 150, "commented": 80, "merged": 100},
            "3": {"reviewed": 150, "commented": 80, "merged": 100},
            "6": {"reviewed": 150, "commented": 80, "merged": 100},
            "12": {"reviewed": 150, "commented": 80, "merged": 100},
            "24": {"reviewed": 150, "commented": 80, "merged": 100},
        },
    }

    cached = {
        "version": 8,
        "start_month": "2024-01",
        "end_month": "2024-03",
        # No "activity" key — old cache format
        "reviewers": {
            "alice": {
                "avatar_url": "https://a.com/alice.png",
                "monthly": {"2024-01": 10},
                "comment_monthly": {},
                "merge_monthly": {},
            },
        },
    }

    mock_disc.return_value = ["alice"]
    mock_rpc.return_value = {"alice": {"1": {"reviewed": 0, "commented": 0}}}
    mock_mc.return_value = ({"alice": {}}, {"alice": {}})
    mock_merge.return_value = {"alice": {}}

    result = reviewers.incremental_update(cached, "owner", "repo", 100)

    # Full update path: discover was called
    mock_disc.assert_called_once()
    # Merge counts were fetched (no skip)
    mock_merge.assert_called_once()
    # Activity now stored
    assert result["activity"] == mock_activity.return_value
