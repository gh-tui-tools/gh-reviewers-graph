"""End-to-end tests for the generated reviewer page."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_page_title(page, live_server):
    page.goto(live_server)
    assert "test-org/test-repo" in page.title()


def test_repo_name_displayed(page, live_server):
    page.goto(live_server)
    expect(page.locator("#repo-name")).to_have_text("test-org/test-repo")


def test_summary_counts(page, live_server):
    page.goto(live_server)
    summary = page.locator("#summary")
    expect(summary).to_contain_text("3 reviewers")
    expect(summary).to_contain_text("57 PRs reviewed")
    expect(summary).to_contain_text("commented on")
    expect(summary).to_contain_text("merged")


def test_reviewer_cards_rendered(page, live_server):
    page.goto(live_server)
    expect(page.locator(".reviewer-card")).to_have_count(3)

    logins = page.locator(".reviewer-login")
    for i in range(logins.count()):
        href = logins.nth(i).get_attribute("href")
        assert href.startswith("https://github.com/")


def test_reviewer_stats_text(page, live_server):
    page.goto(live_server)
    stats = page.locator(".reviewer-stats").first
    expect(stats).to_contain_text("PRs reviewed")
    expect(stats).to_contain_text("commented on")
    expect(stats).to_contain_text("merged")


def test_overview_chart_exists(page, live_server):
    page.goto(live_server)
    expect(page.locator("#overview-chart")).to_be_visible()


def test_sparkline_charts_exist(page, live_server):
    page.goto(live_server)
    cards = page.locator(".reviewer-card")
    count = cards.count()
    assert count > 0
    for i in range(count):
        expect(cards.nth(i).locator("canvas")).to_have_count(1)


def test_period_filter_updates_summary(page, live_server):
    page.goto(live_server)
    summary_all = page.locator("#summary").text_content()

    page.select_option("#period-select", "3")

    expect(page.locator("#summary")).not_to_have_text(summary_all)


def test_period_filter_hides_inactive_reviewers(page, live_server):
    page.goto(live_server)
    expect(page.locator(".reviewer-card")).to_have_count(3)

    page.select_option("#period-select", "3")

    # bob has no activity in last 3 months — card count drops to 2
    expect(page.locator(".reviewer-card")).to_have_count(2)

    logins = page.locator(".reviewer-login")
    texts = [logins.nth(i).text_content() for i in range(logins.count())]
    assert "bob" not in texts


def test_generated_at_footer(page, live_server):
    page.goto(live_server)
    text = page.locator("#generated-at").text_content()
    assert text


def test_default_period_is_12_months(page, live_server):
    page.goto(live_server)
    select = page.locator("#period-select")
    # The <select> should default to "12" (Last 12 months), not "all"
    assert select.input_value() == "12"


def test_reviewer_card_sort_order(page, live_server):
    """Cards are sorted by combined activity (reviews + comments + merges) descending."""
    page.goto(live_server)
    logins = page.locator(".reviewer-login")
    texts = [logins.nth(i).text_content() for i in range(logins.count())]
    # Default period "12": alice (42) > carol (23) > bob (16)
    assert texts == ["alice", "carol", "bob"]


def test_reviewer_stats_contain_search_links(page, live_server):
    """Each reviewer card has hyperlinks in stats pointing to GitHub search."""
    page.goto(live_server)
    first_card = page.locator(".reviewer-card").first
    links = first_card.locator(".reviewer-stats a")
    assert links.count() == 2  # "reviewed" and "commented on" are links
    for i in range(links.count()):
        href = links.nth(i).get_attribute("href")
        assert "github.com/test-org/test-repo/pulls" in href


def test_period_filter_shows_correct_values(page, live_server):
    """Switching period updates summary to the correct repo_totals values."""
    page.goto(live_server)
    page.select_option("#period-select", "3")
    summary = page.locator("#summary")
    expect(summary).to_contain_text("30 PRs reviewed")
    expect(summary).to_contain_text("10 PRs commented on")
    expect(summary).to_contain_text("5 PRs merged")


def test_period_dropdown_options(page, live_server):
    page.goto(live_server)
    options = page.locator("#period-select option")
    values = [options.nth(i).get_attribute("value") for i in range(options.count())]
    assert values == ["all", "1", "3", "6", "12", "24"]


def test_reviewer_avatars_rendered(page, live_server):
    page.goto(live_server)
    avatars = page.locator(".reviewer-avatar")
    count = avatars.count()
    assert count > 0
    for i in range(count):
        src = avatars.nth(i).get_attribute("src")
        assert src.startswith("https://avatars.githubusercontent.com/")


def test_reviewer_rank_numbers(page, live_server):
    """Each card shows a rank number matching its sorted position."""
    page.goto(live_server)
    ranks = page.locator(".reviewer-rank")
    texts = [ranks.nth(i).text_content() for i in range(ranks.count())]
    assert texts == ["#1", "#2", "#3"]


def test_rank_numbers_update_on_period_change(page, live_server):
    """Rank numbers reflect the new sort order after period change."""
    page.goto(live_server)
    # Default "12": alice #1, carol #2, bob #3
    ranks = page.locator(".reviewer-rank")
    assert [ranks.nth(i).text_content() for i in range(ranks.count())] == [
        "#1",
        "#2",
        "#3",
    ]

    page.select_option("#period-select", "3")
    # "3": carol (23) > alice (22), bob hidden — ranks renumber from #1
    logins = page.locator(".reviewer-login")
    texts = [logins.nth(i).text_content() for i in range(logins.count())]
    assert texts[0] == "carol"
    ranks = page.locator(".reviewer-rank")
    assert [ranks.nth(i).text_content() for i in range(ranks.count())] == ["#1", "#2"]
