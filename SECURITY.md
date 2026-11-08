# راهنمای امن‌سازی ponyDinal

> وضعیت: توکن‌ها و کلیدهای حساس قبلاً به‌صورت هاردکد در فایل `ponyDinal.py` و در
> **ریپوی عمومی** منتشر شده‌اند. تغییر کد به‌تنهایی کافی نیست — باید کلیدها
> **باطل/چرخش (rotate)** شوند و **تاریخچه‌ی گیت** پاک شود.

---

## ۱) اقدام فوری — باطل کردن کلیدهای لو رفته

### الف) توکن ربات‌ها (بحرانی‌ترین)
در تلگرام به **@BotFather** بروید:

1. `/mybots` → ربات را انتخاب کنید
2. **API Token** → **Revoke current token**
3. توکن جدید را در فایل `.env` (فقط روی سرور) قرار دهید

این کار را برای **هر دو ربات** انجام دهید:
- ربات اصلی (`BOT_TOKEN`)
- ربات کمکی/اینلاین (`HELPER_BOT_TOKEN` → `ShabahHelper_bot`)

> توجه: تا وقتی توکن باطل نشده، هر کسی می‌تواند پیام‌های ربات شما را بخواند،
> به‌جای شما پنل بفرستد و از سهمیه/شهرت اپ API استفاده کند.

### ب) `API_HASH` / `API_ID`
این‌ها قابل Revoke نیستند. اگر نگران سوءاستفاده هستید:

1. به <https://my.telegram.org> → **API development tools** بروید
2. یک اپ جدید بسازید و `api_id` / `api_hash` جدید بگیرید
3. در `.env` جایگزین کنید

⚠️ تغییر `api_id`/`api_hash` می‌تواند روی فایل‌های `sessions/*.session` موجود اثر
بگذارد؛ قبل از تغییر از `sessions/` بکاپ بگیرید و در یک محیط تست امتحان کنید.

### ج) `INLINE_SECRET`
این رشته رمزِ داخلیِ کوئری اینلاین پنل است و در ریپو عمومی دیده شده. یک مقدار
تصادفی جدید بسازید:

```bash
python3 -c "import secrets; print('shabah_' + secrets.token_urlsafe(24))"
```

مقدار جدید را در `.env` بگذارید و **همه‌ی نمونه‌های در حال اجرا** را با همان
مقدار به‌روزرسانی کنید (در غیر این صورت پنل‌های اینلاین از کار می‌افتند).

### د) اکانت‌های کاربران
فایل‌های `sessions/*.session` معادل **دسترسی کامل به اکانت** هستند.
اگر این فایل‌ها یا بکاپ‌هایشان در جایی عمومی (ریپو، سرور مشترک، فایل zip) بوده‌اند،
آن اکانت‌ها را در Telegram → Devices/Active Sessions خارج کنید و رمز دوم (2FA) را
تغییر دهید. رمزهای دو مرحله‌ای کاربران هم هرگز نباید لاگ شوند.

---

## ۲) پاک کردن تاریخچه‌ی گیت (ایتداژ ضروری)

کامیت جدید با مقدار خالی کافی **نیست**؛ توکن‌ها در تاریخچه می‌مانند و از
فورک‌ها/کش‌ها قابل بازیابی‌اند. یکی از دو روش:

### روش الف: `git filter-repo` (پیشنهادی)
```bash
pip install git-filter-repo
# فایل حاوی رشته‌های حساس را بسازید (هر خط: literal:مقدار)
cat > /tmp/replacements.txt <<'R'
«توکن_ربات_اصلی»==>REDACTED
«توکن_ربات_کمکی»==>REDACTED
«api_hash_قدیمی»==>REDACTED
«inline_secret_قدیمی»==>REDACTED
R
git filter-repo --replace-text /tmp/replacements.txt
git remote add origin git@github.com:pedramneamatzadeh-ux/ponyDinal.git
git push --force --all
git push --force --tags
```

### روش ب: BFG Repo-Cleaner
```bash
java -jar bfg.jar --replace-text /tmp/replacements.txt
git reflog expire --expire=now --all && git gc --prune=now --aggressive
git push --force
```

سپس:
- در GitHub → **Settings → General → Danger Zone** هیچ کش دیگری نمی‌ماند؛ اما
  **فورک‌ها و PR‌های قدیمی** ممکن است کد لو رفته را نگه دارند → آن‌ها را حذف کنید.
- اگر ریپو عمومی است و ممکن است کسی clone کرده باشد، **باطل کردن توکن‌ها** تنها
  راه واقعی است (بند ۱).

---

## ۳) روش استقرار امن

### الف) فایل `.env`
```bash
cp .env.example .env
chmod 600 .env          # فقط مالک بتواند بخواند
# مقادیر واقعی را پر کنید
```
`.env` در `.gitignore` قرار دارد و هرگز نباید کامیت شود.

### ب) systemd (نمونه)
```ini
[Service]
WorkingDirectory=/opt/ponyDinal
EnvironmentFile=/opt/ponyDinal/.env
ExecStart=/opt/ponyDinal/.venv/bin/python ponyDinal.py
User=ponydinal
NoNewPrivileges=true
PrivateTmp=true
Restart=on-failure
```

### ج) Docker (نمونه)
```bash
docker run -d --env-file .env -v "$PWD/sessions:/app/sessions" ponyDinal
```
`.env` را داخل ایمیج `COPY` نکنید.

---

## ۴) چک‌لیست نهایی

- [ ] توکن `BOT_TOKEN` باطل و چرخش داده شد
- [ ] توکن `HELPER_BOT_TOKEN` باطل و چرخش داده شد
- [ ] `INLINE_SECRET` جدید ساخته و در همه‌ی نمونه‌ها اعمال شد
- [ ] در صورت نیاز `API_ID` / `API_HASH` جدید گرفته شد
- [ ] کد حساس‌ها را از `.env` می‌خواند (انجام شد ✅)
- [ ] `.env` و `sessions/` در `.gitignore` هستند (انجام شد ✅)
- [ ] تاریخچه‌ی گیت پاک و force-push شد
- [ ] فورک‌های قدیمی ریپو حذف شدند
- [ ] ریپو در صورت امکان Private شد
- [ ] `chmod 600 .env` روی سرور ست شد
- [ ] `errors.log` و `users.json` بکاپ‌شان رمزنگاری‌شده نگهداری می‌شود
      (شماره تلفن و اطلاعات کاربران در آن‌هاست)

---

## ۵) جلوگیری از تکرار

پیش از هر کامیت:
```bash
git diff --cached | grep -nE "AA[A-Za-z0-9_-]{30,}|[0-9]{8,10}:AA" && echo "⛔ توکن در استیج است!" || echo "✅ پاک"
```

پیشنهاد بلندمدت: `pre-commit` با ابزارهایی مثل `gitleaks` یا `detect-secrets`، و
روشن کردن **Secret Scanning** در GitHub (Settings → Code security).
