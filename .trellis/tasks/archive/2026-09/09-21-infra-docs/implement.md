# infra-docs 执行计划

## Step 1. 根文件
- `.gitignore`（node_modules/.next/__pycache__/*.db/.env/.trellis/.runtime）
- `.env.example`
- `Makefile`
- `README.md`

## Step 2. docker-compose.yml
- 按 `技术设计.md` §68 完整写 7 服务；健康检查、volumes、depends_on

## Step 3. backend/Dockerfile
- python:3.12-slim + requirements + uvicorn CMD

## Step 4. frontend/Dockerfile
- node:20-alpine multi-stage（builder → runner standalone）

## Step 5. 校验
- Python yaml.safe_load 校验 compose YAML 结构 + 服务完整性断言
- 检查 .env.example 键与 compose/backend config 对齐
- 静态 review Dockerfile