# Weekly Reminder Life Telegram Bot

Телеграм-бот, который отправляет пользователям еженедельные напоминания о том, сколько недель они прожили с момента рождения.

## Особенности

- Регистрация пользователей с указанием имени и даты рождения
- Еженедельные уведомления по воскресеньям в 21:00
- Хранение данных в SQLite базе данных
- Контейнеризация с помощью Docker

## Запуск с использованием Docker

### Сборка и запуск с помощью docker-compose

1. Убедитесь, что у вас установлены Docker и docker-compose
2. Клонируйте репозиторий
3. Запустите контейнер:

```bash
docker-compose up -d
```

Для просмотра логов:

```bash
docker-compose logs -f
```

### Сборка и запуск вручную

1. Соберите Docker-образ:

```bash
docker build -t weekly-reminder-bot .
```

2. Запустите контейнер:

```bash
docker run -d --name weekly-reminder-bot \
  -v $(pwd)/data:/app/data \
  weekly-reminder-bot
```

## Настройка

Перед запуском необходимо указать токен вашего Telegram-бота в переменной окружения `BOT_TOKEN`. Вы можете получить токен у [@BotFather](https://t.me/BotFather).

### Настройка токена

1. В файле `docker-compose.yml` укажите ваш токен в переменной окружения:

```yaml
environment:
  - DB_PATH=/app/data/bot_users.db
  - BOT_TOKEN=ваш_токен_бота
```

2. Или при запуске вручную укажите переменную окружения:

```bash
docker run -d --name weekly-reminder-bot \
  -v $(pwd)/data:/app/data \
  -e BOT_TOKEN=ваш_токен_бота \
  weekly-reminder-bot
```

## Структура проекта

- `bot.py` - основной файл бота
- `requirements.txt` - зависимости проекта
- `Dockerfile` - инструкции для сборки Docker-образа
- `docker-compose.yml` - конфигурация для docker-compose
- `data/` - директория для хранения базы данных (создается автоматически)

## Данные

База данных SQLite хранится в директории `data/` и сохраняется между перезапусками контейнера благодаря использованию Docker-тома.