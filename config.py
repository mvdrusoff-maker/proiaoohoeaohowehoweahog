import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Настройки бота
BOT_TOKEN = os.getenv('BOT_TOKEN', '8057715167:AAGyNg1mln9EaCZVA88G0nrGa_acDAQpyMg')
ADMIN_ID = int(os.getenv('ADMIN_ID', '7942871538'))

# Настройки ЮMoney OAuth 2.0
YOOMONEY_CLIENT_ID = os.getenv('YOOMONEY_CLIENT_ID', '9D587BEF83BC7D307C5F30014EA89CF3D86383CF3B9D978E58C8A3BB0C074BBD')
YOOMONEY_CLIENT_SECRET = os.getenv('YOOMONEY_CLIENT_SECRET', '44C7CD4D233416CF3DE4D8F6E86ADD8AA82890C6D4EE521F46FEABFA9A3F95C48AC256C4783F2C69477705CD04983B38E02D97837C7A1CBE2933929374190452')
YOOMONEY_REDIRECT_URI = os.getenv('YOOMONEY_REDIRECT_URI', 'https://yoomoney.ru/authorization')
YOOMONEY_WALLET = os.getenv('YOOMONEY_WALLET', '4100119031273795')

# Реквизиты для СБП и карты
SBP_PHONE = os.getenv('SBP_PHONE', '+79931321491')
BANK_CARD = os.getenv('BANK_CARD', '2204120124383866')
BANK_NAME = os.getenv('BANK_NAME', 'ЮMoney')
RECIPIENT_NAME = os.getenv('RECIPIENT_NAME', 'Анна В.')

# Настройки базы данных
DATABASE_URL = os.getenv('DATABASE_URL', 'donations.db')

# Суммы для доната
DONATION_AMOUNTS = [40, 80, 120]

# Порт для Railway
PORT = int(os.getenv('PORT', 5000))
