# tests/test_schema.py
"""Validate data.json cache format against schema.json."""

import json
from pathlib import Path

import jsonschema
import pytest


SCHEMA_PATH = Path(__file__).parent.parent / "schema.json"


@pytest.fixture
def schema():
    with open(SCHEMA_PATH) as f:
        return json.load(f)


def test_sample_cached_data_validates(schema, sample_cached_data):
    """The shared sample_cached_data fixture conforms to the schema."""
    jsonschema.validate(sample_cached_data, schema)


def test_minimal_valid_data(schema):
    """Smallest possible valid cache: one reviewer, one month, one period."""
    data = {
        "version": 8,
        "start_month": "2024-01",
        "end_month": "2024-01",
        "reviewers": {
            "alice": {
                "avatar_url": "https://avatars.githubusercontent.com/alice",
                "monthly": {"2024-01": 1},
                "comment_monthly": {},
                "merge_monthly": {},
            },
        },
        "activity": {
            "last_pr_updated_at": "2024-01-15T00:00:00Z",
            "total_pr_count": 1,
            "total_merged_prs": 0,
            "total_reviewed_prs": 1,
            "total_commented_prs": 0,
            "repo_totals": {
                "all": {"reviewed": 1, "commented": 0, "merged": 0},
            },
        },
        "reviewer_period_counts": {
            "alice": {
                "1": {"reviewed": 1, "commented": 0},
            },
        },
    }
    jsonschema.validate(data, schema)


def test_empty_reviewers_valid(schema):
    """A cache with zero reviewers is valid."""
    data = {
        "version": 8,
        "start_month": "2024-01",
        "end_month": "2024-01",
        "reviewers": {},
        "activity": {
            "last_pr_updated_at": "2024-01-15T00:00:00Z",
            "total_pr_count": 0,
            "total_merged_prs": 0,
            "total_reviewed_prs": 0,
            "total_commented_prs": 0,
            "repo_totals": {
                "all": {"reviewed": 0, "commented": 0, "merged": 0},
            },
        },
        "reviewer_period_counts": {},
    }
    jsonschema.validate(data, schema)


def test_wrong_version_rejected(schema):
    """Version must be exactly 8."""
    data = {
        "version": 7,
        "start_month": "2024-01",
        "end_month": "2024-01",
        "reviewers": {},
        "activity": {
            "last_pr_updated_at": "2024-01-15T00:00:00Z",
            "total_pr_count": 0,
            "total_merged_prs": 0,
            "total_reviewed_prs": 0,
            "total_commented_prs": 0,
            "repo_totals": {
                "all": {"reviewed": 0, "commented": 0, "merged": 0},
            },
        },
        "reviewer_period_counts": {},
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_missing_required_field_rejected(schema):
    """Omitting a required top-level field is rejected."""
    data = {
        "version": 8,
        "start_month": "2024-01",
        "end_month": "2024-01",
        "reviewers": {},
        # "activity" missing
        "reviewer_period_counts": {},
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_extra_top_level_field_rejected(schema):
    """additionalProperties: false rejects unknown top-level keys."""
    data = {
        "version": 8,
        "start_month": "2024-01",
        "end_month": "2024-01",
        "reviewers": {},
        "activity": {
            "last_pr_updated_at": "2024-01-15T00:00:00Z",
            "total_pr_count": 0,
            "total_merged_prs": 0,
            "total_reviewed_prs": 0,
            "total_commented_prs": 0,
            "repo_totals": {
                "all": {"reviewed": 0, "commented": 0, "merged": 0},
            },
        },
        "reviewer_period_counts": {},
        "surprise": True,
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_bad_month_format_rejected(schema):
    """Month strings must match YYYY-MM pattern."""
    data = {
        "version": 8,
        "start_month": "2024-1",  # missing leading zero
        "end_month": "2024-01",
        "reviewers": {},
        "activity": {
            "last_pr_updated_at": "2024-01-15T00:00:00Z",
            "total_pr_count": 0,
            "total_merged_prs": 0,
            "total_reviewed_prs": 0,
            "total_commented_prs": 0,
            "repo_totals": {
                "all": {"reviewed": 0, "commented": 0, "merged": 0},
            },
        },
        "reviewer_period_counts": {},
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_invalid_period_key_rejected(schema):
    """Period keys in reviewer_period_counts must be 1/3/6/12/24."""
    data = {
        "version": 8,
        "start_month": "2024-01",
        "end_month": "2024-01",
        "reviewers": {},
        "activity": {
            "last_pr_updated_at": "2024-01-15T00:00:00Z",
            "total_pr_count": 0,
            "total_merged_prs": 0,
            "total_reviewed_prs": 0,
            "total_commented_prs": 0,
            "repo_totals": {
                "all": {"reviewed": 0, "commented": 0, "merged": 0},
            },
        },
        "reviewer_period_counts": {
            "alice": {
                "7": {"reviewed": 1, "commented": 0},
            },
        },
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_invalid_repo_totals_period_rejected(schema):
    """repo_totals period keys must be all/1/3/6/12/24."""
    data = {
        "version": 8,
        "start_month": "2024-01",
        "end_month": "2024-01",
        "reviewers": {},
        "activity": {
            "last_pr_updated_at": "2024-01-15T00:00:00Z",
            "total_pr_count": 0,
            "total_merged_prs": 0,
            "total_reviewed_prs": 0,
            "total_commented_prs": 0,
            "repo_totals": {
                "all": {"reviewed": 0, "commented": 0, "merged": 0},
                "99": {"reviewed": 0, "commented": 0, "merged": 0},
            },
        },
        "reviewer_period_counts": {},
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)
