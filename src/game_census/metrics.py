"""Coverage and capped time-weighted averages calculated from retained observations."""
from datetime import datetime, timedelta
import math

ESTIMATOR_VERSION = "capped-step-v1"


def calculate(samples: list[dict], start: datetime, end: datetime, tracking: list[dict],
              gap_cap_multiplier: float = 2) -> dict:
    if start >= end:
        raise ValueError("history window start must precede its end")
    ordered = sorted(samples, key=lambda row: row["observed_at"])
    policies = sorted(tracking, key=lambda row: row["started_at"])
    requested = (end - start).total_seconds()
    in_window = [s for s in ordered if start <= s["observed_at"] < end]
    tracked_seconds, expected = 0.0, 0
    for index, policy in enumerate(policies):
        a = max(start, policy["started_at"])
        b = min(end, policies[index + 1]["started_at"] if index + 1 < len(policies) else end)
        seconds = max(0.0, (b - a).total_seconds())
        tracked_seconds += seconds
        expected += math.ceil(seconds / policy["interval_seconds"])
    covered, integral = 0.0, 0.0
    spans = []
    for index, sample in enumerate(ordered):
        observed = sample["observed_at"]
        applicable = [p for p in policies if p["started_at"] <= observed]
        if not applicable:
            continue
        cadence = applicable[-1]["interval_seconds"]
        a = max(start, observed)
        b = min(end, observed + timedelta(seconds=cadence * gap_cap_multiplier),
                ordered[index + 1]["observed_at"] if index + 1 < len(ordered) else end)
        if b <= a:
            continue
        seconds = (b - a).total_seconds()
        covered += seconds
        integral += sample["player_count"] * seconds
        spans.append((a, b))
    gaps = []
    cursor = start
    for a, b in spans:
        if a > cursor:
            gaps.append({"from": cursor.isoformat(), "to": a.isoformat(), "seconds": (a - cursor).total_seconds()})
        cursor = max(cursor, b)
    if cursor < end:
        gaps.append({"from": cursor.isoformat(), "to": end.isoformat(), "seconds": (end - cursor).total_seconds()})
    return {
        "coverage": {"sample_count": len(in_window), "expected_samples": expected,
                     "covered_seconds": covered, "requested_seconds": requested,
                     "tracked_seconds": tracked_seconds, "maximum_gap_seconds": max((g["seconds"] for g in gaps), default=0),
                     "coverage_ratio": covered / requested},
        "metrics": {"observed_peak": max((s["player_count"] for s in in_window), default=None),
                    "average_observed_ccu": integral / covered if covered else None,
                    "estimator_version": ESTIMATOR_VERSION},
        "gaps": gaps,
    }
