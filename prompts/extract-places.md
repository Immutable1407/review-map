# Prepare Review Map intake

Read the provided capture artifacts and produce one JSON document matching `examples/intake.schema.json`. This is an extraction step for a local collection, not source discovery.

1. Identify the actual capture backend. When outputs come from `yichen-content-archive`, preserve that attribution; do not claim to have developed its video/platform acquisition method.
2. Register each source with a stable platform/content ID when available. Preserve the supplied source text and identify whether it is original text, automatic subtitles, a description, OCR, authorized ASR or user-provided content.
3. Split independent restaurants, cafes, parks, galleries and other places into separate items. Keep non-place knowledge out of the map handoff.
4. For every proposed place, attach exact quotes from the registered text using its source ID. Use only evidence actually read. A title or a downloaded video file does not establish the contents of uninspected frames or missing speech.
5. Set `confirmation: confirmed` only for a name supported by that evidence. Set `needs_review` otherwise. Leave an unknown city empty. Do not invent an address, food recommendation or branch.
6. Use the stored categories: 美食, 甜品, 咖啡, 酒吧, 公园, 展馆, 小店, 游玩. Retain recommendations only when the source supplies them.
7. Deliver the JSON to `scripts/ingest.py` for validation and staging. Use `--deliver` only when this batch is intended to enter the place-matching workflow.

The downstream calibration desk resolves POI branches, addresses and tags. This extraction step should not guess those decisions to make a batch appear complete.

## 中文要点

读取实际产物，保留来源与采集技术归属；将地点拆成独立条目，并附正文中的精确证据。已确认名称才能交接，未知城市留空，地址和分店交给高德候选及人工校对。非地点知识不强塞进地图。JSON 范例见 `examples/intake.json`。
