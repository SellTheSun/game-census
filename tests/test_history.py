"""Independent metric fixtures exercise gaps, boundaries, cadence changes and zero."""
from datetime import datetime, timedelta, timezone
import pytest
from game_census.metrics import calculate

START = datetime(2026,1,1,tzinfo=timezone.utc)


def sample(seconds,count):
    return {"observed_at":START+timedelta(seconds=seconds),"player_count":count}


def policy(seconds=0,interval=300):
    return {"started_at":START+timedelta(seconds=seconds),"interval_seconds":interval}


def test_weighted_average_clips_outage_and_never_counts_unknown_time_as_zero():
    result = calculate([sample(0,10),sample(300,20),sample(1500,100)],START,START+timedelta(seconds=1800),[policy()])
    # 10*300 + 20*600 + 100*300 = 45000 across 1200 seconds.
    assert result["metrics"]["average_observed_ccu"] == 37.5
    assert result["coverage"]["covered_seconds"] == 1200
    assert result["coverage"]["coverage_ratio"] == pytest.approx(2/3)
    assert result["coverage"]["maximum_gap_seconds"] == 600
    assert result["metrics"]["observed_peak"] == 100
    assert result["gaps"][0]["seconds"] == 600


def test_window_includes_preceding_sample_only_for_overlapping_duration():
    result = calculate([sample(-120,40),sample(300,100)],START,START+timedelta(seconds=600),[policy(-1000)])
    assert result["metrics"]["average_observed_ccu"] == 70
    assert result["coverage"]["sample_count"] == 1
    assert result["coverage"]["covered_seconds"] == 600
    assert result["metrics"]["observed_peak"] == 100


def test_empty_history_exposes_unknown_window_and_null_metrics():
    result = calculate([],START,START+timedelta(seconds=3600),[policy(1800)])
    assert result["metrics"]["average_observed_ccu"] is None
    assert result["metrics"]["observed_peak"] is None
    assert result["coverage"]["expected_samples"] == 6
    assert result["coverage"]["tracked_seconds"] == 1800
    assert result["coverage"]["maximum_gap_seconds"] == 3600
    assert result["coverage"]["coverage_ratio"] == 0


def test_successful_zero_contributes_duration_and_zero_average():
    result = calculate([sample(0,0)],START,START+timedelta(seconds=600),[policy()])
    assert result["metrics"]["average_observed_ccu"] == 0
    assert result["metrics"]["observed_peak"] == 0
    assert result["coverage"]["covered_seconds"] == 600


def test_pre_enrollment_time_never_becomes_covered():
    result = calculate([sample(1800,50)],START,START+timedelta(seconds=3600),[policy(1800)])
    assert result["coverage"]["covered_seconds"] == 600
    assert result["coverage"]["coverage_ratio"] == pytest.approx(1/6)
    assert result["coverage"]["tracked_seconds"] == 1800
    assert result["gaps"][0]["seconds"] == 1800


def test_cadence_change_uses_cadence_at_each_observation():
    result = calculate([sample(0,10),sample(600,20)],START,START+timedelta(seconds=1800),[policy(),policy(600,600)])
    assert result["coverage"]["expected_samples"] == 4
    assert result["coverage"]["covered_seconds"] == 1800
    assert result["metrics"]["average_observed_ccu"] == pytest.approx(50/3)


def test_single_sample_at_window_end_has_no_invented_duration():
    result = calculate([sample(600,10)],START,START+timedelta(seconds=600),[policy()])
    assert result["metrics"]["average_observed_ccu"] is None
    assert result["coverage"]["covered_seconds"] == 0
    assert result["coverage"]["sample_count"] == 0
    assert result["metrics"]["observed_peak"] is None


def test_boundary_sample_belongs_only_to_the_next_window():
    boundary = START + timedelta(seconds=600)
    samples = [sample(600,10)]
    older = calculate(samples,START,boundary,[policy()])
    newer = calculate(samples,boundary,boundary+timedelta(seconds=600),[policy()])
    assert older["coverage"]["sample_count"] == 0
    assert older["metrics"]["observed_peak"] is None
    assert newer["coverage"]["sample_count"] == 1
    assert newer["metrics"]["observed_peak"] == 10
