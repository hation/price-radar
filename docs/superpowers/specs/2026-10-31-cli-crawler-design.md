# CLI 爬取工具设计文档

- 日期：2026-10-31
- 状态：已批准（用户逐节确认）
- 范围：为 price-radar 项目新增命令行入口 `pr.py`，支持按关键词爬取、任务管理、历史走势查询、结构化输出

## 1. 背景与目标

现有 CLI（`spider_v2.py`）只能运行**已建好**的任务，无法按关键词即点即爬，也没有结果查看/走势查询能力。用户需要脱离 Web UI 在终端完成：

- 快速试关键词：命令行直接输入关键词爬取
- 给程序调用：输出结构化 JSON/CSV
- 脱离 Web UI：任务管理、结果查看、历史走势都在终端完成

用户已确认需求：
- 场景：快速试关键词 + 给程序调用 + 脱离 Web UI 用
- 功能模块：按关键词爬取、任务管理、历史走势查询、结构化输出（全部 4 项）
- 命令风格：单命令多参数（与 spider_v2 一致）
- 输出：默认对齐表格 + `--json` 切换

## 2. 方案选型

选 **方案 B：新建轻量 CLI 入口 `pr.py`**（根目录，与 `spider_v2.py` 同级）。

- 直接复用 src 服务层（任务仓库、平台注册表、价格历史、结果存储），不依赖 Web 服务运行
- `spider_v2.py` 保持"任务运行器"职责不动（已被定时调度器以 `--task-name` 调用）
- 不新增第三方依赖

否决的方案：
- 方案 A（扩展现有 spider_v2.py）：职责混杂，爬取与任务运行参数堆叠
- 方案 C（CLI 转发本机 HTTP API）：必须服务在跑，与"脱离 Web UI"冲突

## 3. 命令界面

```
# 按关键词爬取（默认 keyword 模式，不依赖 AI key；统一落库积累价格快照）
python pr.py --crawl "三星/SK 64G5600" [--platform goofish] [--pages 3] [--mode ai] [--json]

# 任务管理（与 Web UI 共用 SQLite 同一套任务）
python pr.py --task list
python pr.py --task start <id>     # 终端前台跑已有任务
python pr.py --task stop <id>
python pr.py --task delete <id>
python pr.py --task create --name "xxx" --keyword "xxx" --pages 3 [--platform goofish]

# 历史走势查询（复用价格快照）
python pr.py --trend "三星/SK 64G5600" [--days 30] [--export out.csv] [--json]

# 全局
--json：结构化输出（机器可解析）；默认输出对齐表格
```

要点：
- `--crawl` 默认 `keyword` 模式：快速试词不需要 AI key 和 criteria 文件；`--mode ai` 才走 AI 分析（criteria 缺失时明确提示，不静默）
- `--crawl` 统一落库（含价格快照）：为 `--trend` 积累数据。**已去掉 `--no-save`**（用户确认），"只看不存"用 `--json` 输出满足
- `--platform` 未知值自动回落闲鱼（复用 `normalize_platform_key`）
- `--task start` 在终端前台运行，实时输出日志

## 4. 架构

```
pr.py（新增，根目录）
├── _parse_args()          # argparse 单命令多参数
├── cmd_crawl(args)        # 构造临时 keyword 任务 → 登录态检查 → 平台爬虫 → 输出
├── cmd_task(args)         # list / start / stop / delete / create（复用 SqliteTaskRepository）
├── cmd_trend(args)        # load_price_snapshots + build_price_history_insights → 输出
├── _render_table()        # 标准库文本对齐，无第三方依赖
└── _print_json()          # json.dumps 输出
```

复用现有模块：
- `src.infrastructure.persistence.sqlite_task_repository.SqliteTaskRepository`：任务 CRUD
- `src.platforms.get_scraper / normalize_platform_key / platform_requires_login`：平台分发与登录态
- `src.services.price_history_service.load_price_snapshots / build_price_history_insights`：走势
- 平台函数 `scrape_*`：抓取与落库（内部调用 `persist_platform_items`）

## 5. 数据流

- `--crawl`：临时构造 `{keyword, platform, max_pages, task_name, decision_mode}` 任务配置 → 登录态检查（未登录打印启动提示并退出）→ `get_scraper(platform)(config)` 抓取并落库 → 读回本次结果 → 表格/JSON
- `--trend`：`load_price_snapshots(keyword)` → `build_price_history_insights` → 每日 min/avg/max 行 → 表格/JSON/CSV 导出
- `--task`：直连 `SqliteTaskRepository`（与 Web UI 同一份数据）

## 6. 错误处理

- 无关键词 / 未知 task 动作 → 打印 usage 退出
- 平台未登录（如闲鱼 CDP 9222 未启动）→ 打印 macOS 启动命令提示（含 `--remote-debugging-port=9222` 与 `--user-data-dir`）
- `--mode ai` 缺 criteria 文件或 API key → 明确提示而非静默跳过
- 任务 id 不存在 → 友好报错

## 7. 测试

pytest，遵循现有 `tests/` 结构，命名 `tests/unit/test_pr_cli.py`：

- 参数解析：`--crawl`/`--task`/`--trend` 各组合、缺参报错
- 表格渲染：对齐输出、空列表、`--json` 切换
- `--trend` 返回结构：mock 快照数据，验证 daily_trend 字段
- `--task` CRUD：临时 SQLite 下 list/create/delete
- 爬取类不做网络测试（依赖 CDP Chrome），真实抓取由用户手动验证

## 8. 明确不做（YAGNI）

- 不落库的爬取模式（去掉 `--no-save`）
- 交互式菜单
- 新第三方依赖（不用 rich/click）
- 修改 `spider_v2.py` 行为
