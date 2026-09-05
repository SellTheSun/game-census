"""Deterministic, idempotent projection generation from versioned retained captures."""
import hashlib
from psycopg.types.json import Jsonb
from .sources import REGISTRY, SourceError, players, store


def project(conn, capture: dict) -> None:
    payload = bytes(capture["payload"])
    if hashlib.sha256(payload).hexdigest() != capture["checksum"]:
        raise SourceError("capture_checksum_mismatch", "A retained capture checksum did not match its payload.",
                          "Stop collection and verify a scratch restore before repairing canonical history.")
    adapter = REGISTRY.get(capture["source"])
    if adapter is None or adapter.VERSION != capture["source_version"]:
        raise SourceError("unknown_parser_version", "A retained capture requires an unavailable source parser.",
                          "Restore the matching application version before rebuilding projections.")
    value = adapter.parse(payload, capture["app_id"])
    if adapter is players:
        conn.execute("""INSERT INTO player_sample(capture_id,app_id,observed_at,player_count,parser_version)
            VALUES (%s,%s,%s,%s,%s) ON CONFLICT (capture_id) DO NOTHING""",
            (capture["capture_id"], capture["app_id"], capture["received_at"], value, adapter.VERSION))
    elif adapter is store:
        conn.execute("""INSERT INTO app_name(capture_id,app_id,observed_at,name,parser_version)
            VALUES (%s,%s,%s,%s,%s) ON CONFLICT (capture_id) DO NOTHING""",
            (capture["capture_id"], capture["app_id"], capture["received_at"], value, adapter.VERSION))
    else:
        conn.execute("""INSERT INTO discovery_snapshot(capture_id,source,observed_at,parameters,value,parser_version)
            VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
            (capture["capture_id"], capture["source"], capture["received_at"], Jsonb(capture["parameters"]), Jsonb(value), adapter.VERSION))
        for item in value["items"]:
            conn.execute("INSERT INTO catalog_entry(capture_id,app_id,name) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING",
                         (capture["capture_id"], item["app_id"], item["name"]))
