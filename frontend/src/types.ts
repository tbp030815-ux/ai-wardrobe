/** 衣物（对应后端 clothes 表的一行） */
export interface Clothes {
  id: number
  user_id: number
  /** 原图路径，形如 /uploads/xxx.jpg */
  image_path: string
  /** 抠图后的透明底 PNG 路径，识别失败时仍会有值 */
  cropped_path: string | null
  /** AI 识别的语义字段，未识别时为 null */
  category: string | null
  sub_category: string | null
  color: string | null
  style: string | null
  season: string | null
  tags: string | null
  created_at: string
  /**
   * 上衣 / 下装 / 鞋 / 配饰，由后端按 category 算出来（GET /api/wardrobe 才有）。
   * **必须是可选的**：推荐接口、单元测试的 fixture 里都没有这个字段，
   * 而 `tsc` 会连测试文件一起类型检查 —— 写成必填会让 `npm test` 绿而 `npm run build` 挂。
   * 识别失败的衣物是 null，需要单独分组。
   */
  role?: string | null
}

/** 模特全身照（对应后端 models 表的一行） */
export interface Model {
  id: number
  user_id: number
  /** 试穿时喂给图像模型的就是这张原图 */
  image_path: string
  /** 本期不采集，恒为 null */
  height_cm: number | null
  body_type: string | null
  is_default: boolean
  created_at: string
}

/** 一次试穿记录（对应后端 outfits 表的一行） */
export interface Outfit {
  id: number
  user_id: number
  model_id: number | null
  /** 库里是 JSON 字符串，后端已还原成数组 */
  clothes_ids: number[]
  /** 实际使用的图像模型 id —— 换模型后历史记录不会说谎 */
  generated_by: string
  result_image_url: string
  created_at: string
}

/** 试穿响应 = 记录 + 本次输入的质量提示（warnings 只出参、不落库） */
export interface TryOnResult extends Outfit {
  warnings: string[]
}

/** 天气（对应后端 services/weather.py 的 Weather） */
export interface Weather {
  city: string
  temperature: number
  apparent_temperature: number
  description: string
  temp_max: number
  temp_min: number
  /** 今日最大降水概率 % */
  precipitation_probability: number
  weather_code: number
  /** 推荐引擎实际使用的基准温度（体感取整） */
  reference_temperature: number
}

/** 推荐出的单品 = 衣物 + 它在整套里的角色 */
export interface RecommendedItem extends Clothes {
  /** 上衣 / 下装 / 鞋 / 配饰 */
  role: string
}

/** 穿搭推荐响应（对应 GET /api/recommendation） */
export interface Recommendation {
  weather: Weather
  occasion: string
  /** llm = 模型精选；rule = 规则降级 */
  source: 'llm' | 'rule'
  reason: string
  items: RecommendedItem[]
  /** 缺失提示，如「衣柜里还没有鞋」；为空数组表示不缺 */
  gaps: string[]
}

/** 登录状态（对应 GET /api/auth/me） */
export interface AuthStatus {
  authenticated: boolean
  /** 后端是否已配置访问密码；false 时登录页展示设置指引 */
  configured: boolean
}
