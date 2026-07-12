# TEXNOMIX Eslatma bot

Jarayonlar (Xitoy uskuna / mijozga yetkazish), Moliya (qarzlar) va Retseptlar
(tannarx hisob-kitobi) uchun Telegram bot. Ma'lumot mahalliy SQLite faylida
(`texnomix.db`) saqlanadi — bot qayta ishga tushsa ham yo'qolmaydi.

## Xavfsizlik — MUHIM

Bot tokenini **hech qachon** kodga yozib qo'ymang yoki chatda ulashmang.
Token faqat muhit o'zgaruvchisi (`BOT_TOKEN`) sifatida beriladi. Agar token
avval ochiq joyda (masalan chatda) ko'rinib qolgan bo'lsa, BotFather orqali
uni bekor qilib (`/revoke`), yangisini oling.

## Mahalliy ishga tushirish

```bash
pip install -r requirements.txt
export BOT_TOKEN="sizning_tokeningiz"
python bot.py
```

## Railway'ga joylashtirish

1. Yangi loyiha yarating, ushbu papkani (yoki GitHub reponi) ulang
2. **Variables** bo'limiga qo'shing: `BOT_TOKEN` = sizning tokeningiz
3. Railway `requirements.txt` va `Procfile`ni avtomatik taniydi (worker turi)
4. Deploy qiling — loglar oynasida "Bot ishga tushdi (polling)" yozuvini ko'rasiz

Eslatma: SQLite fayli konteyner disk fazosida saqlanadi. Railway'da doimiy
disk (persistent volume) yoqilmagan bo'lsa, konteyner qayta yaratilganda
(masalan yangi deploy paytida) ma'lumot yo'qolishi mumkin — shuning uchun
Railway loyihasida **Volume** qo'shib, uni `/app` (yoki loyiha ildiziga) bog'lab
qo'yish tavsiya etiladi.

## Foydalanish

- `/start` — botni ishga tushirish, asosiy menyu
- 📦 Jarayonlar — faol jarayonlar ro'yxati, `/yangi_jarayon` — yangi qo'shish
- 💰 Moliya — qarzlar holati, `/yangi_qarz` — yangi qo'shish
- 🧪 Retseptlar — retseptlar ro'yxati, `/yangi_retsept` — yangi qo'shish
- 🔔 Bugun — bugungi va kechikkan ishlarni darhol ko'rish
- Har kuni ertalab soat **08:00 (Toshkent)** da bot avtomatik kechikkan/bugungi
  ishlar haqida xabar yuboradi (agar shunday ishlar bo'lsa)
- Retsept tafsilotida chiqadigan `/hisobla_<id> <kg>` buyrug'i orqali istalgan
  partiya hajmiga ingredientlar va tannarxni qayta hisoblaysiz
- `/bekor` — istalgan bosqichda joriy amalni bekor qilish
