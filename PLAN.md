# AI 智能衣橱 — 技术方案总结

> 最后更新：2026-09-28（补上三类删除端点：衣物 / 模特 / 试穿结果）
>
> 阶段四已完成，含手工端到端联调与两轮 prompt 调优结论（见第七节）

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

> 本节是**最初的设计稿**，确实没按它建（`UploadModal.tsx` / `TryOnPanel.tsx` / `tryon_service.py` 都不存在）。
> 实际结构以 `CLAUDE.md` 的「目录结构」为准，差异也记在第七节各阶段末尾。

```
ai-cloth/
├── backend/                  # Python FastAPI 后端
│   ├── main.py               # 入口 & 路由注册
│   ├── api/                  # REST API 端点
│   │   ├── upload.py         # 上传衣物 / 模特照片
│   │   ├── wardrobe.py       # 衣柜 CRUD
│   │   ├── recommendation.py # 穿搭推荐 ✅ 已实现
│   │   └── tryon.py          # AI 试穿（阶段四）
│   ├── services/             # 业务逻辑层
│   │   ├── seedream_client.py    # Seedream API 统一客户端（识图 + 文本对话）
│   │   ├── background_removal.py # 抠图 (rembg)
│   │   ├── weather.py            # Open-Meteo 天气 ✅ 已实现
│   │   ├── recommendation.py     # 推荐逻辑 ✅ 已实现
│   │   └── tryon_service.py      # 试穿逻辑（阶段四）
│   ├── storage/              # 数据层
│   │   ├── database.py       # SQLite 连接 & 模型定义
│   │   └── clothes_store.py  # 衣物数据访问
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
| PUT | /api/clothes/:id | 编辑标签/分类 ❌ 未实现 |
| DELETE | /api/clothes/:id | 删除衣物 ✅ 已实现（连磁盘上的原图 + 抠图一起删） |

### 5.2 模特管理

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/model | 上传模特全身照 |
| GET | /api/models | 获取模特列表 |
| PUT | /api/models/:id/default | 设为默认模特 |
| DELETE | /api/models/:id | 删除模特照 ✅ 已实现（删掉默认模特时自动把最新一张提为默认） |

### 5.3 穿搭推荐

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/recommendation?location=上海&occasion=通勤 | 生成今日推荐 |

> 注：实际实现用 `occasion`（中文场合名）替代了原设计的 `mode`（英文枚举），取值：通勤/休闲/运动/约会/正式。
> 错误码：400 城市名为空、404 城市查不到、503 天气服务不可用；衣柜为空与 LLM 失败均返回 200 + 降级结果。

### 5.4 AI 试穿

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/tryon | 合成试穿效果图 |
| GET | /api/outfits?limit=20 | 试穿历史 |
| DELETE | /api/outfits/:id | 删除一次试穿记录 ✅ 已实现（连结果图一起删） |

> 注：试穿**不是** query 参数——实际接收 JSON body `{"model_id": 1, "clothes_ids": [2, 3, 4]}`，
> `model_id` 可省略（用默认模特）。衣物 id 字段名是 `clothes_ids` 而非 `cloth_ids`。

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

### 阶段三：穿搭推荐引擎（Day 6-8）✅ 已完成

**目标**：根据天气 + 库存生成搭配建议

```python
# 后端 services/weather.py —— Open-Meteo 免费天气，无需 API Key，支持中文城市名
GET https://geocoding-api.open-meteo.com/v1/search?name=上海&language=zh&count=1
GET https://api.open-meteo.com/v1/forecast?latitude=..&longitude=..
    &current=temperature_2m,apparent_temperature,weather_code
    &daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max

# 后端 services/recommendation.py —— 规则筛选 → LLM 精选 → 校验 → 降级
#   1. build_candidates：按季节带筛候选，按角色（上衣/下装/鞋/配饰）分组，
#      季节+场合+温度打分，每角色取 Top-4
#   2. call_chat_api：把天气 + 场合 + 候选清单（含 id）交给 LLM，只返回
#      {"clothes_ids": [...], "reason": "..."}
#   3. validate_llm_result：越界 id 丢弃、重复去重、整体非法则降级到纯规则
```

**验收标准**：
- ✅ 返回包含上装、下装、鞋履的完整搭配（缺角色时明确提示缺什么）
- ✅ 附带推荐理由（LLM 生成或规则模板）

**与原设计的差异**：
- 实际拆成 `services/weather.py` + `services/recommendation.py` 两个文件（原计划只写一个 `recommendation_engine.py`）
- 新增 `call_chat_api` 到 `seedream_client.py`（原设计想用 `call_seedream` 统一入口，但视觉与文本对话的 payload 差异明显，分开更清晰）
- 推荐结果**不落库**（`outfits` 表留给阶段四试穿，需要 model_id）

### 阶段四：AI 试穿功能（Day 9-14）✅ 已完成

**目标**：勾选衣柜里的衣物，穿到模特身上

```python
# 后端 services/tryon.py —— 把「穿什么」翻译成模型能执行的 prompt
#   1. sort_key / describe_garment：按角色自上而下、同角色按 id 排序，写成可读描述
#   2. build_tryon_prompt：参考图顺序约定为 [模特, 衣物1, 衣物2, ...]，与编号严格对应
#   3. build_tryon：薄封装，交给 services/seedream_client.call_image_api

# 后端 api/tryon.py
POST /api/tryon   {model_id?, clothes_ids: [...]}  → Outfit + warnings
GET  /api/outfits?limit=N                          → Outfit[]
```

**删除管理**（阶段四收尾补做，原设计没排进来）：结果图是按 MB 计的，而试穿一次就产一张，
累积速度约是衣物的 10 倍。三类删除一起补：

```python
# 后端 api/{wardrobe,model,tryon}.py —— 统一三步
#   1. DELETE ... RETURNING *  一次往返原子地拿到被删的行（还要拿路径去删文件）
#   2. 行不存在 → 404「衣物/模特/试穿记录不存在」，不删任何文件
#   3. 再删磁盘文件：uploads_store.delete_upload_files 尽力而为，删不掉也不让请求失败

DELETE /api/clothes/:id   → Clothes    # 原图 + 抠图 PNG
DELETE /api/models/:id    → Model      # 删掉的若是默认模特，同一事务里把最新一张提为默认
DELETE /api/outfits/:id   → Outfit     # 结果图
```

**验收标准**：
- ✅ 输入模特照 + 衣物原图 → 返回合成效果图
- ⚠️ 「姿势不变」**未达成** —— 参考衣物与手臂区域重叠时手臂会漂（见下方已知限制）

**与原设计的差异**：
- 模块名是 `services/tryon.py`，不是 `tryon_service.py`
- **喂原图而不是抠图 PNG**（原设计写的是「已抠好的衣服 PNG」）：抠图边缘有 halo，
  rembg 还可能误裁衣物部件（裤脚连着的鞋），喂给图像编辑模型会带出脏边。
  官方换装 demo 也喂带背景的商品原图。`cropped_path` 只用于衣柜卡片展示
- **不做 `download_image`**：用 `response_format: "b64_json"` 直接拿字节，
  整个「签名 URL 24h 过期」故障模式消失
- **不做放大**：文档写的 921,600 像素下限实测并未强制（430×458 = 196,940 px 生成成功），
  放大只引入插值伪影 → `prepare_reference_image` 只降不升
- **不做批量端点**：一次请求 = 一张图，「对比生成」由前端串行发起。
  一个请求里串 4 张会撞上网关超时，用户也无法中途放弃
- 新增 `UpstreamError(status_code, ...)`：原有客户端把状态码压进错误字符串，
  而试穿需要 **429 透传**让前端区分「稍后再试」和「彻底坏了」
- `generated_by` 写实际的图像模型 id，不写字面量 `'seedream'`
- **新增 `storage/uploads_store.py`**：`/uploads/...` URL → 磁盘路径的唯一入口。
  试穿原本用 `Path(url).name` 取文件名，而结果图在 `uploads/tryon/` 子目录下——
  取 `.name` 会把子目录丢掉，指向一个不存在的文件。删除功能正好需要这条路径映射，一并收口
- **不返回 204**：前端 `request<T>` 一律 `response.json()`，空响应体会解析失败，
  三个删除端点都返回被删的那一行

**三条产品级限制**（实测得出，别再往 prompt 里投入）：

根因：Seedream 是**整图重绘**的通用图像编辑模型，缺三样专用试穿模型（IDM-VTON 那类）天生就有的东西 ——
mask（mask 外像素原样拷回）、pose 条件分支、garment 编码器。「哪些像素不能变」只能靠 prompt 软引导，
而 prompt 对扩散采样器是**概率性**约束，不是硬约束。

1. **参考衣物与手臂区域重叠时，手臂姿势可能漂** —— 模型优先满足「完整展示衣物」这一先验。
   **触发条件是遮挡，不是「换上衣」**：手臂搭在胯上挡住裤子时，只换裤子一样会漂。
   已试过两轮强指令共 19 次真实调用，**姿势指标一次都没动过**：
   - 2026-09-25：「局部修图」「手臂位置必须一致」「点明遮挡关系」（7 次，全无效）
   - 2026-09-26：遮挡规则移回「保持」段 + 「遮挡是正确结果」正常化 + 去掉「自然贴合身体」+ 限定参考图用途
     （12 次，含 3v3 配对）。配对实测姿势保持 **2/2 → 0/3**（点估计反向，Fisher p≈0.10，
     n=3 不足以判定退化，但无任何改善证据）；**构图稳定明显改善**（人物占画布高极差 25.1 → 4.8，
     旧 prompt 出过一次裁头），故保留改动。产品侧在试穿页显式注明这一差异
2. **参考图的水印会传染到成图，但概率低** —— 2026-09-26 全库 9 张结果逐张查底边：**1/9**，
   且已定位到源参考图的「豆包AI生成」水印（位置与缩放吻合）。6 次 `[9,10,11]` 即使参考图自带水印也零泄漏。
   **代价是衣物自带的品牌标志可能一起丢**
3. **输出整体抖动** —— 同一输入连跑 3 次得到「丢侧条 / 丢侧条 / 完整」，另有一次构图漂移。
   **单张结果不可信，重跑是目前唯一的缓解手段**

> **验证门槛**：输出是随机的，「改完跑一次看着好了」什么都证明不了。判断 prompt 变体至少要
> n≥3 同输入 + 对照（约 ¥0.6/变体），且 n=3 时 1/3 vs 2/3 仍在噪声内 —— 只能抓住大幅改善。
>
> **已被推翻的旧结论**（别再引用）：①「换上衣时才会漂」→ 触发条件是遮挡；②「水印已用规则挡住 /
> 多图 5 次泄漏 3 次」→ 实测 1/9；③「Seedream 4.5 是升级路径」→ 该模型 `Retiring`，调用返回 NotFound。

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
