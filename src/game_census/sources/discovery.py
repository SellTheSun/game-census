"""Bounded Steam Store HTML and documented catalog API captures.

HTML contracts deliberately use table cells / search row semantics, not hashed CSS.
"""
import json
import re
from html.parser import HTMLParser
from .base import Capture, SourceError, parse_json, validate_app_id
from .http import request

VERSION = "1"
PLAYED = "steam_charts_mostplayed"
SALES = "steam_charts_topselling"
SEARCH = "steam_store_search"
CATALOG = "steam_store_catalog"
URLS = {PLAYED: "https://store.steampowered.com/charts/mostplayed",
        SALES: "https://store.steampowered.com/charts/topselling/global",
        SEARCH: "https://store.steampowered.com/search/",
        CATALOG: "https://api.steampowered.com/IStoreService/GetAppList/v1/"}


def invalid():
    return SourceError("invalid_schema", "Steam discovery response did not match its source contract.",
                       "Retry after checking the Steam source; the last successful snapshot remains available.")


class ChartHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows, self.cells, self.cell, self.app_id = [], None, None, None
        self.in_body = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tbody":
            self.in_body = True
        if self.in_body and tag == "tr":
            self.cells, self.app_id = [], None
        if self.cells is not None and tag == "td":
            self.cell = []
        if self.cells is not None and tag == "a":
            match = re.match(r"https://store\.steampowered\.com/app/(\d+)(?:/|\?)", attrs.get("href", ""))
            if match:
                self.app_id = int(match[1])

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self.cell is not None:
            self.cells.append("".join(self.cell).strip())
            self.cell = None
        if tag == "tr" and self.cells is not None:
            self.rows.append((self.app_id, self.cells))
            self.cells = None
        if tag == "tbody":
            self.in_body = False


class SearchHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.items, self.item, self.title, self.valid = [], None, False, False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if attrs.get("id") == "search_resultsRows":
            self.valid = True
        if tag == "a" and "search_result_row" in attrs.get("class", "").split():
            value = attrs.get("data-ds-appid", "")
            if value.isdecimal() and attrs.get("data-ds-itemkey", "").startswith("App_"):
                self.item = {"app_id": int(value), "name": ""}
        if self.item and tag == "span" and "title" in attrs.get("class", "").split():
            self.title = True

    def handle_data(self, data):
        if self.item and self.title:
            self.item["name"] += data

    def handle_endtag(self, tag):
        if tag == "span":
            self.title = False
        if tag == "a" and self.item:
            self.item["name"] = self.item["name"].strip()
            self.items.append(self.item)
            self.item, self.title = None, False


class Adapter:
    VERSION = VERSION

    def __init__(self, source):
        self.SOURCE = source
        self.HOST_GROUP = "webapi" if source == CATALOG else "store"

    def parse(self, payload, app_id=None):
        try:
            if self.SOURCE == CATALOG:
                response = parse_json(payload)["response"]
                items = [{"app_id": row["appid"], "name": row["name"]} for row in response["apps"]]
                # The live game catalog includes valid IDs with intentionally blank names.
                for item in items:
                    if isinstance(item["name"], str) and not item["name"].strip():
                        item["name"] = f"Steam app {item['app_id']}"
                more = response.get("have_more_results", False)
                cursor = response.get("last_appid", 0)
                if type(more) is not bool or type(cursor) is not int or cursor < 0 or (more and not items):
                    raise invalid()
                result = {"items": items, "have_more_results": more, "last_appid": cursor}
            elif self.SOURCE == SEARCH:
                parser = SearchHTML()
                parser.feed(payload.decode("utf-8"))
                if not parser.valid:
                    raise invalid()
                result = {"items": parser.items}
            else:
                parser = ChartHTML()
                parser.feed(payload.decode("utf-8"))
                items = []
                for app, cells in parser.rows:
                    if app is None:  # Packages and hardware keep their official rank positions.
                        continue
                    if len(cells) != 6:
                        raise invalid()
                    row = {"app_id": app, "name": cells[2], "rank": int(cells[1])}
                    if self.SOURCE == PLAYED:
                        row.update(players=int(cells[4].replace(",", "")), peak_today=int(cells[5].replace(",", "")))
                    items.append(row)
                if not items or len(items) > 100:
                    raise invalid()
                result = {"items": items}
            seen = set()
            for row in result["items"]:
                validate_app_id(row["app_id"])
                if row["app_id"] in seen or not isinstance(row["name"], str) or not row["name"].strip():
                    raise invalid()
                seen.add(row["app_id"])
                if "rank" in row and not 1 <= row["rank"] <= 100:
                    raise invalid()
                if any(row.get(key, 0) < 0 for key in ("players", "peak_today")):
                    raise invalid()
            return result
        except (KeyError, TypeError, ValueError, UnicodeError):
            raise invalid() from None

    def fetch(self, client, parameters, max_bytes, key=None):
        headers = None
        if self.SOURCE == CATALOG:
            if key is None or not key.get_secret_value():
                raise SourceError("catalog_key_required", "Full catalog sync requires sources.catalog_api_key.",
                                  "Configure a Steam Web API key, or use public Store search and charts.")
            headers = {"x-webapi-key": key.get_secret_value()}
            params = {"input_json": json.dumps(parameters, separators=(",", ":"))}
        else:
            params = parameters
        payload, started, received, status = request(client, URLS[self.SOURCE], params, max_bytes, headers=headers)
        value = self.parse(payload)
        if self.SOURCE == CATALOG and value["have_more_results"] and value["last_appid"] <= parameters["last_appid"]:
            raise invalid()
        return Capture(self.SOURCE, self.VERSION, None, started, received, status, parameters, payload, "raw_response", value)


ADAPTERS = {source: Adapter(source) for source in URLS}
