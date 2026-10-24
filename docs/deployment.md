# Deployment / 部署

Run the generated map and Python review service together. Static hosting alone supports browsing but cannot save reviews.

## Local

```bash
python3 scripts/demo.py
python3 scripts/build_single_file.py
python3 scripts/set_password.py
python3 scripts/serve.py --host 127.0.0.1 --port 8765
```

There is no default password. To change an existing one, use `scripts/set_password.py --replace`; it revokes sessions without replacing reviews.

## Server

1. Prepare the place data and run tests/build/validation locally.
2. Copy the required runtime: `scripts/serve.py`, `scripts/set_password.py`, `VERSION`, `dist/`, and `data/generated/places-data.js`. The matching key, captures, original notes and API caches are not needed by the runtime.
3. Keep the review database in a persistent private directory outside release folders. Use `--db /var/lib/review-map/reviews.sqlite3`.
4. Set the password interactively on the server before exposing the application. Do not put it in a shell argument, front-end script or service file.
5. Run behind HTTPS with `--secure-cookie`. Adapt `deploy/review-map.service.example` and the Nginx location snippet to your host.

The standard-library server is designed for this small single-writer application. Put TLS, access logging and process management in the reverse proxy/service layer. It serves named routes rather than exposing the project directory.

## Updates and backups

Keep stable place IDs. Build new HTML without touching the database; restart the process after a dataset change so accepted IDs reload. Back up SQLite using its backup API before updates, then stage and verify the new release before changing the active release link.

Rolling back frontend code should not restore an old review database over newer reviews. Keep raw acquisition and matching operations on the local workstation if you only need public map/review hosting.

## 中文说明

地图静态文件与点评服务需要一同部署；浏览器只写当前站点的 API。密钥用于本地高德匹配，不进入浏览器构建；服务器运行不需要来源归档、原始收藏或缓存。数据库放在 release 目录之外，更新页面时不覆盖它。

先在服务器交互设置密码，再通过 HTTPS 代理服务，并开启 `--secure-cookie`。修改密码会撤销会话，不会删除评价。更新前使用 SQLite backup 备份；回退前端版本不应覆盖更新后的点评。
