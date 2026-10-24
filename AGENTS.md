# Review Map contributor guide

Keep the collection and its sources separate from code. `raw/`, `data/`, `dist/`, local configuration and external acquisition tools are runtime state and stay out of Git. `examples/` contains the only distributable collection: fictional demo content.

## Product flow

Known source URLs → external acquisition → normalized intake → immutable source versions → confirmed place staging → AMap matching → calibration → map → authenticated personal reviews.

Video acquisition uses the separately installed `yichen-content-archive` component of `mcncarl/yichen-skills`. Do not copy its executors, prompts or platform methods into this repository or describe them as our invention. Keep this attribution in both READMEs and ATTRIBUTION.md. The bridge is independently implemented process orchestration; the external skill has its own license.

Use `prompts/extract-places.md` to prepare intake. Keep source IDs stable, preserve original evidence, and distinguish capture transport status from content completeness. Unknown place names stay in acquisition review; a known name without a confirmed city goes to manual calibration. Never manufacture an address or recommendation.

Do not modify acquired source versions or old ledgers. Handoffs are new files with collision suffixes and explicit per-item metadata. Repeat ingestion and calibration must be idempotent. An unmentioned calibration row remains pending; all-wrong candidates move to manual entry. Preserve POI identity, aliases, food recommendations, source references and manually corrected tags.

MapLibre uses a WGS84 display copy; AMap navigation retains the original GCJ-02 `location`. The map fills the viewport, with floating panels and compact progressive details. Mobile index rows are batched. Respect reduced motion.

Public reads and password-authenticated writes are a single-writer model. Store salted password hashes and sessions in the ignored SQLite directory. No default password and no front-end password check.

## Checks

```bash
python3 -m unittest discover -s tests -v
python3 scripts/demo.py
python3 scripts/build_single_file.py
python3 scripts/validate.py
python3 scripts/audit_public.py
```

Audit the staged tree before publishing. Never push another project's Git history, real source archives, credentials, collection data, calibration exports or production deployment records.
