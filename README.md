# 🤖 Mr.Robux Donate Bot

Telegram бот для приема донатов на Robux.

## 🚀 Быстрый старт

1. **Клонируйте репозиторий**
2. **Установите зависимости**: `pip install -r requirements.txt`
3. **Настройте переменные**: скопируйте `.env.example` в `.env`
4. **Запустите бота**: `python main.py`

## 🌐 Деплой на хостинг

### Render.com (рекомендуется)
1. Подключите GitHub репозиторий
2. Создайте Web Service
3. Добавьте переменные окружения
4. Бот запустится автоматически

### Railway.app
1. Подключите GitHub репозиторий  
2. Добавьте переменные в Settings → Variables
3. Бот запустится автоматически

### Heroku
```bash
heroku create your-bot-name
heroku config:set BOT_TOKEN=your_token
git push heroku main
