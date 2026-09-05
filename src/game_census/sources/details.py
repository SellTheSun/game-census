"""Versioned per-app API captures, independent of the original name-only parser.

An envelope retains the exact response text and requested identity for APIs whose
response does not echo the app ID. Snapshots do not enroll apps for tracking.
"""
import json
import re
from html.parser import HTMLParser
from urllib.parse import urlsplit

from . import players
from .base import Capture, SourceError, parse_json, validate_app_id
from .http import request

STORE = "steam_store_details_v1"
REVIEWS = "steam_review_summary_v1"
NEWS = "steam_app_news_v1"
CURRENT = "steam_app_current_players_v1"
MEDIA_HOSTS = frozenset({"shared.akamai.steamstatic.com", "shared.fastly.steamstatic.com",
                         "cdn.akamai.steamstatic.com", "cdn.fastly.steamstatic.com",
                         "cdn.cloudflare.steamstatic.com", "steamcdn-a.akamaihd.net"})


class ChartImages(HTMLParser):
    """Presentation-only artwork from retained chart HTML; chart facts stay v1."""
    def __init__(self):
        super().__init__()
        self.images, self.app_id, self.image = {}, None, None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self.app_id, self.image = None, None
        if tag == "a":
            match = re.match(r"https://store\.steampowered\.com/app/(\d+)(?:/|\?)", attrs.get("href", ""))
            if match:
                self.app_id = int(match[1])
        if tag == "img":
            candidate = safe_url(attrs.get("src"), media=True)
            if candidate:
                self.image = candidate

    def handle_endtag(self, tag):
        if tag == "tr" and self.app_id and self.image:
            self.images[self.app_id] = self.image


class PlainText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.hidden += 1
        if tag in ("br", "p", "li", "h2", "h3"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def plain(value):
    parser = PlainText()
    parser.feed(value if isinstance(value, str) else "")
    return "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())


def safe_url(value, *, media=False):
    if not isinstance(value, str):
        return None
    try:
        url = urlsplit(value)
        if url.scheme not in ("http", "https") or not url.hostname or url.username or url.password:
            return None
        if media and (url.scheme != "https" or url.hostname not in MEDIA_HOSTS or url.port not in (None, 443)):
            return None
        return value
    except ValueError:
        return None


def invalid():
    return SourceError("invalid_details", "Steam did not return valid details for this app.",
                       "Retry Refresh details later. Previously captured data remains available.")


def strings(value):
    return [plain(item) for item in value if isinstance(item, str)] if isinstance(value, list) else []


def objects(value):
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def ids(value):
    return [item for item in value if type(item) is int and 1 <= item <= 4294967295] if isinstance(value, list) else []


def store_value(body, app_id):
    entry = body.get(str(app_id))
    if not isinstance(entry, dict) or entry.get("success") is not True:
        raise invalid()
    data = entry.get("data")
    if not isinstance(data, dict) or type(data.get("steam_appid")) is not int or data["steam_appid"] != app_id or not isinstance(data.get("name"), str):
        raise invalid()
    result = {"items": [{"app_id": app_id, "name": data["name"]}], "app_id": app_id}
    for key in ("name", "type", "short_description", "about_the_game", "supported_languages", "controller_support", "drm_notice"):
        result[key] = plain(data.get(key))
    for key in ("developers", "publishers"):
        result[key] = strings(data.get(key))
    result["is_free"] = data.get("is_free") if type(data.get("is_free")) is bool else None
    result["platforms"] = [key for key, value in (data.get("platforms") or {}).items() if value is True] if isinstance(data.get("platforms"), dict) else []
    result["release_date"] = plain((data.get("release_date") or {}).get("date")) if isinstance(data.get("release_date"), dict) else ""
    result["coming_soon"] = (data.get("release_date") or {}).get("coming_soon") is True if isinstance(data.get("release_date"), dict) else False
    result["website"] = safe_url(data.get("website"))
    result["header_image"] = safe_url(data.get("header_image"), media=True)
    for key in ("categories", "genres"):
        result[key] = [plain(row.get("description")) for row in objects(data.get(key)) if isinstance(row.get("description"), str)]
    result["screenshots"] = [{"thumbnail": safe_url(row.get("path_thumbnail"), media=True), "full": safe_url(row.get("path_full"), media=True)}
                             for row in objects(data.get("screenshots")) if safe_url(row.get("path_thumbnail"), media=True) and safe_url(row.get("path_full"), media=True)]
    result["requirements"] = {platform: {key: plain(value) for key, value in data.get(platform + "_requirements", {}).items() if key in ("minimum", "recommended") and isinstance(value, str)}
                              for platform in ("pc", "mac", "linux") if isinstance(data.get(platform + "_requirements"), dict)}
    result["dlc"] = ids(data.get("dlc"))
    result["packages"] = ids(data.get("packages"))
    result["demos"] = [{"app_id": row["appid"], "description": plain(row.get("description"))} for row in objects(data.get("demos")) if ids([row.get("appid")])]
    result["fullgame"] = None
    if isinstance(data.get("fullgame"), dict) and str(data["fullgame"].get("appid", "")).isdigit():
        related = int(data["fullgame"]["appid"])
        if ids([related]):
            result["fullgame"] = {"app_id": related, "name": plain(data["fullgame"].get("name"))}
    price = data.get("price_overview")
    result["price"] = None
    if isinstance(price, dict) and isinstance(price.get("currency"), str) and all(type(price.get(key)) is int and price[key] >= 0 for key in ("initial", "final", "discount_percent")):
        result["price"] = {key: price[key] for key in ("currency", "initial", "final", "discount_percent")}
        result["price"].update({key: plain(price.get(key)) for key in ("initial_formatted", "final_formatted")})
    result["purchase_options"] = [{"package_id": row["packageid"], "description": plain(row.get("option_text"))}
                                  for group in objects(data.get("package_groups")) for row in objects(group.get("subs")) if ids([row.get("packageid")])]
    achievements = data.get("achievements")
    result["achievements"] = None
    if isinstance(achievements, dict) and type(achievements.get("total")) is int and achievements["total"] >= 0:
        result["achievements"] = {"total": achievements["total"], "highlighted": [{"name": plain(row.get("localized_name") or row.get("name")), "image": safe_url(row.get("path") or row.get("icon"), media=True)} for row in objects(achievements.get("highlighted"))]}
    return result


class Adapter:
    VERSION = "1"

    def __init__(self, source, group, url):
        self.SOURCE, self.HOST_GROUP, self.URL = source, group, url

    def parse(self, payload, unused_app_id=None):
        envelope = parse_json(payload)
        app_id = envelope.get("app_id")
        validate_app_id(app_id)
        if not isinstance(envelope.get("body"), str):
            raise invalid()
        body = parse_json(envelope["body"].encode("utf-8"))
        if self.SOURCE == STORE:
            return store_value(body, app_id)
        result = {"items": [], "app_id": app_id}
        if self.SOURCE == CURRENT:
            result["player_count"] = players.parse(envelope["body"].encode("utf-8"), app_id)
        elif self.SOURCE == REVIEWS:
            summary = body.get("query_summary")
            if body.get("success") != 1 or not isinstance(summary, dict) or not all(type(summary.get(key)) is int and summary[key] >= 0 for key in ("total_positive", "total_negative", "total_reviews")):
                raise invalid()
            if summary["total_positive"] + summary["total_negative"] != summary["total_reviews"]:
                raise invalid()
            result.update({key: summary[key] for key in ("total_positive", "total_negative", "total_reviews")})
            result["description"] = plain(summary.get("review_score_desc"))
            result["positive_percent"] = round(summary["total_positive"] * 100 / summary["total_reviews"], 2) if summary["total_reviews"] else None
        else:
            news = body.get("appnews")
            if not isinstance(news, dict) or news.get("appid") != app_id or not isinstance(news.get("newsitems"), list):
                raise invalid()
            result["articles"] = [{"title": plain(row.get("title")), "body": plain(row.get("contents")), "date": row["date"], "url": f"https://store.steampowered.com/news/app/{app_id}/view/{row['gid']}"}
                                   for row in objects(news["newsitems"]) if type(row.get("date")) is int and 0 <= row["date"] <= 253402300799 and str(row.get("gid", "")).isdigit() and row.get("feedname") == "steam_community_announcements"]
        return result

    def fetch(self, client, app_id, max_bytes):
        validate_app_id(app_id)
        parameters = {"appid": app_id}
        if self.SOURCE == STORE:
            parameters = {"appids": app_id, "cc": "us", "l": "english"}
        elif self.SOURCE == REVIEWS:
            parameters = {"json": 1, "language": "all", "purchase_type": "all", "num_per_page": 0}
        elif self.SOURCE == NEWS:
            parameters.update(count=5, maxlength=600, feeds="steam_community_announcements")
        payload, started, received, status = request(client, self.URL.format(app_id=app_id), parameters, max_bytes)
        try:
            retained = json.dumps({"app_id": app_id, "body": payload.decode("utf-8")}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except UnicodeError:
            raise invalid() from None
        return Capture(self.SOURCE, self.VERSION, None, started, received, status,
                       {**parameters, "requested_app_id": app_id}, retained, "request_identity_and_raw_response", self.parse(retained))


ADAPTERS = {adapter.SOURCE: adapter for adapter in (
    Adapter(STORE, "store", "https://store.steampowered.com/api/appdetails"),
    Adapter(REVIEWS, "store", "https://store.steampowered.com/appreviews/{app_id}"),
    Adapter(NEWS, "webapi", "https://api.steampowered.com/ISteamNews/GetNewsForApp/v2/"),
    Adapter(CURRENT, "webapi", players.URL),
)}
