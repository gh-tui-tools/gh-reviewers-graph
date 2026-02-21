# tests/conftest.py
import importlib.machinery
import importlib.util
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


def load_reviewers_module():
    """Load gh-reviewers-graph as a module despite lacking .py extension."""
    script_path = Path(__file__).parent.parent / "gh-reviewers-graph"
    loader = importlib.machinery.SourceFileLoader("reviewers", str(script_path))
    spec = importlib.util.spec_from_loader("reviewers", loader)
    module = importlib.util.module_from_spec(spec)
    sys.modules["reviewers"] = module
    with patch.object(sys, "exit"):
        spec.loader.exec_module(module)
    return module


reviewers = load_reviewers_module()


@pytest.fixture
def mod():
    """Provide access to the reviewers module."""
    return reviewers


@pytest.fixture
def mock_graphql():
    """Patch reviewers._graphql_request and yield the mock."""
    with patch.object(reviewers, "_graphql_request") as mock:
        yield mock


@pytest.fixture
def sample_cached_data():
    """A complete v8 cache dict suitable for main() tests."""
    return {
        "version": 8,
        "start_month": "2024-01",
        "end_month": "2024-03",
        "reviewers": {
            "alice": {
                "avatar_url": "https://avatars.githubusercontent.com/alice",
                "monthly": {"2024-01": 15, "2024-02": 8},
                "comment_monthly": {"2024-01": 3, "2024-02": 1},
                "merge_monthly": {"2024-01": 2},
            },
            "bob": {
                "avatar_url": "https://avatars.githubusercontent.com/bob",
                "monthly": {"2024-01": 5, "2024-03": 3},
                "comment_monthly": {"2024-01": 2},
                "merge_monthly": {"2024-02": 1, "2024-03": 1},
            },
        },
        "activity": {
            "last_pr_updated_at": "2024-03-15T00:00:00Z",
            "total_pr_count": 50,
            "total_merged_prs": 20,
            "total_reviewed_prs": 30,
            "total_commented_prs": 15,
            "repo_totals": {
                "all": {"reviewed": 30, "commented": 15, "merged": 20},
                "1": {"reviewed": 5, "commented": 2, "merged": 3},
                "3": {"reviewed": 10, "commented": 5, "merged": 8},
                "6": {"reviewed": 20, "commented": 10, "merged": 15},
                "12": {"reviewed": 28, "commented": 14, "merged": 19},
                "24": {"reviewed": 30, "commented": 15, "merged": 20},
            },
        },
        "reviewer_period_counts": {
            "alice": {
                "1": {"reviewed": 3, "commented": 1},
                "3": {"reviewed": 8, "commented": 2},
                "6": {"reviewed": 15, "commented": 3},
                "12": {"reviewed": 20, "commented": 4},
                "24": {"reviewed": 23, "commented": 4},
            },
            "bob": {
                "1": {"reviewed": 2, "commented": 1},
                "3": {"reviewed": 5, "commented": 2},
                "6": {"reviewed": 5, "commented": 2},
                "12": {"reviewed": 8, "commented": 3},
                "24": {"reviewed": 8, "commented": 3},
            },
        },
    }
