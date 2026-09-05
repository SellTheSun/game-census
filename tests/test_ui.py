"""HTML data semantics and chart geometry; browser journey is a separate live check."""

from datetime import datetime, timedelta, timezone

from game_census.web import _chart
from test_api import fixture_app


def test_chart_splits_large_gaps_without_inventing_points():
    at = datetime(2026, 9, 4, tzinfo=timezone.utc)
    chart = _chart({"from": at, "to": at + timedelta(hours=24), "points": [
        {"observed_at": at + timedelta(hours=1), "player_count": 10},
        {"observed_at": at + timedelta(hours=1, minutes=5), "player_count": 20},
        {"observed_at": at + timedelta(hours=4), "player_count": 0},
    ]}, 300, 2)
    assert len(chart["paths"]) == 2
    assert len(chart["points"]) == 3
    assert chart["points"][-1]["count"] == 0


def test_one_sample_is_one_dot(fixture_app):
    client, db, _ = fixture_app
    db.history_value["points"] = db.history_value["points"][:1]
    db.history_value["coverage"]["sample_count"] = 1
    response = client.get("/apps/570")
    assert response.status_code == 200
    assert response.text.count('class="chart-point"') == 1
    assert "One recorded observation" in response.text
    assert "View observation data" in response.text


def test_no_observations_have_explicit_empty_state(fixture_app):
    client, db, _ = fixture_app
    db.apps[0].update(player_count=None, observed_at=None, availability="no_observations", sample_count=0,
                      highest_recorded=None, observed_24h_peak=None, last_attempt=None)
    db.history_value["points"] = []
    db.history_value["coverage"].update(sample_count=0, coverage_ratio=0, covered_seconds=0)
    db.history_value["metrics"].update(observed_peak=None, average_observed_ccu=None)
    response = client.get("/apps/570")
    assert response.status_code == 200
    assert "No observations in this window" in response.text
    assert "Awaiting observation" in response.text
    assert "Not yet observed" in response.text
    assert 'class="big-count">—' in response.text


def test_chart_and_navigation_have_keyboard_and_table_alternatives(fixture_app):
    client, _, _ = fixture_app
    html = client.get("/apps/570").text
    assert 'class="skip-link"' in html
    assert 'aria-label="Main navigation"' in html
    assert 'aria-labelledby="chart-title chart-description" tabindex="0"' in html
    assert '<details class="data-table">' in html
    assert 'aria-live="polite"' in html
    assert 'scope="col"' in html


def test_chart_uses_recorded_gap_when_cadence_changed():
    at = datetime(2026, 9, 4, tzinfo=timezone.utc)
    chart = _chart({"from": at, "to": at + timedelta(hours=24), "points": [
        {"observed_at": at + timedelta(hours=1), "player_count": 10},
        {"observed_at": at + timedelta(hours=1, minutes=15), "player_count": 20},
    ], "gaps": [{"from": at + timedelta(hours=1, minutes=10), "to": at + timedelta(hours=1, minutes=15), "seconds": 300}]}, 3600, 2)
    assert len(chart["paths"]) == 2


def test_fresh_snapshot_labels_do_not_claim_continuing_freshness(fixture_app):
    client, _, _ = fixture_app
    home = client.get("/").text
    detail = client.get("/apps/570").text
    status = client.get("/status").text
    assert "Fresh at page read" in home
    assert "1 fresh at page read" in home
    assert "Fresh at page read" in detail
    assert "Fresh at page read" in status
    assert "Fresh observation" not in home + detail + status
