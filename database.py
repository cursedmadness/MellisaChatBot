import sqlite3
from sqlite3 import Error

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
    """Создаёт таблицу users и admins, если её нет."""
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    nickname TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS admins (
                    user_id INTEGER PRIMARY KEY,
                    first_name TEXT
                )
            ''')
            conn.commit()
            print("Проверка/создание таблицы 'users and admins' выполнено.")
        except Error as e:
            print(e)
        finally:
            conn.close()

# --- НОВАЯ ФУНКЦИЯ ДЛЯ ДОБАВЛЕНИЯ СТОЛБЦОВ ---
def add_new_columns():
    """
    Добавляет новые столбцы (Описание, Репутация, Активность_пользователя)
    в таблицу users, если они еще не существуют.
    """
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            
            # Словарь: имя_столбца -> тип_данных_и_ограничения
            columns = {
                "Описание": "TEXT(25)",
                "Репутация": "INTEGER DEFAULT 0",
                "Активность_пользователя": "INTEGER DEFAULT 0"
            }
            
            for column_name, column_def in columns.items():
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

            conn.commit()
        except Error as e:
            print(f"Произошла ошибка при добавлении столбцов: {e}")
        finally:
            conn.close()
            
# --- ОСТАЛЬНЫЕ ВАШИ ФУНКЦИИ (без изменений) ---

def add_user(user_id: int, nickname: str):
    """Добавляет пользователя в БД с указанным ником (по умолчанию first_name)."""
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT OR IGNORE INTO users (user_id, nickname) VALUES (?, ?)", (user_id, nickname))
            conn.commit()
            # print(f"Пользователь {user_id} добавлен с ником {nickname}") # Можно убрать, чтобы не спамить
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
                SELECT nickname, Описание, Репутация, Активность_пользователя
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


def set_user_description(user_id: int, description: str):
    """Устанавливает или обновляет описание пользователя."""
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            # Название столбца 'Описание' берем из предыдущего шага
            cursor.execute("UPDATE users SET Описание = ? WHERE user_id = ?", (description, user_id))
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
            cursor.execute("SELECT Описание FROM users WHERE user_id = ?", (user_id,))
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
    
    cursor.execute('SELECT Репутация FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    
    conn.close()
    
    if result:
        return result[0]
    else:
        # Если пользователя нет в базе, создаем запись
        update_user_rate(user_id, 0)
        return 0

def update_user_rate(user_id: int, rate: int):
    conn = create_connection()
    cursor = conn.cursor()
    
    # Используем INSERT OR REPLACE для обновления существующей записи
    cursor.execute('''
        INSERT OR REPLACE INTO users (user_id, Репутация)
        VALUES (?, ?)
    ''', (user_id, rate))
    
    conn.commit()
    conn.close()


# Добавьте эти функции в ваш файл database.py

def increment_user_activity(user_id: int):
    """Увеличивает счётчик активности пользователя на 1."""
    conn = create_connection()
    if conn:
        try:
            cursor = conn.cursor()
            # Используем SQL для атомарного увеличения значения
            cursor.execute("""
                UPDATE users 
                SET Активность_пользователя = Активность_пользователя + 1 
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
                SELECT nickname, Активность_пользователя 
                FROM users 
                WHERE Активность_пользователя > 0
                ORDER BY Активность_пользователя DESC 
                LIMIT ?
            """, (limit,))
            # Возвращаем список кортежей (ник, активность)
            return cursor.fetchall()
        except Error as e:
            print(f"Ошибка при получении лидерборда: {e}")
        finally:
            conn.close()
    return []

# Регистрация самой анкеты, берет информацию из БД(будет использоваться и для профиля частично)
def get_profile_text(user_id: int) -> str:
    """
    Получает данные из БД и возвращает готовый текст для анкеты.
    Эту функцию можно будет использовать в любом роутере.
    """
    profile_data = get_user_profile(user_id)
    
    if profile_data:
        # Если в поле описания ничего нет (None), заменяем на "Не указано"
        description = profile_data.get("description") or "Не указано"

        # Собираем красивое сообщение
        text = (
            f"👤 **Досье гражданина**\n\n"
            f"🗃️ **Учётное имя:** `{profile_data['nickname']}`\n"
            f"🆔 **Публичный цифровой идентификатор:** `{user_id}`\n\n"
            f"🍚 **Социальный рейтинг:** {profile_data['reputation']}\n"
            f"☀️ **Активность:** {profile_data['activity']}\n\n"
            f"📄 **Описание:**\n_{description}_"
        )
        return text
    else:
        return "Не удалось найти твой профиль. Попробуй написать /start"