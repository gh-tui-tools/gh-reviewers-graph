# tests/test_cache.py
import os

from conftest import reviewers


def test_cache_round_trip(tmp_path):
    cache_path = tmp_path / "test_cache.json"
    data = {
        "version": 8,
        "start_month": "2024-01",
        "end_month": "2024-02",
        "reviewers": {
            "alice": {
                "avatar_url": "https://a.com/alice.png",
                "monthly": {"2024-01": 15, "2024-02": 8},
                "comment_monthly": {"2024-01": 3},
                "merge_monthly": {"2024-01": 2},
            },
        },
    }
    reviewers.save_cache(str(cache_path), data)
    loaded = reviewers.load_cache(str(cache_path))
    assert loaded == data


def test_load_cache_missing_file():
    result = reviewers.load_cache("/nonexistent/path/cache.json")
    assert result is None


def test_cache_creates_parent_dirs(tmp_path):
    cache_path = tmp_path / "subdir" / "deep" / "cache.json"
    data = {
        "version": 8,
        "start_month": "2024-01",
        "end_month": "2024-01",
        "reviewers": {},
    }
    reviewers.save_cache(str(cache_path), data)
    assert os.path.exists(cache_path)
    loaded = reviewers.load_cache(str(cache_path))
    assert loaded == data


def test_cache_v1_treated_as_stale(tmp_path):
    """Old v1 cache (no version key) should be treated as None by main()."""
    cache_path = tmp_path / "old_cache.json"
    v1_data = {
        "raw_reviews": [{"login": "alice", "created_at": "2025-01-07T10:00:00Z"}],
        "raw_comments": [],
    }
    reviewers.save_cache(str(cache_path), v1_data)
    loaded = reviewers.load_cache(str(cache_path))
    assert loaded is not None
    assert loaded.get("version") != 8


def test_cache_v2_treated_as_stale(tmp_path):
    """Old v2 cache (version 2, no comment_monthly) should be treated as stale."""
    cache_path = tmp_path / "v2_cache.json"
    v2_data = {
        "version": 2,
        "reviewers": {
            "alice": {
                "avatar_url": "https://a.com/alice.png",
                "monthly": {"2024-01": 15},
            },
        },
    }
    reviewers.save_cache(str(cache_path), v2_data)
    loaded = reviewers.load_cache(str(cache_path))
    assert loaded is not None
    assert loaded.get("version") != 8


def test_cache_v3_treated_as_stale(tmp_path):
    """Old v3 cache (version 3, no merge_monthly) should be treated as stale."""
    cache_path = tmp_path / "v3_cache.json"
    v3_data = {
        "version": 3,
        "reviewers": {
            "alice": {
                "avatar_url": "https://a.com/alice.png",
                "monthly": {"2024-01": 15},
                "comment_monthly": {"2024-01": 3},
            },
        },
    }
    reviewers.save_cache(str(cache_path), v3_data)
    loaded = reviewers.load_cache(str(cache_path))
    assert loaded is not None
    assert loaded.get("version") != 8


def test_cache_v4_treated_as_stale(tmp_path):
    """Old v4 cache (version 4, counts include self-authored PRs) should be treated as stale."""
    cache_path = tmp_path / "v4_cache.json"
    v4_data = {
        "version": 4,
        "reviewers": {
            "alice": {
                "avatar_url": "https://a.com/alice.png",
                "monthly": {"2024-01": 15},
                "comment_monthly": {"2024-01": 3},
                "merge_monthly": {"2024-01": 2},
            },
        },
    }
    reviewers.save_cache(str(cache_path), v4_data)
    loaded = reviewers.load_cache(str(cache_path))
    assert loaded is not None
    assert loaded.get("version") != 8


def test_cache_v5_treated_as_stale(tmp_path):
    """Old v5 cache (version 5, includes bot logins) should be treated as stale."""
    cache_path = tmp_path / "v5_cache.json"
    v5_data = {
        "version": 5,
        "reviewers": {
            "alice": {
                "avatar_url": "https://a.com/alice.png",
                "monthly": {"2024-01": 15},
                "comment_monthly": {"2024-01": 3},
                "merge_monthly": {"2024-01": 2},
            },
        },
    }
    reviewers.save_cache(str(cache_path), v5_data)
    loaded = reviewers.load_cache(str(cache_path))
    assert loaded is not None
    assert loaded.get("version") != 8


def test_cache_v6_treated_as_stale(tmp_path):
    """Old v6 cache (version 6, sequential discovery/merge) should be treated as stale."""
    cache_path = tmp_path / "v6_cache.json"
    v6_data = {
        "version": 6,
        "reviewers": {
            "alice": {
                "avatar_url": "https://a.com/alice.png",
                "monthly": {"2024-01": 15},
                "comment_monthly": {"2024-01": 3},
                "merge_monthly": {"2024-01": 2},
            },
        },
    }
    reviewers.save_cache(str(cache_path), v6_data)
    loaded = reviewers.load_cache(str(cache_path))
    assert loaded is not None
    assert loaded.get("version") != 8


def test_cache_v7_treated_as_stale(tmp_path):
    """Old v7 cache (no start_month/end_month) should be treated as stale."""
    cache_path = tmp_path / "v7_cache.json"
    v7_data = {
        "version": 7,
        "reviewers": {
            "alice": {
                "avatar_url": "https://a.com/alice.png",
                "monthly": {"2024-01": 15},
                "comment_monthly": {"2024-01": 3},
                "merge_monthly": {"2024-01": 2},
            },
        },
    }
    reviewers.save_cache(str(cache_path), v7_data)
    loaded = reviewers.load_cache(str(cache_path))
    assert loaded is not None
    assert loaded.get("version") != 8


def test_cache_v8_without_activity_loads_normally(tmp_path):
    """v8 cache without activity key loads fine (backward compatible)."""
    cache_path = tmp_path / "v8_no_activity.json"
    v8_data = {
        "version": 8,
        "start_month": "2024-01",
        "end_month": "2024-03",
        "reviewers": {
            "alice": {
                "avatar_url": "https://a.com/alice.png",
                "monthly": {"2024-01": 15},
                "comment_monthly": {"2024-01": 3},
                "merge_monthly": {"2024-01": 2},
            },
        },
    }
    reviewers.save_cache(str(cache_path), v8_data)
    loaded = reviewers.load_cache(str(cache_path))
    assert loaded is not None
    assert loaded.get("version") == 8
    assert loaded.get("activity") is None
    assert "alice" in loaded["reviewers"]
