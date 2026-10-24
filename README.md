# Review Map

[English](README.md) · [简体中文](README.zh-CN.md)

![Review Map](docs/cover.svg)

**Turn saved places into a map you can explore and review.**

Review Map connects content collection, evidence-backed place extraction, AMap matching, human calibration, and personal ratings in one local-first workflow. Browse a full-screen map, open compact place cards, find nearby saved places, and add your own 1–5 star ratings and notes.

The acquisition workflow uses **[yichen-content-archive](https://github.com/mcncarl/yichen-skills/tree/main/yichen-content-archive)** from **[mcncarl/yichen-skills](https://github.com/mcncarl/yichen-skills)**, particularly its Douyin video and Xiaohongshu note executors. Review Map provides an independent bridge and downstream product integration; it does **not** claim to have invented those acquisition methods. See [Attribution](ATTRIBUTION.md).

## How it fits together

```text
Known post / video URLs
  → yichen-content-archive: metadata, text, optional media
  → agent-assisted place extraction + source evidence
  → immutable source versions and staged place batches
  → AMap POI search, scoring and branch disambiguation
  → calibration desk: select branches / fill addresses / correct tags
  → full-screen map → personal ratings and reviews
```

Source collection follows the original LLM Wiki workflow: keep the original capture, assign a stable source ID, distinguish retrieval success from content completeness, and hand off confirmed places in a separate step. Non-place knowledge can stay in your Wiki.

## Features

- **Collection bridge:** exact Douyin video and Xiaohongshu note URLs; metadata-only by default, media downloads opt-in. Local normalized captures work without the external skill.
- **Traceable intake:** immutable source versions, append-only ledgers, quoted evidence, place deduplication, and a queue for unconfirmed names.
- **Place matching:** AMap Web Service search and geocoding, name/type scoring, branch ambiguity checks, stable POI identities, merged aliases and recommended food.
- **Desktop calibration:** choose multiple valid branches, use an exclusive “all wrong” option, enter missing addresses, and correct multiple tags. Progress stays in the browser and exports as JSON.
- **Map:** MapLibre/OpenFreeMap, category-colored pins, clusters, search, city/category filters, nearby saved places, navigation, deep links, keyboard shortcuts and mobile layouts.
- **Personal reviews:** public browsing, password-gated writing, optional 1–5 stars, comments, editing, deletion, local drafts and stale-edit detection. SQLite keeps reviews separate from map builds.

## Quick start

Python **3.10+** is enough for the app and build. Node.js is optional for JavaScript syntax checks. The included demo uses four fictional places and two calibration exercises; no AMap key or acquisition account is needed.

```bash
git clone https://github.com/Immutable1407/review-map.git
cd review-map
python3 scripts/demo.py
python3 scripts/build_single_file.py
python3 scripts/set_password.py
python3 scripts/serve.py
```

Open **http://127.0.0.1:8765/**. The password command accepts hidden input; the app has no default password. Open **http://127.0.0.1:8765/calibrate/** for the desktop calibration desk. On a remote host, sign in on the map before opening it.

The build creates `dist/Review-Map.html` and `dist/Calibration-Desk.html`, with fonts, runtime scripts and data embedded. Map tiles still need a network connection. Review writes use the Python service rather than a standalone HTML file.

## Add your own places

### 1. Acquire source content

Install `yichen-content-archive` separately using the [upstream instructions](https://github.com/mcncarl/yichen-skills/tree/main/yichen-content-archive). Its code is **not bundled here**. Its personal-learning/non-commercial license remains separate from this repository’s MIT license; see [the upstream license](https://github.com/mcncarl/yichen-skills/blob/main/LICENSE).

```bash
python3 scripts/acquire.py \
  --url 'https://www.douyin.com/video/<video-id>' \
  --upstream-skill /path/to/yichen-content-archive \
  --python /path/to/acquisition-env/bin/python
```

This invokes the upstream `douyin_download.py` with `--metadata-only`. Xiaohongshu URLs use `xiaohongshu_fetch.py --skip-media`. Add `--download-media` only when you want the associated media. `--dry-run` shows the selected backend and mode without calling it.

Each run gets a new directory under `data/acquisition/runs/` with private executor output and a `capture.json` recording the actual backend, status and artifacts. This bridge does not export private favorites, search for more posts, or perform ASR.

### 2. Extract and register places

Use your coding agent with [the extraction prompt](prompts/extract-places.md), or prepare the same JSON manually. [examples/intake.json](examples/intake.json) shows the contract: source text/status, stable IDs, proposed places and exact evidence quotes.

```bash
python3 scripts/ingest.py path/to/intake.json
python3 scripts/ingest.py path/to/intake.json --deliver
```

The first command registers source versions, stages confirmed place lines and saves uncertain items for review. `--deliver` additionally writes a new `raw/YYYY-M-D_update.md` batch and its per-place metadata. Repeating the same delivered intake does not create another batch. [Architecture and schemas](docs/architecture.md) describe the ledgers and gates.

An agent can read platform text, subtitles or locally produced OCR and prepare the intake. Media download alone is not a transcript. If a name is unconfirmed it stays upstream; if the name is confirmed but the city is unknown, it goes to manual address calibration.

### 3. Match and calibrate

```bash
cp config/amap-config.example.json config/amap-config.local.json
# Fill webService.key in that local file, or set AMAP_WEB_SERVICE_KEY.
python3 scripts/build_places.py
python3 scripts/build_single_file.py
```

Open the calibration desk. Export a JSON batch, put it in `data/reviews/`, and apply it:

```bash
python3 scripts/apply_review_results.py path/to/export.json
python3 scripts/build_single_file.py
python3 scripts/validate.py
```

Unmentioned rows remain pending. “All wrong” moves a place to address entry. A geocoding failure stays available for correction. Reapplying an export is idempotent. The Web Service key is used only by Python; the MapLibre frontend needs no AMap browser key.

Restart the app service after changing the place dataset so its accepted place IDs reload. Rebuilding HTML does not overwrite the review database.

## Project layout

```text
scripts/       acquisition bridge, intake, matching, build and review service
web/           map frontend, calibration desk, fonts and vendored map runtime
examples/      fictional demo places, calibration cases and intake document
prompts/       agent-assisted place extraction contract
config/        distributable configuration templates
deploy/        generic reverse-proxy and service examples
tests/         offline intake, matching/calibration and API tests
raw/           your delivered place batches                  [local]
data/          captures, ledgers, caches and SQLite reviews   [local]
dist/          generated single-file pages                    [local]
```

## Development

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build_single_file.py
python3 scripts/validate.py
git add .
python3 scripts/audit_public.py
```

Tests run offline against synthetic data, temporary SQLite databases and a fake acquisition executor. An optional GitHub Actions template is provided at `.github/ci.example.yml`. Network acquisition depends on the separately installed upstream tool; AMap matching uses your own key.

For hosting, see [deployment](docs/deployment.md). The app is a single-writer personal review service, not a multi-account review marketplace. Acquisition, calibration and runtime data are excluded from Git by default.

## License and credits

Original Review Map code: [MIT](LICENSE). Optional acquisition: **yichen-skills / yichen-content-archive**, separately licensed and not redistributed. MapLibre, gcoord, OpenFreeMap/OpenMapTiles/OpenStreetMap and the bundled fonts retain their own notices. Full component references are in [ATTRIBUTION.md](ATTRIBUTION.md).
