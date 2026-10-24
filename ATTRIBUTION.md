# Attribution / 技术归属

## Content acquisition — yichen-skills

Review Map's original collection workflow used **[mcncarl/yichen-skills](https://github.com/mcncarl/yichen-skills)**, specifically **yichen-content-archive**, for known-URL content acquisition. The relevant components are:

- [douyin_download.py](https://github.com/mcncarl/yichen-skills/blob/6e0c0ae43b5fd168040b8eb5193392e47b6f6301/yichen-content-archive/scripts/douyin_download.py): Douyin video metadata and optional video download.
- [xiaohongshu_fetch.py](https://github.com/mcncarl/yichen-skills/blob/6e0c0ae43b5fd168040b8eb5193392e47b6f6301/yichen-content-archive/scripts/xiaohongshu_fetch.py): Xiaohongshu note capture and optional media/subtitle outputs.

**These acquisition techniques are upstream work, not an invention of Review Map.** The bridge in `scripts/acquire.py` is independently written orchestration: it selects an installed executor, chooses a read/download mode, records a run and hands captured evidence to the place workflow. It does not implement or vendor the platform scraping code.

Interface reference inspected for this release: **`6e0c0ae43b5fd168040b8eb5193392e47b6f6301`**. Offline tests use a fake executor; no live capture is claimed by those tests.

The upstream repository uses a [Personal Learning and Non-Commercial Use License](https://github.com/mcncarl/yichen-skills/blob/6e0c0ae43b5fd168040b8eb5193392e47b6f6301/LICENSE), not MIT. Its executors, skill instructions and dependencies are installed separately and are not redistributed in this project. Its use terms remain independent of the MIT license covering Review Map's original code.

本项目确实使用过 yichen-skills 的相关采集能力，尤其是抖音视频获取；不把上游方法包装成自研。开源部分包括独立适配代码、来源版本与证据管理、地点交接、匹配校对和地图点评产品。上游采集代码、Skill 指令与个人获取产物均未打包，具体许可以上游文件为准。

## Place workflow and application

Review Map integrates source registration and place handoff from the author's LLM Wiki workflow with AMap matching, calibration, the map interface and the personal review service. The public repository starts from a clean export and contains synthetic examples rather than the author's collection, archives, calibration history, database or production configuration.

Place extraction is agent-assisted or manually authored using `prompts/extract-places.md`; it is not presented as a proprietary video recognition model. Optional OCR or ASR outputs are inputs to the evidence contract, not bundled OCR/ASR implementations.

## Runtime and visual components

| Component | Use | License / reference |
| --- | --- | --- |
| MapLibre GL JS 4.7.1 | Map renderer | BSD notices: `web/assets/licenses/MapLibre.LICENSE.txt` |
| OpenFreeMap / Positron | Basemap style, tile service | MIT / BSD-3 code and CC-BY-4.0 style design; `web/assets/licenses/OpenFreeMap-Styles.LICENSE.txt` and `Positron.LICENSE.txt` |
| OpenMapTiles / OpenStreetMap | Map data and attribution | [OpenMapTiles](https://openmaptiles.org/), [OSM copyright](https://www.openstreetmap.org/copyright) |
| gcoord 1.0.7 | GCJ-02 → WGS84 display conversion | MIT: `web/assets/vendor/gcoord.LICENSE` |
| Instrument Serif | Display typography | SIL OFL: `web/assets/licenses/InstrumentSerif.OFL.txt` |
| Newsreader | Editorial text | SIL OFL: `web/assets/licenses/Newsreader.OFL.txt` |
| Inter | Interface text | SIL OFL: `web/assets/licenses/Inter.OFL.txt` |
| IBM Plex Mono | Metadata | SIL OFL: `web/assets/licenses/IBMPlexMono.OFL.txt` |
| AMap Web Service | POI search and address geocoding | [AMap documentation](https://developer.amap.com/api/webservice/guide/api/search); users supply their own key |

Positron is derived from CartoDB Basemaps, designed by Stamen and Paul Norman for CartoDB, and maintained through OpenMapTiles/MapTiler and OpenFreeMap (Zsolt Ero). Review Map recolors the basemap to a paper palette, declutters labels and prefers Chinese labels. The map corner links to these style credits. Original [style notices](https://github.com/hyperknot/openfreemap-styles/blob/main/LICENSE.md) and the [CC-BY-4.0 design license](https://creativecommons.org/licenses/by/4.0/) remain applicable.

The standalone HTML builder includes the bundled runtime/font/style notices in an inert template. Service terms for external data providers are not replaced by this repository's code license.
