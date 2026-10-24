#!/usr/bin/env python3
"""Merge exported calibration choices into generated map data."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIR = ROOT / "data" / "generated"
REVIEWS_DIR = ROOT / "data" / "reviews"
PLACES_PATH = GENERATED_DIR / "places-data.js"
REVIEW_DATA_PATH = GENERATED_DIR / "review-data.js"
REVIEW_SEED_PATH = GENERATED_DIR / "review-progress-seed.js"
UNRESOLVED_PATH = GENERATED_DIR / "待确认地点.md"
CONFIG_PATH = ROOT / "config" / "amap-config.local.json"
GEOCODE_CACHE_PATH = ROOT / "data" / "cache" / "amap-geocode-cache.json"


def load_js_assignment(path: Path, variable: str) -> list[dict] | dict:
    text = path.read_text(encoding="utf-8")
    match = re.fullmatch(rf"window\.{re.escape(variable)} = (.*);\s*", text, re.S)
    if not match:
        raise ValueError(f"Cannot parse {path.name}")
    return json.loads(match.group(1))


def merge_text_values(current: str, incoming: str) -> str:
    values = [x for x in current.split("、") if x]
    for value in incoming.split("、"):
        if value and value not in values:
            values.append(value)
    return "、".join(values)


def normalize_tags(place: dict) -> None:
    tags = [str(tag) for tag in place.get("tags", []) if tag]
    if not tags and place.get("category"):
        tags = [str(place["category"])]
    place["tags"] = list(dict.fromkeys(tags))
    if place["tags"]:
        place["category"] = place["tags"][0]


def merge_place(target: dict, incoming: dict) -> None:
    aliases = list(target.get("savedNames") or [])
    if target.get("savedName") and target["savedName"] not in aliases:
        aliases.append(target["savedName"])
    for alias in incoming.get("savedNames") or [incoming.get("savedName", "")]:
        if alias and alias not in aliases:
            aliases.append(alias)
    target["savedNames"] = aliases
    target["savedName"] = aliases[0] if aliases else target.get("savedName", target["name"])
    target["recommendedFood"] = sorted(set(target.get("recommendedFood", []) + incoming.get("recommendedFood", [])))
    target["source"] = merge_text_values(target.get("source", ""), incoming.get("source", ""))
    target["tags"] = list(dict.fromkeys(target.get("tags", []) + incoming.get("tags", [])))
    if incoming.get("verified"):
        target["verified"] = True
    for field in ('sourceIds', 'sourceUrls'):
        target[field] = list(dict.fromkeys(target.get(field, []) + incoming.get(field, [])))
    normalize_tags(target)


def newest_results_file() -> Path:
    patterns = ("地图校对结果-*.json", "地点确认结果-*.json")
    files = [path for pattern in patterns for path in REVIEWS_DIR.glob(pattern)]
    if not files:
        raise FileNotFoundError("No exported calibration results found in data/reviews")
    return max(files, key=lambda path: path.stat().st_mtime)


def geocode_address(
    key: str,
    city: str,
    address: str,
    cache: dict,
    opener: urllib.request.OpenerDirector,
) -> dict | None:
    cache_key = f"{city}|{address}"
    if cache_key in cache:
        return cache[cache_key]
    params = urllib.parse.urlencode({"key": key, "city": city, "address": address, "output": "JSON"})
    with opener.open("https://restapi.amap.com/v3/geocode/geo?" + params, timeout=20) as response:
        payload = json.load(response)
    if payload.get("status") != "1":
        raise RuntimeError(f"AMap error {payload.get('infocode')}: {payload.get('info')}")
    geocode = (payload.get("geocodes") or [None])[0]
    cache[cache_key] = geocode
    return geocode


def amap_opener() -> urllib.request.OpenerDirector:
    """Return an opener that never inherits the agent runtime HTTP proxy."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def build_seed(exported: dict, review_items: list[dict], existing_seed: dict) -> tuple[dict, int]:
    # Calibration exports may be incremental (for example, tag changes only),
    # so never discard decisions from earlier exports that are absent here.
    seed = dict(existing_seed)
    seed.update({
        result["id"]: {
            key: value
            for key, value in result.items()
            if key in {"kind", "candidateId", "candidateIds", "address", "savedAt"}
        }
        for result in exported.get("results", [])
        if result.get("id") and result.get("kind")
    })
    for change in exported.get("tagChanges", []):
        if change.get("id") and change.get("tags"):
            seed[f"tag:{change['id']}"] = {
                "kind": "tags",
                "tags": change["tags"],
                "savedAt": change.get("savedAt"),
            }
    missing_count = 0
    for item in review_items:
        if item.get("id") and item["id"] not in seed:
            missing_count += 1  # Unmentioned rows remain pending, never implicitly discarded.
    return seed, missing_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", nargs="?", help="exported calibration JSON; defaults to newest file")
    parser.add_argument(
        "--direct-amap",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--mark-all-verified",
        action="store_true",
        help="mark every current map place verified so the calibration UI only shows future additions",
    )
    args = parser.parse_args()
    results_path = Path(args.results).resolve() if args.results else newest_results_file()

    places = load_js_assignment(PLACES_PATH, "PLACES_DATA")
    review_items = load_js_assignment(REVIEW_DATA_PATH, "PLACE_REVIEW_DATA")
    review_by_id = {item["id"]: item for item in review_items}
    exported = json.loads(results_path.read_text(encoding="utf-8"))
    from common import load_amap_config
    config = load_amap_config(ROOT)
    geocode_cache = json.loads(GEOCODE_CACHE_PATH.read_text(encoding="utf-8")) if GEOCODE_CACHE_PATH.exists() else {}
    # AMap is always direct. Keep --direct-amap accepted for compatibility with
    # older documented commands, but do not make safety depend on remembering it.
    opener = amap_opener()
    existing_seed = (
        load_js_assignment(REVIEW_SEED_PATH, "PLACE_REVIEW_SEED")
        if REVIEW_SEED_PATH.exists()
        else {}
    )

    seed, missing_count = build_seed(exported, review_items, existing_seed)
    by_id: dict[str, dict] = {}
    for place in places:
        normalize_tags(place)
        key = str(place.get("amapPoiId") or place["id"])
        if key in by_id:
            merge_place(by_id[key], place)
        else:
            place.setdefault("savedNames", [place.get("savedName", place["name"])])
            by_id[key] = place

    selected_count = 0
    manual_count = 0
    manual_unresolved_count = 0
    retry_manual_ids = set()
    for result in exported.get("results", []):
        review_item = review_by_id.get(result.get("id"), {})
        if result.get("kind") in {"candidate", "candidates"}:
            selected = list(result.get("selectedCandidates") or [])
            if result.get("selectedCandidate"):
                selected.append(result["selectedCandidate"])
            for candidate in selected:
                if not candidate.get("id") or len(candidate.get("location") or []) != 2:
                    continue
                selected_count += 1
                category = result.get("category") or "游玩"
                incoming = {
                    "id": str(candidate["id"]),
                    "name": candidate.get("name") or result["name"],
                    "savedName": result["name"],
                    "savedNames": [result["name"]],
                    "city": result.get("city") or "",
                    "district": candidate.get("district") or "",
                    "address": candidate.get("address") or "",
                    "location": candidate["location"],
                    "category": category,
                    "tags": [category],
                    "recommendedFood": review_item.get("recommendedFood") or [],
                    "note": "",
                    "source": result.get("source") or "",
                    "sourceIds": review_item.get("sourceIds", []),
                    "sourceUrls": review_item.get("sourceUrls", []),
                    "amapPoiId": str(candidate["id"]),
                    "verified": True,
                }
                key = incoming["amapPoiId"]
                if key in by_id:
                    merge_place(by_id[key], incoming)
                    by_id[key]["verified"] = True
                else:
                    by_id[key] = incoming
        elif result.get("kind") == "manual_address" and result.get("address"):
            if not config['webService']['key']:
                retry_manual_ids.add(result['id'])
                manual_unresolved_count += 1
                continue
            addresses = [
                line.strip()
                for line in re.split(r"[\r\n]+", result["address"])
                if line.strip()
            ]
            for address in addresses:
                try:
                    geocode = geocode_address(
                        config["webService"]["key"],
                        result.get("city") or "",
                        address,
                        geocode_cache,
                        opener,
                    )
                except Exception as exc:
                    print(f"manual_unresolved={result.get('name')} error={type(exc).__name__}")
                    manual_unresolved_count += 1
                    retry_manual_ids.add(result['id'])
                    continue
                if not geocode or not geocode.get("location"):
                    print(f"manual_unresolved={result.get('name')}")
                    manual_unresolved_count += 1
                    retry_manual_ids.add(result['id'])
                    continue
                lng, lat = [float(value) for value in geocode["location"].split(",")]
                category = result.get("category") or "游玩"
                place_id = "manual-" + hashlib.sha1(
                    f"{result['id']}|{address}".encode("utf-8")
                ).hexdigest()[:14]
                geocode_city = geocode.get("city")
                if not isinstance(geocode_city, str):
                    geocode_city = ""
                incoming = {
                    "id": place_id,
                    "name": result["name"],
                    "savedName": result["name"],
                    "savedNames": [result["name"]],
                    "city": result.get("city") or geocode_city or str(geocode.get("province") or ""),
                    "district": str(geocode.get("district") or ""),
                    "address": address,
                    "location": [lng, lat],
                    "category": category,
                    "tags": [category],
                    "recommendedFood": review_item.get("recommendedFood") or [],
                    "note": "手工确认地址",
                    "source": result.get("source") or "",
                    "sourceIds": review_item.get("sourceIds", []),
                    "sourceUrls": review_item.get("sourceUrls", []),
                    "amapPoiId": "",
                    "verified": True,
                }
                if place_id in by_id:
                    merge_place(by_id[place_id], incoming)
                    by_id[place_id]["verified"] = True
                else:
                    by_id[place_id] = incoming
                manual_count += 1

    places_by_public_id = {place["id"]: place for place in by_id.values()}
    tag_count = 0
    for change in exported.get("tagChanges", []):
        place = places_by_public_id.get(change.get("id"))
        tags = [str(tag) for tag in change.get("tags", []) if tag]
        if not place or not tags:
            continue
        place["tags"] = list(dict.fromkeys(tags))
        place["category"] = place["tags"][0]
        place["verified"] = True
        tag_count += 1

    merged = sorted(by_id.values(), key=lambda p: (p.get("city", ""), p.get("category", ""), p.get("name", "").lower()))
    if args.mark_all_verified:
        for place in merged:
            place["verified"] = True
    PLACES_PATH.write_text(
        "window.PLACES_DATA = " + json.dumps(merged, ensure_ascii=False, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    for item_id in retry_manual_ids:
        seed[item_id]['kind'] = 'all_wrong'
    REVIEW_SEED_PATH.write_text('window.PLACE_REVIEW_SEED = ' + json.dumps(seed, ensure_ascii=False, separators=(',', ':')) + ';\n', encoding='utf-8')
    remaining_review_items = [item for item in review_items if item.get("id") not in seed or seed[item['id']].get('kind') == 'all_wrong']
    REVIEW_DATA_PATH.write_text(
        "window.PLACE_REVIEW_DATA = "
        + json.dumps(remaining_review_items, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    UNRESOLVED_PATH.write_text(
        f"# 待确认地点\n\n仍有 {len(remaining_review_items)} 个地点待处理。\n",
        encoding="utf-8",
    )
    GEOCODE_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    GEOCODE_CACHE_PATH.write_text(json.dumps(geocode_cache, ensure_ascii=False), encoding="utf-8")
    aliases = sum(max(0, len(place.get("savedNames", [])) - 1) for place in merged)
    discarded_count = sum(
        value.get("kind") == "discarded"
        for key, value in seed.items()
        if not key.startswith("tag:")
    )
    print(
        f"selected={selected_count} manual={manual_count} manual_unresolved={manual_unresolved_count} "
        f"discarded={discarded_count} tag_changes={tag_count} "
        f"places_before={len(places)} places_after={len(merged)} merged_aliases={aliases}"
    )


if __name__ == "__main__":
    main()
