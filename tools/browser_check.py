"""Exercise the real local website without triggering any Steam collection."""
import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default="http://127.0.0.1:8000")
    p.add_argument("--output-dir", type=Path, default=Path("work/browser-check"))
    args = p.parse_args()
    url = args.url.rstrip("/")
    if urlsplit(url).hostname not in ("127.0.0.1", "localhost"):
        p.error("This bounded check accepts only a local instance URL.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as engine:
        browser = engine.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1080}, reduced_motion="reduce")
        errors, external = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("request", lambda req: external.append(req.url) if urlsplit(req.url).hostname not in ("127.0.0.1", "localhost") else None)
        before = page.request.get(url + "/api/v1/status").json()
        response = page.goto(url, wait_until="networkidle")
        assert response.status == 200, "Home must render successfully"
        apps = page.request.get(url + "/api/v1/apps").json()["items"]
        assert apps, "A real enrolled game is required for this journey"
        observed = next(item for item in apps if item["player_count"] is not None)
        app_id = observed["app_id"]
        assert page.get_by_role("heading", name="Player activity. With the full context.").is_visible()
        page.keyboard.press("Tab")
        assert page.get_by_role("link", name="Skip to content").evaluate("e => e === document.activeElement"), "Keyboard skip link must be first"
        page.keyboard.press("Enter")
        assert page.locator("#main").evaluate("e => e === document.activeElement")
        page.screenshot(path=str(args.output_dir / "desktop.png"), full_page=True)
        page.get_by_label("Search tracked game name or Steam app ID").fill(str(app_id))
        page.get_by_role("button", name="Search", exact=True).click()
        assert page.locator(".games-table tbody tr").count() == 1
        page.locator(f'.games-table a[href="/apps/{app_id}"]').click()
        assert page.url == f"{url}/apps/{app_id}"
        chart = page.get_by_role("img", name=f"{observed['name']} player observations over 24 hours")
        chart.focus()
        page.keyboard.press("End")
        assert "observation" in page.locator(".chart-readout").inner_text()
        page.locator("details.data-table summary").click()
        assert page.locator("details.data-table[open] tbody tr").count() >= 1
        page.get_by_role("link", name="1H", exact=True).click()
        assert "hours=1" in page.url
        for path in ("/methodology", "/status"):
            assert page.goto(url + path).status == 200
        assert page.goto(url + "/apps/4294967295").status == 404
        assert "not tracked" in page.locator("main").inner_text().lower()
        page.goto(url)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Mobile page must not overflow horizontally"
        page.screenshot(path=str(args.output_dir / "mobile.png"), full_page=True)
        after = page.request.get(url + "/api/v1/status").json()
        assert before["total_observations"] == after["total_observations"], "Browsing must not collect upstream observations"
        assert not errors, errors
        assert not external, external
        print(json.dumps({"status": "succeeded", "url": url, "app_id": app_id, "observed_player_count": observed["player_count"],
                          "observed_at": observed["observed_at"], "desktop": "1440x1080", "mobile": "390x844",
                          "checks": ["real stored count", "keyboard skip link", "tracked search", "game navigation", "keyboard chart", "observation table", "history window", "methodology", "status", "unknown game", "mobile overflow", "no external requests", "no browser errors", "no collection from browsing"],
                          "screenshots": [str((args.output_dir / name).resolve()) for name in ("desktop.png", "mobile.png")]}, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
