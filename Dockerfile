FROM python:3.11-slim

WORKDIR /app

# Копируем файлы зависимостей
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем файлы проекта
COPY bot.py .

# Создаем директорию для данных
RUN mkdir -p /app/data

# Указываем, что база данных должна храниться в директории с данными
ENV DB_PATH=/app/data/bot_users.db

# Переменная для токена бота (будет переопределена в docker-compose.yml)
ENV BOT_TOKEN=""

# Запускаем бот
CMD ["python", "bot.py"]