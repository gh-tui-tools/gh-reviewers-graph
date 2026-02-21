# tests/test_aggregation.py
from conftest import reviewers


def test_build_output_data_basic():
    cached = {
        "alice": {
            "avatar_url": "https://a.com/alice.png",
            "monthly": {"2024-01": 15, "2024-02": 8},
            "comment_monthly": {"2024-01": 3, "2024-02": 1},
            "merge_monthly": {"2024-01": 2},
        },
        "bob": {
            "avatar_url": "https://a.com/bob.png",
            "monthly": {"2024-01": 5, "2024-03": 3},
            "comment_monthly": {"2024-01": 2},
            "merge_monthly": {"2024-02": 1, "2024-03": 1},
        },
    }
    result = reviewers.build_output_data("mdn/content", cached)

    assert result["repo"] == "mdn/content"
    assert len(result["reviewers"]) == 2

    alice = result["reviewers"][0]
    assert alice["login"] == "alice"
    assert alice["total"] == 23
    assert alice["total_comments"] == 4
    assert alice["total_merges"] == 2
    assert alice["monthly"]["2024-01"] == 15
    assert alice["monthly"]["2024-02"] == 8
    assert alice["comment_monthly"]["2024-01"] == 3
    assert alice["comment_monthly"]["2024-02"] == 1
    assert alice["merge_monthly"]["2024-01"] == 2
    assert alice["html_url"] == "https://github.com/alice"

    bob = result["reviewers"][1]
    assert bob["login"] == "bob"
    assert bob["total"] == 8
    assert bob["total_comments"] == 2
    assert bob["total_merges"] == 2


def test_build_output_data_empty():
    result = reviewers.build_output_data("test/repo", {})
    assert result["reviewers"] == []
    assert result["monthly_totals"] == {}
    assert result["comment_monthly_totals"] == {}
    assert result["merge_monthly_totals"] == {}


def test_build_output_data_monthly_totals():
    cached = {
        "alice": {
            "avatar_url": "https://a.com/a.png",
            "monthly": {"2024-01": 10, "2024-02": 5},
            "comment_monthly": {"2024-01": 2, "2024-03": 1},
            "merge_monthly": {"2024-01": 3, "2024-02": 1},
        },
        "bob": {
            "avatar_url": "https://a.com/b.png",
            "monthly": {"2024-01": 3, "2024-03": 7},
            "comment_monthly": {"2024-02": 4},
            "merge_monthly": {"2024-01": 1},
        },
    }
    result = reviewers.build_output_data("test/repo", cached)

    assert result["monthly_totals"]["2024-01"] == 13
    assert result["monthly_totals"]["2024-02"] == 5
    assert result["monthly_totals"]["2024-03"] == 7

    assert result["comment_monthly_totals"]["2024-01"] == 2
    assert result["comment_monthly_totals"]["2024-02"] == 4
    assert result["comment_monthly_totals"]["2024-03"] == 1

    assert result["merge_monthly_totals"]["2024-01"] == 4
    assert result["merge_monthly_totals"]["2024-02"] == 1


def test_build_output_data_skips_fully_inactive():
    cached = {
        "alice": {
            "avatar_url": "https://a.com/a.png",
            "monthly": {"2024-01": 10},
            "comment_monthly": {},
            "merge_monthly": {},
        },
        "inactive": {
            "avatar_url": "https://a.com/x.png",
            "monthly": {},
            "comment_monthly": {},
            "merge_monthly": {},
        },
    }
    result = reviewers.build_output_data("test/repo", cached)
    assert len(result["reviewers"]) == 1
    assert result["reviewers"][0]["login"] == "alice"


def test_build_output_data_keeps_comment_only_user():
    cached = {
        "reviewer": {
            "avatar_url": "https://a.com/r.png",
            "monthly": {"2024-01": 10},
            "comment_monthly": {},
            "merge_monthly": {},
        },
        "commenter": {
            "avatar_url": "https://a.com/c.png",
            "monthly": {},
            "comment_monthly": {"2024-01": 5, "2024-02": 3},
            "merge_monthly": {},
        },
    }
    result = reviewers.build_output_data("test/repo", cached)
    assert len(result["reviewers"]) == 2
    logins = [r["login"] for r in result["reviewers"]]
    assert "commenter" in logins
    commenter = next(r for r in result["reviewers"] if r["login"] == "commenter")
    assert commenter["total"] == 0
    assert commenter["total_comments"] == 8
    assert commenter["total_merges"] == 0


def test_build_output_data_keeps_merge_only_user():
    cached = {
        "reviewer": {
            "avatar_url": "https://a.com/r.png",
            "monthly": {"2024-01": 10},
            "comment_monthly": {},
            "merge_monthly": {},
        },
        "merger": {
            "avatar_url": "https://a.com/m.png",
            "monthly": {},
            "comment_monthly": {},
            "merge_monthly": {"2024-01": 7, "2024-02": 4},
        },
    }
    result = reviewers.build_output_data("test/repo", cached)
    assert len(result["reviewers"]) == 2
    logins = [r["login"] for r in result["reviewers"]]
    assert "merger" in logins
    merger = next(r for r in result["reviewers"] if r["login"] == "merger")
    assert merger["total"] == 0
    assert merger["total_comments"] == 0
    assert merger["total_merges"] == 11


def test_build_output_data_with_period_counts():
    cached = {
        "alice": {
            "avatar_url": "https://a.com/alice.png",
            "monthly": {"2024-01": 15},
            "comment_monthly": {"2024-01": 3},
            "merge_monthly": {},
        },
        "bob": {
            "avatar_url": "https://a.com/bob.png",
            "monthly": {"2024-01": 5},
            "comment_monthly": {},
            "merge_monthly": {},
        },
    }
    period_counts = {
        "alice": {
            "1": {"reviewed": 10, "commented": 2},
            "3": {"reviewed": 15, "commented": 3},
        },
    }
    result = reviewers.build_output_data("test/repo", cached, period_counts)
    alice = next(r for r in result["reviewers"] if r["login"] == "alice")
    assert alice["period_counts"] == period_counts["alice"]
    bob = next(r for r in result["reviewers"] if r["login"] == "bob")
    assert "period_counts" not in bob


def test_build_output_data_unsearchable_uses_period24_for_totals():
    """Unsearchable users get total/total_comments from period_counts '24'."""
    cached = {
        "trflynn": {
            "avatar_url": "https://a.com/trflynn.png",
            "monthly": {},
            "comment_monthly": {},
            "merge_monthly": {"2024-01": 50},
        },
    }
    period_counts = {
        "trflynn": {
            "1": {"reviewed": 22, "commented": 26},
            "24": {"reviewed": 394, "commented": 472},
        },
    }
    result = reviewers.build_output_data("test/repo", cached, period_counts)
    trflynn = result["reviewers"][0]
    assert trflynn["total"] == 394  # from period_counts["24"], not sum(monthly)
    assert trflynn["total_comments"] == 472
    assert trflynn["total_merges"] == 50
