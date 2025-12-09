import sqlite3
from sqlite3 import Error
from datetime import datetime
import logging

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
    """
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            
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
        "miska_risa": safe(6, 0),
        "mood": safe(7, "отличное"),
        "image_cats": safe(8),
        "age_days": safe(9, 1),
        "last_age_update": safe(10),
        "last_satiety_update": safe(11),
    }


def create_waifu_for_user(user_id: int, cat_name: str = "мяу", category: str = "students", mood: str = "отличное"):
    """
    Создаёт запись кошко-жены для пользователя, если её ещё нет.
    Поле date_cat сохраняем в ISO-формате.
    """
    if category not in ("loli", "students", "MILF"):
        category = "students"

    conn = create_connection()
    if not conn:
        return False

    try:
        cursor = conn.cursor()
        now_iso = datetime.utcnow().isoformat()
        cursor.execute(
            """
            INSERT OR IGNORE INTO waifu_cat (user_id, cat_name, category_cats, date_cat, age_days, last_age_update, mood, satiety, miska_risa, last_satiety_update)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, cat_name, category, now_iso, 1, now_iso, mood, 100, 5, now_iso),
        )
        conn.commit()
        return cursor.rowcount > 0
    except Error as e:
        print(e)
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
                   satiety, miska_risa, mood, image_cats, age_days, last_age_update, last_satiety_update
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


def update_cat_state(user_id: int, *, satiety: int | None = None, miska_risa: int | None = None,
                    mood: str | None = None, last_satiety_update: str | None = None) -> bool:
    """
    Универсальное обновление динамических полей кошко-жены.
    Обновляет только переданные параметры.
    """
    conn = create_connection()
    if not conn:
        return False

    fields = []
    values = []
    if satiety is not None:
        fields.append("satiety = ?")
        values.append(satiety)
    if miska_risa is not None:
        fields.append("miska_risa = ?")
        values.append(miska_risa)
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
        print(e)
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
    Добавляет пользователя в БД с указанным ником и username.
    При повторном добавлении обновляет username.
    """
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (user_id, nickname, username)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username
                """,
                (user_id, nickname, username),
            )
            conn.commit()
        except Error as e:
            print(e)
        finally:    
            conn.close()

def get_user_nickname(user_id: int) -> str:
    """Получает ник пользователя."""
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
    """Устанавливает ник пользователя."""
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
    """Получает все данные пользователя для анкеты."""
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
    Возвращает список всех пользователей из базы данных.
    Каждый пользователь представлен словарем с полями: user_id, nickname, username.
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
    Обновляет username пользователя в базе данных.
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
    Полностью удаляет пользователя из системы по username.
    Удаляет записи из всех таблиц: users, waifu_cat, hebao_items, admins.
    Возвращает True если успешно удален хотя бы один пользователь.
    """
    logger.info(f"Начинаем удаление пользователя @{username}")

    # Сначала найдем user_id
    user_id = get_user_by_username(username)
    if not user_id:
        logger.warning(f"Пользователь @{username} не найден в базе данных")
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
                print(f"Удалено {cursor.rowcount} записей из таблицы {table} для пользователя @{username} (ID: {user_id})")

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


def increment_user_activity(user_id: int):
    """Увеличивает счётчик активности пользователя на 1."""
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            # Используем SQL для атомарного увеличения значения
            cursor.execute("""
                UPDATE users 
                SET User_activity = User_activity + 1 
                WHERE user_id = ?
            """, (user_id,))
            conn.commit()
        except Error as e:
            print(f"Ошибка при инкременте активности: {e}")
        finally:
            conn.close()

def get_chat_leaderboard(limit: int = 10):
    """Получает топ пользователей по активности."""
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
            print(f"Ошибка при получении лидерборда: {e}")
        finally:
            conn.close()
    return []

def get_rate_status(user_id: int) -> str:
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

# Регистрация самой анкеты, берет информацию из БД(будет использоваться и для профиля частично)
async def get_profile_text(user_id: int) -> str:
    """
    Получает данные из БД и возвращает готовый текст для анкеты.
    Эту функцию можно будет использовать в любом роутере.
    """
    profile_data = get_user_profile(user_id)
    rank = get_rate_status(user_id)
    
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
            f"🍚 **Социальный рейтинг:** {reputation} ({rank})\n"
            f"☀️ **Активность:** {activity}\n\n"
            f"📄 **Описание:**\n_{description}_"
        )
        return text
    else:
        return "Не удалось найти твой профиль. Попробуй написать /start"