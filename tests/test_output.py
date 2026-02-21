# tests/test_output.py
import json
import os

from conftest import reviewers


def _sample_data():
    return {
        "repo": "test/repo",
        "generated_at": "2024-01-15T00:00:00+00:00",
        "reviewers": [
            {
                "login": "alice",
                "avatar_url": "https://a.com/alice.png",
                "html_url": "https://github.com/alice",
                "total": 10,
                "total_comments": 3,
                "total_merges": 2,
                "monthly": {"2024-01": 10},
                "comment_monthly": {"2024-01": 3},
                "merge_monthly": {"2024-01": 2},
            },
        ],
        "monthly_totals": {"2024-01": 10},
        "comment_monthly_totals": {"2024-01": 3},
        "merge_monthly_totals": {"2024-01": 2},
    }


def test_generate_output_creates_files(tmp_path):
    out_dir = tmp_path / "output"
    reviewers.generate_output(_sample_data(), str(out_dir))

    assert (out_dir / "index.html").exists(), "index.html not created"
    for filename in ("style.css", "app.js", "data.js"):
        assert not (out_dir / filename).exists(), f"{filename} should not exist"


def test_generate_output_data_js_content(tmp_path):
    out_dir = tmp_path / "output"
    data = _sample_data()
    reviewers.generate_output(data, str(out_dir))

    html = (out_dir / "index.html").read_text()

    # Data is inlined
    assert "const DATA = " in html
    json_start = html.index("const DATA = ") + len("const DATA = ")
    json_end = html.index(";</script>", json_start)
    parsed = json.loads(html[json_start:json_end])
    assert parsed["repo"] == "test/repo"
    assert parsed["reviewers"][0]["login"] == "alice"

    # CSS and JS are inlined
    assert "box-sizing:" in html  # from style.css
    assert "use strict" in html  # from app.js


def test_generate_output_overwrites_existing(tmp_path):
    out_dir = tmp_path / "output"
    os.makedirs(str(out_dir))
    stale = out_dir / "index.html"
    stale.write_text("<html>old</html>")

    reviewers.generate_output(_sample_data(), str(out_dir))

    content = stale.read_text()
    assert "<html>old</html>" not in content
    assert '"alice"' in content
