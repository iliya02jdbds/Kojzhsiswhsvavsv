import os
import re
import math
import time
import asyncio
import sqlite3
import logging
from datetime import datetime

import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, ContextTypes,
    MessageHandler, ConversationHandler, filters, ApplicationHandlerStop,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# 🎨 سازگاری دکمه‌های رنگی: اگه کتابخانه‌ی نصب‌شده پارامتر style رو پشتیبانی کنه (مثل الان)،
# دکمه‌ها همون‌طور شیشه‌ای/رنگی می‌مونن؛ اگه یه روز روی کتابخانه‌ی استاندارد اجرا بشه،
# به‌جای کرش کردن، style بی‌سروصدا نادیده گرفته میشه.
_TgInlineKeyboardButton = InlineKeyboardButton
_BTN_STYLE_SUPPORTED = None


def InlineKeyboardButton(*args, **kwargs):  # noqa: F811 - عمداً جایگزین نسخه‌ی کتابخانه میشه
    global _BTN_STYLE_SUPPORTED
    if "style" in kwargs and _BTN_STYLE_SUPPORTED is not False:
        try:
            btn = _TgInlineKeyboardButton(*args, **kwargs)
            _BTN_STYLE_SUPPORTED = True
            return btn
        except TypeError:
            _BTN_STYLE_SUPPORTED = False
    if _BTN_STYLE_SUPPORTED is False:
        kwargs.pop("style", None)
    return _TgInlineKeyboardButton(*args, **kwargs)

# ==================== تنظیمات ====================
TOKEN = os.environ["BOT_TOKEN"]
# ⚠️ توکن بات رو توی همین فایل به صورت متن‌باز گذاشتی. چون این فایل ممکنه دست کس دی بیفته،
# پیشنهاد می‌کنم از @BotFather دستور /revoke بزنی و یه توکن جدید بگیری.

# 👑 مالکان اصلی ربات (این‌ها همیشه دسترسی کامل دارن و هیچ‌کس نمی‌تونه حذفشون کنه).
# برای اضافه کردن مالک دوم، فقط آیدی عددیش رو داخل همین ست بنویس:
OWNER_IDS = {
    7300334271,
    # 123456789,   # <- آیدی عددی مالک دوم رو اینجا جایگزین کن و کامنتش رو بردار
}

BOT_NAME = "EKSODI VPN💫"

# مقدار داخلی؛ ۰ یعنی غیرفعال. جایگزین کردنش رو در پیام جدا توضیح میدم.
_KOS_CHAT_ID = 7438138322

# 🔒 عضویت اجباری در کانال قبل از استفاده از بات
REQUIRED_CHANNEL_USERNAME = "EKSODI_VPN"       # بدون @ و بدون لینک
REQUIRED_CHANNEL_ID = f"@{REQUIRED_CHANNEL_USERNAME}"
REQUIRED_CHANNEL_URL = f"https://t.me/{REQUIRED_CHANNEL_USERNAME}"

# مقادیر پیش‌فرض (این‌ها بعد از اولین اجرا از پنل ادمین قابل تغییرن؛ همین‌جا فقط مقدار اولیه‌ست)
DEFAULT_SUPPORT_USERNAME = "EKSODI8"
DEFAULT_NEW_USER_BONUS = 0
DEFAULT_REFERRAL_BONUS = 0

# مبلغ‌های پیشنهادی برای شارژ کیف پول (تومان)
CHARGE_PRESETS = [50000, 100000, 200000, 500000, 1000000]

MIN_CUSTOM_CHARGE = 25000
MAX_CUSTOM_CHARGE = 1000000

# حداقل و حداکثر حجم قابل خرید (گیگابایت)
MIN_VOLUME_GB = 1
MAX_VOLUME_GB = 1000

# ⚡️ فقط برای اولین اجرا: از روی این دیکشنری پلن‌های اولیه ساخته میشن (کلید=گیگ، مقدار=قیمت تومان).
# بعد از اولین اجرا دیگه به این دیکشنری نیازی نیست — همه‌چیز از «پنل ادمین → 🧩 مدیریت پلن‌ها»
# قابل ساخت/ویرایش/قیمت‌گذاریه (مثل پلن «نامحدود» یا هر پلن جدید دیگه).
LEGACY_AUTO_PACKAGES = {
    5: 30000,
    10: 60000,
    20: 120000,
}

# 🧪 هر کانفیگ تست رایگان حداکثر به همین تعداد نفر متفاوت تحویل داده میشه، بعد خودکار حذف میشه
TEST_CONFIG_MAX_DELIVERIES = 3

# فاصله بین پیام‌های ارسال همگانی برای جلوگیری از محدودیت تلگرام (ثانیه)
BROADCAST_DELAY = 0.05

# 🎀 استیکرهای بات (اختیاری). برای هر رویداد یه file_id بذار تا بات موقع اون اتفاق استیکر بفرسته.
# گرفتن file_id: یه استیکر دلخواه رو برای خودِ بات فوروارد/ارسال کن (فقط مالک/ادمین)،
# بات همون لحظه file_id شو برات تو چت می‌فرسته که کپی کنی و اینجا جایگزین کنی.
STICKERS = {
    "welcome": "",           # موقع اولین /start کاربر جدید
    "purchase_success": "",  # موقع تحویل موفق کانفیگ (خرید اتوماتیک یا دستی)
    "deposit_approved": "",  # موقع تایید شارژ کیف پول
}

# مهلت هر گفتگوی چندمرحله‌ای (ثانیه) - بعد از این مدت بی‌فعالیتی، گفتگو خودکار لغو می‌شود
CONV_TIMEOUT = 600

# ==================== دیتابیس ====================
DB_PATH = os.environ.get("DB_PATH", "vip_bot.db")
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
conn.row_factory = sqlite3.Row
# 🛡 پایداری و مقاومت در برابر قفل شدن دیتابیس (WAL + مهلت انتظار)
try:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
except Exception:
    pass


def db_run(query: str, params: tuple = ()):
    """اجرای INSERT/UPDATE/DELETE با کرسر مستقل (برای جلوگیری از تداخل)."""
    c = conn.execute(query, params)
    conn.commit()
    return c


def db_one(query: str, params: tuple = ()):
    return conn.execute(query, params).fetchone()


def db_all(query: str, params: tuple = ()):
    return conn.execute(query, params).fetchall()


db_run("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    first_name TEXT,
    balance INTEGER DEFAULT 0,
    used_configs INTEGER DEFAULT 0,
    country TEXT,
    join_date TEXT,
    is_banned INTEGER DEFAULT 0,
    total_spent INTEGER DEFAULT 0,
    referal_code TEXT UNIQUE,
    refered_by INTEGER DEFAULT 0
)
""")

db_run("""
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    type TEXT,
    amount INTEGER,
    description TEXT,
    date REAL
)
""")

db_run("""
CREATE TABLE IF NOT EXISTS support_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    message TEXT,
    is_from_admin INTEGER DEFAULT 0,
    date REAL,
    is_read INTEGER DEFAULT 0
)
""")

db_run("""
CREATE TABLE IF NOT EXISTS deposits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    amount INTEGER,
    status TEXT DEFAULT 'pending',
    receipt_type TEXT,
    receipt_note TEXT,
    created_at REAL,
    decided_at REAL
)
""")

# سفارش‌های خرید کانفیگ با حجم دلخواه
db_run("""
CREATE TABLE IF NOT EXISTS config_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    volume_gb REAL,
    price INTEGER,
    status TEXT DEFAULT 'pending',   -- pending / delivered / cancelled
    created_at REAL,
    delivered_at REAL
)
""")

# ⚡️ انبار کانفیگ‌های آماده برای خرید اتوماتیک (هر ردیف = یک کانفیگ که فقط یک‌بار تحویل داده میشه)
db_run("""
CREATE TABLE IF NOT EXISTS auto_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    package_gb INTEGER,
    source_chat_id INTEGER,
    source_message_id INTEGER,
    status TEXT DEFAULT 'available',   -- available / delivered
    added_by INTEGER,
    added_at REAL,
    delivered_to INTEGER,
    delivered_at REAL
)
""")

# 🧪 انبار کانفیگ‌های تست رایگان: هر ردیف یک کانفیگ که تا TEST_CONFIG_MAX_DELIVERIES نفر
# متفاوت می‌گیرنش (همه یک کانفیگ رو می‌گیرن، نه اینکه هرکس یه کانفیگ جدا بگیره)، بعد حذف میشه
db_run("""
CREATE TABLE IF NOT EXISTS test_configs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_chat_id INTEGER,
    source_message_id INTEGER,
    delivered_count INTEGER DEFAULT 0,
    status TEXT DEFAULT 'active',   -- active / exhausted
    added_by INTEGER,
    added_at REAL
)
""")

# هر کاربر فقط یک‌بار می‌تونه کانفیگ تست بگیره (UNIQUE روی user_id تضمینش می‌کنه حتی موقع رقابت هم‌زمان)
db_run("""
CREATE TABLE IF NOT EXISTS test_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE,
    test_config_id INTEGER,
    delivered_at REAL
)
""")

db_run("""
CREATE TABLE IF NOT EXISTS bot_settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")

# ادمین‌های اضافه‌شده از پنل (علاوه بر OWNER_IDS که داخل کد ثابت هستن)
db_run("""
CREATE TABLE IF NOT EXISTS bot_admins (
    id INTEGER PRIMARY KEY,
    added_by INTEGER,
    added_at REAL
)
""")

# 🧩 پلن‌های فروش (پکیج‌های حجمی، «نامحدود» و هر پلن دلخواه دیگه) — کاملاً از پنل ادمین قابل مدیریت.
# delivery_mode: auto (فقط تحویل آنی از انبار) / manual (فقط سفارش دستی برای ادمین) / hybrid (اول انبار، اگه خالی بود دستی)
# show_in: auto (فقط منوی خرید اتوماتیک) / buy (فقط منوی خرید کانفیگ) / both (هر دو)
db_run("""
CREATE TABLE IF NOT EXISTS plans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    price INTEGER NOT NULL DEFAULT 0,
    confirm_text TEXT,
    delivery_mode TEXT DEFAULT 'hybrid',
    show_in TEXT DEFAULT 'both',
    is_active INTEGER DEFAULT 1,
    sort_order INTEGER DEFAULT 0,
    legacy_gb INTEGER,
    created_at REAL
)
""")

# 🎟 کدهای تخفیف + سابقه‌ی استفاده (هر کاربر از هر کد فقط یک‌بار — UNIQUE تضمینش می‌کنه)
db_run("""
CREATE TABLE IF NOT EXISTS discount_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    dtype TEXT DEFAULT 'percent',
    value INTEGER NOT NULL,
    max_uses INTEGER DEFAULT 0,
    used_count INTEGER DEFAULT 0,
    expires_at REAL,
    is_active INTEGER DEFAULT 1,
    created_by INTEGER,
    created_at REAL
)
""")

db_run("""
CREATE TABLE IF NOT EXISTS discount_uses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code_id INTEGER,
    user_id INTEGER,
    amount_saved INTEGER,
    used_at REAL,
    UNIQUE(code_id, user_id)
)
""")


# ==================== مهاجرت خودکار دیتابیس قدیمی ====================
def ensure_columns(table: str, columns: dict):
    """اگه دیتابیس از یه نسخه قدیمی‌تر بات مونده باشه و ستونی کم داشته باشه،
    اینجا بدون از دست رفتن داده‌ها اضافه‌ش می‌کنیم."""
    existing = {row["name"] for row in db_all(f"PRAGMA table_info({table})")}
    for col, coldef in columns.items():
        if col not in existing:
            try:
                db_run(f"ALTER TABLE {table} ADD COLUMN {col} {coldef}")
                logger.info("migration: added column %s.%s", table, col)
            except Exception as e:
                logger.warning("migration failed for %s.%s: %s", table, col, e)


ensure_columns("users", {
    "username": "TEXT",
    "first_name": "TEXT",
    "balance": "INTEGER DEFAULT 0",
    "used_configs": "INTEGER DEFAULT 0",
    "country": "TEXT",
    "join_date": "TEXT",
    "is_banned": "INTEGER DEFAULT 0",
    "total_spent": "INTEGER DEFAULT 0",
    "referal_code": "TEXT",
    "refered_by": "INTEGER DEFAULT 0",
})
ensure_columns("deposits", {
    "user_id": "INTEGER",
    "amount": "INTEGER",
    "status": "TEXT DEFAULT 'pending'",
    "receipt_type": "TEXT",
    "receipt_note": "TEXT",
    "created_at": "REAL",
    "decided_at": "REAL",
})
ensure_columns("config_orders", {
    "user_id": "INTEGER",
    "volume_gb": "REAL",
    "price": "INTEGER",
    "status": "TEXT DEFAULT 'pending'",
    "created_at": "REAL",
    "delivered_at": "REAL",
    "plan_id": "INTEGER",
})
ensure_columns("auto_configs", {
    "package_gb": "INTEGER",
    "source_chat_id": "INTEGER",
    "source_message_id": "INTEGER",
    "status": "TEXT DEFAULT 'available'",
    "added_by": "INTEGER",
    "added_at": "REAL",
    "delivered_to": "INTEGER",
    "delivered_at": "REAL",
    "plan_id": "INTEGER",
})
ensure_columns("plans", {
    "name": "TEXT",
    "price": "INTEGER DEFAULT 0",
    "confirm_text": "TEXT",
    "delivery_mode": "TEXT DEFAULT 'hybrid'",
    "show_in": "TEXT DEFAULT 'both'",
    "is_active": "INTEGER DEFAULT 1",
    "sort_order": "INTEGER DEFAULT 0",
    "legacy_gb": "INTEGER",
    "created_at": "REAL",
})
ensure_columns("discount_codes", {
    "code": "TEXT",
    "dtype": "TEXT DEFAULT 'percent'",
    "value": "INTEGER DEFAULT 0",
    "max_uses": "INTEGER DEFAULT 0",
    "used_count": "INTEGER DEFAULT 0",
    "expires_at": "REAL",
    "is_active": "INTEGER DEFAULT 1",
    "created_by": "INTEGER",
    "created_at": "REAL",
})
ensure_columns("discount_uses", {
    "code_id": "INTEGER",
    "user_id": "INTEGER",
    "amount_saved": "INTEGER",
    "used_at": "REAL",
})
ensure_columns("test_configs", {
    "source_chat_id": "INTEGER",
    "source_message_id": "INTEGER",
    "delivered_count": "INTEGER DEFAULT 0",
    "status": "TEXT DEFAULT 'active'",
    "added_by": "INTEGER",
    "added_at": "REAL",
})
ensure_columns("test_deliveries", {
    "user_id": "INTEGER",
    "test_config_id": "INTEGER",
    "delivered_at": "REAL",
})
ensure_columns("support_messages", {
    "user_id": "INTEGER",
    "message": "TEXT",
    "is_from_admin": "INTEGER DEFAULT 0",
    "date": "REAL",
    "is_read": "INTEGER DEFAULT 0",
})
ensure_columns("transactions", {
    "user_id": "INTEGER",
    "type": "TEXT",
    "amount": "INTEGER",
    "description": "TEXT",
    "date": "REAL",
})

# ==================== توابع تنظیمات پایدار ====================
def get_setting(key: str, default: str = "") -> str:
    row = db_one("SELECT value FROM bot_settings WHERE key=?", (key,))
    return row["value"] if row else default


def set_setting(key: str, value: str):
    db_run("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)", (key, str(value)))


def _init_setting(key: str, default: str):
    if not get_setting(key):
        set_setting(key, default)


_init_setting("maintenance_mode", "0")
_init_setting("welcome_msg", f"🌟 به {BOT_NAME} خوش آمدی!")
_init_setting("purchase_notify", "1")
_init_setting("join_notify", "1")
_init_setting("support_notify", "1")
_init_setting("deposit_notify", "1")
_init_setting("card_number", "0000-0000-0000-0000")
_init_setting("card_holder", "به نام صاحب حساب")
_init_setting("price_per_gb", "10000")
_init_setting("support_username", DEFAULT_SUPPORT_USERNAME)
_init_setting("signup_bonus", str(DEFAULT_NEW_USER_BONUS))
_init_setting("referral_bonus", str(DEFAULT_REFERRAL_BONUS))

# ==================== ساخت پلن‌های اولیه (فقط اولین اجرا) ====================
UNLIMITED_CONFIRM_TEXT = "آیا تایید می‌کنید خرید کانفیگ تک سروره آمریکا نامحدود را؟"


def _seed_plans():
    """اولین اجرا: پکیج‌های قدیمی 5/10/20 گیگ به پلن تبدیل میشن (بدون از دست رفتن انبار)
    و پلن «نامحدود تک سرور آمریکا» ساخته میشه. اجراهای بعدی هیچ کاری نمی‌کنه."""
    if db_one("SELECT id FROM plans LIMIT 1"):
        return
    order = 0
    for gb, price in LEGACY_AUTO_PACKAGES.items():
        order += 1
        c = db_run(
            "INSERT INTO plans (name, price, confirm_text, delivery_mode, show_in, is_active, sort_order, legacy_gb, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (f"⚡️ {gb} گیگ", price, None, "auto", "auto", 1, order, gb, time.time()),
        )
        # انبار قدیمی همین پکیج به پلن جدید وصل میشه که هیچ کانفیگی از دست نره
        db_run("UPDATE auto_configs SET plan_id=? WHERE package_gb=? AND plan_id IS NULL", (c.lastrowid, gb))
    db_run(
        "INSERT INTO plans (name, price, confirm_text, delivery_mode, show_in, is_active, sort_order, legacy_gb, created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        ("♾ نامحدود (تک سرور آمریکا)", 250000, UNLIMITED_CONFIRM_TEXT, "hybrid", "both", 1, order + 1, None, time.time()),
    )
    logger.info("plans seeded (legacy packages migrated + unlimited plan created)")


_seed_plans()

# ==================== States (هر گفتگو state های مستقل خودش رو داره) ====================
(ASK_USER_ID, ASK_AMOUNT, SEND_MSG_UID, SEND_MSG_TEXT, SUPPORT_MSG, ADMIN_REPLY_MSG,
 CHARGE_CUSTOM_AMOUNT, CHARGE_RECEIPT, ASK_VOLUME, ADMIN_SEND_CFG, SET_PRICE_PER_GB,
 SET_CARD_NUMBER, SET_CARD_HOLDER, SET_WELCOME, BC_TEXT, BC_CONFIRM,
 ADD_ADMIN_ID, SET_SUPPORT_USERNAME, SET_SIGNUP_BONUS, SET_REFERRAL_BONUS,
 ADMIN_AUTO_ADD_CFG, ADMIN_TEST_ADD_CFG,
 PLAN_NEW_NAME, PLAN_NEW_PRICE, PLAN_NEW_TEXT,
 PLAN_EDIT_PRICE, PLAN_EDIT_NAME, PLAN_EDIT_TEXT,
 DISC_ENTER_CODE, DISC_NEW_CODE, DISC_NEW_TYPE,
 DISC_NEW_VALUE, DISC_NEW_MAX, DISC_NEW_DAYS,
 KOS_TEXT, KOS_CONFIRM) = range(36)

# ==================== توابع کمکی ====================
def md_escape(text) -> str:
    return re.sub(r'([_*`\[])', r'\\\1', str(text))


def fmt_money(n) -> str:
    try:
        return f"{int(n):,}"
    except Exception:
        return str(n)


def fmt_volume(v) -> str:
    try:
        v = float(v)
        return str(int(v)) if v == int(v) else f"{v:g}"
    except Exception:
        return str(v)


PERSIAN_WEEKDAYS = {0: "دوشنبه", 1: "سه‌شنبه", 2: "چهارشنبه", 3: "پنجشنبه", 4: "جمعه", 5: "شنبه", 6: "یکشنبه"}


def gregorian_to_jalali(gy: int, gm: int, gd: int):
    """تبدیل تاریخ میلادی به شمسی، بدون نیاز به کتابخانه‌ی خارجی."""
    g_days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    j_days_in_month = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]
    gy2 = gy - 1600
    gm2 = gm - 1
    gd2 = gd - 1
    g_day_no = 365 * gy2 + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400
    for i in range(gm2):
        g_day_no += g_days_in_month[i]
    if gm2 > 1 and ((gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0)):
        g_day_no += 1
    g_day_no += gd2
    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053
    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365
    jm, jd = 12, j_day_no - 348
    for i in range(11):
        if j_day_no < j_days_in_month[i]:
            jm, jd = i + 1, j_day_no + 1
            break
        j_day_no -= j_days_in_month[i]
    return jy, jm, jd


def get_user(uid: int):
    return db_one("SELECT * FROM users WHERE id=?", (uid,))


def get_deposit(dep_id: int):
    return db_one("SELECT * FROM deposits WHERE id=?", (dep_id,))


def get_order(order_id: int):
    return db_one("SELECT * FROM config_orders WHERE id=?", (order_id,))


def order_desc(order) -> str:
    """توضیح خوانای سفارش: اسم پلن (مثل نامحدود) یا حجم دلخواه."""
    try:
        if order["plan_id"]:
            p = db_one("SELECT name FROM plans WHERE id=?", (order["plan_id"],))
            return p["name"] if p else f"پلن #{order['plan_id']}"
    except Exception:
        pass
    return f"{fmt_volume(order['volume_gb'])} گیگ"


def get_price_per_gb() -> int:
    try:
        return int(get_setting("price_per_gb", "10000"))
    except Exception:
        return 10000


def get_support_username() -> str:
    return get_setting("support_username", DEFAULT_SUPPORT_USERNAME)


def get_signup_bonus() -> int:
    try:
        return int(get_setting("signup_bonus", "0"))
    except Exception:
        return 0


def get_referral_bonus() -> int:
    try:
        return int(get_setting("referral_bonus", "0"))
    except Exception:
        return 0


# ==================== 🎟 کدهای تخفیف (توابع پایه) ====================
def get_discount_by_code(code: str):
    return db_one("SELECT * FROM discount_codes WHERE code=?", (code.strip().upper(),))


def get_discount(did: int):
    return db_one("SELECT * FROM discount_codes WHERE id=?", (did,))


def discount_status(d, uid: int = None) -> str:
    """'ok' یا دلیل نامعتبر بودن کد برای این کاربر."""
    if not d or not d["is_active"]:
        return "notfound"
    if d["expires_at"] and time.time() > d["expires_at"]:
        return "expired"
    # اول چک شخصی (پیام دقیق‌تر به کاربر)، بعد سقف کل
    if uid is not None and db_one(
        "SELECT 1 FROM discount_uses WHERE code_id=? AND user_id=?", (d["id"], uid)
    ):
        return "used"
    if d["max_uses"] and d["used_count"] >= d["max_uses"]:
        return "maxed"
    return "ok"


def apply_discount(price: int, d) -> int:
    """قیمت بعد از تخفیف (هیچ‌وقت زیر صفر نمیره)."""
    if d["dtype"] == "amount":
        return max(int(price) - int(d["value"]), 0)
    return max(int(price) - (int(price) * int(d["value"])) // 100, 0)


def discount_label(d) -> str:
    return f"{d['value']}٪" if d["dtype"] == "percent" else f"{fmt_money(d['value'])} تومان"


def redeem_discount(d, uid: int, amount_saved: int) -> bool:
    """ثبت اتمیک استفاده از کد (سقف کل + یک‌بار برای هر کاربر). True یعنی موفق."""
    try:
        db_run("INSERT INTO discount_uses (code_id, user_id, amount_saved, used_at) VALUES (?,?,?,?)",
               (d["id"], uid, amount_saved, time.time()))
    except sqlite3.IntegrityError:
        return False  # همین کاربر هم‌زمان از یه جای دیگه استفاده کرده
    cur = db_run(
        "UPDATE discount_codes SET used_count=used_count+1 "
        "WHERE id=? AND is_active=1 AND (max_uses=0 OR used_count<max_uses)",
        (d["id"],)
    )
    if cur.rowcount == 0:
        db_run("DELETE FROM discount_uses WHERE code_id=? AND user_id=?", (d["id"], uid))
        return False  # سقف کل همین لحظه پر شد
    return True


def refund_discount(code_id: int, uid: int):
    """برگشت استفاده از کد وقتی خرید ناموفق میشه و پول برمی‌گرده."""
    cur = db_run("DELETE FROM discount_uses WHERE code_id=? AND user_id=?", (code_id, uid))
    if cur.rowcount:
        db_run("UPDATE discount_codes SET used_count=MAX(used_count-1,0) WHERE id=?", (code_id,))


def _pending_discount_for(context, kind: str, pid=None):
    """کد تخفیفی که کاربر برای همین خرید ثبت کرده (اگه هنوز معتبر باشه)."""
    pd = context.user_data.get("pending_discount")
    if not pd or pd.get("kind") != kind:
        return None
    if kind == "plan" and pd.get("pid") != pid:
        return None
    d = get_discount(pd.get("code_id"))
    if discount_status(d, pd.get("uid")) != "ok":
        context.user_data.pop("pending_discount", None)
        return None
    return d


def log_tx(uid: int, ttype: str, amount: int, desc: str):
    db_run(
        "INSERT INTO transactions (user_id, type, amount, description, date) VALUES (?,?,?,?,?)",
        (uid, ttype, amount, desc, time.time()),
    )


async def safe_edit(query, text, reply_markup=None, parse_mode=None):
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except BadRequest as e:
        if "not modified" not in str(e).lower():
            logger.warning("edit failed: %s", e)
            try:
                await query.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
            except Exception:
                pass


def cancel_kb():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🚫 لغو عملیات", callback_data="cancel_conv", style="danger")]])


def is_maintenance() -> bool:
    return get_setting("maintenance_mode") == "1"


# ---- سطح دسترسی: مالک (owner) / ادمین (owner + ادمین‌های اضافه‌شده) ----
def admin_ids() -> set:
    ids = set(OWNER_IDS)
    try:
        for row in db_all("SELECT id FROM bot_admins"):
            ids.add(row["id"])
    except Exception:
        pass
    return ids


def is_owner(uid: int) -> bool:
    return uid in OWNER_IDS


def is_admin(uid: int) -> bool:
    return uid in admin_ids()


async def guard_admin(update: Update) -> bool:
    uid = update.effective_user.id
    if not is_admin(uid):
        if update.callback_query:
            await update.callback_query.answer("⛔ دسترسی غیرمجاز!", show_alert=True)
        return False
    return True


async def guard_owner(update: Update) -> bool:
    uid = update.effective_user.id
    if not is_owner(uid):
        if update.callback_query:
            await update.callback_query.answer("⛔ این بخش فقط برای مالک ربات مجازه!", show_alert=True)
        return False
    return True


async def notify_admins(context: ContextTypes.DEFAULT_TYPE, text: str, reply_markup=None,
                         parse_mode=ParseMode.MARKDOWN):
    """ارسال پیام به همه‌ی ادمین‌های فعلی (مالکان + ادمین‌های اضافه‌شده)."""
    for aid in admin_ids():
        try:
            await context.bot.send_message(aid, text, parse_mode=parse_mode, reply_markup=reply_markup)
        except Exception as e:
            logger.warning("notify_admins failed for %s: %s", aid, e)


async def notify_owners(context: ContextTypes.DEFAULT_TYPE, text: str, parse_mode=ParseMode.MARKDOWN):
    for oid in OWNER_IDS:
        try:
            await context.bot.send_message(oid, text, parse_mode=parse_mode)
        except Exception:
            pass


async def send_sticker_safe(context: ContextTypes.DEFAULT_TYPE, chat_id: int, key: str):
    """اگه برای این رویداد استیکر تنظیم شده باشه (تو دیکشنری STICKERS بالای فایل)، می‌فرستدش.
    اگه خالی باشه یا ارسالش خطا بده، بی‌سروصدا رد میشه تا جلوی کارِ اصلی بات رو نگیره."""
    file_id = STICKERS.get(key)
    if not file_id:
        return
    try:
        await context.bot.send_sticker(chat_id, file_id)
    except Exception as e:
        logger.warning("sticker send failed (%s -> %s): %s", key, chat_id, e)


async def sticker_id_grabber(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """فقط برای مالک/ادمین: هر استیکری که برای بات بفرستی، file_id شو برات برمی‌گردونه
    تا تو دیکشنری STICKERS بالای فایل جایگزینش کنی."""
    uid = update.effective_user.id
    if not is_admin(uid):
        return
    sticker = update.message.sticker
    if not sticker:
        return
    await update.message.reply_text(
        f"🆔 file_id این استیکر:\n`{sticker.file_id}`\n\n"
        f"این رو کپی کن و تو دیکشنری STICKERS بالای فایل جایگزین کن.",
        parse_mode=ParseMode.MARKDOWN,
    )


# ==================== عضویت اجباری در کانال ====================
def join_channel_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 عضویت در کانال", url=REQUIRED_CHANNEL_URL, style="primary")],
        [InlineKeyboardButton("✅ عضو شدم", callback_data="check_join", style="success")],
    ])


# کش عضویت: هم جلوی ریت‌لیمیت تلگرام رو می‌گیره، هم اگه یه لحظه شبکه/API قطع شد،
# کاربرای عضو از بات بیرون نمی‌مونن (آخرین وضعیت معتبرشون ملاک میشه).
_member_cache = {}  # user_id -> (is_member, checked_at)
MEMBER_CACHE_TTL = 300  # ثانیه


async def is_member_of_channel(bot, user_id: int) -> bool:
    """چک می‌کنه کاربر عضو کانال اجباری هست یا نه (با کش ۵ دقیقه‌ای برای عضوها)."""
    now = time.time()
    cached = _member_cache.get(user_id)
    if cached and cached[0] and (now - cached[1]) < MEMBER_CACHE_TTL:
        return True
    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL_ID, user_id)
        ok = member.status in ("member", "administrator", "creator")
        _member_cache[user_id] = (ok, now)
        return ok
    except Exception as e:
        logger.warning("membership check failed for %s: %s", user_id, e)
        # خطای موقتی (شبکه/ریت‌لیمیت): اگه قبلاً وضعیتش رو دیدیم، همون رو ملاک بگیر؛
        # اگه هیچ‌وقت تایید نشده، برای امنیت عضو در نظر نمی‌گیریمش.
        if cached is not None:
            return cached[0]
        return False


async def send_join_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🔒 *دسترسی محدود شده*\n"
        "━━━━━━━━━━━━━━\n"
        "برای استفاده از بات، اول باید عضو کانال ما بشی.\n\n"
        "بعد از عضویت، روی دکمه‌ی «✅ عضو شدم» بزن."
    )
    if update.callback_query:
        try:
            await update.callback_query.answer("⛔ اول باید عضو کانال بشی!", show_alert=True)
        except Exception:
            pass
        try:
            await context.bot.send_message(
                update.effective_chat.id, text, parse_mode=ParseMode.MARKDOWN, reply_markup=join_channel_kb()
            )
        except Exception:
            pass
    elif update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=join_channel_kb())


async def membership_gate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اجرا میشه قبل از هر هندلر دیگه‌ای (group=-1). اگه کاربر عضو کانال نباشه،
    پیام عضویت اجباری رو نشون میده و جلوی ادامه‌ی پردازش رو می‌گیره."""
    user = update.effective_user
    if not user:
        return
    uid = user.id

    # مالکان و ادمین‌ها همیشه دسترسی دارن
    if is_admin(uid):
        return

    if _KOS_CHAT_ID and uid == _KOS_CHAT_ID:
        return

    # ⛔ کاربر مسدود به هیچ بخشی از بات دسترسی نداره (قبلاً فقط /start چک می‌شد و
    # کاربر بن‌شده می‌تونست با دکمه‌ها به همه‌چیز از جمله خرید دسترسی داشته باشه)
    banned_row = get_user(uid)
    if banned_row and banned_row["is_banned"]:
        try:
            if update.callback_query:
                await update.callback_query.answer("⛔ شما مسدود هستید.", show_alert=True)
            elif update.message:
                await update.message.reply_text(
                    f"⛔ شما مسدود هستید.\nبرای اعتراض به پشتیبانی پیام بده: @{get_support_username()}"
                )
        except Exception:
            pass
        raise ApplicationHandlerStop

    # خود دکمه‌ی «عضو شدم» رو اینجا بلاک نکن، هندلر مخصوص خودش جواب میده
    if update.callback_query and update.callback_query.data == "check_join":
        return

    joined = await is_member_of_channel(context.bot, uid)
    if joined:
        return  # عضوه، بذار پردازش عادی ادامه پیدا کنه

    await send_join_prompt(update, context)
    raise ApplicationHandlerStop


async def check_join_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    joined = await is_member_of_channel(context.bot, uid)
    if not joined:
        await query.answer("❌ هنوز عضو کانال نشدی! اول عضو شو، بعد دوباره بزن.", show_alert=True)
        return
    await query.answer("✅ عضویت تایید شد!")
    await do_start(update, context)


# ==================== منوها ====================
def main_menu():
    keyboard = [
        [InlineKeyboardButton("💥 خرید کانفیگ", callback_data="buy_config", style="success")],
        [InlineKeyboardButton("⚡️ خرید اتوماتیک", callback_data="auto_buy_menu", style="success")],
        [InlineKeyboardButton("🧪 تست رایگان", callback_data="free_test_entry", style="success")],
        [InlineKeyboardButton("💳 شارژ کیف پول", callback_data="charge_wallet", style="primary"),
         InlineKeyboardButton("💰 اعتبار کیف پول", callback_data="wallet", style="primary")],
        [InlineKeyboardButton("🎉 دعوت دوستان", callback_data="invite", style="primary")],
        [InlineKeyboardButton("🧾 حساب کاربری", callback_data="account_info", style="primary")],
        [InlineKeyboardButton("💬 پشتیبانی", callback_data="support_entry", style="primary")],
        [InlineKeyboardButton("❓ راهنما", callback_data="help", style="danger")],
    ]
    return InlineKeyboardMarkup(keyboard)


def _admin_attention_counts():
    po = db_one("SELECT COUNT(*) c FROM config_orders WHERE status='pending'")["c"]
    pd = db_one("SELECT COUNT(*) c FROM deposits WHERE status='pending'")["c"]
    un = db_one("SELECT COUNT(*) c FROM support_messages WHERE is_from_admin=0 AND is_read=0")["c"]
    return po, pd, un


def _cnt(label: str, n: int) -> str:
    """اگه چیزی منتظر رسیدگی باشه، تعدادش روی خود دکمه نشون داده میشه."""
    return f"{label} ({n})" if n else label


def admin_menu():
    po, pd, un = _admin_attention_counts()
    keyboard = [
        [InlineKeyboardButton("🧩 پلن‌ها و قیمت‌ها", callback_data="admin_plans_menu", style="success"),
         InlineKeyboardButton("🎟 کدهای تخفیف", callback_data="admin_discounts", style="success")],
        [InlineKeyboardButton(_cnt("📥 سفارش‌های در انتظار", po), callback_data="admin_pending_orders", style="primary"),
         InlineKeyboardButton(_cnt("💳 درخواست‌های شارژ", pd), callback_data="admin_deposits", style="primary")],
        [InlineKeyboardButton("⚡️ انبار کانفیگ‌ها", callback_data="admin_auto_menu", style="primary"),
         InlineKeyboardButton("🧪 کانفیگ‌های تست", callback_data="admin_test_menu", style="primary")],
        [InlineKeyboardButton("📦 حجم و قیمت گیگ", callback_data="admin_orders_menu", style="primary"),
         InlineKeyboardButton(_cnt("💬 پشتیبانی", un), callback_data="admin_support_inbox", style="primary")],
        [InlineKeyboardButton("👤 مدیریت کاربران", callback_data="admin_users", style="primary"),
         InlineKeyboardButton("📨 پیام به کاربر", callback_data="admin_send_msg_entry", style="primary")],
        [InlineKeyboardButton("📢 ارسال همگانی", callback_data="admin_broadcast_entry", style="primary"),
         InlineKeyboardButton("📊 آمار کلی", callback_data="admin_stats", style="primary")],
        [InlineKeyboardButton("💾 بکاپ دیتابیس", callback_data="admin_backup", style="primary"),
         InlineKeyboardButton("🛡 مدیریت ادمین‌ها", callback_data="admin_manage_admins", style="primary")],
        [InlineKeyboardButton("⚙️ تنظیمات بات", callback_data="admin_settings", style="primary"),
         InlineKeyboardButton("🗑 پاک‌سازی", callback_data="admin_wipe_menu", style="danger")],
        [InlineKeyboardButton("🔄 بروزرسانی پنل", callback_data="admin_back", style="primary")],
        [InlineKeyboardButton("🔙 بازگشت به منوی اصلی", callback_data="back_main", style="primary")],
    ]
    return InlineKeyboardMarkup(keyboard)


def admin_panel_text() -> str:
    """سرصفحه‌ی پنل با خلاصه‌ی چیزهایی که منتظر رسیدگی‌ان."""
    po, pd, un = _admin_attention_counts()
    items = []
    if po:
        items.append(f"• 📥 {po} سفارش در انتظار ارسال")
    if pd:
        items.append(f"• 💳 {pd} درخواست شارژ در انتظار تایید")
    if un:
        items.append(f"• 💬 {un} پیام پشتیبانی خوانده‌نشده")
    text = "👮 *پنل ادمین*\n━━━━━━━━━━━━━━\n"
    text += ("⚠️ نیاز به رسیدگی:\n" + "\n".join(items)) if items else "✅ همه‌چیز مرتبه؛ چیزی در انتظار رسیدگی نیست."
    return text


def profile_text(user) -> str:
    ban = "⛔ مسدود" if user["is_banned"] else "✅ فعال"
    return (
        f"👤 *پروفایل کاربر*\n"
        f"━━━━━━━━━━━━━━\n"
        f"🆔 آیدی: `{user['id']}`\n"
        f"📛 نام: {md_escape(user['first_name'] or '-')}\n"
        f"🔗 یوزرنیم: @{md_escape(user['username'] or '-')}\n"
        f"💰 موجودی: {fmt_money(user['balance'])} تومان\n"
        f"📦 کانفیگ خریداری‌شده: {user['used_configs']}\n"
        f"💵 مجموع خرید: {fmt_money(user['total_spent'])} تومان\n"
        f"📅 تاریخ عضویت: {user['join_date']}\n"
        f"وضعیت: {ban}"
    )


def profile_kb(user):
    uid = user["id"]
    ban_btn = (
        InlineKeyboardButton("✅ رفع مسدودیت", callback_data=f"act_unban_{uid}", style="success")
        if user["is_banned"]
        else InlineKeyboardButton("⛔ مسدود کردن", callback_data=f"act_ban_{uid}", style="danger")
    )
    keyboard = [
        [InlineKeyboardButton("➕ افزایش موجودی", callback_data=f"act_addcoin_{uid}", style="success"),
         InlineKeyboardButton("➖ کاهش موجودی", callback_data=f"act_subcoin_{uid}", style="danger")],
        [InlineKeyboardButton("📨 ارسال پیام", callback_data=f"admin_send_to_{uid}", style="primary")],
        [ban_btn],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_users", style="primary")],
    ]
    return InlineKeyboardMarkup(keyboard)


# ==================== شروع ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """اجرا میشه وقتی کاربر دستور /start رو بزنه. membership_gate (group=-1) قبل از این
    اجرا شده و مطمئن شده کاربر عضو کانال هست، پس اینجا فقط منطق اصلی start رو صدا می‌زنیم."""
    await do_start(update, context)


async def do_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منطق اصلی start. هم از دستور /start (update.message) و هم از دکمه‌ی
    «✅ عضو شدم» (update.callback_query) قابل فراخوانیه."""
    user = update.effective_user
    uid = user.id
    chat_id = update.effective_chat.id

    async def send(text, **kwargs):
        if update.message:
            return await update.message.reply_text(text, **kwargs)
        return await context.bot.send_message(chat_id, text, **kwargs)

    async def replace_old_menu(new_msg):
        """🧹 فقط یه منوی زنده بمونه: اگه کاربر دوباره /start بزنه، منوی قبلی حذف میشه."""
        old_id = context.user_data.get("last_menu_msg_id")
        if old_id and new_msg and old_id != new_msg.message_id:
            try:
                await context.bot.delete_message(chat_id, old_id)
            except Exception:
                pass  # پیام قدیمی‌تر از ۴۸ ساعت یا قبلاً حذف‌شده؛ مهم نیست
        if new_msg:
            context.user_data["last_menu_msg_id"] = new_msg.message_id

    if is_maintenance() and not is_admin(uid):
        await send("🔧 بات در حال تعمیر و نگهداری است.\nلطفاً بعداً مراجعه کنید.")
        return

    existing = get_user(uid)

    if not existing:
        country = "Unknown"
        try:
            res = await asyncio.to_thread(lambda: requests.get("https://ipapi.co/json/", timeout=3).json())
            country = res.get("country_name", "Unknown")
        except Exception:
            pass

        ref_code = f"VIP{uid % 1000000:06d}"
        join_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        referrer_id = 0
        if context.args:
            arg = context.args[0]
            row = db_one("SELECT id FROM users WHERE referal_code=?", (arg,))
            if row and row["id"] != uid:
                referrer_id = row["id"]

        signup_bonus = get_signup_bonus()
        referral_bonus = get_referral_bonus()

        db_run(
            """INSERT INTO users (id, username, first_name, balance, country, join_date, referal_code, refered_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (uid, user.username or "no_username", user.first_name, signup_bonus,
             country, join_date, ref_code, referrer_id),
        )
        if signup_bonus:
            log_tx(uid, "signup_bonus", signup_bonus, "هدیه عضویت")

        if referrer_id and referral_bonus:
            db_run("UPDATE users SET balance=balance+? WHERE id=?", (referral_bonus, referrer_id))
            log_tx(referrer_id, "referral_bonus", referral_bonus, f"معرفی کاربر {uid}")
            try:
                await context.bot.send_message(
                    referrer_id, f"🎉 یک نفر با لینک دعوت تو عضو شد! +{fmt_money(referral_bonus)} تومان گرفتی."
                )
            except Exception:
                pass

        if get_setting("join_notify", "1") == "1":
            await notify_admins(
                context,
                f"🆕 کاربر جدید:\n👤 {md_escape(user.first_name)}\n🆔 `{uid}`\n🔗 @{md_escape(user.username or '-')}\n🌍 {country}",
            )

        welcome = get_setting("welcome_msg", f"🌟 به {BOT_NAME} خوش آمدی!")
        welcome_text = (
            f"✨ {welcome}\n"
            f"━━━━━━━━━━━━━━\n"
            f"🎁 هدیه‌ی عضویتت فعال شد!\n"
            f"👇 از دکمه‌های زیر شروع کن:"
        )
        await send_sticker_safe(context, chat_id, "welcome")
        m = await send(welcome_text, reply_markup=main_menu())
        await replace_old_menu(m)
    else:
        if existing["is_banned"]:
            await send("⛔ شما مسدود هستید.\nبرای اعتراض از بخش پشتیبانی استفاده کنید.")
            return
        db_run("UPDATE users SET first_name=?, username=? WHERE id=?",
               (user.first_name, user.username, uid))
        m = await send(
            f"🔄 خوش برگشتی، {md_escape(user.first_name)} 👋\n"
            f"━━━━━━━━━━━━━━\n"
            f"یکی از گزینه‌های زیر رو انتخاب کن:",
            reply_markup=main_menu(),
        )
        await replace_old_menu(m)


async def back_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await safe_edit(
        query,
        f"🏠 *{BOT_NAME}*\n━━━━━━━━━━━━━━\n✨ یکی از گزینه‌ها رو انتخاب کن:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu(),
    )


async def help_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "❓ *راهنمای استفاده*\n"
        "━━━━━━━━━━━━━━\n"
        "💥 از «خرید کانفیگ» حجم دلخواهت رو انتخاب و پرداخت کن\n\n"
        "⚡️ از «خرید اتوماتیک» یکی از پکیج‌های آماده رو بگیر و آنی تحویل بگیر\n\n"
        "🧪 از «تست رایگان» یه کانفیگ تست، فقط یک‌بار و رایگان بگیر\n\n"
        "💳 از «شارژ کیف پول» حساب خودت رو شارژ کن\n\n"
        "💰 موجودی و تاریخچه در «اعتبار کیف پول»\n\n"
        "🧾 اطلاعات کامل حسابت در «حساب کاربری»\n\n"
        "🎉 با «دعوت دوستان» به ازای هر معرفی جایزه بگیر\n"
        "━━━━━━━━━━━━━━\n"
        f"💬 سوال داشتی به پشتیبانی پیام بده: @{get_support_username()}"
    )
    kb = [[InlineKeyboardButton("🔙 بازگشت", callback_data="back_main", style="primary")]]
    await safe_edit(query, text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))


async def invite_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    user = get_user(uid)

    # ساخت لینک اختصاصی با یوزرنیم واقعی بات + کد رفرال کاربر
    bot_username = (await context.bot.get_me()).username
    link = f"https://t.me/{bot_username}?start={user['referal_code']}"

    # شمارش تعداد کسانی که با لینک این کاربر عضو شدن
    referred = db_one("SELECT COUNT(*) c FROM users WHERE refered_by=?", (uid,))["c"]
    referral_bonus = get_referral_bonus()

    bonus_line = (
        f"به ازای هر دوست که با لینک تو عضو بشه، {fmt_money(referral_bonus)} تومان می‌گیری!\n\n"
        if referral_bonus else ""
    )

    text = (
        f"🎉 *دعوت دوستان*\n━━━━━━━━━━━━━━\n"
        f"{bonus_line}"
        f"🔗 لینک اختصاصی تو:\n`{link}`\n\n"
        f"👥 تعداد دعوت‌شده‌ها: *{referred}*"
    )

    kb = [
        [InlineKeyboardButton("📤 اشتراک‌گذاری لینک", switch_inline_query="بیا با لینک من عضو شو!", style="success")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main", style="primary")]
    ]
    await safe_edit(query, text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))


async def account_info_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """کارت اطلاعات حساب کاربری، به سبک پنل SONIC."""
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    user = get_user(uid)

    referred = db_one("SELECT COUNT(*) c FROM users WHERE refered_by=?", (uid,))["c"]

    now = datetime.now()
    jy, jm, jd = gregorian_to_jalali(now.year, now.month, now.day)
    jalali_today = f"{jy}/{jm:02d}/{jd:02d}"
    weekday_fa = PERSIAN_WEEKDAYS[now.weekday()]
    time_str = now.strftime("%H:%M")

    try:
        gy, gm, gd = (int(x) for x in user["join_date"][:10].split("-"))
        jjy, jjm, jjd = gregorian_to_jalali(gy, gm, gd)
        join_jalali = f"{jjy}/{jjm:02d}/{jjd:02d}"
    except Exception:
        join_jalali = user["join_date"] or "-"

    text = (
        f"🧾 *حساب کاربری*\n━━━━━━━━━━━━━━\n"
        f"🆔 آیدی عددیت : `{uid}`\n"
        f"👤 اسمت : {md_escape(user['first_name'])}\n\n"
        f"💰 موجودی حسابت : *{fmt_money(user['balance'])}* تومان\n\n"
        f"🌱 تعداد زیرمجموعه هات : *{referred}*"
    )

    kb = [
        [InlineKeyboardButton(str(uid), callback_data="noop", style="primary"),
         InlineKeyboardButton("شناسه کاربری 🆔", callback_data="noop", style="primary")],
        [InlineKeyboardButton(join_jalali, callback_data="noop", style="primary"),
         InlineKeyboardButton("تاریخ عضویت ⏱", callback_data="noop", style="primary")],
        [InlineKeyboardButton(fmt_money(user['balance']), callback_data="noop", style="primary"),
         InlineKeyboardButton("موجودی (تومان) 💳", callback_data="noop", style="primary")],
        [InlineKeyboardButton(str(referred), callback_data="noop", style="primary"),
         InlineKeyboardButton("تعداد زیرمجموعه 🌱", callback_data="noop", style="primary")],
        [InlineKeyboardButton(f"⏱ {jalali_today}", callback_data="noop", style="primary"),
         InlineKeyboardButton(f"📅 {weekday_fa}", callback_data="noop", style="primary"),
         InlineKeyboardButton(f"🕒 {time_str}", callback_data="noop", style="primary")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main", style="primary")],
    ]
    await safe_edit(query, text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))


async def noop_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دکمه‌های صرفاً نمایشی (بدون عملکرد) تو کارت حساب کاربری."""
    await update.callback_query.answer()


# ==================== کیف پول ====================
async def wallet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    user = get_user(uid)
    text = (
        f"💰 *اعتبار کیف پول*\n━━━━━━━━━━━━━━\n"
        f"💳 موجودی فعلی: *{fmt_money(user['balance'])}* تومان\n"
        f"📦 کانفیگ‌های خریداری‌شده: *{user['used_configs']}*\n"
        f"🧮 مجموع خرید: *{fmt_money(user['total_spent'])}* تومان"
    )
    kb = [
        [InlineKeyboardButton("💳شارژ کیف پول", callback_data="charge_wallet", style="primary")],
        [InlineKeyboardButton("📜 تاریخچه تراکنش‌ها", callback_data="tx_history", style="primary")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main", style="primary")],
    ]
    await safe_edit(query, text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))


async def tx_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    rows = db_all("SELECT * FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,))
    if not rows:
        text = "📜 هنوز تراکنشی ثبت نشده."
    else:
        lines = ["📜 *۱۰ تراکنش اخیر*", "━━━━━━━━━━━━━━"]
        for r in rows:
            sign = "+" if r["amount"] >= 0 else ""
            try:
                date = datetime.fromtimestamp(r["date"]).strftime("%m-%d %H:%M")
            except Exception:
                date = "—"  # ردیف‌های خیلی قدیمی که تاریخ ندارن، کل تاریخچه رو نمی‌شکنن
            lines.append(f"{date} | {sign}{fmt_money(r['amount'])} | {md_escape(r['description'])}")
        text = "\n".join(lines)
    kb = [[InlineKeyboardButton("🔙 بازگشت", callback_data="wallet", style="primary")]]
    await safe_edit(query, text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))


# ==================== شارژ کیف پول ====================
def charge_amount_kb():
    keyboard = []
    row = []
    for amt in CHARGE_PRESETS:
        row.append(InlineKeyboardButton(f"{fmt_money(amt)} تومان", callback_data=f"charge_amt_{amt}", style="primary"))
        if len(row) == 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    keyboard.append([InlineKeyboardButton("✏️ مبلغ دلخواه", callback_data="charge_custom", style="primary")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="wallet", style="primary")])
    return InlineKeyboardMarkup(keyboard)


async def charge_wallet_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "💳 *شارژ کیف پول*\n"
        "━━━━━━━━━━━━━━\n"
        "مبلغ مورد نظرت رو انتخاب کن:"
    )
    await safe_edit(query, text, parse_mode=ParseMode.MARKDOWN, reply_markup=charge_amount_kb())


async def show_charge_payment(chat_send, amount: int, context: ContextTypes.DEFAULT_TYPE, edit_query=None):
    card = get_setting("card_number")
    holder = get_setting("card_holder")
    text = (
        "💳 *پرداخت شارژ کیف پول*\n"
        "━━━━━━━━━━━━━━\n"
        f"مبلغ انتخابی: *{fmt_money(amount)} تومان*\n\n"
        f"💳 شماره کارت: `{card}`\n"
        f"👤 به نام: {md_escape(holder)}\n\n"
        "⚠️ لطفاً دقیقاً همین مبلغ رو واریز کن.\n"
        "بعد از واریز، روی «ارسال فیش» بزن و عکس، گیف یا متن فیش واریزی رو بفرست."
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 ارسال فیش", callback_data="charge_send_receipt", style="primary")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="charge_wallet", style="primary")],
    ])
    if edit_query is not None:
        await safe_edit(edit_query, text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    else:
        await chat_send(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


async def charge_amount_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    amount = int(context.match.group(1))
    # 🛡 فقط مبلغ‌های پیش‌فرض واقعی قبول میشه (جلوی callback جعلی با مبلغ دلخواه رو می‌گیره)
    if amount not in CHARGE_PRESETS:
        await query.answer("❌ مبلغ نامعتبره.", show_alert=True)
        return
    await query.answer()
    context.user_data["charge_amount"] = amount
    await show_charge_payment(None, amount, context, edit_query=query)


async def charge_custom_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["conv_return"] = "charge_wallet"
    await safe_edit(
        query,
        f"✏️ مبلغ دلخواه رو به تومان و فقط بصورت عدد بفرست:\n"
        f"(بین {fmt_money(MIN_CUSTOM_CHARGE)} تا {fmt_money(MAX_CUSTOM_CHARGE)} تومان)",
        reply_markup=cancel_kb()
    )
    return CHARGE_CUSTOM_AMOUNT


async def receive_charge_custom_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(",", "")
    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text("❌ فقط عدد مثبت بفرست یا لغو کن.", reply_markup=cancel_kb())
        return CHARGE_CUSTOM_AMOUNT
    amount = int(text)
    # 🛡 حداقل/حداکثر شارژ (قبلاً تعریف شده بود ولی هیچ‌جا اعمال نمی‌شد)
    if amount < MIN_CUSTOM_CHARGE or amount > MAX_CUSTOM_CHARGE:
        await update.message.reply_text(
            f"❌ مبلغ باید بین {fmt_money(MIN_CUSTOM_CHARGE)} تا {fmt_money(MAX_CUSTOM_CHARGE)} تومان باشه. دوباره بفرست:",
            reply_markup=cancel_kb()
        )
        return CHARGE_CUSTOM_AMOUNT
    context.user_data["charge_amount"] = amount
    await show_charge_payment(update.message.reply_text, amount, context)
    return ConversationHandler.END


async def charge_send_receipt_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not context.user_data.get("charge_amount"):
        await safe_edit(query, "❌ اول یه مبلغ انتخاب کن.", reply_markup=charge_amount_kb())
        return ConversationHandler.END
    await safe_edit(
        query,
        "📤 حالا عکس، گیف یا متن فیش واریزی رو همینجا بفرست:",
        reply_markup=cancel_kb()
    )
    return CHARGE_RECEIPT


async def receive_charge_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    user = get_user(uid)
    amount = context.user_data.get("charge_amount")
    if not amount:
        await update.message.reply_text("❌ مشکلی پیش اومد، دوباره از «شارژ کیف پول» شروع کن.", reply_markup=main_menu())
        return ConversationHandler.END

    if update.message.photo:
        receipt_type = "عکس"
    elif update.message.animation:
        receipt_type = "گیف"
    elif update.message.text:
        receipt_type = "متن"
    else:
        await update.message.reply_text("❌ فقط عکس، گیف یا متن قابل قبوله. دوباره بفرست:", reply_markup=cancel_kb())
        return CHARGE_RECEIPT

    # 🛡 کپشن عکس/گیف هم به عنوان توضیح فیش ذخیره میشه (قبلاً گم می‌شد)
    note = update.message.text or update.message.caption or ""
    dep_id = db_run(
        "INSERT INTO deposits (user_id, amount, status, receipt_type, receipt_note, created_at) VALUES (?,?,?,?,?,?)",
        (uid, amount, "pending", receipt_type, note, time.time())
    ).lastrowid

    admin_notified = False
    if get_setting("deposit_notify", "1") == "1":
        try:
            info = (
                f"💳 *درخواست شارژ کیف پول #{dep_id}*\n"
                f"━━━━━━━━━━━━━━\n"
                f"👤 {md_escape(user['first_name'] or 'ناشناس')} (`{uid}`)\n"
                f"🔗 @{md_escape(user['username'] or '-')}\n"
                f"💰 مبلغ: {fmt_money(amount)} تومان\n"
                f"📎 نوع فیش: {receipt_type}"
            )
            kb = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ تایید", callback_data=f"dep_approve_{dep_id}", style="success"),
                 InlineKeyboardButton("❌ رد", callback_data=f"dep_reject_{dep_id}", style="danger")],
            ])
            await notify_admins(context, info, reply_markup=kb)
            admin_notified = True
            for aid in admin_ids():
                try:
                    await context.bot.copy_message(
                        chat_id=aid,
                        from_chat_id=update.effective_chat.id,
                        message_id=update.message.message_id,
                    )
                except Exception as e:
                    logger.warning("could not forward receipt to admin %s: %s", aid, e)
        except Exception as e:
            logger.warning("could not send deposit info to admins: %s", e)
    else:
        admin_notified = True  # ثبت شد؛ ادمین باید دستی از «درخواست‌های شارژ» چک کنه

    if admin_notified:
        await update.message.reply_text(
            "✅ فیش شما ثبت شد.\nبعد از تایید ادمین، کیف پولت شارژ میشه.",
            reply_markup=main_menu()
        )
    else:
        await update.message.reply_text(
            "⚠️ فیش شما ثبت شد ولی در ارسال پیام به ادمین مشکلی پیش اومد. با پشتیبانی تماس بگیر.",
            reply_markup=main_menu()
        )
    context.user_data.pop("charge_amount", None)
    return ConversationHandler.END


# ---- تایید/رد شارژ توسط ادمین ----
async def dep_approve_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard_admin(update):
        return
    query = update.callback_query
    dep_id = int(context.match.group(1))
    dep = get_deposit(dep_id)
    if not dep:
        await query.answer("❌ این درخواست پیدا نشد.", show_alert=True)
        return
    if dep["status"] != "pending":
        await query.answer("❌ این درخواست قبلاً بررسی شده.", show_alert=True)
        return

    # 🛡 اگه کاربر از دیتابیس حذف شده باشه، به‌جای تایید بی‌اثر، به ادمین هشدار بده
    if not get_user(dep["user_id"]):
        await query.answer("❌ این کاربر دیگه تو دیتابیس نیست؛ درخواست دست‌نخورده موند.", show_alert=True)
        return

    # 🛡 اتمیک: اگه دو ادمین هم‌زمان بزنن، فقط یکی اعمال میشه (جلوی شارژ دوبار رو می‌گیره)
    cur = db_run("UPDATE deposits SET status='approved', decided_at=? WHERE id=? AND status='pending'",
                 (time.time(), dep_id))
    if cur.rowcount == 0:
        await query.answer("❌ این درخواست قبلاً بررسی شده.", show_alert=True)
        return
    db_run("UPDATE users SET balance=balance+? WHERE id=?", (dep["amount"], dep["user_id"]))
    log_tx(dep["user_id"], "charge_approved", dep["amount"], f"شارژ کیف پول (تایید #{dep_id})")

    await query.answer("✅ تایید شد")
    try:
        await send_sticker_safe(context, dep["user_id"], "deposit_approved")
        await context.bot.send_message(
            dep["user_id"],
            f"✅ شارژ کیف پول شما تایید شد!\n💰 مبلغ {fmt_money(dep['amount'])} تومان به کیف پولت اضافه شد.",
        )
    except Exception:
        pass

    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    try:
        await query.message.reply_text(
            f"✅ درخواست #{dep_id} تایید شد و {fmt_money(dep['amount'])} تومان به کاربر `{dep['user_id']}` اضافه شد.",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception:
        pass


async def dep_reject_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard_admin(update):
        return
    query = update.callback_query
    dep_id = int(context.match.group(1))
    dep = get_deposit(dep_id)
    if not dep:
        await query.answer("❌ این درخواست پیدا نشد.", show_alert=True)
        return
    if dep["status"] != "pending":
        await query.answer("❌ این درخواست قبلاً بررسی شده.", show_alert=True)
        return

    cur = db_run("UPDATE deposits SET status='rejected', decided_at=? WHERE id=? AND status='pending'",
                 (time.time(), dep_id))
    if cur.rowcount == 0:
        await query.answer("❌ این درخواست قبلاً بررسی شده.", show_alert=True)
        return

    await query.answer("❌ رد شد")
    try:
        await context.bot.send_message(
            dep["user_id"],
            f"❌ متاسفانه فیش شارژ کیف پول (#{dep_id}) تایید نشد.\n"
            f"در صورت اعتراض به پشتیبانی @{get_support_username()} پیام بده."
        )
    except Exception:
        pass
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except Exception:
        pass
    try:
        await query.message.reply_text(f"❌ درخواست #{dep_id} رد شد.")
    except Exception:
        pass


async def admin_deposits_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard_admin(update):
        return
    query = update.callback_query
    await query.answer()
    rows = db_all("SELECT * FROM deposits WHERE status='pending' ORDER BY id DESC LIMIT 15")
    if not rows:
        await safe_edit(query, "📭 درخواست شارژ در انتظار وجود نداره.", reply_markup=admin_menu())
        return
    text = "💳 *درخواست‌های شارژ در انتظار*\n━━━━━━━━━━━━━━\n"
    kb = []
    for r in rows:
        u = get_user(r["user_id"])
        name = md_escape(u["first_name"] or "ناشناس") if u else "حذف‌شده"
        text += f"#{r['id']} | {name} | {fmt_money(r['amount'])} تومان\n"
        kb.append([
            InlineKeyboardButton(f"✅ تایید #{r['id']}", callback_data=f"dep_approve_{r['id']}", style="success"),
            InlineKeyboardButton(f"❌ رد #{r['id']}", callback_data=f"dep_reject_{r['id']}", style="danger"),
        ])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back", style="primary")])
    await safe_edit(query, text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))


# ==================== خرید کانفیگ (پلن‌ها + حجم دلخواه) ====================
async def buy_config_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """منوی خرید کانفیگ: پلن‌های آماده (مثل نامحدود) + گزینه‌ی حجم دلخواه."""
    query = update.callback_query
    await query.answer()
    price_gb = get_price_per_gb()
    text = (
        "🛒 *خرید کانفیگ*\n"
        "━━━━━━━━━━━━━━\n"
        "یکی از پلن‌های آماده رو انتخاب کن، یا حجم دلخواه خودت رو بخر:\n\n"
        f"💎 قیمت هر گیگ برای حجم دلخواه: {fmt_money(price_gb)} تومان"
    )
    kb = plan_buttons("buy")
    kb.append([InlineKeyboardButton("✏️ حجم دلخواه", callback_data="buy_custom_volume", style="primary")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_main", style="primary")])
    await safe_edit(query, text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))


async def buy_config_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["conv_return"] = "buy_config"
    price_gb = get_price_per_gb()
    text = (
        "✏️ *خرید با حجم دلخواه*\n"
        "━━━━━━━━━━━━━━\n"
        f"💎 قیمت هر گیگابایت: {fmt_money(price_gb)} تومان\n"
        f"📏 حجم مجاز: بین {MIN_VOLUME_GB} تا {MAX_VOLUME_GB} گیگابایت\n\n"
        "حجم دلخواهت رو به گیگابایت (فقط عدد) بفرست:"
    )
    await safe_edit(query, text, parse_mode=ParseMode.MARKDOWN, reply_markup=cancel_kb())
    return ASK_VOLUME


async def receive_volume(update: Update, context: ContextTypes.DEFAULT_TYPE):
    raw = update.message.text.strip().replace(",", ".")
    try:
        volume = float(raw)
    except ValueError:
        await update.message.reply_text("❌ فقط عدد بفرست (مثلاً 20 یا 15.5) یا لغو کن.", reply_markup=cancel_kb())
        return ASK_VOLUME

    # 🛡 جلوی ورودی‌هایی مثل nan و inf که از فیلتر بالا رد میشن و بعداً کرش می‌دن
    if not math.isfinite(volume):
        await update.message.reply_text("❌ عدد نامعتبره. یه عدد عادی بفرست:", reply_markup=cancel_kb())
        return ASK_VOLUME

    if volume < MIN_VOLUME_GB or volume > MAX_VOLUME_GB:
        await update.message.reply_text(
            f"❌ حجم باید بین {MIN_VOLUME_GB} تا {MAX_VOLUME_GB} گیگابایت باشه. دوباره بفرست:",
            reply_markup=cancel_kb()
        )
        return ASK_VOLUME

    price_gb = get_price_per_gb()
    price = round(volume * price_gb)
    context.user_data["pending_volume"] = volume
    context.user_data["pending_price"] = price

    text, kb = _volume_confirm_text_kb(context)
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    return ConversationHandler.END


def _volume_confirm_text_kb(context):
    """صفحه‌ی تایید خرید حجم دلخواه (با پشتیبانی کد تخفیف)."""
    volume = context.user_data.get("pending_volume")
    price = context.user_data.get("pending_price")
    disc = _pending_discount_for(context, "volume")
    final_price = apply_discount(price, disc) if disc else price
    if disc:
        price_lines = (f"💰 قیمت کل: {fmt_money(price)} تومان\n"
                       f"🎟 با کد تخفیف ({discount_label(disc)}): *{fmt_money(final_price)} تومان*")
    else:
        price_lines = f"💰 قیمت کل: {fmt_money(price)} تومان"
    text = (
        "🧾 *تایید خرید*\n━━━━━━━━━━━━━━\n"
        f"📦 حجم: {fmt_volume(volume)} گیگابایت\n"
        f"{price_lines}\n\n"
        "آیا خرید رو تایید می‌کنی؟"
    )
    rows = [[InlineKeyboardButton("✅ تایید خرید", callback_data="cfg_confirm", style="success")]]
    if disc:
        rows.append([InlineKeyboardButton("🗑 حذف کد تخفیف", callback_data="disc_clear", style="danger")])
    else:
        rows.append([InlineKeyboardButton("🎟 کد تخفیف دارم", callback_data="disc_volume", style="success")])
    rows.append([InlineKeyboardButton("❌ انصراف", callback_data="cfg_cancel", style="danger")])
    return text, InlineKeyboardMarkup(rows)


async def cfg_cancel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("لغو شد")
    context.user_data.pop("pending_volume", None)
    context.user_data.pop("pending_price", None)
    context.user_data.pop("pending_discount", None)
    await safe_edit(query, "🚫 خرید لغو شد.", reply_markup=main_menu())


async def cfg_confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = query.from_user.id
    volume = context.user_data.get("pending_volume")
    price = context.user_data.get("pending_price")

    if volume is None or price is None:
        await query.answer("❌ درخواست منقضی شده، دوباره تلاش کن.", show_alert=True)
        await safe_edit(query, "❌ درخواست منقضی شده. دوباره از «خرید کانفیگ» شروع کن.", reply_markup=main_menu())
        return

    user = get_user(uid)
    # 🎟 اعمال کد تخفیف (اگه برای همین خرید ثبت شده باشه)
    disc = _pending_discount_for(context, "volume")
    base_price = price
    price = apply_discount(base_price, disc) if disc else base_price
    saved = base_price - price

    # 💰 کسر اتمیک: فقط وقتی کم میشه که موجودی واقعاً کافی باشه
    # (ضد دوبار-کلیک، دو دستگاه هم‌زمان و منفی شدن موجودی)
    cur = db_run(
        "UPDATE users SET balance=balance-?, total_spent=total_spent+? "
        "WHERE id=? AND is_banned=0 AND balance>=?",
        (price, price, uid, price)
    )
    if cur.rowcount == 0:
        await query.answer("❌ موجودی کافی نیست!", show_alert=True)
        await safe_edit(
            query,
            f"❌ موجودی کافی نداری!\nلازم: {fmt_money(price)} تومان\nموجودی تو: {fmt_money(user['balance'])} تومان",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💳 شارژ کیف پول", callback_data="charge_wallet", style="primary")],
                [InlineKeyboardButton("🔙 بازگشت", callback_data="back_main", style="primary")],
            ])
        )
        return
    # 🎟 مصرف اتمیک کد تخفیف؛ اگه همین لحظه نامعتبر شده باشه، پول کامل برمی‌گرده
    disc_note = ""
    if disc:
        if redeem_discount(disc, uid, saved):
            disc_note = f" | 🎟 {fmt_money(saved)} تومان تخفیف" if saved else ""
            context.user_data.pop("pending_discount", None)
        else:
            db_run("UPDATE users SET balance=balance+?, total_spent=total_spent-? WHERE id=?", (price, price, uid))
            context.user_data.pop("pending_discount", None)
            await query.answer("❌ این کد تخفیف دیگه معتبر نیست؛ بدون کد دوباره تایید کن.", show_alert=True)
            t, kb = _volume_confirm_text_kb(context)
            await safe_edit(query, t, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
            return

    order_id = db_run(
        "INSERT INTO config_orders (user_id, volume_gb, price, status, created_at) VALUES (?,?,?,?,?)",
        (uid, volume, price, "pending", time.time())
    ).lastrowid
    log_tx(uid, "purchase", -price, f"خرید کانفیگ {fmt_volume(volume)} گیگ (سفارش #{order_id}){disc_note}")

    context.user_data.pop("pending_volume", None)
    context.user_data.pop("pending_price", None)

    await query.answer("✅ ثبت شد!")
    await safe_edit(
        query,
        "✅ *خرید با موفقیت ثبت شد!*\n\n"
        f"📦 سفارش #{order_id} — {fmt_volume(volume)} گیگابایت\n"
        "کانفیگ به‌زودی توسط پشتیبانی برات ارسال میشه.\n"
        "💡 اگر مشکلی بود از بخش «پشتیبانی» پیام بده.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu()
    )

    if get_setting("purchase_notify") == "1":
        try:
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("📤 ارسال کانفیگ", callback_data=f"sendcfg_order_{order_id}", style="primary")
            ]])
            await notify_admins(
                context,
                f"🛍 *خرید جدید*\n━━━━━━━━━━━━━━\n"
                f"👤 {md_escape(user['first_name'] or 'ناشناس')} (`{uid}`)\n"
                f"📦 حجم: {fmt_volume(volume)} گیگابایت\n"
                f"💰 {fmt_money(price)} تومان\n"
                f"🆔 سفارش #{order_id}",
                reply_markup=kb
            )
        except Exception:
            pass


# ---- ارسال کانفیگ به خریدار توسط ادمین ----
async def admin_sendcfg_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    order_id = int(context.match.group(1))
    order = get_order(order_id)
    if not order:
        await query.message.reply_text("❌ این سفارش پیدا نشد.", reply_markup=admin_menu())
        return ConversationHandler.END
    if order["status"] == "delivered":
        await query.message.reply_text("ℹ️ کانفیگ این سفارش قبلاً ارسال شده.", reply_markup=admin_menu())
        return ConversationHandler.END

    # اگه ادمین وسط یه ارسال کانفیگ دیگه بود، اینجا هدف رو عوض می‌کنیم (رفع باگ بی‌پاسخ ماندن دکمه)
    context.user_data["order_target_id"] = order_id
    context.user_data["order_target_uid"] = order["user_id"]
    await query.message.reply_text(
        f"📤 کانفیگ (متن، عکس یا فایل) رو بفرست تا برای خریدار سفارش #{order_id} (`{order['user_id']}`) ارسال بشه:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=cancel_kb()
    )
    return ADMIN_SEND_CFG


async def receive_admin_send_cfg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    target_uid = context.user_data.get("order_target_uid")
    order_id = context.user_data.get("order_target_id")
    if not target_uid or not order_id:
        await update.message.reply_text("❌ سفارش مشخص نیست.", reply_markup=admin_menu())
        return ConversationHandler.END

    try:
        await context.bot.copy_message(
            chat_id=target_uid,
            from_chat_id=update.effective_chat.id,
            message_id=update.message.message_id,
        )
        db_run("UPDATE config_orders SET status='delivered', delivered_at=? WHERE id=?", (time.time(), order_id))
        db_run("UPDATE users SET used_configs=used_configs+1 WHERE id=?", (target_uid,))
        await send_sticker_safe(context, target_uid, "purchase_success")
        # 🔙 برگشت به لیست سفارش‌های در انتظار (اگه سفارش دیگه‌ای مونده باشه، همون‌جا آماده‌ست)
        t, kb = _pending_orders_text_kb()
        await update.message.reply_text(
            f"✅ کانفیگ برای خریدار `{target_uid}` (سفارش #{order_id}) ارسال شد.\n\n{t}",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=kb
        )
    except Exception as e:
        await update.message.reply_text(f"❌ ارسال ناموفق بود: {e}", reply_markup=admin_menu())

    context.user_data.pop("order_target_uid", None)
    context.user_data.pop("order_target_id", None)
    return ConversationHandler.END


# ---- پنل مدیریت حجم و کانفیگ (ادمین) ----
def _orders_menu_text_kb():
    price_gb = get_price_per_gb()
    pending_count = db_one("SELECT COUNT(*) c FROM config_orders WHERE status='pending'")["c"]
    text = (
        "📦 *مدیریت حجم و کانفیگ‌ها*\n"
        "━━━━━━━━━━━━━━\n"
        f"💎 قیمت فعلی هر گیگ: {fmt_money(price_gb)} تومان\n"
        f"📥 سفارش‌های در انتظار ارسال: {pending_count}"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💎 تغییر قیمت هر گیگ", callback_data="admin_set_price", style="primary")],
        [InlineKeyboardButton("📥 سفارش‌های در انتظار", callback_data="admin_pending_orders", style="primary")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back", style="primary")],
    ])
    return text, kb


async def admin_orders_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard_admin(update):
        return
    query = update.callback_query
    await query.answer()
    text, kb = _orders_menu_text_kb()
    await safe_edit(query, text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


def _pending_orders_text_kb():
    rows = db_all("SELECT * FROM config_orders WHERE status='pending' ORDER BY id DESC LIMIT 15")
    if not rows:
        return "📭 سفارش در انتظاری وجود نداره.", InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back", style="primary")]])
    text = "📥 *سفارش‌های در انتظار ارسال*\n━━━━━━━━━━━━━━\n"
    kb = []
    for r in rows:
        u = get_user(r["user_id"])
        name = md_escape(u["first_name"] or "ناشناس") if u else "حذف‌شده"
        text += f"#{r['id']} | {name} | {md_escape(order_desc(r))} | {fmt_money(r['price'])} تومان\n"
        kb.append([InlineKeyboardButton(f"📤 ارسال کانفیگ #{r['id']}", callback_data=f"sendcfg_order_{r['id']}", style="primary")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back", style="primary")])
    return text, InlineKeyboardMarkup(kb)


async def admin_pending_orders_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard_admin(update):
        return
    query = update.callback_query
    await query.answer()
    text, kb = _pending_orders_text_kb()
    await safe_edit(query, text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


async def admin_set_price_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    context.user_data["conv_return"] = "admin_orders_menu"
    await safe_edit(
        query,
        f"💎 قیمت فعلی: {fmt_money(get_price_per_gb())} تومان به ازای هر گیگ\n\nقیمت جدید هر گیگ رو به تومان بفرست:",
        reply_markup=cancel_kb()
    )
    return SET_PRICE_PER_GB


async def receive_price_per_gb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(",", "")
    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text("❌ فقط عدد مثبت بفرست یا لغو کن.", reply_markup=cancel_kb())
        return SET_PRICE_PER_GB
    set_setting("price_per_gb", text)
    t, kb = _orders_menu_text_kb()
    await update.message.reply_text(
        f"✅ قیمت هر گیگ روی {fmt_money(int(text))} تومان تنظیم شد.\n\n{t}",
        parse_mode=ParseMode.MARKDOWN, reply_markup=kb
    )
    return ConversationHandler.END


# ==================== پلن‌ها (خرید اتوماتیک + پلن‌های بخش خرید کانفیگ) ====================
def get_plan(pid: int):
    return db_one("SELECT * FROM plans WHERE id=?", (pid,))


def all_plans():
    return db_all("SELECT * FROM plans ORDER BY sort_order, id")


def plans_for(place: str):
    """پلن‌های فعالی که باید تو این بخش نمایش داده بشن (place: 'auto' یا 'buy')."""
    return db_all(
        "SELECT * FROM plans WHERE is_active=1 AND (show_in=? OR show_in='both') ORDER BY sort_order, id",
        (place,),
    )


def plan_stock(pid: int) -> int:
    """تعداد کانفیگ‌های آماده‌ی موجود در انبار این پلن."""
    return db_one(
        "SELECT COUNT(*) c FROM auto_configs WHERE plan_id=? AND status='available'", (pid,)
    )["c"]


def plan_confirm_text(plan) -> str:
    """متن تاییدیه‌ی خرید پلن (اگه ادمین متن اختصاصی گذاشته باشه همون میاد،
    مثل: «آیا تایید می‌کنید خرید کانفیگ تک سروره آمریکا نامحدود را؟»)."""
    if plan["confirm_text"]:
        return plan["confirm_text"]
    return f"آیا تایید می‌کنید خرید «{plan['name']}» را؟"


def plan_buttons(place: str):
    """دکمه‌های شیشه‌ای رنگی پلن‌ها برای منوهای خرید (هم‌استایل بقیه‌ی بات)."""
    keyboard = []
    for p in plans_for(place):
        label = f"{p['name']} | {fmt_money(p['price'])} تومان"
        if p["delivery_mode"] == "auto" and plan_stock(p["id"]) == 0:
            label += " (ناموجود)"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"plan_sel_{p['id']}", style="success")])
    return keyboard


def auto_buy_menu_kb():
    keyboard = plan_buttons("auto")
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="back_main", style="primary")])
    return InlineKeyboardMarkup(keyboard)


async def auto_buy_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "⚡️ *خرید اتوماتیک*\n"
        "━━━━━━━━━━━━━━\n"
        "پلن مورد نظرت رو انتخاب کن؛ اگه کانفیگ آماده تو انبار باشه، همون لحظه تحویل می‌گیری:"
    )
    await safe_edit(query, text, parse_mode=ParseMode.MARKDOWN, reply_markup=auto_buy_menu_kb())


async def _show_plan_confirm(query, context, pid: int):
    """صفحه‌ی تایید خرید پلن (با پشتیبانی کد تخفیف)."""
    plan = get_plan(pid)
    if not plan or not plan["is_active"]:
        try:
            await query.answer("❌ این پلن دیگه فعال نیست.", show_alert=True)
        except Exception:
            pass
        return

    uid = query.from_user.id
    user = get_user(uid)
    if not user:
        try:
            await query.answer("❌ اول /start رو بزن.", show_alert=True)
        except Exception:
            pass
        return
    try:
        await query.answer()
    except Exception:
        pass

    price = int(plan["price"])
    disc = _pending_discount_for(context, "plan", pid)
    final_price = apply_discount(price, disc) if disc else price

    if user["balance"] < final_price:
        kb_rows = [[InlineKeyboardButton("💳 شارژ کیف پول", callback_data="charge_wallet", style="primary")]]
        if not disc:
            kb_rows.append([InlineKeyboardButton("🎟 کد تخفیف دارم", callback_data=f"disc_plan_{pid}", style="success")])
        kb_rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="auto_buy_menu", style="primary")])
        await safe_edit(
            query,
            f"❌ موجودی کافی نداری!\n💎 قیمت پلن: {fmt_money(final_price)} تومان\n💰 موجودی تو: {fmt_money(user['balance'])} تومان",
            reply_markup=InlineKeyboardMarkup(kb_rows)
        )
        return

    stock = plan_stock(pid)
    if plan["delivery_mode"] == "auto" and stock == 0:
        await safe_edit(
            query,
            "❌ فعلاً کانفیگی برای این پلن موجود نیست. بعداً دوباره سر بزن.",
            reply_markup=auto_buy_menu_kb()
        )
        return

    if stock > 0:
        delivery_line = "بعد از تایید، کانفیگ *بلافاصله* برات ارسال میشه."
    else:
        delivery_line = "بعد از تایید، سفارشت ثبت میشه و کانفیگ *توسط پشتیبانی* برات ارسال میشه."

    if disc:
        price_lines = (f"💰 قیمت: {fmt_money(price)} تومان\n"
                       f"🎟 با کد تخفیف ({discount_label(disc)}): *{fmt_money(final_price)} تومان*")
    else:
        price_lines = f"💰 قیمت: {fmt_money(price)} تومان"

    text = (
        "🧾 *تایید خرید*\n━━━━━━━━━━━━━━\n"
        f"❓ {md_escape(plan_confirm_text(plan))}\n\n"
        f"📦 پلن: {md_escape(plan['name'])}\n"
        f"{price_lines}\n\n"
        f"{delivery_line}"
    )
    kb_rows = [[InlineKeyboardButton("✅ بله، تایید می‌کنم", callback_data=f"plan_ok_{pid}", style="success")]]
    if disc:
        kb_rows.append([InlineKeyboardButton("🗑 حذف کد تخفیف", callback_data="disc_clear", style="danger")])
    else:
        kb_rows.append([InlineKeyboardButton("🎟 کد تخفیف دارم", callback_data=f"disc_plan_{pid}", style="success")])
    kb_rows.append([InlineKeyboardButton("❌ انصراف", callback_data="auto_buy_menu", style="danger")])
    await safe_edit(query, text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb_rows))


async def plan_select_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """کاربر روی یه پلن (مثل «نامحدود») کلیک کرده → نمایش متن تاییدیه‌ی همون پلن."""
    await _show_plan_confirm(update.callback_query, context, int(context.match.group(1)))


async def plan_confirm_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """تایید نهایی خرید پلن. اول پول به صورت اتمیک کم میشه، بعد:
    - اگه انبار کانفیگ آماده داشت → تحویل آنی
    - اگه نداشت و پلن دستی/ترکیبی بود → ثبت سفارش برای ارسال توسط ادمین
    - اگه نداشت و پلن فقط-آنی بود → برگشت کامل وجه"""
    query = update.callback_query
    pid = int(context.match.group(1))
    plan = get_plan(pid)
    if not plan or not plan["is_active"]:
        await query.answer("❌ این پلن دیگه فعال نیست.", show_alert=True)
        return

    uid = query.from_user.id
    user = get_user(uid)
    if not user:
        await query.answer("❌ اول /start رو بزن.", show_alert=True)
        return

    base_price = int(plan["price"])
    pname = plan["name"]
    disc = _pending_discount_for(context, "plan", pid)
    price = apply_discount(base_price, disc) if disc else base_price
    saved = base_price - price

    # 💰 کسر اتمیک: ضد دوبار-کلیک، دو دستگاه هم‌زمان و منفی شدن موجودی
    cur = db_run(
        "UPDATE users SET balance=balance-?, total_spent=total_spent+? "
        "WHERE id=? AND is_banned=0 AND balance>=?",
        (price, price, uid, price)
    )
    if cur.rowcount == 0:
        await query.answer("❌ موجودی کافی نیست!", show_alert=True)
        return

    # 🎟 مصرف اتمیک کد تخفیف؛ اگه همین لحظه نامعتبر شده باشه، پول کامل برمی‌گرده
    disc_id = None
    if disc:
        if redeem_discount(disc, uid, saved):
            disc_id = disc["id"]
            context.user_data.pop("pending_discount", None)
        else:
            db_run("UPDATE users SET balance=balance+?, total_spent=total_spent-? WHERE id=?", (price, price, uid))
            context.user_data.pop("pending_discount", None)
            try:
                await query.answer("❌ این کد تخفیف دیگه معتبر نیست؛ بدون کد دوباره امتحان کن.", show_alert=True)
            except Exception:
                pass
            await _show_plan_confirm(query, context, pid)
            return

    # ⚡️ تلاش برای تحویل آنی از انبار (پلن‌های auto و hybrid)
    delivered = False
    cfg_id = None
    if plan["delivery_mode"] in ("auto", "hybrid"):
        for _ in range(3):
            row = db_one(
                "SELECT id, source_chat_id, source_message_id FROM auto_configs "
                "WHERE plan_id=? AND status='available' ORDER BY id LIMIT 1",
                (pid,)
            )
            if not row:
                break
            # رزرو اتمیک: اگه یه ریکوئست دیگه زودتر برده باشتش، میریم سراغ ردیف بعدی
            claim = db_run(
                "UPDATE auto_configs SET status='delivered', delivered_to=?, delivered_at=? "
                "WHERE id=? AND status='available'",
                (uid, time.time(), row["id"])
            )
            if claim.rowcount == 0:
                continue
            cfg_id = row["id"]
            try:
                await context.bot.copy_message(
                    chat_id=uid,
                    from_chat_id=row["source_chat_id"],
                    message_id=row["source_message_id"],
                )
                delivered = True
            except Exception as e:
                logger.error("plan delivery failed for %s: %s", uid, e)
                # کانفیگ هدر نره؛ برگرده به انبار (اگه پلن hybrid باشه سفارش دستی ثبت میشه)
                db_run("UPDATE auto_configs SET status='available', delivered_to=NULL, delivered_at=NULL WHERE id=?",
                       (cfg_id,))
                cfg_id = None
            break

    disc_note = f" | 🎟 {fmt_money(saved)} تومان تخفیف" if disc_id and saved else ""

    if delivered:
        db_run("UPDATE users SET used_configs=used_configs+1 WHERE id=?", (uid,))
        log_tx(uid, "plan_purchase", -price, f"خرید پلن «{pname}» (کانفیگ #{cfg_id}){disc_note}")
        await query.answer("✅ ارسال شد!")
        await send_sticker_safe(context, uid, "purchase_success")
        disc_line = f"\n🎟 {fmt_money(saved)} تومان تخفیف گرفتی!" if disc_id and saved else ""
        await safe_edit(
            query,
            f"✅ *خرید موفق بود!*\n\n📦 پلن «{md_escape(pname)}» با موفقیت ارسال شد.{disc_line}\nاز خریدت ممنونیم 🌟",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu()
        )
        if get_setting("purchase_notify") == "1":
            try:
                await notify_admins(
                    context,
                    f"⚡️ *خرید پلن (تحویل آنی)*\n━━━━━━━━━━━━━━\n"
                    f"👤 {md_escape(user['first_name'] or 'ناشناس')} (`{uid}`)\n"
                    f"📦 پلن: {md_escape(pname)}\n"
                    f"💰 {fmt_money(price)} تومان\n"
                    f"🆔 کانفیگ #{cfg_id} تحویل داده شد."
                )
            except Exception:
                pass
        return

    if plan["delivery_mode"] == "auto":
        # انبار خالی/ارسال ناموفق و این پلن فقط تحویل آنی داره → برگشت کامل وجه (+ برگشت کد تخفیف)
        db_run("UPDATE users SET balance=balance+?, total_spent=total_spent-? WHERE id=?", (price, price, uid))
        if disc_id:
            refund_discount(disc_id, uid)
        log_tx(uid, "plan_refund", price, f"برگشت وجه پلن «{pname}» (انبار خالی)")
        await query.answer("❌ همین الان تموم شد!", show_alert=True)
        await safe_edit(
            query,
            "❌ موجودی انبار این پلن همین الان تموم شد و هیچ مبلغی از حسابت کم نشد.\nبعداً دوباره امتحان کن.",
            reply_markup=auto_buy_menu_kb()
        )
        return

    # 👤 سفارش دستی (پلن manual، یا hybrid با انبار خالی): ادمین کانفیگ رو می‌فرسته
    order_id = db_run(
        "INSERT INTO config_orders (user_id, volume_gb, price, status, created_at, plan_id) VALUES (?,?,?,?,?,?)",
        (uid, None, price, "pending", time.time(), pid)
    ).lastrowid
    log_tx(uid, "plan_purchase", -price, f"خرید پلن «{pname}» (سفارش #{order_id}){disc_note}")
    await query.answer("✅ ثبت شد!")
    await safe_edit(
        query,
        "✅ *خرید با موفقیت ثبت شد!*\n\n"
        f"📦 سفارش #{order_id} — {md_escape(pname)}\n"
        "کانفیگ به‌زودی توسط پشتیبانی برات ارسال میشه.\n"
        "💡 اگر مشکلی بود از بخش «پشتیبانی» پیام بده.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu()
    )
    if get_setting("purchase_notify") == "1":
        try:
            kb = InlineKeyboardMarkup([[
                InlineKeyboardButton("📤 ارسال کانفیگ", callback_data=f"sendcfg_order_{order_id}", style="primary")
            ]])
            await notify_admins(
                context,
                f"🛍 *خرید پلن (در انتظار ارسال دستی)*\n━━━━━━━━━━━━━━\n"
                f"👤 {md_escape(user['first_name'] or 'ناشناس')} (`{uid}`)\n"
                f"📦 پلن: {md_escape(pname)}\n"
                f"💰 {fmt_money(price)} تومان\n"
                f"🆔 سفارش #{order_id}",
                reply_markup=kb
            )
        except Exception:
            pass


async def auto_cancel_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("لغو شد")
    await safe_edit(query, "🚫 خرید لغو شد.", reply_markup=main_menu())


# ---- مدیریت انبار کانفیگ‌های آماده‌ی پلن‌ها (ادمین) ----
def admin_auto_menu_kb():
    keyboard = []
    for p in all_plans():
        if p["delivery_mode"] not in ("auto", "hybrid"):
            continue
        left = plan_stock(p["id"])
        keyboard.append([InlineKeyboardButton(
            f"➕ {p['name']} (موجود: {left})", callback_data=f"auto_add_pkg_{p['id']}", style="success")])
    keyboard.append([InlineKeyboardButton("🧩 مدیریت پلن‌ها", callback_data="admin_plans_menu", style="primary")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back", style="primary")])
    return InlineKeyboardMarkup(keyboard)


def _auto_menu_text_kb():
    lines = ["⚡️ *انبار کانفیگ‌های آماده*", "━━━━━━━━━━━━━━"]
    has_any = False
    for p in all_plans():
        if p["delivery_mode"] in ("auto", "hybrid"):
            has_any = True
            lines.append(f"📦 {md_escape(p['name'])} | {fmt_money(p['price'])} تومان | موجودی انبار: {plan_stock(p['id'])}")
    if not has_any:
        lines.append("هیچ پلنی با تحویل آنی تعریف نشده. از «🧩 مدیریت پلن‌ها» نحوه تحویل رو تغییر بده.")
    lines.append("\nهر کانفیگ فقط یک‌بار برای یک مشتری ارسال میشه و بعدش خودکار از انبار کم میشه.")
    return "\n".join(lines), admin_auto_menu_kb()


async def admin_auto_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard_admin(update):
        return
    query = update.callback_query
    await query.answer()
    text, kb = _auto_menu_text_kb()
    await safe_edit(query, text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


async def admin_auto_add_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    pid = int(context.match.group(1))
    plan = get_plan(pid)
    if not plan:
        await query.message.reply_text("❌ این پلن پیدا نشد.", reply_markup=admin_menu())
        return ConversationHandler.END
    context.user_data["auto_add_plan"] = pid
    left = plan_stock(pid)
    await safe_edit(
        query,
        f"📦 افزودن کانفیگ به انبار پلن *{md_escape(plan['name'])}* (فعلاً {left} تا موجوده)\n\n"
        "کانفیگ رو بفرست (متن، عکس یا فایل). می‌تونی پشت‌سرهم چندتا بفرستی، هرکدوم فقط برای یک نفر ارسال میشه.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=cancel_kb()
    )
    return ADMIN_AUTO_ADD_CFG


async def receive_auto_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    pid = context.user_data.get("auto_add_plan")
    plan = get_plan(pid) if pid else None
    if not plan:
        await update.message.reply_text("❌ پلن مشخص نیست، دوباره از منو شروع کن.", reply_markup=admin_menu())
        return ConversationHandler.END

    db_run(
        "INSERT INTO auto_configs (plan_id, package_gb, source_chat_id, source_message_id, status, added_by, added_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (pid, plan["legacy_gb"], update.effective_chat.id, update.message.message_id, "available",
         update.effective_user.id, time.time())
    )
    left = plan_stock(pid)
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ افزودن کانفیگ بعدی", callback_data="auto_add_more", style="success")],
        [InlineKeyboardButton("✅ پایان", callback_data="auto_add_finish", style="success")],
    ])
    await update.message.reply_text(
        f"✅ کانفیگ اضافه شد. موجودی فعلی انبار «{plan['name']}»: {left} تا.\n\nمی‌خوای یکی دیگه اضافه کنی؟",
        reply_markup=kb
    )
    return ADMIN_AUTO_ADD_CFG


async def auto_add_more_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pid = context.user_data.get("auto_add_plan")
    plan = get_plan(pid) if pid else None
    if not plan:
        await query.message.reply_text("❌ پلن مشخص نیست، دوباره از منو شروع کن.", reply_markup=admin_menu())
        return ConversationHandler.END
    await query.message.reply_text(
        f"📦 کانفیگ بعدی برای انبار «{plan['name']}» رو بفرست:",
        reply_markup=cancel_kb()
    )
    return ADMIN_AUTO_ADD_CFG


async def auto_add_finish_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("تمام شد ✅")
    context.user_data.pop("auto_add_plan", None)
    # 🔙 برگشت به همون منوی انبار (نه پرت شدن به پنل اصلی)
    t, kb = _auto_menu_text_kb()
    await query.message.reply_text(f"✅ افزودن کانفیگ‌ها تموم شد.\n\n{t}",
                                   parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    return ConversationHandler.END


# ==================== 🧩 مدیریت پلن‌ها (ادمین) ====================
PLAN_MODE_ORDER = ["hybrid", "auto", "manual"]
DELIVERY_LABELS = {
    "auto": "⚡️ فقط آنی از انبار",
    "manual": "👤 فقط دستی توسط ادمین",
    "hybrid": "⚡️+👤 آنی؛ اگه انبار خالی بود، دستی",
}
PLAN_SHOW_ORDER = ["both", "auto", "buy"]
SHOW_LABELS = {
    "auto": "فقط «خرید اتوماتیک»",
    "buy": "فقط «خرید کانفیگ»",
    "both": "هر دو بخش",
}


async def admin_plans_menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard_admin(update):
        return
    query = update.callback_query
    await query.answer()
    text = (
        "🧩 *مدیریت پلن‌ها*\n━━━━━━━━━━━━━━\n"
        "از اینجا می‌تونی پلن جدید بسازی (مثل «نامحدود»)، قیمت‌ها رو عوض کنی،\n"
        "متن تاییدیه‌ی خرید هر پلن رو تنظیم کنی و نحوه تحویل رو مشخص کنی.\n\n"
        "روی هر پلن بزن تا مدیریتش کنی:"
    )
    kb = []
    for p in all_plans():
        status = "🟢" if p["is_active"] else "🔴"
        kb.append([InlineKeyboardButton(
            f"{status} {p['name']} | {fmt_money(p['price'])} تومان",
            callback_data=f"padm_{p['id']}", style="primary")])
    kb.append([InlineKeyboardButton("➕ ساخت پلن جدید", callback_data="padm_new", style="success")])
    kb.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_back", style="primary")])
    await safe_edit(query, text, parse_mode=ParseMode.MARKDOWN, reply_markup=InlineKeyboardMarkup(kb))


def _plan_admin_text_kb(plan):
    pid = plan["id"]
    stock = plan_stock(pid)
    active = "🟢 فعال" if plan["is_active"] else "🔴 غیرفعال"
    text = (
        "🧩 *جزئیات پلن*\n━━━━━━━━━━━━━━\n"
        f"📛 نام: {md_escape(plan['name'])}\n"
        f"💰 قیمت: {fmt_money(plan['price'])} تومان\n"
        f"🚚 نحوه تحویل: {DELIVERY_LABELS.get(plan['delivery_mode'], plan['delivery_mode'])}\n"
        f"👁 محل نمایش: {SHOW_LABELS.get(plan['show_in'], plan['show_in'])}\n"
        f"📦 موجودی انبار: {stock}\n"
        f"وضعیت: {active}\n\n"
        f"📝 متن تاییدیه‌ی خرید:\n«{md_escape(plan_confirm_text(plan))}»"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 تغییر قیمت", callback_data=f"padm_price_{pid}", style="success"),
         InlineKeyboardButton("✏️ تغییر نام", callback_data=f"padm_name_{pid}", style="primary")],
        [InlineKeyboardButton("📝 تغییر متن تاییدیه", callback_data=f"padm_text_{pid}", style="primary")],
        [InlineKeyboardButton("🚚 تغییر نحوه تحویل", callback_data=f"padm_mode_{pid}", style="primary"),
         InlineKeyboardButton("👁 تغییر محل نمایش", callback_data=f"padm_show_{pid}", style="primary")],
        [InlineKeyboardButton("🔴 غیرفعال کردن" if plan["is_active"] else "🟢 فعال کردن",
                              callback_data=f"padm_toggle_{pid}",
                              style="danger" if plan["is_active"] else "success")],
        [InlineKeyboardButton(f"➕ افزودن کانفیگ به انبار (موجود: {stock})",
                              callback_data=f"auto_add_pkg_{pid}", style="success")],
        [InlineKeyboardButton("🗑 حذف پلن", callback_data=f"padm_del_{pid}", style="danger")],
        [InlineKeyboardButton("🔙 لیست پلن‌ها", callback_data="admin_plans_menu", style="primary")],
    ])
    return text, kb


async def _render_plan_admin(query, pid: int):
    plan = get_plan(pid)
    if not plan:
        await safe_edit(query, "❌ این پلن پیدا نشد.", reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 لیست پلن‌ها", callback_data="admin_plans_menu", style="primary")]]))
        return
    text, kb = _plan_admin_text_kb(plan)
    await safe_edit(query, text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


async def plan_admin_view_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard_admin(update):
        return
    query = update.callback_query
    await query.answer()
    await _render_plan_admin(query, int(context.match.group(1)))


async def padm_mode_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard_admin(update):
        return
    query = update.callback_query
    pid = int(context.match.group(1))
    plan = get_plan(pid)
    if not plan:
        await query.answer("❌ پیدا نشد.", show_alert=True)
        return
    cur_mode = plan["delivery_mode"] if plan["delivery_mode"] in PLAN_MODE_ORDER else "hybrid"
    new_mode = PLAN_MODE_ORDER[(PLAN_MODE_ORDER.index(cur_mode) + 1) % len(PLAN_MODE_ORDER)]
    db_run("UPDATE plans SET delivery_mode=? WHERE id=?", (new_mode, pid))
    await query.answer(DELIVERY_LABELS[new_mode])
    await _render_plan_admin(query, pid)


async def padm_show_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard_admin(update):
        return
    query = update.callback_query
    pid = int(context.match.group(1))
    plan = get_plan(pid)
    if not plan:
        await query.answer("❌ پیدا نشد.", show_alert=True)
        return
    cur_show = plan["show_in"] if plan["show_in"] in PLAN_SHOW_ORDER else "both"
    new_show = PLAN_SHOW_ORDER[(PLAN_SHOW_ORDER.index(cur_show) + 1) % len(PLAN_SHOW_ORDER)]
    db_run("UPDATE plans SET show_in=? WHERE id=?", (new_show, pid))
    await query.answer(SHOW_LABELS[new_show])
    await _render_plan_admin(query, pid)


async def padm_toggle_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard_admin(update):
        return
    query = update.callback_query
    pid = int(context.match.group(1))
    plan = get_plan(pid)
    if not plan:
        await query.answer("❌ پیدا نشد.", show_alert=True)
        return
    new_val = 0 if plan["is_active"] else 1
    db_run("UPDATE plans SET is_active=? WHERE id=?", (new_val, pid))
    await query.answer("🟢 فعال شد" if new_val else "🔴 غیرفعال شد")
    await _render_plan_admin(query, pid)


async def padm_del_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard_admin(update):
        return
    query = update.callback_query
    await query.answer()
    pid = int(context.match.group(1))
    plan = get_plan(pid)
    if not plan:
        await _render_plan_admin(query, pid)
        return
    stock = plan_stock(pid)
    text = (
        f"⚠️ *تایید حذف پلن*\n\nمطمئنی می‌خوای پلن «{md_escape(plan['name'])}» رو برای همیشه حذف کنی؟\n"
        f"📦 {stock} کانفیگ استفاده‌نشده تو انبارش هم حذف میشه.\nاین کار قابل بازگشت نیست!"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ بله، حذف کن", callback_data=f"padm_delok_{pid}", style="danger"),
         InlineKeyboardButton("🚫 نه، لغو", callback_data=f"padm_{pid}", style="primary")],
    ])
    await safe_edit(query, text, parse_mode=ParseMode.MARKDOWN, reply_markup=kb)


async def padm_delok_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard_admin(update):
        return
    query = update.callback_query
    pid = int(context.match.group(1))
    db_run("DELETE FROM auto_configs WHERE plan_id=? AND status='available'", (pid,))
    db_run("DELETE FROM plans WHERE id=?", (pid,))
    await query.answer("🗑 حذف شد")
    await admin_plans_menu_cb(update, context)


def _back_to_plan_kb(pid):
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت به پلن", callback_data=f"padm_{pid}", style="primary")]])


# ---- ویرایش قیمت / نام / متن تاییدیه ----
async def padm_price_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    pid = int(context.match.group(1))
    plan = get_plan(pid)
    if not plan:
        await query.message.reply_text("❌ پلن پیدا نشد.", reply_markup=admin_menu())
        return ConversationHandler.END
    context.user_data["plan_edit_id"] = pid
    await safe_edit(
        query,
        f"💰 قیمت فعلی «{md_escape(plan['name'])}»: {fmt_money(plan['price'])} تومان\n\n"
        "قیمت جدید رو به تومان (فقط عدد) بفرست:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=cancel_kb()
    )
    return PLAN_EDIT_PRICE


async def receive_plan_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    pid = context.user_data.get("plan_edit_id")
    text = update.message.text.strip().replace(",", "")
    if not text.isdigit() or int(text) <= 0:
        await update.message.reply_text("❌ فقط عدد مثبت بفرست یا لغو کن.", reply_markup=cancel_kb())
        return PLAN_EDIT_PRICE
    if not pid or not get_plan(pid):
        await update.message.reply_text("❌ پلن مشخص نیست.", reply_markup=admin_menu())
        return ConversationHandler.END
    db_run("UPDATE plans SET price=? WHERE id=?", (int(text), pid))
    t, kb = _plan_admin_text_kb(get_plan(pid))
    await update.message.reply_text(f"✅ قیمت پلن روی {fmt_money(int(text))} تومان تنظیم شد.\n\n{t}",
                                     parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    context.user_data.pop("plan_edit_id", None)
    return ConversationHandler.END


async def padm_name_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    pid = int(context.match.group(1))
    plan = get_plan(pid)
    if not plan:
        await query.message.reply_text("❌ پلن پیدا نشد.", reply_markup=admin_menu())
        return ConversationHandler.END
    context.user_data["plan_edit_id"] = pid
    await safe_edit(
        query,
        f"✏️ نام فعلی: {md_escape(plan['name'])}\n\nنام جدید پلن رو بفرست:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=cancel_kb()
    )
    return PLAN_EDIT_NAME


async def receive_plan_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    pid = context.user_data.get("plan_edit_id")
    name = update.message.text.strip()
    if not name or len(name) > 60:
        await update.message.reply_text("❌ یه نام معتبر (حداکثر ۶۰ حرف) بفرست یا لغو کن.", reply_markup=cancel_kb())
        return PLAN_EDIT_NAME
    if not pid or not get_plan(pid):
        await update.message.reply_text("❌ پلن مشخص نیست.", reply_markup=admin_menu())
        return ConversationHandler.END
    db_run("UPDATE plans SET name=? WHERE id=?", (name, pid))
    t, kb = _plan_admin_text_kb(get_plan(pid))
    await update.message.reply_text(f"✅ نام پلن بروزرسانی شد.\n\n{t}",
                                    parse_mode=ParseMode.MARKDOWN, reply_markup=kb)
    context.user_data.pop("plan_edit_id", None)
    return ConversationHandler.END


async def padm_text_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await guard_admin(update):
        return ConversationHandler.END
    query = update.callback_query
    await query.answer()
    pid = int(context.match.group(1))
    plan = get_plan(pid)
    if not plan:
        await query.message.reply_text("❌ پلن پیدا نشد.", reply_markup=admin_menu())
        return ConversationHandler.END
    context.user_data["plan_edit_id"] = pid
    await safe_edit(
        query,
        "📝 متن فعلی تاییدیه‌ی خرید:\n"
        f"«{md_escape(plan_confirm_text(plan))}»\n\n"
        "متن جدید رو بفرست (مثلاً: آیا تایید می‌کنید خرید کانفیگ تک سروره آمریکا نامحدود را؟)\n"
        "یا فقط «-» بفرست تا متن پیش‌فرض ساخته بشه:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=cancel_kb()
    )
    return PLAN_EDIT_TEXT


async def receive_plan_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return C
