"""
SQLite 数据库初始化
"""
import aiosqlite
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "wardrobe.db"


async def create_tables(conn: aiosqlite.Connection):
    """在给定连接上创建所有表"""
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS clothes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            image_path TEXT NOT NULL,
            cropped_path TEXT,
            category TEXT,
            sub_category TEXT,
            color TEXT,
            style TEXT,
            season TEXT,
            tags TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            image_path TEXT NOT NULL,
            height_cm REAL,
            body_type TEXT,
            is_default BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS outfits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            model_id INTEGER,
            clothes_ids TEXT,
            generated_by TEXT DEFAULT 'seedream',
            result_image_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    await conn.commit()


async def init_db():
    """初始化数据库，创建所有表"""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await create_tables(db)


async def get_db():
    """获取数据库连接（用于请求上下文）"""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        yield db
