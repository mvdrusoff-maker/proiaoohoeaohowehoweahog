import logging
import asyncio
import aiosqlite
import time
import os
import urllib.parse
import base64
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.strategy import FSMStrategy
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardRemove, ContentType, Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandStart, StateFilter
import aiohttp
import json

# Импорт конфигурации
try:
    from config import *
except ImportError:
    BOT_TOKEN = os.getenv('BOT_TOKEN', '8057715167:AAEEv01CdStyZrK_Icb6ktLppZU85tXvnHU')
    ADMIN_ID = int(os.getenv('ADMIN_ID', '7942871538'))
    YOOMONEY_CLIENT_ID = os.getenv('YOOMONEY_CLIENT_ID', '9D587BEF83BC7D307C5F30014EA89CF3D86383CF3B9D978E58C8A3BB0C074BBD')
    YOOMONEY_CLIENT_SECRET = os.getenv('YOOMONEY_CLIENT_SECRET', '44C7CD4D233416CF3DE4D8F6E86ADD8AA82890C6D4EE521F46FEABFA9A3F95C48AC256C4783F2C69477705CD04983B38E02D97837C7A1CBE2933929374190452')
    YOOMONEY_WALLET = os.getenv('YOOMONEY_WALLET', '4100119031273795')
    SBP_PHONE = os.getenv('SBP_PHONE', '+79931321491')
    BANK_CARD = os.getenv('BANK_CARD', '2204120124383866')
    BANK_NAME = os.getenv('BANK_NAME', 'ЮMoney')
    RECIPIENT_NAME = os.getenv('RECIPIENT_NAME', 'Анна В.')
    DATABASE_URL = os.getenv('DATABASE_URL', 'donations.db')
    DONATION_AMOUNTS = [40, 80, 120]
    PORT = int(os.getenv('PORT', 5000))

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Инициализация бота
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
storage = MemoryStorage()
dp = Dispatcher(storage=storage, fsm_strategy=FSMStrategy.USER_IN_CHAT)

# Классы состояний
class DonateForm(StatesGroup):
    choosing_amount = State()
    entering_custom_amount = State()
    entering_nickname = State()
    choosing_payment = State()
    waiting_screenshot = State()

class SupportForm(StatesGroup):
    choosing_reason = State()
    entering_description = State()
    in_chat = State()

class AdminForm(StatesGroup):
    viewing_orders = State()
    viewing_users = State()
    in_chat = State()

# Класс для работы с ЮMoney API
class YooMoneyAPI:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.base_url = "https://yoomoney.ru/api"
        self.token_url = "https://yoomoney.ru/oauth/token"
        self.access_token = None
        self.token_expires = 0
    
    async def get_access_token(self):
        """Получение access token через Client Credentials"""
        if self.access_token and time.time() < self.token_expires:
            return self.access_token
        
        auth_header = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        
        headers = {
            'Authorization': f'Basic {auth_header}',
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        data = {
            'grant_type': 'client_credentials',
            'scope': 'account-info operation-history payment-p2p'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.token_url, headers=headers, data=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        self.access_token = result['access_token']
                        self.token_expires = time.time() + result['expires_in'] - 300  # 5 минут запаса
                        logger.info("YooMoney access token получен")
                        return self.access_token
                    else:
                        error_text = await response.text()
                        logger.error(f"Ошибка получения токена: {response.status} - {error_text}")
                        return None
        except Exception as e:
            logger.error(f"Ошибка получения токена: {e}")
            return None
    
    async def check_payment(self, label):
        """Проверка статуса платежа по label"""
        access_token = await self.get_access_token()
        if not access_token:
            return False, None
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        data = {
            "type": "deposition",
            "label": label,
            "records": 10
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/operation-history",
                    headers=headers,
                    data=data
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        operations = result.get('operations', [])
                        for operation in operations:
                            if (operation.get('label') == label and 
                                operation.get('status') == 'success'):
                                return True, operation
                    elif response.status == 401:
                        logger.error("Токен устарел, обновляем...")
                        self.access_token = None  # Сбрасываем токен для обновления
                    return False, None
        except Exception as e:
            logger.error(f"YooMoney API error: {e}")
            return False, None

# Инициализация ЮMoney API
yoomoney_api = YooMoneyAPI(YOOMONEY_CLIENT_ID, YOOMONEY_CLIENT_SECRET)

# Инициализация базы данных
async def init_db():
    try:
        async with aiosqlite.connect(DATABASE_URL) as db:
            # Таблица пользователей
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    reg_date TEXT,
                    is_admin BOOLEAN DEFAULT FALSE
                )
            ''')
            
            # Таблица донатов
            await db.execute('''
                CREATE TABLE IF NOT EXISTS donations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    roblox_nickname TEXT,
                    amount INTEGER,
                    payment_method TEXT,
                    status TEXT DEFAULT 'new',
                    screenshot_id TEXT,
                    yoomoney_label TEXT,
                    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # Таблица тикетов поддержки
            await db.execute('''
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    reason TEXT,
                    description TEXT,
                    status TEXT DEFAULT 'open',
                    admin_id INTEGER,
                    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            # Таблица чатов
            await db.execute('''
                CREATE TABLE IF NOT EXISTS chats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    admin_id INTEGER,
                    status TEXT DEFAULT 'active',
                    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(user_id, admin_id)
                )
            ''')
            
            # Таблица сообщений
            await db.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER,
                    user_id INTEGER,
                    message_text TEXT,
                    is_from_admin BOOLEAN,
                    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (chat_id) REFERENCES chats(id)
                )
            ''')
            
            # Добавляем админа если нет
            await db.execute(
                'INSERT OR IGNORE INTO users (user_id, username, full_name, reg_date, is_admin) VALUES (?, ?, ?, ?, ?)',
                (ADMIN_ID, 'admin', 'Administrator', datetime.now().isoformat(), True)
            )
            
            await db.commit()
        logger.info("База данных инициализирована")
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")

# Клавиатуры
def main_menu_keyboard(user_id=None):
    if user_id == ADMIN_ID:
        return admin_main_keyboard()
    
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💎 Задонатить")],
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="📦 Мои донаты")],
            [KeyboardButton(text="🆘 Поддержка")]
        ],
        resize_keyboard=True
    )

def admin_main_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="🛒 Заказы"), KeyboardButton(text="👥 Пользователи")],
            [KeyboardButton(text="💬 Чаты поддержки")],
            [KeyboardButton(text="🔙 Выйти из админки")]
        ],
        resize_keyboard=True
    )

def orders_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🆕 Новые заказы"), KeyboardButton(text="✅ Выполненные")],
            [KeyboardButton(text="❌ Отмененные"), KeyboardButton(text="↩️ Возвраты")],
            [KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True
    )

def back_to_main_keyboard(user_id=None):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Главное меню")]],
        resize_keyboard=True
    )

def amount_choice_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="40 Robux"), KeyboardButton(text="80 Robux")],
            [KeyboardButton(text="120 Robux"), KeyboardButton(text="Другая сумма")],
            [KeyboardButton(text="🔙 Главное меню")]
        ],
        resize_keyboard=True
    )

def payment_method_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💳 ЮMoney")],
            [KeyboardButton(text="📱 СБП")],
            [KeyboardButton(text="💳 По номеру карты")],
            [KeyboardButton(text="🔙 Назад")]
        ],
        resize_keyboard=True
    )

def support_reasons_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="❌ Robux не пришли")],
            [KeyboardButton(text="⏳ Заказ долго не выполняется")],
            [KeyboardButton(text="💸 Заказ не создался, но оплата прошла")],
            [KeyboardButton(text="❓ Другое")],
            [KeyboardButton(text="🔙 Главное меню")]
        ],
        resize_keyboard=True
    )

def chat_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🚪 Выйти из чата")]
        ],
        resize_keyboard=True
    )

def yoomoney_payment_keyboard(url):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Оплатить", url=url)],
            [InlineKeyboardButton(text="✅ Я оплатил", callback_data="check_payment")]
        ]
    )

# Проверка является ли пользователь админом
async def is_admin(user_id):
    try:
        async with aiosqlite.connect(DATABASE_URL) as db:
            async with db.execute(
                'SELECT is_admin FROM users WHERE user_id = ?',
                (user_id,)
            ) as cursor:
                result = await cursor.fetchone()
                return result and result[0] == 1
    except Exception as e:
        logger.error(f"Ошибка проверки админа: {e}")
        return user_id == ADMIN_ID

# Обработчики команд
@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Нет username"
    full_name = message.from_user.full_name
    
    is_user_admin = await is_admin(user_id)
    
    try:
        async with aiosqlite.connect(DATABASE_URL) as db:
            await db.execute(
                'INSERT OR IGNORE INTO users (user_id, username, full_name, reg_date, is_admin) VALUES (?, ?, ?, ?, ?)',
                (user_id, username, full_name, datetime.now().isoformat(), is_user_admin)
            )
            await db.commit()
    except Exception as e:
        logger.error(f"Ошибка добавления пользователя: {e}")
    
    if is_user_admin:
        # Админская панель
        admin_text = (
            "👨‍💻 *Панель администратора*\n\n"
            "Добро пожаловать в админ-панель Mr.Robux!\n\n"
            "📊 *Доступные функции:*\n"
            "• Просмотр статистики\n"
            "• Управление заказами\n"
            "• Управление пользователями\n"
            "• Чат с поддержкой"
        )
        await message.answer(admin_text, reply_markup=admin_main_keyboard())
    else:
        # Обычное меню
        welcome_text = (
            "👋 Добро пожаловать в **Mr.Robux**!\n\n"
            "🎮 *Пополнение Robux с гарантией*\n\n"
            "💎 *Доступные способы оплаты:*\n"
            "• ЮMoney - быстрая оплата\n"
            "• СБП - по номеру телефона\n"
            "• Перевод на карту\n\n"
            "⚡ *Выдача от 1 минуты*\n"
            "🛡️ *100% гарантия возврата*"
        )
        await message.answer(welcome_text, reply_markup=main_menu_keyboard(user_id))

@dp.message(F.text == "🔙 Главное меню")
async def back_to_main_handler(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    is_user_admin = await is_admin(user_id)
    await message.answer("Главное меню:", reply_markup=main_menu_keyboard(user_id))

@dp.message(F.text == "🔙 Выйти из админки")
async def exit_admin_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu_keyboard(message.from_user.id))

# Админские команды
@dp.message(F.text == "📊 Статистика")
async def admin_stats_handler(message: Message):
    if not await is_admin(message.from_user.id):
        return
    
    try:
        async with aiosqlite.connect(DATABASE_URL) as db:
            # Статистика заказов
            async with db.execute(
                'SELECT COUNT(*), SUM(amount) FROM donations WHERE status = "completed"'
            ) as cursor:
                completed_orders, total_revenue = await cursor.fetchone()
                completed_orders = completed_orders or 0
                total_revenue = total_revenue or 0
            
            # Новые заказы
            async with db.execute(
                'SELECT COUNT(*) FROM donations WHERE status = "new"'
            ) as cursor:
                new_orders = (await cursor.fetchone())[0] or 0
            
            # Всего пользователей
            async with db.execute(
                'SELECT COUNT(*) FROM users'
            ) as cursor:
                total_users = (await cursor.fetchone())[0] or 0
            
            stats_text = (
                f"📊 *Статистика магазина*\n\n"
                f"👥 Пользователей: {total_users}\n"
                f"🛒 Заказов: {completed_orders + new_orders}\n"
                f"✅ Выполнено: {completed_orders}\n"
                f"🆕 Новых: {new_orders}\n"
                f"💰 Выручка: {total_revenue} Robux"
            )
            
            await message.answer(stats_text, reply_markup=admin_main_keyboard())
            
    except Exception as e:
        logger.error(f"Ошибка получения статистики: {e}")
        await message.answer("❌ Ошибка получения статистики")

@dp.message(F.text == "🛒 Заказы")
async def admin_orders_handler(message: Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        return
    
    await message.answer("📦 Выберите тип заказов:", reply_markup=orders_keyboard())
    await state.set_state(AdminForm.viewing_orders)

@dp.message(AdminForm.viewing_orders, F.text.in_(["🆕 Новые заказы", "✅ Выполненные", "❌ Отмененные", "↩️ Возвраты"]))
async def admin_orders_type_handler(message: Message, state: FSMContext):
    status_map = {
        "🆕 Новые заказы": "new",
        "✅ Выполненные": "completed", 
        "❌ Отмененные": "cancelled",
        "↩️ Возвраты": "refund"
    }
    
    status = status_map[message.text]
    
    try:
        async with aiosqlite.connect(DATABASE_URL) as db:
            async with db.execute(
                '''SELECT d.id, d.amount, d.payment_method, d.created_date, u.username 
                   FROM donations d 
                   LEFT JOIN users u ON d.user_id = u.user_id 
                   WHERE d.status = ? 
                   ORDER BY d.created_date DESC LIMIT 10''',
                (status,)
            ) as cursor:
                orders = await cursor.fetchall()
        
        if orders:
            orders_text = f"📦 {message.text}:\n\n"
            for order in orders:
                orders_text += f"🔹 #{order[0]}: {order[1]} Robux ({order[2]}) - @{order[4]} - {order[3][:10]}\n"
        else:
            orders_text = f"📭 {message.text} не найдено."
        
        await message.answer(orders_text, reply_markup=orders_keyboard())
        
    except Exception as e:
        logger.error(f"Ошибка получения заказов: {e}")
        await message.answer("❌ Ошибка получения заказов")

@dp.message(AdminForm.viewing_orders, F.text == "🔙 Назад")
async def admin_orders_back_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Админ панель:", reply_markup=admin_main_keyboard())

# Обработка доната
@dp.message(F.text == "💎 Задонатить")
async def donate_handler(message: Message, state: FSMContext):
    await message.answer("🎯 Выберите сумму доната:", reply_markup=amount_choice_keyboard())
    await state.set_state(DonateForm.choosing_amount)

@dp.message(DonateForm.choosing_amount, F.text.in_(["40 Robux", "80 Robux", "120 Robux"]))
async def process_amount_choice(message: Message, state: FSMContext):
    amount = int(message.text.split()[0])
    await state.update_data(amount=amount)
    await message.answer(f"Вы выбрали: {amount} Robux\n\nТеперь введите ваш никнейм в Roblox:", reply_markup=back_to_main_keyboard())
    await state.set_state(DonateForm.entering_nickname)

@dp.message(DonateForm.choosing_amount, F.text == "Другая сумма")
async def process_custom_amount_choice(message: Message, state: FSMContext):
    await message.answer("💎 Введите желаемую сумму Robux:", reply_markup=back_to_main_keyboard())
    await state.set_state(DonateForm.entering_custom_amount)

@dp.message(DonateForm.choosing_amount)
async def invalid_amount_choice(message: Message):
    await message.answer("Пожалуйста, выберите сумму из предложенных вариантов:", reply_markup=amount_choice_keyboard())

@dp.message(DonateForm.entering_custom_amount)
async def process_custom_amount(message: Message, state: FSMContext):
    if message.text == "🔙 Главное меню":
        await state.clear()
        await message.answer("Главное меню:", reply_markup=main_menu_keyboard(message.from_user.id))
        return
        
    try:
        amount = int(message.text)
        if amount <= 0:
            await message.answer("❌ Сумма должна быть положительной. Введите корректную сумму:")
            return
        
        await state.update_data(amount=amount)
        await message.answer(f"Вы ввели: {amount} Robux\n\nТеперь введите ваш никнейм в Roblox:", reply_markup=back_to_main_keyboard())
        await state.set_state(DonateForm.entering_nickname)
    except ValueError:
        await message.answer("❌ Пожалуйста, введите число:")

@dp.message(DonateForm.entering_nickname)
async def process_nickname(message: Message, state: FSMContext):
    if message.text == "🔙 Главное меню":
        await state.clear()
        await message.answer("Главное меню:", reply_markup=main_menu_keyboard(message.from_user.id))
        return
        
    nickname = message.text.strip()
    if len(nickname) < 3:
        await message.answer("❌ Никнейм слишком короткий. Введите корректный никнейм:")
        return
    
    await state.update_data(roblox_nickname=nickname)
    data = await state.get_data()
    amount = data['amount']
    
    await message.answer(
        f"🎯 **Подтверждение заявки**\n\n"
        f"💎 Сумма: {amount} Robux\n"
        f"👤 Никнейм: {nickname}\n\n"
        f"Теперь выберите способ оплаты:",
        reply_markup=payment_method_keyboard()
    )
    await state.set_state(DonateForm.choosing_payment)

# Обработка выбора способа оплаты
@dp.message(DonateForm.choosing_payment, F.text.in_(["💳 ЮMoney", "📱 СБП", "💳 По номеру карты"]))
async def process_payment_method(message: Message, state: FSMContext):
    payment_method = message.text.replace("💳 ", "").replace("📱 ", "")
    data = await state.get_data()
    
    user_id = message.from_user.id
    username = message.from_user.username or "Нет username"
    amount = data['amount']
    roblox_nickname = data['roblox_nickname']
    
    try:
        async with aiosqlite.connect(DATABASE_URL) as db:
            await db.execute(
                'INSERT INTO donations (user_id, roblox_nickname, amount, payment_method) VALUES (?, ?, ?, ?)',
                (user_id, roblox_nickname, amount, payment_method)
            )
            await db.commit()
            
            async with db.execute('SELECT last_insert_rowid()') as cursor:
                donation_id = (await cursor.fetchone())[0]
    except Exception as e:
        logger.error(f"Ошибка создания заказа: {e}")
        await message.answer("❌ Ошибка создания заказа. Попробуйте позже.", reply_markup=main_menu_keyboard(user_id))
        await state.clear()
        return
    
    if payment_method == "ЮMoney":
        # Создаем уникальный label
        label = f"donate_{user_id}_{int(time.time())}"
        
        # Кодируем target для URL
        target = urllib.parse.quote(f"Оплата заказа {user_id}")
        
        payment_url = f"https://yoomoney.ru/quickpay/confirm.xml?receiver={YOOMONEY_WALLET}&quickpay-form=shop&targets={target}&paymentType=AC&sum={amount}&label={label}"
        
        # Сохраняем label в базу
        try:
            async with aiosqlite.connect(DATABASE_URL) as db:
                await db.execute(
                    'UPDATE donations SET yoomoney_label = ? WHERE id = ?',
                    (label, donation_id)
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Ошибка сохранения label: {e}")
        
        payment_text = (
            f"💳 *Оплата через ЮMoney*\n\n"
            f"💰 Сумма: *{amount} руб.*\n"
            f"👤 Никнейм: {roblox_nickname}\n\n"
            f"Нажмите кнопку ниже для оплаты:\n"
            f"После оплаты нажмите '✅ Я оплатил'"
        )
        
        await message.answer(payment_text, reply_markup=yoomoney_payment_keyboard(payment_url))
        await state.update_data(donation_id=donation_id, yoomoney_label=label)
        
    elif payment_method == "СБП":
        await message.answer(
            f"💳 *Оплата через СБП*\n\n"
            f"💰 Сумма: *{amount} руб.*\n\n"
            f"📱 *Номер телефона для перевода:*\n"
            f"`{SBP_PHONE}`\n\n"
            f"👤 *Получатель:* {RECIPIENT_NAME}\n\n"
            f"*После оплаты пришлите скриншот перевода.*",
            reply_markup=back_to_main_keyboard()
        )
        await state.set_state(DonateForm.waiting_screenshot)
        await state.update_data(donation_id=donation_id)
        
    elif payment_method == "По номеру карты":
        await message.answer(
            f"💳 *Оплата по номеру карты*\n\n"
            f"💰 Сумма: *{amount} руб.*\n\n"
            f"💳 *Номер карты для перевода:*\n"
            f"`{BANK_CARD}`\n\n"
            f"🏦 *Банк:* {BANK_NAME}\n"
            f"👤 *Получатель:* {RECIPIENT_NAME}\n\n"
            f"*После оплаты пришлите скриншот перевода.*",
            reply_markup=back_to_main_keyboard()
        )
        await state.set_state(DonateForm.waiting_screenshot)
        await state.update_data(donation_id=donation_id)
    
    # Уведомление админу
    admin_text = (
        f"🎯 *Новый заказ #{donation_id}*\n\n"
        f"👤 Пользователь: @{username} (ID: {user_id})\n"
        f"🎮 Ник в Roblox: {roblox_nickname}\n"
        f"💎 Сумма: {amount} Robux\n"
        f"💳 Способ: {payment_method}\n"
        f"⏰ Время: {datetime.now().strftime('%H:%M %d.%m.%Y')}"
    )
    try:
        await bot.send_message(ADMIN_ID, admin_text)
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления админу: {e}")

@dp.message(DonateForm.choosing_payment, F.text == "🔙 Назад")
async def back_to_amount_choice(message: Message, state: FSMContext):
    await message.answer("Выберите сумму доната:", reply_markup=amount_choice_keyboard())
    await state.set_state(DonateForm.choosing_amount)

@dp.message(DonateForm.choosing_payment)
async def invalid_payment_choice(message: Message):
    await message.answer("Пожалуйста, выберите способ оплаты из предложенных вариантов:", reply_markup=payment_method_keyboard())

# Обработка callback для проверки оплаты
@dp.callback_query(F.data == "check_payment")
async def check_payment_callback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    label = data.get('yoomoney_label')
    
    if not label:
        await callback.answer("❌ Ошибка проверки оплаты")
        return
    
    success, operation = await yoomoney_api.check_payment(label)
    
    if success:
        # Обновляем статус заказа
        try:
            async with aiosqlite.connect(DATABASE_URL) as db:
                await db.execute(
                    'UPDATE donations SET status = ? WHERE yoomoney_label = ?',
                    ('completed', label)
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Ошибка обновления статуса: {e}")
        
        await callback.message.edit_text(
            "✅ *Оплата подтверждена!*\n\n"
            "Robux будут зачислены на ваш аккаунт в течение 5 минут.",
            reply_markup=None
        )
        await state.clear()
    else:
        await callback.answer("❌ Оплата не найдена. Попробуйте позже.")

# Обработка скриншотов
@dp.message(DonateForm.waiting_screenshot, F.content_type == ContentType.PHOTO)
async def process_screenshot(message: Message, state: FSMContext):
    data = await state.get_data()
    donation_id = data['donation_id']
    screenshot_id = message.photo[-1].file_id
    
    try:
        async with aiosqlite.connect(DATABASE_URL) as db:
            await db.execute(
                'UPDATE donations SET screenshot_id = ?, status = ? WHERE id = ?',
                (screenshot_id, 'pending', donation_id)
            )
            await db.commit()
    except Exception as e:
        logger.error(f"Ошибка сохранения скриншота: {e}")
    
    await message.answer(
        "✅ Скриншот принят! Оператор проверит оплату в течение 15 минут.",
        reply_markup=main_menu_keyboard(message.from_user.id)
    )
    
    # Получаем информацию о заказе для админа
    try:
        async with aiosqlite.connect(DATABASE_URL) as db:
            async with db.execute(
                'SELECT payment_method, amount FROM donations WHERE id = ?',
                (donation_id,)
            ) as cursor:
                result = await cursor.fetchone()
                payment_method = result[0] if result else "unknown"
                amount = result[1] if result else 0
    except Exception as e:
        logger.error(f"Ошибка получения данных заказа: {e}")
        payment_method = "unknown"
        amount = 0
    
    # Отправка скриншота админу
    caption = (
        f"📸 *Скриншот оплаты для заказа #{donation_id}*\n\n"
        f"💳 Способ: {payment_method}\n"
        f"💰 Сумма: {amount} руб.\n"
        f"⏰ Время: {datetime.now().strftime('%H:%M %d.%m.%Y')}"
    )
    
    try:
        await bot.send_photo(ADMIN_ID, screenshot_id, caption=caption)
    except Exception as e:
        logger.error(f"Ошибка отправки скриншота админу: {e}")
    
    await state.clear()

@dp.message(DonateForm.waiting_screenshot)
async def wrong_content_type(message: Message):
    await message.answer("❌ Пожалуйста, отправьте скриншот перевода в виде фотографии.", reply_markup=back_to_main_keyboard())

# Фоновая задача проверки платежей
async def check_payments_task():
    while True:
        try:
            async with aiosqlite.connect(DATABASE_URL) as db:
                async with db.execute(
                    'SELECT id, yoomoney_label, user_id FROM donations WHERE status = "new" AND payment_method = "ЮMoney"'
                ) as cursor:
                    pending_payments = await cursor.fetchall()
                    
                    for payment_id, label, user_id in pending_payments:
                        success, operation = await yoomoney_api.check_payment(label)
                        if success:
                            # Обновляем статус
                            await db.execute(
                                'UPDATE donations SET status = ? WHERE id = ?',
                                ('completed', payment_id)
                            )
                            await db.commit()
                            
                            # Уведомляем пользователя
                            try:
                                await bot.send_message(
                                    user_id,
                                    "✅ *Оплата подтверждена!*\n\n"
                                    "Robux зачислены на ваш аккаунт."
                                )
                            except:
                                pass
            
            await asyncio.sleep(60)  # Проверяем каждую минуту
            
        except Exception as e:
            logger.error(f"Ошибка проверки платежей: {e}")
            await asyncio.sleep(300)

# Запуск бота
async def main():
    try:
        await init_db()
        logger.info("Бот запускается...")
        
        # Проверяем подключение к ЮMoney API
        logger.info("Проверка подключения к ЮMoney...")
        access_token = await yoomoney_api.get_access_token()
        if access_token:
            logger.info("✅ Подключение к ЮMoney успешно")
        else:
            logger.warning("⚠️ Не удалось подключиться к ЮMoney API")
        
        # Запускаем фоновую задачу проверки платежей
        asyncio.create_task(check_payments_task())
        
        # Останавливаем предыдущие вебхуки если были
        await bot.delete_webhook(drop_pending_updates=True)
        
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")
        await asyncio.sleep(5)
        await main()

if __name__ == '__main__':
    asyncio.run(main())
