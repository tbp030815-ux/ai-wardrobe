# CLAUDE.md

## 项目概述

AI 智能衣橱 — 用户上传衣物照片，通过 AI 自动抠图入库、上传模特全身照、实现 AI 虚拟试穿和天气感知穿搭推荐。

## 技术栈

| 层级 | 技术 | 备注 |
|---|---|---|
| 前端 | React 18 + Vite 5 + Tailwind CSS 3 + React Router | SPA，不需 SSR |
| 后端 | FastAPI + Uvicorn (Python 3.10) | 异步，AI 能力全走 HTTP 调用 |
| 数据库 | SQLite (aiosqlite) | 单文件，路径 `backend/data/wardrobe.db` |
| 抠图 | rembg (U2-Net 本地推理) | 免费无需 Key，模型 168MB 存于 `~/.u2net/` |
| AI 识别/生成 | 火山方舟 (Volcano Ark) API | Key 存于 `backend/.env` |
| 测试 | pytest + pytest-asyncio（后端）/ vitest + testing-library（前端） | TDD 开发 |

## 环境

- **Python**: 必须用 `C:\Users\tianbaoping\AppData\Local\Programs\Python\Python310\python.exe`（系统默认 python 是 3.7，太旧无法装 FastAPI）
- **虚拟环境**: `backend/venv/`
- **rembg 模型**: `~/.u2net/u2net.onnx`（168MB）。GitHub 直连下载只有 ~12KB/s，用国内镜像：
  ```bash
  curl -L -o ~/.u2net/u2net.onnx "https://gh-proxy.com/https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx"
  ```

## 启动命令

```bash
# 后端 (端口 8000)
cd backend
./venv/Scripts/python.exe -m uvicorn main:app --port 8000

# 前端 (端口 5173)
cd frontend
npm run dev

# 测试
cd backend && ./venv/Scripts/python.exe -m pytest -v
cd frontend && npm test
```

- 前端开发代理：`/api` 和 `/uploads` → `http://localhost:8000`（见 `frontend/vite.config.ts`）
- 后端 API 文档：`http://localhost:8000/docs`

## 目录结构

```
backend/
├── main.py                    # FastAPI 入口，挂载 /uploads 静态目录
├── config.py                  # Settings（读 .env）
├── api/
│   ├── upload.py              # POST /api/upload（抠图 → 识别 → 入库）
│   ├── wardrobe.py            # GET /api/wardrobe, GET /api/clothes/{id}
│   └── recommendation.py      # GET /api/recommendation（天气 + 穿搭推荐）
├── services/
│   ├── background_removal.py  # rembg 本地抠图
│   ├── seedream_client.py     # 火山方舟 API 客户端（识图 + 文本对话）
│   ├── weather.py             # Open-Meteo 天气（免 Key）
│   └── recommendation.py      # 推荐引擎：规则筛选 → LLM 精选 → 降级
├── storage/
│   ├── database.py            # SQLite 连接 & 建表
│   └── clothes_store.py       # 衣物数据访问
├── tests/                     # pytest
├── uploads/                   # 上传图片存储
├── requirements.txt           # 运行时依赖
└── requirements-dev.txt       # 含测试依赖
frontend/
├── src/App.tsx                # 路由框架：/ (今日推荐) /wardrobe (衣柜) /tryon (试穿)
├── src/types.ts               # Clothes 等接口定义
├── src/api/client.ts          # fetch 封装
├── src/pages/                 # Home / Wardrobe / TryOn（Home、Wardrobe 已对接后端）
├── src/components/            # WardrobeGrid
└── vite.config.ts             # 代理 /api + /uploads
PLAN.md                        # 完整技术方案（开发计划、API 设计、数据库表）
```

## 数据库表

- **clothes**: 衣物（image_path 原图、cropped_path 抠图PNG、category/color/style/season/tags）
- **models**: 模特全身照（is_default 默认模特）
- **outfits**: 穿搭记录（model_id + clothes_ids JSON）

## 开发约定

- **TDD**：先写失败的测试，再写实现。后端用 pytest，前端用 vitest
- **API 风格**: REST，路径前缀 `/api`，图片上传用 `multipart/form-data`
- **AI 调用统一走** `backend/services/seedream_client.py`，业务代码不直接调 API
- **新装 Python 依赖时**，先用 `pip install` 再手动加到 `requirements.txt`（测试依赖加到 `requirements-dev.txt`）
- **前端样式只用 Tailwind**，不要引入第三方 UI 库
- **前端测试注意**：jsdom 测试文件顶部需加 `// @vitest-environment jsdom`；vitest 未开 `globals`，需手动 `cleanup()`
- **试穿（阶段四）用原图 `image_path`，`cropped_path` 仅用于衣柜卡片展示**：抠图边缘有 halo，且 rembg 可能误扣衣物部件（如裤脚连着的鞋），喂给图像编辑模型会带出脏边；官方换装 demo 也喂带背景的商品原图

## 配置

`backend/.env`（已创建，已被 `.gitignore` 忽略）：

| 变量 | 说明 |
|---|---|
| `SEEDREAM_API_KEY` | 火山方舟 API Key。**留空时跳过 AI 识别**，衣物仍能抠图入库（语义字段为 null） |
| `SEEDREAM_VISION_MODEL` | 衣物识别模型，当前为 `doubao-seed-2-1-lite-260915`（旧版 `doubao-seed-1-6-vision-250815` 已下线，调用会返回 `InvalidEndpointOrModel.NotFound`） |
| `SEEDREAM_IMAGE_MODEL` | 图像生成/编辑模型（阶段四 AI 试穿用） |
| `ARK_BASE_URL` | 火山方舟地址 `https://ark.cn-beijing.volces.com/api/v3` |

## 部署

- Docker Compose 部署待实现（计划阶段五）

## 穿搭推荐接口（阶段三）

```
GET /api/recommendation?location=上海&occasion=休闲&user_id=1
```

| 情况 | 行为 |
|---|---|
| 正常 | 200，`items` 带 `role`（上衣/下装/鞋/配饰），`source` 为 `llm` 或 `rule` |
| 城市名为空 | 400 |
| 城市查不到 | 404（注意「火星」这类词在广东韶关确实是地名，不会 404） |
| 天气服务不可用 | 503（不做"无天气推荐"） |
| 衣柜为空 / LLM 失败 | **200**，`items: []` + `gaps` 提示 / `source: "rule"` 降级 |

- 架构：规则筛选（季节 + 场合 + 温度打分，每角色 Top-4）→ LLM 精选 → 校验 id → 任何异常降级到纯规则
- **无 `SEEDREAM_API_KEY` 时根本不调用 LLM**，衣物语义字段为 null 也能推荐（只降权不剔除）
- `occasion` 取值：通勤 / 休闲 / 运动 / 约会 / 正式，非法值回退「休闲」
- 天气来自 Open-Meteo（免费无 Key），中文城市名直接传 `name=` 参数

## 当前进度

- ✅ 阶段一：前后端骨架跑通
- ✅ 阶段二：抠图 + 衣物识别 + 前端衣柜页对接，真实 API 联调通过
- ✅ 阶段三：穿搭推荐（Open-Meteo 天气 + 规则/LLM 混合推荐 + 前端今日推荐页），后端 100 / 前端 25 测试全绿，真实端到端联调通过
- ⏳ 阶段四：AI 试穿（需开通图像生成模型，推荐 `doubao-seedream-5-0-pro-260628`）
- 完整路线图见 `PLAN.md`
