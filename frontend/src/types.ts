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
