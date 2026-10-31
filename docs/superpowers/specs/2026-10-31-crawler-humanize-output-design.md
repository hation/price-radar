# 爬虫拟人化抖动 + 搜索结果输出目录重构 设计文档

- 日期：2026-10-31
- 状态：已批准（用户逐节确认）
- 范围：为 price-radar 爬虫增加统一拟人化行为（防机器人识别），并重构搜索结果输出（`--platform all` 一键多平台 + `output/关键词_时间戳/` 目录结构）

## 1. 背景与目标

用户在"希捷"多平台爬取中遇到：
- 1688 触发滑块验证（风控）
- 各平台滚动/点击行为机械（固定距离、固定延迟），易被识别为机器人
- 搜索结果输出分散（手动导 CSV），无统一目录结构

用户确认需求：
- **抖动强度**：中等（滚动 + 鼠标轨迹 + 停留）
- **输出格式**：分平台 CSV + 合并 CSV（含平台字段）+ JSONL
- **触发方式**：`--platform all` 一键多平台，完成后自动建 `output/关键词_yyyymmddhhmm/`
- **入库确认**：爬取结果已入库（result_items + price_snapshots），导出为拷贝

## 2. 方案选型

选 **方案 A：三层结构**：
- 新增 `src/platforms/_human.py`：统一拟人工具
- 新增 `src/services/search_output_service.py`：导出逻辑
- CLI 扩展：`--crawl --platform all`

否决的方案：
- 方案 B（内联在各平台 + CLI）：拟人逻辑重复、导出逻辑难测试
- 方案 C（独立导出脚本）：与 `--platform all` 集成度低

## 3. 拟人化工具（src/platforms/_human.py）

统一封装，替换各平台机械行为：

```
async def human_scroll(page, rounds=1, *, direction=1)
    # 拟人滚动：每轮随机距离(900-1600)、随机速度(steps)、轮间随机暂停(800-2200ms)、
    # 20% 概率反向小幅回滚(模仿人上下扫视)
async def human_move_to(page, locator)
    # 拟人鼠标移动：迁移自 taobao.py 现有 _human_move_to（分段轨迹+随机偏移+随机速度）
async def human_click(page, locator)
    # 拟人点击：移动到目标→随机停留→点击→随机延迟
async def human_pause(page, min_ms=800, max_ms=2200)
    # 随机停留
```

**集成**（4 个平台文件）：
- `goofish_cdp.py`：机械 `mouse.wheel` → `human_scroll`；翻页页码点击 → `human_click`
- `jd.py`：机械滚动 → `human_scroll`；翻页点击前后加 `human_pause`
- `ali1688.py`：机械滚动 → `human_scroll`；翻页 goto 前后加 `human_pause`
- `taobao.py`：本地 `_human_move_to` 改为引用 `_human.py`（消除重复）

## 4. 导出服务（src/services/search_output_service.py）

```
def build_search_output_dir(keyword, now=None) -> str
    # → output/{关键词}_{yyyymmddhhmm}，关键词做文件名安全化

def export_search_results(keyword, items_by_platform) -> str
    # 建目录，写入：
    #   - 分平台 CSV：{关键词}_{platform}.csv（UTF-8-BOM）
    #   - 合并 CSV：{关键词}_merged.csv（含 platform 列）
    #   - 合并 JSONL：{关键词}_merged.jsonl（每行一条记录，含 platform）
```

字段：标题、价格、链接、商品ID、卖家、地区、发布时间、爬取时间、平台（合并文件）。

## 5. CLI 扩展（pr.py cmd_crawl）

- `--platform all`：遍历平台注册表（goofish/jd/taobao/1688），逐个爬取
- 单平台失败（无登录态/滑块）→ 记录原因继续下一个，最终只导出成功的平台
- 全部爬完后：查询该关键词全部平台结果 → `export_search_results` → 打印输出目录路径
- 单平台模式（`--platform goofish` 等）保持现有行为，但**也输出到 output 目录**（保持一致）

**数据流**：
```
--crawl "希捷" --platform all --pages 10
  → 逐平台爬取（各自落库 result_items + price_snapshots）
  → 查 result_items（关键词=希捷，全部平台）
  → export_search_results → output/希捷_202610311030/{分平台CSV, 合并CSV, JSONL}
```

## 6. 入库说明

爬取结果已入库：
- `result_items`：商品结果，按链接去重（UNIQUE(result_filename, link_unique_key)）
- `price_snapshots`：价格快照，每次运行记录（供走势）
导出仅是库数据的拷贝。

## 7. 测试（pytest）

- `_human`：mock page，断言函数调用不抛错、随机行为生效
- `search_output_service`：tmp_path 建目录写文件，断言合并 CSV 含平台列、JSONL 行数正确、目录名格式 `关键词_yyyymmddhhmm`
- CLI `--platform all`：mock `get_scraper`，断言遍历全部平台并调用导出

## 8. 明确不做（YAGNI）

- 完整拟人行为包（页面缩放/切 Tab/点空白）
- 代理池轮换
- 修改 Web UI 输出
- 不重复造轮子：复用现有 `query_result_records` / `build_result_filename` / 平台注册表
