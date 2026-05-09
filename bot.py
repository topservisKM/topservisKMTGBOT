import os
import sqlite3
import logging
import threading
from datetime import datetime
from dotenv import load_dotenv
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from flask import Flask

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
ADMIN_ID  = int(os.getenv("ADMIN_ID", "0"))
DB_PATH   = "topservice.db"

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

app = Flask(__name__)

@app.route("/")
def index():
    return "OK", 200

@app.route("/health")
def health():
    return "OK", 200


# ── Состояния ─────────────────────────────────────────────────────────
user_state: dict[int, str] = {}
user_temp:  dict[int, dict] = {}
active_chat: dict = {}


# ── DB ────────────────────────────────────────────────────────────────
def db_init():
    with sqlite3.connect(DB_PATH) as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id  INTEGER PRIMARY KEY,
                phone    TEXT NOT NULL,
                name     TEXT NOT NULL,
                username TEXT,
                reg_date TEXT
            )
        """)
        c.commit()

def get_user(uid: int):
    with sqlite3.connect(DB_PATH) as c:
        c.row_factory = sqlite3.Row
        r = c.execute("SELECT * FROM users WHERE user_id=?", (uid,)).fetchone()
        return dict(r) if r else None

def save_user(uid, phone, name, username):
    with sqlite3.connect(DB_PATH) as c:
        c.execute(
            "INSERT OR REPLACE INTO users VALUES (?,?,?,?,?)",
            (uid, phone, name, username, datetime.now().strftime("%d.%m.%Y %H:%M"))
        )
        c.commit()


# ── Keyboards ─────────────────────────────────────────────────────────
def kb_phone():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.add(KeyboardButton("📲 Поділитись номером", request_contact=True))
    return kb

def kb_client_idle():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("💬 Написати майстру"))
    kb.add(KeyboardButton("📞 Подзвонити"), KeyboardButton("📍 Адреса"))
    return kb

def kb_client_in_chat():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🔴 Завершити чат"))
    return kb

def kb_admin_in_chat():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton("🔴 Завершити чат"))
    return kb

def kb_admin_open_chat(uid: int):
    kb = InlineKeyboardMarkup()
    kb.add(InlineKeyboardButton("💬 Відкрити чат з клієнтом", callback_data=f"open:{uid}"))
    return kb

def kb_welcome_new():
    """Inline-кнопки для нового незареєстрованого користувача"""
    kb = InlineKeyboardMarkup(row_width=1)
    kb.add(
        InlineKeyboardButton("🚀 Зареєструватись і написати майстру", callback_data="start_reg"),
        InlineKeyboardButton("📞 Подзвонити: 066 005 2325",            url="tel:+380660052325"),
        InlineKeyboardButton("📍 Адреса на Google Maps",               url="https://maps.google.com/maps?q=вул.+Медична+1/11+Камʼянське"),
    )
    return kb


# ── Helpers ───────────────────────────────────────────────────────────
def user_card(u: dict) -> str:
    uname = f"@{u['username']}" if u.get("username") else "—"
    return (
        f"👤 <b>{u['name']}</b>\n"
        f"📞 <b>{u['phone']}</b>\n"
        f"🔗 {uname} · <code>{u['user_id']}</code>\n"
        f"📅 {u.get('reg_date','—')}"
    )

def end_chat(initiator: str):
    uid = active_chat.pop("user_id", None)
    if not uid:
        return
    user_state[uid] = "idle"
    if initiator == "admin":
        client_msg = "🔴 <b>Майстер завершив чат.</b>\n\nЯкщо є ще питання — пишіть знову!"
        admin_msg  = "🔴 Чат завершено."
    else:
        user = get_user(uid)
        name = user["name"] if user else str(uid)
        client_msg = "🔴 <b>Чат завершено.</b>\n\nДякуємо! Якщо є ще питання — пишіть знову."
        admin_msg  = f"🔴 Клієнт <b>{name}</b> завершив чат."
    bot.send_message(uid,      client_msg, reply_markup=kb_client_idle())
    bot.send_message(ADMIN_ID, admin_msg,  reply_markup=ReplyKeyboardRemove())


# ════════════════════════════════════════════════════════════════════
#  /start
# ════════════════════════════════════════════════════════════════════
@bot.message_handler(commands=["start"])
def cmd_start(msg):
    uid = msg.from_user.id

    # Адмін
    if uid == ADMIN_ID:
        bot.send_message(uid,
            "⚙️ <b>ТОП СЕРВІС · Панель майстра</b>\n\n"
            "Очікую повідомлень від клієнтів.\n\n"
            "Коли клієнт напише — отримаєш його дані та кнопку <b>Відкрити чат</b>.")
        return

    user = get_user(uid)

    # Вже зареєстрований
    if user:
        user_state[uid] = "idle"
        bot.send_message(uid,
            f"⚙️ <b>ТОП СЕРВІС</b> · Камʼянське\n\n"
            f"З поверненням, <b>{user['name']}</b>! 👋\n\n"
            f"📱 Ремонт смартфонів та ноутбуків\n"
            f"⚡ від 30 хвилин · 🛡 Гарантія 90 днів\n\n"
            f"Оберіть що вас цікавить 👇",
            reply_markup=kb_client_idle())
        return

    # Новий користувач — привітання + inline-кнопки
    bot.send_message(uid,
        "👋 Вітаємо у <b>ТОП СЕРВІС</b>!\n\n"
        "🔧 Ремонт смартфонів та ноутбуків у Камʼянському\n"
        "📍 вул. Медична 1/11\n"
        "🕐 Пн–Сб: 09:00–18:00\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📱 <b>iPhone · Samsung · Xiaomi · Huawei</b> та інші\n"
        "💻 Ноутбуки будь-яких брендів\n\n"
        "⚡ Ремонт від <b>30 хвилин</b>\n"
        "🔩 Оригінальні запчастини\n"
        "🛡 Гарантія <b>90 днів</b>\n"
        "🔍 Діагностика <b>БЕЗКОШТОВНО</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Щоб написати майстру — потрібна швидка реєстрація (номер телефону) 👇",
        reply_markup=kb_welcome_new())


# Натиснув «Зареєструватись» в привітанні
@bot.callback_query_handler(func=lambda c: c.data == "start_reg")
def cb_start_reg(call):
    uid = call.from_user.id
    bot.answer_callback_query(call.id)
    # Прибираємо inline-кнопки з попереднього повідомлення
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    user_state[uid] = "wait_phone"
    bot.send_message(uid,
        "📲 Натисніть кнопку нижче щоб поділитись номером телефону.\n\n"
        "<i>Номер потрібен щоб майстер міг зв'язатись з вами.</i>",
        reply_markup=kb_phone())


# ════════════════════════════════════════════════════════════════════
#  РЕЄСТРАЦІЯ
# ════════════════════════════════════════════════════════════════════
@bot.message_handler(content_types=["contact"])
def handle_contact(msg):
    uid = msg.from_user.id
    if user_state.get(uid) != "wait_phone":
        return
    phone = msg.contact.phone_number
    if not phone.startswith("+"):
        phone = "+" + phone
    user_temp[uid] = {"phone": phone}
    user_state[uid] = "wait_name"
    bot.send_message(uid,
        f"✅ Номер отримано: <b>{phone}</b>\n\nЯк вас звати? Введіть <b>ім'я</b>:",
        reply_markup=ReplyKeyboardRemove())

@bot.message_handler(func=lambda m: user_state.get(m.from_user.id) == "wait_name")
def handle_name(msg):
    uid  = msg.from_user.id
    name = msg.text.strip()
    if len(name) < 2 or len(name) > 50:
        bot.send_message(uid, "⚠️ Введіть коректне ім'я (2–50 символів).")
        return
    phone = user_temp.pop(uid, {}).get("phone", "")
    save_user(uid, phone, name, msg.from_user.username)
    user_state[uid] = "idle"
    bot.send_message(uid,
        f"🎉 <b>Реєстрація завершена!</b>\n\n"
        f"👤 {name} · 📞 {phone}\n\n"
        f"Тепер ви можете написати майстру — він відповість вам тут 👇",
        reply_markup=kb_client_idle())


# ════════════════════════════════════════════════════════════════════
#  КНОПКИ КЛІЄНТА
# ════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "📍 Адреса" and m.from_user.id != ADMIN_ID)
def btn_address(msg):
    bot.send_message(msg.from_user.id,
        "📍 <b>ТОП СЕРВІС</b>\n"
        "вул. Медична 1/11, Камʼянське\n\n"
        "🕐 Пн–Сб: 09:00–18:00\n"
        "❌ Неділя: вихідний\n\n"
        "🗺 https://maps.google.com/maps?q=вул.+Медична+1/11+Камʼянське")

@bot.message_handler(func=lambda m: m.text == "📞 Подзвонити" and m.from_user.id != ADMIN_ID)
def btn_call(msg):
    bot.send_message(msg.from_user.id,
        "📞 <b>066 005 2325</b>\n\n"
        "🕐 Пн–Сб: 09:00–18:00\n"
        "Або напишіть майстру прямо тут 👇",
        reply_markup=kb_client_idle())

@bot.message_handler(func=lambda m: m.text == "💬 Написати майстру" and m.from_user.id != ADMIN_ID)
def btn_write(msg):
    uid  = msg.from_user.id
    user = get_user(uid)
    if not user:
        user_state[uid] = "wait_phone"
        bot.send_message(uid, "⚠️ Спочатку зареєструйтесь:", reply_markup=kb_phone())
        return
    try:
        bot.send_message(ADMIN_ID,
            f"🔔 <b>Новий запит на чат</b>\n━━━━━━━━━━━━━━━━━━━━\n{user_card(user)}",
            reply_markup=kb_admin_open_chat(uid))
    except Exception as e:
        log.error(f"Помилка сповіщення адміна: {e}")
    user_state[uid] = "wait_admin"
    bot.send_message(uid,
        "⏳ <b>Запит надіслано майстру.</b>\n\n"
        "Зачекайте, він скоро підключиться...",
        reply_markup=ReplyKeyboardRemove())


# ════════════════════════════════════════════════════════════════════
#  АДМІН: відкрити чат
# ════════════════════════════════════════════════════════════════════
@bot.callback_query_handler(func=lambda c: c.data.startswith("open:"))
def cb_open_chat(call):
    if call.from_user.id != ADMIN_ID:
        bot.answer_callback_query(call.id, "⛔ Немає прав.")
        return
    uid  = int(call.data.split(":")[1])
    user = get_user(uid)
    if active_chat and active_chat.get("user_id") != uid:
        other = get_user(active_chat["user_id"])
        name  = other["name"] if other else str(active_chat["user_id"])
        bot.answer_callback_query(call.id, f"⚠️ Вже є чат з {name}. Завершіть його.", show_alert=True)
        return
    active_chat["user_id"] = uid
    user_state[uid] = "in_chat"
    bot.answer_callback_query(call.id)
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    bot.send_message(ADMIN_ID,
        f"💬 <b>Чат відкрито</b>\n"
        f"👤 {user['name']} · 📞 {user['phone']}\n\n"
        f"Пишіть — повідомлення будуть пересилатись клієнту.",
        reply_markup=kb_admin_in_chat())
    bot.send_message(uid,
        "✅ <b>Майстер підключився!</b>\n\n"
        "Пишіть ваше питання або опишіть проблему 👇",
        reply_markup=kb_client_in_chat())


# ════════════════════════════════════════════════════════════════════
#  ЗАВЕРШЕННЯ ЧАТУ
# ════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.text == "🔴 Завершити чат" and m.from_user.id == ADMIN_ID)
def admin_end_chat(msg):
    if not active_chat:
        bot.send_message(ADMIN_ID, "Активного чату немає.", reply_markup=ReplyKeyboardRemove())
        return
    end_chat("admin")

@bot.message_handler(func=lambda m: m.text == "🔴 Завершити чат" and m.from_user.id != ADMIN_ID)
def client_end_chat(msg):
    uid = msg.from_user.id
    if active_chat.get("user_id") != uid:
        user_state[uid] = "idle"
        bot.send_message(uid, "Чат вже завершено.", reply_markup=kb_client_idle())
        return
    end_chat("client")


# ════════════════════════════════════════════════════════════════════
#  RELAY
# ════════════════════════════════════════════════════════════════════
@bot.message_handler(
    func=lambda m: m.from_user.id != ADMIN_ID and user_state.get(m.from_user.id) == "in_chat",
    content_types=["text","photo","video","document","voice","sticker"])
def client_msg(msg):
    uid  = msg.from_user.id
    user = get_user(uid)
    name = user["name"] if user else str(uid)
    if active_chat.get("user_id") != uid:
        bot.send_message(uid, "⚠️ Чат ще не відкрито майстром. Зачекайте...")
        return
    try:
        bot.send_message(ADMIN_ID, f"👤 <b>{name}:</b>")
        bot.forward_message(ADMIN_ID, uid, msg.message_id)
    except Exception as e:
        log.error(f"Relay client→admin: {e}")

@bot.message_handler(
    func=lambda m: m.from_user.id == ADMIN_ID and bool(active_chat),
    content_types=["text","photo","video","document","voice","sticker"])
def admin_msg(msg):
    uid = active_chat.get("user_id")
    if not uid:
        return
    try:
        bot.send_message(uid, "🔧 <b>Майстер:</b>")
        bot.forward_message(uid, ADMIN_ID, msg.message_id)
    except Exception as e:
        log.error(f"Relay admin→client: {e}")
        bot.send_message(ADMIN_ID, f"❌ Помилка: {e}")


# ════════════════════════════════════════════════════════════════════
#  ЗАХИСТ
# ════════════════════════════════════════════════════════════════════
@bot.message_handler(func=lambda m: m.from_user.id != ADMIN_ID
    and user_state.get(m.from_user.id) not in ("wait_name","idle","in_chat","wait_admin"))
def unregistered(msg):
    uid = msg.from_user.id
    user_state[uid] = "wait_phone"
    bot.send_message(uid, "⚠️ Спочатку зареєструйтесь:", reply_markup=kb_phone())


# ── Polling thread ────────────────────────────────────────────────────
def run_polling():
    db_init()
    bot.remove_webhook()
    log.info("⚙️ Webhook видалено. Bot polling запущено...")
    bot.infinity_polling(timeout=30, long_polling_timeout=30)

polling_thread = threading.Thread(target=run_polling, daemon=True)
polling_thread.start()
