import aiosqlite
from sqlite3 import Error
from datetime import datetime, timedelta
import logging

from config import MAX_RICE_PER_USER

logger = logging.getLogger(__name__)

DB_NAME = "users.db"  # Имя файла БД

_db = None

async def init_db() -> aiosqlite.Connection:
    """Инициализирует глобальное соединение с БД."""
    global _db
    if _db is None:
        try:
            _db = await aiosqlite.connect(DB_NAME)
            _db.row_factory = aiosqlite.Row
            await _db.execute("PRAGMA foreign_keys = ON")
            await _db.execute("PRAGMA journal_mode = WAL")
            logger.info(f"Глобальное соединение с БД {DB_NAME} установлено (WAL mode: ON).")
        except Exception as e:
            logger.error(f"Ошибка инициализации БД: {e}")
            raise
    return _db

async def close_db() -> None:
    """Закрывает глобальное соединение с БД."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None
        logger.info("Глобальное соединение с БД закрыто.")

class AsyncSQLiteContext:
     def __init__(self, db):
         self.db = db

     async def __aenter__(self):
         return self.db

     async def __aexit__(self, exc_type, exc_val, exc_tb):
         # Мы не закрываем глобальное соединение здесь.
         pass

async def create_connection() -> AsyncSQLiteContext:
     """Возвращает контекстный менеджер для работы с глобальным соединением."""
     if _db is None:
         await init_db()
     return AsyncSQLiteContext(_db)

async def _generic_update(table: str, where_col: str, where_val: any, **fields) -> bool:
    """Универсальная функция для обновления полей в любой таблице."""
    if not fields:
        return False
    
    async with await create_connection() as conn:
        if not conn:
            return False
            
        set_clause = ", ".join([f"{k} = ?" for k in fields.keys()])
        values = list(fields.values())
        values.append(where_val)
        
        try:
            cursor = await conn.cursor()
            await cursor.execute(f"UPDATE {table} SET {set_clause} WHERE {where_col} = ?", tuple(values))
            await conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Ошибка при обновлении таблицы {table} [{where_col}={where_val}]: {e}")
            return False

async def create_table() -> None:
    """Создаёт таблицу users и admins и waifu_cats, если её нет."""
    async with await create_connection() as conn:
        if conn:
            try:
                cursor = await conn.cursor()
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        nickname TEXT,
                        username TEXT
                    )
                 ''')
                await cursor.execute('''CREATE TABLE IF NOT EXISTS waifu_cat (
                    cats_id INTEGER PRIMARY KEY,
                    user_id INTEGER UNIQUE NOT NULL,
                    cat_name TEXT,
                    category_cats TEXT CHECK(category_cats IN ('kitten', 'students', 'MILF')),
                    date_cat TEXT,
                    satiety INTEGER DEFAULT 100,
                    miska_risa INTEGER DEFAULT 0,
                    mood TEXT,
                    image_cats TEXT,
                    age_days INTEGER DEFAULT 1,
                    last_age_update TEXT,
                    last_satiety_update TEXT
                )''')

                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS marriages (
                        marriage_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER UNIQUE NOT NULL,
                        cat_id INTEGER NOT NULL,
                        marriage_date TEXT,
                        FOREIGN KEY (user_id) REFERENCES users(user_id),
                        FOREIGN KEY (cat_id) REFERENCES waifu_cat(cats_id)
                    )
                ''')

                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS hebao_items (
                        item_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        item_key TEXT NOT NULL,
                        item_name TEXT NOT NULL,
                        quantity INTEGER NOT NULL DEFAULT 0,
                        updated_at TEXT,
                        UNIQUE(user_id, item_key)
                    )
                ''')

                # Создаем индексы для оптимизации запросов
                await cursor.execute('CREATE INDEX IF NOT EXISTS idx_hebao_user_item ON hebao_items(user_id, item_key)')
                await cursor.execute('CREATE INDEX IF NOT EXISTS idx_hebao_quantity ON hebao_items(quantity)')
                await cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')
                await cursor.execute('CREATE INDEX IF NOT EXISTS idx_waifu_user ON waifu_cat(user_id)')
                await cursor.execute('CREATE INDEX IF NOT EXISTS idx_marriages_cat ON marriages(cat_id)')
                
                # Добавляем колонку для отслеживания последней ежедневной выдачи риса
                try:
                    await cursor.execute('ALTER TABLE hebao_items ADD COLUMN last_rice_given TEXT')
                except (aiosqlite.OperationalError, Error):
                    # Колонка уже существует
                    pass

                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS chat_rules (
                        chat_id INTEGER PRIMARY KEY,
                        rules_text TEXT NOT NULL,
                        created_by INTEGER,
                        created_at TEXT,
                        updated_by INTEGER,
                        updated_at TEXT
                    )
                ''')

                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS admins (
                        user_id INTEGER PRIMARY KEY,
                        first_name TEXT
                    )
                ''')
                await conn.commit()
                logger.info("Проверка/создание таблиц выполнена.")
            except Error as e:
                logger.error(f"Ошибка при создании таблиц: {e}")

async def add_new_columns() -> None:
    """
    Добавляет новые столбцы (Description, Reputation, User_activity)
    в таблицу users, если они еще не существуют.
    А также дополнительные поля для waifu_cat из требований роутера.
    Также создает таблицы для системы модерации.
    """
    async with await create_connection() as conn:
        if conn:
            try:
                cursor = await conn.cursor()

                # Создаем таблицы модерации, если они не существуют
                # Таблица для предупреждений (варнов)
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS user_warnings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        chat_id INTEGER NOT NULL,
                        reason TEXT,
                        warned_by INTEGER NOT NULL,
                        warned_at TEXT DEFAULT (datetime('now')),
                        UNIQUE(user_id, chat_id)
                    )
                ''')

                # Таблица для активных наказаний
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS active_punishments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        chat_id INTEGER NOT NULL,
                        punishment_type TEXT NOT NULL, -- 'ban', 'mute', 'warn'
                        reason TEXT,
                        punished_by INTEGER NOT NULL,
                        punished_at TEXT DEFAULT (datetime('now')),
                        expires_at TEXT, -- NULL для перманентных наказаний
                        is_active INTEGER DEFAULT 1,
                        UNIQUE(user_id, chat_id, punishment_type)
                    )
                ''')

                # Таблица истории наказаний
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS punishment_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        chat_id INTEGER NOT NULL,
                        punishment_type TEXT NOT NULL,
                        action TEXT NOT NULL, -- 'added', 'removed', 'expired'
                        reason TEXT,
                        moderator_id INTEGER NOT NULL,
                        timestamp TEXT DEFAULT (datetime('now')),
                        duration_minutes INTEGER -- для временных наказаний
                    )
                ''')

                # Создаем индексы для таблиц модерации
                await cursor.execute('CREATE INDEX IF NOT EXISTS idx_warnings_user_chat ON user_warnings(user_id, chat_id)')
                await cursor.execute('CREATE INDEX IF NOT EXISTS idx_punishments_user_chat ON active_punishments(user_id, chat_id)')
                await cursor.execute('CREATE INDEX IF NOT EXISTS idx_punishment_history_user ON punishment_history(user_id)')
                await cursor.execute('CREATE INDEX IF NOT EXISTS idx_punishment_history_timestamp ON punishment_history(timestamp)')
                
                # Таблица истории рейтинга
                await cursor.execute('''
                    CREATE TABLE IF NOT EXISTS rating_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        reputation INTEGER NOT NULL,
                        change_date TEXT DEFAULT (datetime('now', 'localtime'))
                    )
                ''')
                await cursor.execute('CREATE INDEX IF NOT EXISTS idx_rating_history_user ON rating_history(user_id)')
                
                # Словарь: имя_столбца -> тип_данных_и_ограничения
                columns_users = {
                    "description": "TEXT(25)",
                    "reputation": "INTEGER DEFAULT 0",
                    "user_activity": "INTEGER DEFAULT 0",
                    "username": "TEXT",
                    "city": "TEXT"
                }
                
                for column_name, column_def in columns_users.items():
                    try:
                        # Пытаемся добавить каждый столбец
                        await cursor.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_def}")
                        logger.info(f"Столбец '{column_name}' успешно добавлен.")
                    except aiosqlite.OperationalError as e:
                        # Если столбец уже существует, SQLite выдаст ошибку, которую мы перехватим
                        if "duplicate column name" in str(e):
                            # Это ожидаемое поведение, если скрипт запускается не в первый раз
                            pass
                        else:
                            # Сообщаем о других, неожиданных ошибках
                            raise e

                # Дополнительные столбцы для таблицы waifu_cat
                columns_waifu = {
                    "cat_name": "TEXT",
                    "date_cat": "TEXT",
                    "satiety": "INTEGER DEFAULT 100",
                    "miska_risa": "INTEGER DEFAULT 0",
                    "mood": "TEXT",
                    "age_days": "INTEGER DEFAULT 1",
                    "last_age_update": "TEXT",
                    "last_satiety_update": "TEXT",
                    "trust": "INTEGER DEFAULT 0"
                }

                for column_name, column_def in columns_waifu.items():
                    try:
                        await cursor.execute(f"ALTER TABLE waifu_cat ADD COLUMN {column_name} {column_def}")
                        logger.info(f"Столбец '{column_name}' успешно добавлен в waifu_cat.")
                    except aiosqlite.OperationalError as e:
                        if "duplicate column name" in str(e):
                            pass
                        else:
                            raise e

                # Добавляем столбец is_active для таблицы active_punishments
                try:
                    await cursor.execute("ALTER TABLE active_punishments ADD COLUMN is_active INTEGER DEFAULT 1")
                    logger.info("Столбец 'is_active' успешно добавлен в active_punishments.")
                except aiosqlite.OperationalError as e:
                     if "duplicate column name" in str(e):
                         pass
                     else:
                         raise e

                await conn.commit()
            except Error as e:
                logger.error(f"Произошла ошибка при добавлении столбцов: {e}")
    
    # Запускаем миграцию constraints, если нужно
    await check_and_fix_waifu_constraint()



async def check_and_fix_waifu_constraint() -> None:
    """
    Проверяет и исправляет CHECK constraint в таблице waifu_cat.
    Заменяет 'loli' на 'kitten' в определении таблицы и самих данных.
    """
    async with await create_connection() as conn:
        if not conn:
            return

        try:
            cursor = await conn.cursor()
            
            # 1. Получаем SQL создания таблицы
            await cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='waifu_cat'")
            row = await cursor.fetchone()
            
            if not row:
                return
            
            create_sql = row[0]
            
            # Если в определении есть 'loli', значит нужно мигрировать
            if "'loli'" in create_sql:
                logger.info("Обнаружен устаревший CHECK constraint ('loli'). Начинаем миграцию...")
                
                await cursor.execute("BEGIN TRANSACTION")
                
                # 2. Переименовываем старую таблицу
                await cursor.execute("ALTER TABLE waifu_cat RENAME TO waifu_cat_old")
                
                # 3. Создаем новую таблицу с правильным constraint
                await cursor.execute('''
                    CREATE TABLE waifu_cat (
                        cats_id INTEGER PRIMARY KEY,
                        user_id INTEGER UNIQUE NOT NULL,
                        cat_name TEXT,
                        category_cats TEXT CHECK(category_cats IN ('kitten', 'students', 'MILF')),
                        date_cat TEXT,
                        satiety INTEGER DEFAULT 100,
                        miska_risa INTEGER DEFAULT 0,
                        mood TEXT,
                        image_cats TEXT,
                        age_days INTEGER DEFAULT 1,
                        last_age_update TEXT,
                        last_satiety_update TEXT
                    )
                ''')
                
                # 4. Копируем данные, заменяя loli на kitten
                await cursor.execute('''
                    INSERT INTO waifu_cat (
                        cats_id, user_id, cat_name, category_cats, date_cat, 
                        satiety, miska_risa, mood, image_cats, 
                        age_days, last_age_update, last_satiety_update
                    )
                    SELECT 
                        cats_id, user_id, cat_name, 
                        CASE WHEN category_cats = 'loli' THEN 'kitten' ELSE category_cats END,
                        date_cat, satiety, miska_risa, mood, image_cats, 
                        age_days, last_age_update, last_satiety_update
                    FROM waifu_cat_old
                ''')
                
                # 5. Удаляем старую таблицу
                await cursor.execute("DROP TABLE waifu_cat_old")
                
                # 6. Восстанавливаем индекс
                await cursor.execute('CREATE INDEX IF NOT EXISTS idx_waifu_user ON waifu_cat(user_id)')
                
                await conn.commit()
                logger.info("Миграция waifu_cat успешно завершена: 'loli' -> 'kitten'")
                
        except Exception as e:
            await conn.rollback()
            logger.error(f"Ошибка при миграции waifu_cat: {e}")

def _hebao_row_to_dict(row: aiosqlite.Row | None) -> dict | None:
    if not row:
        return None
    return {
        "item_id": row[0],
        "user_id": row[1],
        "item_key": row[2],
        "item_name": row[3],
        "quantity": row[4],
        "updated_at": row[5],
    }


async def get_hebao_items(user_id: int) -> list[dict]:
    """Возвращает список предметов хэбао пользователя (только с количеством > 0)."""
    async with await create_connection() as conn:
        if not conn:
            return []
        try:
            cursor = await conn.cursor()
            await cursor.execute(
                """
                SELECT item_id, user_id, item_key, item_name, quantity, updated_at
                FROM hebao_items
                WHERE user_id = ? AND quantity > 0
                ORDER BY item_name
                """,
                (user_id,),
            )
            rows = await cursor.fetchall()
            return [_hebao_row_to_dict(r) for r in rows if r]
        except Error as e:
            logger.error(f"Ошибка получения хэбао: {e}")
            return []


async def upsert_hebao_item(
    user_id: int,
    item_key: str,
    item_name: str | None = None,
    *,
    delta: int | None = None,
    set_value: int | None = None,
) -> bool:
    """
    Добавляет/обновляет предмет в хэбао.
    - set_value: жёстко устанавливает количество (не меньше 0)
    - delta: прибавляет/вычитает от текущего количества (не опуская ниже 0)
    """
    if not item_key:
        return False

    async with await create_connection() as conn:
        if not conn:
            return False

        try:
            cursor = await conn.cursor()
            now_iso = datetime.utcnow().isoformat()
            display_name = item_name or item_key

            if set_value is not None:
                new_qty = max(int(set_value), 0)
            else:
                await cursor.execute(
                    "SELECT quantity FROM hebao_items WHERE user_id = ? AND item_key = ?",
                    (user_id, item_key),
                )
                row = await cursor.fetchone()
                current_qty = row[0] if row else 0
                delta_val = int(delta or 0)
                new_qty = current_qty + delta_val
                if new_qty < 0:
                    new_qty = 0

            await cursor.execute(
                """
                INSERT INTO hebao_items (user_id, item_key, item_name, quantity, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id, item_key) DO UPDATE SET
                    item_name = excluded.item_name,
                    quantity = excluded.quantity,
                    updated_at = excluded.updated_at
                """,
                (user_id, item_key, display_name, new_qty, now_iso),
            )
            await conn.commit()
            return True
        except Error as e:
            logger.error(f"Ошибка апсерта хэбао: {e}")
            return False


async def get_hebao_overview(user_id: int, merge_waifu_rice: bool = True) -> list[dict]:
    """
    Возвращает список предметов в хэбао.
    При merge_waifu_rice дополнительно добавляет миски риса из профиля кошки.
    """
    items = await get_hebao_items(user_id)
    items_by_key = {item["item_key"]: item for item in items if item}

    if merge_waifu_rice:
        waifu = await get_waifu_by_user(user_id)
        bowls = 0
        if waifu and waifu.get("miska_risa") is not None:
            bowls = int(waifu.get("miska_risa") or 0)

        if bowls > 0:
            rice_item = items_by_key.get("miska_risa")
            if rice_item:
                rice_item["quantity"] += bowls
            else:
                items_by_key["miska_risa"] = {
                    "item_id": None,
                    "user_id": user_id,
                    "item_key": "miska_risa",
                    "item_name": "миска риса",
                    "quantity": bowls,
                    "updated_at": waifu.get("last_satiety_update") if waifu else None,
                }

    return sorted(items_by_key.values(), key=lambda x: x["item_name"].lower())


# --- Функции для работы с waifu_cat ---

def _waifu_row_to_dict(row: aiosqlite.Row | None) -> dict | None:
    if not row:
        return None
    # Поддержка старых схем: если нет новых колонок, подставляем значения по умолчанию
    row_len = len(row)
    def safe(idx, default=None):
        return row[idx] if row_len > idx else default

    return {
        "cats_id": safe(0),
        "user_id": safe(1),
        "cat_name": safe(2),
        "category_cats": safe(3),
        "date_cat": safe(4),
        "satiety": safe(5, 100),
        "mood": safe(6, "отличное"),
        "image_cats": safe(7),
        "age_days": safe(8, 1),
        "last_age_update": safe(9),
        "last_satiety_update": safe(10),
        "trust": safe(11, 0),
    }


async def create_waifu_for_user(user_id: int, cat_name: str = "мяу", category: str = "kitten", mood: str = "отличное") -> bool:
    """
    Создаёт запись кошко-жены для пользователя, если её ещё нет.
    Поле date_cat сохраняем в ISO-формате.
    Теперь выдает 1 миску риса при создании.
    """
    # Проверяем категорию согласно CHECK constraint в БД
    if category not in ("kitten", "students", "MILF"):
        category = "kitten"

    async with await create_connection() as conn:
        if not conn:
            logger.error(f"Не удалось подключиться к БД для создания кошки user_id={user_id}")
            return False

        try:
            cursor = await conn.cursor()
            
            # Сначала проверяем, есть ли уже кошка
            await cursor.execute("SELECT user_id FROM waifu_cat WHERE user_id = ?", (user_id,))
            existing = await cursor.fetchone()
            
            if existing:
                logger.info(f"У пользователя {user_id} уже есть кошка, создание пропущено")
                return False
            
            # Кошки нет, создаём
            now_iso = datetime.utcnow().isoformat()

            await cursor.execute(
                """
                INSERT INTO waifu_cat (user_id, cat_name, category_cats, date_cat, age_days, last_age_update, mood, satiety, last_satiety_update, trust)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, cat_name, category, now_iso, 1, now_iso, mood, 100, now_iso, 5),
            )

            # Выдаём 1 миску риса и 3 корма кошко-жены (korm_waifu)
            await upsert_hebao_item(user_id, "miska_risa", "миска риса", set_value=1)
            await upsert_hebao_item(user_id, "korm_waifu", "корм кошко-жены", set_value=3)
            await conn.commit()
            
            logger.info(f"Кошка успешно создана для пользователя {user_id}, выдана 1 миска риса")
            return True
            
        except Error as e:
            logger.error(f"Ошибка при создании кошки для user_id {user_id}: {e}")
            return False


async def get_waifu_by_user(user_id: int) -> dict | None:
    """Возвращает словарь с данными кошко-жены пользователя или None."""
    async with await create_connection() as conn:
        if not conn:
            return None
        try:
            cursor = await conn.cursor()
            await cursor.execute(
                """
                SELECT cats_id, user_id, cat_name, category_cats, date_cat,
                       satiety, mood, image_cats, age_days, last_age_update, last_satiety_update, trust
                FROM waifu_cat WHERE user_id = ?
                """,
                (user_id,),
            )
            row = await cursor.fetchone()
            return _waifu_row_to_dict(row)
        except Error as e:
            logger.error(f"Ошибка получения кошки: {e}")
            return None


async def update_cat_name(user_id: int, new_name: str) -> bool:
    """Обновляет кличку кошко-жены пользователя. Возвращает True, если обновлено."""
    return await _generic_update("waifu_cat", "user_id", user_id, cat_name=new_name)


async def update_cat_image(user_id: int, image_path: str) -> bool:
    """Сохраняет путь к изображению кошко-жены."""
    return await _generic_update("waifu_cat", "user_id", user_id, image_cats=image_path)


async def update_cat_state(user_id: int, *, satiety: int | None = None,
                    mood: str | None = None, last_satiety_update: str | None = None) -> bool:
    """
    Универсальное обновление динамических полей кошко-жены.
    Обновляет только переданные параметры.
    """
    fields = {}
    if satiety is not None:
        fields["satiety"] = satiety
    if mood is not None:
        fields["mood"] = mood
    if last_satiety_update is not None:
        fields["last_satiety_update"] = last_satiety_update

    return await _generic_update("waifu_cat", "user_id", user_id, **fields)


async def update_waifu_trust(user_id: int, delta: int) -> bool:
    """Обновляет уровень доверия кошко-жены (диапазон 0-100)."""
    async with await create_connection() as conn:
        if not conn:
            return False
        try:
            cursor = await conn.cursor()
            await cursor.execute(
                "SELECT trust FROM waifu_cat WHERE user_id = ?", (user_id,)
            )
            row = await cursor.fetchone()
            if row is None:
                return False
            
            new_trust = max(0, min(100, row[0] + delta))
            return await _generic_update("waifu_cat", "user_id", user_id, trust=new_trust)
        except Error as e:
            logger.error(f"Ошибка обновления доверия для user_id {user_id}: {e}")
            return False


async def get_marriage(user_id: int) -> dict | None:
    """Возвращает данные о браке пользователя."""
    async with await create_connection() as conn:
        if not conn:
            return None
        try:
            cursor = await conn.cursor()
            await cursor.execute(
                "SELECT marriage_id, user_id, cat_id, marriage_date FROM marriages WHERE user_id = ?",
                (user_id,),
            )
            row = await cursor.fetchone()
            if row:
                return {
                    "marriage_id": row[0],
                    "user_id": row[1],
                    "cat_id": row[2],
                    "marriage_date": row[3],
                }
            return None
        except Error as e:
            logger.error(f"Ошибка получения данных о браке для {user_id}: {e}")
            return None


async def register_marriage(user_id: int, cat_id: int) -> bool:
    """Регистрирует новый брак."""
    async with await create_connection() as conn:
        if not conn:
            return False
        try:
            cursor = await conn.cursor()
            now_iso = datetime.utcnow().isoformat()
            await cursor.execute(
                "INSERT INTO marriages (user_id, cat_id, marriage_date) VALUES (?, ?, ?)",
                (user_id, cat_id, now_iso),
            )
            await conn.commit()
            return True
        except Error as e:
            logger.error(f"Ошибка регистрации брака для {user_id}: {e}")
            return False


async def update_waifu_age(user_id: int, new_age: int, last_update_iso: str) -> bool:
    """Обновляет возраст и метку обновления, а также категорию на основе возраста."""
    if new_age <= 30:
        new_category = "kitten"
    elif new_age <= 120:
        new_category = "students"
    else:
        new_category = "MILF"

    return await _generic_update(
        "waifu_cat", "user_id", user_id, 
        age_days=new_age, last_age_update=last_update_iso, category_cats=new_category
    )


async def get_all_waifus_with_owners() -> list[dict]:
    """
    Возвращает список всех кошко-жен с информацией об их владельцах.
    Используется для рассылок приветствий и админ-списка.
    """
    async with await create_connection() as conn:
        if not conn:
            return []
        try:
            cursor = await conn.cursor()
            await cursor.execute(
                """
                SELECT w.user_id, w.cat_name, w.category_cats, w.age_days,
                       u.nickname, u.username
                FROM waifu_cat w
                LEFT JOIN users u ON w.user_id = u.user_id
                """
            )
            rows = await cursor.fetchall()
            return [
                {
                    "user_id": row[0],
                    "cat_name": row[1],
                    "category": row[2],
                    "age_days": row[3],
                    "nickname": row[4],
                    "username": row[5]
                } for row in rows
            ]
        except Error as e:
            logger.error(f"Ошибка при получении списка всех кошек: {e}")
            return []


async def clear_all_waifus() -> int:
    """
    Полностью очищает таблицу кошко-жен.
    Возвращает количество удаленных записей.
    """
    async with await create_connection() as conn:
        if not conn:
            return 0
        try:
            cursor = await conn.cursor()
            await cursor.execute("DELETE FROM waifu_cat")
            count = cursor.rowcount
            await conn.commit()
            logger.warning(f"База кошко-жен очищена. Удалено {count} записей.")
            return count
        except Error as e:
            logger.error(f"Ошибка при очистке таблицы кошек: {e}")
            return 0


async def delete_waifu_by_user(user_id: int) -> bool:
    """
    Удаляет запись о кошко-жене для конкретного пользователя.
    Возвращает True в случае успеха.
    """
    async with await create_connection() as conn:
        if not conn:
            return False
        try:
            cursor = await conn.cursor()
            await cursor.execute("DELETE FROM waifu_cat WHERE user_id = ?", (user_id,))
            count = cursor.rowcount
            await conn.commit()
            if count > 0:
                logger.info(f"Кошко-жена пользователя {user_id} удалена из базы.")
            return count > 0
        except Error as e:
            logger.error(f"Ошибка при удалении кошки для user_id {user_id}: {e}")
            return False
            
# --- ОСТАЛЬНЫЕ ВАШИ ФУНКЦИИ (без изменений) ---

async def add_user(user_id: int, nickname: str, username: str | None = None) -> None:
    """
    Добавляет гражданина в БД с указанным ником и username.
    При повторном добавлении обновляет username.
    Также выдает 1 миску риса новым гражданам.
    """
    async with await create_connection() as conn:
        if not conn:
            return

        try:
            cursor = await conn.cursor()

            # Проверяем, новый ли гражданин
            await cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            existing_user = await cursor.fetchone()

            if existing_user:
                # Гражданин уже существует, обновляем только username
                await cursor.execute(
                    "UPDATE users SET username = ? WHERE user_id = ?",
                    (username, user_id),
                )
            else:
                # Новый гражданин - добавляем с рейтингом 300
                await cursor.execute(
                    """
                    INSERT INTO users (user_id, nickname, username, reputation)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, nickname, username, 300),
                )
                # Логируем начальный рейтинг 300
                await _log_rating_history_cursor(conn, cursor, user_id, 300)
                
                # Выдаем 1 миску риса
                await upsert_hebao_item(user_id, "miska_risa", "миска риса", set_value=1)
                logger.info(f"Новому гражданину {user_id} (@{username or 'нет'}) установлен рейтинг 300 и выдана 1 миска риса")

            await conn.commit()
        except Error as e:
            logger.error(f"Ошибка при добавлении гражданина {user_id}: {e}")

async def get_user_nickname(user_id: int) -> str | None:
    """Получает ник гражданина."""
    async with await create_connection() as conn:
        if not conn:
            return None
        try:
            cursor = await conn.cursor()
            await cursor.execute("SELECT nickname FROM users WHERE user_id = ?", (user_id,))
            result = await cursor.fetchone()
            return result[0] if result else None
        except Error as e:
            logger.error(f"Ошибка получения никнейма: {e}")
            return None

async def set_user_nickname(user_id: int, nickname: str) -> bool:
    """Устанавливает ник гражданина."""
    return await _generic_update("users", "user_id", user_id, nickname=nickname)

async def get_user_profile(user_id: int) -> dict | None:
    """Получает все данные гражданина для анкеты."""
    async with await create_connection() as conn:
        if not conn:
            return None
        try:
            cursor = await conn.cursor()
            # Выбираем все нужные поля одним запросом
            await cursor.execute("""
                SELECT nickname, description, reputation, user_activity, city
                FROM users WHERE user_id = ?
            """, (user_id,))
            result = await cursor.fetchone()
            if result:
                # Возвращаем данные в виде удобного словаря
                profile_data = {
                    "nickname": result[0],
                    "description": result[1],
                    "reputation": result[2],
                    "activity": result[3],
                    "city": result[4]
                }
                return profile_data
        except Error as e:
            logger.error(f"Ошибка получения профиля: {e}")
            return None


async def get_user_by_username(username: str) -> int | None:
    """Ищет user_id по username в базе данных."""
    async with await create_connection() as conn:
        if not conn:
            return None
        try:
            cursor = await conn.cursor()
            await cursor.execute("SELECT user_id FROM users WHERE username = ?", (username,))
            result = await cursor.fetchone()
            return result[0] if result else None
        except Error as e:
            logger.error(f"Ошибка при поиске user_id по username {username}: {e}")
            return None


async def get_all_users() -> list[dict]:
    """
    Возвращает список всех граждан из базы данных.
    Каждый гражданин представлен словарем с полями: user_id, nickname, username.
    """
    async with await create_connection() as conn:
        if not conn:
            return []

        try:
            cursor = await conn.cursor()
            await cursor.execute("SELECT user_id, nickname, username FROM users ORDER BY user_id")
            rows = await cursor.fetchall()

            users = []
            for row in rows:
                users.append({
                    "user_id": row[0],
                    "nickname": row[1] or "нет",
                    "username": row[2] or "нет"
                })

            return users

        except Error as e:
            logger.error(f"Ошибка при получении списка пользователей: {e}")
            return []


async def update_user_username(user_id: int, username: str | None) -> bool:
    """Обновляет username гражданина в базе данных."""
    return await _generic_update("users", "user_id", user_id, username=username)


async def delete_user_completely(username: str) -> bool:
    """
    Полностью удаляет гражданина из системы по username.
    Удаляет записи из всех таблиц: users, waifu_cat, hebao_items, admins.
    Возвращает True если успешно удален хотя бы один гражданин.
    """
    logger.info(f"Начинаем удаление гражданина @{username}")

    # Сначала найдем user_id
    user_id = await get_user_by_username(username)
    if not user_id:
        logger.warning(f"Гражданин @{username} не найден в базе данных")
        return False

    async with await create_connection() as conn:
        if not conn:
            return False

        try:
            cursor = await conn.cursor()

            # Удаляем из всех таблиц
            tables_to_clean = ['hebao_items', 'waifu_cat', 'admins', 'users']
            deleted_records = 0

            for table in tables_to_clean:
                await cursor.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
                deleted_records += cursor.rowcount
                if cursor.rowcount > 0:
                    logger.info(f"Удалено {cursor.rowcount} записей из таблицы {table} для гражданина @{username} (ID: {user_id})")

            await conn.commit()

            if deleted_records > 0:
                logger.info(f"Пользователь @{username} (ID: {user_id}) полностью удален из системы. Всего удалено {deleted_records} записей")
                return True
            else:
                logger.warning(f"Не найдено записей для удаления пользователя @{username} (ID: {user_id})")
                return False

        except Error as e:
            logger.error(f"Ошибка при удалении пользователя @{username}: {e}")
            return False


# --- Функции для работы с правилами чата ---

async def save_chat_rules(chat_id: int, rules_text: str, user_id: int) -> bool:
    """
    Сохраняет или обновляет правила чата.
    Возвращает True при успехе.
    """
    async with await create_connection() as conn:
        if not conn:
            logger.error("Не удалось подключиться к базе данных")
            return False

        try:
            cursor = await conn.cursor()
            now_iso = datetime.utcnow().isoformat()

            await cursor.execute('''
                INSERT INTO chat_rules (chat_id, rules_text, created_by, created_at, updated_by, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    rules_text = excluded.rules_text,
                    updated_by = excluded.updated_by,
                    updated_at = excluded.updated_at
            ''', (chat_id, rules_text, user_id, now_iso, user_id, now_iso))

            await conn.commit()
            if cursor.rowcount > 0:
                logger.info(f"Правила чата {chat_id} сохранены пользователем {user_id}")
                return True
            else:
                logger.warning(f"Не удалось сохранить правила чата {chat_id}")
                return False

        except Error as e:
            logger.error(f"Ошибка при сохранении правил чата {chat_id}: {e}")
            return False


async def get_chat_rules(chat_id: int) -> str | None:
    """
    Получает правила чата по chat_id.
    Возвращает текст правил или None если правил нет.
    """
    async with await create_connection() as conn:
        if not conn:
            return None
        try:
            cursor = await conn.cursor()
            await cursor.execute("SELECT rules_text FROM chat_rules WHERE chat_id = ?", (chat_id,))
            result = await cursor.fetchone()
            return result[0] if result else None
        except Error as e:
            logger.error(f"Ошибка при получении правил чата {chat_id}: {e}")
            return None


async def get_chat_rules_info(chat_id: int) -> dict | None:
    """
    Получает полную информацию о правилах чата.
    Возвращает словарь с данными или None.
    """
    async with await create_connection() as conn:
        if not conn:
            return None
        try:
            cursor = await conn.cursor()
            await cursor.execute("SELECT rules_text, created_by, updated_at FROM chat_rules WHERE chat_id = ?", (chat_id,))
            row = await cursor.fetchone()
            if row:
                return {
                    "rules_text": row[0],
                    "user_id": row[1],
                    "updated_at": row[2]
                }
            return None
        except Error as e:
            logger.error(f"Ошибка при получении инфо о правилах чата {chat_id}: {e}")
            return None

async def delete_chat_rules(chat_id: int) -> bool:
    """
    Полностью удаляет правила чата из базы данных.
    Возвращает True при успехе.
    """
    async with await create_connection() as conn:
        if not conn:
            return False
        try:
            cursor = await conn.cursor()
            await cursor.execute("DELETE FROM chat_rules WHERE chat_id = ?", (chat_id,))
            await conn.commit()
            return cursor.rowcount > 0
        except Error as e:
            logger.error(f"Ошибка при удалении правил чата {chat_id}: {e}")
            return False


# --- Функции для ежедневной выдачи риса ---

async def cleanup_expired_punishments() -> tuple[int, list]:
    """
    Автоматически снимает истекшие наказания.
    Возвращает количество снятых наказаний.
    """
    async with await create_connection() as conn:
        if not conn:
            return 0, []
        try:
            cursor = await conn.cursor()
            now = datetime.utcnow().isoformat()
            
            # Получаем список тех, кого будем разбанивать/размучивать (для логов или уведомлений)
            await cursor.execute(
                "SELECT user_id, chat_id, punishment_type FROM active_punishments WHERE expires_at IS NOT NULL AND expires_at <= ? AND is_active = 1",
                (now,)
            )
            expired = await cursor.fetchall()
            
            if expired:
                await cursor.execute(
                    "UPDATE active_punishments SET is_active = 0 WHERE expires_at IS NOT NULL AND expires_at <= ? AND is_active = 1",
                    (now,)
                )
                await conn.commit()
            
            return len(expired), expired # Возвращаем кортеж с количеством и списком
        except Error as e:
            logger.error(f"Ошибка при очистке истекших наказаний: {e}")
            return 0, []

async def get_all_banned_users(chat_id: int) -> list[dict]:
    """
    Возвращает список всех активных банов в чате.
    """
    async with await create_connection() as conn:
        if not conn:
            return []
        try:
            cursor = await conn.cursor()
            await cursor.execute(
                """
                SELECT u.user_id, u.nickname, p.reason, p.expires_at 
                FROM active_punishments p
                JOIN users u ON p.user_id = u.user_id
                WHERE p.chat_id = ? AND p.punishment_type = 'ban' AND p.is_active = 1
                """,
                (chat_id,)
            )
            rows = await cursor.fetchall()
            return [{"user_id": r[0], "nickname": r[1], "reason": r[2], "expires_at": r[3]} for r in rows]
        except Error as e:
            logger.error(f"Ошибка при получении банлиста чата {chat_id}: {e}")
            return []

async def get_last_punishment_details(user_id: int, p_type: str) -> dict | None:
    """
    Получает детали последнего активного наказания пользователя по типу.
    """
    async with await create_connection() as conn:
        if not conn:
            return None
        try:
            cursor = await conn.cursor()
            await cursor.execute(
                """
                SELECT p.reason, p.punished_by, p.expires_at, u.nickname as moderator_name
                FROM active_punishments p
                LEFT JOIN users u ON p.punished_by = u.user_id
                WHERE p.user_id = ? AND p.punishment_type = ? AND p.is_active = 1
                ORDER BY p.id DESC LIMIT 1
                """,
                (user_id, p_type)
            )
            row = await cursor.fetchone()
            if row:
                return {
                    "reason": row[0],
                    "moderator_id": row[1],
                    "expires_at": row[2],
                    "moderator_name": row[3] or f"ID:{row[1]}"
                }
            return None
        except Error as e:
            logger.error(f"Ошибка при получении деталей наказания {user_id}: {e}")
            return None


async def get_user_rice_count(user_id: int) -> int:
    """
    Получает количество мисок риса у пользователя.
    Возвращает 0 если риса нет.
    """
    async with await create_connection() as conn:
        if not conn:
            return 0

        try:
            cursor = await conn.cursor()
            await cursor.execute(
                "SELECT quantity FROM hebao_items WHERE user_id = ? AND item_key = 'miska_risa'",
                (user_id,)
            )
            result = await cursor.fetchone()
            return result[0] if result else 0

        except Error as e:
            logger.error(f"Ошибка при получении количества риса для user_id {user_id}: {e}")
            return 0


async def give_daily_rice(user_id: int) -> bool:
    """
    Выдает 1 миску риса пользователю, если у него меньше максимального количества.
    Обновляет время последней выдачи.
    Возвращает True если рис был выдан.
    """
    rice_count = await get_user_rice_count(user_id)

    if rice_count >= MAX_RICE_PER_USER:
        logger.info(f"Пользователь {user_id} имеет {rice_count} мисок риса (>={MAX_RICE_PER_USER}), ежедневная выдача пропущена")
        return False

    # Выдаем 1 миску риса
    success = await upsert_hebao_item(user_id, "miska_risa", "миска риса", delta=1)

    if success:
        # Обновляем время последней выдачи
        async with await create_connection() as conn:
            if conn:
                try:
                    cursor = await conn.cursor()
                    now_iso = datetime.utcnow().isoformat()
                    await cursor.execute(
                        "UPDATE hebao_items SET last_rice_given = ? WHERE user_id = ? AND item_key = 'miska_risa'",
                        (now_iso, user_id)
                    )
                    await conn.commit()
                    logger.info(f"Пользователю {user_id} выдана 1 миска риса (было {rice_count}, стало {rice_count + 1})")
                except Error as e:
                    logger.error(f"Ошибка обновления last_rice_given для user_id {user_id}: {e}")

        return True

    return False


async def reset_all_rice_to_one() -> int:
    """
    Обнуляет количество риса у всех граждан до 1 миски.
    Возвращает количество обновленных граждан.
    """
    async with await create_connection() as conn:
        if not conn:
            logger.error("Не удалось подключиться к БД для сброса риса")
            return 0

        try:
            cursor = await conn.cursor()

            # Получаем всех граждан с рисом
            await cursor.execute("SELECT user_id, quantity FROM hebao_items WHERE item_key = 'miska_risa' AND quantity > 1")
            users_with_rice = await cursor.fetchall()

            updated_count = 0
            for user_id, current_quantity in users_with_rice:
                # Обновляем до 1 миски
                await cursor.execute(
                    "UPDATE hebao_items SET quantity = 1, updated_at = ? WHERE user_id = ? AND item_key = 'miska_risa'",
                    (datetime.utcnow().isoformat(), user_id)
                )
                if cursor.rowcount > 0:
                    updated_count += 1
                    logger.info(f"Пользователь {user_id}: рис сброшен с {current_quantity} до 1 миски")

            # Добавляем 1 миску риса гражданам, у которых ее нет вообще
            await cursor.execute("SELECT user_id FROM users WHERE user_id NOT IN (SELECT user_id FROM hebao_items WHERE item_key = 'miska_risa')")
            users_without_rice = await cursor.fetchall()

            for (user_id,) in users_without_rice:
                await upsert_hebao_item(user_id, "miska_risa", "миска риса", set_value=1)
                updated_count += 1
                logger.info(f"Пользователь {user_id}: добавлена 1 миска риса")

            await conn.commit()
            logger.info(f"Сброс риса завершен. Обновлено {updated_count} граждан")

            return updated_count

        except Error as e:
            logger.error(f"Ошибка при сбросе риса: {e}")
            return 0


async def reset_all_ratings_to_default(default_rating: int = 100) -> int:
    """
    Сбрасывает рейтинг всех граждан до значения по умолчанию (100).
    Возвращает количество обновленных граждан.
    """
    async with await create_connection() as conn:
        if not conn:
            logger.error("Не удалось подключиться к БД для сброса рейтинга")
            return 0

        try:
            cursor = await conn.cursor()

            # Получаем всех граждан с текущим рейтингом
            await cursor.execute("SELECT user_id, reputation FROM users")
            all_users = await cursor.fetchall()

            updated_count = 0
            for user_id, current_rating in all_users:
                if current_rating != default_rating:
                    await cursor.execute(
                        "UPDATE users SET reputation = ? WHERE user_id = ?",
                        (default_rating, user_id)
                    )
                    if cursor.rowcount > 0:
                        updated_count += 1
                        logger.info(f"Гражданин {user_id}: рейтинг сброшен с {current_rating} до {default_rating}")
                        # Логируем сброс
                        await _log_rating_history_cursor(conn, cursor, user_id, default_rating)

            await conn.commit()
            logger.info(f"Сброс рейтинга завершен. Обновлено {updated_count} граждан до {default_rating}")

            return updated_count

        except Error as e:
            logger.error(f"Ошибка при сбросе рейтинга: {e}")
            return 0


async def initialize_default_ratings(default_rating: int = 100) -> int:
    """
    Устанавливает рейтинг по умолчанию (100) всем гражданам, у которых рейтинг еще не установлен.
    Используется для первичной инициализации.
    Возвращает количество обновленных граждан.
    """
    async with await create_connection() as conn:
        if not conn:
            logger.error("Не удалось подключиться к БД для инициализации рейтинга")
            return 0

        try:
            cursor = await conn.cursor()

            # Обновляем граждан, у которых рейтинг NULL или 0
            await cursor.execute(
                "UPDATE users SET reputation = ? WHERE reputation IS NULL OR reputation = 0",
                (default_rating,)
            )

            updated_count = cursor.rowcount
            await conn.commit()

            if updated_count > 0:
                logger.info(f"Инициализация рейтинга завершена. Установлено {default_rating} рейтинга для {updated_count} граждан")

            return updated_count

        except Error as e:
            logger.error(f"Ошибка при инициализации рейтинга: {e}")
            return 0


async def process_daily_rice_distribution() -> int:
    """
    Обрабатывает ежедневную выдачу риса всем гражданам.
    Вызывается раз в сутки.
    Возвращает количество пользователей, которым был выдан рис.
    """
    logger.info("Начинается ежедневная выдача риса")

    async with await create_connection() as conn:
        if not conn:
            logger.error("Не удалось подключиться к БД для ежедневной выдачи риса")
            return 0

        try:
            cursor = await conn.cursor()

            # Получаем всех граждан
            await cursor.execute("SELECT user_id FROM users")
            all_users = await cursor.fetchall()

            distributed_count = 0

            for (user_id,) in all_users:
                if await give_daily_rice(user_id):
                    distributed_count += 1

            logger.info(f"Ежедневная выдача риса завершена. Выдано {distributed_count} гражданам")
            return distributed_count

        except Error as e:
            logger.error(f"Ошибка при ежедневной выдаче риса: {e}")
            return 0


async def set_user_description(user_id: int, description: str) -> bool:
    """Устанавливает или обновляет описание пользователя."""
    return await _generic_update("users", "user_id", user_id, description=description)

async def add_admin(user_id: int, first_name: str) -> None:
    """Добавляет администратора в таблицу admins."""
    async with await create_connection() as conn:
        if conn:
            try:
                cursor = await conn.cursor()
                await cursor.execute("INSERT OR IGNORE INTO admins (user_id, first_name) VALUES (?, ?)", (user_id, first_name))
                await conn.commit()
                logger.info(f"Администратор {user_id} добавлен с именем {first_name}")
            except Error as e:
                logger.error(f"Ошибка при добавлении админа {user_id}: {e}")

async def remove_admin(user_id: int) -> None:
    """Удаляет администратора из таблицы admins."""
    async with await create_connection() as conn:
        if conn:
            try:
                cursor = await conn.cursor()
                await cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
                await conn.commit()
                logger.info(f"Администратор {user_id} удалён")
            except Error as e:
                logger.error(f"Ошибка при удалении админа {user_id}: {e}")

async def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    async with await create_connection() as conn:
        if conn:
            try:
                cursor = await conn.cursor()
                await cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
                result = await cursor.fetchone()
                return bool(result)
            except Error as e:
                logger.error(f"Ошибка при проверке прав админа {user_id}: {e}")
    return False

async def get_all_admins() -> list[tuple[int, str]]:
    """Получает список всех администраторов (user_id и first_name)."""
    async with await create_connection() as conn:
        if conn:
            try:
                cursor = await conn.cursor()
                await cursor.execute("SELECT user_id, first_name FROM admins")
                return await cursor.fetchall()  # Возвращает список кортежей [(user_id, first_name), ...]
            except Error as e:
                logger.error(f"Ошибка при получении списка админов: {e}")
    return []

async def initialize_admins(admin_ids: list[int]) -> None:
    """Инициализирует таблицу admins из списка ADMIN_IDS, если она пуста."""
    async with await create_connection() as conn:
        if conn:
            try:
                cursor = await conn.cursor()
                await cursor.execute("SELECT COUNT(*) FROM admins")
                result = await cursor.fetchone()
                count = result[0]
                if count == 0:
                    for user_id in admin_ids:
                        await add_admin(user_id, "Администратор")  # Placeholder first_name; можно заменить на реальное через API
                    logger.info("Таблица admins инициализирована из ADMIN_IDS")
            except Error as e:
                logger.error(f"Ошибка при инициализации админов: {e}")

async def set_user_city(user_id: int, city: str) -> bool:
    """Устанавливает или обновляет город пользователя."""
    return await _generic_update("users", "user_id", user_id, city=city)

async def get_user_city(user_id: int) -> str | None:
    """Получает город пользователя из БД."""
    async with await create_connection() as conn:
        if conn:
            try:
                cursor = await conn.cursor()
                await cursor.execute("SELECT city FROM users WHERE user_id = ?", (user_id,))
                result = await cursor.fetchone()
                return result[0] if result else None
            except Error as e:
                logger.error(f"Ошибка при получении города для {user_id}: {e}")
    return None

async def get_user_description(user_id: int) -> str | None:
    """Получает описание пользователя из БД."""
    async with await create_connection() as conn:
        if conn:
            try:
                cursor = await conn.cursor()
                await cursor.execute("SELECT description FROM users WHERE user_id = ?", (user_id,))
                result = await cursor.fetchone()
                # Возвращаем описание (result[0]) если оно есть, иначе None
                return result[0] if result else None
            except Error as e:
                logger.error(f"Ошибка при получении описания для {user_id}: {e}")
    return None

async def get_user_rate(user_id: int) -> int:
    async with await create_connection() as conn:
        if not conn:
            return None
        try:
            cursor = await conn.cursor()
            await cursor.execute('SELECT reputation FROM users WHERE user_id = ?', (user_id,))
            result = await cursor.fetchone()
            return result[0] if result else None
        except Error as e:
            logger.error(f"Ошибка при получении рейтинга для {user_id}: {e}")
            return None

async def get_user_rating_history(user_id: int) -> list[tuple[str, int]]:
    """
    Получает историю изменения рейтинга пользователя.
    Возвращает список кортежей (дата_изменения, рейтинг), отсортированных по дате (от старых к новым).
    """
    async with await create_connection() as conn:
        if not conn:
            return []
        try:
            cursor = await conn.cursor()
            await cursor.execute(
                "SELECT change_date, reputation FROM rating_history WHERE user_id = ? ORDER BY change_date ASC",
                (user_id,)
            )
            rows = await cursor.fetchall()
            return [(r[0], r[1]) for r in rows]
        except Error as e:
            logger.error(f"Ошибка при получении истории рейтинга для {user_id}: {e}")
            return []

async def _log_rating_history(user_id: int, rate: int) -> None:
    """Внутренняя функция для записи истории изменения рейтинга."""
    async with await create_connection() as conn:
        if conn:
            try:
                cursor = await conn.cursor()
                await _log_rating_history_cursor(conn, cursor, user_id, rate)
                await conn.commit()
            except Error as e:
                logger.error(f"Ошибка при записи истории рейтинга пользователя {user_id}: {e}")

async def _log_rating_history_cursor(conn, cursor, user_id: int, rate: int) -> None:
    """Функция записи истории рейтинга с использованием переданного курсора для массовых операций."""
    try:
        await cursor.execute(
            "INSERT INTO rating_history (user_id, reputation, change_date) VALUES (?, ?, ?)",
            (user_id, rate, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        )
    except Error as e:
        logger.error(f"Ошибка при записи истории рейтинга курсором {user_id}: {e}")

async def update_user_rate(user_id: int, rate: int) -> bool:
    """
    Обновляет рейтинг пользователя. 
    Если рейтинг достигает 500 и у пользователя нет кошки, она создается автоматически.
    Возвращает True, если была создана новая кошка.
    """
    success = await _generic_update("users", "user_id", user_id, reputation=rate)
    if not success:
        return False
    
    # Логируем изменение
    await _log_rating_history(user_id, rate)
    
    # После обновления рейтинга проверяем, нужно ли создать кошку
    if rate >= 500:
        logger.info(f"Рейтинг {rate} >= 500, проверяем создание кошки для пользователя {user_id}")
        cat_created = await create_waifu_for_user(user_id)
        logger.info(f"Результат создания кошки для {user_id}: {cat_created}")
        return cat_created
    
    return False

async def unrate_user(user_id: int, rate: int) -> bool:
    """Сбрасывает рейтинг пользователя."""
    success = await _generic_update("users", "user_id", user_id, reputation=rate)
    if success:
        await _log_rating_history(user_id, rate)
    return success


async def increment_user_activity(user_id: int) -> bool:
    """Увеличивает счётчик активности гражданина на 1."""
    async with await create_connection() as conn:
        if not conn:
            logger.error("Не удалось подключиться к БД для увеличения активности")
            return False

        try:
            cursor = await conn.cursor()
            # Используем SQL для атомарного увеличения значения
            await cursor.execute("""
                UPDATE users
                SET user_activity = user_activity + 1
                WHERE user_id = ?
            """, (user_id,))

            if cursor.rowcount == 0:
                # Гражданин не найден, создаем его
                logger.warning(f"Гражданин {user_id} не найден при увеличении активности, создаем")
                await add_user(user_id, "пользователь")
                # Повторяем попытку
                await cursor.execute("""
                    UPDATE users
                    SET user_activity = user_activity + 1
                    WHERE user_id = ?
                """, (user_id,))

            await conn.commit()
            return True

        except Error as e:
            logger.error(f"Ошибка при инкременте активности гражданина {user_id}: {e}")
            return False

async def get_chat_leaderboard(limit: int = 10) -> list[aiosqlite.Row]:
    """Получает топ граждан по активности."""
    async with await create_connection() as conn:
        if conn:
            try:
                cursor = await conn.cursor()
                # Выбираем ник и активность, сортируем по убыванию активности
                # LIMIT ограничивает вывод, чтобы не спамить в чат
                await cursor.execute("""
                    SELECT nickname, User_activity
                    FROM users
                    WHERE User_activity > 0
                    ORDER BY User_activity DESC
                    LIMIT ?
                """, (limit,))
                # Возвращаем список кортежей (ник, активность)
                return await cursor.fetchall()
            except Error as e:
                logger.error(f"Ошибка при получении лидерборда: {e}")
    return []

async def get_highly_active_users(min_activity: int) -> list[tuple[int, str, int]]:
    """
    Возвращает список пользователей, чья активность выше заданного порога.
    [(user_id, nickname, user_activity), ...]
    """
    async with await create_connection() as conn:
        if not conn:
            return []
        try:
            cursor = await conn.cursor()
            await cursor.execute(
                "SELECT user_id, nickname, user_activity FROM users WHERE user_activity >= ?",
                (min_activity,)
            )
            return await cursor.fetchall()
        except Error as e:
            logger.error(f"Ошибка при получении списка активных пользователей: {e}")
            return []


async def reset_daily_activity() -> bool:
    """Сбрасывает ежедневную активность всех граждан."""
    async with await create_connection() as conn:
        if not conn:
            logger.error("Не удалось подключиться к БД для сброса ежедневной активности")
            return False

        try:
            cursor = await conn.cursor()
            await cursor.execute("UPDATE users SET user_activity = 0")
            await conn.commit()
            logger.info("Ежедневная активность всех граждан сброшена")
            return True
        except Error as e:
            logger.error(f"Ошибка при сбросе ежедневной активности: {e}")
            return False


async def get_daily_top(limit: int = 5) -> list[aiosqlite.Row]:
    """Получает топ граждан по активности за текущий день."""
    return await get_chat_leaderboard(limit)


async def get_monthly_top(limit: int = 30) -> list[aiosqlite.Row]:
    """Получает топ граждан по активности за текущий месяц."""
    # Пока что возвращаем общий топ, но в будущем можно добавить логику по месяцам
    return await get_chat_leaderboard(limit)

async def get_rate_status(user_id: int) -> str:
    """Возвращает букву ранга рейтинга (S, A, B, C, D, F)"""
    rate = await get_user_rate(user_id) or 0
    if rate >= 5000:
        return "S"
    elif 3500 <= rate <= 4999:
        return "A"
    elif 1000 <= rate <= 3499:
        return "B"
    elif 51 <= rate <= 999:
        return "C"
    elif -499 <= rate <= 50:
        return "D"
    elif rate <= -500:
        return "F"
    else:
        return "N/A"

async def get_users_by_rate_range(min_rate: int, max_rate: int | None = None) -> list[dict]:
    """
    Возвращает список пользователей, чей рейтинг находится в заданном диапазоне.
    Если max_rate не указан, берется все, что выше min_rate.
    """
    async with await create_connection() as conn:
        if not conn:
            return []
        try:
            cursor = await conn.cursor()
            if max_rate is not None:
                await cursor.execute(
                    "SELECT user_id, nickname, reputation FROM users WHERE reputation >= ? AND reputation <= ? ORDER BY reputation DESC",
                    (min_rate, max_rate)
                )
            else:
                await cursor.execute(
                    "SELECT user_id, nickname, reputation FROM users WHERE reputation >= ? ORDER BY reputation DESC",
                    (min_rate,)
                )
            rows = await cursor.fetchall()
            return [{"user_id": r[0], "nickname": r[1], "reputation": r[2]} for r in rows]
        except Error as e:
            logger.error(f"Ошибка при получении списка пользователей по диапазону рейтинга: {e}")
            return []

async def reset_user_rating(user_id: int) -> bool:
    """
    Обнуляет рейтинг пользователя (устанавливает в 0).
    Возвращает True в случае успеха.
    """
    async with await create_connection() as conn:
        if not conn:
            return False
        try:
            cursor = await conn.cursor()
            await cursor.execute("UPDATE users SET reputation = 0 WHERE user_id = ?", (user_id,))
            await conn.commit()
            if cursor.rowcount > 0:
                await _log_rating_history(user_id, 0)
                return True
            return False
        except Error as e:
            logger.error(f"Ошибка при обнулении рейтинга пользователя {user_id}: {e}")
            return False


# --- ФУНКЦИИ ДЛЯ РАБОТЫ С НАКАЗАНИЯМИ ---

async def add_warning(user_id: int, chat_id: int, reason: str, warned_by: int) -> bool:
    """
    Добавляет предупреждение гражданину в чате.
    Возвращает True если предупреждение добавлено успешно.
    """
    async with await create_connection() as conn:
        if not conn:
            logger.error("Не удалось подключиться к БД для добавления предупреждения")
            return False

        try:
            cursor = await conn.cursor()

            # Добавляем предупреждение
            await cursor.execute(
                """
                INSERT OR REPLACE INTO user_warnings (user_id, chat_id, reason, warned_by, warned_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, chat_id, reason, warned_by, datetime.utcnow().isoformat())
            )

            # Добавляем в историю наказаний
            await cursor.execute(
                """
                INSERT INTO punishment_history (user_id, chat_id, punishment_type, action, reason, moderator_id)
                VALUES (?, ?, 'warn', 'added', ?, ?)
                """,
                (user_id, chat_id, reason, warned_by)
            )

            await conn.commit()
            logger.info(f"Гражданину {user_id} в чате {chat_id} выдано предупреждение модератором {warned_by}: {reason}")
            return True

        except Error as e:
            logger.error(f"Ошибка при добавлении предупреждения гражданину {user_id}: {e}")
            return False


async def remove_warning(user_id: int, chat_id: int, removed_by: int) -> bool:
    """
    Снимает предупреждение с гражданина в чате.
    Возвращает True если предупреждение снято успешно.
    """
    async with await create_connection() as conn:
        if not conn:
            logger.error("Не удалось подключиться к БД для снятия предупреждения")
            return False

        try:
            cursor = await conn.cursor()

            # Получаем информацию о предупреждении перед удалением
            await cursor.execute(
                "SELECT reason FROM user_warnings WHERE user_id = ? AND chat_id = ?",
                (user_id, chat_id)
            )
            warning = await cursor.fetchone()

            if warning:
                reason = warning[0]

                # Удаляем предупреждение
                await cursor.execute(
                    "DELETE FROM user_warnings WHERE user_id = ? AND chat_id = ?",
                    (user_id, chat_id)
                )

                # Добавляем в историю наказаний
                await cursor.execute(
                    """
                    INSERT INTO punishment_history (user_id, chat_id, punishment_type, action, reason, moderator_id)
                    VALUES (?, ?, 'warn', 'removed', ?, ?)
                    """,
                    (user_id, chat_id, reason, removed_by)
                )

                await conn.commit()
                logger.info(f"С гражданина {user_id} в чате {chat_id} снято предупреждение модератором {removed_by}")
                return True
            else:
                logger.warning(f"У гражданина {user_id} в чате {chat_id} нет активных предупреждений")
                return False

        except Error as e:
            logger.error(f"Ошибка при снятии предупреждения с гражданина {user_id}: {e}")
            return False


async def get_warnings_count(user_id: int, chat_id: int) -> int:
    """
    Возвращает количество активных предупреждений у гражданина в чате.
    """
    async with await create_connection() as conn:
        if not conn:
            return 0

        try:
            cursor = await conn.cursor()
            await cursor.execute(
                "SELECT COUNT(*) FROM user_warnings WHERE user_id = ? AND chat_id = ?",
                (user_id, chat_id)
            )
            result = await cursor.fetchone()
            return result[0] if result else 0
        except Error as e:
            logger.error(f"Ошибка при получении количества предупреждений гражданина {user_id}: {e}")
            return 0


async def add_punishment(user_id: int, chat_id: int, punishment_type: str, reason: str, punished_by: int, duration_minutes: int = None) -> bool:
    """
    Добавляет наказание гражданину.
    punishment_type: 'ban', 'mute', 'warn'
    duration_minutes: None для перманентных наказаний
    Возвращает True если наказание добавлено успешно.
    """
    async with await create_connection() as conn:
        if not conn:
            logger.error("Не удалось подключиться к БД для добавления наказания")
            return False

        try:
            cursor = await conn.cursor()

            expires_at = None
            if duration_minutes:
                expires_at = (datetime.utcnow() + timedelta(minutes=duration_minutes)).isoformat()

            # Добавляем активное наказание
            await cursor.execute(
                """
                INSERT OR REPLACE INTO active_punishments (user_id, chat_id, punishment_type, reason, punished_by, punished_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, chat_id, punishment_type, reason, punished_by, datetime.utcnow().isoformat(), expires_at)
            )

            # Добавляем в историю наказаний
            await cursor.execute(
                """
                INSERT INTO punishment_history (user_id, chat_id, punishment_type, action, reason, moderator_id, duration_minutes)
                VALUES (?, ?, ?, 'added', ?, ?, ?)
                """,
                (user_id, chat_id, punishment_type, reason, punished_by, duration_minutes)
            )

            await conn.commit()
            duration_text = f"на {duration_minutes} минут" if duration_minutes else "перманентно"
            logger.info(f"Гражданину {user_id} в чате {chat_id} выдано наказание '{punishment_type}' {duration_text} модератором {punished_by}: {reason}")
            return True

        except Error as e:
            logger.error(f"Ошибка при добавлении наказания гражданину {user_id}: {e}")
            return False


async def remove_punishment(user_id: int, chat_id: int, punishment_type: str, removed_by: int) -> bool:
    """
    Снимает наказание с гражданина.
    Возвращает True если наказание снято успешно.
    """
    async with await create_connection() as conn:
        if not conn:
            logger.error("Не удалось подключиться к БД для снятия наказания")
            return False

        try:
            cursor = await conn.cursor()

            # Получаем информацию о наказании перед удалением
            await cursor.execute(
                "SELECT reason FROM active_punishments WHERE user_id = ? AND chat_id = ? AND punishment_type = ? AND is_active = 1",
                (user_id, chat_id, punishment_type)
            )
            punishment = await cursor.fetchone()

            if punishment:
                reason = punishment[0]

                # Удаляем наказание
                await cursor.execute(
                    "UPDATE active_punishments SET is_active = 0 WHERE user_id = ? AND chat_id = ? AND punishment_type = ?",
                    (user_id, chat_id, punishment_type)
                )

                # Добавляем в историю наказаний
                await cursor.execute(
                    """
                    INSERT INTO punishment_history (user_id, chat_id, punishment_type, action, reason, moderator_id)
                    VALUES (?, ?, ?, 'removed', ?, ?)
                    """,
                    (user_id, chat_id, punishment_type, reason, removed_by)
                )

                await conn.commit()
                logger.info(f"С гражданина {user_id} в чате {chat_id} снято наказание '{punishment_type}' модератором {removed_by}")
                return True
            else:
                logger.warning(f"У гражданина {user_id} в чате {chat_id} нет активного наказания '{punishment_type}'")
                return False

        except Error as e:
            logger.error(f"Ошибка при снятии наказания с гражданина {user_id}: {e}")
            return False


async def get_active_punishments(user_id: int, chat_id: int) -> list[dict]:
    """
    Возвращает список активных наказаний гражданина в чате.
    """
    async with await create_connection() as conn:
        if not conn:
            return []

        try:
            cursor = await conn.cursor()
            await cursor.execute(
                "SELECT punishment_type, reason, punished_by, punished_at, expires_at FROM active_punishments WHERE user_id = ? AND chat_id = ? AND is_active = 1",
                (user_id, chat_id)
            )
            punishments = await cursor.fetchall()

            result = []
            for punishment in punishments:
                result.append({
                    'type': punishment[0],
                    'reason': punishment[1],
                    'punished_by': punishment[2],
                    'punished_at': punishment[3],
                    'expires_at': punishment[4]
                })
            return result

        except Error as e:
            logger.error(f"Ошибка при получении активных наказаний гражданина {user_id}: {e}")
            return []


async def get_expired_punishments() -> list[dict]:
    """
    Возвращает список истекших наказаний для автоматического снятия.
    """
    async with await create_connection() as conn:
        if not conn:
            return []

        try:
            cursor = await conn.cursor()
            await cursor.execute(
                """
                SELECT user_id, chat_id, punishment_type, reason, punished_by
                FROM active_punishments
                WHERE expires_at IS NOT NULL AND expires_at < ? AND is_active = 1
                """,
                (datetime.utcnow().isoformat(),)
            )
            punishments = await cursor.fetchall()

            result = []
            for punishment in punishments:
                result.append({
                    'user_id': punishment[0],
                    'chat_id': punishment[1],
                    'type': punishment[2],
                    'reason': punishment[3],
                    'punished_by': punishment[4]
                })
            return result

        except Error as e:
            logger.error(f"Ошибка при получении истекших наказаний: {e}")
            # Если таблица не существует, возвращаем пустой список
            return []



