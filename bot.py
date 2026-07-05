"""
TEXNOMIX GROUP - Kundalik ish va zakazlar uchun eslatma bot.
Faqat bitta foydalanuvchi (siz) uchun mo'ljallangan.

Ishlash tartibi:
    /start   - botni ishga tushirish, chat ID sini eslab qolish
    /yangi   - yangi vazifa/zakaz qo'shish (matn -> sana -> vaqt)
    /royxat  - hali bajarilmagan barcha eslatmalarni ko'rsatish
    /bugun   - faqat bugungi eslatmalarni ko'rsatish

Belgilangan vaqtda bot avtomatik xabar yuboradi va "Bajarildi" tugmasi chiqadi.
"""

import logging
import os
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# ---------------------------------------------------------------------------
# SOZLAMALAR
# ---------------------------------------------------------------------------

TOKEN = os.environ.get("BOT_TOKEN", "SIZNING_BOT_TOKENINGIZ_BU_YERGA")
TIMEZONE = ZoneInfo("Asia/Tashkent")
DB_PATH = os.path.join(os.path.dirname(__file__), "eslatmalar.db")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# Conversation bosqichlari
MATN, SANA, VAQT = range(3)


# ---------------------------------------------------------------------------
# BAZA BILAN ISHLASH
# ---------------------------------------------------------------------------

def db_init():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS eslatmalar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            matn TEXT NOT NULL,
            due_iso TEXT NOT NULL,
            yuborildi INTEGER DEFAULT 0,
            bajarildi INTEGER DEFAULT 0
        )
        """
    )
    conn.commit()
    conn.close()


def db_add(chat_id: int, matn: str, due_iso: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "INSERT INTO eslatmalar (chat_id, matn, due_iso) VALUES (?, ?, ?)",
        (chat_id, matn, due_iso),
    )
    conn.commit()
    new_id = cur.lastrowid
    conn.close()
    return new_id


def db_mark_done(eslatma_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE eslatmalar SET bajarildi = 1 WHERE id = ?", (eslatma_id,))
    conn.commit()
    conn.close()


def db_get_pending(chat_id: int):
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, matn, due_iso FROM eslatmalar "
        "WHERE chat_id = ? AND bajarildi = 0 ORDER BY due_iso ASC",
        (chat_id,),
    ).fetchall()
    conn.close()
    return rows


def db_get_due_unsent(now_iso: str):
    """Vaqti kelgan va hali yuborilmagan eslatmalarni topadi."""
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT id, chat_id, matn FROM eslatmalar "
        "WHERE yuborildi = 0 AND due_iso <= ?",
        (now_iso,),
    ).fetchall()
    conn.close()
    return rows


def db_mark_sent(eslatma_id: int):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("UPDATE eslatmalar SET yuborildi = 1 WHERE id = ?", (eslatma_id,))
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# BUYRUQLAR
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Assalomu alaykum! Men TEXNOMIX eslatma botiman.\n\n"
        "/yangi - yangi vazifa yoki zakaz qo'shish\n"
        "/royxat - bajarilmagan eslatmalar ro'yxati\n"
        "/bugun - bugungi eslatmalar"
    )


async def yangi_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Vazifa yoki zakaz matnini yozing.\n"
        "Masalan: \"Sherzod aka uchun 20L shampun tayyor bo'lishi kerak\""
    )
    return MATN


async def yangi_matn(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["matn"] = update.message.text
    await update.message.reply_text(
        "Qachon? Sanani yozing (KUN.OY masalan: 07.07) yoki \"bugun\" / \"ertaga\" deb yozing."
    )
    return SANA


async def yangi_sana(update: Update, context: ContextTypes.DEFAULT_TYPE):
    matn = update.message.text.strip().lower()
    bugun = datetime.now(TIMEZONE).date()

    if matn == "bugun":
        sana = bugun
    elif matn == "ertaga":
        from datetime import timedelta
        sana = bugun + timedelta(days=1)
    else:
        try:
            kun, oy = matn.split(".")
            sana = bugun.replace(month=int(oy), day=int(kun))
            if sana < bugun:
                sana = sana.replace(year=sana.year + 1)
        except Exception:
            await update.message.reply_text(
                "Formatni tushunmadim. Masalan: 07.07 yoki \"bugun\" / \"ertaga\" deb yozing."
            )
            return SANA

    context.user_data["sana"] = sana
    await update.message.reply_text("Soat nechida? Masalan: 18:00")
    return VAQT


async def yangi_vaqt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    matn = update.message.text.strip()
    try:
        soat, minut = matn.split(":")
        sana = context.user_data["sana"]
        due = datetime(
            sana.year, sana.month, sana.day, int(soat), int(minut), tzinfo=TIMEZONE
        )
    except Exception:
        await update.message.reply_text("Formatni tushunmadim. Masalan: 18:00")
        return VAQT

    chat_id = update.effective_chat.id
    vazifa_matni = context.user_data["matn"]
    eslatma_id = db_add(chat_id, vazifa_matni, due.isoformat())

    await update.message.reply_text(
        f"✅ Saqlandi!\n\n{vazifa_matni}\n🕒 {due.strftime('%d.%m.%Y %H:%M')}"
    )
    return ConversationHandler.END


async def bekor_qilish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Bekor qilindi.")
    return ConversationHandler.END


async def royxat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    rows = db_get_pending(chat_id)
    if not rows:
        await update.message.reply_text("Hozircha bajarilmagan eslatma yo'q.")
        return

    for eslatma_id, matn, due_iso in rows:
        due = datetime.fromisoformat(due_iso)
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("✅ Bajarildi", callback_data=f"done:{eslatma_id}")]]
        )
        await update.message.reply_text(
            f"🕒 {due.strftime('%d.%m.%Y %H:%M')}\n{matn}", reply_markup=keyboard
        )


async def bugun(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    rows = db_get_pending(chat_id)
    bugun_sana = datetime.now(TIMEZONE).date()
    topildi = False
    for eslatma_id, matn, due_iso in rows:
        due = datetime.fromisoformat(due_iso)
        if due.date() == bugun_sana:
            topildi = True
            keyboard = InlineKeyboardMarkup(
                [[InlineKeyboardButton("✅ Bajarildi", callback_data=f"done:{eslatma_id}")]]
            )
            await update.message.reply_text(
                f"🕒 {due.strftime('%H:%M')}\n{matn}", reply_markup=keyboard
            )
    if not topildi:
        await update.message.reply_text("Bugunga eslatma yo'q.")


async def tugma_bosildi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    action, eslatma_id = query.data.split(":")
    if action == "done":
        db_mark_done(int(eslatma_id))
        await query.edit_message_text(query.message.text + "\n\n✅ Bajarildi deb belgilandi.")


# ---------------------------------------------------------------------------
# FON VAZIFASI: har daqiqada tekshirib, vaqti kelgan eslatmalarni yuborish
# ---------------------------------------------------------------------------

async def tekshir_va_yubor(context: ContextTypes.DEFAULT_TYPE):
    now_iso = datetime.now(TIMEZONE).isoformat()
    rows = db_get_due_unsent(now_iso)
    for eslatma_id, chat_id, matn in rows:
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("✅ Bajarildi", callback_data=f"done:{eslatma_id}")]]
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"⏰ ESLATMA!\n\n{matn}",
            reply_markup=keyboard,
        )
        db_mark_sent(eslatma_id)


# ---------------------------------------------------------------------------
# ISHGA TUSHIRISH
# ---------------------------------------------------------------------------

def main():
    db_init()
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("yangi", yangi_start)],
        states={
            MATN: [MessageHandler(filters.TEXT & ~filters.COMMAND, yangi_matn)],
            SANA: [MessageHandler(filters.TEXT & ~filters.COMMAND, yangi_sana)],
            VAQT: [MessageHandler(filters.TEXT & ~filters.COMMAND, yangi_vaqt)],
        },
        fallbacks=[CommandHandler("bekor", bekor_qilish)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(CommandHandler("royxat", royxat))
    app.add_handler(CommandHandler("bugun", bugun))
    app.add_handler(CallbackQueryHandler(tugma_bosildi))

    # Har 60 soniyada bir marta tekshiradi
    app.job_queue.run_repeating(tekshir_va_yubor, interval=60, first=5)

    logger.info("Bot ishga tushdi...")
    app.run_polling()


if __name__ == "__main__":
    main()
