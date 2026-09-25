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
