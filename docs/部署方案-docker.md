# Docker 部署方案

监控程序用 Docker 部署，**数据库使用外置 PostgreSQL**（独立部署，不在 Docker 内），配置完全走宿主 `.env` 的 `DB_DSN`。

## 架构

```
┌──────────────┐    WSS 8501-8506    ┌──────────────┐   psycopg   ┌──────────────┐
│ 斗鱼 CDN     │ ──────────────────► │ monitor 容器  │ ──────────► │ 外置 PostgreSQL │
│ danmuproxy   │                     │ (python)      │             │ (任意主机)     │
└──────────────┘                     └──────────────┘             └──────────────┘
        │   logs/ 挂载到宿主机
```

## 前置条件

- Docker Desktop（Windows/Mac）或 docker（Linux）
- 一台可访问的外置 PostgreSQL（>= 15），已执行 `sql/schema.sql` 建表
- 仓库根目录有 `.env`，其中 `DB_DSN` 指向外置库

## 文件说明

| 文件 | 作用 |
|---|---|
| `Dockerfile` | Python 3.12 slim，非 root 运行，时区 Asia/Shanghai，pip 走清华镜像 |
| `.dockerignore` | 排除 `.env`、`.venv`、日志等敏感/无用文件进镜像 |
| `docker-compose.yml` | 仅 monitor 一个服务，配置经 `env_file: .env` 注入 |

## 快速开始

```powershell
# 1. 准备配置（.env 里填房间号和数据库连接串）
copy .env.example .env
# 编辑 .env：
#   ROOMS=12598324
#   DB_DSN=postgresql://user:pass@host:5432/dbname
#   （不要填 127.0.0.1/localhost——容器里访问不到宿主本机，用局域网 IP 或域名）

# 2. 在外置库执行建表 SQL（首次）
psql -h <db-host> -U <user> -d <dbname> -f sql/schema.sql

# 3. 启动
docker compose up -d --build

# 4. 查看日志
docker compose logs -f monitor
```

## 配置

- `.env` 中的所有变量（`ROOMS`、`DB_DSN`、`BATCH_SIZE`、`FLUSH_INTERVAL` 等）由 compose 以 `env_file` 注入容器，直接改 `.env` 后 `docker compose up -d` 生效。
- 礼物字典 `gift_catalog` 需要手动导入（镜像内不含 `gift.json`）：
  ```powershell
  docker compose cp gift.json monitor:/tmp/gift.json
  docker compose exec monitor python -m scripts.import_gifts --path /tmp/gift.json
  ```

## 备份与恢复（外置库）

```bash
pg_dump -h <db-host> -U <user> <dbname> > backup.sql
psql -h <db-host> -U <user> <dbname> < backup.sql
```

## 常见问题

1. **监控容器反复重启**：`docker compose logs monitor` 看原因，多为 DB_DSN 连不上（容器内访问不到 `localhost`，需用局域网 IP）或 CDN 握手超时（正常，会自动重连）。
2. **端口范围**：程序只连 8501–8506，不再连 8500。
3. **时区**：容器与日志均为 Asia/Shanghai。
4. **代理环境**：Dockerfile 已用清华 PyPI 镜像；若网络还拦 https，可在 build 前给 Docker Desktop 配代理，或改 `PIP_INDEX_URL`。
