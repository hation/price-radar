# CLI 命令行使用指南（pr.py）

项目内置轻量命令行入口 `pr.py`（仓库根目录），无需启动 Web 服务即可按关键词爬取、管理任务、查询历史走势。输出默认对齐表格，`--json` 切换结构化 JSON。

依赖条件：Python 3.10+，项目依赖已安装（`pip install -r requirements.txt`）。

## 命令总览

```bash
python pr.py --crawl KEYWORD [--platform PLATFORM] [--pages N] [--mode ai|keyword] [--json]
python pr.py --task list | create | start | stop | delete
python pr.py --trend KEYWORD [--days N] [--export PATH] [--json]
python pr.py --help
```

`--crawl` / `--task` / `--trend` 三选一（互斥，必选其一）。

## 参数速查

| 参数 | 说明 | 默认 |
|---|---|---|
| `--crawl KEYWORD` | 按关键词爬取并落库 | - |
| `--task ACTION` | 任务管理动作：list/create/start/stop/delete | - |
| `--trend KEYWORD` | 查询关键词历史价格走势 | - |
| `--platform` | 平台：goofish/jd/taobao/1688，未知值回落闲鱼 | `goofish` |
| `--pages` | 爬取页数 | `3` |
| `--mode` | crawl 模式：`ai` / `keyword`（keyword 纯采集，不依赖 AI） | `keyword` |
| `--json` | 结构化 JSON 输出 | 关闭 |
| `--days` | 走势窗口天数 | `30` |
| `--export PATH` | trend 导出 CSV 路径 | 无 |
| `--name` / `--keyword` | task create 的任务名与关键词（必填） | - |
| `--id` | task start/stop/delete 的任务 ID | - |

## 按关键词爬取

```bash
# 纯采集 + 落库（默认），结果输出表格
python pr.py --crawl "iphone 15" --pages 3

# 结构化 JSON 输出
python pr.py --crawl "iphone 15" --json

# AI 模式：需该关键词的分析标准文件 prompts/<keyword>_criteria.txt
python pr.py --crawl "三星/SK 64G5600" --mode ai
```

说明：
- 每次爬取都会写入结果并积累价格快照，供 `--trend` 查询。
- 当前采集管线为纯抓取；AI 分析由任务运行管线执行（`--mode ai` 仅校验分析标准文件存在）。
- 闲鱼（goofish）爬取前自动探测 CDP 专用 Chrome（端口 9222），未启动会打印 macOS 启动命令。

## 任务管理

```bash
python pr.py --task list                                  # 查看所有任务
python pr.py --task create --name "xxx" --keyword "xxx" --pages 3   # 创建（keyword 模式）
python pr.py --task start --id 0                          # 终端前台运行任务（Ctrl+C 中断）
python pr.py --task stop --id 0                           # 清理任务运行状态标记
python pr.py --task delete --id 1                         # 删除任务
```

说明：
- 与 Web UI 共用同一套 SQLite 任务数据（`data/app.sqlite3`），两边操作互通。
- `--task create` 默认创建 keyword 模式任务（不依赖 AI key / 分析标准）。
- `--task stop` 仅清理运行状态标记；若任务由 Web 服务进程启动，需在 Web UI 停止对应进程。

## 历史走势查询

```bash
python pr.py --trend "iphone 15" --days 30                # 表格：每日最低/均价/最高价
python pr.py --trend "iphone 15" --export trend.csv --json  # 导出 CSV 且输出 JSON
```

说明：
- 数据来自每次爬取（`--crawl` 或任务运行）记录的价格快照（默认保留 30 天，`PRICE_SNAPSHOT_RETENTION_DAYS` 控制）。
- `--trend` 按关键词精确匹配快照，空格/斜杠不一致会查不到；用同一关键词执行 `--crawl` 后查询即可闭环。

## 注意事项

1. **闲鱼 CDP Chrome**：`--crawl` / `--task start` 前自动探测 `http://127.0.0.1:9222`。未启动时按提示执行：
   ```
   "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
     --remote-debugging-port=9222 \
     --user-data-dir=/Users/xingan/Documents/software/aiengine/price-radar/state/cdp-chrome-profile
   ```
   启动后需在 Chrome 中登录闲鱼一次（登录态持久化在 `state/cdp-chrome-profile/`）。
2. **其他平台**（jd/taobao/1688）：登录态由平台函数内部处理（`state/<platform>/` 或 `<platform>_state.json`），未配置时会提示。
3. **关键词一致性**：走势/结果按关键词分桶，请保持同一关键词写法一致。

## 相关文件

- 实现：`pr.py`（根目录）
- 单元测试：`tests/unit/test_pr_cli.py`
- 设计文档：`docs/superpowers/specs/2026-10-31-cli-crawler-design.md`
- 实施计划：`docs/superpowers/plans/2026-10-31-cli-crawler.md`
