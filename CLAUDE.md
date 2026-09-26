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
│   ├── recommendation.py      # GET /api/recommendation（天气 + 穿搭推荐）
│   ├── model.py               # POST /api/model, GET /api/models, PUT /api/models/{id}/default
│   └── tryon.py               # POST /api/tryon, GET /api/outfits
├── services/
│   ├── background_removal.py  # rembg 本地抠图
│   ├── seedream_client.py     # 火山方舟 API 客户端（识图 + 文本对话 + 图像生成）
│   ├── weather.py             # Open-Meteo 天气（免 Key）
│   ├── recommendation.py      # 推荐引擎：规则筛选 → LLM 精选 → 降级
│   ├── garment_roles.py       # 品类 → 部位（上衣/下装/鞋/配饰）映射，推荐与试穿共用
│   └── tryon.py               # 试穿：衣物描述 → prompt → call_image_api
├── storage/
│   ├── database.py            # SQLite 连接 & 建表
│   ├── clothes_store.py       # 衣物数据访问
│   ├── model_store.py         # 模特数据访问（is_default 记账）
│   └── outfits_store.py       # 试穿记录（clothes_ids JSON 的读写）
├── tests/                     # pytest
├── uploads/                   # 上传图片存储（uploads/tryon/ 存生成结果）
├── requirements.txt           # 运行时依赖
└── requirements-dev.txt       # 含测试依赖
frontend/
├── src/App.tsx                # 路由框架：/ (今日推荐) /wardrobe (衣柜) /tryon (试穿)
├── src/types.ts               # Clothes / Model / Outfit / TryOnResult
├── src/api/client.ts          # fetch 封装
├── src/pages/                 # Home / Wardrobe / TryOn（三个页面均已对接后端）
├── src/components/            # WardrobeGrid（可选选中模式）
├── src/utils/                 # tryonIds.ts / variants.ts（纯函数，重点单测）
└── vite.config.ts             # 代理 /api + /uploads
PLAN.md                        # 完整技术方案（开发计划、API 设计、数据库表）
```

## 数据库表

- **clothes**: 衣物（image_path 原图、cropped_path 抠图PNG、category/color/style/season/tags）
- **models**: 模特全身照（is_default 默认模特；SQLite 无 bool，读出来是 0/1，出参前必须 `bool()` 转）
- **outfits**: 试穿记录（model_id + clothes_ids 存 TEXT 但**出参必须是数组** + generated_by 图像模型 id + result_image_url）

## 开发约定

- **TDD**：先写失败的测试，再写实现。后端用 pytest，前端用 vitest
- **API 风格**: REST，路径前缀 `/api`，图片上传用 `multipart/form-data`
- **AI 调用统一走** `backend/services/seedream_client.py`，业务代码不直接调 API
- **新装 Python 依赖时**，先用 `pip install` 再手动加到 `requirements.txt`（测试依赖加到 `requirements-dev.txt`）
- **前端样式只用 Tailwind**，不要引入第三方 UI 库
- **前端测试注意**：jsdom 测试文件顶部需加 `// @vitest-environment jsdom`；vitest 未开 `globals`，需手动 `cleanup()`
- **试穿用原图 `image_path`，`cropped_path` 仅用于衣柜卡片展示**：抠图边缘有 halo，且 rembg 可能误扣衣物部件（如裤脚连着的鞋），喂给图像编辑模型会带出脏边；官方换装 demo 也喂带背景的商品原图
- **花钱的调用只能挂在 click handler 上，绝不能放进 `useEffect`**：`main.tsx` 开了 `StrictMode`，dev 下 effect 双跑 = 一次点击打两次付费 API（试穿已按此实现）

## 配置

`backend/.env`（已创建，已被 `.gitignore` 忽略）：

| 变量 | 说明 |
|---|---|
| `SEEDREAM_API_KEY` | 火山方舟 API Key。**留空时跳过 AI 识别**，衣物仍能抠图入库（语义字段为 null） |
| `SEEDREAM_VISION_MODEL` | 衣物识别模型，当前为 `doubao-seed-2-1-lite-260915`（旧版 `doubao-seed-1-6-vision-250815` 已下线，调用会返回 `InvalidEndpointOrModel.NotFound`） |
| `SEEDREAM_IMAGE_MODEL` | 图像生成/编辑模型（阶段四 AI 试穿），当前为 `doubao-seedream-4-0-250828`，写进 `outfits.generated_by` |
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

## 试穿接口（阶段四）

```
POST /api/tryon    {"model_id": 1, "clothes_ids": [9, 10, 11]}   # model_id 可省略，用默认模特
GET  /api/outfits?limit=20
```

| 情况 | 行为 |
|---|---|
| 正常 | 200，`Outfit` + `warnings`（警告只出参、不落库） |
| `clothes_ids` 为空 / 超过 8 件 | 400 |
| 衣物或模特不存在 | 404 |
| 没有 `model_id` 且一张模特照都没传 | 400 |
| 上游限流 | **429 透传**（前端提示「稍后重试」） |
| 未配 Key / 上游不可用 / 超时 | 503（超时文案注明「本次可能已产生费用」） |

- 模特：`POST /api/model`（multipart `file`，字段名与 upload 一致）、`GET /api/models`、`PUT /api/models/{id}/default`
- `is_default` 三条规则：第一张上传的**自动成为默认**；无标记行时**回退到最新一张**（传了 3 张但没点过「设为默认」不该 404）；设默认在**一个事务里**先置位再清其余，失败回滚
- **一次请求 = 一张图，没有批量端点**：「对比生成」由前端**串行**发起（逐张上屏、避开限流、可中途放弃）
- 结果图写 `uploads/tryon/{uuid}.jpg`（JPEG 不写 PNG：2K PNG 3-6MB / JPEG q88 约 400KB），扩展名由 `guess_mime` 推导
- 前端「对比生成」：每个变体每个部位只放一件（同部位多件会被后端按 id 平局规则丢掉一件），笛卡尔积超 4 就只变单品最多的那个角色

## 三条产品级限制（实测得出，别再往 prompt 里投入）

根因：Seedream 是**整图重绘**的通用图像编辑模型，缺三样专用试穿模型（IDM-VTON 那类）天生就有的东西 —— mask（mask 外像素原样拷回）、pose 条件分支、garment 编码器。「哪些像素不能变」只能靠 prompt 软引导，而 prompt 对扩散采样器是**概率性**约束，不是硬约束。

1. **参考衣物与手臂区域重叠时，手臂姿势可能漂** —— 模型优先满足「完整展示衣物」这一训练先验。**触发条件是遮挡，不是「换上衣」**：手臂搭在胯上挡住裤子时，只换裤子一样会漂。已试过两轮强指令共 19 次真实调用，**姿势指标一次都没动过**（2026-09-25 三种强指令 7 次全无效；2026-09-26 三处 prompt 改动 12 次，配对实测姿势保持 **2/2 → 0/3**，点估计反向）。**prompt 调优到此为止**，试穿页已注明这一差异
2. **参考图的水印会传染到成图，但概率低** —— 2026-09-26 全库 9 张结果逐张查底边：**1/9**，且那一次已定位到源参考图的「豆包AI生成」水印（位置与缩放吻合）。6 次 `[9,10,11]` 即使参考图自带水印也一次没泄漏。代价是衣物自带的品牌标志可能一起丢
3. **输出整体抖动** —— 同一输入连跑 3 次得到「丢侧条 / 丢侧条 / 完整」，另有一次构图漂移（裁掉头顶）。**单张结果不可信，重跑是目前唯一的缓解手段**

> **验证门槛**：输出是随机的，「改完跑一次看着好了」什么都证明不了。判断 prompt 变体至少要 n≥3 同输入 + 对照（约 ¥0.6/变体），且 n=3 时 1/3 vs 2/3 仍在噪声内 —— 只能抓住大幅改善。
>
> **已被推翻的旧结论**（别再引用）：①「换上衣时才会漂」→ 触发条件是遮挡；②「水印已用规则挡住 / 多图 5 次泄漏 3 次」→ 实测 1/9；③「Seedream 4.5 是升级路径」→ 该模型 `Retiring`，调用返回 NotFound。

## 当前进度

- ✅ 阶段一：前后端骨架跑通
- ✅ 阶段二：抠图 + 衣物识别 + 前端衣柜页对接，真实 API 联调通过
- ✅ 阶段三：穿搭推荐（Open-Meteo 天气 + 规则/LLM 混合推荐 + 前端今日推荐页），后端 100 / 前端 25 测试全绿，真实端到端联调通过
- ✅ 阶段四：AI 试穿（模特管理 + 自由勾选多件 + 对比生成 + 历史记录 + 推荐页「试穿这套」联动），后端 207 / 前端 95 测试全绿。手工端到端 7 步联调已跑完（约 ¥1.8）。**已知限制：遮挡导致手臂漂、参考图水印偶发传染、输出抖动**，见上文
- ⏳ 阶段五：用户认证、Docker 部署、国际化
- ⏳ **阶段四待办**：试穿结果删除管理（结果图持续累积）；`models` / `clothes` 都没有 DELETE 端点（传错图无法在 UI 里删）；503 文案把上游 401 JSON 原样吐给用户（含 request id）；衣物上传处缺「建议用自己拍的照片，购物 App 下载的图常带水印」提示；模特体型识别（`height_cm` / `body_type` 仍为 NULL）；浏览器内验证（第 6 步）
- 完整路线图见 `PLAN.md`
