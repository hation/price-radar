# 快捷触发词速查

本文件是 price-radar 项目的快捷指令文档。**直接对 Trae 说下面的短句即可**，AI 会按"完整行为"自动执行。详细 CLI 命令见 [cli.md](cli.md)。

## 核心触发词

| 你说 | AI 自动执行的完整行为 |
|---|---|
| **爬取 X 数据**（如「爬取希捷数据」） | 执行 `python pr.py --crawl "X" --pages 10 --platform all`（闲鱼/京东/淘宝/1688 全部平台，各前 10 页）；未登录平台跳过并说明原因；检查 `output/` 最新文件夹（分平台 CSV + 合并 CSV 含 platform 列 + JSONL）；汇报合并 CSV 路径和各平台条数 |
| **爬取 X 数据 N 页**（如「爬取希捷数据 5 页」） | 同上，但页数为 N |
| **查 X 的历史走势**（如「查希捷的历史走势」） | 执行 `python pr.py --trend "X" --days 30`，输出每日最低/均价/最高价走势 |
| **查看任务** | 执行 `python pr.py --task list`，展示全部任务 |
| **把 X 的 CSV 给我** | 读取 `output/` 下 X 关键词最新文件夹的合并 CSV，给出路径链接 |

## 完整行为定义（爬取类）

用户说「爬取 X 数据」时，AI 执行：

1. **执行命令**：`python pr.py --crawl "X" --pages 10 --platform all`
2. **平台容错**：某平台未登录/触发风控（如滑块）→ 跳过该平台并说明原因，继续其余平台
3. **校验产物**：爬完后检查 `output/` 下**最新生成**的文件夹，确认存在：
   - 分平台 CSV（`X_闲鱼.csv` / `X_jd.csv` 等）
   - 合并 CSV（`X_merged.csv`，含 platform 列）
   - 合并 JSONL（`X_merged.jsonl`）
4. **汇报**：合并 CSV 完整路径 + 各平台抓取条数

## 使用前提

- **CDP 专用 Chrome** 需运行（端口 9222），登录态持久化在 `state/cdp-chrome-profile/`：
  ```bash
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
    --remote-debugging-port=9222 \
    --user-data-dir=/Users/xingan/Documents/software/aiengine/price-radar/state/cdp-chrome-profile
  ```
- **各平台登录态**：闲鱼在 CDP Chrome 登录；京东/淘宝/1688 可复用同一 Chrome 登录。未登录的平台会被跳过。

## 常用示例

```
爬取希捷数据
爬取希捷数据 5 页
爬取三星/SK 64G5600 数据
查希捷的历史走势
```

## 相关文件

- CLI 命令详解：`docs/cli.md`
- CLI 实现：`pr.py`
- 输出目录：`output/{关键词}_{yyyymmddhhmm}/`
