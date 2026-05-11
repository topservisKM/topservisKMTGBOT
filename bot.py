import os
import json
import threading
from datetime import datetime
import pytz

from flask import Flask, request
import telebot
from telebot import types


BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = os.getenv("ADMIN_ID")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not BOT_TOKEN:
    raise Exception("BOT_TOKEN missing")
if not ADMIN_ID:
    raise Exception("ADMIN_ID missing")
if not WEBHOOK_URL:
    raise Exception("WEBHOOK_URL missing")

ADMIN_ID = int(ADMIN_ID)

KYIV_TZ = pytz.timezone("Europe/Kiev")
INACTIVITY_TIMEOUT = 10 * 60

bot = telebot.TeleBot(BOT_TOKEN, threaded=False)
app = Flask(__name__)

DATA_FILE = "chat_sessions.json"

waiting_for_phone = {}
waiting_for_name = {}

inactivity_timers = {}
timers_lock = threading.Lock()



def load_chats():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {int(k): v for k, v in data.items()}
        except Exception:
            return {}
    return {}


def save_chats(data):
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving chats: {e}")


def get_active_chats():
    return load_chats()


def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn1 = types.KeyboardButton("✍️ Написати майстру")
    btn2 = types.KeyboardButton("📅 Графік роботи")
    markup.add(btn1, btn2)
    return markup


def get_phone_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    btn = types.KeyboardButton("📱 Поділитися номером", request_contact=True)
    btn_cancel = types.KeyboardButton("❌ Скасувати")
    markup.add(btn)
    markup.add(btn_cancel)
    return markup


def get_chat_keyboard():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    btn = types.KeyboardButton("🛑 Завершити чат")
    markup.add(btn)
    return markup


def is_working_hours():
    now = datetime.now(KYIV_TZ)
    day = now.weekday()
    hour = now.hour
    if day == 6:
        return False
    if day == 5:
        return 11 <= hour < 14
    return 10 <= hour < 18


def find_active_user_for_admin():
    active_chats = get_active_chats()
    for chat_id, data in active_chats.items():
        if data.get("status") == "chat_active" and data.get("admin_id") == ADMIN_ID:
            return chat_id
    return None



def cancel_inactivity_timer(user_id):
    with timers_lock:
        timer = inactivity_timers.pop(user_id, None)
        if timer:
            timer.cancel()


def reset_inactivity_timer(user_id):
    cancel_inactivity_timer(user_id)
    timer = threading.Timer(INACTIVITY_TIMEOUT, auto_close_chat, args=[user_id])
    timer.daemon = True
    with timers_lock:
        inactivity_timers[user_id] = timer
    timer.start()


def auto_close_chat(user_id):
    active_chats = get_active_chats()
    if user_id not in active_chats:
        return
    session = active_chats[user_id]
    if session.get("status") != "chat_active":
        return
    admin_id = session.get("admin_id")
    active_chats[user_id]["status"] = "closed"
    save_chats(active_chats)
    with timers_lock:
        inactivity_timers.pop(user_id, None)
    try:
        bot.send_message(user_id, "⏱️ Чат автоматично закрито через 10 хвилин бездіяльності.", reply_markup=get_main_keyboard())
    except Exception as e:
        print(f"Error notifying user on auto-close: {e}")
    if admin_id:
        try:
            bot.send_message(admin_id, "⏱️ Чат закрито автоматично через 10 хвилин бездіяльності.", reply_markup=get_main_keyboard())
        except Exception as e:
            print(f"Error notifying admin on auto-close: {e}")



def forward_media(message, target_id, prefix):
    """Переслати будь-який тип медіа або текст на target_id."""
    caption = message.caption or ""
    cap = f"{prefix}{caption}" if caption else None

    try:
        if message.content_type == "text":
            bot.send_message(target_id, f"{prefix}{message.text}")

        elif message.content_type == "photo":
            file_id = message.photo[-1].file_id
            bot.send_photo(target_id, file_id, caption=cap)

        elif message.content_type == "video":
            bot.send_video(target_id, message.video.file_id, caption=cap)

        elif message.content_type == "voice":
            bot.send_voice(target_id, message.voice.file_id, caption=cap)

        elif message.content_type == "video_note":
            bot.send_video_note(target_id, message.video_note.file_id)

        elif message.content_type == "audio":
            bot.send_audio(target_id, message.audio.file_id, caption=cap)

        elif message.content_type == "document":
            bot.send_document(target_id, message.document.file_id, caption=cap)

        elif message.content_type == "sticker":
            bot.send_sticker(target_id, message.sticker.file_id)

        elif message.content_type == "animation":
            bot.send_animation(target_id, message.animation.file_id, caption=cap)

        elif message.content_type == "location":
            bot.send_location(target_id, message.location.latitude, message.location.longitude)

        elif message.content_type == "contact":
            c = message.contact
            bot.send_contact(target_id, c.phone_number, c.first_name, last_name=c.last_name)

        else:
            bot.send_message(target_id, f"{prefix}[Непідтримуваний тип: {message.content_type}]")

    except Exception as e:
        print(f"forward_media error: {e}")
        bot.send_message(target_id, f"❌ Помилка передачі медіа: {e}")



@bot.message_handler(commands=["start"])
def start(message):
    user_name = message.from_user.first_name or "Користувач"
    bot.send_message(
        message.chat.id,
        f"🔧 Привіт, {user_name}!\n\n"
        f"Ласкаво просимо до <b>ТОП СЕРВІС</b> 🏢\n\n"
        f"Ми готові допомогти вам з будь-якими проблемами!",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )


@bot.message_handler(commands=["help"])
def help_command(message):
    bot.send_message(
        message.chat.id,
        "ℹ️ <b>Як користуватись ботом:</b>\n\n"
        "📱 <b>Написати майстру</b> — скласти заявку\n"
        "📅 <b>Графік роботи</b> — дізнатись час роботи",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )



@bot.message_handler(func=lambda m: m.text == "📅 Графік роботи")
def show_schedule(message):
    bot.send_message(
        message.chat.id,
        "📅 <b>Графік роботи ТОП СЕРВІС</b>\n\n"
        "Понеділок — П'ятниця: 10:00 — 18:00\n"
        "Субота: 11:00 — 14:00\n"
        "Неділя: Вихідний",
        parse_mode="HTML",
        reply_markup=get_main_keyboard()
    )


@bot.message_handler(func=lambda m: m.text == "✍️ Написати майстру")
def start_request(message):
    if message.chat.id == ADMIN_ID:
        bot.send_message(message.chat.id, "👨‍💼 Ви адміністратор.", reply_markup=get_main_keyboard())
        return

    if not is_working_hours():
        bot.send_message(
            message.chat.id,
            "⏰ Зараз неробочий час, але ви можете залишити заявку — "
            "майстер зв'яжеться з вами у робочий час.\n\n"
            "📅 Графік роботи:\n"
            "Пн-Пт: 10:00 — 18:00\n"
            "Сб: 11:00 — 14:00\n"
            "Нд: Вихідний",
        )

    waiting_for_phone[message.chat.id] = True
    bot.send_message(message.chat.id, "📱 Поділіться номером телефону:", reply_markup=get_phone_keyboard())


@bot.message_handler(func=lambda m: m.text == "❌ Скасувати")
def cancel_request(message):
    waiting_for_phone.pop(message.chat.id, None)
    waiting_for_name.pop(message.chat.id, None)
    bot.send_message(message.chat.id, "❌ Заявку скасовано", reply_markup=get_main_keyboard())



@bot.message_handler(content_types=["contact"])
def handle_contact(message):
    if message.chat.id not in waiting_for_phone:
        return
    phone = message.contact.phone_number
    active_chats = get_active_chats()
    active_chats[message.chat.id] = {"phone": phone, "user_id": message.chat.id}
    save_chats(active_chats)
    waiting_for_phone.pop(message.chat.id, None)
    waiting_for_name[message.chat.id] = True
    bot.send_message(
        message.chat.id,
        f"✅ Номер отримано: {phone}\n\n👤 Напишіть ваше ім'я:",
        reply_markup=types.ReplyKeyboardRemove()
    )


@bot.message_handler(func=lambda m: m.chat.id in waiting_for_name)
def handle_name(message):
    if message.text and message.text.startswith("/"):
        return
    name = message.text or "Без імені"
    active_chats = get_active_chats()
    if message.chat.id not in active_chats:
        waiting_for_name.pop(message.chat.id, None)
        bot.send_message(message.chat.id, "❌ Сесія застаріла. Спробуйте ще раз.", reply_markup=get_main_keyboard())
        return

    active_chats[message.chat.id]["name"] = name
    active_chats[message.chat.id]["status"] = "waiting_admin"
    active_chats[message.chat.id]["timestamp"] = datetime.now(KYIV_TZ).isoformat()
    save_chats(active_chats)

    phone = active_chats[message.chat.id]["phone"]
    user_id = message.chat.id
    waiting_for_name.pop(message.chat.id, None)

    bot.send_message(message.chat.id, f"✅ Дякуємо, {name}!\n\nЗаявка надіслана майстру.", reply_markup=get_main_keyboard())

    off_hours_note = ""
    if not is_working_hours():
        now = datetime.now(KYIV_TZ)
        off_hours_note = f"\n⏰ <b>Поза робочим часом</b> ({now.strftime('%H:%M, %A')})"

    admin_message = (
        f"📬 <b>НОВА ЗАЯВКА</b>{off_hours_note}\n\n"
        f"👤 <b>Ім'я:</b> {name}\n"
        f"📱 <b>Телефон:</b> {phone}\n"
        f"🆔 <b>ID:</b> {user_id}"
    )

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💬 Відкрити чат", callback_data=f"open_chat_{user_id}"))
    bot.send_message(ADMIN_ID, admin_message, parse_mode="HTML", reply_markup=markup)



@bot.callback_query_handler(func=lambda call: call.data.startswith("open_chat_"))
def open_chat(call):
    user_id = int(call.data.split("_")[-1])
    active_chats = get_active_chats()

    if user_id not in active_chats:
        bot.answer_callback_query(call.id, "❌ Заявку не знайдено")
        return
    if active_chats[user_id].get("status") == "chat_active":
        bot.answer_callback_query(call.id, "Чат вже відкрито")
        return
    if active_chats[user_id].get("status") == "closed":
        bot.answer_callback_query(call.id, "Чат вже завершено")
        return

    active_chats[user_id]["status"] = "chat_active"
    active_chats[user_id]["admin_id"] = ADMIN_ID
    save_chats(active_chats)
    reset_inactivity_timer(user_id)

    bot.send_message(
        user_id,
        "✅ Майстер підключився до чату\n\n⏱️ Чат закриється автоматично через 10 хвилин бездіяльності.",
        reply_markup=get_chat_keyboard()
    )
    bot.send_message(
        ADMIN_ID,
        "✅ Чат відкрито. Пишіть — повідомлення будуть передані користувачу.\n\n"
        "⏱️ Чат закриється автоматично через 10 хвилин бездіяльності.",
        reply_markup=get_chat_keyboard()
    )
    bot.answer_callback_query(call.id)



@bot.message_handler(func=lambda m: m.text == "🛑 Завершити чат")
def close_chat_button(message):
    close_chat(message)


def close_chat(message):
    user_id = message.chat.id
    active_chats = get_active_chats()

    if user_id == ADMIN_ID:
        target_user = find_active_user_for_admin()
        if not target_user:
            bot.send_message(ADMIN_ID, "⚠️ Немає активних чатів.", reply_markup=get_main_keyboard())
            return
        cancel_inactivity_timer(target_user)
        active_chats[target_user]["status"] = "closed"
        save_chats(active_chats)
        bot.send_message(target_user, "🛑 Майстер завершив чат.", reply_markup=get_main_keyboard())
        bot.send_message(ADMIN_ID, "🛑 Чат завершено.", reply_markup=get_main_keyboard())
    else:
        if user_id not in active_chats:
            bot.send_message(user_id, "⚠️ Активний чат не знайдено.", reply_markup=get_main_keyboard())
            return
        cancel_inactivity_timer(user_id)
        admin_id = active_chats[user_id].get("admin_id")
        active_chats[user_id]["status"] = "closed"
        save_chats(active_chats)
        if admin_id:
            bot.send_message(admin_id, "🛑 Користувач завершив чат.", reply_markup=get_main_keyboard())
        bot.send_message(user_id, "🛑 Чат завершено.", reply_markup=get_main_keyboard())


def _is_in_active_chat(message):
    if message.text == "🛑 Завершити чат":
        return False
    active_chats = get_active_chats()
    chat_id = message.chat.id
    if chat_id in active_chats and active_chats[chat_id].get("status") == "chat_active":
        return True
    if chat_id == ADMIN_ID:
        return find_active_user_for_admin() is not None
    return False


CHAT_CONTENT_TYPES = [
    "text", "photo", "video", "voice", "video_note",
    "audio", "document", "sticker", "animation", "location", "contact"
]


@bot.message_handler(
    content_types=CHAT_CONTENT_TYPES,
    func=lambda m: _is_in_active_chat(m)
)
def handle_chat(message):
    user_id = message.chat.id
    active_chats = get_active_chats()

    if user_id == ADMIN_ID:
        target_user = find_active_user_for_admin()
        if target_user:
            reset_inactivity_timer(target_user)
            forward_media(message, target_user, "🛠️ Майстер: ")
        else:
            bot.send_message(ADMIN_ID, "⚠️ Немає активних чатів.")
    else:
        admin_id = active_chats[user_id].get("admin_id")
        if admin_id:
            reset_inactivity_timer(user_id)
            name = active_chats[user_id].get("name", "Користувач")
            forward_media(message, admin_id, f"👤 {name}: ")



@bot.message_handler(func=lambda m: True)
def other_messages(message):
    chat_id = message.chat.id
    if chat_id in waiting_for_phone:
        bot.send_message(chat_id, "📱 Натисніть кнопку нижче щоб поділитися номером", reply_markup=get_phone_keyboard())
    elif chat_id in waiting_for_name:
        bot.send_message(chat_id, "👤 Будь ласка, напишіть ваше ім'я")
    else:
        bot.send_message(chat_id, "🔧 Використовуйте кнопки нижче", reply_markup=get_main_keyboard())



@app.route("/", methods=["GET"])
def index():
    return "Bot is running", 200


@app.route(f"/{BOT_TOKEN}", methods=["POST"])
def webhook():
    json_str = request.get_data().decode("UTF-8")
    update = telebot.types.Update.de_json(json_str)
    bot.process_new_updates([update])
    return "OK", 200


def setup_webhook():
    try:
        bot.remove_webhook()
        bot.set_webhook(url=f"{WEBHOOK_URL}/{BOT_TOKEN}")
        print(f"✅ Webhook set: {WEBHOOK_URL}/{BOT_TOKEN}")
    except Exception as e:
        print(f"❌ Webhook setup failed: {e}")


setup_webhook()
