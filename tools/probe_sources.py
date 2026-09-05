"""Bounded, read-only planning evidence: three public GETs, no key or retries."""
import datetime as dt
import json
import sys
import urllib.error
import urllib.request


def main():
    sources = [
        ("current_players", "https://api.steampowered.com/ISteamUserStats/GetNumberOfCurrentPlayers/v1/?appid=570"),
        ("store_details", "https://store.steampowered.com/api/appdetails?appids=570&cc=us&l=english&filters=basic,price_overview"),
        ("review_summary", "https://store.steampowered.com/appreviews/570?json=1&filter=all&language=all&day_range=30&cursor=*&review_type=all&purchase_type=steam&num_per_page=1&filter_offtopic_activity=1"),
    ]
    results = []
    for source, url in sources:
        item = {"source": source, "url": url, "observed_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Game-Census-Planning-Probe/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=20) as response:
                item["http_status"] = response.status
                payload = response.read(2_000_001)
                if len(payload) > 2_000_000:
                    raise ValueError("Response exceeds the 2 MB planning-probe limit")
                data = json.loads(payload)
            if source == "current_players":
                item["data"] = data["response"]
                if item["data"].get("result") != 1 or type(item["data"].get("player_count")) is not int or item["data"]["player_count"] < 0:
                    raise ValueError("Current-player response contract failed")
            elif source == "store_details":
                entry = data["570"]
                if entry.get("success") is not True:
                    raise ValueError("Store application result was unsuccessful")
                fields = ("steam_appid", "type", "name", "is_free", "required_age", "price_overview")
                item["data"] = {key: entry["data"][key] for key in fields if key in entry["data"]}
            else:
                if data.get("success") != 1 or "query_summary" not in data:
                    raise ValueError("Review summary response contract failed")
                item["data"] = data["query_summary"]
                # Do not persist reviewer identifiers, text, or playtime.
            item["status"] = "success"
        except (OSError, ValueError, KeyError, TypeError) as exc:
            item["status"] = "failed"
            item["error"] = {"type": type(exc).__name__, "message": str(exc), "next_action": "Inspect source access and response contract before enabling this adapter."}
        results.append(item)
    print(json.dumps({"purpose": "Planning evidence, not a production collector or availability guarantee", "requests_max": 3, "results": results}, indent=2))
    return 1 if any(row["status"] != "success" for row in results) else 0


if __name__ == "__main__":
    sys.exit(main())
