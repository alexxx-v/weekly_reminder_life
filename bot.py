import logging
import os
from datetime import datetime, date, time
import io
import sqlite3
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes
)
from dateutil.relativedelta import relativedelta
from dateutil.relativedelta import relativedelta

# Загружаем переменные окружения из файла .env
load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы для ConversationHandler
MAIN_MENU, GET_NAME, GET_BIRTHDATE, EDIT_PROFILE, EDIT_NAME, EDIT_BIRTHDATE, EDIT_LIFE_EXPECTANCY = range(7)

# Путь к базе данных SQLite
DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'weekly_reminder.db')

class DatabaseConnection:
    """Контекстный менеджер для работы с базой данных SQLite"""
    def __init__(self):
        self.conn = None
        
    def __enter__(self):
        try:
            # Создаем директорию data, если она не существует
            os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
            self.conn = sqlite3.connect(DB_PATH)
            self.conn.row_factory = sqlite3.Row  # Для доступа к колонкам по имени
            return self.conn
        except sqlite3.Error as e:
            logger.error(f"Ошибка при подключении к базе данных: {e}")
            raise
            
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            self.conn.close()
            
def get_db_connection():
    """Создает и возвращает соединение с базой данных SQLite как контекстный менеджер"""
    return DatabaseConnection()

def init_db():
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Проверяем, существует ли таблица users
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='users'
            """)
            table_exists = cursor.fetchone() is not None
            
            if not table_exists:
                # Создаем таблицу users
                cursor.execute("""
                    CREATE TABLE users (
                        user_id INTEGER PRIMARY KEY,
                        name TEXT NOT NULL,
                        birthdate TEXT NOT NULL,
                        life_expectancy INTEGER DEFAULT 90,
                        notifications_enabled INTEGER DEFAULT 1
                    )
                """)
                logger.info("Таблица users создана успешно")
            else:
                # Проверяем, существует ли колонка life_expectancy
                cursor.execute("PRAGMA table_info(users)")
                columns = [column[1] for column in cursor.fetchall()]
                
                if 'life_expectancy' not in columns:
                    # Добавляем колонку life_expectancy, если она не существует
                    cursor.execute("ALTER TABLE users ADD COLUMN life_expectancy INTEGER DEFAULT 90")
                    logger.info("Колонка life_expectancy добавлена в таблицу users")
                
                if 'notifications_enabled' not in columns:
                    # Добавляем колонку notifications_enabled, если она не существует
                    cursor.execute("ALTER TABLE users ADD COLUMN notifications_enabled INTEGER DEFAULT 1")
                    logger.info("Колонка notifications_enabled добавлена в таблицу users")
            
            conn.commit()
            logger.info(f"База данных SQLite инициализирована успешно")
    except sqlite3.Error as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
        raise

try:
    init_db()
except Exception as e:
    logger.critical(f"Критическая ошибка при запуске: {e}")
    # В реальном приложении здесь можно добавить уведомление администратора

def get_main_menu_keyboard():
    """Создает клавиатуру основного меню"""
    keyboard = [
        [KeyboardButton("📝 Регистрация"), KeyboardButton("📊 Моя статистика")],
        [KeyboardButton("📅 Календарь жизни"), KeyboardButton("✏️ Изменить данные")],
        [KeyboardButton("ℹ️ О боте")]
    ]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отправляет приветственное сообщение и показывает главное меню"""
    await update.message.reply_text(
        "Привет! Я бот для отслеживания прожитых недель. Выбери действие:",
        reply_markup=get_main_menu_keyboard()
    )
    return MAIN_MENU

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор пункта в главном меню"""
    text = update.message.text
    
    if text == "📝 Регистрация":
        await update.message.reply_text("Как тебя зовут?")
        return GET_NAME
    elif text == "📊 Моя статистика":
        return await show_statistics(update, context)
    elif text == "📅 Календарь жизни":
        return await show_life_calendar(update, context)
    elif text == "✏️ Изменить данные":
        return await edit_profile(update, context)
    elif text == "ℹ️ О боте":
        await update.message.reply_text(
            "Этот бот помогает отслеживать количество прожитых недель. "
            "Каждое воскресенье в 21:00 ты будешь получать уведомление с текстовой статистикой и календарем жизни.",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU
    else:
        await update.message.reply_text(
            "Пожалуйста, используй кнопки меню для навигации.",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data['name'] = update.message.text
    await update.message.reply_text("Отлично! Теперь введи свою дату рождения в формате ДД.ММ.ГГГГ")
    return GET_BIRTHDATE

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Операция отменена.", 
        reply_markup=get_main_menu_keyboard()
    )
    return MAIN_MENU

async def get_birthdate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try:
        birthdate = datetime.strptime(update.message.text, "%d.%m.%Y").date()
        if birthdate > date.today():
            await update.message.reply_text("Дата рождения не может быть в будущем. Введи снова:")
            return GET_BIRTHDATE
            
        user_id = update.message.from_user.id
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                # Проверяем, существует ли пользователь
                cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
                user_exists = cursor.fetchone() is not None
                
                if user_exists:
                    # Обновляем существующего пользователя
                    cursor.execute(
                        "UPDATE users SET name = ?, birthdate = ?, life_expectancy = ? WHERE user_id = ?",
                        (context.user_data['name'], birthdate, 90, user_id)
                    )
                else:
                    # Добавляем нового пользователя
                    cursor.execute(
                        "INSERT INTO users (user_id, name, birthdate, life_expectancy, notifications_enabled) VALUES (?, ?, ?, ?, ?)",
                        (user_id, context.user_data['name'], birthdate, 90, True)
                    )
                cursor.close()
                
                conn.commit()
            
            await update.message.reply_text(
                "✅ Данные сохранены! Каждое воскресенье в 21:00 ты будешь получать обновление.",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
        except sqlite3.Error as e:
            logger.error(f"Ошибка при сохранении данных пользователя {user_id}: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при сохранении данных. Пожалуйста, попробуйте позже.",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU

    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Используй ДД.ММ.ГГГГ:")
        return GET_BIRTHDATE

async def show_statistics(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает статистику пользователя"""
    user_id = update.message.from_user.id
    today = date.today()
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name, birthdate, life_expectancy FROM users WHERE user_id = ?", 
                (user_id,)
            )
            user_data = cursor.fetchone()
            cursor.close()
        
        if not user_data:
            await update.message.reply_text(
                "❌ Ты еще не зарегистрирован. Выбери пункт 'Регистрация' в меню.",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
            
        name, birthdate_str, life_expectancy = user_data
        # Парсим строку даты из SQLite в объект date
        birthdate = datetime.strptime(birthdate_str, '%Y-%m-%d').date()
        
        # Расчет статистики с использованием dateutil для точных расчетов
        delta = relativedelta(today, birthdate)
        days = (today - birthdate).days
        weeks = days // 7
        
        # Точные расчеты месяцев и лет
        years = delta.years
        months = delta.years * 12 + delta.months
        
        # Расчет оставшегося времени с учетом високосных лет
        remaining_delta = relativedelta(years=life_expectancy) - delta
        remaining_years = remaining_delta.years
        remaining_months = remaining_delta.years * 12 + remaining_delta.months
        
        # Приблизительный расчет оставшихся дней и недель
        # Учитываем високосные годы (примерно 365.25 дней в году)
        remaining_days = int(remaining_years * 365.25)
        remaining_weeks = remaining_days // 7
        
        await update.message.reply_text(
            f"📊 Статистика для {name}:\n\n"
            f"📅 Дата рождения: {birthdate.strftime('%d.%m.%Y')}\n"
            f"⏱ Прожито дней: {days}\n"
            f"📆 Прожито недель: {weeks}\n"
            f"🗓 Прожито месяцев: {months}\n"
            f"🎂 Прожито лет: {years}\n\n"
            f"⏳ Ожидаемая продолжительность жизни: {life_expectancy} лет\n"
            f"⌛ Осталось примерно: {remaining_years} лет\n"
            f"📅 Это примерно {remaining_days} дней\n"
            f"📆 Или {remaining_weeks} недель\n"
            f"🗓 Или {remaining_months} месяцев",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU
        
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении данных пользователя {user_id}: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при получении данных. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU

async def edit_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает меню редактирования профиля"""
    user_id = update.message.from_user.id
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name, birthdate, life_expectancy, notifications_enabled FROM users WHERE user_id = ?", 
                (user_id,)
            )
            user_data = cursor.fetchone()
            cursor.close()
        
        if not user_data:
            await update.message.reply_text(
                "❌ Ты еще не зарегистрирован. Выбери пункт 'Регистрация' в меню.",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
            
        name, birthdate_str, life_expectancy, notifications_enabled = user_data
        # Парсим строку даты из SQLite в объект date
        birthdate = datetime.strptime(birthdate_str, '%Y-%m-%d').date()
        
        notifications_status = "Включены ✅" if notifications_enabled else "Отключены ❌"
        
        keyboard = [
            [KeyboardButton("✏️ Изменить имя"), KeyboardButton("📅 Изменить дату рождения")],
            [KeyboardButton("⏳ Изменить продолжительность жизни")],
            [KeyboardButton("🔔 Управление уведомлениями")],
            [KeyboardButton("❌ Удалить профиль")],
            [KeyboardButton("🔙 Назад в меню")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            f"Текущие данные:\n"
            f"👤 Имя: {name}\n"
            f"📅 Дата рождения: {birthdate.strftime('%d.%m.%Y')}\n"
            f"⏳ Продолжительность жизни: {life_expectancy} лет\n"
            f"🔔 Уведомления: {notifications_status}\n\n"
            f"Что хочешь изменить?",
            reply_markup=reply_markup
        )
        return EDIT_PROFILE
        
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении данных пользователя {user_id}: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при получении данных. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU

# Константы для новых состояний ConversationHandler
MANAGE_NOTIFICATIONS, DELETE_PROFILE, CUSTOM_LIFE_EXPECTANCY = range(7, 10)

async def edit_profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор в меню редактирования профиля"""
    text = update.message.text
    
    if text == "✏️ Изменить имя":
        await update.message.reply_text("Введи новое имя:")
        return EDIT_NAME
    elif text == "📅 Изменить дату рождения":
        await update.message.reply_text("Введи новую дату рождения в формате ДД.ММ.ГГГГ:")
        return EDIT_BIRTHDATE
    elif text == "⏳ Изменить продолжительность жизни":
        keyboard = [
            [KeyboardButton("70 лет"), KeyboardButton("80 лет"), KeyboardButton("90 лет")],
            [KeyboardButton("Другое значение")],
            [KeyboardButton("🔙 Назад")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "Выбери ожидаемую продолжительность жизни:",
            reply_markup=reply_markup
        )
        return EDIT_LIFE_EXPECTANCY
    elif text == "🔔 Управление уведомлениями":
        user_id = update.message.from_user.id
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT notifications_enabled FROM users WHERE user_id = ?", 
                    (user_id,)
                )
                result = cursor.fetchone()
                notifications_enabled = result[0] if result else True
                cursor.close()
                
                # Создаем клавиатуру с противоположным действием
                keyboard = [[
                    KeyboardButton("Отключить уведомления" if notifications_enabled else "Включить уведомления")
                ], [KeyboardButton("🔙 Назад")]]
                reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
                
                status = "включены" if notifications_enabled else "отключены"
                await update.message.reply_text(
                    f"Сейчас уведомления {status}. Что ты хочешь сделать?",
                    reply_markup=reply_markup
                )
                return MANAGE_NOTIFICATIONS
        except sqlite3.Error as e:
            logger.error(f"Ошибка при получении статуса уведомлений пользователя {user_id}: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при получении данных. Пожалуйста, попробуйте позже.",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
    elif text == "❌ Удалить профиль":
        keyboard = [
            [KeyboardButton("✅ Да, удалить профиль")],
            [KeyboardButton("❌ Нет, отменить")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "⚠️ Ты уверен, что хочешь удалить свой профиль? Все данные будут безвозвратно удалены.",
            reply_markup=reply_markup
        )
        return DELETE_PROFILE
    elif text == "🔙 Назад в меню":
        await update.message.reply_text(
            "Возвращаемся в главное меню.",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU
    else:
        await update.message.reply_text(
            "Пожалуйста, используй кнопки меню для навигации."
        )
        return EDIT_PROFILE

async def edit_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обновляет имя пользователя"""
    new_name = update.message.text
    user_id = update.message.from_user.id
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE users SET name = ? WHERE user_id = ?",
                (new_name, user_id)
            )
            cursor.close()
            conn.commit()
        
        await update.message.reply_text(
            f"✅ Имя успешно изменено на '{new_name}'!",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU
        
    except sqlite3.Error as e:
        logger.error(f"Ошибка при обновлении имени пользователя {user_id}: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при обновлении данных. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU

async def edit_birthdate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обновляет дату рождения пользователя"""
    try:
        new_birthdate = datetime.strptime(update.message.text, "%d.%m.%Y").date()
        if new_birthdate > date.today():
            await update.message.reply_text("Дата рождения не может быть в будущем. Введи снова:")
            return EDIT_BIRTHDATE
            
        user_id = update.message.from_user.id
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET birthdate = ? WHERE user_id = ?",
                    (new_birthdate, user_id)
                )
                cursor.close()
                conn.commit()
            
            await update.message.reply_text(
                f"✅ Дата рождения успешно изменена на {new_birthdate.strftime('%d.%m.%Y')}!",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка при обновлении даты рождения пользователя {user_id}: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при обновлении данных. Пожалуйста, попробуйте позже.",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU

    except ValueError:
        await update.message.reply_text("❌ Неверный формат. Используй ДД.ММ.ГГГГ:")
        return EDIT_BIRTHDATE

async def edit_life_expectancy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обновляет ожидаемую продолжительность жизни пользователя"""
    text = update.message.text
    
    if text == "🔙 Назад":
        return await edit_profile(update, context)
    
    if text == "Другое значение":
        await update.message.reply_text(
            "Введи желаемую продолжительность жизни (целое число от 50 до 120):",
            reply_markup=ReplyKeyboardRemove()
        )
        return CUSTOM_LIFE_EXPECTANCY
    
    try:
        # Извлекаем число из текста (70, 80 или 90)
        new_life_expectancy = int(text.split()[0])
        
        # Проверяем, что значение находится в допустимом диапазоне
        if new_life_expectancy not in [70, 80, 90]:
            keyboard = [
                [KeyboardButton("70 лет"), KeyboardButton("80 лет"), KeyboardButton("90 лет")],
                [KeyboardButton("Другое значение")],
                [KeyboardButton("🔙 Назад")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text(
                "❌ Пожалуйста, выбери одно из предложенных значений или 'Другое значение'.",
                reply_markup=reply_markup
            )
            return EDIT_LIFE_EXPECTANCY
            
        user_id = update.message.from_user.id
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET life_expectancy = ? WHERE user_id = ?",
                    (new_life_expectancy, user_id)
                )
                cursor.close()
                conn.commit()
            
            await update.message.reply_text(
                f"✅ Ожидаемая продолжительность жизни успешно изменена на {new_life_expectancy} лет!",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка при обновлении продолжительности жизни пользователя {user_id}: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при обновлении данных. Пожалуйста, попробуйте позже.",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU

    except (ValueError, IndexError):
        keyboard = [
            [KeyboardButton("70 лет"), KeyboardButton("80 лет"), KeyboardButton("90 лет")],
            [KeyboardButton("Другое значение")],
            [KeyboardButton("🔙 Назад")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "❌ Пожалуйста, выбери одно из предложенных значений или 'Другое значение'.",
            reply_markup=reply_markup
        )
        return EDIT_LIFE_EXPECTANCY

async def custom_life_expectancy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает ввод произвольного значения продолжительности жизни"""
    try:
        new_life_expectancy = int(update.message.text)
        
        # Проверяем, что значение находится в разумном диапазоне
        if new_life_expectancy < 50 or new_life_expectancy > 120:
            await update.message.reply_text(
                "❌ Пожалуйста, введи значение от 50 до 120 лет:"
            )
            return CUSTOM_LIFE_EXPECTANCY
            
        user_id = update.message.from_user.id
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET life_expectancy = ? WHERE user_id = ?",
                    (new_life_expectancy, user_id)
                )
                cursor.close()
                conn.commit()
            
            await update.message.reply_text(
                f"✅ Ожидаемая продолжительность жизни успешно изменена на {new_life_expectancy} лет!",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка при обновлении продолжительности жизни пользователя {user_id}: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при обновлении данных. Пожалуйста, попробуйте позже.",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU

    except ValueError:
        await update.message.reply_text(
            "❌ Пожалуйста, введи целое число от 50 до 120:"
        )
        return CUSTOM_LIFE_EXPECTANCY

def generate_life_calendar(birthdate: date, life_expectancy: int) -> io.BytesIO:
    """Генерирует изображение календаря жизни"""
    # Константы для изображения
    CELL_SIZE = 10  # Размер одной ячейки в пикселях
    WEEKS_PER_ROW = 52  # Количество недель в году (по горизонтали)
    YEARS = life_expectancy  # Количество лет (по вертикали)
    
    # Отступы и размеры подписей
    MARGIN_LEFT = 50  # Отступ слева для подписей лет
    MARGIN_TOP = 50   # Отступ сверху для подписей недель
    
    # Рассчитываем размер изображения
    width = MARGIN_LEFT + WEEKS_PER_ROW * CELL_SIZE + 20  # Добавляем отступ справа
    height = MARGIN_TOP + YEARS * CELL_SIZE + 20  # Добавляем отступ снизу
    
    # Создаем новое изображение с белым фоном
    image = Image.new('RGB', (width, height), color='white')
    draw = ImageDraw.Draw(image)
    
    # Пытаемся загрузить шрифт, если не получается, используем шрифт по умолчанию
    try:
        font = ImageFont.truetype("Arial", 12)
    except IOError:
        font = ImageFont.load_default()
    
    # Рисуем заголовки
    draw.text((MARGIN_LEFT, 10), "Недели ——>", fill="black", font=font)
    draw.text((10, MARGIN_TOP), "В\nо\nз\nр\nа\nс\nт\n\n|", fill="black", font=font)
    draw.text((10, MARGIN_TOP + 100), "↓", fill="black", font=font)
    
    # Рисуем подписи недель (по 5)
    for i in range(0, WEEKS_PER_ROW + 1, 5):
        x = MARGIN_LEFT + i * CELL_SIZE
        draw.text((x, 30), str(i), fill="black", font=font)
    
    # Рисуем подписи лет (по 5)
    for i in range(0, YEARS + 1, 5):
        y = MARGIN_TOP + i * CELL_SIZE
        draw.text((20, y), str(i), fill="black", font=font)
    
    # Рисуем сетку и заполняем прожитые недели
    today = date.today()
    total_weeks_lived = (today - birthdate).days // 7
    
    for year in range(YEARS):
        for week in range(WEEKS_PER_ROW):
            x = MARGIN_LEFT + week * CELL_SIZE
            y = MARGIN_TOP + year * CELL_SIZE
            
            # Индекс текущей недели
            current_week_index = year * WEEKS_PER_ROW + week
            
            # Определяем цвет ячейки
            if current_week_index < total_weeks_lived:
                # Прожитая неделя - красная
                cell_color = 'red'
            else:
                # Будущая неделя - контур
                cell_color = 'lightgray'
            
            # Рисуем ячейку
            draw.rectangle(
                [(x, y), (x + CELL_SIZE - 1, y + CELL_SIZE - 1)],
                outline='gray',
                fill=cell_color if current_week_index < total_weeks_lived else None
            )
    
    # Сохраняем изображение в байтовый поток
    img_byte_arr = io.BytesIO()
    image.save(img_byte_arr, format='PNG')
    img_byte_arr.seek(0)  # Перемещаем указатель в начало потока
    
    return img_byte_arr

async def show_life_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Показывает календарь жизни пользователя"""
    user_id = update.message.from_user.id
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name, birthdate, life_expectancy FROM users WHERE user_id = ?", 
                (user_id,)
            )
            user_data = cursor.fetchone()
            cursor.close()
        
        if not user_data:
            await update.message.reply_text(
                "❌ Ты еще не зарегистрирован. Выбери пункт 'Регистрация' в меню.",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
            
        name, birthdate_str, life_expectancy = user_data
        # Парсим строку даты из SQLite в объект date
        birthdate = datetime.strptime(birthdate_str, '%Y-%m-%d').date()
        
        # Генерируем календарь жизни
        calendar_image = generate_life_calendar(birthdate, life_expectancy)
        
        # Отправляем изображение
        await update.message.reply_photo(
            photo=calendar_image,
            caption=f"📅 Календарь жизни для {name}\n\nКаждый красный квадрат - прожитая неделя.\nВсего прожито: {(date.today() - birthdate).days // 7} недель.",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU
        
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении данных пользователя {user_id}: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при получении данных. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU

async def send_weekly_update(context: ContextTypes.DEFAULT_TYPE):
    today = date.today()
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id, name, birthdate, life_expectancy, notifications_enabled FROM users")
            users = cursor.fetchall()
            cursor.close()
    except sqlite3.Error as e:
        logger.error(f"Ошибка при получении данных пользователей: {e}")
        return

    for user_data in users:
        user_id, name, birthdate_str, life_expectancy, notifications_enabled = user_data
        
        # Пропускаем пользователей, отключивших уведомления
        if not notifications_enabled:
            logger.info(f"Пропускаем отправку уведомления пользователю {user_id} ({name}), т.к. уведомления отключены")
            continue
            
        try:
            # Парсим строку даты из SQLite в объект date
            birthdate = datetime.strptime(birthdate_str, '%Y-%m-%d').date()
            
            # Используем dateutil для более точных расчетов
            delta = relativedelta(today, birthdate)
            weeks = (today - birthdate).days // 7
            years = delta.years
            
            # Расчет оставшегося времени с учетом високосных лет
            remaining_delta = relativedelta(years=life_expectancy) - delta
            remaining_years = remaining_delta.years
            
            # Отправляем текстовое сообщение
            await context.bot.send_message(
                chat_id=user_id,
                text=f"📅 Здравствуй, {name}! Ты прожил {weeks} недель. При ожидаемой продолжительности жизни {life_expectancy} лет, тебе осталось примерно {remaining_years} лет."
            )
            
            # Генерируем и отправляем календарь жизни
            calendar_image = generate_life_calendar(birthdate, life_expectancy)
            await context.bot.send_photo(
                chat_id=user_id,
                photo=calendar_image,
                caption=f"📅 Твой календарь жизни. Каждый красный квадрат - прожитая неделя."
            )
        except sqlite3.Error as e:
            logger.error(f"Ошибка базы данных для пользователя {user_id}: {e}")
        except telegram.error.TelegramError as e:
            logger.error(f"Ошибка Telegram для пользователя {user_id}: {e}")
        except IOError as e:
            logger.error(f"Ошибка ввода/вывода для пользователя {user_id}: {e}")
        except Exception as e:
            logger.error(f"Непредвиденная ошибка для пользователя {user_id}: {str(e)}")

async def manage_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает включение/отключение уведомлений"""
    text = update.message.text
    user_id = update.message.from_user.id
    
    if text == "🔙 Назад":
        return await edit_profile(update, context)
    
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Определяем новое состояние уведомлений
            new_state = text == "Включить уведомления"
            
            cursor.execute(
                "UPDATE users SET notifications_enabled = ? WHERE user_id = ?",
                (new_state, user_id)
            )
            cursor.close()
            conn.commit()
        
        status = "включены" if new_state else "отключены"
        await update.message.reply_text(
            f"✅ Уведомления успешно {status}!",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU
        
    except sqlite3.Error as e:
        logger.error(f"Ошибка при обновлении статуса уведомлений пользователя {user_id}: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при обновлении данных. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU

async def delete_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает удаление профиля пользователя"""
    text = update.message.text
    user_id = update.message.from_user.id
    
    if text == "❌ Нет, отменить":
        await update.message.reply_text(
            "Операция отменена.",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU
    
    if text == "✅ Да, удалить профиль":
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM users WHERE user_id = ?", (user_id,))
                cursor.close()
                conn.commit()
            
            await update.message.reply_text(
                "✅ Твой профиль успешно удален. Если захочешь вернуться, просто зарегистрируйся снова.",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
            
        except sqlite3.Error as e:
            logger.error(f"Ошибка при удалении профиля пользователя {user_id}: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при удалении профиля. Пожалуйста, попробуйте позже.",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
    
    # Если пользователь ввел что-то другое
    keyboard = [
        [KeyboardButton("✅ Да, удалить профиль")],
        [KeyboardButton("❌ Нет, отменить")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "⚠️ Пожалуйста, выбери один из предложенных вариантов.",
        reply_markup=reply_markup
    )
    return DELETE_PROFILE

def main() -> None:
    # Получаем токен бота из переменной окружения
    bot_token = os.environ.get('BOT_TOKEN')
    if not bot_token:
        logger.critical("Ошибка: Переменная окружения BOT_TOKEN не установлена")
        return
    
    application = Application.builder().token(bot_token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, main_menu_handler)],
            GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            GET_BIRTHDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_birthdate)],
            EDIT_PROFILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_profile_handler)],
            EDIT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_name)],
            EDIT_BIRTHDATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_birthdate)],
            EDIT_LIFE_EXPECTANCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_life_expectancy)],
            CUSTOM_LIFE_EXPECTANCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, custom_life_expectancy)],
            MANAGE_NOTIFICATIONS: [MessageHandler(filters.TEXT & ~filters.COMMAND, manage_notifications)],
            DELETE_PROFILE: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_profile)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    # Добавляем обработчик команды отмены
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(conv_handler)
    
    # Запускаем еженедельное обновление только по воскресеньям (day_of_week=6)
    application.job_queue.run_daily(send_weekly_update, time=time(21, 0), days=(6,))
    application.run_polling()

if __name__ == "__main__":
    main()