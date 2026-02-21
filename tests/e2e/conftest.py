"""Fixtures for Playwright end-to-end tests."""

import sys
import threading
from datetime import datetime
from functools import partial
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from conftest import reviewers


def _month_offset(months_ago):
    """Return 'YYYY-MM' for N months before today."""
    now = datetime.now()
    month = now.month - months_ago
    year = now.year
    while month < 1:
        month += 12
        year -= 1
    return f"{year}-{month:02d}"


@pytest.fixture(scope="session")
def e2e_data():
    """Sample DATA dict with 3 reviewers spanning multiple months.

    - alice: activity in both old and recent months (always visible)
    - bob: activity only >3 months ago (disappears with "Last 3 months")
    - carol: activity only in recent months (always visible)
    """
    recent_0 = _month_offset(0)
    recent_1 = _month_offset(1)
    recent_2 = _month_offset(2)
    old_1 = _month_offset(5)
    old_2 = _month_offset(6)

    return {
        "repo": "test-org/test-repo",
        "generated_at": datetime.now().isoformat(),
        "reviewers": [
            {
                "login": "alice",
                "avatar_url": "https://avatars.githubusercontent.com/alice",
                "html_url": "https://github.com/alice",
                "total": 30,
                "total_comments": 8,
                "total_merges": 4,
                "monthly": {old_1: 10, old_2: 5, recent_1: 10, recent_2: 5},
                "comment_monthly": {old_1: 3, recent_1: 3, recent_2: 2},
                "merge_monthly": {old_2: 2, recent_0: 2},
            },
            {
                "login": "bob",
                "avatar_url": "https://avatars.githubusercontent.com/bob",
                "html_url": "https://github.com/bob",
                "total": 12,
                "total_comments": 3,
                "total_merges": 1,
                "monthly": {old_1: 7, old_2: 5},
                "comment_monthly": {old_1: 2, old_2: 1},
                "merge_monthly": {old_1: 1},
            },
            {
                "login": "carol",
                "avatar_url": "https://avatars.githubusercontent.com/carol",
                "html_url": "https://github.com/carol",
                "total": 15,
                "total_comments": 5,
                "total_merges": 3,
                "monthly": {recent_0: 8, recent_1: 7},
                "comment_monthly": {recent_0: 3, recent_1: 2},
                "merge_monthly": {recent_0: 2, recent_1: 1},
            },
        ],
        "monthly_totals": {
            old_1: 17,
            old_2: 10,
            recent_0: 8,
            recent_1: 17,
            recent_2: 5,
        },
        "comment_monthly_totals": {
            old_1: 5,
            old_2: 1,
            recent_0: 3,
            recent_1: 5,
            recent_2: 2,
        },
        "merge_monthly_totals": {
            old_1: 1,
            old_2: 2,
            recent_0: 4,
            recent_1: 1,
        },
        "repo_totals": {
            "all": {"reviewed": 57, "commented": 16, "merged": 8},
            "1": {"reviewed": 15, "commented": 5, "merged": 4},
            "3": {"reviewed": 30, "commented": 10, "merged": 5},
            "6": {"reviewed": 45, "commented": 14, "merged": 7},
            "12": {"reviewed": 57, "commented": 16, "merged": 8},
            "24": {"reviewed": 57, "commented": 16, "merged": 8},
        },
    }


@pytest.fixture(scope="session")
def live_server(e2e_data, tmp_path_factory):
    """Start a local HTTP server serving the generated page."""
    out_dir = tmp_path_factory.mktemp("e2e_output")
    reviewers.generate_output(e2e_data, str(out_dir))

    handler = partial(SimpleHTTPRequestHandler, directory=str(out_dir))
    server = HTTPServer(("localhost", 0), handler)
    port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    yield f"http://localhost:{port}"

    server.shutdown()
