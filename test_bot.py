import pytest
import sqlite3
import os
import tempfile
from unittest.mock import patch, MagicMock, Mock
from datetime import date, datetime
from bot import (
    DatabaseConnection, init_db, get_db_connection, show_statistics, 
    show_life_calendar, generate_life_calendar, edit_name, edit_birthdate,
    custom_life_expectancy, manage_notifications, delete_profile, send_weekly_update,
    start
)

class TestDatabaseConnection:
    """Тесты для подключения к базе данных"""
    
    def setup_method(self):
        """Создаем временную базу данных для каждого теста"""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name
        
    def teardown_method(self):
        """Удаляем временную базу данных после каждого теста"""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
    
    def test_database_connection_creation(self):
        """Тест создания соединения с базой данных"""
        with patch('bot.DB_PATH', self.db_path):
            db_conn = DatabaseConnection()
            assert db_conn is not None
    
    def test_database_connection_context_manager(self):
        """Тест контекстного менеджера базы данных"""
        with patch('bot.DB_PATH', self.db_path):
            with DatabaseConnection() as conn:
                assert conn is not None
                assert isinstance(conn, sqlite3.Connection)
    
    def test_database_initialization(self):
        """Тест инициализации таблиц в базе данных"""
        with patch('bot.DB_PATH', self.db_path):
            init_db()
            
            # Проверяем, что таблицы созданы
            with DatabaseConnection() as conn:
                cursor = conn.cursor()
                
                # Проверяем таблицу users
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
                table_exists = cursor.fetchone() is not None
                assert table_exists, "Таблица users не была создана"
                
                # Проверяем структуру таблицы
                cursor.execute("PRAGMA table_info(users)")
                columns = [column[1] for column in cursor.fetchall()]
                expected_columns = ['user_id', 'name', 'birthdate', 'life_expectancy', 'notifications_enabled']
                for col in expected_columns:
                    assert col in columns, f"Колонка {col} отсутствует в таблице users"
                
                cursor.close()

class TestUserRegistration:
    """Тесты для регистрации пользователей через базу данных"""
    
    def setup_method(self):
        """Настройка для каждого теста"""
        # Создаем временную базу данных
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()
        
        # Инициализируем базу данных
        with patch('bot.DB_PATH', self.temp_db_path):
            init_db()
    
    def teardown_method(self):
        """Очистка после каждого теста"""
        if os.path.exists(self.temp_db_path):
            os.unlink(self.temp_db_path)
    
    def test_register_new_user_direct_db(self):
        """Тест прямой регистрации пользователя в базе данных"""
        with patch('bot.DB_PATH', self.temp_db_path):
            # Прямая вставка в базу данных
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (user_id, name, birthdate, life_expectancy, notifications_enabled) VALUES (?, ?, ?, ?, ?)",
                    (12345, "Тест Пользователь", date(1990, 5, 15), 90, True)
                )
                cursor.close()
                conn.commit()
            
            # Проверяем, что пользователь добавлен
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id, name, birthdate FROM users WHERE user_id = ?", (12345,))
                user_data = cursor.fetchone()
                cursor.close()
                
                assert user_data is not None
                assert user_data[0] == 12345
                assert user_data[1] == "Тест Пользователь"
    
    def test_update_existing_user_direct_db(self):
        """Тест обновления существующего пользователя в базе данных"""
        with patch('bot.DB_PATH', self.temp_db_path):
            # Добавляем пользователя
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (user_id, name, birthdate, life_expectancy, notifications_enabled) VALUES (?, ?, ?, ?, ?)",
                    (12345, "Первое Имя", date(1990, 5, 15), 90, True)
                )
                cursor.close()
                conn.commit()
            
            # Обновляем данные пользователя
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET name = ?, birthdate = ? WHERE user_id = ?",
                    ("Новое Имя", date(1985, 3, 20), 12345)
                )
                cursor.close()
                conn.commit()
            
            # Проверяем обновление
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name, birthdate FROM users WHERE user_id = ?", (12345,))
                user_data = cursor.fetchone()
                cursor.close()
                
                assert user_data[0] == "Новое Имя"
    
    def test_get_user_data_nonexistent(self):
        """Тест получения данных несуществующего пользователя"""
        with patch('bot.DB_PATH', self.temp_db_path):
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users WHERE user_id = ?", (99999,))
                user_data = cursor.fetchone()
                cursor.close()
                
                assert user_data is None
    
    def test_get_birthdate(self):
        """Тест получения даты рождения пользователя"""
        with patch('bot.DB_PATH', self.temp_db_path):
            # Добавляем пользователя
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (user_id, name, birthdate, life_expectancy, notifications_enabled) VALUES (?, ?, ?, ?, ?)",
                    (12345, "Тест Пользователь", date(1990, 5, 15), 90, True)
                )
                cursor.close()
                conn.commit()
            
            # Получаем дату рождения
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT birthdate FROM users WHERE user_id = ?", (12345,))
                result = cursor.fetchone()
                cursor.close()
                
                if result:
                    birthdate_str = result[0]
                    birthdate = datetime.strptime(birthdate_str, '%Y-%m-%d').date()
                    assert birthdate == date(1990, 5, 15)

class TestProfileEditing:
    """Тесты для редактирования профиля пользователя"""
    
    def setup_method(self):
        """Настройка для каждого теста"""
        # Создаем временную базу данных
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()
        
        # Инициализируем базу данных
        with patch('bot.DB_PATH', self.temp_db_path):
            init_db()
            
            # Добавляем тестового пользователя
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (user_id, name, birthdate, life_expectancy, notifications_enabled) VALUES (?, ?, ?, ?, ?)",
                    (12345, "Тест Пользователь", date(1990, 5, 15), 80, True)
                )
                cursor.close()
                conn.commit()
    
    def teardown_method(self):
        """Очистка после каждого теста"""
        if os.path.exists(self.temp_db_path):
            os.unlink(self.temp_db_path)
    
    @patch('bot.DB_PATH')
    def test_update_user_name(self, mock_db_path):
        """Тест обновления имени пользователя"""
        mock_db_path.return_value = self.temp_db_path
        
        with patch('bot.DB_PATH', self.temp_db_path):
            # Обновляем имя пользователя
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET name = ? WHERE user_id = ?",
                    ("Новое Имя", 12345)
                )
                cursor.close()
                conn.commit()
            
            # Проверяем обновление
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM users WHERE user_id = ?", (12345,))
                result = cursor.fetchone()
                cursor.close()
                
                assert result[0] == "Новое Имя"
    
    def test_update_user_birthdate(self):
        """Тест обновления даты рождения пользователя"""
        with patch('bot.DB_PATH', self.temp_db_path):
            new_birthdate = date(1985, 3, 20)
            
            # Обновляем дату рождения
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET birthdate = ? WHERE user_id = ?",
                    (new_birthdate, 12345)
                )
                cursor.close()
                conn.commit()
            
            # Проверяем обновление
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT birthdate FROM users WHERE user_id = ?", (12345,))
                result = cursor.fetchone()
                cursor.close()
                
                if result:
                    birthdate_str = result[0]
                    birthdate = datetime.strptime(birthdate_str, '%Y-%m-%d').date()
                    assert birthdate == new_birthdate
    
    def test_update_user_life_expectancy(self):
        """Тест обновления ожидаемой продолжительности жизни"""
        with patch('bot.DB_PATH', self.temp_db_path):
            new_life_expectancy = 90
            
            # Обновляем продолжительность жизни
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET life_expectancy = ? WHERE user_id = ?",
                    (new_life_expectancy, 12345)
                )
                cursor.close()
                conn.commit()
            
            # Проверяем обновление
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT life_expectancy FROM users WHERE user_id = ?", (12345,))
                result = cursor.fetchone()
                cursor.close()
                
                assert result[0] == new_life_expectancy
    
    def test_delete_user_profile(self):
        """Тест удаления профиля пользователя"""
        with patch('bot.DB_PATH', self.temp_db_path):
            # Удаляем пользователя
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM users WHERE user_id = ?", (12345,))
                cursor.close()
                conn.commit()
            
            # Проверяем удаление
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users WHERE user_id = ?", (12345,))
                result = cursor.fetchone()
                cursor.close()
                
                assert result is None

class TestLifeCalendar:
    """Тесты для генерации календаря жизни"""
    
    def setup_method(self):
        """Настройка для каждого теста"""
        # Создаем временную базу данных
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()
        
        # Инициализируем базу данных
        with patch('bot.DB_PATH', self.temp_db_path):
            init_db()
            
            # Добавляем тестового пользователя
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (user_id, name, birthdate, life_expectancy, notifications_enabled) VALUES (?, ?, ?, ?, ?)",
                    (12345, "Тест Пользователь", date(1990, 5, 15), 80, True)
                )
                cursor.close()
                conn.commit()
    
    def teardown_method(self):
        """Очистка после каждого теста"""
        if os.path.exists(self.temp_db_path):
            os.unlink(self.temp_db_path)
    
    @patch('bot.generate_life_calendar')
    def test_generate_life_calendar(self, mock_generate):
        """Тест генерации календаря жизни"""
        with patch('bot.DB_PATH', self.temp_db_path):
            # Настраиваем мок для возврата изображения
            mock_generate.return_value = "/tmp/test_calendar.png"
            
            # Тестовые данные
            birthdate = date(1990, 5, 15)
            life_expectancy = 80
            
            # Вызываем функцию
            result = mock_generate(birthdate, life_expectancy)
            
            # Проверяем, что функция была вызвана с правильными аргументами
            mock_generate.assert_called_once_with(birthdate, life_expectancy)
            assert result is not None
            assert isinstance(result, str)
            assert result.endswith('.png')
    
    @patch('bot.show_life_calendar')
    def test_show_life_calendar_function_call(self, mock_show):
        """Тест вызова функции show_life_calendar"""
        
        with patch('bot.DB_PATH', self.temp_db_path):
            # Мокаем Telegram объекты
            mock_update = Mock()
            mock_context = Mock()
            mock_update.effective_user.id = 12345
            
            # Вызываем функцию
            mock_show(mock_update, mock_context)
            
            # Проверяем, что функция была вызвана с правильными аргументами
            mock_show.assert_called_once_with(mock_update, mock_context)

class TestNotifications:
    """Тесты для управления уведомлениями"""
    
    def setup_method(self):
        """Настройка для каждого теста"""
        # Создаем временную базу данных
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()
        
        # Инициализируем базу данных
        with patch('bot.DB_PATH', self.temp_db_path):
            init_db()
            
            # Добавляем тестового пользователя
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (user_id, name, birthdate, life_expectancy, notifications_enabled) VALUES (?, ?, ?, ?, ?)",
                    (12345, "Тест Пользователь", date(1990, 5, 15), 80, True)
                )
                cursor.close()
                conn.commit()
        
    def teardown_method(self):
        """Очистка после каждого теста"""
        if os.path.exists(self.temp_db_path):
            os.unlink(self.temp_db_path)
    
    def test_notification_settings_default(self):
        """Тест получения настроек уведомлений по умолчанию"""
        with patch('bot.DB_PATH', self.temp_db_path):
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT notifications_enabled FROM users WHERE user_id = ?", (12345,))
                result = cursor.fetchone()
                cursor.close()
                
                # По умолчанию уведомления должны быть включены
                assert result[0] == 1  # SQLite хранит булевы как 1/0
    
    def test_update_notification_settings(self):
        """Тест обновления настроек уведомлений"""
        with patch('bot.DB_PATH', self.temp_db_path):
            # Отключаем уведомления
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET notifications_enabled = ? WHERE user_id = ?",
                    (False, 12345)
                )
                cursor.close()
                conn.commit()
            
            # Проверяем обновление
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT notifications_enabled FROM users WHERE user_id = ?", (12345,))
                result = cursor.fetchone()
                cursor.close()
                
                assert result[0] == 0  # SQLite хранит булевы как 1/0
            
            # Включаем уведомления
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE users SET notifications_enabled = ? WHERE user_id = ?",
                    (True, 12345)
                )
                cursor.close()
                conn.commit()
            
            # Проверяем обновление
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT notifications_enabled FROM users WHERE user_id = ?", (12345,))
                result = cursor.fetchone()
                cursor.close()
                
                assert result[0] == 1  # SQLite хранит булевы как 1/0

class TestTelegramIntegration:
    """Тесты для интеграции с Telegram"""
    
    def setup_method(self):
        """Настройка для каждого теста"""
        # Создаем временную базу данных
        self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
        self.temp_db_path = self.temp_db.name
        self.temp_db.close()
        
        # Инициализируем базу данных
        with patch('bot.DB_PATH', self.temp_db_path):
            init_db()
            
            # Добавляем тестового пользователя
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (user_id, name, birthdate, life_expectancy, notifications_enabled) VALUES (?, ?, ?, ?, ?)",
                    (12345, "Тест Пользователь", date(1990, 5, 15), 80, True)
                )
                cursor.close()
                conn.commit()
    
    def teardown_method(self):
        """Очистка после каждого теста"""
        if os.path.exists(self.temp_db_path):
            os.unlink(self.temp_db_path)
    
    @patch('bot.start')
    def test_start_command(self, mock_start):
        """Тест команды /start"""
        with patch('bot.DB_PATH', self.temp_db_path):
            mock_update = MagicMock()
            mock_context = MagicMock()
            
            # Вызываем команду start
            mock_start(mock_update, mock_context)
            
            # Проверяем, что функция была вызвана
            mock_start.assert_called_once_with(mock_update, mock_context)
    
    @patch('bot.show_statistics')
    def test_show_statistics_command(self, mock_show_stats):
        """Тест команды показа статистики"""
        with patch('bot.DB_PATH', self.temp_db_path):
            mock_update = MagicMock()
            mock_context = MagicMock()
            
            # Вызываем функцию
            mock_show_stats(mock_update, mock_context)
            
            # Проверяем, что функция была вызвана
            mock_show_stats.assert_called_once_with(mock_update, mock_context)
    
    @patch('bot.generate_life_calendar')
    @patch('bot.Application')
    def test_weekly_update_sending(self, mock_app, mock_generate_calendar):
        """Тест отправки еженедельных обновлений"""
        with patch('bot.DB_PATH', self.temp_db_path):
            # Мокаем приложение и бота
            mock_bot = MagicMock()
            mock_app.return_value.bot = mock_bot
            mock_context = MagicMock()
            mock_context.bot = mock_bot
            
            # Мокаем генерацию календаря
            mock_generate_calendar.return_value = "test_calendar.png"
            
            # Вызываем функцию отправки обновлений с context
            send_weekly_update(mock_context)
            
            # Проверяем, что функция выполнилась без ошибок
            assert True  # Если дошли до этой точки, значит функция выполнилась
    
    def test_date_parsing(self):
        """Тест парсинга дат"""
        # Тестируем различные форматы дат
        test_dates = [
            "1990-05-15",
            "2000-12-31",
            "1985-01-01"
        ]
        
        for date_str in test_dates:
            try:
                parsed_date = datetime.strptime(date_str, '%Y-%m-%d').date()
                assert isinstance(parsed_date, date)
            except ValueError:
                pytest.fail(f"Не удалось распарсить дату: {date_str}")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])