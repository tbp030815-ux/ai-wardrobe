# AI 智能衣橱 — 技术方案总结

> 最后更新：2025-09-22

---

## 一、项目概述

**AI 智能衣橱**是一个帮助用户管理衣物并实现虚拟试穿的网页应用，核心功能四个：

1. **添加衣物照片 → AI 自动抠图存入衣柜**
2. **上传人体全身照 → 作为试穿模特**
3. **选择衣柜里的衣服 + 模特 → AI 虚拟换装**
4. **根据天气/场合 → AI 穿搭推荐**

---

## 二、技术栈（极简方案 — 全部豆包）

| 层级 | 技术 | 数量 | 理由 |
|---|---|---|---|
| **前端** | React + Vite + Tailwind CSS | 1 个 | SPA 足够，无需 SSR；生态最大 |
| **后端** | FastAPI (Python 3.10+) | 1 个 | Python 是 AI 生态一等公民，无缝对接 |
| **数据库** | SQLite + aiosqlite | 1 个 | 零安装成本，单用户场景完全够用 |
| **AI 能力** | 火山引擎 Seedream API | **1 套 Key** | 一个 API 覆盖全部图像任务 |
| **部署** | Docker Compose | 1 条命令 | 一键启动所有服务 |

### 为什么没有千问/Qwen？

Seedream 既能看图识别又能编辑图片（抠图 + 换装），一套 Key 管所有。**千问只擅长文本识别，不具备图像编辑能力**。

### 为什么没有 IDM-VTON？

Seedream 已有参考图换装/局部重绘功能，虽然不如专业模型极致，但**对个人使用完全够用**，且免去了部署显卡服务器的运维成本。

---

## 三、目录结构

```
ai-cloth/
├── backend/                  # Python FastAPI 后端
│   ├── main.py               # 入口 & 路由注册
│   ├── api/                  # REST API 端点
│   │   ├── upload.py         # 上传衣物 / 模特照片
│   │   ├── wardrobe.py       # 衣柜 CRUD
│   │   ├── recommendation.py # 穿搭推荐
│   │   └── tryon.py          # AI 试穿
│   ├── services/             # 业务逻辑层
│   │   ├── seedream_client.py    # Seedream API 统一客户端
│   │   ├── background_removal.py # 抠图 (rembg)
│   │   ├── image_analysis.py     # 图像分析 (seedream vision)
│   │   ├── recommendation_engine.py # 推荐逻辑
│   │   └── tryon_service.py      # 试穿逻辑
│   ├── storage/              # 数据层
│   │   └── database.py       # SQLite 连接 & 模型定义
│   ├── uploads/              # 图片存储
│   └── requirements.txt
├── frontend/                 # React + Vite 前端
│   ├── src/
│   │   ├── components/       # 通用组件
│   │   │   ├── WardrobeGrid.tsx    # 衣柜网格展示
│   │   │   ├── UploadModal.tsx     # 上传弹窗
│   │   │   └── TryOnPanel.tsx      # 试穿面板
│   │   ├── pages/            # 页面
│   │   │   ├── Home.tsx          # 首页 - 今日推荐
│   │   │   ├── Wardrobe.tsx      # 衣柜浏览
│   │   │   ├── AddClothes.tsx    # 录入新衣服
│   │   │   └── TryOn.tsx         # AI 试穿页
│   │   ├── hooks/            # 自定义 hooks
│   │   │   ├── useUpload.ts
│   │   │   └── useRecommendation.ts
│   │   └── utils/
│   ├── package.json
│   └── vite.config.ts
├── docker-compose.yml
└── PLAN.md                   # 本文件
```

---

## 四、数据库表设计

### 4.1 衣物表 (clothes)

```sql
CREATE TABLE clothes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    image_path TEXT NOT NULL,           -- 原图路径
    cropped_path TEXT,                  -- 抠图后透明底 PNG 路径
    category TEXT,                       -- 上衣/裤子/鞋/配饰
    sub_category TEXT,                   -- T恤/卫衣/牛仔裤...
    color TEXT,                          -- 藏青色
    style TEXT,                          -- 休闲/商务
    season TEXT,                         -- 春夏/秋冬
    tags TEXT,                           -- JSON: {"tags": ["运动", "薄款"]}
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 4.2 模特表 (models)

```sql
CREATE TABLE models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    image_path TEXT NOT NULL,
    height_cm REAL,                      -- 身高 cm
    body_type TEXT,                      -- 体型描述
    is_default BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 4.3 穿搭记录表 (outfits)

```sql
CREATE TABLE outfits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    model_id INTEGER,
    clothes_ids TEXT,                    -- JSON: [id1, id2, ...]
    generated_by TEXT DEFAULT 'seedream',
    result_image_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 五、API 接口设计

### 5.1 衣物管理

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/upload | 上传图片（触发抠图 + 识别） |
| GET | /api/wardrobe | 获取衣柜列表（支持筛选） |
| GET | /api/clothes/:id | 获取衣物详情 |
| PUT | /api/clothes/:id | 编辑标签/分类 |
| DELETE | /api/clothes/:id | 删除衣物 |

### 5.2 模特管理

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/model | 上传模特全身照 |
| GET | /api/models | 获取模特列表 |
| PUT | /api/models/:id/default | 设为默认模特 |

### 5.3 穿搭推荐

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/recommendation?location=上海&mode=commute | 生成今日推荐 |

### 5.4 AI 试穿

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/tryon?model_id=1&cloth_ids=[2,3,4] | 合成试穿效果图 |

### 5.5 配置

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/config | 保存 Seedream API Key |
| GET | /api/config | 获取当前配置 |

---

## 六、Seedream API 调用方式

### 6.1 统一客户端

```python
# backend/services/seedream_client.py

async def call_seedream(task_type: str, **kwargs):
    """统一的 Seedream API 入口"""
    
    if task_type == "background_remove":
        # 模式：remove-background
        # 输入：图片
        # 输出：透明底 PNG
        
    elif task_type == "analyze":
        # 模式：vision
        # 输入：图片 + prompt "分析这件衣服的类别/颜色/风格"
        # 输出：JSON
        
    elif task_type == "recommend":
        # 模式：LLM
        # 输入：衣橱列表 + 天气信息
        # 输出：搭配建议 + 理由
        
    elif task_type == "tryon":
        # 模式：参考图换装
        # 输入：模特照 + 已抠好的衣服PNG
        # 输出：合成效果图
```

### 6.2 价格对比

| 模型 | 单价（人民币） |
|---|---|
| doubao-seedream-5.0-lite | ¥0.22/次 |
| doubao-seedream-4.5 | ¥0.25/次 |
| doubao-seedream-4.0 | ¥0.20/次 |

**新用户有免费试用额度**，足够验证需求和做出原型。

---

## 七、分阶段开发计划

### 阶段一：基础框架搭建（Day 1-2）

**目标**：前后端跑通基本通信

```bash
# 后端
cd backend && python -m venv venv && pip install fastapi uvicorn aiosqlite pillow httpx
uvicorn main:app --reload

# 前端
npm create vite@latest frontend -- --template react-ts
cd frontend && npm install tailwindcss && npx tailwindcss init
```

**验收标准**：
- `POST /api/upload` 能保存图片到磁盘
- 前端能调用该接口并在页面展示图片列表

### 阶段二：抠图 + 衣物识别（Day 3-5）

**目标**：上传衣服照片 → 自动去背景 + 打标签

```python
# 后端 services/background_removal.py
from rembg import remove
from PIL import Image
import io

async def remove_background(image_bytes: bytes) -> bytes:
    img = Image.open(io.BytesIO(image_bytes))
    result = remove(img)  # U2-Net 本地推理
    buf = io.BytesIO()
    result.save(buf, format="PNG")
    return buf.getvalue()
```

**验收标准**：
- 上传人像照，返回透明底 PNG
- 调用 Seedream vision API，返回结构化 JSON

### 阶段三：穿搭推荐引擎（Day 6-8）

**目标**：根据天气 + 库存生成搭配建议

```python
# 后端 services/recommendation_engine.py

# 1. 接入 Open-Meteo 免费天气接口
GET https://geocoding-api.open-meteo.com/v1/search?name=Shanghai
GET https://api.open-meteo.com/v1/forecast?latitude=31.2&longitude=121.5&hourly=temperature_2m

# 2. Seedream LLM 生成推荐
prompt = f"""
当前天气：{temp}°C, {weather_desc}
用户衣橱里有以下衣服：{wardrobe_list}
请推荐一套搭配（上装+下装+鞋履），并说明理由
"""
response = await call_seedream("recommend", prompt=prompt)
```

**验收标准**：
- 返回包含上装、下装、鞋履的完整搭配
- 附带推荐理由

### 阶段四：AI 试穿功能（Day 9-14）

**目标**：选一件已抠好的衣服，穿上到模特身上

```python
# 后端 services/tryon_service.py

async def run_tryon(person_image_bytes, garment_image_bytes, category):
    # 通过 Seedream API 的参考图换装模式调用
    # 传入两张图：模特全身照 + 已抠好的衣服 PNG
    # 等待返回合成后的效果图
    pass
```

**验收标准**：
- 输入模特照 + 衣服 PNG → 返回合成效果图
- 效果可接受（姿势不变，光影自然）

### 阶段五：完善与优化（Day 15-18）

- 用户认证系统（登录/注册）
- 季节模式筛选
- Docker 容器化部署
- 国际化（中英双语）

---

## 八、验证流程（端到端测试）

```
用户上传衣服照片
→ POST /api/upload (multipart/form-data)
→ 后端接收 → 调用 rembg 抠图 → 保存 cropped.png
→ 调用 Seedream vision API → 解析出 JSON
→ 存入 SQLite
→ 前端 GET /api/wardrobe 拉取列表 ✓

点击"今日推荐"
→ GET /api/recommendation?location=Shanghai
→ 后端查天气 → 组合衣橱列表 → 调 Seedream recommend
→ 返回搭配卡片 + 理由
→ 前端渲染 ✓

进入试穿页面
→ 选择衣服 + 模特 → POST /api/tryon
→ 后端调 Seedream tryon 模式
→ 返回合成效果图 URL
→ 前端全屏展示 ✓
```

---

## 九、环境变量 (.env)

```bash
# 火山引擎 Seedream API
SEEDREAM_API_KEY=your_api_key_here
SEEDREAM_MODEL=doubao-seedream-5.0-lite
SEEDREAM_BASE_URL=https://api.volcengine.com/v1

# 数据库
DATABASE_URL=./data/wardrobe.db

# 上传目录
UPLOAD_DIR=./uploads
```

---

## 十、风险与注意事项

| 风险 | 应对 |
|---|---|
| Seedream API 限流或涨价 | 预留 fallback 到第三方 VTON API 的接口 |
| 试穿效果不达标 | 保留切换到 IDM-VTON 自部署的可能 |
| SQLite 并发瓶颈 | 用户量上来后迁移 PostgreSQL |
| 图片存储膨胀 | 定期清理无用图片，考虑 OSS |

---

*本文档为动态文件，随开发进展持续更新。*
