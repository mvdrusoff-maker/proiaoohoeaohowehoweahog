import logging
import asyncio
import aiosqlite
import time
import os
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.fsm.strategy import FSMStrategy
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardRemove, ContentType, Message, ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import Command, CommandStart, StateFilter
import aiohttp
import json
import urllib.parse
import base64

# Импорт конфигурации
try:
    from config import *
except ImportError:
    BOT_TOKEN = os.getenv('BOT_TOKEN', '8057715167:AAEEv01CdStyZrK_Icb6ktLppZU85tXvnHU')
    ADMIN_ID = int(os.getenv('ADMIN_ID', '7942871538'))
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

# Инициализация базы данных
async def init_db():
    try:
        async with aiosqlite.connect(DATABASE_URL) as db:
            await db.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    full_name TEXT,
                    reg_date TEXT
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS donations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    roblox_nickname TEXT,
                    amount INTEGER,
                    payment_method TEXT,
                    status TEXT DEFAULT 'new',
                    screenshot_id TEXT,
                    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            await db.execute('''
                CREATE TABLE IF NOT EXISTS support_tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    reason TEXT,
                    description TEXT,
                    status TEXT DEFAULT 'open',
                    created_date TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            await db.commit()
        logger.info("База данных инициализирована")
    except Exception as e:
        logger.error(f"Ошибка инициализации БД: {e}")

# Клавиатуры
def main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💎 Задонатить")],
            [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="📦 Мои донаты")],
            [KeyboardButton(text="🆘 Поддержка")]
        ],
        resize_keyboard=True
    )

def back_to_main_keyboard():
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

# Обработчики команд
@dp.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "Нет username"
    full_name = message.from_user.full_name
    
    try:
        async with aiosqlite.connect(DATABASE_URL) as db:
            await db.execute(
                'INSERT OR IGNORE INTO users (user_id, username, full_name, reg_date) VALUES (?, ?, ?, ?)',
                (user_id, username, full_name, datetime.now().isoformat())
            )
            await db.commit()
    except Exception as e:
        logger.error(f"Ошибка добавления пользователя: {e}")
    
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
    
    await message.answer(welcome_text, reply_markup=main_menu_keyboard())

@dp.message(F.text == "🔙 Главное меню")
async def back_to_main_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu_keyboard())

@dp.message(F.text == "💎 Задонатить")
async def donate_handler(message: Message, state: FSMContext):
    await message.answer("🎯 Выберите сумму доната:", reply_markup=amount_choice_keyboard())
    await state.set_state(DonateForm.choosing_amount)

@dp.message(F.text == "👤 Профиль")
async def profile_handler(message: Message):
    user_id = message.from_user.id
    try:
        async with aiosqlite.connect(DATABASE_URL) as db:
            async with db.execute(
                'SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM donations WHERE user_id = ? AND status = "completed"',
                (user_id,)
            ) as cursor:
                result = await cursor.fetchone()
                donations_count = result[0] if result else 0
                total_donated = result[1] if result else 0
    except Exception as e:
        logger.error(f"Ошибка получения профиля: {e}")
        donations_count = 0
        total_donated = 0
    
    profile_text = (
        f"📊 **Ваш профиль**\n\n"
        f"🆔 ID: {user_id}\n"
        f"👤 Имя: {message.from_user.full_name}\n"
        f"📦 Завершенных донатов: {donations_count}\n"
        f"💎 Всего получено Robux: {total_donated}"
    )
    await message.answer(profile_text, reply_markup=main_menu_keyboard())

@dp.message(F.text == "📦 Мои донаты")
async def donations_handler(message: Message):
    user_id = message.from_user.id
    try:
        async with aiosqlite.connect(DATABASE_URL) as db:
            async with db.execute(
                'SELECT id, amount, status, payment_method, created_date FROM donations WHERE user_id = ? ORDER BY created_date DESC LIMIT 5',
                (user_id,)
            ) as cursor:
                donations = await cursor.fetchall()
    except Exception as e:
        logger.error(f"Ошибка получения донатов: {e}")
        donations = []
    
    if donations:
        donations_text = "📋 **Последние заявки:**\n\n"
        for don in donations:
            status_emoji = "🆕" if don[2] == "new" else "✅" if don[2] == "completed" else "❌"
            donations_text += f"{status_emoji} #{don[0]}: {don[1]} Robux ({don[3]}) - {don[4][:10]}\n"
    else:
        donations_text = "📭 У вас еще не было заявок на донат."
    
    await message.answer(donations_text, reply_markup=main_menu_keyboard())

@dp.message(F.text == "🆘 Поддержка")
async def support_handler(message: Message, state: FSMContext):
    support_text = (
        "🆘 **Поддержка**\n\n"
        "Выберите причину обращения:"
    )
    await message.answer(support_text, reply_markup=support_reasons_keyboard())
    await state.set_state(SupportForm.choosing_reason)

# Обработка выбора суммы
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
        await message.answer("Главное меню:", reply_markup=main_menu_keyboard())
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
        await message.answer("Главное меню:", reply_markup=main_menu_keyboard())
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
        await message.answer("❌ Ошибка создания заказа. Попробуйте позже.", reply_markup=main_menu_keyboard())
        await state.clear()
        return
    
    if payment_method == "ЮMoney":
        payment_url = f"https://yoomoney.ru/quickpay/confirm.xml?receiver={YOOMONEY_WALLET}&quickpay-form=shop&targets=Оплата заказа {donation_id}&paymentType=AC&sum={amount}&label=donate_{donation_id}"
        
        await message.answer(
            f"💳 *Оплата через ЮMoney*\n\n"
            f"💰 Сумма: *{amount} руб.*\n\n"
            f"👉 [Перейти к оплате]({payment_url})\n\n"
            f"*После оплаты пришлите скриншот чека для подтверждения.*",
            reply_markup=back_to_main_keyboard()
        )
        
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
        reply_markup=main_menu_keyboard()
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

# Обработка поддержки
@dp.message(SupportForm.choosing_reason, F.text.in_(["❌ Robux не пришли", "⏳ Заказ долго не выполняется", "💸 Заказ не создался, но оплата прошла", "❓ Другое"]))
async def support_reason_handler(message: Message, state: FSMContext):
    await state.update_data(reason=message.text)
    
    if message.text == "❓ Другое":
        await message.answer("📝 Опишите вашу проблему подробно:", reply_markup=back_to_main_keyboard())
        await state.set_state(SupportForm.entering_description)
    else:
        user_id = message.from_user.id
        username = message.from_user.username or "Нет username"
        full_name = message.from_user.full_name
        
        try:
            async with aiosqlite.connect(DATABASE_URL) as db:
                await db.execute(
                    'INSERT INTO support_tickets (user_id, reason, status) VALUES (?, ?, ?)',
                    (user_id, message.text, 'open')
                )
                await db.commit()
        except Exception as e:
            logger.error(f"Ошибка создания тикета: {e}")
        
        ticket_text = (
            f"🎫 **Новый тикет поддержки**\n\n"
            f"👤 Пользователь: {full_name} (@{username})\n"
            f"📌 Причина: {message.text}\n"
            f"🆔 ID: {user_id}\n"
            f"⏰ Время: {datetime.now().strftime('%H:%M %d.%m.%Y')}"
        )
        
        try:
            await bot.send_message(ADMIN_ID, ticket_text)
        except Exception as e:
            logger.error(f"Ошибка отправки тикета админу: {e}")
        
        await message.answer("✅ Ваше обращение отправлено! Оператор свяжется с вами в течение 15 минут.", 
                           reply_markup=main_menu_keyboard())
        await state.clear()

@dp.message(SupportForm.entering_description)
async def support_description_handler(message: Message, state: FSMContext):
    if message.text == "🔙 Главное меню":
        await state.clear()
        await message.answer("Главное меню:", reply_markup=main_menu_keyboard())
        return
        
    data = await state.get_data()
    reason = data.get('reason', 'Другое')
    
    user_id = message.from_user.id
    username = message.from_user.username or "Нет username"
    full_name = message.from_user.full_name
    
    try:
        async with aiosqlite.connect(DATABASE_URL) as db:
            await db.execute(
                'INSERT INTO support_tickets (user_id, reason, description, status) VALUES (?, ?, ?, ?)',
                (user_id, reason, message.text, 'open')
            )
            await db.commit()
    except Exception as e:
        logger.error(f"Ошибка сохранения тикета: {e}")
    
    ticket_text = (
        f"🎫 **Новый тикет поддержки**\n\n"
        f"👤 Пользователь: {full_name} (@{username})\n"
        f"📌 Причина: {reason}\n"
        f"📝 Описание: {message.text}\n"
        f"🆔 ID: {user_id}\n"
        f"⏰ Время: {datetime.now().strftime('%H:%M %d.%m.%Y')}"
    )
    
    try:
        await bot.send_message(ADMIN_ID, ticket_text)
    except Exception as e:
        logger.error(f"Ошибка отправки тикета админу: {e}")
    
    await message.answer("✅ Ваше обращение отправлено! Оператор свяжется с вами в течение 15 минут.", 
                       reply_markup=main_menu_keyboard())
    await state.clear()

@dp.message(SupportForm.choosing_reason, F.text == "🔙 Главное меню")
async def support_back_to_main(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Главное меню:", reply_markup=main_menu_keyboard())

@dp.message(SupportForm.choosing_reason)
async def invalid_support_reason(message: Message):
    await message.answer("Пожалуйста, выберите причину из предложенных вариантов:", reply_markup=support_reasons_keyboard())

# Команда для получения реквизитов
@dp.message(Command("requisites"))
async def cmd_requisites(message: Message):
    requisites_text = (
        "🏦 *Наши реквизиты для оплаты:*\n\n"
        f"📱 *СБП (по номеру телефона):*\n"
        f"`{SBP_PHONE}`\n"
        f"👤 {RECIPIENT_NAME}\n\n"
        f"💳 *По номеру карты:*\n"
        f"`{BANK_CARD}`\n"
        f"🏦 {BANK_NAME}\n"
        f"👤 {RECIPIENT_NAME}\n\n"
        f"💎 *ЮMoney кошелек:*\n"
        f"`{YOOMONEY_WALLET}`\n\n"
        f"*В комментарии к переводу укажите ваш ID: {message.from_user.id}*"
    )
    
    await message.answer(requisites_text, reply_markup=main_menu_keyboard())

# Команда для проверки статуса заказа
@dp.message(Command("status"))
async def cmd_status(message: Message):
    user_id = message.from_user.id
    
    try:
        async with aiosqlite.connect(DATABASE_URL) as db:
            async with db.execute(
                'SELECT id, amount, status, payment_method, created_date FROM donations WHERE user_id = ? ORDER BY created_date DESC LIMIT 1',
                (user_id,)
            ) as cursor:
                last_order = await cursor.fetchone()
    except Exception as e:
        logger.error(f"Ошибка получения статуса: {e}")
        last_order = None
    
    if last_order:
        order_id, amount, status, payment_method, created_date = last_order
        
        status_emoji = {
            'new': '🆕',
            'pending': '⏳',
            'completed': '✅',
            'cancelled': '❌'
        }.get(status, '📊')
        
        status_text = {
            'new': 'ожидает оплаты',
            'pending': 'проверяется',
            'completed': 'выполнен',
            'cancelled': 'отменен'
        }.get(status, status)
        
        response = (
            f"{status_emoji} *Статус последнего заказа *#{order_id}\n\n"
            f"💎 Сумма: {amount} Robux\n"
            f"💳 Способ: {payment_method}\n"
            f"📊 Статус: {status_text}\n"
            f"📅 Дата: {created_date}\n\n"
        )
        
        if status == 'new':
            response += "ℹ️ Для получения реквизитов используйте /requisites"
        elif status == 'pending':
            response += "⏳ Заказ в обработке, ожидайте выдачи Robux"
            
    else:
        response = "📭 У вас еще не было заказов."
    
    await message.answer(response, reply_markup=main_menu_keyboard())

# Админ команды
@dp.message(Command("admin"))
async def cmd_admin(message: Message):
    if message.from_user.id != ADMIN_ID:
        await message.answer("❌ Доступ запрещен", reply_markup=main_menu_keyboard())
        return
    
    admin_text = (
        "👨‍💻 *Панель администратора*\n\n"
        "Доступные команды:\n"
        "/stats - Статистика\n"
        "/orders - Список заказов\n"
        "/users - Список пользователей"
    )
    await message.answer(admin_text, reply_markup=main_menu_keyboard())

# Запуск бота
async def main():
    try:
        await init_db()
        logger.info("Бот запускается...")
        
        # Останавливаем предыдущие вебхуки если были
        await bot.delete_webhook(drop_pending_updates=True)
        
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Ошибка запуска бота: {e}")
        # Перезапуск через 5 секунд при ошибке
        await asyncio.sleep(5)
        await main()

if __name__ == '__main__':
    asyncio.run(main())
