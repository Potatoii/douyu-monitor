# Docker 部署方案

监控程序 + PostgreSQL 用 Docker Compose 一键部署，数据存在命名卷，日志映射到宿主机 `logs/` 目录。

## 架构

```
┌──────────────┐    WSS 8501-8506    ┌──────────────┐   psycopg   ┌──────────────┐
│ 斗鱼 CDN     │ ──────────────────► │ monitor 容器  │ ──────────► │  db 容器      │
│ danmuproxy   │                     │ (python)      │             │ postgres:17  │
└──────────────┘                     └──────────────┘             └──────────────┘
        │   logs/ 挂载到宿主机，gift.json 字典灌入 gift_catalog
```

## 前置条件

- Docker Desktop（Windows/Mac）或 docker + docker compose（Linux）
- 仓库根目录有 `.env`（配置房间号；无则从 `.env.example` 复制）
- 首次构建需要能访问外网拉镜像和 pip 依赖

## 文件说明

| 文件 | 作用 |
|---|---|
| `Dockerfile` | Python 3.12 slim，非 root 运行，时区 Asia/Shanghai，pip 走清华镜像 |
| `.dockerignore` | 排除 `.env`、`.venv`、日志等敏感/无用文件进镜像 |
| `docker-compose.yml` | db + monitor 两个服务，健康检查依赖启动 |
| `sql/schema.sql` | 首次启动 db 容器时自动建表（幂等） |

## 快速开始

```powershell
# 1. 准备配置（.env 里填要监控的房间号）
copy .env.example .env
# 编辑 .env：ROOMS=12598324

# 2. 启动
docker compose up -d --build

# 3. 查看日志
docker compose logs -f monitor
```

## 配置

- `.env` 中的 `ROOMS`、`BATCH_SIZE`、`FLUSH_INTERVAL` 等由 compose 以 `env_file` 注入容器，直接改 `.env` 后 `docker compose up -d` 生效。
- `DB_DSN` 在 compose 里被显式覆盖为指向 `db` 容器，宿主机 `.env` 里的 DSN 会被忽略。
- 数据库账号密码在 `docker-compose.yml` 的 db 服务里配置，若要修改，需同时改 monitor 的 `DB_DSN`，并删除旧卷重建（见常见问题 4）。

## 数据与备份

- 数据库存于 Docker 命名卷 `pgdata`，删除容器不会丢数据。
- 备份：
  ```powershell
  docker compose exec db pg_dump -U douyu douyu_monitor > backup.sql
  ```
- 恢复：
  ```powershell
  docker compose exec -T db psql -U douyu douyu_monitor < backup.sql
  ```
- 礼物字典 `gift_catalog` 是运行时从 `gift.json` 导入的，容器镜像不包含该文件；如需重建，在 monitor 容器里执行：
  ```powershell
  docker compose exec monitor python scripts/backfill_value.py  # 或重新导入
  ```

## 常见问题

1. **监控容器启动后反复重启**：先看 `docker compose logs monitor`，多为连不上 db（等健康检查）或 CDN 握手超时（正常，会自动重连）。
2. **端口范围**：程序只连 8501–8506，不再连 8500。
3. **时区**：容器与日志均为 Asia/Shanghai。
4. **想换数据库密码**：改 compose 两处（db 环境变量 + monitor 的 DB_DSN）后执行 `docker compose down -v` 重建（会清空数据库，先备份）。
5. **代理环境**：Dockerfile 已用清华 PyPI 镜像；若公司网络还拦 https，可在 build 前给 Docker Desktop 配代理，或改 `PIP_INDEX_URL`。
