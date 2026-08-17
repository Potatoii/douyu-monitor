# douyu-monitor

斗鱼直播间礼物监控工具。通过 WebSocket 连接斗鱼弹幕服务器（WSS，端口 8501–8506），实时解析礼物消息（dgb），去重后写入 PostgreSQL，并同步记录礼物名、鱼翅价、人民币价值与来源 CDN 端口。

## 功能

- 同时监控多个直播间（每直播间 6 个 CDN 端口连接，断线自动指数退避重连）
- 礼物消息解析：`gfid` 礼物 ID、数量、送礼/收礼用户、礼物名（`gfn`）
- 按 `message_id` 去重，批量写入（BATCH_SIZE=50 / 2s 刷新）
- 价值换算：基于本地 `gift.json` 字典导入的 `gift_catalog`（鱼翅 + 人民币两套价格）
- 日志四通道：`logs/raw`（原始消息）、`logs/gift`（礼物明细）、`logs/system`、`logs/error`，JSONL 按天轮转
- 支持 Docker Compose 一键部署（PostgreSQL + 监控）

## 架构

```
斗鱼 CDN (WSS 8501-8506)
      │
      ▼
DanmuConnection ──► GiftMonitor ──► 去重 (Deduper) ──► 批量入库 (psycopg pool)
      │                  │
      └── 原始日志        └── 礼物日志（含 port/价格）
```

## 快速开始（Windows 本地）

### 1. 环境

- Python 3.10+（开发验证于 3.14）
- PostgreSQL（>= 15，建库后执行 `sql/schema.sql`）

### 2. 安装

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 配置

```powershell
copy .env.example .env
```

编辑 `.env`：

```ini
ROOMS=12598324              # 直播间 ID，逗号分隔支持多个
DB_DSN=postgresql://user:pass@host:5432/dbname
BATCH_SIZE=50
FLUSH_INTERVAL=2.0
```

导入礼物字典（可选，价值换算需要；`gift.json` 从斗鱼客户端/网页获取，价格为"分"）：

```powershell
python -m scripts.import_gifts   # 将 gift.json 导入 gift_catalog（价格 ÷100 → 元）
```

### 4. 运行

```powershell
python -u main.py
# 或指定房间（会与 .env 合并）：
python -u main.py --room 12598324
```

> 注意：Windows 上 psycopg 需 SelectorEventLoop，代码已内置（`loop_factory=asyncio.SelectorEventLoop`），直接运行即可。

### 5. 测试

```powershell
python -m pytest tests
```

## Docker 部署

见 [docs/部署方案-docker.md](docs/部署方案-docker.md)。数据库使用外置 PostgreSQL（不在 Docker 内），配置走 `.env` 的 `DB_DSN`。

```powershell
copy .env.example .env    # 填 ROOMS 和 DB_DSN（外置库）
docker compose up -d --build
docker compose logs -f monitor
```

## 数据表

- `gift_events` — 礼物事件（已去重，含 message_id、房间、用户、礼物、数量、价格、价值、来源端口、时间）
- `gift_catalog` — 礼物字典（gift_id → 名称、鱼翅价、人民币价）

## 礼物字典来源

`gift_catalog` 数据来自以下接口/文件（`scripts/` 下对应导入脚本，幂等 upsert）：

| 来源 | URL | id_type | 脚本 |
|------|-----|---------|------|
| 本地缓存字典 | `gift.json`（仓库内） | gfid/pid/pgid | `import_gifts.py` |
| 房间礼物列表 | `https://gift.douyucdn.cn/api/gift/v5/web/list?rid=<rid>` | gfid | `fetch_gifts.py` |
| 七夕活动配置 | `https://wconf.douyucdn.cn/resource/common/activity/actqx202608_w.json` | gfid/pid | `fetch_activity_gifts.py` |
| 潘多拉开奖表 | `https://www.douyu.com/japi/interact/comm/pandora/config?rid=<rid>` | pid | `fetch_activity_gifts.py` |
| 礼物图鉴 | `https://wconf.douyucdn.cn/resource/common/giftPhotos_w.json` | pgid | `fetch_gift_photos.py` |

价格单位：接口返回"分"，入库时 ÷100 存"元"（`price_yu`/`value_rmb`）。同一礼物可能有多个 ID 命名空间（gfid/pid/pgid），不同来源同名礼物价格可交叉验证（如七夕礼物 gfid 与图鉴 pgid 价格一致）。

## 日志

```powershell
# 实时看礼物
Get-Content logs\gift\2026-07-31.jsonl -Wait
```

每行 JSON 含 `record.extra`（stream/room_id/port/msg_id）与消息体（gift_id、gift_count、port、价格等）。

## 目录结构

```
config/      环境配置 (pydantic-settings)
core/        WebSocket 连接、斗鱼协议编解码、消息解析、日志
monitor/     监控主逻辑（多连接、消费批量入库）
dedup/       消息去重
services/    价值换算
storage/     数据库连接池与仓储
scripts/     礼物字典导入、价值回填
sql/         建表 SQL
docs/        部署与开发文档
tests/       pytest 测试
```
