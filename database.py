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
    """Создаёт таблицу users, если её нет."""
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
            conn.commit()
            print("Проверка/создание таблицы 'users' выполнено.")
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