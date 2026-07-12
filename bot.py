"""
TEXNOMIX Eslatma bot
Jarayonlar (Xitoy uskuna / mijozga yetkazish), Moliya (qarzlar) va
Retseptlar (tannarx hisob-kitobi) uchun Telegram bot.

Ishga tushirish:
    export BOT_TOKEN="..."          # Telegram token, hech qachon kodga yozmang
    python bot.py

Railway'da: Variables bo'limiga BOT_TOKEN qo'shing, Start command: python bot.py
"""
import os
import logging
import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

import db
from constants import TYPE_META, CUR_LABEL

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("texnomix_bot")

MAIN_MENU = ReplyKeyboardMarkup(
    [["📦 Jarayonlar", "💰 Moliya"], ["🧪 Retseptlar", "🔔 Bugun"]],
    resize_keyboard=True,
)

# ---- conversation states ----
(P_TYPE, P_TITLE, P_COUNTERPARTY, P_DUE) = range(4)
(D_DIRECTION, D_PARTY, D_AMOUNT, D_CURRENCY, D_DUE) = range(10, 15)
(R_NAME, R_CATEGORY, R_BASE, R_INGREDIENTS) = range(20, 24)
(U_STAGE, U_NOTE) = range(30, 32)


def fmt_num(n):
    try:
        return f"{float(n):,.2f}".rstrip("0").rstrip(".")
    except (TypeError, ValueError):
        return str(n)


def parse_date(text):
    text = text.strip()
    if text in ("-", "/skip", "yoq", "yo'q"):
        return None, True
    for pattern in ("%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y"):
        try:
            d = datetime.datetime.strptime(text, pattern).date()
            return d.isoformat(), True
        except ValueError:
            continue
    return None, False


def days_until(due_date_iso):
    if not due_date_iso:
        return None
    today = datetime.date.today()
    d = datetime.date.fromisoformat(due_date_iso)
    return (d - today).days


def due_label(due_date_iso):
    n = days_until(due_date_iso)
    if n is None:
        return ""
    if n < 0:
        return f" ⚠️ {abs(n)} kun kechikdi"
    if n == 0:
        return " ⏰ Bugun"
    if n == 1:
        return " ⏰ Ertaga"
    return f" ⏰ {n} kundan keyin"


# ============================================================ BASIC COMMANDS

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Salom! Men TEXNOMIX Eslatma botiman.\n\n"
        "📦 Jarayonlar — Xitoy uskuna va mijozga yetkazish bosqichlarini kuzataman\n"
        "💰 Moliya — kimga qarzdorligingiz, kim sizga qarzdor\n"
        "🧪 Retseptlar — formulalar va tannarx hisob-kitobi\n"
        "🔔 Bugun — bugungi va kechikkan ishlar\n\n"
        "Har kuni ertalab (8:00) kechikkan/bugungi ishlar haqida avtomatik xabar yuboraman.",
        reply_markup=MAIN_MENU,
    )


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Bekor qilindi.", reply_markup=MAIN_MENU)
    return ConversationHandler.END


async def today_summary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    procs = db.overdue_and_today_processes(user_id)
    debts = db.overdue_and_today_debts(user_id)
    if not procs and not debts:
        await update.message.reply_text("Bugun uchun kechikkan yoki muddati kelgan ish yo'q. 👍", reply_markup=MAIN_MENU)
        return
    lines = ["🔔 *Bugungi eslatmalar:*\n"]
    for p in procs:
        meta = TYPE_META[p["type"]]
        lines.append(f"{meta['label']} — *{p['title']}*{due_label(p['due_date'])}\n   Bosqich: {p['stage']}")
    for d in debts:
        direction = "Menga qarzdor" if d["direction"] == "owed_to_me" else "Men qarzdorman"
        lines.append(f"💰 {direction}: *{d['party']}* — {fmt_num(d['amount'])} {CUR_LABEL[d['currency']]}{due_label(d['due_date'])}")
    await update.message.reply_text("\n\n".join(lines), parse_mode="Markdown", reply_markup=MAIN_MENU)


# ============================================================ PROCESSES

async def processes_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    procs = db.list_processes(user_id, status="active")
    if not procs:
        await update.message.reply_text(
            "Hozircha faol jarayon yo'q.\n\n➕ Yangi qo'shish uchun /yangi_jarayon",
            reply_markup=MAIN_MENU,
        )
        return
    await update.message.reply_text(f"📦 Faol jarayonlar ({len(procs)} ta):\n\n➕ Yangi qo'shish: /yangi_jarayon")
    for p in procs:
        meta = TYPE_META[p["type"]]
        text = f"{meta['label']}\n*{p['title']}*"
        if p["counterparty"]:
            text += f" — {p['counterparty']}"
        text += f"\n📍 {p['stage']}{due_label(p['due_date'])}"
        kb = [[
            InlineKeyboardButton("🔄 Bosqich", callback_data=f"pupdate:{p['id']}"),
            InlineKeyboardButton("✅ Yakunlash", callback_data=f"pdone:{p['id']}"),
            InlineKeyboardButton("🗑", callback_data=f"pdel:{p['id']}"),
        ]]
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def new_process_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[InlineKeyboardButton(m["label"], callback_data=f"ptype:{k}")] for k, m in TYPE_META.items()]
    await update.message.reply_text("Jarayon turini tanlang:", reply_markup=InlineKeyboardMarkup(kb))
    return P_TYPE


async def new_process_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    type_key = query.data.split(":")[1]
    context.user_data["new_process"] = {"type": type_key}
    await query.edit_message_text(f"Tur: {TYPE_META[type_key]['label']}\n\nNomini yozing (masalan: Avtomoyka uskunasi):")
    return P_TITLE


async def new_process_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_process"]["title"] = update.message.text.strip()
    await update.message.reply_text("Kontragent nomi (yetkazib beruvchi/mijoz)? Yo'q bo'lsa \"-\" yozing.")
    return P_COUNTERPARTY


async def new_process_counterparty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data["new_process"]["counterparty"] = "" if text == "-" else text
    await update.message.reply_text("Eslatma sanasi? (YYYY-MM-DD, masalan 2026-07-20). Kerak bo'lmasa \"-\" yozing.")
    return P_DUE


async def new_process_due(update: Update, context: ContextTypes.DEFAULT_TYPE):
    due, ok = parse_date(update.message.text)
    if not ok:
        await update.message.reply_text("Sana formati noto'g'ri. Masalan: 2026-07-20 yoki \"-\"")
        return P_DUE
    data = context.user_data.pop("new_process")
    stage = TYPE_META[data["type"]]["stages"][0]
    db.add_process(update.effective_user.id, data["type"], data["title"], data["counterparty"], stage, due, "")
    await update.message.reply_text(f"✅ Qo'shildi: {data['title']} ({stage})", reply_markup=MAIN_MENU)
    return ConversationHandler.END


async def process_update_stage_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pid = query.data.split(":")[1]
    p = db.get_process(pid)
    if not p:
        await query.edit_message_text("Topilmadi.")
        return
    stages = TYPE_META[p["type"]]["stages"]
    kb = [[InlineKeyboardButton(("✅ " if s == p["stage"] else "") + s, callback_data=f"pstage:{pid}:{i}")] for i, s in enumerate(stages)]
    await query.message.reply_text(f"«{p['title']}» — yangi bosqichni tanlang:", reply_markup=InlineKeyboardMarkup(kb))


async def process_set_stage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, pid, idx = query.data.split(":")
    p = db.get_process(pid)
    if not p:
        await query.edit_message_text("Topilmadi.")
        return ConversationHandler.END
    new_stage = TYPE_META[p["type"]]["stages"][int(idx)]
    context.user_data["update_process"] = {"id": pid, "stage": new_stage}
    await query.edit_message_text(f"Yangi bosqich: {new_stage}\n\nIzoh qo'shasizmi? Yo'q bo'lsa \"-\" yozing.")
    return U_NOTE


async def process_set_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    note = "" if text == "-" else text
    data = context.user_data.pop("update_process")
    db.update_process_stage(data["id"], data["stage"], note)
    await update.message.reply_text(f"✅ Yangilandi: {data['stage']}", reply_markup=MAIN_MENU)
    return ConversationHandler.END


async def process_toggle_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pid = query.data.split(":")[1]
    db.toggle_process_complete(pid)
    p = db.get_process(pid)
    status = "yakunlandi ✅" if p and p["completed"] else "faollashtirildi"
    await query.edit_message_text(f"{p['title']} — {status}")


async def process_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    pid = query.data.split(":")[1]
    p = db.get_process(pid)
    title = p["title"] if p else ""
    db.delete_process(pid)
    await query.edit_message_text(f"🗑 O'chirildi: {title}")


# ============================================================ FINANCE (DEBTS)

async def finance_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    totals = db.debt_totals(user_id)
    lines = ["💰 *Moliya holati*\n"]
    owed = totals.get("owed_to_me", {})
    iowe = totals.get("i_owe", {})
    lines.append("📥 Menga berishlari kerak: " + (", ".join(f"{fmt_num(v)} {CUR_LABEL[c]}" for c, v in owed.items()) or "0"))
    lines.append("📤 Men berishim kerak: " + (", ".join(f"{fmt_num(v)} {CUR_LABEL[c]}" for c, v in iowe.items()) or "0"))
    lines.append("\n➕ Yangi qarz qo'shish: /yangi_qarz")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")

    debts = db.list_debts(user_id, status="unpaid")
    for d in debts:
        direction = "📥 Menga qarzdor" if d["direction"] == "owed_to_me" else "📤 Men qarzdorman"
        text = f"{direction}\n*{d['party']}* — {fmt_num(d['amount'])} {CUR_LABEL[d['currency']]}{due_label(d['due_date'])}"
        if d["note"]:
            text += f"\n_{d['note']}_"
        kb = [[
            InlineKeyboardButton("✅ To'landi", callback_data=f"dpaid:{d['id']}"),
            InlineKeyboardButton("🗑", callback_data=f"ddel:{d['id']}"),
        ]]
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def new_debt_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = [[
        InlineKeyboardButton("📥 Menga berishi kerak", callback_data="ddir:owed_to_me"),
        InlineKeyboardButton("📤 Men berishim kerak", callback_data="ddir:i_owe"),
    ]]
    await update.message.reply_text("Yo'nalishni tanlang:", reply_markup=InlineKeyboardMarkup(kb))
    return D_DIRECTION


async def new_debt_direction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    direction = query.data.split(":")[1]
    context.user_data["new_debt"] = {"direction": direction}
    await query.edit_message_text("Kim bilan? (Ism yoki kompaniya nomi)")
    return D_PARTY


async def new_debt_party(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_debt"]["party"] = update.message.text.strip()
    await update.message.reply_text("Summani kiriting (raqam bilan, masalan 1500000):")
    return D_AMOUNT


async def new_debt_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().replace(" ", "").replace(",", "")
    try:
        amount = float(text)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Summa noto'g'ri. Faqat raqam kiriting, masalan: 1500000")
        return D_AMOUNT
    context.user_data["new_debt"]["amount"] = amount
    kb = [[
        InlineKeyboardButton("so'm", callback_data="dcur:UZS"),
        InlineKeyboardButton("USD", callback_data="dcur:USD"),
        InlineKeyboardButton("CNY (yuan)", callback_data="dcur:CNY"),
    ]]
    await update.message.reply_text("Valyuta:", reply_markup=InlineKeyboardMarkup(kb))
    return D_CURRENCY


async def new_debt_currency(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    currency = query.data.split(":")[1]
    context.user_data["new_debt"]["currency"] = currency
    await query.edit_message_text("Muddat? (YYYY-MM-DD, yoki \"-\" agar kerak bo'lmasa)")
    return D_DUE


async def new_debt_due(update: Update, context: ContextTypes.DEFAULT_TYPE):
    due, ok = parse_date(update.message.text)
    if not ok:
        await update.message.reply_text("Sana formati noto'g'ri. Masalan: 2026-07-20 yoki \"-\"")
        return D_DUE
    data = context.user_data.pop("new_debt")
    db.add_debt(update.effective_user.id, data["party"], data["direction"], data["amount"], data["currency"], due, "")
    await update.message.reply_text(f"✅ Qo'shildi: {data['party']} — {fmt_num(data['amount'])} {CUR_LABEL[data['currency']]}", reply_markup=MAIN_MENU)
    return ConversationHandler.END


async def debt_toggle_paid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    did = query.data.split(":")[1]
    db.toggle_debt_paid(did)
    d = db.get_debt(did)
    status = "to'landi ✅" if d and d["paid"] else "to'lanmagan deb belgilandi"
    await query.edit_message_text(f"{d['party']} — {status}")


async def debt_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    did = query.data.split(":")[1]
    d = db.get_debt(did)
    party = d["party"] if d else ""
    db.delete_debt(did)
    await query.edit_message_text(f"🗑 O'chirildi: {party}")


# ============================================================ RECIPES

async def recipes_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    recipes = db.list_recipes(user_id)
    if not recipes:
        await update.message.reply_text("Hozircha retsept yo'q.\n\n➕ Yangi qo'shish: /yangi_retsept", reply_markup=MAIN_MENU)
        return
    await update.message.reply_text(f"🧪 Retseptlar ({len(recipes)} ta):\n\n➕ Yangi: /yangi_retsept")
    for r in recipes:
        full = db.get_recipe(r["id"])
        _, total_cost, per_kg = db.recipe_cost(full)
        text = f"*{r['name']}*"
        if r["category"]:
            text += f" — {r['category']}"
        text += f"\nBaza: {fmt_num(r['base_batch'])} kg · {len(full['ingredients'])} ingredient\nTannarx: {fmt_num(per_kg)} so'm/kg"
        kb = [[
            InlineKeyboardButton("📋 Tafsilot", callback_data=f"rview:{r['id']}"),
            InlineKeyboardButton("🗑", callback_data=f"rdel:{r['id']}"),
        ]]
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))


async def recipe_view(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rid = query.data.split(":")[1]
    r = db.get_recipe(rid)
    if not r:
        await query.edit_message_text("Topilmadi.")
        return
    total_weight, total_cost, per_kg = db.recipe_cost(r)
    lines = [f"*{r['name']}*\n"]
    for ing in r["ingredients"]:
        lines.append(f"• {ing['name']}: {fmt_num(ing['amount'])} kg × {fmt_num(ing['price'])} so'm = {fmt_num(ing['amount'] * ing['price'])} so'm")
    lines.append(f"\nJami: {fmt_num(total_weight)} kg — {fmt_num(total_cost)} so'm")
    lines.append(f"Tannarx: *{fmt_num(per_kg)} so'm/kg*")
    lines.append(f"\nBoshqa hajmga hisoblash: /hisobla_{r['id']} <kg>\nMasalan: /hisobla_{r['id']} 1500")
    await query.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def recipe_calc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # command looks like /hisobla_<recipe_id> <kg>
    cmd = update.message.text.split()
    if len(cmd) < 2:
        await update.message.reply_text("Foydalanish: /hisobla_<retsept_id> <kg>")
        return
    rid = cmd[0].split("_", 1)[1].lstrip("@").split("@")[0]
    try:
        target_kg = float(cmd[1].replace(",", "."))
    except ValueError:
        await update.message.reply_text("Hajm noto'g'ri. Masalan: /hisobla_abc123 1500")
        return
    r = db.get_recipe(rid)
    if not r:
        await update.message.reply_text("Retsept topilmadi.")
        return
    factor = target_kg / r["base_batch"] if r["base_batch"] else 0
    _, total_cost, _ = db.recipe_cost(r)
    lines = [f"*{r['name']}* — {fmt_num(target_kg)} kg uchun:\n"]
    for ing in r["ingredients"]:
        lines.append(f"• {ing['name']}: {fmt_num(ing['amount'] * factor)} kg")
    lines.append(f"\nUmumiy tannarx: *{fmt_num(total_cost * factor)} so'm*")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def recipe_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    rid = query.data.split(":")[1]
    r = db.get_recipe(rid)
    name = r["name"] if r else ""
    db.delete_recipe(rid)
    await query.edit_message_text(f"🗑 O'chirildi: {name}")


async def new_recipe_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_recipe"] = {"ingredients": []}
    await update.message.reply_text("Retsept nomi? (masalan: Kontaktsiz avtomoyka shampuni)")
    return R_NAME


async def new_recipe_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_recipe"]["name"] = update.message.text.strip()
    await update.message.reply_text("Kategoriya? (masalan: Avtomoyka kimyosi). Kerak bo'lmasa \"-\"")
    return R_CATEGORY


async def new_recipe_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    context.user_data["new_recipe"]["category"] = "" if text == "-" else text
    await update.message.reply_text("Baza partiya hajmi (kg)? Masalan: 1000")
    return R_BASE


async def new_recipe_base(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        base = float(update.message.text.strip().replace(",", "."))
        if base <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Noto'g'ri son. Masalan: 1000")
        return R_BASE
    context.user_data["new_recipe"]["base_batch"] = base
    await update.message.reply_text(
        "Endi ingredientlarni yuboring, har birini alohida xabarda, formatda:\n"
        "`Nomi, miqdor(kg), narxi(so'm/kg)`\n"
        "Masalan: `SLES, 120, 18000`\n\n"
        "Hammasini kiritib bo'lgach /tayyor deb yozing.",
        parse_mode="Markdown",
    )
    return R_INGREDIENTS


async def new_recipe_ingredient(update: Update, context: ContextTypes.DEFAULT_TYPE):
    parts = [p.strip() for p in update.message.text.split(",")]
    if len(parts) < 2:
        await update.message.reply_text("Format: Nomi, miqdor, narxi — masalan: SLES, 120, 18000")
        return R_INGREDIENTS
    name = parts[0]
    try:
        amount = float(parts[1].replace(",", "."))
        price = float(parts[2].replace(",", ".")) if len(parts) > 2 else 0.0
    except (ValueError, IndexError):
        await update.message.reply_text("Miqdor/narx raqam bo'lishi kerak. Masalan: SLES, 120, 18000")
        return R_INGREDIENTS
    context.user_data["new_recipe"]["ingredients"].append({"name": name, "amount": amount, "price": price})
    count = len(context.user_data["new_recipe"]["ingredients"])
    await update.message.reply_text(f"✅ Qo'shildi ({count} ta). Yana qo'shing yoki /tayyor deb yozing.")
    return R_INGREDIENTS


async def new_recipe_done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data.pop("new_recipe", None)
    if not data or not data["ingredients"]:
        await update.message.reply_text("Hech bo'lmasa bitta ingredient kerak.", reply_markup=MAIN_MENU)
        return ConversationHandler.END
    db.add_recipe(update.effective_user.id, data["name"], data.get("category", ""), data["base_batch"], data["ingredients"], "")
    await update.message.reply_text(f"✅ Retsept saqlandi: {data['name']} ({len(data['ingredients'])} ta ingredient)", reply_markup=MAIN_MENU)
    return ConversationHandler.END


# ============================================================ DAILY REMINDER JOB

async def daily_reminder_job(context: ContextTypes.DEFAULT_TYPE):
    for user_id in db.all_user_ids():
        procs = db.overdue_and_today_processes(user_id)
        debts = db.overdue_and_today_debts(user_id)
        if not procs and not debts:
            continue
        lines = ["🔔 *Xayrli tong! Bugungi eslatmalar:*\n"]
        for p in procs:
            meta = TYPE_META[p["type"]]
            lines.append(f"{meta['label']} — *{p['title']}*{due_label(p['due_date'])}")
        for d in debts:
            direction = "Menga qarzdor" if d["direction"] == "owed_to_me" else "Men qarzdorman"
            lines.append(f"💰 {direction}: *{d['party']}* — {fmt_num(d['amount'])} {CUR_LABEL[d['currency']]}{due_label(d['due_date'])}")
        try:
            await context.bot.send_message(chat_id=user_id, text="\n".join(lines), parse_mode="Markdown")
        except Exception as e:
            logger.warning("Could not send reminder to %s: %s", user_id, e)


# ============================================================ APP WIRING

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise SystemExit("BOT_TOKEN environment variable topilmadi. Uni Railway Variables bo'limida sozlang.")

    db.init_db()
    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bekor", cancel))
    app.add_handler(MessageHandler(filters.Regex("^🔔 Bugun$"), today_summary))
    app.add_handler(MessageHandler(filters.Regex("^📦 Jarayonlar$"), processes_menu))
    app.add_handler(MessageHandler(filters.Regex("^💰 Moliya$"), finance_menu))
    app.add_handler(MessageHandler(filters.Regex("^🧪 Retseptlar$"), recipes_menu))
    app.add_handler(MessageHandler(filters.Regex(r"^/hisobla_\S+"), recipe_calc))

    process_conv = ConversationHandler(
        entry_points=[CommandHandler("yangi_jarayon", new_process_start)],
        states={
            P_TYPE: [CallbackQueryHandler(new_process_type, pattern="^ptype:")],
            P_TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_process_title)],
            P_COUNTERPARTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_process_counterparty)],
            P_DUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_process_due)],
        },
        fallbacks=[CommandHandler("bekor", cancel)],
    )
    app.add_handler(process_conv)

    debt_conv = ConversationHandler(
        entry_points=[CommandHandler("yangi_qarz", new_debt_start)],
        states={
            D_DIRECTION: [CallbackQueryHandler(new_debt_direction, pattern="^ddir:")],
            D_PARTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_debt_party)],
            D_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_debt_amount)],
            D_CURRENCY: [CallbackQueryHandler(new_debt_currency, pattern="^dcur:")],
            D_DUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_debt_due)],
        },
        fallbacks=[CommandHandler("bekor", cancel)],
    )
    app.add_handler(debt_conv)

    recipe_conv = ConversationHandler(
        entry_points=[CommandHandler("yangi_retsept", new_recipe_start)],
        states={
            R_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_recipe_name)],
            R_CATEGORY: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_recipe_category)],
            R_BASE: [MessageHandler(filters.TEXT & ~filters.COMMAND, new_recipe_base)],
            R_INGREDIENTS: [
                CommandHandler("tayyor", new_recipe_done),
                MessageHandler(filters.TEXT & ~filters.COMMAND, new_recipe_ingredient),
            ],
        },
        fallbacks=[CommandHandler("bekor", cancel)],
    )
    app.add_handler(recipe_conv)

    stage_update_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(process_set_stage, pattern="^pstage:")],
        states={
            U_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_set_note)],
        },
        fallbacks=[CommandHandler("bekor", cancel)],
    )
    app.add_handler(stage_update_conv)

    app.add_handler(CallbackQueryHandler(process_update_stage_prompt, pattern="^pupdate:"))
    app.add_handler(CallbackQueryHandler(process_toggle_done, pattern="^pdone:"))
    app.add_handler(CallbackQueryHandler(process_delete, pattern="^pdel:"))
    app.add_handler(CallbackQueryHandler(debt_toggle_paid, pattern="^dpaid:"))
    app.add_handler(CallbackQueryHandler(debt_delete, pattern="^ddel:"))
    app.add_handler(CallbackQueryHandler(recipe_view, pattern="^rview:"))
    app.add_handler(CallbackQueryHandler(recipe_delete, pattern="^rdel:"))

    # Daily reminder at 08:00 Asia/Tashkent (UTC+5 -> 03:00 UTC)
    if app.job_queue:
        app.job_queue.run_daily(daily_reminder_job, time=datetime.time(hour=3, minute=0))

    logger.info("Bot ishga tushdi (polling).")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
