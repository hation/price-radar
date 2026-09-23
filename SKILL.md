---
name: price-radar
description: 多平台商品比价与盯价系统——丢一个关键词(如"vivo X Fold5"),自动采集淘宝/京东/1688/闲鱼四平台行情,跨平台比价+同款识别(配件过滤),历史价格查询(慢慢买),价格跌破目标价自动推飞书。触发场景:比价/查价/历史价格/蹲降价/这个多少钱买合适/watch 价格/多平台价格对比。
created: 2026-09-23
platforms: 淘宝 · 京东 · 1688(CDP 实时采集)+ 闲鱼(可选)+ 慢慢买(历史价/间接价)
---

# price-radar · 多平台比价与盯价

## 它能干什么

| 能力 | 命令 | 说明 |
|------|------|------|
| 全网比价 | `python scripts/compare_price.py "关键词"` | 汇总已采集行情→同款识别(配件过滤)→价格对比报告(先采集落库,见第 4 步) |
| 历史价格 | `python scripts/watch_price.py now <商品URL>` | 任意商品链接→慢慢买历史价曲线数据 |
| 盯价提醒 | `python scripts/watch_price.py add <URL> <目标价>` | 跌破目标价自动推飞书 |
| 定时轮询 | `watch_price.py check` 配计划任务/cron | 每天查一轮,跌破才推,平时静默 |
| Web 控制台 | `python desktop_launcher.py` | 配采集任务/看行情/AI 分析(高级) |

## 首次使用(六步,约 15 分钟)

### 第 0 步:安装依赖

```bash
pip install -r requirements.txt
playwright install chromium
```

复制 `.env.example` → `.env`,按需填:
- `WEBHOOK_URL`(飞书群机器人 webhook,盯价提醒用;不填则盯价结果只在命令行显示)
- `OPENAI_API_KEY` / `OPENAI_BASE_URL`(仅 Web 控制台的 AI 商品分析用;**命令行比价/盯价不需要**,可不填)

### 第 1 步:启动专用 Chrome(所有平台共用的登录容器)

Windows PowerShell:
```powershell
Start-Process chrome -ArgumentList '--remote-debugging-port=9222','--user-data-dir=<项目目录>\state\cdp-chrome-profile'
```

这是**独立数据目录的 Chrome**,与你日常用的 Chrome 互不干扰。采集全部走"CDP 接管"模式——脚本操作这个真 Chrome,最大程度降低被平台误判为自动化程序的概率。**它保持开着即可**,不用时关掉也无妨,登录态存在本地 profile 里。

### 第 2 步:逐平台登录(每个平台一次性,之后免登录)

在**上面那个专用 Chrome** 里依次打开并登录(账号自选,建议用小号):

| 平台 | 操作 | 登录态 |
|------|------|--------|
| ① 淘宝 | 打开 `taobao.com` 扫码登录 | 之后 1688/闲鱼**自动继承**,不用重复登 |
| ② 京东 | 直接在专用 Chrome 里打开 `jd.com` 登录(推荐);或跑 `python scripts/login_capture.py jd` 另存 cookie | 两条路线代码都支持,前者免维护第二套登录态 |
| ③ 1688 | 淘宝登录后打开 `1688.com` 验证一下(通行证自动跳工作台=已登录) | 继承淘宝 |
| ④ 慢慢买 | 跑 `python scripts/capture_manmanbuy_auth.py`,弹窗微信扫码 | state/manmanbuy_browser.json |

> 慢慢买是历史价格数据源,盯价功能必配。**授权绑定扫码账号**:后续"京东授权"弹层要用**同一个微信登录的慢慢买 App** 扫(授权过期跑 `python scripts/manmanbuy_auth_qrcode.py` 重新弹码;若反复失败说明会话本身失效,重跑本步④重新扫码)。

### 第 3 步:配飞书提醒(可选,盯价需要)

飞书群 → 设置 → 群机器人 → 添加自定义机器人 → 复制 Webhook 地址 → 填入 `.env` 的 `WEBHOOK_URL`。

### 第 4 步:先采集落库,再比价

比价引擎读的是**采集落库的行情快照**——没有采集数据,比价输出会是"暂无数据"。两条路任选:

```bash
# 路线 A:Web 控制台建采集任务(推荐,可视化配置)
python desktop_launcher.py    # 浏览器打开后建关键词任务,手动触发一轮采集

# 路线 B:命令行跑任务(任务在 config.json 或控制台已建好后)
python spider_v2.py --task-name "你的任务名"
```

### 第 5 步:首跑验证

```bash
# 比价(汇总第 4 步采集到的行情)
python scripts/compare_price.py "iPhone 15"

# 盯价(走慢慢买历史价,不依赖第 4 步,仅需第 2 步④授权)
python scripts/watch_price.py add "https://item.jd.com/1000xxxx.html" 5999 "iPhone 15"
python scripts/watch_price.py check
```

> 闲鱼行情为可选项:比价引擎默认读 `XIANYU_EXTERNAL_DB` 指向的外部闲鱼监控器库(见 .env.example);未配置时闲鱼一路自动跳过,淘宝/京东/1688 不受影响。

### 第 6 步:定时轮询(可选)

Windows 计划任务示例(每天 10:07 查一轮盯价,跌破才推飞书):
```powershell
schtasks /Create /TN "PriceWatch" /SC DAILY /ST 10:07 /TR "python <项目目录>\scripts\watch_price.py check"
```

## 命令速查

```bash
python scripts/compare_price.py "关键词"              # 全平台比价
python scripts/compare_price.py "关键词" jd,taobao    # 指定平台
python scripts/watch_price.py add <URL> <目标价> [备注] # 加盯价
python scripts/watch_price.py list                    # 盯价列表
python scripts/watch_price.py check                   # 查一轮,跌破推飞书
python scripts/watch_price.py now <URL>               # 查某商品历史价
python scripts/watch_price.py rm <URL>                # 删盯价
python scripts/login_capture.py <平台>                 # 补登录态(jd/taobao/goofish/1688)
python desktop_launcher.py                            # Web 控制台(配任务/看行情)
```

## 高级:采集任务与调度

- `python spider_v2.py --help`:批量采集任务(任务在 Web 控制台或 config.json 配置)
- Web 控制台(`desktop_launcher.py`)支持:多任务管理 / 采集调度 / AI 商品分析 / 行情快照 / 消息推送(飞书/TG/Bark/邮件等十余种渠道,见 .env.example)
- 比价引擎读取采集落库的行情快照,采集越多比价越准

## 平台风控纪律(实测教训,务必遵守)

1. **反爬拦截 ≠ 登录失效**:弹滑块/扣数据=浏览器指纹问题(CDP 模式已解决);只有明确"请登录"才是登录态问题。别反复重登。
2. **1688 风控敏感**:连续自动化查询必触发拦截,采集频率应保持**每天最多一次**(此为使用纪律,代码不做强制,靠调度安排);命中拦截人工过一次滑块即可恢复。
3. **淘宝必须拟人操作**:脚本已内置行为链(鼠标轨迹+逐字打字),不要改走直连搜索 URL,会被强制验证。
4. **卡住先人工确认**:连续两次失败,先自己打开专用 Chrome 手动操作验证平台是否正常,再排查脚本。

## 隐私与安全

- 登录态全部存本地 `state/`,`.gitignore` 已排除,**绝不入库上传**
- 密钥只放 `.env`(同样被排除)
- 脚本只做只读采集(搜索/浏览),不下单、不改账号数据

## 免责声明

本项目仅供个人学习与价格研究,采集行为请遵守各平台服务条款,控制频率,尊重平台反爬机制。商用风险自负。
