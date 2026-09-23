# infra-docs：Docker Compose / 文档

## Goal
交付部署与运维基础设施：docker-compose.yml（postgres+pgvector, redis, minio, backend, worker, frontend）、backend/frontend Dockerfile、.env.example、README、Makefile、.gitignore。本机无 docker，做静态交付与校验。

## Requirements

### docker-compose.yml（`技术设计.md` §68-69）
- postgres: pgvector/pgvector:pg16（DB 名 personalos，healthcheck pg_isready）
- redis: redis:7-alpine（appendonly）
- minio: minio/minio（9000+9001，ROOT 账号 env）
- backend: build ./backend, env(DATABASE_URL postgresql+asyncpg, REDIS_URL, S3_*, LLM_PROVIDER, OPENAI/ANTHROPIC key), port 8000, volume, depends_on healthy
- worker: build ./backend, 同 env, command `python -m app.jobs.worker`
- frontend: build ./frontend, NEXT_PUBLIC_API_URL, port 3000
- volumes：postgres_data, redis_data, minio_data
- 容器间用服务名（postgres/redis/minio/backend），不用 localhost

### Dockerfile
- backend：python:3.12-slim，requirements + COPY .，uvicorn 0.0.0.0:8000
- frontend：node:20-alpine build + standalone run

### 文档
- README.md：快速开始（docker compose up -d / 本地 package 启动两种方式）、目录结构、env 配置说明、API 入口 http://localhost:8000/docs
- .env.example：DATABASE_URL / REDIS_URL / S3 配置 / LLM_PROVIDER / OPENAI_API_KEY / ANTHROPIC_API_KEY / NEXT_PUBLIC_API_URL
- Makefile：dev-up, dev-down, backend-run, backend-install, frontend-run, lint, test, migrate
- .gitignore：node_modules, .next, __pycache__, *.db, .env, .trellis/.runtime, .trellis/workspace (可选)

## Acceptance Criteria
- [ ] docker-compose.yml 语法与缩进正确、服务依赖关系完整（无 docker 时用 `docker compose config` 不能运行，则做 YAML 解析校验）
- [ ] 两个 Dockerfile 编写完整可构建的形态
- [ ] .env.example 覆盖全部关键变量
- [ ] README 有双运行路径说明
- [ ] Makefile 目标齐全
- [ ] .gitignore 正确排除本地产物

## Notes
- 本机无 docker：用 Python yaml 解析校验 docker-compose 结构
- 各服务 env 与 backend core config.py 的字段名对齐