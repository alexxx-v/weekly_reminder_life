import logging
import os
from datetime import datetime, date, time
import io
import psycopg2
from psycopg2 import sql
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

# Загружаем переменные окружения из файла .env
load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы для ConversationHandler
MAIN_MENU, GET_NAME, GET_BIRTHDATE, EDIT_PROFILE, EDIT_NAME, EDIT_BIRTHDATE, EDIT_LIFE_EXPECTANCY = range(7)

# Получаем параметры подключения к базе данных из переменных окружения
DB_HOST = os.environ.get('DB_HOST', 'localhost')
DB_PORT = os.environ.get('DB_PORT', '5432')
DB_NAME = os.environ.get('DB_NAME', 'weekly_reminder')
DB_USER = os.environ.get('DB_USER', 'postgres')
DB_PASSWORD = os.environ.get('DB_PASSWORD', 'postgres')

def get_db_connection():
    """Создает и возвращает соединение с базой данных PostgreSQL"""
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        return conn
    except psycopg2.Error as e:
        logger.error(f"Ошибка при подключении к базе данных: {e}")
        raise

def init_db():
    try:
        conn = get_db_connection()
        conn.autocommit = True
        cursor = conn.cursor()
        
        # Проверяем, существует ли таблица users
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'users'
            );
        """)
        result = cursor.fetchone()
        table_exists = result[0] if result is not None else False
        
        if not table_exists:
            # Создаем таблицу users
            cursor.execute("""
                CREATE TABLE users (
                    user_id BIGINT PRIMARY KEY,
                    name TEXT NOT NULL,
                    birthdate DATE NOT NULL,
                    life_expectancy INTEGER DEFAULT 90
                )
            """)
            logger.info("Таблица users создана успешно")
        else:
            # Проверяем, существует ли колонка life_expectancy
            cursor.execute("""
                SELECT EXISTS (
                    SELECT FROM information_schema.columns 
                    WHERE table_name = 'users' AND column_name = 'life_expectancy'
                );
            """)
            result = cursor.fetchone()
            column_exists = result[0] if result is not None else False
            
            if not column_exists:
                # Добавляем колонку life_expectancy, если она не существует
                cursor.execute("ALTER TABLE users ADD COLUMN life_expectancy INTEGER DEFAULT 90")
                logger.info("Колонка life_expectancy добавлена в таблицу users")
        
        cursor.close()
        conn.close()
        logger.info(f"База данных PostgreSQL инициализирована успешно")
    except psycopg2.Error as e:
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
            conn = get_db_connection()
            cursor = conn.cursor()
            
            # Проверяем, существует ли пользователь
            cursor.execute("SELECT user_id FROM users WHERE user_id = %s", (user_id,))
            user_exists = cursor.fetchone() is not None
            
            if user_exists:
                # Обновляем существующего пользователя
                cursor.execute(
                    "UPDATE users SET name = %s, birthdate = %s, life_expectancy = %s WHERE user_id = %s",
                    (context.user_data['name'], birthdate, 90, user_id)
                )
            else:
                # Добавляем нового пользователя
                cursor.execute(
                    "INSERT INTO users (user_id, name, birthdate, life_expectancy) VALUES (%s, %s, %s, %s)",
                    (user_id, context.user_data['name'], birthdate, 90)
                )
            
            conn.commit()
            cursor.close()
            conn.close()
            
            await update.message.reply_text(
                "✅ Данные сохранены! Каждое воскресенье в 21:00 ты будешь получать обновление.",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
        except psycopg2.Error as e:
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
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT name, birthdate, life_expectancy FROM users WHERE user_id = %s", 
            (user_id,)
        )
        user_data = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not user_data:
            await update.message.reply_text(
                "❌ Ты еще не зарегистрирован. Выбери пункт 'Регистрация' в меню.",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
            
        name, birthdate, life_expectancy = user_data
        # birthdate уже является объектом date в PostgreSQL
        
        # Расчет статистики
        days = (today - birthdate).days
        weeks = days // 7
        months = days // 30  # Приблизительно
        years = days // 365  # Приблизительно
        
        # Расчет оставшегося времени
        remaining_years = life_expectancy - years
        remaining_days = remaining_years * 365  # Приблизительно
        remaining_weeks = remaining_days // 7  # Приблизительно
        remaining_months = remaining_years * 12  # Приблизительно
        
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
        
    except psycopg2.Error as e:
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
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT name, birthdate, life_expectancy FROM users WHERE user_id = %s", 
            (user_id,)
        )
        user_data = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not user_data:
            await update.message.reply_text(
                "❌ Ты еще не зарегистрирован. Выбери пункт 'Регистрация' в меню.",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
            
        name, birthdate, life_expectancy = user_data
        # birthdate уже является объектом date в PostgreSQL
        
        keyboard = [
            [KeyboardButton("✏️ Изменить имя"), KeyboardButton("📅 Изменить дату рождения")],
            [KeyboardButton("⏳ Изменить продолжительность жизни")],
            [KeyboardButton("🔙 Назад в меню")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(
            f"Текущие данные:\n"
            f"👤 Имя: {name}\n"
            f"📅 Дата рождения: {birthdate.strftime('%d.%m.%Y')}\n"
            f"⏳ Продолжительность жизни: {life_expectancy} лет\n\n"
            f"Что хочешь изменить?",
            reply_markup=reply_markup
        )
        return EDIT_PROFILE
        
    except psycopg2.Error as e:
        logger.error(f"Ошибка при получении данных пользователя {user_id}: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при получении данных. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU

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
            [KeyboardButton("🔙 Назад")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "Выбери ожидаемую продолжительность жизни:",
            reply_markup=reply_markup
        )
        return EDIT_LIFE_EXPECTANCY
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
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "UPDATE users SET name = %s WHERE user_id = %s",
            (new_name, user_id)
        )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        await update.message.reply_text(
            f"✅ Имя успешно изменено на '{new_name}'!",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU
        
    except psycopg2.Error as e:
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
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                "UPDATE users SET birthdate = %s WHERE user_id = %s",
                (new_birthdate, user_id)
            )
            
            conn.commit()
            cursor.close()
            conn.close()
            
            await update.message.reply_text(
                f"✅ Дата рождения успешно изменена на {new_birthdate.strftime('%d.%m.%Y')}!",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
            
        except psycopg2.Error as e:
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
    
    try:
        # Извлекаем число из текста (70, 80 или 90)
        new_life_expectancy = int(text.split()[0])
        
        # Проверяем, что значение кратно 10 и находится в допустимом диапазоне
        if new_life_expectancy not in [70, 80, 90]:
            keyboard = [
                [KeyboardButton("70 лет"), KeyboardButton("80 лет"), KeyboardButton("90 лет")],
                [KeyboardButton("🔙 Назад")]
            ]
            reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
            await update.message.reply_text(
                "❌ Пожалуйста, выбери одно из предложенных значений.",
                reply_markup=reply_markup
            )
            return EDIT_LIFE_EXPECTANCY
            
        user_id = update.message.from_user.id
        try:
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                "UPDATE users SET life_expectancy = %s WHERE user_id = %s",
                (new_life_expectancy, user_id)
            )
            
            conn.commit()
            cursor.close()
            conn.close()
            
            await update.message.reply_text(
                f"✅ Ожидаемая продолжительность жизни успешно изменена на {new_life_expectancy} лет!",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
            
        except psycopg2.Error as e:
            logger.error(f"Ошибка при обновлении продолжительности жизни пользователя {user_id}: {e}")
            await update.message.reply_text(
                "❌ Произошла ошибка при обновлении данных. Пожалуйста, попробуйте позже.",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU

    except (ValueError, IndexError):
        keyboard = [
            [KeyboardButton("70 лет"), KeyboardButton("80 лет"), KeyboardButton("90 лет")],
            [KeyboardButton("🔙 Назад")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        await update.message.reply_text(
            "❌ Пожалуйста, выбери одно из предложенных значений.",
            reply_markup=reply_markup
        )
        return EDIT_LIFE_EXPECTANCY

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
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT name, birthdate, life_expectancy FROM users WHERE user_id = %s", 
            (user_id,)
        )
        user_data = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if not user_data:
            await update.message.reply_text(
                "❌ Ты еще не зарегистрирован. Выбери пункт 'Регистрация' в меню.",
                reply_markup=get_main_menu_keyboard()
            )
            return MAIN_MENU
            
        name, birthdate, life_expectancy = user_data
        # birthdate уже является объектом date в PostgreSQL
        
        # Генерируем календарь жизни
        calendar_image = generate_life_calendar(birthdate, life_expectancy)
        
        # Отправляем изображение
        await update.message.reply_photo(
            photo=calendar_image,
            caption=f"📅 Календарь жизни для {name}\n\nКаждый красный квадрат - прожитая неделя.\nВсего прожито: {(date.today() - birthdate).days // 7} недель.",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU
        
    except psycopg2.Error as e:
        logger.error(f"Ошибка при получении данных пользователя {user_id}: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при получении данных. Пожалуйста, попробуйте позже.",
            reply_markup=get_main_menu_keyboard()
        )
        return MAIN_MENU

async def send_weekly_update(context: ContextTypes.DEFAULT_TYPE):
    today = date.today()
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, name, birthdate, life_expectancy FROM users")
        users = cursor.fetchall()
        cursor.close()
        conn.close()
    except psycopg2.Error as e:
        logger.error(f"Ошибка при получении данных пользователей: {e}")
        return

    for user_id, name, birthdate, life_expectancy in users:
        try:
            weeks = (today - birthdate).days // 7
            years = (today - birthdate).days // 365
            remaining_years = life_expectancy - years
            
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
        except Exception as e:
            logger.error(f"Ошибка для пользователя {user_id}: {str(e)}")

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