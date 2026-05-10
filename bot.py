import os
import json
from datetime import datetime

from flask import Flask, request
import telebot
from telebot import types

# ==================== CONFIG ====================

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")

if not BOT_TOKEN:
    raise Exception("BOT_TOKEN missing")

if not ADMIN_ID:
    raise Exception("ADMIN_ID missing")

ADMIN_ID = int(ADMIN_ID)

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# ==================== DATA ====================

DATA_FILE = "chat_sessions.json"

active_chats = {}
waiting_for_phone = {}
waiting_for_name = {}

# ==================== HELPERS ====================

def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)

    btn1 = types.KeyboardButton("✍️ Написати майстру")
    btn2 = types.KeyboardButton("📅 Графік роботи")

    markup.add(btn1, btn2)

    return markup


def get_phone_keyboard():
    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True,
        one_time_keyboard=True
    )

    btn = types.KeyboardButton(
        "📱 Поділитися номером",
        request_contact=True
    )

    btn_cancel = types.KeyboardButton("❌ Скасувати")

    markup.add(btn)
    markup.add(btn_cancel)

    return markup


def get_chat_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)

    btn = types.KeyboardButton("🛑 Завершити чат")

    markup.add(btn)

    return markup


def load_chats():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    return {}


def save_chats(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_working_hours():
    now = datetime.now()

    day = now.weekday()
    hour = now.hour

    # Sunday
    if day == 6:
        return False

    # Saturday
    if day == 5:
        return 11 <= hour < 14

    # Monday-Friday
    return 10 <= hour < 18


# ==================== COMMANDS ====================

@bot.message_handler(commands=["start"])
def start(message):
    user_name = message.from_user.first_name or "Користувач"

    bot.send_message(
        message.chat.id,
        f"🔧 Привіт, {user_name}!\n\n"
        f"Добро пожалуйте до <b>ТОП СЕРВІС</b> 🏢\n\n"
        f"Ми готові допомогти вам з будь-якими проблемами!",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )


@bot.message_handler(commands=["help"])
def help_command(message):
    bot.send_message(
        message.chat.id,
        "ℹ️ <b>Як користуватись ботом:</b>\n\n"
        "📱 <b>Написати майстру</b> - скласти заявку\n"
        "📅 <b>Графік роботи</b> - дізнатись час роботи",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )


# ==================== MAIN BUTTONS ====================

@bot.message_handler(func=lambda message: message.text == "📅 Графік роботи")
def show_schedule(message):
    bot.send_message(
        message.chat.id,
        "📅 <b>Графік роботи ТОП СЕРВІС</b>\n\n"
        "Понеділок - П'ятниця: 10:00 - 18:00\n"
        "Субота: 11:00 - 14:00\n"
        "Неділя: Вихідний",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )


@bot.message_handler(func=lambda message: message.text == "✍️ Написати майстру")
def start_request(message):

    if not is_working_hours():
        bot.send_message(
            message.chat.id,
            "⏰ Сервіс зараз закритий.",
            reply_markup=get_main_keyboard()
        )
        return

    waiting_for_phone[message.chat.id] = True

    bot.send_message(
        message.chat.id,
        "📱 Поділіться номером телефону:",
        reply_markup=get_phone_keyboard()
    )


@bot.message_handler(func=lambda message: message.text == "❌ Скасувати")
def cancel_request(message):

    if message.chat.id in waiting_for_phone:
        del waiting_for_phone[message.chat.id]

    if message.chat.id in waiting_for_name:
        del waiting_for_name[message.chat.id]

    bot.send_message(
        message.chat.id,
        "❌ Заявку скасовано",
        reply_markup=get_main_keyboard()
    )


# ==================== CONTACT ====================

@bot.message_handler(content_types=["contact"])
def handle_contact(message):

    if message.chat.id not in waiting_for_phone:
        return

    phone = message.contact.phone_number

    if message.chat.id not in active_chats:
        active_chats[message.chat.id] = {}

    active_chats[message.chat.id]["phone"] = phone
    active_chats[message.chat.id]["user_id"] = message.chat.id

    del waiting_for_phone[message.chat.id]

    waiting_for_name[message.chat.id] = True

    bot.send_message(
        message.chat.id,
        f"✅ Номер отримано: {phone}\n\n"
        f"👤 Напишіть ваше ім'я:",
        reply_markup=types.ReplyKeyboardRemove()
    )


# ==================== NAME ====================

@bot.message_handler(func=lambda message: message.chat.id in waiting_for_name)
def handle_name(message):

    if message.text.startswith("/"):
        return

    name = message.text

    active_chats[message.chat.id]["name"] = name
    active_chats[message.chat.id]["status"] = "waiting_admin"
    active_chats[message.chat.id]["timestamp"] = datetime.now().isoformat()

    phone = active_chats[message.chat.id]["phone"]
    user_id = message.chat.id

    del waiting_for_name[message.chat.id]

    bot.send_message(
        message.chat.id,
        f"✅ Дякуємо, {name}!\n\n"
        f"Заявка надіслана майстру.",
        reply_markup=get_main_keyboard()
    )

    admin_message = (
        f"📬 <b>НОВА ЗАЯВКА</b>\n\n"
        f"👤 <b>Ім'я:</b> {name}\n"
        f"📱 <b>Телефон:</b> {phone}\n"
        f"🆔 <b>ID:</b> {user_id}"
    )

    markup = types.InlineKeyboardMarkup()

    markup.add(
        types.InlineKeyboardButton(
            "💬 Відкрити чат",
            callback_data=f"open_chat_{user_id}"
        )
    )

    bot.send_message(
        ADMIN_ID,
        admin_message,
        parse_mode="HTML",
        reply_markup=markup
    )

    save_chats(active_chats)


# ==================== CALLBACK ====================

@bot.callback_query_handler(func=lambda call: call.data.startswith("open_chat_"))
def open_chat(call):

    user_id = int(call.data.split("_")[-1])

    if user_id not in active_chats:
        return

    active_chats[user_id]["status"] = "chat_active"
    active_chats[user_id]["admin_id"] = ADMIN_ID

    save_chats(active_chats)

    bot.send_message(
        user_id,
        "✅ Майстер підключився до чату",
        reply_markup=get_chat_keyboard()
    )

    bot.send_message(
        ADMIN_ID,
        "✅ Чат відкрито",
        reply_markup=get_chat_keyboard()
    )

    bot.answer_callback_query(call.id)


# ==================== CHAT ====================

@bot.message_handler(
    func=lambda message:
    message.chat.id in active_chats
    and active_chats[message.chat.id].get("status") == "chat_active"
)
def handle_chat(message):

    user_id = message.chat.id

    if message.text == "🛑 Завершити чат":
        close_chat(message)
        return

    try:

        if user_id == ADMIN_ID:

            target_user = None

            for chat_id, data in active_chats.items():

                if (
                    data.get("status") == "chat_active"
                    and data.get("admin_id") == ADMIN_ID
                ):
                    target_user = chat_id
                    break

            if target_user:
                bot.send_message(
                    target_user,
                    f"🛠️ Майстер: {message.text}"
                )

        else:

            admin_id = active_chats[user_id].get("admin_id")

            if admin_id:
                bot.send_message(
                    admin_id,
                    f"👤 Користувач: {message.text}"
                )

    except Exception as e:
        bot.send_message(user_id, f"❌ Помилка: {e}")


def close_chat(message):

    user_id = message.chat.id

    if user_id == ADMIN_ID:

        target_user = None

        for chat_id, data in active_chats.items():

            if (
                data.get("status") == "chat_active"
                and data.get("admin_id") == ADMIN_ID
            ):
                target_user = chat_id
                break

        if not target_user:
            return

        active_chats[target_user]["status"] = "closed"

        bot.send_message(
            target_user,
            "🛑 Чат завершено",
            reply_markup=get_main_keyboard()
        )

        bot.send_message(
            ADMIN_ID,
            "🛑 Чат завершено",
            reply_markup=get_main_keyboard()
        )

    else:

        active_chats[user_id]["status"] = "closed"

        admin_id = active_chats[user_id].get("admin_id")

        if admin_id:
            bot.send_message(
                admin_id,
                "🛑 Користувач завершив чат",
                reply_markup=get_main_keyboard()
            )

        bot.send_message(
            user_id,
            "🛑 Чат завершено",
            reply_markup=get_main_keyboard()
        )

    save_chats(active_chats)


# ==================== OTHER ====================

@bot.message_handler(func=lambda message: True)
def other_messages(message):

    if message.chat.id in waiting_for_phone:

        bot.send_message(
            message.chat.id,
            "📱 Натисніть кнопку нижче",
            reply_markup=get_phone_keyboard()
        )

    elif message.chat.id in waiting_for_name:

        bot.send_message(
            message.chat.id,
            "👤 Напишіть ваше ім'я"
        )

    else:

        bot.send_message(
            message.chat.id,
            "🔧 Використовуйте кнопки нижче",
            reply_markup=get_main_keyboard()
        )


# ==================== FLASK ====================

@app.route("/", methods=["GET"])
def index():
    return "Bot is running", 200


@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():

    json_str = request.get_data().decode("UTF-8")

    update = telebot.types.Update.de_json(json_str)

    bot.process_new_updates([update])

    return "OK", 200


# ==================== START ====================

if __name__ == "__main__":

    print("🤖 BOT STARTING...")

    bot.remove_webhook()

    bot.set_webhook(url=WEBHOOK_URL)

    port = int(os.environ.get("PORT", 10000))

    app.run(host="0.0.0.0", port=port)
