#!/usr/bin/env python3
"""Parse the raw Markdown collection and resolve places through AMap Web Service."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "raw"
CACHE_PATH = ROOT / "data" / "cache" / "amap-search-cache.json"
GENERATED_DIR = ROOT / "data" / "generated"
PLACES_PATH = GENERATED_DIR / "places-data.js"
REVIEW_DATA_PATH = GENERATED_DIR / "review-data.js"
REVIEW_SEED_PATH = GENERATED_DIR / "review-progress-seed.js"
UNRESOLVED_PATH = GENERATED_DIR / "待确认地点.md"
RAW_UPDATE_METADATA_PATH = ROOT / "config" / "raw-update-metadata.local.json"

@dataclass
class Candidate:
    name: str
    query: str
    city: str
    category: str
    source: str
    section: str = ""
    recommended_food: list[str] = field(default_factory=list)
    note: str = ""
    source_ids: list[str] = field(default_factory=list)
    source_urls: list[str] = field(default_factory=list)


def clean_name(value: str) -> str:
    value = re.sub(r"^\d+[.、]\s*", "", value.strip())
    return value.rstrip("。；;")


def parse_item(line: str, city: str, category: str, source: str, section: str) -> Candidate:
    name = clean_name(line)
    recommended: list[str] = []
    note = ""
    if "：" in name or ":" in name:
        parts = re.split(r"[：:]", name, maxsplit=1)
        name = parts[0].strip()
        recommended = [x.strip() for x in re.split(r"[，,、]", parts[1]) if x.strip()]
    match = re.search(r"[（(]([^）)]+)[）)]", name)
    if match:
        parenthetical = match.group(1).strip()
        note = parenthetical
    return Candidate(
        name=name,
        query=name,
        city=city,
        category=category,
        source=source,
        section=section,
        recommended_food=recommended,
        note=note,
    )


def parse_markdown_files() -> tuple[list[Candidate], list[Candidate]]:
    """Read explicitly annotated raw batches; never infer a city from a filename."""
    metadata = json.loads(RAW_UPDATE_METADATA_PATH.read_text(encoding="utf-8")) if RAW_UPDATE_METADATA_PATH.exists() else {}
    candidates, manual = [], []
    for path in sorted(RAW_DIR.glob("*.md")):
        entries = metadata.get(path.name)
        if not isinstance(entries, dict):
            raise ValueError(f"Add per-place metadata for {path.name} before matching")
        for raw_line in path.read_text(encoding="utf-8").splitlines():
            line = clean_name(re.sub(r"^[-*]\s+", "", raw_line.strip()))
            if not line or line.startswith("#"):
                continue
            candidate = parse_item(line, "", "", path.name, "")
            item = entries.get(candidate.name)
            if not isinstance(item, dict):
                raise ValueError(f"Missing metadata for {candidate.name!r} in {path.name}")
            candidate.city = str(item.get("city") or "")
            candidate.category = str(item.get("category") or "")
            if candidate.category not in {"美食","甜品","咖啡","酒吧","公园","展馆","小店","游玩"}:
                raise ValueError(f"Choose a supported category for {candidate.name!r}")
            candidate.query = str(item.get("query") or candidate.name)
            candidate.source_ids = list(item.get("sourceIds") or [])
            candidate.source_urls = list(item.get("sourceUrls") or [])
            (candidates if candidate.city else manual).append(candidate)
    return candidates, manual

def normalized(value: str) -> str:
    value = value.lower()
    value = re.sub(r"[（(].*?[）)]", "", value)
    value = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "", value)
    for suffix in ("餐厅", "酒吧", "咖啡店", "咖啡", "烘焙", "料理", "专门店", "旗舰店"):
        if value.endswith(suffix) and len(value) > len(suffix) + 1:
            value = value[: -len(suffix)]
    return value


def similarity(query: str, poi_name: str) -> float:
    a, b = normalized(query), normalized(poi_name)
    if not a or not b:
        return 0.0
    seq = SequenceMatcher(None, a, b).ratio()
    containment = min(len(a), len(b)) / max(len(a), len(b)) if a in b or b in a else 0
    return max(seq, containment)


def search_amap(
    key: str,
    candidate: Candidate,
    cache: dict,
    opener: urllib.request.OpenerDirector,
) -> list[dict]:
    cache_key = f"{candidate.city}|{candidate.query}"
    if cache_key in cache:
        return cache[cache_key]
    params = urllib.parse.urlencode({
        "key": key,
        "keywords": candidate.query,
        "city": candidate.city,
        "citylimit": "true",
        "offset": "10",
        "page": "1",
        "extensions": "all",
    })
    url = "https://restapi.amap.com/v3/place/text?" + params
    with opener.open(url, timeout=20) as response:
        payload = json.load(response)
    if payload.get("status") != "1":
        raise RuntimeError(f"AMap error {payload.get('infocode')}: {payload.get('info')}")
    results = payload.get("pois", [])
    cache[cache_key] = results
    time.sleep(0.06)
    return results


def amap_opener() -> urllib.request.OpenerDirector:
    """Return a direct AMap opener independent of proxy environment variables."""
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def type_adjustment(category: str, poi_type: str) -> float:
    if category in {"美食", "甜品", "咖啡"}:
        return 0.08 if "餐饮服务" in poi_type else -0.16
    if category == "酒吧":
        return 0.06 if "餐饮服务" in poi_type or "体育休闲服务" in poi_type else -0.10
    if category == "公园":
        return 0.08 if "风景名胜" in poi_type else -0.08
    if category == "展馆":
        return 0.08 if "科教文化服务" in poi_type or "风景名胜" in poi_type else -0.08
    return 0.0


def rank_results(candidate: Candidate, results: list[dict]) -> list[tuple[float, dict]]:
    ranked = []
    for poi in results:
        poi_type = str(poi.get("type", ""))
        if candidate.category in {"美食", "甜品", "咖啡"} and "餐饮服务" not in poi_type:
            continue
        if candidate.category == "酒吧" and "餐饮服务" not in poi_type and "体育休闲服务" not in poi_type:
            continue
        score = similarity(candidate.query, str(poi.get("name", "")))
        score += type_adjustment(candidate.category, poi_type)
        section = candidate.section
        if section and str(poi.get("adname", "")) in section:
            score += 0.08
        note = candidate.note
        if note and (note in str(poi.get("name", "")) or note in str(poi.get("address", ""))):
            score += 0.12
        ranked.append((score, poi))
    return sorted(ranked, key=lambda item: item[0], reverse=True)


def is_ambiguous(candidate: Candidate, ranked: list[tuple[float, dict]]) -> bool:
    if len(ranked) < 2:
        return False
    top_score, top = ranked[0]
    second_score, second = ranked[1]
    has_branch_hint = bool(candidate.note and any(x in candidate.note for x in ("店", "区", "路", "街", "里")))
    same_brand = normalized(str(top.get("name", ""))) == normalized(str(second.get("name", "")))
    return not has_branch_hint and same_brand and top_score - second_score < 0.08


def short_name_mismatch(candidate: Candidate, ranked: list[tuple[float, dict]]) -> bool:
    if not ranked:
        return False
    query = normalized(candidate.query)
    result = normalized(str(ranked[0][1].get("name", "")))
    if len(query) > 4:
        return False
    if len(query) <= 3:
        return query != result
    return query not in result and result not in query


def place_record(candidate: Candidate, poi: dict) -> dict:
    lng, lat = [float(x) for x in str(poi["location"]).split(",")]
    place_id = str(poi.get("id") or hashlib.sha1(f"{candidate.city}|{candidate.name}|{lng}|{lat}".encode()).hexdigest()[:14])
    return {
        "id": place_id,
        "name": str(poi.get("name") or candidate.name),
        "savedName": candidate.name,
        "city": candidate.city,
        "district": str(poi.get("adname") or ""),
        "address": str(poi.get("address") or ""),
        "location": [lng, lat],
        "category": candidate.category,
        "tags": [candidate.category],
        "recommendedFood": candidate.recommended_food,
        "note": candidate.note,
        "source": candidate.source,
        "amapPoiId": str(poi.get("id") or ""),
        "sourceIds": candidate.source_ids,
        "sourceUrls": candidate.source_urls,
    }


def write_outputs(resolved: list[dict], unresolved: list[tuple[Candidate, list[tuple[float, dict]], str]], config: dict) -> None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    auto_resolved_count = len(resolved)
    existing_places: list[dict] = []
    if PLACES_PATH.exists():
        match = re.fullmatch(
            r"window\.PLACES_DATA = (.*);\s*",
            PLACES_PATH.read_text(encoding="utf-8"),
            re.S,
        )
        if match:
            existing_places = json.loads(match.group(1))
    # Never carry forward an auto-match made from an unscoped dated update.
    # Such records can only predate the required per-item metadata workflow.
    existing_places = [
        place
        for place in existing_places
        if not (
            not place.get("city")
            and re.fullmatch(
                r"\d{4}-\d{1,2}-\d{1,2}_update\.md",
                str(place.get("source") or ""),
            )
        )
    ]
    seed: dict[str, dict] = {}
    calibrated_tag_ids: set[str] = set()
    if REVIEW_SEED_PATH.exists():
        seed_match = re.fullmatch(
            r"window\.PLACE_REVIEW_SEED = (.*);\s*",
            REVIEW_SEED_PATH.read_text(encoding="utf-8"),
            re.S,
        )
        if seed_match:
            seed = json.loads(seed_match.group(1))
            calibrated_tag_ids = {
                key.removeprefix("tag:")
                for key in seed
                if key.startswith("tag:")
            }
    if not REVIEW_SEED_PATH.exists():
        REVIEW_SEED_PATH.write_text('window.PLACE_REVIEW_SEED = {};\n', encoding='utf-8')
    merged_by_id = {
        str(place.get("amapPoiId") or place["id"]): place
        for place in existing_places
    }
    for place in resolved:
        key = str(place.get("amapPoiId") or place["id"])
        existing = merged_by_id.get(key)
        if not existing:
            place.setdefault("savedNames", [place.get("savedName", place["name"])])
            merged_by_id[key] = place
            continue
        aliases = list(existing.get("savedNames") or [existing.get("savedName", existing["name"])])
        same_saved_item = place.get("savedName") in aliases
        for alias in place.get('savedNames') or [place.get('savedName')]:
            if alias and alias not in aliases:
                aliases.append(alias)
        existing["savedNames"] = aliases
        for field in ("sourceIds", "sourceUrls"):
            existing[field] = list(dict.fromkeys(existing.get(field, []) + place.get(field, [])))
        existing["savedName"] = aliases[0]
        existing["recommendedFood"] = sorted(set(existing.get("recommendedFood", []) + place.get("recommendedFood", [])))
        sources = [value for value in existing.get("source", "").split("、") if value]
        for source in place.get("source", "").split("、"):
            if source and source not in sources:
                sources.append(source)
        existing["source"] = "、".join(sources)
        if str(existing.get("id")) not in calibrated_tag_ids:
            if same_saved_item:
                existing["category"] = place["category"]
                existing["tags"] = list(place["tags"])
            else:
                tags = list(existing.get("tags") or [existing.get("category", "游玩")])
                if place["category"] not in tags:
                    tags.append(place["category"])
                existing["tags"] = tags
        else:
            existing.setdefault("tags", [existing.get("category", "游玩")])
    resolved = list(merged_by_id.values())
    resolved.sort(key=lambda p: (p["city"], p["category"], p["name"].lower()))
    payload = json.dumps(resolved, ensure_ascii=False, separators=(",", ":"))
    PLACES_PATH.write_text(f"window.PLACES_DATA = {payload};\n", encoding="utf-8")
    review_by_id: dict[str, dict] = {}
    active_unresolved: list[tuple[Candidate, list[tuple[float, dict]], str]] = []
    for candidate, ranked, reason in unresolved:
        review_id = hashlib.sha1(
            f"{candidate.city}|{candidate.name}|{candidate.source}".encode("utf-8")
        ).hexdigest()[:16]
        prior_decision = seed.get(review_id, {})
        if prior_decision.get("kind") in {
            "candidate", "candidates", "manual_address", "discarded",
        }:
            continue
        active_unresolved.append((candidate, ranked, reason))
        item = review_by_id.setdefault(review_id, {
            "id": review_id,
            "name": candidate.name,
            "city": candidate.city,
            "category": candidate.category,
            "source": candidate.source,
            "reason": reason,
            "recommendedFood": candidate.recommended_food,
            "sourceIds": candidate.source_ids,
            "sourceUrls": candidate.source_urls,
            "candidates": [],
        })
        seen_candidate_ids = {p["id"] for p in item["candidates"]}
        for _, poi in ranked[:3]:
            poi_id = str(poi.get("id") or hashlib.sha1(
                f"{poi.get('name')}|{poi.get('address')}".encode("utf-8")
            ).hexdigest()[:14])
            if poi_id in seen_candidate_ids:
                continue
            location = []
            if poi.get("location"):
                try:
                    location = [float(x) for x in str(poi["location"]).split(",")]
                except (TypeError, ValueError):
                    location = []
            item["candidates"].append({
                "id": poi_id,
                "name": str(poi.get("name") or ""),
                "district": str(poi.get("adname") or ""),
                "address": str(poi.get("address") or ""),
                "location": location,
            })
            seen_candidate_ids.add(poi_id)
    review_items = sorted(
        review_by_id.values(),
        key=lambda item: (0 if item["candidates"] else 1, item["city"], item["name"].lower()),
    )
    REVIEW_DATA_PATH.write_text(
        "window.PLACE_REVIEW_DATA = "
        + json.dumps(review_items, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    lines = [
        "# 待确认地点",
        "",
        f"本次自动确认 {auto_resolved_count} 个地点；地图累计 {len(resolved)} 个地点；以下 {len(active_unresolved)} 个条目需要补充地址或选择门店。",
        "",
    ]
    for candidate, ranked, reason in active_unresolved:
        lines.extend([f"## {candidate.name}", "", f"- 城市：{candidate.city or '未知'}", f"- 来源：{candidate.source}", f"- 原因：{reason}"])
        if ranked:
            lines.append("- 高德候选：")
            for _, poi in ranked[:3]:
                lines.append(f"  - {poi.get('name')}｜{poi.get('adname', '')}{poi.get('address', '')}")
        lines.append("")
    UNRESOLVED_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="ignore cached AMap responses")
    parser.add_argument(
        "--direct-amap",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()
    from common import load_amap_config
    config = load_amap_config(ROOT)
    key = config["webService"]["key"]
    candidates, manual = parse_markdown_files()
    if candidates and not key:
        raise SystemExit("Set AMAP_WEB_SERVICE_KEY or config/amap-config.local.json before matching")
    # AMap is always direct. Keep --direct-amap accepted for compatibility with
    # older documented commands.
    opener = amap_opener()
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cache = {} if args.refresh or not CACHE_PATH.exists() else json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    resolved_by_id: dict[str, dict] = {}
    unresolved: list[tuple[Candidate, list[tuple[float, dict]], str]] = [(c, [], "无法从原文确定城市或具体地点") for c in manual]
    for index, candidate in enumerate(candidates, 1):
        try:
            results = search_amap(key, candidate, cache, opener)
        except Exception as exc:
            unresolved.append((candidate, [], f"查询失败：{type(exc).__name__}"))
            continue
        ranked = rank_results(candidate, results)
        if not ranked or ranked[0][0] < 0.66:
            unresolved.append((candidate, ranked, "没有足够可信的匹配"))
            continue
        if short_name_mismatch(candidate, ranked):
            unresolved.append((candidate, ranked, "短名称与搜索结果不完全一致"))
            continue
        if is_ambiguous(candidate, ranked):
            unresolved.append((candidate, ranked, "存在多个同名或同品牌门店"))
            continue
        record = place_record(candidate, ranked[0][1])
        existing = resolved_by_id.get(record["id"])
        if existing:
            from apply_review_results import merge_place
            merge_place(existing,record)
        else:
            resolved_by_id[record["id"]] = record
        if index % 25 == 0:
            CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            print(f"resolved queries: {index}/{len(candidates)}")
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    write_outputs(list(resolved_by_id.values()), unresolved, config)
    print(f"places={len(resolved_by_id)} unresolved={len(unresolved)}")


if __name__ == "__main__":
    main()
