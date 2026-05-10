import telebot
from telebot import types
from datetime import datetime
import json
import os

# ==================== КОНФІГУРАЦІЯ ====================

# Використання змінних оточення для безпеки
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID'))

if not BOT_TOKEN or not ADMIN_ID:
    print("❌ ПОМИЛКА: BOT_TOKEN або ADMIN_ID не встановлені!")
    print("Встановіть змінні оточення на Render")
    exit(1)

try:
    bot = telebot.TeleBot(BOT_TOKEN)
    print("✅ Бот успішно ініціалізований")
except Exception as e:
    print(f"❌ Помилка ініціалізації: {e}")
    exit(1)

# ==================== КОНСТАНТИ ====================

DATA_FILE = "chat_sessions.json"

active_chats = {}
waiting_for_phone = {}
waiting_for_name = {}

# ==================== ДОПОМІЖНІ ФУНКЦІЇ ====================

def get_main_keyboard():
    """Головна клавіатура бота"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("✍️ Написати майстру")
    btn2 = types.KeyboardButton("📅 Графік роботи")
    markup.add(btn1, btn2)
    return markup

def get_phone_keyboard():
    """Клавіатура для запиту номера телефону"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    btn = types.KeyboardButton("📱 Поділитися номером", request_contact=True)
    btn_cancel = types.KeyboardButton("❌ Скасувати")
    markup.add(btn)
    markup.add(btn_cancel)
    return markup

def get_chat_keyboard():
    """Клавіатура під час активного чату"""
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn = types.KeyboardButton("🛑 Завершити чат")
    markup.add(btn)
    return markup

def load_chats():
    """Завантажити дані чатів з файлу"""
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_chats(data):
    """Зберегти дані чатів у файл"""
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def is_working_hours():
    """Перевірка чи сервіс працює"""
    now = datetime.now()
    day_of_week = now.weekday()  # 0 = пн, 1 = вт, ..., 6 = вс
    hour = now.hour
    
    # Неділя: закрито
    if day_of_week == 6:
        return False
    
    # Субота: 11:00 - 14:00
    if day_of_week == 5:
        return 11 <= hour < 14
    
    # Пн-Пт: 10:00 - 18:00
    return 10 <= hour < 18

# ==================== КОМАНДИ ====================

@bot.message_handler(commands=['start'])
def start(message):
    """Команда /start"""
    user_name = message.from_user.first_name or "Користувач"
    bot.send_message(
        message.chat.id,
        f"🔧 Привіт, {user_name}!\n\n"
        f"Добро пожалуйте до <b>ТОП СЕРВІС</b> 🏢\n\n"
        f"Ми готові допомогти вам з будь-якими проблемами!",
        parse_mode='HTML',
        reply_markup=get_main_keyboard()
    )

@bot.message_handler(commands=['help'])
def help_command(message):
    """Команда /help"""
    bot.send_message(
        message.chat.id,
        "ℹ️ <b>Як користуватись ботом:</b>\n\n"
        "📱 <b>Написати майстру</b> - скласти заявку на обслуговування\n"
        "📅 <b>Графік роботи</b> - дізнатись час роботи\n\n"
        "Під час активного чату можна легко спілкуватись з майстром!",
        parse_mode='HTML',
        reply_markup=get_main_keyboard()
    )

# ==================== ОБРОБКА ОСНОВНИХ КНОПОК ====================

@bot.message_handler(func=lambda message: message.text == "📅 Графік роботи")
def show_schedule(message):
    """Показати графік роботи"""
    bot.send_message(
        message.chat.id,
        "📅 <b>Графік роботи ТОП СЕРВІС</b>\n\n"
        "Понеділок - П'ятниця: 10:00 - 18:00\n"
        "Субота: 11:00 - 14:00\n"
        "Неділя: Вихідний\n\n"
        "Зв'яжіться з нами у зазначений час!",
        parse_mode='HTML',
        reply_markup=get_main_keyboard()
    )

@bot.message_handler(func=lambda message: message.text == "✍️ Написати майстру")
def start_request(message):
    """Почати процес написання до майстру"""
    if not is_working_hours():
        bot.send_message(
            message.chat.id,
            "⏰ На жаль, сервіс наразі закритий.\n\n"
            "📅 <b>Графік роботи ТОП СЕРВІС</b>\n\n"
            "Понеділок - П'ятниця: 10:00 - 18:00\n"
            "Субота: 11:00 - 14:00\n"
            "Неділя: Вихідний",
            parse_mode='HTML',
            reply_markup=get_main_keyboard()
        )
        return
    
    waiting_for_phone[message.chat.id] = True
    
    bot.send_message(
        message.chat.id,
        "📱 Будь ласка, поділіться вашим номером телефону:",
        reply_markup=get_phone_keyboard()
    )

@bot.message_handler(func=lambda message: message.text == "❌ Скасувати")
def cancel_request(message):
    """Скасувати заявку"""
    if message.chat.id in waiting_for_phone:
        del waiting_for_phone[message.chat.id]
    if message.chat.id in waiting_for_name:
        del waiting_for_name[message.chat.id]
    
    bot.send_message(
        message.chat.id,
        "❌ Заявку скасовано.",
        reply_markup=get_main_keyboard()
    )

# ==================== ОБРОБКА КОНТАКТУ ====================

@bot.message_handler(content_types=['contact'])
def handle_contact(message):
    """Обробити отримання номера телефону"""
    if message.chat.id not in waiting_for_phone:
        return
    
    phone = message.contact.phone_number
    
    if message.chat.id not in active_chats:
        active_chats[message.chat.id] = {}
    
    active_chats[message.chat.id]['phone'] = phone
    active_chats[message.chat.id]['user_id'] = message.chat.id
    
    del waiting_for_phone[message.chat.id]
    waiting_for_name[message.chat.id] = True
    
    bot.send_message(
        message.chat.id,
        f"✅ Номер отримано: {phone}\n\n👤 Тепер напишіть ваше ім'я:",
        reply_markup=types.ReplyKeyboardRemove()
    )

# ==================== ОБРОБКА ІМЕНІ ====================

@bot.message_handler(func=lambda message: message.chat.id in waiting_for_name)
def handle_name(message):
    """Обробити отримання імені користувача"""
    if message.text.startswith('/'):
        bot.send_message(message.chat.id, "⚠️ Будь ласка, напишіть ваше ім'я:")
        return
    
    name = message.text
    
    active_chats[message.chat.id]['name'] = name
    active_chats[message.chat.id]['status'] = 'waiting_admin'
    active_chats[message.chat.id]['timestamp'] = datetime.now().isoformat()
    
    phone = active_chats[message.chat.id]['phone']
    user_id = message.chat.id
    
    del waiting_for_name[message.chat.id]
    
    bot.send_message(
        message.chat.id,
        f"✅ Дякуємо, {name}!\n\n"
        f"Ваша заявка надіслана майстру.\n"
        f"Очікуйте на відповідь...",
        reply_markup=get_main_keyboard()
    )
    
    # Повідомлення адміністратору
    admin_message = (
        f"📬 <b>НОВА ЗАЯВКА</b>\n\n"
        f"👤 <b>Ім'я:</b> {name}\n"
        f"📱 <b>Номер телефону:</b> {phone}\n"
        f"🆔 <b>ID користувача:</b> {user_id}\n"
        f"⏰ <b>Час:</b> {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n\n"
        f"<i>Натисніть кнопку нижче, щоб відкрити чат</i>"
    )
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💬 Відкрити чат", callback_data=f"open_chat_{user_id}"))
    
    bot.send_message(ADMIN_ID, admin_message, parse_mode='HTML', reply_markup=markup)
    save_chats(active_chats)

# ==================== ОБРОБКА CALLBACK ====================

@bot.callback_query_handler(func=lambda call: call.data.startswith('open_chat_'))
def open_chat(call):
    """Відкрити чат з користувачем"""
    user_id = int(call.data.split('_')[-1])
    
    if user_id not in active_chats:
        bot.answer_callback_query(call.id, "❌ Користувач не знайдений", show_alert=True)
        return
    
    active_chats[user_id]['status'] = 'chat_active'
    active_chats[user_id]['admin_id'] = call.from_user.id
    save_chats(active_chats)
    
    user_name = active_chats[user_id]['name']
    
    bot.send_message(
        user_id,
        f"✅ <b>Майстер готовий до спілкування!</b>\n\n"
        f"Чат з майстром відкритий. Ви можете спілкуватись.\n\n"
        f"Натисніть <b>'🛑 Завершити чат'</b> коли завершите.",
        parse_mode='HTML',
        reply_markup=get_chat_keyboard()
    )
    
    bot.send_message(
        ADMIN_ID,
        f"✅ <b>Чат з {user_name} відкритий</b>\n\n"
        f"Можете почати спілкування.\n\n"
        f"Натисніть <b>'🛑 Завершити чат'</b> коли завершите.",
        parse_mode='HTML',
        reply_markup=get_chat_keyboard()
    )
    
    bot.answer_callback_query(call.id, "✅ Чат відкритий", show_alert=False)

# ==================== СПІЛКУВАННЯ В ЧАТІ ====================

@bot.message_handler(func=lambda message: message.chat.id in active_chats and 
                    active_chats[message.chat.id].get('status') == 'chat_active')
def handle_chat_message(message):
    """Обробити повідомлення під час активного чату"""
    
    user_id = message.chat.id
    
    if message.text == "🛑 Завершити чат":
        close_chat(message)
        return
    
    is_admin = user_id == ADMIN_ID
    is_user = user_id in active_chats
    
    if not (is_admin or is_user):
        return
    
    try:
        if is_user:
            other_id = active_chats[user_id].get('admin_id')
            sender_type = "👤 Користувач"
        else:
            other_id = None
            for chat_id, chat_data in active_chats.items():
                if chat_data.get('admin_id') == ADMIN_ID and chat_data.get('status') == 'chat_active':
                    other_id = chat_id
                    break
            
            if not other_id:
                bot.send_message(ADMIN_ID, "⚠️ Активний чат не знайдений.")
                return
            
            sender_type = "🛠️ Майстер"
        
        formatted_message = f"{sender_type}: {message.text}"
        bot.send_message(other_id, formatted_message)
        
    except Exception as e:
        bot.send_message(user_id, f"❌ Помилка відправки: {str(e)}")

def close_chat(message):
    """Завершити чат"""
    user_id = message.chat.id
    
    if user_id not in active_chats:
        bot.send_message(user_id, "⚠️ Активного чату не знайдено.")
        return
    
    is_user = user_id in active_chats
    
    if is_user:
        other_id = active_chats[user_id].get('admin_id')
        user_name = active_chats[user_id].get('name', 'Користувач')
    else:
        other_id = None
        for chat_id, chat_data in active_chats.items():
            if chat_data.get('admin_id') == ADMIN_ID and chat_data.get('status') == 'chat_active':
                other_id = chat_id
                user_name = chat_data.get('name', 'Користувач')
                break
        
        if not other_id:
            bot.send_message(ADMIN_ID, "⚠️ Активний чат не знайдений.")
            return
    
    active_chats[other_id]['status'] = 'closed'
    save_chats(active_chats)
    
    bot.send_message(
        user_id,
        "🛑 <b>Чат завершено</b>\n\nДякуємо за спілкування!",
        parse_mode='HTML',
        reply_markup=get_main_keyboard()
    )
    
    bot.send_message(
        other_id,
        f"🛑 <b>Чат з {user_name} завершено</b>",
        parse_mode='HTML',
        reply_markup=get_main_keyboard()
    )

# ==================== ОБРОБКА ІНШИХ ПОВІДОМЛЕНЬ ====================

@bot.message_handler(func=lambda message: True)
def handle_other_messages(message):
    """Обробити інші повідомлення"""
    if message.chat.id in waiting_for_phone:
        bot.send_message(
            message.chat.id,
            "⚠️ Будь ласка, поділіться номером телефону за допомогою кнопки нижче:",
            reply_markup=get_phone_keyboard()
        )
    elif message.chat.id in waiting_for_name:
        bot.send_message(message.chat.id, "⚠️ Будь ласка, напишіть ваше ім'я:")
    else:
        bot.send_message(
            message.chat.id,
            "🔧 Вибачте, я не зрозумів вашу команду. "
            "Скористайтесь кнопками нижче:",
            reply_markup=get_main_keyboard()
        )

# ==================== ЗАПУСК БОТА ====================

if __name__ == "__main__":
    print("=" * 50)
    print("🤖 ТОП СЕРВІС БОТ - RENDER VERSION")
    print("=" * 50)
    print("⏳ Очікування повідомлень...")
    print("=" * 50)
    
    try:
        bot.infinity_polling()
    except KeyboardInterrupt:
        print("\n" + "=" * 50)
        print("🛑 Бот зупинено")
        print("=" * 50)
    except Exception as e:
        print(f"❌ Помилка: {e}")
