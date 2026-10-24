# Review Map

[English](README.md) · [简体中文](README.zh-CN.md)

![Review Map](docs/cover.svg)

**把收藏过的地方，变成可以探索和点评的个人地图。**

Review Map 将信息采集、基于原文证据的地点提炼、高德匹配、人工校对、地图展示和个人评价连成一条工作流。地图铺满视口，地点详情按需展开；出门时可以查看附近收藏，到访后留下 1–5 星评分和文字评价。

信息采集流程使用了 **[mcncarl/yichen-skills](https://github.com/mcncarl/yichen-skills)** 中的 **[yichen-content-archive](https://github.com/mcncarl/yichen-skills/tree/main/yichen-content-archive)**，尤其是抖音视频和小红书笔记执行器。Review Map 提供独立的适配层和后续产品整合，**不将这些采集方法描述为自己的原创技术**。具体来源见 [技术归属](ATTRIBUTION.md)。

## 产品闭环

```text
已知图文 / 视频链接
  → yichen-content-archive 获取元数据、正文或所需媒体
  → Agent 辅助提炼地点，并附原文证据
  → 不可变来源版本与地点暂存批次
  → 高德 POI 查询、评分与分店识别
  → 人工校对：选候选 / 填地址 / 改标签
  → 地图探索 → 个人评分与评论
```

上游采用原 LLM Wiki 的整理方式：保留原始获取结果，为来源分配稳定身份，将“获取成功”与“内容完整”分开记录，再单独交接已确认地点。不属于地点的信息仍可留在自己的 Wiki。

## 功能

- **采集适配**：处理明确给出的抖音视频、小红书笔记链接，默认仅读取元数据和文字，媒体下载单独开启；也可直接导入本地标准化内容。
- **可追溯入库**：不可变来源版本、追加式台账、证据引用、地点去重，以及未确认名称的上游待审队列。
- **地点处理**：高德 Web Service 查询与地理编码，名称和类型评分、分店歧义判断、POI ID 去重、别名与推荐菜合并。
- **电脑校对台**：候选支持多选，“全不对”与候选互斥；可补地址、修改多个标签。操作即时保存至本机浏览器，并导出 JSON。
- **地图展示**：MapLibre/OpenFreeMap、分类图标、聚合、搜索、城市和类别筛选、附近收藏、导航、地点链接、键盘操作和手机布局。
- **个人评价**：公开浏览，登录后写入；评分和评论至少填一项，支持修改、删除、草稿保留和更新冲突检测。SQLite 评价数据与地图构建分离。

## 快速体验

应用与构建只需 **Python 3.10+**。Node.js 用于可选的 JavaScript 语法检查。示例包含四个虚构地点和两条校对练习，无需高德 Key 或采集账号即可启动。

```bash
git clone https://github.com/Immutable1407/review-map.git
cd review-map
python3 scripts/demo.py
python3 scripts/build_single_file.py
python3 scripts/set_password.py
python3 scripts/serve.py
```

打开 **http://127.0.0.1:8765/**。设置密码时输入不会回显，项目不包含默认密码。电脑校对台位于 **http://127.0.0.1:8765/calibrate/**；远程部署时需先在地图上登录。

构建生成 `dist/Review-Map.html` 与 `dist/Calibration-Desk.html`，字体、脚本和数据均已内嵌。底图瓦片仍需联网；保存评价需要 Python 服务，不能只靠双击 HTML。

## 换成自己的收藏

### 1. 获取来源

按照[上游说明](https://github.com/mcncarl/yichen-skills/tree/main/yichen-content-archive)单独安装 `yichen-content-archive`。本项目**不打包其代码**；上游的个人学习、非商业使用许可独立于本仓库 MIT 许可，详见[上游许可证](https://github.com/mcncarl/yichen-skills/blob/main/LICENSE)。

```bash
python3 scripts/acquire.py \
  --url 'https://www.douyin.com/video/<视频ID>' \
  --upstream-skill /path/to/yichen-content-archive \
  --python /path/to/acquisition-env/bin/python
```

抖音调用上游 `douyin_download.py --metadata-only`；小红书调用 `xiaohongshu_fetch.py --skip-media`。确实需要媒体时加 `--download-media`。`--dry-run` 只展示后端和执行模式，不进行获取。

每次执行会在 `data/acquisition/runs/` 创建独立目录，保存本地执行日志与 `capture.json`，记录实际使用的后端、状态和产物。这个适配器不导出私人收藏列表、不搜索更多内容，也不执行语音转写。

### 2. 提炼、登记与交接

让编码 Agent 使用[地点提炼提示](prompts/extract-places.md)，或者自行整理相同结构的 JSON。[examples/intake.json](examples/intake.json) 展示来源正文和状态、稳定 ID、候选地点及原文证据字段。

```bash
python3 scripts/ingest.py path/to/intake.json
python3 scripts/ingest.py path/to/intake.json --deliver
```

第一条命令登记来源版本、暂存已确认地点，并保存待审条目；`--deliver` 还会新增 `raw/YYYY-M-D_update.md` 及逐地点元数据。重复处理相同的已交接内容，不会再生成一份批次。字段、台账和确认规则见[架构说明](docs/architecture.md)。

Agent 可以基于平台正文、字幕或本地 OCR 结果整理输入；下载到视频不等于取得完整口播。名称不确定的条目留在上游待审；名称确认但城市未知的条目进入手填地址流程。

### 3. 高德匹配与人工校对

```bash
cp config/amap-config.example.json config/amap-config.local.json
# 在本地文件填写 webService.key，或设置 AMAP_WEB_SERVICE_KEY。
python3 scripts/build_places.py
python3 scripts/build_single_file.py
```

打开校对台，导出 JSON，放入 `data/reviews/`，然后执行：

```bash
python3 scripts/apply_review_results.py path/to/export.json
python3 scripts/build_single_file.py
python3 scripts/validate.py
```

未填写的条目继续待处理；“全不对”转入地址补充；地理编码失败的地址保留以便重试。重复应用同一份校对结果不会增加重复地点。高德 Web Service Key 只供 Python 使用，地图前端无需高德浏览器 Key。

地点数据变动后重启应用服务，以重新载入允许点评的地点 ID。重建 HTML 不会覆盖评价数据库。

## 目录

```text
scripts/       采集适配、入库、匹配、构建与评价服务
web/           地图前端、校对台、字体和地图运行库
examples/      合成地点、校对案例与标准化输入
prompts/       Agent 辅助提炼地点的输入输出要求
config/        可分发配置模板
deploy/        通用反向代理与服务模板
tests/         离线流程测试与 API 测试
raw/           个人地点交接批次                 [本地]
data/          来源归档、台账、缓存与评价数据库  [本地]
dist/          构建后的单文件页面              [本地]
```

## 开发与部署

```bash
python3 -m unittest discover -s tests -v
python3 scripts/build_single_file.py
python3 scripts/validate.py
git add .
python3 scripts/audit_public.py
```

测试使用合成数据、临时 SQLite 和模拟采集执行器，不依赖联网。`.github/ci.example.yml` 提供可选的 GitHub Actions 模板。实际信息获取依赖独立安装的上游工具，高德匹配使用自己的 Key。托管方式见[部署说明](docs/deployment.md)。

当前产品是单写入者的个人点评工具，不是多账号点评社区。来源归档、收藏、校对进度、密钥和运行数据默认不进入 Git。

## 许可与致谢

Review Map 原创代码采用 [MIT](LICENSE)。可选采集依赖 **yichen-skills / yichen-content-archive**，不在本仓库重新分发。MapLibre、gcoord、OpenFreeMap/OpenMapTiles/OpenStreetMap 与字体保留各自的归属及许可，完整说明见 [ATTRIBUTION.md](ATTRIBUTION.md)。
