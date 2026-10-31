# Repository Guidelines

## 项目结构与模块组织
- 后端位于 `src/`，入口 `src/app.py`，API 路由在 `src/api/routes/`，服务层在 `src/services/`，领域模型在 `src/domain/`，基础设施在 `src/infrastructure/`。
- 前端在 `web-ui/`（Vue 3 + Vite），视图放于 `web-ui/src/views/`，组件在 `web-ui/src/components/`，构建产物会复制到根目录 `dist/`。
- 测试位于 `tests/`，命名遵循 `test_*.py` 或 `tests/*/test_*.py`。
- 运行数据与资源：`prompts/`、`jsonl/`、`logs/`、`images/`、`static/`、`state/`，配置文件 `config.json` 与 `.env` 位于仓库根目录。

## 构建、测试与本地开发
- 后端开发：`python -m src.app` 或 `uvicorn src.app:app --host 0.0.0.0 --port 8000 --reload`。
- 爬虫任务：`python spider_v2.py --task-name "MacBook Air M1" --debug-limit 3`（可用 `--config` 指定自定义配置）。
- 前端开发：`cd web-ui && npm install && npm run dev`；构建：`cd web-ui && npm run build`（产物复制到根目录 `dist/`）。
- 一键本地启动：`bash start.sh`（自动安装依赖、前端构建并启动后端）。
- Docker：`docker compose up --build -d`，查看日志 `docker compose logs -f app`，停止 `docker compose down`。

## CLI 命令速查（pr.py）
仓库根目录的 `pr.py` 是轻量命令行入口，无需启动 Web 服务即可爬取/管理任务/查走势。详细文档见 `docs/cli.md`。

```bash
python pr.py --crawl KEYWORD [--platform PLATFORM] [--pages N] [--mode ai|keyword] [--json]   # 按关键词爬取并落库（积累价格快照）
python pr.py --task list|create|start|stop|delete                                            # 任务管理（与 Web UI 共用同一 SQLite）
python pr.py --trend KEYWORD [--days N] [--export PATH] [--json]                             # 历史走势（每日最低/均价/最高价）
python pr.py --help                                                                          # 参数速查
```

- `--crawl`/`--task`/`--trend` 三选一互斥；`--platform` 未知值回落闲鱼；默认表格输出，`--json` 切 JSON。
- 闲鱼爬取前自动探测 CDP 专用 Chrome（9222 端口），未启动会打印 macOS 启动命令；登录态持久化于 `state/cdp-chrome-profile/`。
- `--trend` 按关键词精确匹配快照，空格/斜杠不一致会查不到，需与 `--crawl` 使用同一关键词。

## 快捷触发词（用户短句 → 自动展开的完整行为）
**完整速查文档见 `docs/quick-commands.md`（务必读取）。** 当用户说「爬取 X 数据」（如「爬取希捷数据」），默认展开为多平台前 10 页爬取与汇总：
1. 执行：`python pr.py --crawl "X" --pages 10 --platform all`（闲鱼/京东/淘宝/1688 全部平台）
2. 平台未登录导致失败时：跳过该平台并说明原因，继续其余平台
3. 爬完后检查 `output/` 下最新文件夹，确认有分平台 CSV、合并 CSV（含 platform 列）、JSONL
4. 向用户汇报：合并 CSV 完整路径 + 各平台抓到多少条
其他触发词（查走势/看任务/要 CSV）与使用前提（CDP Chrome、登录态）见 `docs/quick-commands.md`。

## 编码风格与命名约定
- 保持分层：API → services → domain → infrastructure，避免跨层耦合，模块保持精简。
- Python 测试函数命名为 `test_*`，文件与路径遵循上述测试目录规范。
- 使用描述性、任务导向的命名（如爬虫任务名、配置键），与业务含义对应。

## 架构与运行时
- 后端使用 FastAPI 提供 API 与静态资源，爬虫与 AI 推理在独立任务进程中协作，前后端通过 HTTP/Web UI 交互。
- 任务运行会在 `jsonl/` 写入结果、在 `logs/` 留存运行日志、在 `images/` 下载图片，前端监控页面依赖这些数据。
- 默认监听 8000 端口，前端构建后静态文件可由后端或 Docker 镜像直接提供。

## 测试指南
- 测试框架：`pytest`（默认同步测试，无需 `pytest-asyncio`）。
- 运行全部测试：`pytest`；覆盖率：`pytest --cov=src` 或 `coverage run -m pytest`；定向测试：`pytest tests/test_utils.py::test_safe_get`。
- 优先覆盖核心服务、爬虫管道的异常分支与重试逻辑，避免回归。
- PR 前请运行相关测试，新增逻辑补充针对性用例。

## 提交与 PR 规范
- Commit 采用类 Conventional Commits：`feat(...)`、`fix(...)`、`refactor(...)`、`chore(...)`、`docs(...)` 等。
- PR 需说明变更范围与影响模块；UI 变更在 `web-ui/` 提供截图；关联相关 Issue；提及配置或迁移步骤。

## 安全与配置提示
- 复制 `.env.example` 为 `.env`，设置必填项 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL_NAME` 等。
- 不要提交真实凭据或 cookies（如 `state.json`）；Playwright 需本地浏览器，Docker 镜像已预装 Chromium。
- Web 认证默认 `admin/admin123`，生产环境务必修改，推荐启用 HTTPS 并限制访问来源。
