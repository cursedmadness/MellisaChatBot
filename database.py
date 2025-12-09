import sqlite3
from sqlite3 import Error
from datetime import datetime, timedelta
import logging

from config import MAX_RICE_PER_USER

logger = logging.getLogger(__name__)

DB_NAME = "users.db"  # Имя файла БД

def create_connection():
     """Создаёт соединение с БД."""
     conn = None
     try:
         conn = sqlite3.connect(DB_NAME)
         # Убрал print, чтобы не засорять вывод при каждом вызове
     except Error as e:
         print(e)
     return conn

def create_table():
    """Создаёт таблицу users и admins и waifu_cats, если её нет."""
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    nickname TEXT,
                    username TEXT
                )
             ''')
            cursor.execute('''CREATE TABLE IF NOT EXISTS waifu_cat (
                cats_id INTEGER PRIMARY KEY,
                user_id INTEGER UNIQUE NOT NULL,
                cat_name TEXT,
                category_cats TEXT CHECK(category_cats IN ('loli', 'students', 'MILF')),
                date_cat TEXT,
                satiety INTEGER DEFAULT 100,
                miska_risa INTEGER DEFAULT 0,
                mood TEXT,
                image_cats TEXT,
                age_days INTEGER DEFAULT 1,
                last_age_update TEXT,
                last_satiety_update TEXT
            )''')

            cursor.execute('''
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
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_hebao_user_item ON hebao_items(user_id, item_key)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_hebao_quantity ON hebao_items(quantity)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_activity ON users(user_activity)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_waifu_user ON waifu_cat(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_admins_user ON admins(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_chat_rules_chat ON chat_rules(chat_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_warnings_user_chat ON user_warnings(user_id, chat_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_punishments_user_chat ON active_punishments(user_id, chat_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_punishment_history_user ON punishment_history(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_punishment_history_timestamp ON punishment_history(timestamp)')

            # Добавляем колонку для отслеживания последней ежедневной выдачи риса
            try:
                cursor.execute('ALTER TABLE hebao_items ADD COLUMN last_rice_given TEXT')
            except sqlite3.OperationalError:
                # Колонка уже существует
                pass

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_rules (
                    chat_id INTEGER PRIMARY KEY,
                    rules_text TEXT NOT NULL,
                    created_by INTEGER,
                    created_at TEXT,
                    updated_by INTEGER,
                    updated_at TEXT
                )
            ''')

            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY,
                    first_name TEXT
                )
            ''')
            conn.commit()
            print("Проверка/создание таблицы 'users, admins, waifu_cats, chat_rules' выполнено.")
        except Error as e:
            print(e)
        finally:
            conn.close()

# --- НОВАЯ ФУНКЦИЯ ДЛЯ ДОБАВЛЕНИЯ СТОЛБЦОВ ---
def add_new_columns():
    """
    Добавляет новые столбцы (Description, Reputation, User_activity)
    в таблицу users, если они еще не существуют.
    А также дополнительные поля для waifu_cat из требований роутера.
    Также создает таблицы для системы модерации.
    """
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()

            # Создаем таблицы модерации, если они не существуют
            # Таблица для предупреждений (варнов)
            cursor.execute('''
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
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS active_punishments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    punishment_type TEXT NOT NULL, -- 'ban', 'mute', 'warn'
                    reason TEXT,
                    punished_by INTEGER NOT NULL,
                    punished_at TEXT DEFAULT (datetime('now')),
                    expires_at TEXT, -- NULL для перманентных наказаний
                    UNIQUE(user_id, chat_id, punishment_type)
                )
            ''')

            # Таблица истории наказаний
            cursor.execute('''
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
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_warnings_user_chat ON user_warnings(user_id, chat_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_punishments_user_chat ON active_punishments(user_id, chat_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_punishment_history_user ON punishment_history(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_punishment_history_timestamp ON punishment_history(timestamp)')
            
            # Словарь: имя_столбца -> тип_данных_и_ограничения
            columns_users = {
                "description": "TEXT(25)",
                "reputation": "INTEGER DEFAULT 0",
                "user_activity": "INTEGER DEFAULT 0",
                "username": "TEXT"
            }
            
            for column_name, column_def in columns_users.items():
                try:
                    # Пытаемся добавить каждый столбец
                    cursor.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_def}")
                    print(f"Столбец '{column_name}' успешно добавлен.")
                except sqlite3.OperationalError as e:
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
            }

            for column_name, column_def in columns_waifu.items():
                try:
                    cursor.execute(f"ALTER TABLE waifu_cat ADD COLUMN {column_name} {column_def}")
                    print(f"Столбец '{column_name}' успешно добавлен в waifu_cat.")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e):
                        pass
                    else:
                        raise e

            conn.commit()
        except Error as e:
            print(f"Произошла ошибка при добавлении столбцов: {e}")
        finally:
            conn.close()


# --- Функции для хэбао (инвентарь) ---

def _hebao_row_to_dict(row):
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


def get_hebao_items(user_id: int) -> list[dict]:
    """Возвращает список предметов хэбао пользователя (только с количеством > 0)."""
    conn = create_connection()
    if not conn:
        return []
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT item_id, user_id, item_key, item_name, quantity, updated_at
            FROM hebao_items
            WHERE user_id = ? AND quantity > 0
            ORDER BY item_name
            """,
            (user_id,),
        )
        rows = cursor.fetchall()
        return [_hebao_row_to_dict(r) for r in rows if r]
    except Error as e:
        print(e)
        return []
    finally:
        conn.close()


def upsert_hebao_item(
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

    conn = create_connection()
    if not conn:
        return False

    try:
        cursor = conn.cursor()
        now_iso = datetime.utcnow().isoformat()
        display_name = item_name or item_key

        if set_value is not None:
            new_qty = max(int(set_value), 0)
        else:
            cursor.execute(
                "SELECT quantity FROM hebao_items WHERE user_id = ? AND item_key = ?",
                (user_id, item_key),
            )
            row = cursor.fetchone()
            current_qty = row[0] if row else 0
            delta_val = int(delta or 0)
            new_qty = current_qty + delta_val
            if new_qty < 0:
                new_qty = 0

        cursor.execute(
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
        conn.commit()
        return True
    except Error as e:
        print(e)
        return False
    finally:
        conn.close()


def get_hebao_overview(user_id: int, merge_waifu_rice: bool = True) -> list[dict]:
    """
    Возвращает список предметов в хэбао.
    При merge_waifu_rice дополнительно добавляет миски риса из профиля кошки.
    """
    items = get_hebao_items(user_id)
    items_by_key = {item["item_key"]: item for item in items if item}

    if merge_waifu_rice:
        waifu = get_waifu_by_user(user_id)
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

def _waifu_row_to_dict(row):
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
    }


def create_waifu_for_user(user_id: int, cat_name: str = "мяу", category: str = "students", mood: str = "отличное"):
    """
    Создаёт запись кошко-жены для пользователя, если её ещё нет.
    Поле date_cat сохраняем в ISO-формате.
    Теперь выдает 1 миску риса при создании.
    """
    if category not in ("loli", "students", "MILF"):
        category = "students"

    conn = create_connection()
    if not conn:
        return False

    try:
        cursor = conn.cursor()
        now_iso = datetime.utcnow().isoformat()

        # Проверяем, есть ли уже кошка
        cursor.execute("SELECT user_id FROM waifu_cat WHERE user_id = ?", (user_id,))
        existing_waifu = cursor.fetchone()

        cursor.execute(
            """
            INSERT OR IGNORE INTO waifu_cat (user_id, cat_name, category_cats, date_cat, age_days, last_age_update, mood, satiety, last_satiety_update)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, cat_name, category, now_iso, 1, now_iso, mood, 100, now_iso),
        )

        created = cursor.rowcount > 0

        # Если кошка создана впервые, убеждаемся что есть 1 миска риса
        if created:
            upsert_hebao_item(user_id, "miska_risa", "миска риса", set_value=1)
            logger.info(f"Кошка создана для пользователя {user_id}, выдана 1 миска риса")

        conn.commit()
        return created
    except Error as e:
        logger.error(f"Ошибка при создании кошки для user_id {user_id}: {e}")
        return False
    finally:
        conn.close()


def get_waifu_by_user(user_id: int):
    """Возвращает словарь с данными кошко-жены пользователя или None."""
    conn = create_connection()
    if not conn:
        return None
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT cats_id, user_id, cat_name, category_cats, date_cat,
                   satiety, mood, image_cats, age_days, last_age_update, last_satiety_update
            FROM waifu_cat WHERE user_id = ?
            """,
            (user_id,),
        )
        row = cursor.fetchone()
        return _waifu_row_to_dict(row)
    except Error as e:
        print(e)
        return None
    finally:
        conn.close()


def update_cat_name(user_id: int, new_name: str) -> bool:
    """Обновляет кличку кошко-жены пользователя. Возвращает True, если обновлено."""
    conn = create_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE waifu_cat SET cat_name = ? WHERE user_id = ?",
            (new_name, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    except Error as e:
        print(e)
        return False
    finally:
        conn.close()


def update_cat_image(user_id: int, image_path: str) -> bool:
    """Сохраняет путь к изображению кошко-жены."""
    conn = create_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE waifu_cat SET image_cats = ? WHERE user_id = ?",
            (image_path, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    except Error as e:
        print(e)
        return False
    finally:
        conn.close()


def update_cat_state(user_id: int, *, satiety: int | None = None,
                    mood: str | None = None, last_satiety_update: str | None = None) -> bool:
    """
    Универсальное обновление динамических полей кошко-жены.
    Обновляет только переданные параметры.
    Примечание: miska_risa больше не используется, рис хранится в hebao_items.
    """
    conn = create_connection()
    if not conn:
        return False

    fields = []
    values = []
    if satiety is not None:
        fields.append("satiety = ?")
        values.append(satiety)
    if mood is not None:
        fields.append("mood = ?")
        values.append(mood)
    if last_satiety_update is not None:
        fields.append("last_satiety_update = ?")
        values.append(last_satiety_update)

    if not fields:
        return False

    values.append(user_id)

    try:
        cursor = conn.cursor()
        cursor.execute(
            f"UPDATE waifu_cat SET {', '.join(fields)} WHERE user_id = ?",
            tuple(values),
        )
        conn.commit()
        return cursor.rowcount > 0
    except Error as e:
        logger.error(f"Ошибка обновления состояния кошки для user_id {user_id}: {e}")
        return False
    finally:
        conn.close()


def update_waifu_age(user_id: int, new_age: int, last_update_iso: str) -> bool:
    """Обновляет возраст и метку обновления."""
    conn = create_connection()
    if not conn:
        return False
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE waifu_cat SET age_days = ?, last_age_update = ?
            WHERE user_id = ?
            """,
            (new_age, last_update_iso, user_id),
        )
        conn.commit()
        return cursor.rowcount > 0
    except Error as e:
        print(e)
        return False
    finally:
        conn.close()
            
# --- ОСТАЛЬНЫЕ ВАШИ ФУНКЦИИ (без изменений) ---

def add_user(user_id: int, nickname: str, username: str | None = None):
    """
    Добавляет гражданина в БД с указанным ником и username.
    При повторном добавлении обновляет username.
    Также выдает 1 миску риса новым гражданам.
    """
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()

            # Проверяем, новый ли гражданин
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            existing_user = cursor.fetchone()

            if existing_user:
                # Гражданин уже существует, обновляем только username
                cursor.execute(
                    "UPDATE users SET username = ? WHERE user_id = ?",
                    (username, user_id),
                )
            else:
                # Новый гражданин - добавляем с рейтингом 100
                cursor.execute(
                    """
                    INSERT INTO users (user_id, nickname, username, reputation)
                    VALUES (?, ?, ?, ?)
                    """,
                    (user_id, nickname, username, 100),
                )
                # Выдаем 1 миску риса
                upsert_hebao_item(user_id, "miska_risa", "миска риса", set_value=1)
                logger.info(f"Новому гражданину {user_id} (@{username or 'нет'}) установлен рейтинг 100 и выдана 1 миска риса")

            conn.commit()
        except Error as e:
            logger.error(f"Ошибка при добавлении гражданина {user_id}: {e}")
        finally:
            conn.close()

def get_user_nickname(user_id: int) -> str:
    """Получает ник гражданина."""
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT nickname FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            return result[0] if result else None
        except Error as e:
            print(e)
        finally:
            conn.close()
    return None

def set_user_nickname(user_id: int, nickname: str):
    """Устанавливает ник гражданина."""
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET nickname = ? WHERE user_id = ?", (nickname, user_id))
            conn.commit()
            print(f"Ник для {user_id} установлен: {nickname}")
        except Error as e:
            print(e)
        finally:
            conn.close()

def get_user_profile(user_id: int):
    """Получает все данные гражданина для анкеты."""
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            # Выбираем все нужные поля одним запросом
            cursor.execute("""
                SELECT nickname, description, reputation, user_activity
                FROM users WHERE user_id = ?
            """, (user_id,))
            result = cursor.fetchone()
            if result:
                # Возвращаем данные в виде удобного словаря
                profile_data = {
                    "nickname": result[0],
                    "description": result[1],
                    "reputation": result[2],
                    "activity": result[3]
                }
                return profile_data
        except Error as e:
            print(e)
        finally:
            conn.close()
    return None


def get_user_by_username(username: str) -> int | None:
    """Ищет user_id по username в базе данных."""
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE username = ?", (username,))
            result = cursor.fetchone()
            return result[0] if result else None
        except Error as e:
            print(e)
        finally:
            conn.close()
    return None


def get_all_users() -> list[dict]:
    """
    Возвращает список всех граждан из базы данных.
    Каждый гражданин представлен словарем с полями: user_id, nickname, username.
    """
    conn = create_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, nickname, username FROM users ORDER BY user_id")
        rows = cursor.fetchall()

        users = []
        for row in rows:
            users.append({
                "user_id": row[0],
                "nickname": row[1] or "нет",
                "username": row[2] or "нет"
            })

        return users

    except Error as e:
        print(f"Ошибка при получении списка пользователей: {e}")
        return []
    finally:
        conn.close()


def update_user_username(user_id: int, username: str | None) -> bool:
    """
    Обновляет username гражданина в базе данных.
    """
    conn = create_connection()
    if not conn:
        return False

    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET username = ? WHERE user_id = ?",
            (username, user_id)
        )
        conn.commit()
        return cursor.rowcount > 0
    except Error as e:
        print(f"Ошибка при обновлении username для user_id {user_id}: {e}")
        return False
    finally:
        conn.close()


def delete_user_completely(username: str) -> bool:
    """
    Полностью удаляет гражданина из системы по username.
    Удаляет записи из всех таблиц: users, waifu_cat, hebao_items, admins.
    Возвращает True если успешно удален хотя бы один гражданин.
    """
    logger.info(f"Начинаем удаление гражданина @{username}")

    # Сначала найдем user_id
    user_id = get_user_by_username(username)
    if not user_id:
        logger.warning(f"Гражданин @{username} не найден в базе данных")
        return False

    conn = create_connection()
    if not conn:
        return False

    try:
        cursor = conn.cursor()

        # Удаляем из всех таблиц
        tables_to_clean = ['hebao_items', 'waifu_cat', 'admins', 'users']
        deleted_records = 0

        for table in tables_to_clean:
            if table == 'users':
                cursor.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
            else:
                cursor.execute(f"DELETE FROM {table} WHERE user_id = ?", (user_id,))
            deleted_records += cursor.rowcount
            if cursor.rowcount > 0:
                print(f"Удалено {cursor.rowcount} записей из таблицы {table} для гражданина @{username} (ID: {user_id})")

        conn.commit()

        if deleted_records > 0:
            logger.info(f"Пользователь @{username} (ID: {user_id}) полностью удален из системы. Всего удалено {deleted_records} записей")
            return True
        else:
            logger.warning(f"Не найдено записей для удаления пользователя @{username} (ID: {user_id})")
            return False

    except Error as e:
        logger.error(f"Ошибка при удалении пользователя @{username}: {e}")
        return False
    finally:
        conn.close()


# --- Функции для работы с правилами чата ---

def save_chat_rules(chat_id: int, rules_text: str, user_id: int) -> bool:
    """
    Сохраняет или обновляет правила чата.
    Возвращает True при успехе.
    """
    conn = create_connection()
    if not conn:
        logger.error("Не удалось подключиться к базе данных")
        return False

    try:
        cursor = conn.cursor()
        now_iso = datetime.utcnow().isoformat()

        cursor.execute('''
            INSERT INTO chat_rules (chat_id, rules_text, created_by, created_at, updated_by, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                rules_text = excluded.rules_text,
                updated_by = excluded.updated_by,
                updated_at = excluded.updated_at
        ''', (chat_id, rules_text, user_id, now_iso, user_id, now_iso))

        conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"Правила чата {chat_id} сохранены пользователем {user_id}")
            return True
        else:
            logger.warning(f"Не удалось сохранить правила чата {chat_id}")
            return False

    except Error as e:
        logger.error(f"Ошибка при сохранении правил чата {chat_id}: {e}")
        return False
    finally:
        conn.close()


def get_chat_rules(chat_id: int) -> str | None:
    """
    Получает правила чата по chat_id.
    Возвращает текст правил или None если правил нет.
    """
    conn = create_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT rules_text FROM chat_rules WHERE chat_id = ?", (chat_id,))
        result = cursor.fetchone()
        return result[0] if result else None

    except Error as e:
        print(f"Ошибка при получении правил чата {chat_id}: {e}")
        return None
    finally:
        conn.close()


def get_chat_rules_info(chat_id: int) -> dict | None:
    """
    Получает полную информацию о правилах чата.
    Возвращает словарь с данными или None.
    """
    conn = create_connection()
    if not conn:
        return None

    try:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT rules_text, created_by, created_at, updated_by, updated_at
            FROM chat_rules WHERE chat_id = ?
        ''', (chat_id,))

        result = cursor.fetchone()
        if result:
            return {
                "rules_text": result[0],
                "created_by": result[1],
                "created_at": result[2],
                "updated_by": result[3],
                "updated_at": result[4]
            }
        return None

    except Error as e:
        print(f"Ошибка при получении информации о правилах чата {chat_id}: {e}")
        return None
    finally:
        conn.close()


# --- Функции для ежедневной выдачи риса ---

def get_user_rice_count(user_id: int) -> int:
    """
    Получает количество мисок риса у пользователя.
    Возвращает 0 если риса нет.
    """
    conn = create_connection()
    if not conn:
        return 0

    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT quantity FROM hebao_items WHERE user_id = ? AND item_key = 'miska_risa'",
            (user_id,)
        )
        result = cursor.fetchone()
        return result[0] if result else 0

    except Error as e:
        logger.error(f"Ошибка при получении количества риса для user_id {user_id}: {e}")
        return 0
    finally:
        conn.close()


def give_daily_rice(user_id: int) -> bool:
    """
    Выдает 1 миску риса пользователю, если у него меньше максимального количества.
    Обновляет время последней выдачи.
    Возвращает True если рис был выдан.
    """
    rice_count = get_user_rice_count(user_id)

    if rice_count >= MAX_RICE_PER_USER:
        logger.info(f"Пользователь {user_id} имеет {rice_count} мисок риса (>={MAX_RICE_PER_USER}), ежедневная выдача пропущена")
        return False

    # Выдаем 1 миску риса
    success = upsert_hebao_item(user_id, "miska_risa", "миска риса", delta=1)

    if success:
        # Обновляем время последней выдачи
        conn = create_connection()
        if conn:
            try:
                cursor = conn.cursor()
                now_iso = datetime.utcnow().isoformat()
                cursor.execute(
                    "UPDATE hebao_items SET last_rice_given = ? WHERE user_id = ? AND item_key = 'miska_risa'",
                    (now_iso, user_id)
                )
                conn.commit()
                logger.info(f"Пользователю {user_id} выдана 1 миска риса (было {rice_count}, стало {rice_count + 1})")
            except Error as e:
                logger.error(f"Ошибка обновления last_rice_given для user_id {user_id}: {e}")
            finally:
                conn.close()

        return True

    return False


def reset_all_rice_to_one() -> int:
    """
    Обнуляет количество риса у всех граждан до 1 миски.
    Возвращает количество обновленных граждан.
    """
    conn = create_connection()
    if not conn:
        logger.error("Не удалось подключиться к БД для сброса риса")
        return 0

    try:
        cursor = conn.cursor()

        # Получаем всех граждан с рисом
        cursor.execute("SELECT user_id, quantity FROM hebao_items WHERE item_key = 'miska_risa' AND quantity > 1")
        users_with_rice = cursor.fetchall()

        updated_count = 0
        for user_id, current_quantity in users_with_rice:
            # Обновляем до 1 миски
            cursor.execute(
                "UPDATE hebao_items SET quantity = 1, updated_at = ? WHERE user_id = ? AND item_key = 'miska_risa'",
                (datetime.utcnow().isoformat(), user_id)
            )
            if cursor.rowcount > 0:
                updated_count += 1
                logger.info(f"Пользователь {user_id}: рис сброшен с {current_quantity} до 1 миски")

        # Добавляем 1 миску риса гражданам, у которых ее нет вообще
        cursor.execute("SELECT user_id FROM users WHERE user_id NOT IN (SELECT user_id FROM hebao_items WHERE item_key = 'miska_risa')")
        users_without_rice = cursor.fetchall()

        for (user_id,) in users_without_rice:
            upsert_hebao_item(user_id, "miska_risa", "миска риса", set_value=1)
            updated_count += 1
            logger.info(f"Пользователь {user_id}: добавлена 1 миска риса")

        conn.commit()
        logger.info(f"Сброс риса завершен. Обновлено {updated_count} граждан")

        return updated_count

    except Error as e:
        logger.error(f"Ошибка при сбросе риса: {e}")
        return 0
    finally:
        conn.close()


def reset_all_ratings_to_default(default_rating: int = 100) -> int:
    """
    Сбрасывает рейтинг всех граждан до значения по умолчанию (100).
    Возвращает количество обновленных граждан.
    """
    conn = create_connection()
    if not conn:
        logger.error("Не удалось подключиться к БД для сброса рейтинга")
        return 0

    try:
        cursor = conn.cursor()

        # Получаем всех граждан с текущим рейтингом
        cursor.execute("SELECT user_id, reputation FROM users")
        all_users = cursor.fetchall()

        updated_count = 0
        for user_id, current_rating in all_users:
            if current_rating != default_rating:
                cursor.execute(
                    "UPDATE users SET reputation = ? WHERE user_id = ?",
                    (default_rating, user_id)
                )
                if cursor.rowcount > 0:
                    updated_count += 1
                    logger.info(f"Гражданин {user_id}: рейтинг сброшен с {current_rating} до {default_rating}")

        conn.commit()
        logger.info(f"Сброс рейтинга завершен. Обновлено {updated_count} граждан до {default_rating}")

        return updated_count

    except Error as e:
        logger.error(f"Ошибка при сбросе рейтинга: {e}")
        return 0
    finally:
        conn.close()


def initialize_default_ratings(default_rating: int = 100) -> int:
    """
    Устанавливает рейтинг по умолчанию (100) всем гражданам, у которых рейтинг еще не установлен.
    Используется для первичной инициализации.
    Возвращает количество обновленных граждан.
    """
    conn = create_connection()
    if not conn:
        logger.error("Не удалось подключиться к БД для инициализации рейтинга")
        return 0

    try:
        cursor = conn.cursor()

        # Обновляем граждан, у которых рейтинг NULL или 0
        cursor.execute(
            "UPDATE users SET reputation = ? WHERE reputation IS NULL OR reputation = 0",
            (default_rating,)
        )

        updated_count = cursor.rowcount
        conn.commit()

        if updated_count > 0:
            logger.info(f"Инициализация рейтинга завершена. Установлено {default_rating} рейтинга для {updated_count} граждан")

        return updated_count

    except Error as e:
        logger.error(f"Ошибка при инициализации рейтинга: {e}")
        return 0
    finally:
        conn.close()


def process_daily_rice_distribution() -> int:
    """
    Обрабатывает ежедневную выдачу риса всем гражданам.
    Вызывается раз в сутки.
    Возвращает количество пользователей, которым был выдан рис.
    """
    logger.info("Начинается ежедневная выдача риса")

    conn = create_connection()
    if not conn:
        logger.error("Не удалось подключиться к БД для ежедневной выдачи риса")
        return 0

    try:
        cursor = conn.cursor()

        # Получаем всех граждан
        cursor.execute("SELECT user_id FROM users")
        all_users = cursor.fetchall()

        distributed_count = 0

        for (user_id,) in all_users:
            if give_daily_rice(user_id):
                distributed_count += 1

        logger.info(f"Ежедневная выдача риса завершена. Выдано {distributed_count} гражданам")
        return distributed_count

    except Error as e:
        logger.error(f"Ошибка при ежедневной выдаче риса: {e}")
        return 0
    finally:
        conn.close()


def set_user_description(user_id: int, description: str):
    """Устанавливает или обновляет описание пользователя."""
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            # Название столбца 'Описание' берем из предыдущего шага
            cursor.execute("UPDATE users SET description = ? WHERE user_id = ?", (description, user_id))
            conn.commit()
            print(f"Описание для {user_id} установлено.")
        except Error as e:
            print(e)
        finally:
            conn.close()

def add_admin(user_id: int, first_name: str):
    """Добавляет администратора в таблицу admins."""
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO admins (user_id, first_name) VALUES (?, ?)", (user_id, first_name))
            conn.commit()
            print(f"Администратор {user_id} добавлен с именем {first_name}")
        except Error as e:
            print(e)
        finally:
            conn.close()

def remove_admin(user_id: int):
    """Удаляет администратора из таблицы admins."""
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
            conn.commit()
            print(f"Администратор {user_id} удалён")
        except Error as e:
            print(e)
        finally:
            conn.close()

def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором."""
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            return bool(result)
        except Error as e:
            print(e)
        finally:
            conn.close()
    return False

def get_all_admins() -> list:
    """Получает список всех администраторов (user_id и first_name)."""
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, first_name FROM admins")
            return cursor.fetchall()  # Возвращает список кортежей [(user_id, first_name), ...]
        except Error as e:
            print(e)
        finally:
            conn.close()
    return []

def initialize_admins(admin_ids: list):
    """Инициализирует таблицу admins из списка ADMIN_IDS, если она пуста."""
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM admins")
            count = cursor.fetchone()[0]
            if count == 0:
                for user_id in admin_ids:
                    add_admin(user_id, "Администратор")  # Placeholder first_name; можно заменить на реальное через API
                print("Таблица admins инициализирована из ADMIN_IDS")
        except Error as e:
            print(e)
        finally:
            conn.close()


def get_user_description(user_id: int):
    """Получает описание пользователя из БД."""
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT description FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            # Возвращаем описание (result[0]) если оно есть, иначе None
            return result[0] if result else None
        except Error as e:
            print(e)
        finally:
            conn.close()
    return None

def get_user_rate(user_id: int) -> int:
    conn = create_connection()
    cursor = conn.cursor()
    try:
    
        cursor.execute('SELECT reputation FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()

        return result[0] if result else None
    except Error as e:
        print(e)
    finally:
        conn.close()


def update_user_rate(user_id: int, rate: int):
    conn = create_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
        UPDATE users SET reputation = ? WHERE user_id = ?
    ''', (rate, user_id))
        conn.commit()
    except Exception as e:
        print(e)
    finally:
        conn.close()

def unrate_user(user_id: int, rate: int):
    conn = create_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
        UPDATE users SET reputation = ? WHERE user_id = ?
    ''', (rate, user_id))
        conn.commit()
    except Exception as e:
        print(e)
    finally:
        conn.close()


def increment_user_activity(user_id: int) -> bool:
    """Увеличивает счётчик активности гражданина на 1."""
    conn = create_connection()
    if not conn:
        logger.error("Не удалось подключиться к БД для увеличения активности")
        return False

    try:
        cursor = conn.cursor()
        # Используем SQL для атомарного увеличения значения
        cursor.execute("""
            UPDATE users
            SET user_activity = user_activity + 1
            WHERE user_id = ?
        """, (user_id,))

        if cursor.rowcount == 0:
            # Гражданин не найден, создаем его
            logger.warning(f"Гражданин {user_id} не найден при увеличении активности, создаем")
            add_user(user_id, "пользователь")
            # Повторяем попытку
            cursor.execute("""
                UPDATE users
                SET user_activity = user_activity + 1
                WHERE user_id = ?
            """, (user_id,))

        conn.commit()
        return True

    except Error as e:
        logger.error(f"Ошибка при инкременте активности гражданина {user_id}: {e}")
        return False
    finally:
        conn.close()

def get_chat_leaderboard(limit: int = 10):
    """Получает топ граждан по активности."""
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            # Выбираем ник и активность, сортируем по убыванию активности
            # LIMIT ограничивает вывод, чтобы не спамить в чат
            cursor.execute("""
                SELECT nickname, User_activity
                FROM users
                WHERE User_activity > 0
                ORDER BY User_activity DESC
                LIMIT ?
            """, (limit,))
            # Возвращаем список кортежей (ник, активность)
            return cursor.fetchall()
        except Error as e:
            logger.error(f"Ошибка при получении лидерборда: {e}")
        finally:
            conn.close()
    return []


def reset_daily_activity():
    """Сбрасывает ежедневную активность всех граждан."""
    conn = create_connection()
    if not conn:
        logger.error("Не удалось подключиться к БД для сброса ежедневной активности")
        return False

    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET user_activity = 0")
        conn.commit()
        logger.info("Ежедневная активность всех граждан сброшена")
        return True
    except Error as e:
        logger.error(f"Ошибка при сбросе ежедневной активности: {e}")
        return False
    finally:
        conn.close()


def get_daily_top(limit: int = 5) -> list[tuple[str, int]]:
    """Получает топ граждан по активности за текущий день."""
    return get_chat_leaderboard(limit)


def get_monthly_top(limit: int = 30) -> list[tuple[str, int]]:
    """Получает топ граждан по активности за текущий месяц."""
    # Пока что возвращаем общий топ, но в будущем можно добавить логику по месяцам
    return get_chat_leaderboard(limit)

def get_rate_status(user_id: int) -> str:
    """Возвращает букву ранга рейтинга (S, A, B, C, D, F)"""
    rate = get_user_rate(user_id)
    if rate >= 5001:
        return "S"
    elif 3501 <= rate <= 5000:
        return "A"
    elif 1001 <= rate <= 3500:
        return "B"
    elif 51 <= rate <= 1000:
        return "C"
    elif -499 <= rate <= 50:
        return "D"
    elif rate <= -500:
        return "F"
    else:
        return "N/A"  # на случай, если rate None или что-то не так


# --- ФУНКЦИИ ДЛЯ РАБОТЫ С НАКАЗАНИЯМИ ---

def add_warning(user_id: int, chat_id: int, reason: str, warned_by: int) -> bool:
    """
    Добавляет предупреждение гражданину в чате.
    Возвращает True если предупреждение добавлено успешно.
    """
    conn = create_connection()
    if not conn:
        logger.error("Не удалось подключиться к БД для добавления предупреждения")
        return False

    try:
        cursor = conn.cursor()

        # Добавляем предупреждение
        cursor.execute(
            """
            INSERT OR REPLACE INTO user_warnings (user_id, chat_id, reason, warned_by, warned_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, chat_id, reason, warned_by, datetime.utcnow().isoformat())
        )

        # Добавляем в историю наказаний
        cursor.execute(
            """
            INSERT INTO punishment_history (user_id, chat_id, punishment_type, action, reason, moderator_id)
            VALUES (?, ?, 'warn', 'added', ?, ?)
            """,
            (user_id, chat_id, reason, warned_by)
        )

        conn.commit()
        logger.info(f"Гражданину {user_id} в чате {chat_id} выдано предупреждение модератором {warned_by}: {reason}")
        return True

    except Error as e:
        logger.error(f"Ошибка при добавлении предупреждения гражданину {user_id}: {e}")
        return False
    finally:
        conn.close()


def remove_warning(user_id: int, chat_id: int, removed_by: int) -> bool:
    """
    Снимает предупреждение с гражданина в чате.
    Возвращает True если предупреждение снято успешно.
    """
    conn = create_connection()
    if not conn:
        logger.error("Не удалось подключиться к БД для снятия предупреждения")
        return False

    try:
        cursor = conn.cursor()

        # Получаем информацию о предупреждении перед удалением
        cursor.execute(
            "SELECT reason FROM user_warnings WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        )
        warning = cursor.fetchone()

        if warning:
            reason = warning[0]

            # Удаляем предупреждение
            cursor.execute(
                "DELETE FROM user_warnings WHERE user_id = ? AND chat_id = ?",
                (user_id, chat_id)
            )

            # Добавляем в историю наказаний
            cursor.execute(
                """
                INSERT INTO punishment_history (user_id, chat_id, punishment_type, action, reason, moderator_id)
                VALUES (?, ?, 'warn', 'removed', ?, ?)
                """,
                (user_id, chat_id, reason, removed_by)
            )

            conn.commit()
            logger.info(f"С гражданина {user_id} в чате {chat_id} снято предупреждение модератором {removed_by}")
            return True
        else:
            logger.warning(f"У гражданина {user_id} в чате {chat_id} нет активных предупреждений")
            return False

    except Error as e:
        logger.error(f"Ошибка при снятии предупреждения с гражданина {user_id}: {e}")
        return False
    finally:
        conn.close()


def get_warnings_count(user_id: int, chat_id: int) -> int:
    """
    Возвращает количество активных предупреждений у гражданина в чате.
    """
    conn = create_connection()
    if not conn:
        return 0

    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM user_warnings WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        )
        result = cursor.fetchone()
        return result[0] if result else 0
    except Error as e:
        logger.error(f"Ошибка при получении количества предупреждений гражданина {user_id}: {e}")
        return 0
    finally:
        conn.close()


def add_punishment(user_id: int, chat_id: int, punishment_type: str, reason: str, punished_by: int, duration_minutes: int = None) -> bool:
    """
    Добавляет наказание гражданину.
    punishment_type: 'ban', 'mute', 'warn'
    duration_minutes: None для перманентных наказаний
    Возвращает True если наказание добавлено успешно.
    """
    conn = create_connection()
    if not conn:
        logger.error("Не удалось подключиться к БД для добавления наказания")
        return False

    try:
        cursor = conn.cursor()

        expires_at = None
        if duration_minutes:
            expires_at = (datetime.utcnow() + timedelta(minutes=duration_minutes)).isoformat()

        # Добавляем активное наказание
        cursor.execute(
            """
            INSERT OR REPLACE INTO active_punishments (user_id, chat_id, punishment_type, reason, punished_by, punished_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, chat_id, punishment_type, reason, punished_by, datetime.utcnow().isoformat(), expires_at)
        )

        # Добавляем в историю наказаний
        cursor.execute(
            """
            INSERT INTO punishment_history (user_id, chat_id, punishment_type, action, reason, moderator_id, duration_minutes)
            VALUES (?, ?, ?, 'added', ?, ?, ?)
            """,
            (user_id, chat_id, punishment_type, reason, punished_by, duration_minutes)
        )

        conn.commit()
        duration_text = f"на {duration_minutes} минут" if duration_minutes else "перманентно"
        logger.info(f"Гражданину {user_id} в чате {chat_id} выдано наказание '{punishment_type}' {duration_text} модератором {punished_by}: {reason}")
        return True

    except Error as e:
        logger.error(f"Ошибка при добавлении наказания гражданину {user_id}: {e}")
        return False
    finally:
        conn.close()


def remove_punishment(user_id: int, chat_id: int, punishment_type: str, removed_by: int) -> bool:
    """
    Снимает наказание с гражданина.
    Возвращает True если наказание снято успешно.
    """
    conn = create_connection()
    if not conn:
        logger.error("Не удалось подключиться к БД для снятия наказания")
        return False

    try:
        cursor = conn.cursor()

        # Получаем информацию о наказании перед удалением
        cursor.execute(
            "SELECT reason FROM active_punishments WHERE user_id = ? AND chat_id = ? AND punishment_type = ?",
            (user_id, chat_id, punishment_type)
        )
        punishment = cursor.fetchone()

        if punishment:
            reason = punishment[0]

            # Удаляем наказание
            cursor.execute(
                "DELETE FROM active_punishments WHERE user_id = ? AND chat_id = ? AND punishment_type = ?",
                (user_id, chat_id, punishment_type)
            )

            # Добавляем в историю наказаний
            cursor.execute(
                """
                INSERT INTO punishment_history (user_id, chat_id, punishment_type, action, reason, moderator_id)
                VALUES (?, ?, ?, 'removed', ?, ?)
                """,
                (user_id, chat_id, punishment_type, reason, removed_by)
            )

            conn.commit()
            logger.info(f"С гражданина {user_id} в чате {chat_id} снято наказание '{punishment_type}' модератором {removed_by}")
            return True
        else:
            logger.warning(f"У гражданина {user_id} в чате {chat_id} нет активного наказания '{punishment_type}'")
            return False

    except Error as e:
        logger.error(f"Ошибка при снятии наказания с гражданина {user_id}: {e}")
        return False
    finally:
        conn.close()


def get_active_punishments(user_id: int, chat_id: int) -> list[dict]:
    """
    Возвращает список активных наказаний гражданина в чате.
    """
    conn = create_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT punishment_type, reason, punished_by, punished_at, expires_at FROM active_punishments WHERE user_id = ? AND chat_id = ?",
            (user_id, chat_id)
        )
        punishments = cursor.fetchall()

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
    finally:
        conn.close()


def get_expired_punishments() -> list[dict]:
    """
    Возвращает список истекших наказаний для автоматического снятия.
    """
    conn = create_connection()
    if not conn:
        return []

    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT user_id, chat_id, punishment_type, reason, punished_by
            FROM active_punishments
            WHERE expires_at IS NOT NULL AND expires_at < ?
            """,
            (datetime.utcnow().isoformat(),)
        )
        punishments = cursor.fetchall()

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
    finally:
        conn.close()


def cleanup_expired_punishments() -> int:
    """
    Автоматически снимает истекшие наказания.
    Возвращает количество снятых наказаний.
    """
    try:
        expired_punishments = get_expired_punishments()
        cleaned_count = 0

        for punishment in expired_punishments:
            if remove_punishment(punishment['user_id'], punishment['chat_id'], punishment['type'], 0):  # 0 как системный пользователь
                # Добавляем запись об истечении в историю
                conn = create_connection()
                if conn:
                    try:
                        cursor = conn.cursor()
                        cursor.execute(
                            """
                            INSERT INTO punishment_history (user_id, chat_id, punishment_type, action, reason, moderator_id)
                            VALUES (?, ?, ?, 'expired', ?, 0)
                            """,
                            (punishment['user_id'], punishment['chat_id'], punishment['type'], punishment['reason'])
                        )
                        conn.commit()
                        cleaned_count += 1
                    except Error as e:
                        logger.error(f"Ошибка при добавлении записи об истечении наказания: {e}")
                    finally:
                        conn.close()

        if cleaned_count > 0:
            logger.info(f"Автоматически снято {cleaned_count} истекших наказаний")

        return cleaned_count
    except Exception as e:
        logger.warning(f"Не удалось выполнить очистку истекших наказаний (возможно, таблицы еще не созданы): {e}")
        return 0


def get_rate_display(user_id: int) -> str:
    """Возвращает красивое отображение рейтинга с эмодзи и текстом"""
    rate = get_user_rate(user_id)
    if rate >= 5001:
        return f"👑 Ваш социальный рейтинг: {rate} (S)"
    elif 3501 <= rate <= 5000:
        return f"🐉 Ваш социальный рейтинг: {rate} (A)"
    elif 1001 <= rate <= 3500:
        return f"☀️ Ваш социальный рейтинг: {rate} (B)"
    elif 51 <= rate <= 1000:
        return f"🍀 Ваш социальный рейтинг: {rate} (C)"
    elif -499 <= rate <= 50:
        return f"😈 Ваш социальный рейтинг: {rate} (D)"
    elif rate <= -500:
        return f"☠️ Ваш социальный рейтинг: {rate} (F)"
    else:
        return f"❓ Ваш социальный рейтинг: {rate} (N/A)"

# Регистрация самой анкеты, берет информацию из БД(будет использоваться и для профиля частично)
async def get_profile_text(user_id: int) -> str:
    """
    Получает данные из БД и возвращает готовый текст для анкеты.
    Эту функцию можно будет использовать в любом роутере.
    """
    profile_data = get_user_profile(user_id)
    rate_display = get_rate_display(user_id)

    if profile_data:
        # Безопасное получение данных с значениями по умолчанию
        nickname = profile_data.get("nickname", "Не указано")
        reputation = profile_data.get("reputation", 0)
        activity = profile_data.get("activity", "Не указано")
        description = profile_data.get("description") or "Не указано"

        # Собираем красивое сообщение
        text = (
            f"👤 **Досье гражданина**\n\n"
            f"🗃️ **Учётное имя:** `{nickname}`\n"
            f"🆔 **Публичный цифровой идентификатор:** `{user_id}`\n\n"
            f"{rate_display}\n"
            f"☀️ **Активность:** {activity}\n\n"
            f"📄 **Описание:**\n_{description}_"
        )
        return text
    else:
        return "Не удалось найти твой профиль. Попробуй написать /start"