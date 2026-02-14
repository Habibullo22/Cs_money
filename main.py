# main.py — CS2 Skin Shop bot (TeleBot)
# ✅ Admin: skin qo‘shish (rasmni TELEGRAMdan yuborasiz), o‘chirish, narx o‘zgartirish, aktiv/passiv
# ✅ User: katalog (bo‘lim -> qurol -> ro‘yxat), qidiruv, sotib olish, balans, depozit
# ✅ Depozit: user rasm(chek/ss) yuboradi -> admin ✅/❌
# ✅ Order: user sotib oladi -> admin ✅/❌/📤 Delivered
# ✅ Referral: depozitdan % bonus

import sqlite3
import time
from typing import Dict, List, Optional

from telebot import TeleBot, types

# =======================
# CONFIG
# =======================
TOKEN = "8061624031:AAG5LQ1tHO4V8hkh8egQDdZfgW2zy3X5jAo"   # ⚠️ Tokenni kodga ochiq tashlamang (env/keep_alive bilan yaxshi)
ADMIN_ID = 5815294733
DB_PATH = "cs2_shop.db"

PAYMENT_REKV = {
    "visa": "💳 VISA/UZCARD — hozir ishlamaydi. HUMO ni bosing!",
    "humo": "🟦 HUMO rekvizit:\n\nKarta: 9860 \nIsm: \nBank: HUMO",
    "crypto": "💠 Crypto — hozir ishlamaydi. HUMO ni bosing!",
}

REF_BONUS_PERCENT = 3
MIN_DEPOSIT = 1000

WEAR_LIST = ["Factory New", "Minimal Wear", "Field-Tested", "Well-Worn", "Battle-Scarred"]

CATEGORIES: Dict[str, List[str]] = {
    "🔪 Knives": [
        "Bayonet", "Flip Knife", "Gut Knife", "Karambit", "M9 Bayonet", "Huntsman Knife",
        "Falchion Knife", "Bowie Knife", "Butterfly Knife", "Shadow Daggers", "Navaja Knife",
        "Stiletto Knife", "Ursus Knife", "Talon Knife", "Classic Knife", "Paracord Knife",
        "Survival Knife", "Nomad Knife", "Skeleton Knife", "Kukri Knife"
    ],
    "🧤 Gloves": [
        "Sport Gloves", "Driver Gloves", "Hand Wraps", "Moto Gloves", "Specialist Gloves",
        "Hydra Gloves", "Broken Fang Gloves"
    ],
    "🔫 Pistols": [
        "Glock-18", "USP-S", "P2000", "P250", "Five-SeveN", "Tec-9", "CZ75-Auto",
        "Dual Berettas", "Desert Eagle", "R8 Revolver"
    ],
    "🔫 SMG": [
        "MAC-10", "MP9", "MP7", "MP5-SD", "UMP-45", "P90", "PP-Bizon"
    ],
    "🔫 Rifles": [
        "AK-47", "M4A4", "M4A1-S", "FAMAS", "Galil AR", "SG 553", "AUG"
    ],
    "🎯 Snipers": [
        "AWP", "SSG 08", "SCAR-20", "G3SG1"
    ],
    "💥 Heavy": [
        "Nova", "XM1014", "MAG-7", "Sawed-Off", "M249", "Negev"
    ],
    "⚡ Equipment": [
        "Zeus x27"
    ]
}

bot = TeleBot(TOKEN, parse_mode="HTML")

# =======================
# HELPERS
# =======================
def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID

def db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def now() -> int:
    return int(time.time())

def esc(s: str) -> str:
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

# =======================
# DB SCHEMA
# =======================
def ensure_schema():
    con = db()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY,
        balance INTEGER DEFAULT 0,
        joined_at INTEGER,
        referred_by INTEGER
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS products(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        section TEXT NOT NULL,
        weapon TEXT NOT NULL,
        title TEXT NOT NULL,
        price INTEGER NOT NULL,
        wear TEXT NOT NULL,
        used_note TEXT,
        photo_file_id TEXT,
        description TEXT,
        active INTEGER DEFAULT 1,
        created_at INTEGER
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS deposits(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        proof_file_id TEXT,
        status TEXT NOT NULL, -- pending/approved/rejected
        created_at INTEGER
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        price INTEGER NOT NULL,
        status TEXT NOT NULL, -- pending/approved/rejected/delivered
        created_at INTEGER
    )
    """)

    con.commit()
    con.close()

def get_user(uid: int) -> dict:
    con = db()
    cur = con.cursor()
    cur.execute("SELECT user_id, balance, joined_at, referred_by FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    if not row:
        cur.execute("INSERT INTO users(user_id, balance, joined_at, referred_by) VALUES(?,?,?,?)", (uid, 0, now(), None))
        con.commit()
        cur.execute("SELECT user_id, balance, joined_at, referred_by FROM users WHERE user_id=?", (uid,))
        row = cur.fetchone()
    con.close()
    return {"user_id": row[0], "balance": row[1], "joined_at": row[2], "referred_by": row[3]}

def set_referred_by(uid: int, ref: int):
    if ref == uid:
        return
    con = db()
    cur = con.cursor()
    cur.execute("SELECT referred_by FROM users WHERE user_id=?", (uid,))
    r = cur.fetchone()
    if r and r[0] is None:
        cur.execute("UPDATE users SET referred_by=? WHERE user_id=?", (ref, uid))
        con.commit()
    con.close()

def add_balance(uid: int, amount: int):
    con = db()
    cur = con.cursor()
    cur.execute("UPDATE users SET balance = COALESCE(balance,0) + ? WHERE user_id=?", (amount, uid))
    con.commit()
    con.close()

def sub_balance(uid: int, amount: int) -> bool:
    con = db()
    cur = con.cursor()
    cur.execute("SELECT balance FROM users WHERE user_id=?", (uid,))
    row = cur.fetchone()
    bal = row[0] if row else 0
    if bal < amount:
        con.close()
        return False
    cur.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, uid))
    con.commit()
    con.close()
    return True

# =======================
# DEMO SEED (bo‘sh bo‘lmasin)
# =======================
def seed_demo_if_empty():
    con = db()
    cur = con.cursor()
    cur.execute("SELECT COUNT(*) FROM products")
    cnt = cur.fetchone()[0]
    if cnt > 0:
        con.close()
        return

    base_prices = {
        "🔪 Knives": 250000,
        "🧤 Gloves": 180000,
        "🔫 Pistols": 45000,
        "🔫 SMG": 60000,
        "🔫 Rifles": 90000,
        "🎯 Snipers": 120000,
        "💥 Heavy": 70000,
        "⚡ Equipment": 30000
    }

    t = now()
    for section, weapons in CATEGORIES.items():
        for w in weapons:
            title = f"{w} | Demo Skin"
            wear = "Field-Tested"
            price = base_prices.get(section, 50000)
            cur.execute("""
                INSERT INTO products(section, weapon, title, price, wear, used_note, photo_file_id, description, active, created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)
            """, (section, w, title, price, wear, None, None, "Demo (keyin real skinlar bilan almashtirasiz).", 1, t))
    con.commit()
    con.close()

# =======================
# KEYBOARDS
# =======================
def main_menu_kb(uid: int) -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("🛒 Katalog", "🔎 Qidiruv")
    kb.row("💰 Balans", "➕ Depozit")
    if is_admin(uid):
        kb.row("🛠 Admin Panel")
    return kb

def admin_menu_kb() -> types.ReplyKeyboardMarkup:
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("➕ Skin qo‘shish", "📦 Mahsulotlar")
    kb.row("💳 Depozitlar", "🧾 Buyurtmalar")
    kb.row("⬅️ Asosiy menyu")
    return kb

def categories_kb(prefix: str) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    for sec in CATEGORIES.keys():
        kb.add(types.InlineKeyboardButton(sec, callback_data=f"{prefix}:sec:{sec}"))
    return kb

def weapons_kb(prefix: str, section: str) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    for w in CATEGORIES.get(section, []):
        kb.add(types.InlineKeyboardButton(w, callback_data=f"{prefix}:wep:{w}"))
    kb.add(types.InlineKeyboardButton("⬅️ Bo‘limlar", callback_data=f"{prefix}:back:sections"))
    return kb

def wear_kb() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    for w in WEAR_LIST:
        kb.add(types.InlineKeyboardButton(w, callback_data=f"wear:{w}"))
    return kb

def pay_kb() -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🟦 HUMO", callback_data="pay:humo"))
    kb.add(types.InlineKeyboardButton("💳 VISA/UZCARD", callback_data="pay:visa"))
    kb.add(types.InlineKeyboardButton("💠 Crypto", callback_data="pay:crypto"))
    return kb

def product_actions_kb(pid: int) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🛍 Sotib olish", callback_data=f"buy:{pid}"))
    kb.add(types.InlineKeyboardButton("⬅️ Ro‘yxatga qaytish", callback_data="nav:back_to_list"))
    return kb

def admin_product_manage_kb(pid: int, active: int) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(types.InlineKeyboardButton("🗑 O‘chirish", callback_data=f"admprod:del:{pid}"))
    kb.add(types.InlineKeyboardButton("✏️ Narx", callback_data=f"admprod:price:{pid}"))
    kb.add(types.InlineKeyboardButton("✅ Aktiv" if active == 0 else "⛔️ Passiv", callback_data=f"admprod:toggle:{pid}"))
    return kb

def admin_deposit_kb(deposit_id: int) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Tasdiq", callback_data=f"dep:ok:{deposit_id}"))
    kb.add(types.InlineKeyboardButton("❌ Rad", callback_data=f"dep:no:{deposit_id}"))
    return kb

def admin_order_kb(order_id: int) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ Tasdiq", callback_data=f"ord:ok:{order_id}"))
    kb.add(types.InlineKeyboardButton("❌ Rad", callback_data=f"ord:no:{order_id}"))
    kb.add(types.InlineKeyboardButton("📤 Delivered", callback_data=f"ord:del:{order_id}"))
    return kb

# =======================
# STATES
# =======================
state: Dict[int, dict] = {}
nav_state: Dict[int, dict] = {}  # section, weapon, offset, last_list_msg_id

# =======================
# PRODUCT QUERIES
# =======================
def fetch_products(section: str, weapon: str, limit: int = 10, offset: int = 0) -> List[dict]:
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT id, title, price, wear, used_note, photo_file_id, description
        FROM products
        WHERE active=1 AND section=? AND weapon=?
        ORDER BY created_at DESC, id DESC
        LIMIT ? OFFSET ?
    """, (section, weapon, limit, offset))
    rows = cur.fetchall()
    con.close()
    return [{
        "id": r[0], "title": r[1], "price": r[2], "wear": r[3],
        "used_note": r[4], "photo_file_id": r[5], "description": r[6],
        "section": section, "weapon": weapon
    } for r in rows]

def fetch_product(pid: int) -> Optional[dict]:
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT id, section, weapon, title, price, wear, used_note, photo_file_id, description, active
        FROM products WHERE id=?
    """, (pid,))
    r = cur.fetchone()
    con.close()
    if not r:
        return None
    return {
        "id": r[0], "section": r[1], "weapon": r[2], "title": r[3], "price": r[4],
        "wear": r[5], "used_note": r[6], "photo_file_id": r[7], "description": r[8], "active": r[9]
    }

def search_products(q: str, limit: int = 12) -> List[dict]:
    q = q.strip()
    if not q:
        return []
    like = f"%{q}%"
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT id, section, weapon, title, price, wear, photo_file_id
        FROM products
        WHERE active=1 AND (title LIKE ? OR weapon LIKE ? OR section LIKE ?)
        ORDER BY created_at DESC, id DESC
        LIMIT ?
    """, (like, like, like, limit))
    rows = cur.fetchall()
    con.close()
    return [{
        "id": r[0], "section": r[1], "weapon": r[2], "title": r[3],
        "price": r[4], "wear": r[5], "photo_file_id": r[6]
    } for r in rows]

# =======================
# SEND PRODUCT
# =======================
def send_product(chat_id: int, p: dict):
    text = (
        f"🧾 <b>{esc(p['title'])}</b>\n"
        f"📁 {esc(p['section'])}\n"
        f"🔫 {esc(p['weapon'])} | <i>{esc(p['wear'])}</i>\n"
        f"💰 <b>{p['price']}</b> so‘m\n"
    )
    if p.get("used_note"):
        text += f"🕒 Ishlatilgan: {esc(p['used_note'])}\n"
    if p.get("description"):
        text += f"📝 {esc(p['description'])}\n"

    if p.get("photo_file_id"):
        bot.send_photo(chat_id, p["photo_file_id"], caption=text, reply_markup=product_actions_kb(p["id"]))
    else:
        bot.send_message(chat_id, text, reply_markup=product_actions_kb(p["id"]))

# =======================
# LIST VIEW (katalog list)
# =======================
def product_list_kb(uid: int, items: List[dict]) -> types.InlineKeyboardMarkup:
    kb = types.InlineKeyboardMarkup()
    for p in items:
        kb.add(types.InlineKeyboardButton(
            f"{p['title']} — {p['price']} so‘m",
            callback_data=f"view:{p['id']}"
        ))
    kb.row(
        types.InlineKeyboardButton("⬅️", callback_data="nav:prev"),
        types.InlineKeyboardButton("➡️", callback_data="nav:next")
    )
    kb.add(types.InlineKeyboardButton("⬅️ Qurollar", callback_data="nav:back_weapons"))
    kb.add(types.InlineKeyboardButton("⬅️ Bo‘limlar", callback_data="nav:back_sections"))
    return kb

def show_product_list(chat_id: int, uid: int, edit_message_id: Optional[int] = None):
    nav = nav_state.get(uid)
    if not nav:
        bot.send_message(chat_id, "❗ Sessiya yo‘q. Katalogdan qayta kiring.")
        return

    section = nav["section"]
    weapon = nav["weapon"]
    offset = nav.get("offset", 0)

    items = fetch_products(section, weapon, limit=10, offset=offset)

    title = f"📁 <b>{esc(section)}</b>\n🔫 <b>{esc(weapon)}</b>\n\n"
    if not items:
        text = title + "❗ Hozircha skin yo‘q (admin keyin qo‘shadi)."
    else:
        text = title + "🧾 Skinlar ro‘yxati (tanlang):"

    kb = product_list_kb(uid, items)

    if edit_message_id:
        bot.edit_message_text(text, chat_id, edit_message_id, reply_markup=kb)
        nav_state[uid]["last_list_msg_id"] = edit_message_id
    else:
        msg = bot.send_message(chat_id, text, reply_markup=kb)
        nav_state[uid]["last_list_msg_id"] = msg.message_id

# =======================
# START / MENU
# =======================
@bot.message_handler(commands=["start"])
def cmd_start(m):
    uid = m.from_user.id
    get_user(uid)

    # referral: /start 12345
    parts = (m.text or "").split()
    if len(parts) >= 2 and parts[1].isdigit():
        ref = int(parts[1])
        set_referred_by(uid, ref)

    bot.send_message(
        m.chat.id,
        "👋 Salom! CS2 Skin Shop botiga xush kelibsiz.\n\n"
        "🛒 Katalogdan skin tanlang yoki 🔎 qidiruvdan foydalaning.\n"
        "➕ Depozit qilib balans to‘ldiring.",
        reply_markup=main_menu_kb(uid)
    )

@bot.message_handler(func=lambda m: m.text == "⬅️ Asosiy menyu")
def go_main_menu(m):
    bot.send_message(m.chat.id, "✅ Asosiy menyu", reply_markup=main_menu_kb(m.from_user.id))

# =======================
# USER: BALANCE
# =======================
@bot.message_handler(func=lambda m: m.text == "💰 Balans")
def user_balance(m):
    u = get_user(m.from_user.id)
    bot.send_message(m.chat.id, f"💰 Balansingiz: <b>{u['balance']}</b> so‘m")

# =======================
# USER: CATALOG
# =======================
@bot.message_handler(func=lambda m: m.text == "🛒 Katalog")
def user_catalog(m):
    bot.send_message(m.chat.id, "📁 Bo‘lim tanlang:", reply_markup=categories_kb("cat"))

@bot.callback_query_handler(func=lambda c: c.data.startswith("cat:sec:"))
def cat_pick_section(c):
    section = c.data.split("cat:sec:", 1)[1]
    bot.edit_message_text(
        f"{esc(section)}\n\n🔫 Qurol tanlang:",
        c.message.chat.id,
        c.message.message_id,
        reply_markup=weapons_kb("cat", section)
    )
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("cat:wep:"))
def cat_pick_weapon(c):
    weapon = c.data.split("cat:wep:", 1)[1]

    # sectionni message textdan olamiz:
    section = (c.message.text or "").split("\n", 1)[0].strip()
    if section not in CATEGORIES:
        # fallback
        for k in CATEGORIES.keys():
            if k in (c.message.text or ""):
                section = k
                break
        if section not in CATEGORIES:
            section = list(CATEGORIES.keys())[0]

    nav_state[c.from_user.id] = {"section": section, "weapon": weapon, "offset": 0, "last_list_msg_id": None}
    show_product_list(c.message.chat.id, c.from_user.id, edit_message_id=c.message.message_id)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "cat:back:sections")
def cat_back_sections(c):
    bot.edit_message_text(
        "📁 Bo‘lim tanlang:",
        c.message.chat.id,
        c.message.message_id,
        reply_markup=categories_kb("cat")
    )
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "nav:prev")
def nav_prev(c):
    nav = nav_state.get(c.from_user.id)
    if not nav:
        bot.answer_callback_query(c.id, "Sessiya yo‘q.")
        return
    nav["offset"] = max(0, nav.get("offset", 0) - 10)
    show_product_list(c.message.chat.id, c.from_user.id, edit_message_id=c.message.message_id)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "nav:next")
def nav_next(c):
    nav = nav_state.get(c.from_user.id)
    if not nav:
        bot.answer_callback_query(c.id, "Sessiya yo‘q.")
        return
    nav["offset"] = nav.get("offset", 0) + 10
    show_product_list(c.message.chat.id, c.from_user.id, edit_message_id=c.message.message_id)
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "nav:back_weapons")
def nav_back_weapons(c):
    nav = nav_state.get(c.from_user.id)
    if not nav:
        bot.answer_callback_query(c.id, "Sessiya yo‘q.")
        return
    section = nav["section"]
    bot.edit_message_text(
        f"{esc(section)}\n\n🔫 Qurol tanlang:",
        c.message.chat.id,
        c.message.message_id,
        reply_markup=weapons_kb("cat", section)
    )
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data == "nav:back_sections")
def nav_back_sections(c):
    bot.edit_message_text(
        "📁 Bo‘lim tanlang:",
        c.message.chat.id,
        c.message.message_id,
        reply_markup=categories_kb("cat")
    )
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("view:"))
def view_product(c):
    pid = int(c.data.split(":", 1)[1])
    p = fetch_product(pid)
    if not p or p["active"] != 1:
        bot.answer_callback_query(c.id, "Topilmadi.")
        return
    bot.answer_callback_query(c.id)
    send_product(c.message.chat.id, p)

@bot.callback_query_handler(func=lambda c: c.data == "nav:back_to_list")
def nav_back_to_list(c):
    nav = nav_state.get(c.from_user.id)
    bot.answer_callback_query(c.id)
    if not nav:
        bot.send_message(c.message.chat.id, "📁 Bo‘lim tanlang:", reply_markup=categories_kb("cat"))
        return
    # oxirgi listni qayta ko‘rsatamiz
    show_product_list(c.message.chat.id, c.from_user.id)

# =======================
# USER: SEARCH
# =======================
@bot.message_handler(func=lambda m: m.text == "🔎 Qidiruv")
def user_search(m):
    state[m.from_user.id] = {"step": "search"}
    bot.send_message(m.chat.id, "🔎 Skin nomini yozing (masalan: AWP, Karambit, Fade):")

@bot.message_handler(func=lambda m: state.get(m.from_user.id, {}).get("step") == "search")
def user_search_query(m):
    q = (m.text or "").strip()
    items = search_products(q, limit=15)
    state.pop(m.from_user.id, None)

    if not items:
        bot.send_message(m.chat.id, "❗ Hech narsa topilmadi.")
        return

    kb = types.InlineKeyboardMarkup()
    for p in items:
        kb.add(types.InlineKeyboardButton(
            f"{p['title']} — {p['price']} so‘m",
            callback_data=f"view:{p['id']}"
        ))
    bot.send_message(m.chat.id, f"✅ Topildi: <b>{len(items)}</b> ta", reply_markup=kb)

# =======================
# USER: DEPOSIT
# =======================
@bot.message_handler(func=lambda m: m.text == "➕ Depozit")
def user_deposit(m):
    state[m.from_user.id] = {"step": "dep_amount"}
    bot.send_message(m.chat.id, f"➕ Depozit summasini yozing (min {MIN_DEPOSIT} so‘m):")

@bot.message_handler(func=lambda m: state.get(m.from_user.id, {}).get("step") == "dep_amount")
def dep_amount(m):
    txt = (m.text or "").strip()
    if not txt.isdigit():
        bot.send_message(m.chat.id, "❗ Faqat son kiriting.")
        return
    amt = int(txt)
    if amt < MIN_DEPOSIT:
        bot.send_message(m.chat.id, f"❗ Minimal depozit: {MIN_DEPOSIT} so‘m.")
        return
    state[m.from_user.id] = {"step": "dep_pay", "amount": amt}
    bot.send_message(m.chat.id, "💳 To‘lov turini tanlang:", reply_markup=pay_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("pay:"))
def dep_paytype(c):
    st = state.get(c.from_user.id)
    if not st or st.get("step") != "dep_pay":
        bot.answer_callback_query(c.id)
        return
    key = c.data.split(":", 1)[1]
    info = PAYMENT_REKV.get(key, "Noma'lum")
    st["paytype"] = key
    st["step"] = "dep_proof"
    bot.answer_callback_query(c.id)
    bot.send_message(
        c.message.chat.id,
        f"{info}\n\n📸 Endi to‘lov chekini/ss ni rasm qilib yuboring.\n"
        f"Yoki 'skip' deb yozing (isbotsiz yuborish)."
    )

@bot.message_handler(func=lambda m: state.get(m.from_user.id, {}).get("step") == "dep_proof")
def dep_proof_skip_text(m):
    st = state.get(m.from_user.id)
    txt = (m.text or "").strip().lower()
    if txt != "skip":
        bot.send_message(m.chat.id, "📸 Iltimos rasm yuboring yoki 'skip' deb yozing.")
        return

    con = db()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO deposits(user_id, amount, proof_file_id, status, created_at)
        VALUES(?,?,?,?,?)
    """, (m.from_user.id, st["amount"], None, "pending", now()))
    dep_id = cur.lastrowid
    con.commit()
    con.close()

    state.pop(m.from_user.id, None)
    bot.send_message(m.chat.id, "✅ Depozit so‘rovi yuborildi. Admin tekshiradi.")
    notify_admin_deposit(dep_id)

@bot.message_handler(content_types=["photo"], func=lambda m: state.get(m.from_user.id, {}).get("step") == "dep_proof")
def dep_proof_photo(m):
    st = state.get(m.from_user.id)
    photo_id = m.photo[-1].file_id

    con = db()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO deposits(user_id, amount, proof_file_id, status, created_at)
        VALUES(?,?,?,?,?)
    """, (m.from_user.id, st["amount"], photo_id, "pending", now()))
    dep_id = cur.lastrowid
    con.commit()
    con.close()

    state.pop(m.from_user.id, None)
    bot.send_message(m.chat.id, "✅ Depozit so‘rovi yuborildi. Admin tekshiradi.")
    notify_admin_deposit(dep_id)

def notify_admin_deposit(dep_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("SELECT id, user_id, amount, proof_file_id FROM deposits WHERE id=?", (dep_id,))
    r = cur.fetchone()
    con.close()
    if not r:
        return

    _, uid, amt, proof = r
    text = (
        f"💳 <b>DEPOZIT SO‘ROVI</b>\n"
        f"👤 User: <code>{uid}</code>\n"
        f"💰 Summa: <b>{amt}</b> so‘m\n"
        f"🕒 {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now()))}"
    )
    if proof:
        bot.send_photo(ADMIN_ID, proof, caption=text, reply_markup=admin_deposit_kb(dep_id))
    else:
        bot.send_message(ADMIN_ID, text + "\n\n(Isbotsiz)", reply_markup=admin_deposit_kb(dep_id))

@bot.callback_query_handler(func=lambda c: c.data.startswith("dep:"))
def admin_deposit_action(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id)
        return

    _, act, dep_id_s = c.data.split(":")
    dep_id = int(dep_id_s)

    con = db()
    cur = con.cursor()
    cur.execute("SELECT user_id, amount, status FROM deposits WHERE id=?", (dep_id,))
    row = cur.fetchone()
    if not row:
        con.close()
        bot.answer_callback_query(c.id, "Topilmadi.")
        return

    uid, amt, status = row
    if status != "pending":
        con.close()
        bot.answer_callback_query(c.id, "Allaqachon ko‘rilgan.")
        return

    if act == "ok":
        cur.execute("UPDATE deposits SET status='approved' WHERE id=?", (dep_id,))
        con.commit()
        con.close()

        add_balance(uid, amt)

        # referral bonus
        u = get_user(uid)
        ref = u.get("referred_by")
        if ref:
            bonus = int(amt * REF_BONUS_PERCENT / 100)
            if bonus > 0:
                add_balance(ref, bonus)
                try:
                    bot.send_message(ref, f"🎁 Referral bonus: <b>{bonus}</b> so‘m (do‘stingiz depozit qildi).")
                except Exception:
                    pass

        bot.answer_callback_query(c.id, "Tasdiqlandi ✅")
        try:
            bot.send_message(uid, f"✅ Depozitingiz tasdiqlandi: <b>{amt}</b> so‘m.\n💰 Balansingiz to‘ldirildi.")
        except Exception:
            pass
        bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)

    elif act == "no":
        cur.execute("UPDATE deposits SET status='rejected' WHERE id=?", (dep_id,))
        con.commit()
        con.close()

        bot.answer_callback_query(c.id, "Rad etildi ❌")
        try:
            bot.send_message(uid, "❌ Depozitingiz rad etildi. Agar xato bo‘lsa, qayta yuboring.")
        except Exception:
            pass
        bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)

# =======================
# USER: BUY / ORDER
# =======================
@bot.callback_query_handler(func=lambda c: c.data.startswith("buy:"))
def user_buy(c):
    pid = int(c.data.split(":", 1)[1])
    p = fetch_product(pid)
    if not p or p["active"] != 1:
        bot.answer_callback_query(c.id, "Topilmadi.")
        return

    uid = c.from_user.id
    u = get_user(uid)

    if u["balance"] < p["price"]:
        bot.answer_callback_query(c.id, "Balans yetarli emas.")
        bot.send_message(c.message.chat.id, f"❗ Balans yetarli emas.\n💰 Balans: <b>{u['balance']}</b> so‘m\n💳 Narx: <b>{p['price']}</b> so‘m")
        return

    if not sub_balance(uid, p["price"]):
        bot.answer_callback_query(c.id, "Balans yetarli emas.")
        return

    con = db()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO orders(user_id, product_id, price, status, created_at)
        VALUES(?,?,?,?,?)
    """, (uid, pid, p["price"], "pending", now()))
    order_id = cur.lastrowid
    con.commit()
    con.close()

    bot.answer_callback_query(c.id, "Buyurtma yuborildi ✅")
    bot.send_message(c.message.chat.id, f"✅ Buyurtma yuborildi!\n🧾 Order ID: <code>{order_id}</code>\nAdmin tez orada tekshiradi.")
    notify_admin_order(order_id)

def notify_admin_order(order_id: int):
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT o.id, o.user_id, o.price, o.status, p.title, p.weapon, p.wear, p.photo_file_id
        FROM orders o
        JOIN products p ON p.id = o.product_id
        WHERE o.id=?
    """, (order_id,))
    r = cur.fetchone()
    con.close()
    if not r:
        return

    oid, uid, price, status, title, weapon, wear, photo = r
    text = (
        f"📦 <b>BUYURTMA</b>\n"
        f"🧾 Order ID: <code>{oid}</code>\n"
        f"👤 User: <code>{uid}</code>\n"
        f"🧾 Skin: <b>{esc(title)}</b>\n"
        f"🔫 {esc(weapon)} | {esc(wear)}\n"
        f"💰 Narx: <b>{price}</b> so‘m\n"
        f"📌 Status: <b>{status}</b>"
    )
    if photo:
        bot.send_photo(ADMIN_ID, photo, caption=text, reply_markup=admin_order_kb(oid))
    else:
        bot.send_message(ADMIN_ID, text, reply_markup=admin_order_kb(oid))

@bot.callback_query_handler(func=lambda c: c.data.startswith("ord:"))
def admin_order_action(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id)
        return

    _, act, oid_s = c.data.split(":")
    oid = int(oid_s)

    con = db()
    cur = con.cursor()
    cur.execute("SELECT user_id, price, status FROM orders WHERE id=?", (oid,))
    row = cur.fetchone()
    if not row:
        con.close()
        bot.answer_callback_query(c.id, "Topilmadi.")
        return

    uid, price, status = row
    if status not in ("pending", "approved"):
        con.close()
        bot.answer_callback_query(c.id, "Allaqachon yakunlangan.")
        return

    if act == "ok":
        cur.execute("UPDATE orders SET status='approved' WHERE id=?", (oid,))
        con.commit()
        con.close()

        bot.answer_callback_query(c.id, "Tasdiq ✅")
        try:
            bot.send_message(uid, f"✅ Buyurtmangiz tasdiqlandi!\n🧾 Order ID: <code>{oid}</code>")
        except Exception:
            pass
        bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=admin_order_kb(oid))

    elif act == "no":
        cur.execute("UPDATE orders SET status='rejected' WHERE id=?", (oid,))
        con.commit()
        con.close()

        add_balance(uid, price)

        bot.answer_callback_query(c.id, "Rad ❌ (refund)")
        try:
            bot.send_message(uid, f"❌ Buyurtmangiz rad etildi.\n🧾 Order ID: <code>{oid}</code>\n💰 Pul qaytarildi: <b>{price}</b> so‘m")
        except Exception:
            pass
        bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)

    elif act == "del":
        con2 = db()
        cur2 = con2.cursor()
        cur2.execute("UPDATE orders SET status='delivered' WHERE id=?", (oid,))
        con2.commit()
        con2.close()

        bot.answer_callback_query(c.id, "Delivered 📤")
        try:
            bot.send_message(uid, f"📤 Buyurtmangiz yetkazildi!\n🧾 Order ID: <code>{oid}</code>")
        except Exception:
            pass
        bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)

# =======================
# ADMIN PANEL
# =======================
@bot.message_handler(func=lambda m: m.text == "🛠 Admin Panel")
def admin_panel(m):
    if not is_admin(m.from_user.id):
        return
    bot.send_message(m.chat.id, "🛠 Admin Panel", reply_markup=admin_menu_kb())

# ---------- Admin: Add Product ----------
@bot.message_handler(func=lambda m: m.text == "➕ Skin qo‘shish")
def admin_add_start(m):
    if not is_admin(m.from_user.id):
        return
    state[m.from_user.id] = {"step": "add_section", "data": {}}
    bot.send_message(m.chat.id, "📁 Bo‘lim tanlang:", reply_markup=categories_kb("add"))

@bot.callback_query_handler(func=lambda c: c.data.startswith("add:sec:"))
def admin_add_section_pick(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id)
        return
    section = c.data.split("add:sec:", 1)[1]
    st = state.get(c.from_user.id)
    if not st or st.get("step") != "add_section":
        bot.answer_callback_query(c.id, "Sessiya yo‘q.")
        return
    st["data"]["section"] = section
    st["step"] = "add_weapon"
    bot.edit_message_text(
        f"{esc(section)}\n\n🔫 Qurol tanlang:",
        c.message.chat.id,
        c.message.message_id,
        reply_markup=weapons_kb("add", section)
    )
    bot.answer_callback_query(c.id)

@bot.callback_query_handler(func=lambda c: c.data.startswith("add:wep:"))
def admin_add_weapon_pick(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id)
        return
    weapon = c.data.split("add:wep:", 1)[1]
    st = state.get(c.from_user.id)
    if not st or st.get("step") != "add_weapon":
        bot.answer_callback_query(c.id, "Sessiya yo‘q.")
        return
    st["data"]["weapon"] = weapon
    st["step"] = "add_title"
    bot.answer_callback_query(c.id)
    bot.send_message(c.message.chat.id, f"✅ Qurol: <b>{esc(weapon)}</b>\nSkin nomini yozing:")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and state.get(m.from_user.id, {}).get("step") == "add_title")
def admin_add_title(m):
    st = state[m.from_user.id]
    title = (m.text or "").strip()
    if len(title) < 2:
        bot.send_message(m.chat.id, "❗ To‘g‘ri nom yozing.")
        return
    st["data"]["title"] = title
    st["step"] = "add_price"
    bot.send_message(m.chat.id, "Narx (son, so‘m):")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and state.get(m.from_user.id, {}).get("step") == "add_price")
def admin_add_price(m):
    txt = (m.text or "").strip()
    if not txt.isdigit():
        bot.send_message(m.chat.id, "❗ Faqat son kiriting.")
        return
    st = state[m.from_user.id]
    st["data"]["price"] = int(txt)
    st["step"] = "add_wear"
    bot.send_message(m.chat.id, "Holatini tanlang:", reply_markup=wear_kb())

@bot.callback_query_handler(func=lambda c: c.data.startswith("wear:"))
def admin_add_wear_pick(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id)
        return
    st = state.get(c.from_user.id)
    if not st or st.get("step") != "add_wear":
        bot.answer_callback_query(c.id)
        return
    wear = c.data.split(":", 1)[1]
    st["data"]["wear"] = wear
    st["step"] = "add_used"
    bot.answer_callback_query(c.id)
    bot.send_message(c.message.chat.id, "Ishlatilgani (masalan: 2 oy) yoki 'skip':")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and state.get(m.from_user.id, {}).get("step") == "add_used")
def admin_add_used(m):
    st = state[m.from_user.id]
    txt = (m.text or "").strip()
    st["data"]["used_note"] = None if txt.lower() == "skip" else txt
    st["step"] = "add_photo"
    bot.send_message(m.chat.id, "📸 Rasm yuboring (yoki 'skip' deb yozing):")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and state.get(m.from_user.id, {}).get("step") == "add_photo")
def admin_add_photo_skip_or_text(m):
    st = state[m.from_user.id]
    txt = (m.text or "").strip().lower()
    if txt == "skip":
        st["data"]["photo_file_id"] = None
        st["step"] = "add_desc"
        bot.send_message(m.chat.id, "Tavsif (yoki 'skip'):")
    else:
        bot.send_message(m.chat.id, "📸 Iltimos rasm yuboring yoki 'skip' deb yozing.")

@bot.message_handler(content_types=["photo"], func=lambda m: is_admin(m.from_user.id) and state.get(m.from_user.id, {}).get("step") == "add_photo")
def admin_add_photo_file(m):
    st = state[m.from_user.id]
    st["data"]["photo_file_id"] = m.photo[-1].file_id
    st["step"] = "add_desc"
    bot.send_message(m.chat.id, "✅ Rasm qabul qilindi.\nTavsif (yoki 'skip'):")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and state.get(m.from_user.id, {}).get("step") == "add_desc")
def admin_add_desc(m):
    st = state[m.from_user.id]
    txt = (m.text or "").strip()
    st["data"]["description"] = None if txt.lower() == "skip" else txt

    d = st["data"]
    con = db()
    cur = con.cursor()
    cur.execute("""
        INSERT INTO products(section, weapon, title, price, wear, used_note, photo_file_id, description, active, created_at)
        VALUES(?,?,?,?,?,?,?,?,?,?)
    """, (
        d["section"], d["weapon"], d["title"], d["price"], d["wear"],
        d.get("used_note"), d.get("photo_file_id"), d.get("description"),
        1, now()
    ))
    con.commit()
    con.close()

    state.pop(m.from_user.id, None)
    bot.send_message(m.chat.id, "✅ Skin katalogga qo‘shildi!", reply_markup=admin_menu_kb())

# ---------- Admin: Products list/manage ----------
@bot.message_handler(func=lambda m: m.text == "📦 Mahsulotlar")
def admin_products(m):
    if not is_admin(m.from_user.id):
        return
    send_admin_products_page(m.chat.id, 0)

def send_admin_products_page(chat_id: int, offset: int):
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT id, title, price, weapon, wear, active
        FROM products
        ORDER BY created_at DESC, id DESC
        LIMIT 10 OFFSET ?
    """, (offset,))
    rows = cur.fetchall()
    con.close()

    if not rows:
        bot.send_message(chat_id, "❗ Mahsulot yo‘q.")
        return

    kb = types.InlineKeyboardMarkup()
    for pid, title, price, weapon, wear, active in rows:
        status = "✅" if active == 1 else "⛔️"
        kb.add(types.InlineKeyboardButton(
            f"{status} {title} — {price} so‘m",
            callback_data=f"admprod:view:{pid}"
        ))
    kb.row(
        types.InlineKeyboardButton("⬅️", callback_data=f"admprod:page:{max(0, offset-10)}"),
        types.InlineKeyboardButton("➡️", callback_data=f"admprod:page:{offset+10}")
    )
    bot.send_message(chat_id, "📦 Mahsulotlar (tanlang):", reply_markup=kb)

@bot.callback_query_handler(func=lambda c: c.data.startswith("admprod:page:"))
def admprod_page(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id)
        return
    off = int(c.data.split(":")[-1])
    bot.answer_callback_query(c.id)
    send_admin_products_page(c.message.chat.id, off)

@bot.callback_query_handler(func=lambda c: c.data.startswith("admprod:view:"))
def admprod_view(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id)
        return
    pid = int(c.data.split(":")[-1])
    p = fetch_product(pid)
    if not p:
        bot.answer_callback_query(c.id, "Topilmadi.")
        return
    bot.answer_callback_query(c.id)

    text = (
        f"🧾 <b>{esc(p['title'])}</b>\n"
        f"📁 {esc(p['section'])}\n"
        f"🔫 {esc(p['weapon'])} | {esc(p['wear'])}\n"
        f"💰 <b>{p['price']}</b> so‘m\n"
        f"📌 Active: <b>{'YES' if p['active']==1 else 'NO'}</b>\n"
    )
    if p.get("description"):
        text += f"📝 {esc(p['description'])}\n"

    if p.get("photo_file_id"):
        bot.send_photo(c.message.chat.id, p["photo_file_id"], caption=text, reply_markup=admin_product_manage_kb(pid, p["active"]))
    else:
        bot.send_message(c.message.chat.id, text, reply_markup=admin_product_manage_kb(pid, p["active"]))

@bot.callback_query_handler(func=lambda c: c.data.startswith("admprod:del:"))
def admprod_del(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id)
        return
    pid = int(c.data.split(":")[-1])
    con = db()
    cur = con.cursor()
    cur.execute("DELETE FROM products WHERE id=?", (pid,))
    con.commit()
    con.close()
    bot.answer_callback_query(c.id, "O‘chirildi 🗑")
    bot.edit_message_reply_markup(c.message.chat.id, c.message.message_id, reply_markup=None)

@bot.callback_query_handler(func=lambda c: c.data.startswith("admprod:toggle:"))
def admprod_toggle(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id)
        return
    pid = int(c.data.split(":")[-1])
    con = db()
    cur = con.cursor()
    cur.execute("SELECT active FROM products WHERE id=?", (pid,))
    r = cur.fetchone()
    if not r:
        con.close()
        bot.answer_callback_query(c.id, "Topilmadi.")
        return
    newv = 0 if r[0] == 1 else 1
    cur.execute("UPDATE products SET active=? WHERE id=?", (newv, pid))
    con.commit()
    con.close()
    bot.answer_callback_query(c.id, "Yangilandi ✅")

@bot.callback_query_handler(func=lambda c: c.data.startswith("admprod:price:"))
def admprod_price(c):
    if not is_admin(c.from_user.id):
        bot.answer_callback_query(c.id)
        return
    pid = int(c.data.split(":")[-1])
    state[c.from_user.id] = {"step": "edit_price", "pid": pid}
    bot.answer_callback_query(c.id)
    bot.send_message(c.message.chat.id, "✏️ Yangi narxni yozing (son):")

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and state.get(m.from_user.id, {}).get("step") == "edit_price")
def admprod_price_set(m):
    txt = (m.text or "").strip()
    if not txt.isdigit():
        bot.send_message(m.chat.id, "❗ Faqat son kiriting.")
        return
    pid = state[m.from_user.id]["pid"]
    new_price = int(txt)
    con = db()
    cur = con.cursor()
    cur.execute("UPDATE products SET price=? WHERE id=?", (new_price, pid))
    con.commit()
    con.close()
    state.pop(m.from_user.id, None)
    bot.send_message(m.chat.id, f"✅ Narx yangilandi: <b>{new_price}</b> so‘m")

# ---------- Admin: Deposits / Orders list ----------
@bot.message_handler(func=lambda m: m.text == "💳 Depozitlar")
def adm_deposits_list(m):
    if not is_admin(m.from_user.id):
        return
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT id, user_id, amount, status, created_at
        FROM deposits
        ORDER BY created_at DESC, id DESC
        LIMIT 20
    """)
    rows = cur.fetchall()
    con.close()
    if not rows:
        bot.send_message(m.chat.id, "Depozitlar yo‘q.")
        return
    text = "💳 <b>So‘nggi depozitlar</b>\n\n"
    for did, uid, amt, stt, t in rows:
        text += f"#{did} | <code>{uid}</code> | {amt} so‘m | <b>{stt}</b>\n"
    bot.send_message(m.chat.id, text)

@bot.message_handler(func=lambda m: m.text == "🧾 Buyurtmalar")
def adm_orders_list(m):
    if not is_admin(m.from_user.id):
        return
    con = db()
    cur = con.cursor()
    cur.execute("""
        SELECT o.id, o.user_id, o.price, o.status, p.title
        FROM orders o
        JOIN products p ON p.id=o.product_id
        ORDER BY o.created_at DESC, o.id DESC
        LIMIT 20
    """)
    rows = cur.fetchall()
    con.close()
    if not rows:
        bot.send_message(m.chat.id, "Buyurtmalar yo‘q.")
        return
    text = "📦 <b>So‘nggi buyurtmalar</b>\n\n"
    for oid, uid, price, stt, title in rows:
        text += f"#{oid} | <code>{uid}</code> | {price} so‘m | <b>{stt}</b>\n🧾 {esc(title)}\n\n"
    bot.send_message(m.chat.id, text)

# =======================
# RUN
# =======================
def main():
    ensure_schema()
    seed_demo_if_empty()
    print("Bot running...")
    bot.infinity_polling(skip_pending=True)

if __name__ == "__main__":
    main()
