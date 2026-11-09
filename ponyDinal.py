
def _translate_bot_errors(e):
    err_text = str(e)
    # اگر خطا مربوط به رمز دو مرحله‌ای یا CheckPasswordRequest بود
    if "CheckPasswordRequest" in err_text or ("password" in err_text.lower() and "invalid" in err_text.lower()):
        return "❌ رمز عبوری که وارد کردید نامعتبر است (لطفاً رمز دو مرحله‌ای تلگرام را بررسی کنید)."
    return err_text

# -*- coding: utf-8 -*-
import asyncio, io, json, os, re, time, sys, random, platform, html as html_lib
from datetime import datetime, timedelta
from pathlib import Path
from difflib import get_close_matches
from telethon import TelegramClient, events, types
from telethon.errors import (SessionPasswordNeededError, FloodWaitError,
    MessageIdInvalidError, MessageNotModifiedError)
from telethon.tl.functions.messages import (
    GetInlineBotResultsRequest, SendInlineBotResultRequest,
    EditInlineBotMessageRequest)
from telethon.tl.functions.contacts import ResolveUsernameRequest
from telethon.tl.functions.users import GetFullUserRequest
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.photos import UpdateProfilePhotoRequest
from telethon.tl.types import (
    ReplyInlineMarkup, KeyboardButtonRow, KeyboardButtonUrl,
    MessageMediaDocument, DocumentAttributeFilename, DocumentAttributeAudio,
)

# آیا InputBotInlineMessageMediaAuto پارامتر media را می‌پذیرد؟
try:
    import inspect as _inspect
    from telethon.tl.types import (
        InputBotInlineMessageMediaAuto as _IBIMA)
    _INLINE_MEDIA_SUPPORTED = (
        "media" in _inspect.signature(_IBIMA.__init__).parameters)
except Exception:  # pragma: no cover
    _INLINE_MEDIA_SUPPORTED = False


# ═══════════════════════════════════════════════════════
# تسک‌های پس‌زمینه — رفرنس نگه می‌داریم تا GC وسط کار جمع‌شان نکند
# ═══════════════════════════════════════════════════════
_BG_TASKS = set()


def _spawn(coro):
    """جایگزین امن asyncio.create_task برای تسک‌هایی که رفرنس نگه نمی‌داریم."""
    try:
        task = asyncio.ensure_future(coro)
    except RuntimeError:
        return None
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)
    return task


def _bg_task_count():
    return len(_BG_TASKS)


# ═══════════════════════════════════════════════════════
# بارگذاری متغیرهای محیطی از فایل .env (بدون وابستگی خارجی)
# ═══════════════════════════════════════════════════════
_ENV_FILE = Path(__file__).resolve().parent / ".env"


def _load_dotenv(path=_ENV_FILE):
    """فایل .env را می‌خواند و در os.environ قرار می‌دهد.
    متغیرهای محیطی واقعیِ سیستم همیشه اولویت دارند (setdefault).
    """
    try:
        if not path.exists():
            return
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            if key.startswith("export "):
                key = key[len("export "):].strip()
            val = val.split("  #")[0].strip()
            if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                val = val[1:-1]
            os.environ.setdefault(key, val)
    except Exception as e:
        print(f"⚠️ خطا در خواندن {path}: {e}")


_load_dotenv()


def _env(name, default=None, required=False, cast=None):
    """خواندن یک متغیر محیطی با اعتبارسنجی و پیام خطای فارسی."""
    val = os.environ.get(name)
    if val is None or (isinstance(val, str) and val.strip() == ""):
        if required:
            raise SystemExit(
                f"❌ متغیر محیطی «{name}» تنظیم نشده است.\n"
                f"   یک فایل .env کنار {Path(__file__).name} بسازید "
                f"(نمونه: .env.example) یا از export استفاده کنید."
            )
        val = default
    if val is not None and cast is not None:
        try:
            val = cast(val)
        except (TypeError, ValueError):
            raise SystemExit(f"❌ مقدار متغیر «{name}» نامعتبر است: {val!r}")
    return val


# ═══════════════════════════════════════════════════════
# توکن‌ها و API  (همه از .env / متغیرهای محیطی — هیچ مقدار حساسی اینجا نباشد)
# ═══════════════════════════════════════════════════════
BOT_TOKEN = _env("BOT_TOKEN", required=True)
HELPER_BOT_TOKEN = _env("HELPER_BOT_TOKEN", default="")
HELPER_BOT_USERNAME = _env("HELPER_BOT_USERNAME", default="ShabahHelper_bot")
INLINE_SECRET = _env("INLINE_SECRET", required=True)
API_ID = _env("API_ID", required=True, cast=int)
API_HASH = _env("API_HASH", required=True)
OWNER_ID = _env("OWNER_ID", required=True, cast=int)
BOT_SELF_ID = 0

PEW_BOT_USERNAME = "PewPewBot"
PEW_BOT_ID = 0

# ═══════════════════════════════════════════════════════
# کانستنت‌ها
# ═══════════════════════════════════════════════════════
STATS_START_TIME = time.time()
MAX_ALLIES_PER_TEAM = 4
MAX_TEAM_ATTACK_MEMBERS = 7
SESSION_DIR = Path("./sessions"); SESSION_DIR.mkdir(exist_ok=True)
TEMP_DIR = Path("./temp_files"); TEMP_DIR.mkdir(exist_ok=True)
BANNER_MEDIA_DIR = TEMP_DIR / "banners"; BANNER_MEDIA_DIR.mkdir(exist_ok=True)
GENDER_DIR = TEMP_DIR / "gender_banners"; GENDER_DIR.mkdir(exist_ok=True)
USERS_FILE = "users.json"; BANNERS_FILE = "banners.json"
STATS_FILE = "stats.json"; ERRORS_LOG = "errors.log"; BATTLE_FILE = "battle_config.json"
GENDER_BANNERS_FILE = "gender_banners.json"
RUNTIME_FILE = "runtime.json"; MONITOR_FILE = "monitor.json"
CMD = "،"
GAME_BOT_USERNAME = "CardinalRPG_Bot"; GAME_BOT_ID = 8876785338
CITY_EXIT_COMMAND = "🏰 خروج از شهر!"
CITY_MAX_RETRIES = 5; CITY_RETRY_DELAY = 30; CITY_WARNING_DELAY = 30 * 60
SELL_CHECK_INTERVAL = 3600
TRANSFER_FAST_DELAY = 6 * 3600; TRANSFER_SLOW_DELAY = 24 * 3600
TRANSFER_INVALID_ID_RETRY = 6 * 3600
CHAT_BLOCK_DURATION = 15 * 60
DAILY_GIFT_INTERVAL = 25 * 60 * 60
TEAM_ATTACK_JOIN_TIMEOUT = 180
TEAM_ATTACK_JOIN_RETRY = 15
QUEUE_MAX_SIZE = 200
PONY_RETRY_DELAY = 15
DUNGEON_MONSTERS = ["کیو کیو", "زارک", "کرون", "مورگان", "دراکس",
                    "ورکس", "نیسا", "گروم", "زرو", "موکو"]
DUNGEON_INTERVAL = 15 * 60; DUNGEON_FLOW_TIMEOUT = 300
HUNT_FLOOR_COOLDOWN = 30 * 60; HUNT_FLOOR_STEP = 2; HUNT_LEVEL_RETRY_STEP = 5
BANNER_TARGET_W = 1520; BANNER_TARGET_H = 500
BANNER_BLUR_RADIUS = 25; BANNER_DARKEN = 0.6
PEW_TARGET_SHOOT_INTERVAL = 15
PEW_TARGET_DEATH_WAIT = 11 * 60
PEW_TARGET_SHOOT_CMD = "شلیک"
PEW_HP_HEAL_THRESHOLD = 100
PEW_HEAL_INTERVAL = 4
PEW_HEAL_MAX_ATTEMPTS = 100
PERSIAN_DIGITS_TRANS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
# ═══════════════════════════════════════════════════════
# استایل‌ها و فونت‌ها
# ═══════════════════════════════════════════════════════
HTML_STYLES = {
    "none":       {"label": "❌ بدون استایل", "open": "", "close": ""},
    "bold":       {"label": "🅱️ پررنگ", "open": "<b>", "close": "</b>"},
    "italic":     {"label": "ℹ️ کج", "open": "<i>", "close": "</i>"},
    "bolditalic": {"label": "🅱️ℹ️ پررنگ و کج", "open": "<b><i>", "close": "</i></b>"},
    "underline":  {"label": "🇺 زیرخط‌دار", "open": "<u>", "close": "</u>"},
    "strike":     {"label": "🇸 خط‌خورده", "open": "<s>", "close": "</s>"},
    "spoiler":    {"label": "🙈 اسپویلر", "open": "<tg-spoiler>", "close": "</tg-spoiler>"},
    "mono":       {"label": "⌨️ تک‌عرض", "open": "<code>", "close": "</code>"},
    "code":       {"label": "📦 بلوک کد", "open": "<pre>", "close": "</pre>"},
    "quote":      {"label": "💬 نقل‌قول", "open": "<blockquote>", "close": "</blockquote>"},
    "kashida":    {"label": "〰️ کشیده", "open": "", "close": ""},
    # Legacy alias retained for users who previously selected `.استایل pre`.
    "pre":        {"label": "📦 بلوک کد (قدیمی)", "open": "<pre>", "close": "</pre>"},
}
EN_LOWER = "abcdefghijklmnopqrstuvwxyz"
EN_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
EN_DIGITS = "0123456789"
ENGLISH_FONTS = {
    "none":  {"label": "❌ بدون فونت", "lower": EN_LOWER, "upper": EN_UPPER, "digits": EN_DIGITS},
    "bold":  {"label": "𝐁 Bold",
              "lower": "𝐚𝐛𝐜𝐝𝐞𝐟𝐠𝐡𝐢𝐣𝐤𝐥𝐦𝐧𝐨𝐩𝐪𝐫𝐬𝐭𝐮𝐯𝐰𝐱𝐲𝐳",
              "upper": "𝐀𝐁𝐂𝐃𝐄𝐅𝐆𝐇𝐈𝐉𝐊𝐋𝐌𝐍𝐎𝐏𝐐𝐑𝐒𝐓𝐔𝐕𝐖𝐗𝐘𝐙",
              "digits": "𝟎𝟏𝟐𝟑𝟒𝟓𝟔𝟕𝟖𝟗"},
    "italic":{"label": "𝑰 Italic",
              "lower": "𝑎𝑏𝑐𝑑𝑒𝑓𝑔ℎ𝑖𝑗𝑘𝑙𝑚𝑛𝑜𝑝𝑞𝑟𝑠𝑡𝑢𝑣𝑤𝑥𝑦𝑧",
              "upper": "𝐴𝐵𝐶𝐷𝐸𝐹𝐺𝐻𝐼𝐽𝐾𝐿𝑀𝑁𝑂𝑃𝑄𝑅𝑆𝑇𝑈𝑉𝑊𝑋𝑌𝑍", "digits": EN_DIGITS},
    "boldit":{"label": "𝑩 BoldItalic",
              "lower": "𝒂𝒃𝒄𝒅𝒆𝒇𝒈𝒉𝒊𝒋𝒌𝒍𝒎𝒏𝒐𝒑𝒒𝒓𝒔𝒕𝒖𝒗𝒘𝒙𝒚𝒛",
              "upper": "𝑨𝑩𝑪𝑫𝑬𝑭𝑮𝑯𝑰𝑱𝑲𝑳𝑴𝑵𝑶𝑷𝑸𝑹𝑺𝑻𝑼𝑽𝑾𝑿𝒀𝒁", "digits": EN_DIGITS},
    "script":{"label": "𝒮 Script",
              "lower": "𝒶𝒷𝒸𝒹ℯ𝒻ℊ𝒽𝒾𝒿𝓀𝓁𝓂𝓃ℴ𝓅𝓆𝓇𝓈𝓉𝓊𝓋𝓌𝓍𝓎𝓏",
              "upper": "𝒜ℬ𝒞𝒟ℰℱ𝒢ℋℐ𝒥𝒦ℒℳ𝒩𝒪𝒫𝒬ℛ𝒮𝒯𝒰𝒱𝒲𝒳𝒴𝒵", "digits": EN_DIGITS},
    "bscript":{"label": "𝓢 BoldScript",
              "lower": "𝓪𝓫𝓬𝓭𝓮𝓯𝓰𝓱𝓲𝓳𝓴𝓵𝓶𝓷𝓸𝓹𝓺𝓻𝓼𝓽𝓾𝓿𝔀𝔁𝔂𝔃",
              "upper": "𝓐𝓑𝓒𝓓𝓔𝓕𝓖𝓗𝓘𝓙𝓚𝓛𝓜𝓝𝓞𝓟𝓠𝓡𝓢𝓣𝓤𝓥𝓦𝓧𝓨𝓩", "digits": EN_DIGITS},
    "fraktur":{"label": "𝔉 Fraktur",
              "lower": "𝔞𝔟𝔠𝔡𝔢𝔣𝔤𝔥𝔦𝔧𝔨𝔩𝔪𝔫𝔬𝔭𝔮𝔯𝔰𝔱𝔲𝔳𝔴𝔵𝔶𝔷",
              "upper": "𝔄𝔅ℭ𝔇𝔈𝔉𝔊ℌℑ𝔍𝔎𝔏𝔐𝔑𝔒𝔓𝔔ℜ𝔖𝔗𝔘𝔙𝔚𝔛𝔜ℨ", "digits": EN_DIGITS},
    "double":{"label": "𝔻 Double-Struck",
              "lower": "𝕒𝕓𝕔𝕕𝕖𝕗𝕘𝕙𝕚𝕛𝕜𝕝𝕞𝕟𝕠𝕡𝕢𝕣𝕤𝕥𝕦𝕧𝕨𝕩𝕪𝕫",
              "upper": "𝔸𝔹ℂ𝔻𝔼𝔽𝔾ℍ𝕀𝕁𝕂𝕃𝕄ℕ𝕆ℙℚℝ𝕊𝕋𝕌𝕍𝕎𝕏𝕐ℤ",
              "digits": "𝟘𝟙𝟚𝟛𝟜𝟝𝟞𝟟𝟠𝟡"},
    "mono":  {"label": "𝙼 Monospace",
              "lower": "𝚊𝚋𝚌𝚍𝚎𝚏𝚐𝚑𝚒𝚓𝚔𝚕𝚖𝚗𝚘𝚙𝚚𝚛𝚜𝚝𝚞𝚟𝚠𝚡𝚢𝚣",
              "upper": "𝙰𝙱𝙲𝙳𝙴𝙵𝙶𝙷𝙸𝙹𝙺𝙻𝙼𝙽𝙾𝙿𝚀𝚁𝚂𝚃𝚄𝚅𝚆𝚇𝚈𝚉",
              "digits": "𝟶𝟷𝟸𝟹𝟺𝟻𝟼𝟽𝟾𝟿"},
    "circled":{"label": "Ⓒ Circled",
              "lower": "ⓐⓑⓒⓓⓔⓕⓖⓗⓘⓙⓚⓛⓜⓝⓞⓟⓠⓡⓢⓣⓤⓥⓦⓧⓨⓩ",
              "upper": "ⒶⒷⒸⒹⒺⒻⒼⒽⒾⒿⓀⓁⓂⓃⓄⓅⓆⓇⓈⓉⓊⓋⓌⓍⓎⓏ",
              "digits": "⓪①②③④⑤⑥⑦⑧⑨"},
    "fullwidth":{"label": "Ｆ Fullwidth",
              "lower": "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ",
              "upper": "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ",
              "digits": "０１２３４５６７８９"},
}

# ═══════════════════════════════════════════════════════
# توابع پایه
# ═══════════════════════════════════════════════════════
def normalize_digits(text):
    if not text: return text
    return text.translate(PERSIAN_DIGITS_TRANS)

def _normalize_persian(text):
    if not text: return ""
    t = text.replace('\u200c', ' ').replace('\u200f', '').replace('\u200e', '')
    t = t.replace('\u00a0', ' ').replace('\u200b', '')
    return re.sub(r'\s+', ' ', t)

def load_json(filename, default=None):
    if not os.path.exists(filename): return {} if default is None else default
    try:
        with open(filename, "r", encoding="utf-8") as f: return json.load(f)
    except: return {} if default is None else default

def save_json(filename, data):
    """ذخیرهٔ اتمیک JSON؛ خطا هرگز باعث کرش هندلرها نمی‌شود."""
    tmp = filename + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, filename)
        return True
    except TypeError:
        # دادهٔ غیرقابل‌سریالایز (مثلاً آبجکت تلگرام) → رشته‌ای ذخیره می‌شود
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            os.replace(tmp, filename)
            log_error(f"save_json fallback(default=str) for {filename}")
            return True
        except Exception as e:
            log_error(f"save_json fallback {filename}: {_translate_bot_errors(e)}")
            return False
    except Exception as e:
        log_error(f"save_json {filename}: {_translate_bot_errors(e)}")
        return False

def log_error(msg):
    try:
        with open(ERRORS_LOG, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat()}] {msg}\n")
    except: pass

def _resize_banner_image(src_path, dst_path,
                          target_w=BANNER_TARGET_W, target_h=BANNER_TARGET_H):
    try:
        from PIL import Image, ImageFilter, ImageEnhance
    except ImportError:
        log_error("Pillow نصب نیست"); return False
    try:
        img = Image.open(src_path)
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            bg_white = Image.new("RGB", img.size, (255, 255, 255))
            bg_white.paste(img, mask=img.split()[-1])
            img = bg_white
        else:
            img = img.convert("RGB")
        W, H = img.size
        scale = min(target_w / W, target_h / H)
        new_w = max(1, int(W * scale)); new_h = max(1, int(H * scale))
        resized = img.resize((new_w, new_h), Image.LANCZOS)
        bg_scale = max(target_w / W, target_h / H)
        bg_w = max(target_w, int(W * bg_scale))
        bg_h = max(target_h, int(H * bg_scale))
        bg = img.resize((bg_w, bg_h), Image.LANCZOS)
        l = (bg_w - target_w) // 2; t = (bg_h - target_h) // 2
        bg = bg.crop((l, t, l + target_w, t + target_h))
        bg = bg.filter(ImageFilter.GaussianBlur(radius=BANNER_BLUR_RADIUS))
        bg = ImageEnhance.Brightness(bg).enhance(BANNER_DARKEN)
        x = (target_w - new_w) // 2; y = (target_h - new_h) // 2
        bg.paste(resized, (x, y))
        bg.save(dst_path, "JPEG", quality=88, optimize=True)
        return True
    except Exception as e:
        log_error(f"_resize_banner_image {src_path}: {_translate_bot_errors(e)}"); return False

def extract_msg_id_from_link(link):
    if not link: return None
    link = link.strip()
    m = re.match(r'^(?:https?://)?t\.me/(?:c/)?[^/]+/(\d+)(?:\?.*)?$', link)
    if m:
        try: return int(m.group(1))
        except: return None
    return None

def is_pew_bot_sender(sender_obj):
    if not sender_obj: return False
    try:
        s_uname = (getattr(sender_obj, "username", "") or "").lower().lstrip("@")
        s_id = getattr(sender_obj, "id", None)
        if PEW_BOT_USERNAME and s_uname == PEW_BOT_USERNAME.lower().lstrip("@"):
            return True
        if PEW_BOT_ID and s_id and int(s_id) == int(PEW_BOT_ID):
            return True
    except: pass
    return False
    # ═══════════════════════════════════════════════════════
# لود دیتابیس‌ها
# ═══════════════════════════════════════════════════════
users_db = load_json(USERS_FILE, {"users": {}})
if "users" not in users_db: users_db["users"] = {}
if "managers" not in users_db: users_db["managers"] = []
banners_db = load_json(BANNERS_FILE); stats_db = load_json(STATS_FILE, {})
battle_db = load_json(BATTLE_FILE, {})
if "chats" not in battle_db:
    battle_db = {"chats": {}}; save_json(BATTLE_FILE, battle_db)
gender_banners_db = load_json(GENDER_BANNERS_FILE, {"girl": [], "boy": []})
monitor_db = load_json(MONITOR_FILE, {})
if "girl" not in gender_banners_db: gender_banners_db["girl"] = []
if "boy" not in gender_banners_db: gender_banners_db["boy"] = []

# ═══════════════════════════════════════════════════════
# متغیرهای Global
# ═══════════════════════════════════════════════════════
bot_client = None
helper_bot = None
user_clients = {}
login_states = {}
broadcast_tasks = {}; pending_battle_tasks = {}
recent_ally_joins = {}; recent_farakhans = {}; broadcast_waiting = {}
sell_mode_users = {}; sell_queues = {}
AUTO_SEND_CONFIG = {
    "شکار": {"command": "🦖 شکار هیولا", "interval": 10 * 60 + 10},
    "سیاه": {"command": "💀 سیاه‌چال مخفی", "interval": 7 * 60 + 10},
}
YES_PROMPTS = [
    {"match": ["کریستال شانس", "استفاده"], "reply": "✅ بله، استفاده شود"},
    {"match": ["گزینه", "بله", "خیر"], "reply": "✅ بله، استفاده شود"},
    {"match": ["کریستال شانس"], "reply": "✅ بله، استفاده شود"},
]
auto_send_tasks = {}; auto_send_status = {}
transfer_configs = {}; transfer_queues = {}; user_workflow_locks = {}
chat_blocks = {}
escape_config = {}; return_config = {}
daily_gift_status = {}; daily_gift_tasks = {}
team_attack_ready = {}; team_attack_pending = {}
defense_pending = {}
pony_config = {}
transfer_materials_config = {}
transfer_items_config = {}; transfer_scheduler_tasks = {}
pony_waiting = {}; pony_tasks = {}; pony_state = {}; naz_auto_tasks = {}
dungeon_config = {}; dungeon_tasks = {}; dungeon_waiting = {}
hunt_floor_state = {}; ally_paused = {}; yes_retry_state = {}
floor_test_config = {}; hunt_fail_counter = {}; pm_banner_states = {}
# Opaque callback tokens bind every inline panel button to its originating account.
panel_callback_tokens = {}
pm_banner_add_timeout_tasks = {}
pew_art_config = {}; pew_art_stats = {}; pew_art_pending = {}
pew_ring_config = {}; pew_ring_state = {}; pew_ring_tasks = {}
pew_target_config = {}; pew_target_tasks = {}; pew_target_state = {}
pew_dog_config = {}; pew_dog_tasks = {}; pew_dog_state = {}
pew_master = {}
pew_heal_tasks = {}
_CURRENT_INLINE = {}
pm_panel_chat = {}
name_emoji_tasks = {}
random_profile_tasks = {}
monitor_tasks = {}
NAME_EMOJI_PRESETS = ["🌸", "💖", "✨", "🌙", "🦋", "💫", "🌈", "🍀"]
fishing_status = {}
fishing_tasks = {}
user_current_floor = {}
pew_hunt_groups = {}
pew_user_group = {}
_syncing_users = set()
_ttl_processing = set()
_runtime_save_task = None

# ═══════════════════════════════════════════════════════
# توابع کمکی برای پنل‌های متنی
# ═══════════════════════════════════════════════════════
def _p_bar(pct, width=10):
    pct = max(0, min(100, int(pct)))
    filled = round(pct * width / 100)
    return "▰" * filled + "▱" * (width - filled)

def _p_status_line(label, on, extra="", hint=""):
    if on:
        icon = "🟢"
        status = "✅ <b>روشن</b>"
    else:
        icon = "🔴"
        status = "⭕ <b>خاموش</b>"
    line = f"  {icon} {label}  ─  {status}"
    if extra:
        line += f"  ·  <code>{extra}</code>"
    if not on and hint:
        line += f"\n     💡 <code>{hint}</code>"
    return line

def _p_sep(): return "  ┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈"

def _p_foot(): return "  ━━━━━━━━━━━━━━━━━━"

# ═══════════════════════════════════════════════════════
# Runtime Persist
# ═══════════════════════════════════════════════════════
def _tk(k):
    if isinstance(k, tuple): return "|".join(str(x) for x in k)
    return str(k)

def _uk(s):
    if "|" in s:
        parts = s.split("|")
        try: return tuple(int(p) for p in parts)
        except: return tuple(parts)
    try: return int(s)
    except: return s

def _strip_task(v):
    if not isinstance(v, dict): return v
    return {kk: vv for kk, vv in v.items() if kk != "task" and kk != "scheduler_task"}

def save_runtime():
    try:
        data = {
            "sell_mode_users": {str(k): {"enabled": v.get("enabled", False)}
                                 for k, v in sell_mode_users.items()},
            "auto_send_status": {str(k): dict(v) for k, v in auto_send_status.items()},
            "transfer_configs": {str(k): _strip_task(v) for k, v in transfer_configs.items()},
            "escape_config": {str(k): dict(v) for k, v in escape_config.items()},
            "return_config": {str(k): dict(v) for k, v in return_config.items()},
            "daily_gift_status": {str(k): v for k, v in daily_gift_status.items()},
            "pony_config": {_tk(k): dict(v) for k, v in pony_config.items()},
            "pony_state": {_tk(k): dict(v) for k, v in pony_state.items()},
            "dungeon_config": {_tk(k): dict(v) for k, v in dungeon_config.items()},
            "hunt_floor_state": {str(k): dict(v) for k, v in hunt_floor_state.items()},
            "ally_paused": {_tk(k): True for k in ally_paused.keys()},
            "pew_art_config": {str(k): dict(v) for k, v in pew_art_config.items()},
            "pew_art_stats": {str(k): dict(v) for k, v in pew_art_stats.items()},
            "pew_ring_config": {_tk(k): dict(v) for k, v in pew_ring_config.items()},
            "pew_ring_state": {_tk(k): dict(v) for k, v in pew_ring_state.items()},
            "pew_target_config": {_tk(k): _strip_task(v) for k, v in pew_target_config.items()},
            "pew_target_state": {_tk(k): dict(v) for k, v in pew_target_state.items()},
            "pew_dog_config": {_tk(k): dict(v) for k, v in pew_dog_config.items()},
            "pew_dog_state": {_tk(k): dict(v) for k, v in pew_dog_state.items()},
            "pew_master": {str(k): dict(v) for k, v in pew_master.items()},
            "pm_panel_chat": {str(k): v for k, v in pm_panel_chat.items()},
            "pew_hunt_groups": pew_hunt_groups,
            "pew_user_group": {str(k): v for k, v in pew_user_group.items()},
        }
        data["transfer_materials_config"] = {str(k): v for k, v in transfer_materials_config.items()}
        data["transfer_items_config"] = {
            str(k): _strip_task(v) for k, v in transfer_items_config.items()}
        save_json(RUNTIME_FILE, data)
    except Exception as e:
        log_error(f"save_runtime: {_translate_bot_errors(e)}")

def load_runtime():
    data = load_json(RUNTIME_FILE, {})
    try:
        for k, v in data.get("sell_mode_users", {}).items():
            try: sell_mode_users[int(k)] = {"enabled": bool(v.get("enabled")), "scheduler_task": None}
            except: pass
        for k, v in data.get("auto_send_status", {}).items():
            try: auto_send_status[int(k)] = dict(v)
            except: pass
        for k, v in data.get("transfer_configs", {}).items():
            try:
                cfg = dict(v); cfg["task"] = None; cfg["mode"] = "fast"
                transfer_configs[int(k)] = cfg
            except: pass
        for k, v in data.get("escape_config", {}).items():
            try: escape_config[int(k)] = dict(v)
            except: pass
        for k, v in data.get("return_config", {}).items():
            try: return_config[int(k)] = dict(v)
            except: pass
        for k, v in data.get("daily_gift_status", {}).items():
            try: daily_gift_status[int(k)] = bool(v)
            except: pass
        for k, v in data.get("pony_config", {}).items():
            try: pony_config[_uk(k)] = dict(v)
            except: pass
        for k, v in data.get("pony_state", {}).items():
            try: pony_state[_uk(k)] = dict(v)
            except: pass
        for k, v in data.get("dungeon_config", {}).items():
            try: dungeon_config[_uk(k)] = dict(v)
            except: pass
        for k, v in data.get("hunt_floor_state", {}).items():
            try: hunt_floor_state[int(k)] = dict(v)
            except: pass
        for k in data.get("ally_paused", {}).keys():
            try: ally_paused[_uk(k)] = True
            except: pass
        for k, v in data.get("pew_art_config", {}).items():
            try: pew_art_config[int(k)] = dict(v)
            except: pass
        for k, v in data.get("pew_art_stats", {}).items():
            try: pew_art_stats[int(k)] = dict(v)
            except: pass
        for k, v in data.get("pew_ring_config", {}).items():
            try: pew_ring_config[_uk(k)] = dict(v)
            except: pass
        for k, v in data.get("pew_ring_state", {}).items():
            try: pew_ring_state[_uk(k)] = dict(v)
            except: pass
        for k, v in data.get("pew_target_config", {}).items():
            try:
                cfg = dict(v); cfg["task"] = None
                pew_target_config[_uk(k)] = cfg
            except: pass
        for k, v in data.get("pew_target_state", {}).items():
            try: pew_target_state[_uk(k)] = dict(v)
            except: pass
        for k, v in data.get("pew_dog_config", {}).items():
            try: pew_dog_config[_uk(k)] = dict(v)
            except: pass
        for k, v in data.get("pew_dog_state", {}).items():
            try: pew_dog_state[_uk(k)] = dict(v)
            except: pass
        for k, v in data.get("pew_master", {}).items():
            try: pew_master[int(k)] = dict(v)
            except: pass
        for k, v in data.get("pm_panel_chat", {}).items():
            try: pm_panel_chat[int(k)] = int(v)
            except: pass
        for k, v in data.get("pew_hunt_groups", {}).items():
            try:
                v["owner"] = int(v.get("owner"))
                v["members"] = [int(m) for m in v.get("members", [])]
                v["disabled_users"] = [int(m) for m in v.get("disabled_users", [])]
                pew_hunt_groups[k] = v
            except: pass
        for k, v in data.get("pew_user_group", {}).items():
            try: pew_user_group[int(k)] = v
            except: pass
        for k, v in data.get("transfer_materials_config", {}).items():
            try: transfer_materials_config[int(k)] = dict(v)
            except: pass
        for k, v in data.get("transfer_items_config", {}).items():
            try: transfer_items_config[int(k)] = dict(v)
            except: pass
        log_error("✅ runtime loaded")
    except Exception as e:
        log_error(f"load_runtime: {_translate_bot_errors(e)}")

def schedule_save_runtime():
    global _runtime_save_task
    if _runtime_save_task and not _runtime_save_task.done():
        return
    async def _delayed():
        await asyncio.sleep(2)
        save_runtime()
        global _runtime_save_task
        _runtime_save_task = None
    try:
        _runtime_save_task = asyncio.create_task(_delayed())
    except:
        save_runtime()

async def _restart_runtime_tasks():
    await asyncio.sleep(8)
    try:
        for uid, v in list(sell_mode_users.items()):
            _t = v.get("scheduler_task")
            if v.get("enabled") and (_t is None or _t.done()):
                sell_mode_users[uid]["scheduler_task"] = asyncio.create_task(sell_scheduler(uid))
        
        for uid, v in list(transfer_items_config.items()):
            if v.get("enabled"):
                _ensure_transfer_scheduler(uid, "item")
                
        for uid, v in list(transfer_materials_config.items()):
            if v.get("enabled"):
                _ensure_transfer_scheduler(uid, "material")
        for uid, v in list(auto_send_status.items()):
            for key, on in v.items():
                if on and key in AUTO_SEND_CONFIG:
                    try: start_auto_send(uid, key)
                    except: pass
        for uid, cfg in list(transfer_configs.items()):
            _t = cfg.get("task")
            if _t is not None and not _t.done():
                # جلوگیری از دو scheduler هم‌زمان برای یک کاربر (انتقال تکراری)
                continue
            if cfg.get("enabled") and cfg.get("c_id"):
                cfg["mode"] = "fast"
                cfg["task"] = asyncio.create_task(transfer_scheduler(uid))
        for uid, on in list(daily_gift_status.items()):
            if on:
                try: start_daily_gift(uid)
                except: pass
        for uid, info in list(users_db.get("users", {}).items()):
            try:
                if info.get("name_emoji", {}).get("enabled") and is_user_active(int(uid)):
                    start_name_emoji_task(int(uid))
                if info.get("random_profile", {}).get("enabled") and is_user_active(int(uid)):
                    start_random_profile_task(int(uid))
            except: pass
        for uid, cfg in list(monitor_db.items()):
            try:
                if cfg.get("enabled") and is_user_active(int(uid)):
                    start_monitor_task(int(uid))
            except: pass
        for key, cfg in list(pony_config.items()):
            if cfg.get("collect") and is_user_active(key[0]):
                try: start_pony_task(key[0], key[1])
                except: pass
            if cfg.get("naz_enabled") and is_user_active(key[0]):
                try: start_naz_auto_task(key[0], key[1])
                except: pass
        for key, cfg in list(dungeon_config.items()):
            if cfg.get("enabled") and is_user_active(key[0]):
                try: start_dungeon_task(key[0], key[1])
                except: pass
        log_error(f"🔍 ring configs count: {len(pew_ring_config)}")
        for key, cfg in list(pew_ring_config.items()):
            log_error(f"🔍 ring check: key={key} enabled={cfg.get('enabled')} active={is_user_active(key[0])}")
            if cfg.get("enabled") and is_user_active(key[0]):
                try: 
                    ok = start_pew_ring_task(key[0], key[1])
                    log_error(f"🔍 ring started: {ok} for {key}")
                except Exception as e: 
                    log_error(f"❌ ring start fail: {_translate_bot_errors(e)}")
        for key, cfg in list(pew_target_config.items()):
            if cfg.get("enabled") and is_user_active(key[0]):
                try: start_pew_target_task(key[0], key[1], key[2])
                except: pass
        for key, cfg in list(pew_dog_config.items()):
            if cfg.get("enabled") and is_user_active(key[0]):
                try: start_pew_dog_task(key[0], key[1])
                except: pass
        log_error("🔄 runtime tasks restarted")
    except Exception as e:
        log_error(f"_restart_runtime_tasks: {_translate_bot_errors(e)}")
        # ═══════════════════════════════════════════════════════
# User / Gender / Banner
# ═══════════════════════════════════════════════════════
def _save_gb(): save_json(GENDER_BANNERS_FILE, gender_banners_db)

def get_user_gender(uid):
    return users_db["users"].get(str(uid), {}).get("gender")

def set_user_gender(uid, gender):
    uid_s = str(uid); _ensure_user(uid_s)
    users_db["users"][uid_s]["gender"] = gender
    save_json(USERS_FILE, users_db)

def get_user_banner_id(uid):
    return users_db["users"].get(str(uid), {}).get("banner_id")

def set_user_banner_id(uid, bid):
    uid_s = str(uid); _ensure_user(uid_s)
    old_bid = users_db["users"][uid_s].get("banner_id")
    if old_bid:
        for g in ("girl", "boy"):
            for b in gender_banners_db.get(g, []):
                if b["id"] == old_bid and int(uid) in b.get("users", []):
                    b["users"].remove(int(uid))
    users_db["users"][uid_s]["banner_id"] = bid
    if bid:
        b = get_gender_banner_by_id(bid)
        if b is not None:
            b.setdefault("users", [])
            if int(uid) not in b["users"]:
                b["users"].append(int(uid))
    save_json(USERS_FILE, users_db); _save_gb()

def get_gender_banner_by_id(bid):
    if not bid: return None
    for g in ("girl", "boy"):
        for b in gender_banners_db.get(g, []):
            if b["id"] == bid: return b
    return None

def add_gender_banner(gender, file_path, uploaded_by):
    bid = f"{gender}_{int(time.time())}_{random.randint(1000,9999)}"
    item = {"id": bid, "file": file_path, "likes_by": [], "dislikes_by": [],
        "users": [], "uploaded_by": int(uploaded_by),
        "uploaded_at": datetime.now().isoformat()}
    gender_banners_db.setdefault(gender, []).append(item)
    _save_gb(); return item

def delete_gender_banner(bid):
    for g in ("girl", "boy"):
        lst = gender_banners_db.get(g, [])
        for i, b in enumerate(lst):
            if b["id"] == bid:
                try: os.remove(b["file"])
                except: pass
                lst.pop(i); _save_gb()
                for u, info in users_db["users"].items():
                    if info.get("banner_id") == bid: info["banner_id"] = None
                save_json(USERS_FILE, users_db); return True
    return False

def get_user_display_banner(uid):
    bid = get_user_banner_id(uid)
    if not bid: return None
    b = get_gender_banner_by_id(bid)
    if b and os.path.exists(b["file"]): return b["file"]
    return None

# ═══════════════════════════════════════════════════════
# Style & Font
# ═══════════════════════════════════════════════════════
def get_user_html_style(uid):
    u = users_db["users"].get(str(uid), {})
    if not u.get("html_style_on", False): return None
    s = u.get("html_style", "bold")
    st = HTML_STYLES.get(s, HTML_STYLES["bold"])
    if s == "kashida": return st
    if not st["open"]: return None
    return st

def set_user_html_style_on(uid, on):
    uid_s = str(uid); _ensure_user(uid_s)
    users_db["users"][uid_s]["html_style_on"] = bool(on)
    save_json(USERS_FILE, users_db)

def set_user_html_style(uid, key):
    uid_s = str(uid); _ensure_user(uid_s)
    if key not in HTML_STYLES: key = "bold"
    users_db["users"][uid_s]["html_style"] = key
    save_json(USERS_FILE, users_db)

def get_user_font(uid):
    u = users_db["users"].get(str(uid), {})
    if not u.get("font_on", False): return None
    f = u.get("font", "none")
    if f == "none": return None
    return ENGLISH_FONTS.get(f)

def set_user_font_on(uid, on):
    uid_s = str(uid); _ensure_user(uid_s)
    users_db["users"][uid_s]["font_on"] = bool(on)
    save_json(USERS_FILE, users_db)

def set_user_font(uid, key):
    uid_s = str(uid); _ensure_user(uid_s)
    if key not in ENGLISH_FONTS: key = "none"
    users_db["users"][uid_s]["font"] = key
    save_json(USERS_FILE, users_db)

def apply_english_font(text, font):
    if not font: return text
    lower = font.get("lower", EN_LOWER); upper = font.get("upper", EN_UPPER)
    digits = font.get("digits", EN_DIGITS)
    trans = {}
    for i, c in enumerate(EN_LOWER):
        if i < len(lower): trans[ord(c)] = lower[i]
    for i, c in enumerate(EN_UPPER):
        if i < len(upper): trans[ord(c)] = upper[i]
    for i, c in enumerate(EN_DIGITS):
        if i < len(digits): trans[ord(c)] = digits[i]
    return text.translate(trans)

def _apply_persian_underline(text):
    result = []
    for c in text:
        if c in " \t\n\u200c\u200f\u200e\u00a0":
            result.append(c)
        else:
            result.append(c + "\u0332")
    return "".join(result)

def _apply_persian_strike(text):
    result = []
    for c in text:
        if c in " \t\n\u200c\u200f\u200e\u00a0":
            result.append(c)
        else:
            result.append(c + "\u0336")
    return "".join(result)

def _apply_persian_font_effects(text, font_key):
    if not text or font_key in ("none", None):
        return text
    if font_key == "underline":
        return _apply_persian_underline(text)
    if font_key == "strike":
        return _apply_persian_strike(text)
    return text

def _apply_kashida(text):
    """Add Arabic tatweel only between join-capable Persian/Arabic letters."""
    if not text: return text
    letters = set("ءآأؤإئابةتثجحخدذرزسشصضطظعغفقكلمنهوىيپچژگک")
    non_joining = set("اآأإدذرزژوؤ")
    out = []
    for i, char in enumerate(text):
        out.append(char)
        nxt = text[i + 1] if i + 1 < len(text) else ""
        if char in letters and char not in non_joining and nxt in letters:
            out.append("ـ")
    return "".join(out)


def apply_user_style(uid, text):
    if not text: return text
    u = users_db["users"].get(str(uid), {})
    transformed = False
    if u.get("font_on", False):
        fk = u.get("font", "none")
        if fk != "none":
            font = ENGLISH_FONTS.get(fk)
            if font:
                text = apply_english_font(text, font)
                transformed = True
            text = _apply_persian_font_effects(text, fk)
            transformed = True
    html_s = get_user_html_style(uid)
    if html_s and u.get("html_style") == "kashida":
        text = html_lib.escape(_apply_kashida(text))
        transformed = True
    elif html_s:
        text = f"{html_s['open']}{html_lib.escape(text)}{html_s['close']}"
        transformed = True
    elif transformed:
        # Avoid treating the user's literal angle brackets as HTML while editing.
        text = html_lib.escape(text)
    return text


def _preview_style_text(key, text):
    if key == "none": return text
    if key == "bold": return apply_english_font(text, ENGLISH_FONTS["bold"])
    if key == "italic": return apply_english_font(text, ENGLISH_FONTS["italic"])
    if key == "bolditalic": return apply_english_font(text, ENGLISH_FONTS["boldit"])
    if key == "underline": return _apply_persian_underline(text)
    if key == "strike": return _apply_persian_strike(text)
    if key == "mono": return apply_english_font(text, ENGLISH_FONTS["mono"])
    if key in ("code", "pre"): return "▤" + apply_english_font(text, ENGLISH_FONTS["mono"]) + "▤"
    if key == "quote": return "❝" + text + "❞"
    if key == "spoiler": return "▒" + text + "▒"
    if key == "kashida": return _apply_kashida(text)
    return text

def _preview_font_text(key, text):
    if key == "none": return text
    f = ENGLISH_FONTS.get(key)
    if not f: return text
    return apply_english_font(text, f)

# ═══════════════════════════════════════════════════════
# نقشه نام‌های فارسی → استایل/فونت
# ═══════════════════════════════════════════════════════
STYLE_ALIASES = {
    "none": ["بدون", "هیچ", "خالی", "پاک", "حذف", "normal", "خاموش"],
    "bold": ["بولد", "پررنگ", "پر رنگ", "ضخیم"],
    "italic": ["ایتالیک", "کج", "مورب", "خمیده"],
    "bolditalic": ["پررنگ و کج", "بولد ایتالیک", "بولد و کج"],
    "underline": ["زیرخط", "زیر خط", "خط‌زیر", "زیرین"],
    "strike": ["روخط", "رو خط", "خط‌خورده", "خط خورده", "خط‌دار"],
    "spoiler": ["مخفی", "محرمانه", "پنهان"],
    "mono": ["تک‌عرض", "تک عرض", "تکفاصله", "مونو", "monospace"],
    "code": ["بلوک کد", "کد", "کدی", "pre"],
    "quote": ["نقل قول", "نقل‌قول", "نقلقول", "کوتیشن", "نقل"],
    "kashida": ["کشیده", "کَشیده", "تطویل"],
}

FONT_ALIASES = {
    "none": ["بدون", "هیچ", "خالی", "پاک", "حذف", "none", "normal", "خاموش"],
    "bold": ["بولد", "پررنگ", "پر رنگ", "ضخیم", "bold"],
    "italic": ["ایتالیک", "کج", "مورب", "خمیده", "italic"],
    "boldit": ["بولد ایتالیک", "بولدایتالیک", "پررنگ کج", "boldit", "bolditalic"],
    "script": ["دست نویس", "دستنویس", "اسکریپت", "خطاطی", "script"],
    "bscript": ["بولد اسکریپت", "بولداسکریپت", "دست نویس ضخیم", "bscript", "boldscript"],
    "fraktur": ["فراکتور", "فراکتور قدیمی", "گوتیک", "fraktur"],
    "double": ["دوتایی", "دابل", "دوبل", "double", "double-struck", "توخالی"],
    "mono": ["مونو", "تکفاصله", "تک فاصله", "تایپی", "mono", "monospace"],
    "circled": ["دایره", "دایره‌ای", "گرد", "circled", "circle"],
    "fullwidth": ["پهن", "تمام عرض", "تمام‌عرض", "فول", "fullwidth", "full-width", "عریض"],
}

def _find_style_key(user_input):
    if not user_input: return None
    t = _normalize_persian(user_input).strip().lower()
    if t in HTML_STYLES: return t
    for key, aliases in STYLE_ALIASES.items():
        for alias in aliases:
            if _normalize_persian(alias).lower() == t:
                return key
    return None

def _find_font_key(user_input):
    if not user_input: return None
    t = _normalize_persian(user_input).strip().lower()
    if t in ENGLISH_FONTS: return t
    for key, aliases in FONT_ALIASES.items():
        for alias in aliases:
            if _normalize_persian(alias).lower() == t:
                return key
    return None

# ═══════════════════════════════════════════════════════
# Banner Type Detection
# ═══════════════════════════════════════════════════════
def _banner_media_path(uid, name):
    safe = re.sub(r'[^\w\u0600-\u06FF-]', '_', name)[:50]
    return BANNER_MEDIA_DIR / f"{uid}_{safe}"

def _detect_banner_type(msg):
    if getattr(msg, 'sticker', None):
        st = msg.sticker
        if getattr(st, 'mime_type', ''):
            mt = st.mime_type.lower()
            if 'webm' in mt: return "sticker", ".webm"
            if 'tgs' in mt: return "sticker", ".tgs"
            return "sticker", ".webp"
        return "sticker", ".webp"
    if getattr(msg, 'photo', None): return "photo", ".jpg"
    if getattr(msg, 'video', None):
        if getattr(msg, 'gif', False): return "gif", ".mp4"
        if getattr(msg.video, 'gif', False): return "gif", ".mp4"
        return "video", ".mp4"
    if getattr(msg, 'voice', None): return "voice", ".ogg"
    if getattr(msg, 'audio', None): return "audio", ".mp3"
    if getattr(msg, 'document', None):
        name = getattr(msg.document, 'mime_type', '') or ''
        if 'gif' in name: return "gif", ".gif"
        return "file", ".bin"
    return "text", None

def _type_label(t):
    return {"text": "متنی", "photo": "عکس", "gif": "گیف", "video": "ویدئو",
            "voice": "ویس", "audio": "صدا", "sticker": "استیکر",
            "file": "فایل"}.get(t, t)

def format_interval_short(seconds):
    seconds = int(seconds)
    if seconds <= 0: return "0s"
    d, rem = divmod(seconds, 86400); h, rem = divmod(rem, 3600); m, s = divmod(rem, 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    if m: parts.append(f"{m}m")
    if s: parts.append(f"{s}s")
    return " ".join(parts) if parts else "0s"

def format_interval_persian(seconds):
    seconds = int(seconds)
    if seconds <= 0: return "0 ثانیه"
    d, rem = divmod(seconds, 86400); h, rem = divmod(rem, 3600); m, s = divmod(rem, 60)
    parts = []
    if d: parts.append(f"{d} روز")
    if h: parts.append(f"{h} ساعت")
    if m: parts.append(f"{m} دقیقه")
    if s: parts.append(f"{s} ثانیه")
    if not parts: return "0 ثانیه"
    if len(parts) == 1: return parts[0]
    return " و ".join(parts)

def _fmt_iv(seconds): return format_interval_short(int(seconds))

def get_yes_reply(text):
    t = _normalize_persian(text)
    for rule in YES_PROMPTS:
        if all(k in t for k in rule["match"]): return rule["reply"]
    return None

def parse_money_amount(text):
    if text is None: return None
    t = normalize_digits(str(text).strip())
    t = t.replace(",", "").replace("،", "").replace(" ", "")
    t = t.replace("\u200c", "").replace("\u200f", "").replace("\u200e", "")
    t = t.replace("کا", "k").replace("ک", "k")
    m = re.match(r'^(\d+(?:\.\d+)?)\s*([kKmM]?)$', t)
    if not m: return None
    try: num = float(m.group(1))
    except: return None
    suffix = m.group(2).lower()
    if suffix == 'k': num *= 1000
    elif suffix == 'm': num *= 1000000
    return int(num)

def parse_interval(text):
    if not text: return None
    text = normalize_digits(text.strip()).lower().replace(" ", "")
    unit_map = {"s": "s", "ث": "s", "m": "m", "د": "m", "h": "h", "س": "h", "d": "d", "ر": "d"}
    match = re.match(r"^(\d+)([a-zآ-ی])$", text)
    if not match: return None
    value = int(match.group(1)); unit = unit_map.get(match.group(2))
    if not unit: return None
    if unit == "s": seconds = max(30, value)
    elif unit == "m": seconds = max(30, value * 60)
    elif unit == "h": seconds = max(30, value * 3600)
    elif unit == "d": seconds = max(30, value * 86400)
    else: return None
    return {"value": value, "unit": unit, "seconds": seconds}

def has_bad_separator(arg):
    if not arg: return False
    for m in re.finditer(r'[+\-*_]', arg):
        i = m.start()
        before = arg[i-1] if i > 0 else ''
        after = arg[i+1] if i+1 < len(arg) else ''
        if before != ' ' or after != ' ':
            return True
    return False

# ═══════════════════════════════════════════════════════
# Floor test config
# ═══════════════════════════════════════════════════════
def is_escape_enabled(user_id):
    return bool(escape_config.get(user_id, {}).get("enabled", True))

def is_return_enabled(user_id):
    return bool(return_config.get(user_id, {}).get("enabled", True))

def is_floor_test_enabled(user_id):
    return floor_test_config.get(int(user_id), {}).get("enabled", True)

def save_floor_test(user_id, enabled):
    floor_test_config.setdefault(int(user_id), {})["enabled"] = bool(enabled)
    uid = str(user_id); _ensure_user(uid)
    users_db["users"][uid]["floor_test"] = bool(enabled)
    save_json(USERS_FILE, users_db)
    schedule_save_runtime()

def get_max_fails(user_id):
    return int(floor_test_config.get(int(user_id), {}).get("max_fails", 2))

def save_max_fails(user_id, n):
    n = max(1, min(10, int(n)))
    floor_test_config.setdefault(int(user_id), {})["max_fails"] = n
    uid = str(user_id); _ensure_user(uid)
    users_db["users"][uid]["floor_test_max_fails"] = n
    save_json(USERS_FILE, users_db)
    schedule_save_runtime()

def _load_floor_test_from_db():
    for uid_str, info in users_db["users"].items():
        if "floor_test" in info or "floor_test_max_fails" in info:
            try:
                floor_test_config[int(uid_str)] = {
                    "enabled": bool(info.get("floor_test", True)),
                    "max_fails": int(info.get("floor_test_max_fails", 2))}
            except: pass
            # ═══════════════════════════════════════════════════════
# User Management
# ═══════════════════════════════════════════════════════
def is_grp_owner(user_id): return int(user_id) == int(OWNER_ID)
def get_managers(): return users_db.setdefault("managers", [])
def is_manager(user_id): return int(user_id) in get_managers()

def is_media_allowed(uid):
    if is_grp_owner(uid): return True
    u = users_db["users"].get(str(uid), {})
    return bool(u.get("media_allowed", False))

def set_media_allowed(uid, val):
    uid_s = str(uid); _ensure_user(uid_s)
    user = users_db["users"][uid_s]
    user["media_allowed"] = bool(val)
    # Revoking access also turns off saved TTL automation so it cannot resume later.
    if not val and int(uid) != int(OWNER_ID):
        user["ttl_enabled"] = False
    save_json(USERS_FILE, users_db)

def get_media_allowed_users():
    res = []
    for uid, info in users_db["users"].items():
        if info.get("media_allowed"):
            try: res.append(int(uid))
            except: pass
    return res

def toggle_manager(user_id):
    managers = get_managers(); uid = int(user_id)
    if uid in managers:
        managers.remove(uid); save_json(USERS_FILE, users_db); return False
    managers.append(uid); save_json(USERS_FILE, users_db); return True

def is_user_allowed(user_id):
    if is_grp_owner(user_id): return True
    user = users_db["users"].get(str(user_id))
    if user is None: return True
    return not user.get("banned", False) and not user.get("all_access_locked", False)

def set_user_access_locked(user_id, locked):
    uid = str(user_id); _ensure_user(uid)
    users_db["users"][uid]["all_access_locked"] = bool(locked)
    save_json(USERS_FILE, users_db)

# ═══════════════════════════════════════════════════════
# 🔐 قفل تک‌بخشی (هر بخش دکمهٔ قفل مستقل خودش را دارد)
# کلید قفل = همان دیتای دکمهٔ آن بخش/دکمه (مثل pn_cardinal_panel)
# ═══════════════════════════════════════════════════════
SECTION_LOCK_TITLES = {
    "pn_games": "🎮 بازی",
    "pn_cardinal_panel": "⚔ کاردینال",
    "pn_pony_main": "🐴 پونی‌لند",
    "pn_pew_panel": "🔫 پیوپیو",
    "pn_war_panel": "⚔ نبرد و حمله",
    "pn_transfer_menu": "💸 انتقال",
    "pn_transfer_info": "💰 انتقال پول",
    "pn_transfer_materials": "📦 انتقال مواد",
    "pn_transfer_items": "🎁 انتقال کالا",
    "pn_nosell_panel": "🚫 نفروش",
    "pn_return_panel": "🔙 برگشت",
    "pn_floortest_max_panel": "💀 مرگ تست طبقه",
    "pn_tools": "🛠 ابزارها",
    "pn_settings": "⚙️ تنظیمات",
    "pn_status_panel": "📊 وضعیت",
    "pn_banner_main": "📢 تبچی",
    "pn_banner_list": "📢 لیست بنرها",
    "pn_mon_main": "👁 پایش پروفایل",
    "pn_tts_panel": "🔊 متن و ویس",
    "pn_html_panel": "🎨 استایل HTML",
    "pn_font_panel": "🔤 فونت",
    "pn_ttl_panel": "🔥 TTL",
    "pn_save_panel": "📥 ذخیره",
    "pn_name_emoji_panel": "😀 ایموجی اسم",
    "pn_random_profile_panel": "📷 پروفایل رندوم",
    "pn_gender_panel": "👤 جنسیت",
    "pn_notif_panel": "🔔 اعلان‌ها",
    "pn_pew_art_panel": "🎨 پیو آرت",
    "pn_pewring_master_panel": "🏋️ پیو رینگ",
    "pn_dog_master_panel": "🐕 پیو سگ",
    "pn_pew_target_panel": "🎯 پیو هدف",
    "pn_group_hunt_panel": "🎯 شکار گروهی",
    "pn_ghunt_mgmt": "🎯 مدیریت شکار گروهی",
    "pn_gender_banners_panel": "🖼 مدیریت بنرها",
}

# دکمه‌هایی که هرگز نباید قفل/مخفی شوند
_SECTION_LOCK_IGNORE = {"", "pn_noop", "pn_close", "pn_refresh", "pn_owner"}
# بخش‌های مخصوص مالک که قفل‌کردنشان معنا ندارد
_SECTION_LOCK_OWNER_PREFIX = (
    "pn_access_", "pn_users_", "pn_user_", "pn_media_", "pn_managers",
    "pn_broadcast", "pn_gb_", "pn_banner_edit", "pn_ping", "pn_reload_",
    "pn_rmsess_", "pn_ban_", "pn_unban_", "pn_addmgr_", "pn_rmmgr_",
)


def get_locked_sections(user_id):
    """دیکشنری قفل‌های فعال کاربر: {کلید_dکمه: برچسب}"""
    info = users_db.get("users", {}).get(str(user_id), {}) or {}
    locks = info.get("locked_sections")
    if isinstance(locks, dict):
        return {str(k): str(v) for k, v in locks.items() if str(k).strip()}
    if isinstance(locks, (list, tuple)):
        return {str(k): str(k) for k in locks if str(k).strip()}
    return {}


def is_section_locked(user_id, key):
    try:
        if is_grp_owner(user_id):
            return False
    except Exception:
        pass
    key = str(key or "").strip()
    if not key:
        return False
    return key in get_locked_sections(user_id)


def set_section_locked(user_id, key, locked, label=""):
    """قفل/بازکردن یک بخش یا یک دکمهٔ مشخص برای کاربر."""
    key = str(key or "").strip()
    if not key:
        return False
    uid = str(int(user_id))
    _ensure_user(uid)
    info = users_db["users"][uid]
    locks = get_locked_sections(user_id)
    if locked:
        clean = re.sub(r"\s+", " ", str(label or key)).strip()[:48]
        locks[key] = clean or key
    else:
        locks.pop(key, None)
    info["locked_sections"] = locks
    save_json(USERS_FILE, users_db)
    return bool(locked)


def clear_section_locks(user_id):
    uid = str(int(user_id))
    _ensure_user(uid)
    users_db["users"][uid]["locked_sections"] = {}
    save_json(USERS_FILE, users_db)


def _panel_lock_label(raw, text=None):
    """برچسب انسانی برای یک بخش؛ از رجیستری یا خط اول متن پنل."""
    raw = str(raw or "")
    title = SECTION_LOCK_TITLES.get(raw)
    if not title and text:
        first = str(text).split("\n")[0]
        first = re.sub(r"<[^>]+>", "", first)
        first = re.sub(r"\s+", " ", first).strip()
        if first:
            title = first[:28]
    return title or raw


def _is_lockable_panel(raw):
    raw = str(raw or "")
    if not raw or raw in _SECTION_LOCK_IGNORE:
        return False
    if raw.startswith(_SECTION_LOCK_OWNER_PREFIX):
        return False
    if raw in SECTION_LOCK_TITLES:
        return True
    return raw.endswith(("_panel", "_main", "_menu"))


def _filter_locked_sections(uid, kb):
    """دکمه‌های بخش‌های قفل‌شده را از پنل کاربر حذف می‌کند."""
    if not kb:
        return kb
    try:
        if is_grp_owner(uid):
            return kb
    except Exception:
        pass
    locks = get_locked_sections(uid)
    if not locks:
        return kb
    out = []
    for row in kb:
        keep = []
        for button in row:
            raw = getattr(button, "data", None)
            if isinstance(raw, bytes):
                raw = raw.decode(errors="ignore")
            if raw and str(raw) in locks:
                continue
            keep.append(button)
        if keep:
            out.append(keep)
    return out


def _locked_command_label(user_id, text):
    """اگر دستور متنی مربوط به بخش قفل‌شده باشد، برچسب آن بخش را برمی‌گرداند."""
    if not text:
        return None
    pairs = [
        ((f"{CMD}پنل بازی", f"{CMD}بازی"), "pn_games"),
        ((f"{CMD}پنل کاردینال", f"{CMD}کاردینال"), "pn_cardinal_panel"),
        ((f"{CMD}پنل پونی", f"{CMD}پونی"), "pn_pony_main"),
        ((f"{CMD}پنل پیو", f"{CMD}پیو"), "pn_pew_panel"),
        ((f"{CMD}پنل تبچی", f"{CMD}تبچی"), "pn_banner_main"),
        ((f"{CMD}پنل ابزار", f"{CMD}ابزارها", f"{CMD}پنل ابزارها"), "pn_tools"),
        ((f"{CMD}پنل فونت",), "pn_font_panel"),
        ((f"{CMD}پنل استایل", f"{CMD}پنل HTML", f"{CMD}استایل", f"{CMD}راهنمای استایل"), "pn_html_panel"),
        ((f"{CMD}پنل پایش", f"{CMD}پایش"), "pn_mon_main"),
        ((f"{CMD}پنل ویس", f"{CMD}پنل صدا", f"{CMD}ویس"), "pn_tts_panel"),
    ]
    for commands, key in pairs:
        if text in commands and is_section_locked(user_id, key):
            return get_locked_sections(user_id).get(key) or SECTION_LOCK_TITLES.get(key, key)
    return None

def is_user_active(user_id):
    try:
        if is_grp_owner(user_id):
            return True   # مالک همیشه فعال است (حتی اگر رکورد کاربری‌اش کامل نباشد)
    except Exception:
        pass
    user = users_db["users"].get(str(user_id))
    if user and (user.get("locally_disabled", False) or user.get("all_access_locked", False)):
        return False
    return bool(user and user.get("active", False))

def is_user_locally_disabled(user_id):
    user = users_db["users"].get(str(user_id))
    return bool(user and user.get("locally_disabled", False))

def _ensure_user(uid):
    uid = str(uid)
    if uid not in users_db["users"]:
        users_db["users"][uid] = {"banned": False, "active": False,
            "locally_disabled": False, "phone": "", "name": "", "no_sell": [],
            "gender": None, "banner_id": None, "banner_scope": "private",
            "html_style_on": False, "html_style": "bold",
            "font_on": False, "font": "none",
            "ttl_enabled": False, "ttl_target": "me",
            "locked_sections": {}}
    else:
        u = users_db["users"][uid]
        if "ttl_enabled" not in u: u["ttl_enabled"] = False
        if "ttl_target" not in u: u["ttl_target"] = "me"
        if not isinstance(u.get("locked_sections"), dict): u["locked_sections"] = {}
    return users_db["users"][uid]

def set_user_active(user_id, active):
    uid = str(user_id); _ensure_user(uid)
    users_db["users"][uid]["active"] = bool(active)
    if active:
        users_db["users"][uid]["locally_disabled"] = False
        users_db["users"][uid]["relogin_notified"] = False
    save_json(USERS_FILE, users_db)

def set_user_locally_disabled(user_id, disabled):
    uid = str(user_id); _ensure_user(uid)
    users_db["users"][uid]["locally_disabled"] = bool(disabled)
    save_json(USERS_FILE, users_db)

def set_user_phone(user_id, phone):
    uid = str(user_id); _ensure_user(uid)
    users_db["users"][uid]["phone"] = phone; save_json(USERS_FILE, users_db)

def set_user_name(user_id, name):
    uid = str(user_id); _ensure_user(uid)
    users_db["users"][uid]["name"] = name; save_json(USERS_FILE, users_db)

async def update_user_phone_from_account(user_id, client):
    try:
        me = await client.get_me()
        if hasattr(me, 'phone') and me.phone:
            phone = re.sub(r'[^\d+]', '', me.phone)
            if phone.endswith("+"): phone = phone[:-1]
            if not phone.startswith("+"): phone = "+" + phone
            set_user_phone(user_id, phone); return phone
    except: pass
    return None

async def update_user_name_from_account(user_id, client):
    try:
        me = await client.get_me()
        if hasattr(me, 'first_name'):
            name = me.first_name or ""
            if me.last_name: name += " " + me.last_name
            set_user_name(user_id, name.strip()); return name
    except: pass
    return None

# ═══════════════════════════════════════════════════════
# Notify / Safe send / helpers
# ═══════════════════════════════════════════════════════
async def _notify_user(user_id, msg):
    if bot_client:
        try: await bot_client.send_message(int(user_id), msg)
        except Exception as e: log_error(f"notify_user {user_id}: {_translate_bot_errors(e)}")

async def _notify_escape(user_id, msg): await _notify_user(user_id, msg)

async def _notify_chat_blocked(uid, chat_id):
    if not bot_client: return
    try:
        title = str(chat_id)
        try:
            c = user_clients.get(int(uid))
            if c:
                ent = await c.get_entity(chat_id)
                title = getattr(ent, 'title', None) or str(chat_id)
        except: pass
        msg = (f"⛔ یکی از چت های شما پیام قبول نمی کند.\n\n"
               f"اسم چت:\n{title}\nچت: {chat_id}")
        await bot_client.send_message(int(uid), msg)
    except Exception as e: log_error(f"notify_chat_blocked {uid}: {_translate_bot_errors(e)}")

async def safe_send(client, uid, chat_id, text, tag="send"):
    key = (int(uid), str(chat_id))
    info = chat_blocks.get(key)
    if info:
        if time.time() < info["until"]: return False
        del chat_blocks[key]
    target = chat_id
    if isinstance(chat_id, str) and chat_id.lower().lstrip("@") == GAME_BOT_USERNAME.lower():
        target = GAME_BOT_ID
    try:
        await client.send_message(target, text); return True
    except FloodWaitError as e:
        await asyncio.sleep(e.seconds)
        try:
            await client.send_message(target, text); return True
        except: return False
    except Exception as e:
        err_name = type(e).__name__.lower(); err_str = _translate_bot_errors(e).lower()
        if ("chatwriteforbidden" in err_name or "userbanned" in err_name
            or "forbidden" in err_str or "banned" in err_str or "blocked" in err_str):
            chat_blocks[key] = {"until": time.time() + CHAT_BLOCK_DURATION}
            log_error(f"chat_blocked {uid}->{chat_id}: {_translate_bot_errors(e)}")
            await _notify_chat_blocked(uid, chat_id); return False
        log_error(f"safe_send[{tag}] {uid}->{chat_id}: {_translate_bot_errors(e)}"); return False

def get_user_lock(user_id):
    if user_id not in user_workflow_locks:
        user_workflow_locks[user_id] = asyncio.Lock()
    return user_workflow_locks[user_id]

async def safe_edit(event, text, buttons=None, parse_mode=None):
    try:
        await event.edit(text, buttons=buttons, parse_mode=parse_mode); return True
    except MessageIdInvalidError: return False
    except MessageNotModifiedError: return True
    except Exception as e:
        print(f"Edit failed: {_translate_bot_errors(e)}"); return False

async def get_plain_name(client, user_id):
    try:
        entity = await client.get_entity(user_id)
        name = entity.first_name or ""
        if entity.last_name: name += f" {entity.last_name}"
        return name.strip() or str(user_id)
    except: return str(user_id)

async def resolve_user_arg(event, client, arg):
    arg = (arg or "").strip()
    if arg:
        clean = normalize_digits(arg)
        if clean.lstrip("-").isdigit(): return int(clean)
        uname = arg if arg.startswith("@") else f"@{arg}"
        try: return (await client.get_entity(uname)).id
        except:
            try: return (await client.get_entity(arg)).id
            except: return None
    
    # بخش ریپلای (اصلاح شده برای تلگرام)
    reply = await event.get_reply_message()
    if reply:
        if reply.sender_id: return reply.sender_id
        if getattr(reply, "from_id", None) and getattr(reply.from_id, "user_id", None):
            return reply.from_id.user_id
    return None


async def notify_disconnect(user_id):
    if not bot_client: return
    uid = str(user_id)
    if uid not in users_db["users"]: return
    if users_db["users"][uid].get("relogin_notified", False): return
    if users_db["users"][uid].get("banned", False): return
    session_path = SESSION_DIR / str(user_id)
    if not os.path.exists(str(session_path) + ".session"): return
    try:
        await bot_client.send_message(int(user_id),
            "🔌 اتصال شما قطع شد!\n\n"
            "برای اتصال مجدد دکمه زیر رو بزن 👇",
            buttons=[[types.KeyboardButtonCallback("🔌 اتصال مجدد", data="relogin_start")]])
        users_db["users"][uid]["relogin_notified"] = True
        save_json(USERS_FILE, users_db)
    except Exception as e: log_error(f"notify_disconnect {user_id}: {_translate_bot_errors(e)}")

def clear_relogin_flag(user_id):
    uid = str(user_id)
    if uid in users_db["users"]:
        users_db["users"][uid]["relogin_notified"] = False
        save_json(USERS_FILE, users_db)

async def notify_users_on_startup():
    await asyncio.sleep(3)
    if not bot_client: return
    notified = failed = 0
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg_text = (f"🟢 ربات روشن شد!\n\n⏰ زمان: {now_str}\n\n"
                f"برای پنل: {CMD}پنل\n🔌 /login")
    for uid, info in list(users_db["users"].items()):
        if info.get("banned") or not info.get("active"): continue
        try:
            await bot_client.send_message(int(uid), msg_text)
            notified += 1; await asyncio.sleep(0.1)
        except FloodWaitError as e: await asyncio.sleep(e.seconds)
        except Exception as e:
            failed += 1; log_error(f"startup_notify {uid}: {_translate_bot_errors(e)}")
    print(f"📢 اطلاع‌رسانی: موفق {notified} / ناموفق {failed}")

# ═══════════════════════════════════════════════════════
# Ally pause
# ═══════════════════════════════════════════════════════
def is_ally_paused(chat_id, ally_id):
    return (int(chat_id), int(ally_id)) in ally_paused

def pause_all_allies_of_commander(chat_id, commander_id):
    c = get_chat_battle(chat_id); count = 0
    for aid, cmid in c.get("allies", {}).items():
        if str(cmid) == str(commander_id):
            ally_paused[(int(chat_id), int(aid))] = True; count += 1
    if count: schedule_save_runtime()
    return count

def unpause_all_allies_of_commander(chat_id, commander_id):
    c = get_chat_battle(chat_id); count = 0
    for aid, cmid in c.get("allies", {}).items():
        if str(cmid) == str(commander_id):
            key = (int(chat_id), int(aid))
            if key in ally_paused:
                del ally_paused[key]; count += 1
    if count: schedule_save_runtime()
    return count

def clear_ally_paused(chat_id):
    for k in [k for k in list(ally_paused.keys()) if k[0] == int(chat_id)]:
        del ally_paused[k]
    schedule_save_runtime()

# ═══════════════════════════════════════════════════════
# Pony / Dungeon helper
# ═══════════════════════════════════════════════════════
def get_pony_cfg(user_id, chat_id):
    return pony_config.setdefault((int(user_id), int(chat_id)),
        {"collect": False, "upgrade": False,
         "naz_enabled": False, "naz_interval_mins": 3})

def get_dungeon_cfg(user_id, chat_id):
    return dungeon_config.setdefault((int(user_id), int(chat_id)),
        {"enabled": False, "current_idx": 0, "working_idx": -1, "test_mode": False,
         "mode": "auto", "manual_idx": 0})

def stop_all_pony_for_user(user_id):
    uid = int(user_id)
    for k in [k for k in list(naz_auto_tasks.keys()) if k[0] == uid]:
        t = naz_auto_tasks.pop(k, None)
        if t and not t.done(): t.cancel()
    for k in [k for k in list(pony_tasks.keys()) if k[0] == uid]:
        t = pony_tasks.pop(k, None)
        if t and not t.done(): t.cancel()
    for k in [k for k in list(pony_config.keys()) if k[0] == uid]:
        del pony_config[k]
    for k in [k for k in list(pony_state.keys()) if k[0] == uid]:
        del pony_state[k]
    st = pony_waiting.pop(uid, None)
    if st and st.get("retry_task"):
        t = st["retry_task"]
        if not t.done(): t.cancel()
    schedule_save_runtime()

def stop_all_dungeon_for_user(user_id):
    uid = int(user_id)
    for k in [k for k in list(dungeon_tasks.keys()) if k[0] == uid]:
        t = dungeon_tasks.pop(k, None)
        if t and not t.done(): t.cancel()
    for k in [k for k in list(dungeon_config.keys()) if k[0] == uid]:
        del dungeon_config[k]
    st = dungeon_waiting.pop(uid, None)
    if st and st.get("timeout_task"):
        t = st["timeout_task"]
        if not t.done(): t.cancel()
    schedule_save_runtime()

# ═══════════════════════════════════════════════════════
# Queue helpers
# ═══════════════════════════════════════════════════════
def _get_queue(user_id, feature):
    key = (user_id, feature)
    if key not in sell_queues:
        sell_queues[key] = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
    return sell_queues[key]

async def _drain_sell_queue(user_id, feature="sell"):
    q = _get_queue(user_id, feature); n = 0
    while True:
        try: q.get_nowait(); n += 1
        except asyncio.QueueEmpty: break
    if n: log_error(f"🧹 drained {n} for {user_id}/{feature}")

async def _wait_for_sell_message(user_id, timeout, predicate, feature="sell"):
    q = _get_queue(user_id, feature); deadline = time.time() + timeout
    while True:
        remaining = deadline - time.time()
        if remaining <= 0: return None
        try: msg = await asyncio.wait_for(q.get(), timeout=remaining)
        except asyncio.TimeoutError: return None
        if predicate(msg): return msg

async def _sell_send_and_wait(user_id, cmd, timeout, predicate, feature="sell"):
    send_task = asyncio.create_task(_send_game_cmd(user_id, cmd, tag=feature))
    result = await _wait_for_sell_message(user_id, timeout, predicate, feature)
    try: await send_task
    except: pass
    return result

async def _send_game_cmd(user_id, cmd, tag="sell"):
    client = user_clients.get(int(user_id))
    if not client or not client.is_connected():
        client = await ensure_user_client(user_id)
        if not client: return False
    ok = await safe_send(client, user_id, GAME_BOT_ID, cmd, tag=tag)
    if ok: log_error(f"💸 {tag} cmd by {user_id}: {cmd}")
    return ok

async def _route_game_bot_message(user_id, text):
    if user_id in sell_mode_users and sell_mode_users[user_id].get("enabled"):
        try: _get_queue(user_id, "sell").put_nowait(text)
        except: pass
    if is_escape_enabled(user_id):
        try: _get_queue(user_id, "escape").put_nowait(text)
        except: pass
    if transfer_materials_config.get(user_id, {}).get("enabled"):
        try: _get_queue(user_id, "mat_inv").put_nowait(text)
        except: pass
    if is_inventory_message(text):
        try: _get_queue(user_id, "mat_inv").put_nowait(text)
        except: pass
    if is_return_enabled(user_id):
        try: _get_queue(user_id, "return").put_nowait(text)
        except: pass
    if daily_gift_status.get(user_id, False):
        try: _get_queue(user_id, "gift").put_nowait(text)
        except: pass
    if user_id in transfer_configs and transfer_configs[user_id].get("enabled"):
        try: _get_transfer_queue(user_id).put_nowait(text)
        except: pass
    try:
        chats = get_battle_chats()
        for _ck, cdata in chats.items():
            if str(user_id) in cdata.get("commanders", {}) or str(user_id) in cdata.get("allies", {}):
                try: _get_queue(user_id, "battle").put_nowait(text)
                except: pass
                break
    except: pass

# ═══════════════════════════════════════════════════════
# Inline helpers
# ═══════════════════════════════════════════════════════
def _is_inline_id(obj):
    if obj is None: return False
    if isinstance(obj, int): return False
    if isinstance(obj, str):
        if obj.lstrip('-').isdigit(): return False
        return True
    return True

def _bind_panel_callbacks(kb, panel_user_id):
    """Issue short opaque callback IDs bound to the account that opened the panel."""
    kb = _filter_locked_sections(panel_user_id, kb)
    now = time.time()
    for token, value in list(panel_callback_tokens.items()):
        if now - value[2] > 8 * 3600:
            panel_callback_tokens.pop(token, None)
    bound = []
    for row in (kb or []):
        new_row = []
        for button in row:
            if hasattr(button, "data") and hasattr(button, "text"):
                raw_data = button.data
                if isinstance(raw_data, bytes):
                    raw_data = raw_data.decode(errors="ignore")
                token = f"pc_{random.getrandbits(48):012x}"
                while token in panel_callback_tokens:
                    token = f"pc_{random.getrandbits(48):012x}"
                panel_callback_tokens[token] = (int(panel_user_id), str(raw_data), now)
                new_row.append(_cb(button.text, token))
            else:
                new_row.append(button)
        bound.append(new_row)
    return bound


def _kb_to_inline_markup(kb):
    if not kb: return None
    rows = []
    for row in kb:
        btns = []
        for b in row:
            try:
                if hasattr(b, 'text') and hasattr(b, 'data'):
                    btns.append(types.KeyboardButtonCallback(text=b.text, data=b.data))
                elif isinstance(b, KeyboardButtonUrl):
                    btns.append(KeyboardButtonUrl(text=b.text, url=b.url))
                else:
                    btns.append(b)
            except Exception:
                btns.append(b)
        if btns:
            rows.append(KeyboardButtonRow(buttons=btns))
    return ReplyInlineMarkup(rows=rows) if rows else None

async def _try_inline_edit_global(imid, text, kb):
    if not imid or not helper_bot: return False
    try:
        try:
            from telethon.extensions import html as _thtml
            msg_text, entities = _thtml.parse(text or "")
        except Exception:
            msg_text, entities = (text or ""), []
        markup = _kb_to_inline_markup(kb)
        req = EditInlineBotMessageRequest(
            id=imid, message=msg_text,
            entities=entities or None, reply_markup=markup)
        await helper_bot(req)
        return True
    except Exception as e:
        log_error(f"❌ _try_inline_edit_global: {type(e).__name__}: {_translate_bot_errors(e)}")
        return False

async def _pm_safe_edit(event, uid, text, kb=None, file_path=None):
    try:
        q = getattr(event, 'query', None)
        if q is not None:
            m = getattr(q, 'msg_id', None)
            if _is_inline_id(m):
                ok = await _try_inline_edit_global(m, text, kb)
                if ok:
                    return True
    except: pass
    client = user_clients.get(int(uid))
    if not client or not client.is_connected():
        client = await ensure_user_client(uid)
    if client:
        try:
            kwargs = {"buttons": kb, "parse_mode": "html"}
            if file_path: kwargs["file"] = file_path
            await client.edit_message(event.chat_id, event.message_id, text, **kwargs)
            return True
        except Exception as e:
            log_error(f"_pm_safe_edit user: {_translate_bot_errors(e)}")
    try:
        kwargs = {"buttons": kb, "parse_mode": "html"}
        if file_path: kwargs["file"] = file_path
        await event.edit(text, **kwargs)
        return True
    except Exception as e:
        log_error(f"_pm_safe_edit helper: {_translate_bot_errors(e)}")
    # آخرین تلاش: متن بدون تگ (اگر HTML مشکل داشته باشد پنل باز هم آپدیت شود)
    try:
        plain = re.sub(r"<[^>]+>", "", str(text or ""))
        plain = html_lib.unescape(plain)
        await event.edit(plain, buttons=kb)
        return True
    except Exception as e:
        log_error(f"_pm_safe_edit plain fallback: {_translate_bot_errors(e)}")
        return False

async def _pm_edit_with_banner(event, uid, text, kb):
    banner = get_user_display_banner(uid)
    await _pm_safe_edit(event, uid, text, kb, banner)

async def _pm_reply_with_banner(event, uid, text, kb):
    banner = get_user_display_banner(uid)
    if banner:
        try:
            await event.reply(text, file=banner, buttons=kb, parse_mode="html"); return
        except Exception as e: log_error(f"_pm_reply_with_banner: {_translate_bot_errors(e)}")
    try:
        await event.reply(text, buttons=kb, parse_mode="html")
    except Exception as e: log_error(f"_pm_reply_with_banner fallback: {_translate_bot_errors(e)}")

# ═══════════════════════════════════════════════════════
# TTL + ذخیره
# ═══════════════════════════════════════════════════════
def get_ttl_config(uid):
    u = users_db["users"].get(str(uid), {})
    return {
        "enabled": bool(u.get("ttl_enabled", False)),
        "target": u.get("ttl_target", "me"),
    }

def set_ttl_config(uid, key, val):
    uid_s = str(uid); _ensure_user(uid_s)
    users_db["users"][uid_s][f"ttl_{key}"] = val
    save_json(USERS_FILE, users_db)

def get_media_ttl(message):
    media = getattr(message, "media", None)
    if media is None: return None
    try:
        ttl = int(getattr(media, "ttl_seconds", 0) or 0)
        if ttl > 0: return ttl
    except: pass
    if isinstance(media, MessageMediaDocument):
        doc = media.document
        if doc and hasattr(doc, "attributes"):
            for attr in doc.attributes:
                if hasattr(attr, "ttl_seconds"):
                    try:
                        ttl = int(attr.ttl_seconds or 0)
                        return ttl if ttl > 0 else None
                    except: return None
    return None

async def _try_ttl_save(user_id, event):
    cfg = get_ttl_config(user_id)
    if not is_media_allowed(user_id):
        if cfg["enabled"]:
            set_ttl_config(user_id, "enabled", False)
        return False
    if not cfg["enabled"]: return False
    if not event.is_private: return False
    if event.sender_id == user_id: return False
    ttl = get_media_ttl(event.message)
    if ttl is None: return False
    key = (int(event.chat_id), int(event.id))
    if key in _ttl_processing: return True
    _ttl_processing.add(key)
    try:
        client = event.client
        if not client or not client.is_connected():
            client = user_clients.get(int(user_id))
            if not client or not client.is_connected():
                client = await ensure_user_client(user_id)
            if not client: return True
        data = await asyncio.wait_for(
            client.download_media(event.message, file=bytes),
            timeout=min(ttl + 30, 90)
        )
        if not data: return True
        typ, ext, is_voice = "فایل", ".bin", False
        if event.photo: typ, ext = "عکس", ".jpg"
        elif event.video: typ, ext = "ویدیو", ".mp4"
        elif event.gif: typ, ext = "گیف", ".mp4"
        elif event.video_note: typ, ext = "ویدیو مسیج", ".mp4"
        elif event.voice: typ, ext, is_voice = "ویس", ".ogg", True
        elif event.audio: typ, ext, is_voice = "فایل صوتی", ".mp3", True
        else:
            doc = getattr(event.message.media, "document", None)
            if doc:
                for a in getattr(doc, "attributes", []):
                    if isinstance(a, DocumentAttributeFilename):
                        ext = Path(a.file_name).suffix or ".bin"
                    elif isinstance(a, DocumentAttributeAudio):
                        if getattr(a, "voice", False):
                            typ, ext, is_voice = "ویس", ".ogg", True
                        else:
                            typ, ext, is_voice = "فایل صوتی", ".mp3", True
        name = str(event.sender_id)
        try:
            s = await event.get_sender()
            if s and getattr(s, "first_name", None): name = s.first_name
        except: pass
        dur = "یک بار مشاهده" if ttl == 2147483647 else f"{ttl} ثانیه"
        cap = (
            f"⏱ {typ} ناپدیدشونده ذخیره شد\n"
            f"👤 فرستنده: {name}\n"
            f"🆔 شناسه: {event.sender_id}\n"
            f"⌛ مدت نمایش: {dur}\n"
            f"🕒 ذخیره: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        f = io.BytesIO(data)
        f.name = f"ttl_{event.id}{ext}"
        target = cfg["target"] or "me"
        if is_voice:
            await client.send_file(target, f, caption=cap, voice_note=True, silent=True, parse_mode=None)
        else:
            await client.send_file(target, f, caption=cap, silent=True, parse_mode=None)
        log_error(f"✅ TTL saved: user={user_id} from={event.sender_id} type={typ} ttl={ttl}")
    except Exception as e:
        log_error(f"_try_ttl_save {user_id}: {_translate_bot_errors(e)}")
    finally:
        _ttl_processing.discard(key)
    return True

def _extract_tg_links(text):
    if not text: return []
    # Drop trailing punctuation copied from prose while retaining Telegram paths.
    pattern = r'(?:https?://)?t\.me/(?:c/)?[^/\s]+/\d+'
    links = re.findall(pattern, text, flags=re.IGNORECASE)
    return [link.rstrip(".,;:!?،؛.)]}") for link in links]

def _get_source_media_caption(message):
    """Return the original text/caption attached to a media message, if any."""
    if not message:
        return ""
    for attr in ("message", "raw_text", "text"):
        value = getattr(message, attr, None)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


async def _download_and_save_media(client, message, caption=None):
    file_path = None
    try:
        if not message or not message.media:
            return "❌ رسانه ندارد"
        source_caption = _get_source_media_caption(message)
        saved_caption = source_caption or caption or "📥 ذخیره شده"
        file_size = 5 * 1024 * 1024
        try:
            if hasattr(message.media, 'document') and hasattr(message.media.document, 'size'):
                file_size = message.media.document.size or file_size
        except: pass
        base_to = max(30, min(300, file_size // (50 * 1024)))
        if file_size > 100 * 1024 * 1024:
            base_to = max(base_to, 600)
        tmp_dir = TEMP_DIR / "saves"; tmp_dir.mkdir(exist_ok=True)
        file_path = await asyncio.wait_for(
            client.download_media(message, file=str(tmp_dir)),
            timeout=base_to * 2
        )
        if not file_path:
            return "❌ دانلود ناموفق"
        if len(saved_caption) <= 1024:
            await client.send_file("me", file_path, caption=saved_caption, silent=True, parse_mode=None)
        else:
            # Telegram captions are limited; keep the full original text as a following Saved Message.
            await client.send_file("me", file_path, caption="📥 ذخیره شده", silent=True, parse_mode=None)
            for offset in range(0, len(saved_caption), 4000):
                await client.send_message("me", saved_caption[offset:offset + 4000], silent=True, parse_mode=None)
        return "✅ ذخیره شد"
    except asyncio.TimeoutError:
        return "❌ زمان دانلود تمام شد"
    except FloodWaitError as e:
        return f"⏱ باید {e.seconds} ثانیه صبر کنی"
    except Exception as e:
        return f"❌ خطا: {_translate_bot_errors(e)[:80]}"
    finally:
        if file_path:
            try: os.remove(file_path)
            except: pass

async def _get_album_messages(client, message):
    if not message: return []
    gid = getattr(message, 'grouped_id', None)
    if not gid: return [message]
    try:
        chat_id = message.chat_id or message.peer_id
        album = []
        async for m in client.iter_messages(
            chat_id, min_id=max(0, message.id - 15), max_id=message.id + 16, reverse=True):
            mg = getattr(m, 'grouped_id', None)
            if mg == gid and m.media:
                album.append(m)
            elif album and mg != gid:
                break
        if not album:
            return [message]
        if not any(m.id == message.id for m in album):
            album.append(message)
        album.sort(key=lambda m: m.id)
        return album
    except Exception as e:
        log_error(f"_get_album_messages: {_translate_bot_errors(e)}")
        return [message]

async def _process_save_link(client, link, seen_albums=None):
    pattern = r'(?:https?://)?t\.me/(?:c/)?([^/]+)/(\d+)'
    m = re.search(pattern, link, flags=re.IGNORECASE)
    if not m: return link, "❌ لینک نامعتبر"
    chat_id_str, msg_id_str = m.group(1), m.group(2)
    try: msg_id = int(msg_id_str)
    except: return link, "❌ شماره پیام نامعتبر"
    try:
        if chat_id_str.isdigit():
            entity = await client.get_entity(int(f'-100{chat_id_str}'))
        else:
            entity = await client.get_entity(f'@{chat_id_str}')
        msg = await client.get_messages(entity, ids=msg_id)
        if not msg: return link, "❌ پیدا نشد"
        if not msg.media: return link, "❌ رسانه ندارد"
        album = await _get_album_messages(client, msg)
        if not album: album = [msg]
        grouped_id = getattr(msg, "grouped_id", None)
        album_key = (str(getattr(msg, "chat_id", chat_id_str)), str(grouped_id)) if grouped_id else None
        if album_key and seen_albums is not None:
            if album_key in seen_albums:
                return link, "↪️ این آلبوم قبلاً از لینک دیگری ذخیره شد"
            seen_albums.add(album_key)
        if len(album) == 1:
            result = await _download_and_save_media(client, album[0], "📥 ذخیره شده از لینک")
            return link, result
        ok = 0
        for item in album:
            result = await _download_and_save_media(client, item, "📥 ذخیره شده از لینک")
            if result.startswith("✅"): ok += 1
        return link, f"✅ {ok} از {len(album)} رسانه آلبوم ذخیره شد"
    except Exception as e:
        return link, f"❌ خطا: {_translate_bot_errors(e)[:60]}"


async def _process_save_links(client, links):
    seen_albums = set()
    results = []
    for link in links:
        results.append(await _process_save_link(client, link, seen_albums))
    return results

async def _handle_save_command(event, user_id, raw_arg):
    if not is_media_allowed(user_id):
        await safe_edit(event, "🔒 این قابلیت در دسترس نیست.")
        return
    client = user_clients.get(int(user_id))
    if not client or not client.is_connected():
        client = await ensure_user_client(user_id)
    if not client:
        await safe_edit(event, "❌ اتصال نیست."); return
    if raw_arg:
        links = _extract_tg_links(raw_arg)
        if not links:
            await safe_edit(event, "❌ لینک معتبری پیدا نشد."); return
        if len(links) == 1:
            await safe_edit(event, "⏳ در حال دانلود...")
            _, result = await _process_save_link(client, links[0])
            await safe_edit(event, result); return
        await safe_edit(event, f"⏳ در حال دانلود {len(links)} لینک...")
        results = await _process_save_links(client, links)
        lines = [f"{i}️⃣ {r}" for i, (_, r) in enumerate(results, 1)]
        await safe_edit(event, "\n\n".join(lines)); return
    reply = await event.get_reply_message()
    if not reply:
        await safe_edit(event, f"❌ روی پیام ریپلای کن یا لینک بفرست.\n\n{CMD}ذخیره <لینک>")
        return
    if reply.media:
        album = await _get_album_messages(client, reply)
        if len(album) > 1:
            await safe_edit(event, f"⏳ در حال دانلود {len(album)} رسانه...")
            ok = 0
            for am in album:
                r = await _download_and_save_media(client, am, "📥 ذخیره شده از ریپلای")
                if r.startswith("✅"): ok += 1
                await asyncio.sleep(0.5)
            await safe_edit(event, f"✅ {ok} از {len(album)} رسانه ذخیره شد")
            return
        await safe_edit(event, "⏳ در حال دانلود...")
        result = await _download_and_save_media(client, reply, "📥 ذخیره شده از ریپلای")
        await safe_edit(event, result); return
    links = _extract_tg_links(reply.raw_text or "")
    if not links:
        await safe_edit(event, "❌ رسانه یا لینکی پیدا نشد."); return
    if len(links) == 1:
        await safe_edit(event, "⏳ در حال دانلود...")
        _, result = await _process_save_link(client, links[0])
        await safe_edit(event, result); return
    await safe_edit(event, f"⏳ در حال دانلود {len(links)} لینک...")
    results = await _process_save_links(client, links)
    lines = [f"{i}️⃣ {r}" for i, (_, r) in enumerate(results, 1)]
    await safe_edit(event, "\n\n".join(lines))

# ═══════════════════════════════════════════════════════
# send_panel_via_helper
# ═══════════════════════════════════════════════════════
async def send_panel_via_helper(user_id, chat_id,
                                 helper_username=HELPER_BOT_USERNAME,
                                 query=INLINE_SECRET):
    client = user_clients.get(int(user_id))
    if not client or not client.is_connected():
        client = await ensure_user_client(user_id)
        if not client:
            log_error(f"send_panel: no client {user_id}")
            return False
    try: pm_panel_chat[int(user_id)] = int(chat_id)
    except: pass

    # ─── فقط از طریق inline helper_bot ───
    try:
        helper_entity = await client.get_entity(helper_username)
        res = await client(GetInlineBotResultsRequest(
            bot=helper_entity, peer=chat_id, query=query, offset=""))
        if res and res.results:
            first = res.results[0]
            await client(SendInlineBotResultRequest(
                peer=chat_id, query_id=res.query_id, id=first.id,
                random_id=random.randint(-2**63, 2**63 - 1)))
            log_error(f"✅ panel INLINE via helper → {chat_id} by {user_id}")
            schedule_save_runtime()
            return True
        log_error(f"⚠️ inline empty for {chat_id}")
    except Exception as e:
        log_error(f"❌ inline fail {user_id}→{chat_id}: {type(e).__name__}: {_translate_bot_errors(e)}")
    return False



# ═══════════════════════════════════════════════════════
def is_inventory_message(text):
    if not text: return False
    t = _normalize_persian(text)
    return ("کوله" in t and "ظرفیت" in t) or ("دارایی نقدی" in t)

def parse_inventory_capacity(text):
    m = re.search(r'ظرفیت\s+کوله\s*پشتی[:\s]+(\d+)\s*/\s*(\d+)',
                  _normalize_persian(normalize_digits(text)))
    return (int(m.group(1)), int(m.group(2))) if m else None

def is_city_arrival_message(text):
    t = _normalize_persian(text)
    return ("دروازه شهر" in t and "ورود به منطقه امن" in t) or \
           ("منطقه امن" in t and "Safe Zone" in text)

def is_city_exit_message(text):
    t = _normalize_persian(text)
    if "دروازه" in t and "بسته شد" in t: return True
    if "بیرون از شهر" in t and "موقعیت" in t: return True
    return False

def is_distance_error_message(text):
    t = _normalize_persian(text)
    if "خطای موقعیت" in t: return True
    if "زمان باقیمانده" in t and "دروازه شهر" in t: return True
    if "تلپورت اجباری" in t and "کریستال" in t: return True
    if "خطای منطقه" in t: return True
    if "باید در منطقه امن" in t: return True
    if "نمی‌توانی به شهر" in t or "نمی‌تونی به شهر" in t: return True
    if "نمی‌توانید به شهر" in t or "نمی‌تونید به شهر" in t: return True
    if "کریستال تلپورت اجباری" in t: return True
    return False

def is_crystal_success_message(text):
    return "کریستال تلپورت اجباری فعال" in _normalize_persian(text)

def is_crystal_luck_prompt(text):
    t = _normalize_persian(text)
    if "کریستال شانس" in t and "استفاده" in t: return True
    if "گزینه" in t and "بله" in t and "خیر" in t: return True
    return False

def is_forbidden_equipment_prompt(text):
    t = _normalize_persian(text)
    if "تجهیزات ممنوعه" in t: return True
    if "معجون قدرت" in t and "ممنوعه" in t: return True
    if "هشدار تجهیزات" in t: return True
    if "لول مورد نیاز" in t and "لول فعلی شما" in t: return True
    return False

def is_yes_no_retry_prompt(text):
    t = _normalize_persian(text)
    if "یکی از گزینه" in t and "بله" in t and "خیر" in t: return True
    if "لطفاً یکی از گزینه" in t: return True
    if "لطفا یکی از گزینه" in t: return True
    return False

def is_hunt_success(text):
    t = _normalize_persian(text)
    return ("شکارت موفقیت آمیز بود" in t) or ("هیولای شکار شده" in t) or \
           ("تجربه (XP)" in t and "سکه (کاردینالت)" in t)

def is_hunt_cooldown(text):
    t = _normalize_persian(text)
    return ("در حال تجهیز مجدد" in t) or ("زمان باقیمانده تا شکار بعدی" in t)

def is_hunt_safe_zone(text):
    t = _normalize_persian(text)
    return ("خطای دسترسی" in t and "منطقه امن" in t) or \
           ("داخل شهر (منطقه امن)" in t) or \
           ("سیستم نبرد در این محدوده غیرفعال است" in t)

def is_hunt_failure_return_city(text):
    t = _normalize_persian(text)
    if "شکار ناموفق" in t: return True
    if "قدرتش فراتر از انتظار" in t and "شکست" in t: return True
    if "سریع برگرد شهر" in t: return True
    if "برو طبقه" in t and ("پایین" in t or "کمتر" in t): return True
    return False

def is_dungeon_hunt_win(text):
    if not text: return False
    t = _normalize_persian(text)
    if "شما شکست خوردید" in t: return False
    if "شما شکست خوردين" in t: return False
    if "شما پیروز شدید" in t: return True
    return False

def is_dungeon_hunt_loss(text):
    if not text: return False
    t = _normalize_persian(text)
    if "شما شکست خوردید" in t: return True
    if "شما شکست خوردين" in t: return True
    return False

def is_spy_warning(text):
    t = _normalize_persian(text)
    return "قاتل ناشناس" in t and "جاسوسی" in t and "هشدار امنیتی" in t

def is_kill_message(text):
    t = _normalize_persian(text)
    if "شما هدف قرار گرفتید" in t: return True
    if "شما توسط" in t and "کشته شدید" in t: return True
    if "منتقل شدید" in t and "شهر امن" in t: return True
    return False

def is_defense_win_message(text):
    t = _normalize_persian(text)
    if "اعلان پیروزی دفاعی" in t: return True
    if "مهاجم" in t and "شکست خورد" in t and "شهر امن" in t: return True
    if "غنیمت دفاعی" in t: return True
    return False

def is_team_attack_win(text):
    t = _normalize_persian(text)
    if "حمله تیمی موفق" in t: return True
    if "حمله تیمی" in t and "شکست خورد" in t and "غارت" in t and "موفق" in t: return True
    return False

def is_team_attack_loss(text):
    t = _normalize_persian(text)
    if "حمله تیمی نافرجام" in t: return True
    if "حمله تیمی" in t and "تیم مهاجم" in t and "شکست خورد" in t: return True
    if "تیم مهاجم شکست خورد" in t: return True
    return False

def is_defense_alert_message(text):
    t = _normalize_persian(text)
    if "اعلان آبی" in t and "دفاعی" in t: return True
    if "سپر دفاعی تیمی" in t: return True
    if "فراخوان اتحاد دفاعی" in t: return True
    return False

def is_profile_message(text):
    t = _normalize_persian(text)
    if "پروفایل اشرافی" in t: return True
    if "پروفایل بازیکن" in t: return True
    if "مشخصات فردی" in t: return True
    if "طبقه فعلی" in t and "مرز پیشروی" in t: return True
    return False

def parse_level_from_profile(text):
    t = _normalize_persian(normalize_digits(text))
    m = re.search(r'سطح\s+فعلی[:\s]+(\d+)', t)
    return int(m.group(1)) if m else None

def parse_profile_info(text):
    t = _normalize_persian(normalize_digits(text))
    current_floor = 0; max_floor = 0; location = "?"
    m = re.search(r'طبقه\s+فعلی[:\s]+(\d+)', t)
    if m: current_floor = int(m.group(1))
    m = re.search(r'مرز\s+پیشروی[:\s]+طبقه\s+(\d+)', t)
    if not m: m = re.search(r'مرز\s+پیشروی[:\s]+(\d+)', t)
    if m: max_floor = int(m.group(1))
    m = re.search(r'مکان\s+فعلی[:\s]+([^\n]+)', t)
    if m:
        location = m.group(1).strip()
        location = re.sub(r'\s*[🏰🏯🚪🗺️🗺]+\s*$', '', location).strip()
    return current_floor, max_floor, location

def is_teleport_prompt(text):
    t = _normalize_persian(text)
    return "دروازه" in t and "تلپورت" in t and ("شماره طبقه" in t or "شماره طبقه‌ای" in t)

def is_teleport_success(text):
    t = _normalize_persian(text)
    return "انتقال موفق" in t or ("تلپورت انجام شد" in t and "با موفقیت" in t)

def is_teleport_fail_no_money(text):
    return "موجودی سکه شما کافی نیست" in _normalize_persian(text)

def parse_teleport_result_floor(text):
    t = _normalize_persian(normalize_digits(text))
    m = re.search(r'موقعیت\s+فعلی[:\s]+طبقه\s+(\d+)', t)
    return int(m.group(1)) if m else None

def is_join_rejected(text):
    t = _normalize_persian(text)
    return "باید دقیقاً در طبقه" in t and "حضور داشته باشید" in t

def is_join_wrong_floor(text): return is_join_rejected(text)

def get_required_floor_from_reject(text):
    t = _normalize_persian(normalize_digits(text))
    m = re.search(r'دقیقاً در طبقه\s+(\d+)', t)
    return int(m.group(1)) if m else None

def is_join_need_outside(text):
    t = _normalize_persian(text)
    if "باید بیرون از شهر" in t: return True
    if "بیرون از شهر (منطقه ناامن)" in t: return True
    if "شما باید خارج از شهر" in t: return True
    if "خارج از شهر باشید" in t: return True
    return False

def is_target_in_safe_zone(text):
    t = _normalize_persian(text)
    if "بازیکن هدف در منطقه امن" in t: return True
    if "قابل حمله نیست" in t: return True
    return False

def is_not_same_floor_error(text):
    t = _normalize_persian(text)
    if "بازیکن هدف هم طبقه شما نیست" in t: return True
    if "حمله تیمی فقط بین بازیکنان هم طبقه" in t: return True
    return False

def is_user_inside_city(location):
    if not location: return False
    loc = _normalize_persian(location).lower()
    if "داخل شهر" in loc: return True
    if "منطقه امن" in loc: return True
    if "safe zone" in loc: return True
    if "بیرون" in loc: return False
    return False

def is_shop_message(text): return "فروشگاه شهر" in _normalize_persian(text)

def is_sell_list_message(text):
    t = _normalize_persian(text)
    if "فروشگاه شهر" in t: return True
    if "مغازه‌دار" in t and "فروش:" in t: return True
    if "sell_item" in t or "sell_mini" in t: return True
    return False

def is_sell_receipt(text):
    t = _normalize_persian(text)
    if "رسید رسمی فروش" in t: return True
    if "فروش با موفقیت انجام" in t: return True
    if "غنائم" in t and "فروش" in t and "موفقیت" in t: return True
    if "آیتم واگذار شده" in t and "دریافتی" in t: return True
    return False

def is_item_not_owned(text):
    return "این آیتم را در موجودی خود ندارید" in _normalize_persian(text)

def is_special_item(name): return "ویژه" in name

def is_equipment_item(name):
    if not name: return False
    n = _normalize_persian(name).lower()
    for tag in ["(armor)","(weapon)","(shield)","(helmet)","(ring)",
                "(boots)","(gloves)","(robe)","(cloak)"]:
        if tag in n: return True
    for w in ["شمشیر","زره","سپر","کلاه‌خود","کلاه خود","کلاهخود",
              "خنجر","نیزه","کمان","تبر","گرز","داس","چماق",
              "کارد","قمه","زوبین","دشنه","عصا","چوبدستی",
              "انگشتر","بازوبند","گردن‌بند","طلسم","سنگ جادو",
              "پوتین","چکمه","دستکش","سرنیزه","پیکان",
              "افسون","جادویی","کماندار","شمشیرزن","نیزه‌دار",
              "آرمر","ویپن","شیلد","هلمت","بووت"]:
        if w in n: return True
    for w in ["کلاه","تیغ","سنگین","سبک","فولادی","آهنی","برنزی",
              "طلایی","نقره‌ای","الماس","فلش"]:
        if re.search(r'(?<![\u0600-\u06FF])' + re.escape(w) + r'(?![\u0600-\u06FF])', n):
            return True
    return False

def clean_item_name(raw):
    if not raw: return ""
    t = _normalize_persian(raw).strip() # تبدیل نیم‌فاصله به فاصله
    t = re.sub(r'^\d+[\.\)]\s*', '', t)
    t = re.sub(r'^[^\w\u0600-\u06FF]+\s*', '', t)
    t = re.sub(r'\s*-\s*\(\d+\s*عدد\)', '', t)
    t = re.sub(r'\s*\(لول\s*\d+\)\s*-\s*شناسه:\s*\d+', '', t)
    return t.strip()
    t = re.sub(r'^\d+[\.\)]\s*', '', raw.strip())
    t = re.sub(r'^[^\w\u0600-\u06FF]+\s*', '', t)
    t = re.sub(r'\s*\(موجودی\s*:\s*\d+\)\s*-\s*قیمت\s*:\s*\d+C?', '', t)
    t = re.sub(r'\s*-\s*\(\d+\s*عدد\)', '', t)
    t = re.sub(r'\s*\(لول\s*\d+\)\s*-\s*شناسه\s*:\s*\d+', '', t)
    return t.strip()

def parse_sell_list(text):
    items = []
    if not text: return items
    lines = text.split('\n')
    current_name = None
    current_qty = 0
    for line in lines:
        line_s = line.strip()
        if not line_s: continue
        m = re.search(r'^.+?\s*\(موجودی:\s*(\d+)\)', line_s)
        if m:
            name_part = re.split(r'\s*\(موجودی:', line_s)[0]
            current_name = clean_item_name(name_part)
            current_qty = int(m.group(1))
            continue
        m = re.search(r'فروش:\s*`?(/[^`\s]+)`?', line_s)
        if m and current_name is not None:
            items.append({"name": current_name, "qty": current_qty, "cmd": m.group(1)})
            current_name = None
            current_qty = 0
    return items
    lines = text.split('\n')
    current_name = None
    current_qty = 0
    for line in lines:
        line_s = line.strip()
        if not line_s: continue
        m = re.search(r'^.+?\(موجودی:\s*(\d+)\)', line_s)
        if m:
            current_name = clean_item_name(line_s)
            current_qty = int(m.group(1))
            continue
        m = re.search(r'فروش:\s*[`\'"«]?(/[^\s`\'"»\n]+)', line_s)
        if m and current_name is not None:
            items.append({"name": current_name, "qty": current_qty, "cmd": m.group(1)})
            current_name = None
            current_qty = 0
    return items

def parse_inventory_items(text):
    if not text: return []
    items = []
    for line in text.split('\n'):
        line_s = line.strip()
        if not line_s: continue
        m = re.search(r'^\d+\.\s*(.+?)\s*-\s*\((\d+)\s*عدد\)\s*$', line_s)
        if m:
            items.append({"name": clean_item_name(m.group(1)), "qty": int(m.group(2))})
            continue
        m = re.search(r'^\d+\.\s*(.+?)\s*\(لول\s*\d+\)\s*-\s*شناسه', line_s)
        if m:
            items.append({"name": clean_item_name(m.group(1)), "qty": 1})
            continue
    return items


# ═══════════════════════════════════════════════════════
# No-Sell
# ═══════════════════════════════════════════════════════
def get_no_sell_list(user_id):
    user = users_db["users"].get(str(user_id))
    if not user: return []
    lst = user.get("no_sell", [])
    if not isinstance(lst, list): return []
    return lst

def set_no_sell_list(user_id, lst):
    uid = str(user_id); _ensure_user(uid)
    users_db["users"][uid]["no_sell"] = list(lst)
    save_json(USERS_FILE, users_db)

def add_no_sell_items(user_id, items):
    lst = get_no_sell_list(user_id)
    existing_lower = [x.lower() for x in lst]
    added = []; skipped = []
    for it in items:
        it = it.strip()
        if not it: continue
        if it.lower() in existing_lower:
            skipped.append(it)
        else:
            lst.append(it); existing_lower.append(it.lower()); added.append(it)
    if added: set_no_sell_list(user_id, lst)
    return added, skipped

def remove_no_sell_items(user_id, items):
    lst = get_no_sell_list(user_id)
    if not lst: return 0
    removed_total = 0
    for it in items:
        it_low = it.strip().lower()
        if not it_low: continue
        new_lst = [x for x in lst if x.strip().lower() != it_low]
        removed_total += (len(lst) - len(new_lst))
        lst = new_lst
    if removed_total: set_no_sell_list(user_id, lst)
    return removed_total

def item_matches_no_sell(name, no_sell_list):
    if not no_sell_list: return False
    nl = name.strip().lower()
    for ns in no_sell_list:
        ns_c = ns.strip().lower()
        if not ns_c: continue
        if ns_c in nl: return True
    return False

def parse_no_sell_args(arg):
    if not arg: return []
    parts = re.split(r'\s+[+\-*_]\s+|\n+', arg)
    return [p.strip() for p in parts if p.strip()]

async def fetch_inventory_quantities(user_id):
    try:
        client = user_clients.get(int(user_id))
        if not client or not client.is_connected():
            client = await ensure_user_client(user_id)
            if not client: return {}
        await _drain_sell_queue(user_id, "sell"); await asyncio.sleep(0.3)
        inv_resp = await _sell_send_and_wait(user_id, "🎒 موجودی من", 45, is_inventory_message, "sell")
        if not inv_resp: return {}
        quantities = {}
        for line in inv_resp.split('\n'):
            m = re.search(r'(.+?)\s*\(موجودی:\s*(\d+)\)', line)
            if m:
                nm = clean_item_name(m.group(1).strip())
                quantities[nm] = int(m.group(2))
        return quantities
    except Exception as e:
        log_error(f"fetch_inv {user_id}: {_translate_bot_errors(e)}")
        return {}
        # ═══════════════════════════════════════════════════════
# Hunt Adaptive
# ═══════════════════════════════════════════════════════
def get_hunt_state(user_id):
    st = hunt_floor_state.setdefault(user_id, {"safe_floor": 0, "level_at_test": 0, "banned": {}})
    if "banned" not in st: st["banned"] = {}
    return st

def is_floor_banned_for_hunt(user_id, floor):
    st = hunt_floor_state.get(user_id)
    if not st: return False
    banned = st.get("banned", {})
    until = banned.get(int(floor))
    if until is None: return False
    if time.time() >= until:
        del banned[int(floor)]; return False
    return True

def ban_floor_for_hunt(user_id, floor, cooldown=None):
    st = get_hunt_state(user_id)
    cd = cooldown if cooldown is not None else HUNT_FLOOR_COOLDOWN
    st["banned"][int(floor)] = time.time() + cd
    schedule_save_runtime()

async def _retry_hunt_once(user_id):
    try:
        await asyncio.sleep(6)
        client = user_clients.get(int(user_id))
        if not client or not client.is_connected():
            client = await ensure_user_client(user_id)
            if not client: return
        await _send_game_cmd(user_id, "🦖 شکار هیولا", tag="retry_hunt")
    except Exception as e: log_error(f"_retry_hunt_once {user_id}: {_translate_bot_errors(e)}")

async def _manual_floor_test(user_id, target_floor):
    try:
        async with get_user_lock(user_id):
            client = user_clients.get(int(user_id))
            if not client or not client.is_connected():
                client = await ensure_user_client(user_id)
                if not client:
                    await _notify_user(user_id, "❌ اتصال نیست."); return
            await _drain_sell_queue(user_id, "battle"); await asyncio.sleep(0.3)
            info_resp = await _sell_send_and_wait(user_id, "🪶 اطلاعات من", 45, is_profile_message, "battle")
            if not info_resp:
                await _notify_user(user_id, "❌ اطلاعات نیامد."); return
            cur, maxf, loc = parse_profile_info(info_resp)
            inside = is_user_inside_city(loc)
            await _notify_user(user_id, f"📍 فعلی: {cur} · مرز: {maxf}\n🎯 هدف: {target_floor}")
            if maxf > 0 and maxf < target_floor:
                await _notify_user(user_id, f"❌ مرز {maxf}، نمی‌تونم {target_floor}"); return
            if cur != target_floor:
                if not inside:
                    await _drain_sell_queue(user_id, "battle")
                    city_resp = await _sell_send_and_wait(user_id, "🏰 بازگشت به شهر", 45,
                        lambda t: is_city_arrival_message(t) or is_distance_error_message(t), "battle")
                    if city_resp and is_distance_error_message(city_resp):
                        await asyncio.sleep(1)
                        cr = await _sell_send_and_wait(user_id, "💎 استفاده از کریستال تلپورت اجباری",
                            45, is_crystal_success_message, "battle")
                        if not cr: await _notify_user(user_id, "❌ کریستال کمه"); return
                    await asyncio.sleep(1.5); inside = True
                await _drain_sell_queue(user_id, "battle")
                tp = await _sell_send_and_wait(user_id, "🌀 تلپورت به طبقات", 45, is_teleport_prompt, "battle")
                if not tp:
                    await _notify_user(user_id, "❌ منوی تلپورت نیامد"); return
                await asyncio.sleep(1); await _drain_sell_queue(user_id, "battle")
                tr = await _sell_send_and_wait(user_id, str(target_floor), 45,
                    lambda t: is_teleport_success(t) or is_teleport_fail_no_money(t), "battle")
                if not (tr and is_teleport_success(tr)):
                    await _notify_user(user_id, f"❌ تلپورت به {target_floor} نشد"); return
                await asyncio.sleep(1.5); inside = True
            if inside:
                exit_resp = await _sell_send_and_wait(user_id, "🏰 خروج از شهر!", 45, is_city_exit_message, "battle")
                if not exit_resp:
                    try: await _send_game_cmd(user_id, "🏰 خروج از شهر!", tag="manual_test")
                    except: pass
                    await asyncio.sleep(3)
                else:
                    await asyncio.sleep(1)
            await _drain_sell_queue(user_id, "battle")
            result = await _sell_send_and_wait(user_id, "🦖 شکار هیولا", 60,
                lambda t: is_hunt_success(t) or is_hunt_cooldown(t) or is_hunt_safe_zone(t)
                          or is_hunt_failure_return_city(t) or is_dungeon_hunt_win(t), "battle")
            if not result:
                await _notify_user(user_id, f"⚠️ تست طبقه {target_floor}: جوابی نیامد"); return
            if is_hunt_success(result) or is_dungeon_hunt_win(result):
                await _notify_user(user_id, f"✅ طبقه {target_floor}: موفق")
            elif is_hunt_failure_return_city(result):
                await _notify_user(user_id, f"💀 طبقه {target_floor}: ناموفق")
            elif is_hunt_cooldown(result):
                await _notify_user(user_id, f"⏱ طبقه {target_floor}: کول‌داون")
            elif is_hunt_safe_zone(result):
                await _notify_user(user_id, f"🏰 طبقه {target_floor}: منطقه امن")
            else:
                await _notify_user(user_id, f"⚠️ نتیجه طبقه {target_floor} نامشخص")
    except Exception as e:
        log_error(f"_manual_floor_test {user_id}: {_translate_bot_errors(e)}")
        await _notify_user(user_id, f"❌ خطا: {_translate_bot_errors(e)}")

async def _handle_hunt_failure(user_id, chat_id, test_cmd="🦖 شکار هیولا"):
    if not is_floor_test_enabled(user_id):
        log_error(f"⏸ floor test off for {user_id}, skip"); return
    try:
        client = user_clients.get(int(user_id))
        if not client or not client.is_connected():
            client = await ensure_user_client(user_id)
            if not client: return
        async with get_user_lock(user_id):
            await _drain_sell_queue(user_id, "battle"); await asyncio.sleep(0.3)
            info_resp = await _sell_send_and_wait(user_id, "🪶 اطلاعات من", 45,
                is_profile_message, "battle")
            if not info_resp:
                log_error(f"💀 hunt fail {user_id}: no profile"); return
            cur_floor, max_floor, location = parse_profile_info(info_resp)
            level = parse_level_from_profile(info_resp) or 0
            inside_city = is_user_inside_city(location)
            if inside_city:
                log_error(f"💀 hunt fail inside city, skip: {user_id}"); return
            st = get_hunt_state(user_id)
            level_at_test = st.get("level_at_test", 0)
            if level_at_test > 0 and level >= level_at_test + HUNT_LEVEL_RETRY_STEP:
                st["banned"] = {}; st["level_at_test"] = level
                schedule_save_runtime()
                await _notify_user(user_id,
                    f"🆙 لول +{HUNT_LEVEL_RETRY_STEP} شد\n🎯 همه banها آزاد شدن")
                return
            if cur_floor > 0:
                ban_floor_for_hunt(user_id, cur_floor)
                if max_floor and cur_floor + 1 <= max_floor:
                    ban_floor_for_hunt(user_id, cur_floor + 1)
            if level > 0 and st.get("level_at_test", 0) == 0:
                st["level_at_test"] = level
                schedule_save_runtime()
            target_floor = max(1, cur_floor - HUNT_FLOOR_STEP)
            log_error(f"💀 hunt fail: cur={cur_floor} → target={target_floor}")
            await _notify_user(user_id, f"💀 شکار ناموفق\n🔄 می‌رم طبقه {target_floor} تست کنم...")
            if cur_floor != target_floor:
                if not inside_city:
                    await _drain_sell_queue(user_id, "battle")
                    city_resp = await _sell_send_and_wait(user_id, "🏰 بازگشت به شهر", 45,
                        lambda t: is_city_arrival_message(t) or is_distance_error_message(t), "battle")
                    if city_resp and is_distance_error_message(city_resp):
                        await asyncio.sleep(1)
                        cr = await _sell_send_and_wait(user_id,
                            "💎 استفاده از کریستال تلپورت اجباری", 45, is_crystal_success_message, "battle")
                        if not cr:
                            await _notify_user(user_id, "❌ کریستال کمه"); return
                    await asyncio.sleep(1.5)
                await _drain_sell_queue(user_id, "battle")
                tp_prompt = await _sell_send_and_wait(user_id, "🌀 تلپورت به طبقات", 45, is_teleport_prompt, "battle")
                if tp_prompt:
                    await asyncio.sleep(1); await _drain_sell_queue(user_id, "battle")
                    tp_res = await _sell_send_and_wait(user_id, str(target_floor), 45,
                        lambda t: is_teleport_success(t) or is_teleport_fail_no_money(t), "battle")
                    if not (tp_res and is_teleport_success(tp_res)):
                        await _notify_user(user_id, f"❌ تلپورت {target_floor} نشد"); return
                    await asyncio.sleep(1.5)
            await _drain_sell_queue(user_id, "battle")
            exit_resp = await _sell_send_and_wait(user_id, "🏰 خروج از شهر!", 45, is_city_exit_message, "battle")
            if not exit_resp:
                try: await _send_game_cmd(user_id, "🏰 خروج از شهر!", tag="hunt_fail_out")
                except: pass
                await asyncio.sleep(3)
            else:
                await asyncio.sleep(2)
            await _drain_sell_queue(user_id, "battle")
            await _notify_user(user_id, f"🎯 حالا تو طبقه {target_floor} شکار می‌زنم...")
            test_resp = await _sell_send_and_wait(user_id, test_cmd, 60,
                lambda t: is_hunt_success(t) or is_hunt_cooldown(t) or is_hunt_safe_zone(t)
                          or is_crystal_luck_prompt(t) or is_hunt_failure_return_city(t)
                          or is_dungeon_hunt_win(t), "battle")
            if test_resp and is_hunt_failure_return_city(test_resp):
                ban_floor_for_hunt(user_id, target_floor)
                await _notify_user(user_id,
                    f"💀 تو طبقه {target_floor} هم باختم\n⏱ این طبقه هم ban شد")
            elif test_resp and (is_hunt_success(test_resp) or is_dungeon_hunt_win(test_resp)):
                st["safe_floor"] = target_floor
                schedule_save_runtime()
                await _notify_user(user_id,
                    f"✅ تو طبقه {target_floor} موفق شدم\n📍 اینجام می‌مونم")
            elif test_resp and is_hunt_cooldown(test_resp):
                await _notify_user(user_id, f"⏱ طبقه {target_floor} — کول‌داون")
            else:
                await _notify_user(user_id, f"⚠️ نتیجه طبقه {target_floor} نامشخص")
    except Exception as e:
        log_error(f"_handle_hunt_failure {user_id}: {_translate_bot_errors(e)}")

# ═══════════════════════════════════════════════════════
# Pew Heal
# ═══════════════════════════════════════════════════════
def parse_pew_hp(text):
    if not text: return None
    t = _normalize_persian(text)
    m = re.search(r'سلامتی\s+فعلی\s*[:：]\s*(\d+)\s*/\s*(\d+)', t)
    if m:
        try: return ("self", int(m.group(1)), int(m.group(2)))
        except: pass
    m = re.search(r'سلامتی\s+باقی[\s‌]?مانده[\s‌]?ی\s+(.+?)\s*[:：]\s*(\d+)\s*/\s*(\d+)', t)
    if not m:
        m = re.search(r'سلامتی\s+([^:：\n]+?)\s*[:：]\s*(\d+)\s*/\s*(\d+)', t)
    if m:
        try:
            name = m.group(1).strip()
            name = re.sub(r'^[^\w\u0600-\u06FF]+', '', name).strip()
            name = re.sub(r'[^\w\u0600-\u06FF]+$', '', name).strip()
            return (name or "?", int(m.group(2)), int(m.group(3)))
        except: pass
    m = re.search(r'(?:HP|سلامتی)[^\d]*(\d+)\s*/\s*(\d+)', t, re.IGNORECASE)
    if m:
        try: return ("?", int(m.group(1)), int(m.group(2)))
        except: pass
    return None

def is_pew_heal_full(text):
    if not text: return False
    t = _normalize_persian(text)
    if "از قبل کامله" in t: return True
    if "نیازی به هیل نیست" in t: return True
    if "کاملاً سالمه" in t: return True
    if "کاملا سالمه" in t: return True
    return False

async def _pew_heal_loop(uid, chat_id):
    key = int(uid)
    try:
        for i in range(PEW_HEAL_MAX_ATTEMPTS):
            if pew_heal_tasks.get(key) is not asyncio.current_task():
                return
            client = user_clients.get(key)
            if not client or not client.is_connected():
                client = await ensure_user_client(uid)
                if not client: return
            try:
                await client.send_message(chat_id, "پیو هیل")
                log_error(f"💚 heal #{i+1} for {uid}")
            except Exception as e:
                log_error(f"heal send {uid}: {_translate_bot_errors(e)}")
                return
            await asyncio.sleep(PEW_HEAL_INTERVAL)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        log_error(f"heal loop {uid}: {_translate_bot_errors(e)}")
    finally:
        if pew_heal_tasks.get(key) is asyncio.current_task():
            pew_heal_tasks.pop(key, None)

def _start_pew_heal(uid, chat_id):
    key = int(uid)
    old = pew_heal_tasks.get(key)
    if old and not old.done(): return
    pew_heal_tasks[key] = asyncio.create_task(_pew_heal_loop(uid, chat_id))

def _stop_pew_heal(uid):
    key = int(uid)
    task = pew_heal_tasks.pop(key, None)
    if task and not task.done(): task.cancel()

# ═══════════════════════════════════════════════════════
# Group resolver
# ═══════════════════════════════════════════════════════
async def _resolve_pew_group(client, event):
    txt = (event.raw_text or "").strip()
    if not txt: return None, "invalid"
    m = re.match(r'^(?:https?://)?t\.me/(?:c/)?(?:joinchat/)?\+?([^/\s?]+)', txt)
    if m:
        key = m.group(1)
        if "t.me/+" in txt or "joinchat" in txt:
            return None, "not_member"
        if key.isdigit():
            try:
                cid = int("-100" + key)
                ent = await client.get_entity(cid)
                return {"id": int(ent.id),
                        "title": getattr(ent, 'title', None) or str(cid)}, None
            except Exception as e:
                log_error(f"resolve -100{key} fail: {_translate_bot_errors(e)}")
                return None, "not_member"
        else:
            try:
                ent = await client.get_entity("@" + key)
                if getattr(ent, 'broadcast', False) and not getattr(ent, 'megagroup', False):
                    return None, "is_channel"
                return {"id": int(ent.id),
                        "title": getattr(ent, 'title', None) or key}, None
            except Exception as e:
                log_error(f"resolve @{key} fail: {type(e).__name__}: {_translate_bot_errors(e)}")
                return None, "not_member"
    if txt.startswith("@"):
        try:
            ent = await client.get_entity(txt)
            if getattr(ent, 'broadcast', False) and not getattr(ent, 'megagroup', False):
                return None, "is_channel"
            return {"id": int(ent.id),
                    "title": getattr(ent, 'title', None) or txt}, None
        except Exception as e:
            log_error(f"resolve {txt} fail: {type(e).__name__}: {_translate_bot_errors(e)}")
            return None, "not_member"
    norm = normalize_digits(txt).strip()
    if norm.lstrip("-").isdigit():
        try: cid = int(norm)
        except: return None, "invalid"
        candidates = []
        if str(cid).startswith("-100"): candidates.append(cid)
        elif str(cid).startswith("-"): candidates.append(cid)
        else:
            candidates.append(cid)
            candidates.append(int("-100" + norm))
        for c in candidates:
            try:
                ent = await client.get_entity(c)
                if getattr(ent, 'broadcast', False) and not getattr(ent, 'megagroup', False):
                    return None, "is_channel"
                return {"id": int(ent.id),
                        "title": getattr(ent, 'title', None) or str(c)}, None
            except: continue
        return None, "not_member"
    return None, "invalid"

# ═══════════════════════════════════════════════════════
# Client mgmt
# ═══════════════════════════════════════════════════════
def _start_user_profile_tasks(user_id):
    uid = int(user_id)
    if not is_user_active(uid) or not is_user_allowed(uid):
        return
    try:
        user_cfg = users_db.get("users", {}).get(str(uid), {})
        if user_cfg.get("name_emoji", {}).get("enabled"):
            start_name_emoji_task(uid)
        if user_cfg.get("random_profile", {}).get("enabled"):
            start_random_profile_task(uid)
    except Exception as e:
        log_error(f"restart profile tasks {uid}: {_translate_bot_errors(e)}")
    try:
        if monitor_db.get(str(uid), {}).get("enabled"):
            start_monitor_task(uid)
    except Exception as e:
        log_error(f"restart profile monitor {uid}: {_translate_bot_errors(e)}")


async def ensure_user_client(user_id):
    client = user_clients.get(int(user_id))
    if client and client.is_connected():
        try:
            if await client.is_user_authorized():
                _start_user_profile_tasks(user_id)
                return client
        except: pass
    session_path = SESSION_DIR / str(user_id)
    if not os.path.exists(str(session_path) + ".session"): return None
    try:
        new_client = TelegramClient(str(session_path), API_ID, API_HASH)
        await new_client.connect()
        if await new_client.is_user_authorized():
            if client:
                try: await client.disconnect()
                except: pass
            user_clients[int(user_id)] = new_client
            new_client.add_event_handler(make_user_handler(user_id), events.NewMessage)
            new_client.add_event_handler(make_battle_handler(user_id), events.NewMessage)
            new_client.add_event_handler(make_sync_handler(user_id), events.NewMessage)
            await update_user_name_from_account(user_id, new_client)
            await update_user_phone_from_account(user_id, new_client)
            clear_relogin_flag(user_id)
            _start_user_profile_tasks(user_id)
            return new_client
        await new_client.disconnect()
        _spawn(notify_disconnect(user_id)); return None
    except Exception as e:
        log_error(f"ensure_user_client {user_id}: {_translate_bot_errors(e)}")
        _spawn(notify_disconnect(user_id)); return None

async def disconnect_user_client(user_id):
    if user_id in user_clients:
        try: await user_clients[user_id].disconnect()
        except: pass
        del user_clients[user_id]

async def create_user_client(user_id):
    session_path = SESSION_DIR / str(user_id)
    if user_id in user_clients:
        client = user_clients[user_id]
        try:
            if client.is_connected() and await client.is_user_authorized():
                await update_user_name_from_account(user_id, client)
                await update_user_phone_from_account(user_id, client)
                clear_relogin_flag(user_id)
                _start_user_profile_tasks(user_id)
                return client
        except: pass
        try: await client.disconnect()
        except: pass
        del user_clients[user_id]
    client = TelegramClient(str(session_path), API_ID, API_HASH)
    try:
        await client.connect()
        if await client.is_user_authorized():
            user_clients[user_id] = client
            client.add_event_handler(make_user_handler(user_id), events.NewMessage)
            client.add_event_handler(make_battle_handler(user_id), events.NewMessage)
            client.add_event_handler(make_sync_handler(user_id), events.NewMessage)
            await update_user_name_from_account(user_id, client)
            await update_user_phone_from_account(user_id, client)
            clear_relogin_flag(user_id)
            _start_user_profile_tasks(user_id)
            return client
        await client.disconnect()
        _spawn(notify_disconnect(user_id)); return None
    except Exception as e:
        log_error(f"create_user_client {user_id}: {_translate_bot_errors(e)}")
        _spawn(notify_disconnect(user_id)); return None

# ═══════════════════════════════════════════════════════
# پونی
# ═══════════════════════════════════════════════════════
def is_pony_profile_message(text):
    t = _normalize_persian(text)
    if "پروفایل پونی" in t: return True
    if "پونی" in t and "موجودی فعلی" in t and "ارتقای بعدی" in t: return True
    return False

def parse_pony_info(text):
    t = _normalize_persian(normalize_digits(text))
    balance = None; upgrade_cost = None
    m = re.search(r'موجودی\s+فعلی[:\s]*([\d,]+)', t)
    if m:
        try: balance = int(m.group(1).replace(",", ""))
        except: pass
    m = re.search(r'ارتقای\s+بعدی[:\s]*([\d,]+)', t)
    if m:
        try: upgrade_cost = int(m.group(1).replace(",", ""))
        except: pass
    return balance, upgrade_cost

def parse_pony_level(text):
    t = _normalize_persian(normalize_digits(text))
    m = re.search(r'سطح\s*[:：]?\s*(\d+)\s*/\s*(\d+)', t)
    if m: return int(m.group(1)), int(m.group(2))
    m = re.search(r'\b(\d{1,3})\s*/\s*(\d{1,3})\b', t)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        if 0 < a <= b <= 100: return a, b
    return None, None

def parse_pony_fill_percent(text):
    if not text: return None
    t = _normalize_persian(normalize_digits(text))
    for m in re.finditer(r'(\d{1,3})\s*%', t):
        try:
            v = int(m.group(1))
            if 0 <= v <= 100: return v
        except: pass
    return None

async def click_button_by_text(message, button_text):
    try:
        btns = getattr(message, 'buttons', None)
        if btns:
            for row in btns:
                for btn in row:
                    if button_text in (btn.text or ""):
                        await btn.click()
                        log_error(f"🖱 clicked btn: {btn.text}"); return True
    except Exception as e: log_error(f"click_btn {button_text}: {_translate_bot_errors(e)}")
    return False

def has_button_with_text(message, button_text):
    try:
        btns = getattr(message, 'buttons', None)
        if btns:
            for row in btns:
                for btn in row:
                    if button_text in (btn.text or ""): return True
    except: pass
    try:
        rm = getattr(message, 'reply_markup', None)
        rows = getattr(rm, 'rows', None)
        if rows:
            for row in rows:
                for btn in getattr(row, 'buttons', []) or []:
                    txt = getattr(btn, 'text', '') or ''
                    if button_text in txt: return True
    except: pass
    return False

async def _wait_for_pony_sample(user_id, chat_id, timeout=60, since_ts=0):
    key = (int(user_id), int(chat_id))
    deadline = time.time() + timeout
    while time.time() < deadline:
        st = pony_state.get(key, {})
        samples = st.get("samples", [])
        if samples and samples[-1][0] > since_ts: return samples[-1]
        await asyncio.sleep(2)
    return None

async def pony_retry_task(user_id):
    try:
        for attempt in range(3):
            await asyncio.sleep(PONY_RETRY_DELAY)
            if user_id not in pony_waiting: return
            state = pony_waiting.get(user_id, {})
            chat_id = state.get("chat_id")
            cfg = pony_config.get((int(user_id), int(chat_id)), {}) if chat_id else {}
            if not cfg.get("collect"):
                pony_waiting.pop(user_id, None); return
            client = state.get("client")
            if not client or not chat_id: return
            try: await client.send_message(chat_id, "پونی")
            except: pass
            if attempt == 2:
                await asyncio.sleep(PONY_RETRY_DELAY)
                if user_id in pony_waiting:
                    pony_waiting.pop(user_id, None)
                    try: await _notify_user(user_id, "⚠️ پونی جواب نداد!")
                    except: pass
    except asyncio.CancelledError: pass
    except Exception as e: log_error(f"pony_retry {user_id}: {_translate_bot_errors(e)}")

async def run_pony_workflow(user_id, chat_id):
    cfg = pony_config.get((int(user_id), int(chat_id)))
    if not cfg or not cfg.get("collect"): return
    client = user_clients.get(int(user_id))
    if not client or not client.is_connected():
        client = await ensure_user_client(user_id)
        if not client: return
    old = pony_waiting.get(user_id, {})
    old_task = old.get("retry_task")
    if old_task and not old_task.done(): old_task.cancel()
    pony_waiting[user_id] = {"chat_id": int(chat_id), "client": client, "retry_task": None}
    try:
        await client.send_message(chat_id, "پونی")
    except Exception as e:
        log_error(f"run_pony {user_id}: {_translate_bot_errors(e)}")
        pony_waiting.pop(user_id, None); return
    pony_waiting[user_id]["retry_task"] = asyncio.create_task(pony_retry_task(user_id))

async def handle_pony_response(event, user_id):
    try:
        state = pony_waiting.pop(user_id, None)
        if state:
            rt = state.get("retry_task")
            if rt and not rt.done(): rt.cancel()
        chat_id = state.get("chat_id") if state else event.chat_id
        cfg = pony_config.get((int(user_id), int(chat_id)), {})
        if not cfg.get("collect"): return
        msg = event.message
        st_key = (int(user_id), int(chat_id))
        st = pony_state.get(st_key, {})
        phase = st.get("phase", "learning")
        raw = msg.raw_text or ""
        fill = parse_pony_fill_percent(raw)
        if fill is not None:
            st["last_fill"] = fill
            if phase == "learning":
                now = time.time()
                st.setdefault("samples", []).append((now, fill))
                st["samples"] = [(t, f) for t, f in st["samples"] if now - t < 3600]
            pony_state[st_key] = st
            schedule_save_runtime()
        if phase == "learning": return
        raw_lower = (msg.raw_text or "").lower()
        has_collect = (has_button_with_text(msg, "برداشت") or
            "برداشت" in raw_lower or "درآمد" in raw_lower)
        has_upgrade = (has_button_with_text(msg, "ارتقای پونی") or
            has_button_with_text(msg, "ارتقاء پونی") or
            "ارتقای پونی" in raw_lower or "ارتقاء پونی" in raw_lower)
        has_convert = (has_button_with_text(msg, "تبدیل") or
            has_button_with_text(msg, "تغیر پونی") or
            "تبدیل به پونی" in raw_lower or "تغیر پونی" in raw_lower)
        if has_collect:
            await click_button_by_text(msg, "برداشت")
            await asyncio.sleep(2.5)
            try:
                msg = await event.client.get_messages(event.chat_id, ids=msg.id)
                raw_lower2 = (msg.raw_text or "").lower()
                has_upgrade = (has_button_with_text(msg, "ارتقای پونی") or
                    has_button_with_text(msg, "ارتقاء پونی") or
                    "ارتقای پونی" in raw_lower2 or "ارتقاء پونی" in raw_lower2)
                has_convert = (has_button_with_text(msg, "تبدیل") or
                    has_button_with_text(msg, "تغیر پونی") or
                    "تبدیل به پونی" in raw_lower2 or "تغیر پونی" in raw_lower2)
                if has_upgrade or has_convert:
                    st["max_notified"] = False
                    pony_state[st_key] = st
            except: pass
        if cfg.get("upgrade"):
            cur_level, max_level = parse_pony_level(msg.raw_text or "")
            is_truly_max = False
            if cur_level is not None and max_level is not None:
                if cur_level >= max_level: is_truly_max = True
            else:
                balance, upgrade_cost = parse_pony_info(msg.raw_text or "")
                if upgrade_cost is None or upgrade_cost == 0:
                    if not has_upgrade and not has_convert: is_truly_max = True
            if is_truly_max:
                if not st.get("max_notified", False):
                    try:
                        await _notify_user(user_id,
                            "🐴 پونی به آخرین سطح رسید!\n\n"
                            "دو راه داری:\n"
                            "  • برو پونی بعدی (تبدیل)\n"
                            "  • یا ارتقا رو خاموش کن: از پنل")
                    except: pass
                    st["max_notified"] = True; pony_state[st_key] = st
            else:
                balance, upgrade_cost = parse_pony_info(msg.raw_text or "")
                if has_upgrade and balance is not None and upgrade_cost is not None and balance >= upgrade_cost:
                    await click_button_by_text(msg, "ارتقای پونی")
                    st["max_notified"] = False; pony_state[st_key] = st
                else:
                    if st.get("max_notified"):
                        st["max_notified"] = False; pony_state[st_key] = st
    except Exception as e: log_error(f"handle_pony {user_id}: {_translate_bot_errors(e)}")

async def naz_auto_loop(user_id, chat_id):
    """Send the configured short message to this user's selected group periodically."""
    uid, cid = int(user_id), int(chat_id)
    key = (uid, cid)
    this_task = asyncio.current_task()
    try:
        while True:
            cfg = pony_config.get(key, {})
            if not cfg.get("naz_enabled"):
                break
            if not is_user_active(uid) or not is_user_allowed(uid):
                break
            client = user_clients.get(uid)
            if not client or not client.is_connected():
                client = await ensure_user_client(uid)
            if client and client.is_connected() and pony_config.get(key, {}).get("naz_enabled"):
                try:
                    async with get_user_lock(uid):
                        if pony_config.get(key, {}).get("naz_enabled"):
                            await client.send_message(cid, "ناز")
                    log_error(f"💞 auto-naz sent to group {cid} for {uid}")
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    log_error(f"auto-naz {uid}/{cid}: {_translate_bot_errors(e)}")
            sent_at = time.monotonic()
            # Read the interval during the wait so changing 3/5 minutes applies
            # to the current cycle. The extra 10 seconds are part of the interval.
            while pony_config.get(key, {}).get("naz_enabled"):
                current = pony_config.get(key, {})
                minutes = int(current.get("naz_interval_mins", 3) or 3)
                interval = (minutes * 60) + 10
                remaining = interval - (time.monotonic() - sent_at)
                if remaining <= 0:
                    break
                await asyncio.sleep(min(5, remaining))
    except asyncio.CancelledError:
        pass
    except Exception as e:
        log_error(f"naz_auto_loop {uid}/{cid}: {_translate_bot_errors(e)}")
    finally:
        if naz_auto_tasks.get(key) is this_task:
            naz_auto_tasks.pop(key, None)


def start_naz_auto_task(user_id, chat_id):
    key = (int(user_id), int(chat_id))
    task = naz_auto_tasks.get(key)
    if task and not task.done():
        return False
    naz_auto_tasks[key] = asyncio.create_task(naz_auto_loop(*key))
    return True


def stop_naz_auto_task(user_id, chat_id):
    key = (int(user_id), int(chat_id))
    task = naz_auto_tasks.pop(key, None)
    if task and not task.done():
        task.cancel()


async def pony_loop(user_id, chat_id):
    """Run pony collection on the user's configured interval without overlapping attempts."""
    key = (int(user_id), int(chat_id))
    this_task = asyncio.current_task()
    try:
        while True:
            cfg = pony_config.get(key, {})
            if not cfg.get("collect"):
                break
            if not is_user_active(user_id) or not is_user_allowed(user_id):
                break

            st = pony_state.setdefault(key, {
                "phase": "auto", "samples": [], "learned": None,
                "start_ts": time.time(), "last_fill": 0, "max_notified": False})
            # Manual intervals replace the old learning cadence, while retaining
            # all state used by response handling (upgrade/max-level notifications).
            if st.get("phase") != "auto":
                st["phase"] = "auto"
                pony_state[key] = st

            # The bot's retry workflow is per-user, so wait for any in-flight
            # attempt before issuing another command (even if another chat started it).
            waited_for_pending = 0
            while pony_waiting.get(int(user_id)):
                if not pony_config.get(key, {}).get("collect"):
                    return
                pending = pony_waiting.get(int(user_id))
                retry_task = pending.get("retry_task") if pending else None
                if waited_for_pending >= 75:
                    if retry_task and not retry_task.done():
                        retry_task.cancel()
                    if pony_waiting.get(int(user_id)) is pending:
                        pony_waiting.pop(int(user_id), None)
                    log_error(f"pony pending attempt timed out for {user_id}/{chat_id}")
                    break
                await asyncio.sleep(1)
                waited_for_pending += 1

            cfg = pony_config.get(key, {})
            if not cfg.get("collect"):
                break
            cycle_started = time.monotonic()
            sent = False
            async with get_user_lock(user_id):
                # Recheck after taking the lock to avoid simultaneous sends from
                # two pony tasks belonging to the same user.
                if not pony_waiting.get(int(user_id)):
                    await run_pony_workflow(user_id, chat_id)
                    sent = True
            if not sent:
                await asyncio.sleep(1)
                continue

            # Wait for the response/retry workflow to finish before the next cycle.
            waited = 0
            while pony_waiting.get(int(user_id)):
                if not pony_config.get(key, {}).get("collect"):
                    return
                if waited >= 75:
                    pending = pony_waiting.get(int(user_id))
                    retry_task = pending.get("retry_task") if pending else None
                    if retry_task and not retry_task.done():
                        retry_task.cancel()
                    if pony_waiting.get(int(user_id)) is pending:
                        pony_waiting.pop(int(user_id), None)
                    log_error(f"pony response timed out for {user_id}/{chat_id}")
                    break
                await asyncio.sleep(1)
                waited += 1

            # Interval is measured between command starts. It is read repeatedly,
            # so changing it in the panel takes effect without restarting the task.
            while pony_config.get(key, {}).get("collect"):
                current = pony_config.get(key, {})
                interval = max(1, int(current.get("interval_mins", 15))) * 60
                remaining = interval - (time.monotonic() - cycle_started)
                if remaining <= 0:
                    break
                await asyncio.sleep(min(5, remaining))
            if not pony_config.get(key, {}).get("collect"):
                return
    except asyncio.CancelledError:
        pass
    except Exception as e:
        log_error(f"pony_loop {user_id}: {_translate_bot_errors(e)}")
    finally:
        # A cancelled old loop must not remove a newer task registered under the same key.
        if pony_tasks.get(key) is this_task:
            pony_tasks.pop(key, None)

def start_pony_task(user_id, chat_id):
    key = (int(user_id), int(chat_id))
    task = pony_tasks.get(key)
    if task and not task.done(): return False
    pony_tasks[key] = asyncio.create_task(pony_loop(user_id, chat_id))
    return True

def stop_pony_task(user_id, chat_id=None):
    if chat_id is not None:
        key = (int(user_id), int(chat_id))
        task = pony_tasks.pop(key, None)
        if task and not task.done(): task.cancel()
    else:
        for k in [k for k in list(pony_tasks.keys()) if k[0] == int(user_id)]:
            task = pony_tasks.pop(k, None)
            if task and not task.done(): task.cancel()

# ═══════════════════════════════════════════════════════
# دانجن
# ═══════════════════════════════════════════════════════
def _clean_btn_text(txt):
    return re.sub(r'[^\w\s\u0600-\u06FF]', '', txt or '').strip()

def is_dungeon_menu_message(message):
    try:
        btns = getattr(message, 'buttons', None) or []
        count = 0
        for row in btns:
            for btn in row:
                clean = _clean_btn_text(btn.text or "")
                for m in DUNGEON_MONSTERS:
                    if m and (clean == m or m in clean):
                        count += 1; break
        return count >= 3
    except: return False

def is_dungeon_win(text):
    if not text: return False
    t = _normalize_persian(text)
    if "شکست خوردید" in t: return False
    if "شکست خوردين" in t: return False
    if "چیزی رو از دست ندادی" in t: return False
    if "چيزي رو از دست ندادي" in t: return False
    if "متاسفانه" in t: return False
    if "متأسفانه" in t: return False
    if "شما پیروز شدید" in t: return True
    if "شکست دادید" in t: return True
    if "شکست دادين" in t: return True
    if "رو شکست دادید" in t: return True
    if "نابود کردید" in t: return True
    if "نابود کردين" in t: return True
    if "شما برنده شدید" in t: return True
    if "کوین دریافت شده" in t: return True
    if "با موفقیت" in t and "شکست" in t: return True
    if "با موفقیت" in t and "نابود" in t: return True
    return False

def is_dungeon_loss(text):
    if not text: return False
    t = _normalize_persian(text)
    if "شکست خوردید" in t: return True
    if "شکست خوردين" in t: return True
    if "چیزی رو از دست ندادی" in t: return True
    if "متاسفانه" in t: return True
    return False

async def click_dungeon_monster(message, monster_name):
    try:
        btns = getattr(message, 'buttons', None)
        if not btns: return False
        for row in btns:
            for btn in row:
                clean = _clean_btn_text(btn.text or "")
                if monster_name and (clean == monster_name or monster_name in clean):
                    await btn.click()
                    return True
    except Exception as e: log_error(f"click_dungeon_monster {monster_name}: {_translate_bot_errors(e)}")
    return False

async def handle_dungeon_response(event, user_id):
    try:
        state = dungeon_waiting.get(user_id)
        if not state: return False
        if time.time() - state.get("sent_at", 0) > DUNGEON_FLOW_TIMEOUT:
            dungeon_waiting.pop(user_id, None); return False
        stage = state.get("stage")
        msg = event.message
        text = event.raw_text or ""
        if is_dungeon_win(text):
            dungeon_waiting.pop(user_id, None)
            _spawn(_on_dungeon_win(user_id, state)); return True
        if is_dungeon_loss(text):
            dungeon_waiting.pop(user_id, None)
            _spawn(_on_dungeon_loss(user_id, state)); return True
        if stage == "menu":
            if is_dungeon_menu_message(msg):
                idx = state.get("monster_idx", 0)
                monster = DUNGEON_MONSTERS[idx] if 0 <= idx < len(DUNGEON_MONSTERS) else DUNGEON_MONSTERS[0]
                if await click_dungeon_monster(msg, monster):
                    state["stage"] = "attack_prompt"; state["sent_at"] = time.time()
                    dungeon_waiting[user_id] = state; return True
            return False
        if stage == "attack_prompt":
            if has_button_with_text(msg, "حمله به هیولا"):
                await click_button_by_text(msg, "حمله به هیولا")
                state["stage"] = "result"; state["sent_at"] = time.time()
                dungeon_waiting[user_id] = state; return True
            return False
        return False
    except Exception as e: log_error(f"handle_dungeon {user_id}: {_translate_bot_errors(e)}")
    return False

async def _on_dungeon_win(user_id, state):
    try:
        chat_id = state.get("chat_id", 0)
        key = (int(user_id), int(chat_id))
        cfg = dungeon_config.setdefault(key, {"enabled": False, "current_idx": 0,
            "working_idx": -1, "test_mode": False, "mode": "auto", "manual_idx": 0})
        idx = state.get("monster_idx", 0)
        mode = cfg.get("mode", "auto")
        cfg["working_idx"] = idx
        dungeon_config[key] = cfg
        schedule_save_runtime()
        if mode == "manual":
            if not cfg.get("manual_notified", False):
                monster = DUNGEON_MONSTERS[idx]
                try:
                    await _notify_user(user_id,
                        f"🏆 دانجن (دستی): «{monster}» رو زدم!\n📍 از این به بعد همین رو می‌زنم.")
                except: pass
                cfg["manual_notified"] = True; dungeon_config[key] = cfg
        else:
            was_testing = state.get("test_mode", False) or cfg.get("working_idx", -1) < 0
            cfg["current_idx"] = idx; cfg["test_mode"] = False; dungeon_config[key] = cfg
            if was_testing:
                monster = DUNGEON_MONSTERS[idx]
                try:
                    await _notify_user(user_id,
                        f"🏆 دانجن: تونستم «{monster}» رو بزنم!\n📍 از این به بعد روی همین می‌مونم.")
                except: pass
    except Exception as e: log_error(f"_on_dungeon_win {user_id}: {_translate_bot_errors(e)}")

async def _on_dungeon_loss(user_id, state):
    try:
        chat_id = state.get("chat_id", 0)
        key = (int(user_id), int(chat_id))
        cfg = dungeon_config.setdefault(key, {"enabled": False, "current_idx": 0,
            "working_idx": -1, "test_mode": False, "mode": "auto", "manual_idx": 0})
        idx = state.get("monster_idx", 0)
        mode = cfg.get("mode", "auto")
        if mode == "manual":
            dungeon_config[key] = cfg
        else:
            was_testing = state.get("test_mode", False) or cfg.get("working_idx", -1) < 0
            next_idx = idx + 1
            if next_idx >= len(DUNGEON_MONSTERS): next_idx = 0
            cfg["current_idx"] = next_idx
            if was_testing: cfg["test_mode"] = True
            dungeon_config[key] = cfg
            if was_testing:
                old_m = DUNGEON_MONSTERS[idx]; new_m = DUNGEON_MONSTERS[next_idx]
                try:
                    await _notify_user(user_id,
                        f"💀 دانجن: «{old_m}» زد منو.\n➡️ می‌رم سراغ «{new_m}»")
                except: pass
        schedule_save_runtime()
    except Exception as e: log_error(f"_on_dungeon_loss {user_id}: {_translate_bot_errors(e)}")

async def dungeon_timeout_task(user_id):
    try:
        await asyncio.sleep(DUNGEON_FLOW_TIMEOUT + 30)
        if user_id in dungeon_waiting: dungeon_waiting.pop(user_id, None)
    except asyncio.CancelledError: pass

async def run_dungeon_workflow(user_id, chat_id):
    cfg = dungeon_config.get((int(user_id), int(chat_id)))
    if not cfg or not cfg.get("enabled"): return
    client = user_clients.get(int(user_id))
    if not client or not client.is_connected():
        client = await ensure_user_client(user_id)
        if not client: return
    mode = cfg.get("mode", "auto")
    if mode == "manual": idx = cfg.get("manual_idx", 0)
    else: idx = cfg.get("current_idx", 0)
    if idx < 0 or idx >= len(DUNGEON_MONSTERS): idx = 0
    monster = DUNGEON_MONSTERS[idx]
    old = dungeon_waiting.get(user_id, {})
    old_t = old.get("timeout_task")
    if old_t and not old_t.done(): old_t.cancel()
    state = {"stage": "menu", "client": client, "chat_id": int(chat_id),
        "sent_at": time.time(), "monster_idx": idx, "monster": monster,
        "test_mode": cfg.get("test_mode", False), "mode": mode}
    state["timeout_task"] = asyncio.create_task(dungeon_timeout_task(user_id))
    dungeon_waiting[user_id] = state
    try:
        await client.send_message(chat_id, "دانجن")
    except Exception as e:
        log_error(f"run_dungeon {user_id}: {_translate_bot_errors(e)}")
        dungeon_waiting.pop(user_id, None)

async def dungeon_loop(user_id, chat_id):
    key = (int(user_id), int(chat_id))
    try:
        await asyncio.sleep(3)
        while True:
            cfg = dungeon_config.get(key, {})
            if not cfg.get("enabled"): break
            if not is_user_active(user_id) or not is_user_allowed(user_id): break
            async with get_user_lock(user_id):
                await run_dungeon_workflow(user_id, chat_id)
            for _ in range(300):
                await asyncio.sleep(1)
                if user_id not in dungeon_waiting: break
                if not dungeon_config.get(key, {}).get("enabled"): return
            waited = 0
            while waited < DUNGEON_INTERVAL:
                await asyncio.sleep(min(30, DUNGEON_INTERVAL - waited)); waited += 30
                if not dungeon_config.get(key, {}).get("enabled"): return
    except asyncio.CancelledError: pass
    except Exception as e: log_error(f"dungeon_loop {user_id}: {_translate_bot_errors(e)}")
    finally: dungeon_tasks.pop(key, None)

def start_dungeon_task(user_id, chat_id):
    key = (int(user_id), int(chat_id))
    task = dungeon_tasks.get(key)
    if task and not task.done(): return False
    dungeon_tasks[key] = asyncio.create_task(dungeon_loop(user_id, chat_id))
    return True

def stop_dungeon_task(user_id, chat_id=None):
    if chat_id is not None:
        key = (int(user_id), int(chat_id))
        task = dungeon_tasks.pop(key, None)
        if task and not task.done(): task.cancel()
        st = dungeon_waiting.pop(user_id, None)
        if st and st.get("timeout_task"):
            t = st["timeout_task"]
            if not t.done(): t.cancel()
    else:
        for k in [k for k in list(dungeon_tasks.keys()) if k[0] == int(user_id)]:
            task = dungeon_tasks.pop(k, None)
            if task and not task.done(): task.cancel()
        st = dungeon_waiting.pop(user_id, None)
        if st and st.get("timeout_task"):
            t = st["timeout_task"]
            if not t.done(): t.cancel()
            # ═══════════════════════════════════════════════════════
# Pew Art
# ═══════════════════════════════════════════════════════
def is_pew_art_enabled(user_id):
    return bool(pew_art_config.get(int(user_id), {}).get("enabled", False))

def is_pew_art_prompt(text):
    if not text: return False
    t = _normalize_persian(text).replace("ي", "ی").replace("ك", "ک")
    # The character name may vary; match the invariant announcement and its arrival verb.
    has_new_fanart = "فن آرت جدید" in t
    has_arrival_verb = re.search(
        r"(?:^|\s)(?:افتاد(?:ه)?|اومد(?:ه)?|آمد(?:ه)?|رسید(?:ه)?)(?:$|\s|[!؟?.,،؛:])", t)
    if has_new_fanart and has_arrival_verb:
        return True
    # Some bot variants announce the same claim with these extra phrases instead.
    if has_new_fanart and "کالکشنت" in t: return True
    if "اولین نفری" in t and "/art" in t: return True
    return False

def is_pew_art_group_prompt(user_id, event, text):
    return bool(
        is_pew_art_enabled(user_id)
        and getattr(event, "is_group", False)
        and not getattr(event, "out", False)
        and is_pew_art_prompt(text)
    )

def is_pew_art_win(text):
    if not text: return False
    t = _normalize_persian(text)
    if "دیر رسیدی" in t: return False
    if "قبلاً برداشت" in t or "قبلا برداشت" in t: return False
    if "یه قدم جلوتر" in t: return False
    if "رو گرفت" in t and "فن آرت" in t: return True
    if "🎉" in text and "فن آرت" in t: return True
    if "گرفت" in t and "کالکشنت" in t: return True
    return False

def is_pew_art_loss(text):
    if not text: return False
    t = _normalize_persian(text)
    if "دیر رسیدی" in t: return True
    if "قبلاً برداشت" in t or "قبلا برداشت" in t: return True
    if "یه قدم جلوتر بود" in t: return True
    return False

async def _pew_art_catch(user_id, event):
    try:
        if not is_pew_art_enabled(user_id): return
        client = user_clients.get(int(user_id))
        if not client or not client.is_connected():
            client = await ensure_user_client(user_id)
            if not client: return
        pew_art_pending[int(user_id)] = {
            "chat_id": event.chat_id, "msg_id": event.message.id, "sent_at": time.time()}
        try:
            await client.send_message(event.chat_id, "/art", reply_to=event.message.id)
            log_error(f"🎨 pew art /art sent by {user_id}")
        except FloodWaitError as e: log_error(f"pew art flood {user_id}: {e.seconds}s")
        except Exception as e: log_error(f"pew art send {user_id}: {_translate_bot_errors(e)}")
    except Exception as e:
        log_error(f"_pew_art_catch {user_id}: {_translate_bot_errors(e)}")

async def _pew_art_result(user_id, event):
    try:
        if not is_pew_art_enabled(user_id): return False
        text = event.raw_text or ""
        if is_pew_art_win(text):
            st = pew_art_stats.setdefault(int(user_id), {"grabbed": 0, "missed": 0})
            st["grabbed"] += 1
            pew_art_pending.pop(int(user_id), None)
            schedule_save_runtime()
            await _notify_user(user_id, "🎉 فن‌آرت رو گرفتی!")
            return True
        if is_pew_art_loss(text):
            st = pew_art_stats.setdefault(int(user_id), {"grabbed": 0, "missed": 0})
            st["missed"] += 1
            pew_art_pending.pop(int(user_id), None)
            schedule_save_runtime()
            await _notify_user(user_id, "🕸 دیر رسیدی — یکی دیگه برداشت.")
            return True
        return False
    except Exception as e:
        log_error(f"_pew_art_result {user_id}: {_translate_bot_errors(e)}")
        return False

# ═══════════════════════════════════════════════════════
# Pew Ring
# ═══════════════════════════════════════════════════════
PEW_RING_STAT_LABEL = {
    "skill": "مهارت", "speed": "سرعت", "power": "قدرت", "health": "سلامتی"}

def is_pew_ring_enabled(user_id, chat_id):
    return bool(pew_ring_config.get((int(user_id), int(chat_id)), {}).get("enabled", False))

def is_pew_ring_message(text):
    if not text: return False
    t = _normalize_persian(text)
    if "انرژی" not in t: return False
    if "ارتقای بعدی" not in t and "سقف انرژی" not in t: return False
    return ("رینگ" in t) or ("سقف انرژی" in t)

def parse_pew_ring_energy(text):
    t = _normalize_persian(normalize_digits(text))
    m = re.search(r'انرژی[:\s]*([\d.]+)\s*/\s*(\d+)', t)
    if m:
        try: return float(m.group(1)), int(m.group(2))
        except: pass
    return None, None

def parse_pew_ring_upgrades(text):
    t = _normalize_persian(normalize_digits(text))
    upgrades = {}
    for key in ("skill", "speed", "power", "health"):
        name = PEW_RING_STAT_LABEL[key]
        pat = rf'{re.escape(name)}.*?ارتقای\s+بعدی[^\d\u06F0-\u06F9]*([\d\u06F0-\u06F9,]+)'
        m = re.search(pat, t, re.DOTALL)
        if m:
            try:
                raw = normalize_digits(m.group(1)).replace(",", "").replace("،", "")
                upgrades[key] = float(raw)
            except: pass
    return upgrades

async def _pew_ring_get_response(user_id, chat_id, sent_msg_id, timeout=25):
    client = user_clients.get(int(user_id))
    if not client or not client.is_connected():
        client = await ensure_user_client(user_id)
        if not client: return None
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            msgs = await client.get_messages(chat_id, limit=25)
            for m in msgs:
                if not m.date: continue
                # فقط پیام‌هایی که بعد از پیام ما اومدن
                if m.id <= sent_msg_id: continue
                # اگه reply داره باید به پیام ما باشه
                if m.reply_to_msg_id and int(m.reply_to_msg_id) != int(sent_msg_id):
                    continue
                try: snd = await m.get_sender()
                except: snd = None
                if not is_pew_bot_sender(snd): continue
                t = m.raw_text or ""
                if is_pew_ring_message(t):
                    log_error(f"✅ pew_ring reply found: msg_id={m.id} after={sent_msg_id}")
                    return m
        except Exception as e:
            log_error(f"_pew_ring_get_response {user_id}: {_translate_bot_errors(e)}")
        await asyncio.sleep(2)
    return None

async def run_pew_ring_workflow(user_id, chat_id):
    key = (int(user_id), int(chat_id))
    cfg = pew_ring_config.get(key)
    if not cfg or not cfg.get("enabled"): return
    state = pew_ring_state.setdefault(key, {"last_energy": None, "last_max": None,
                                              "last_upgrades": {}, "last_ts": 0})
    for step in range(40):
        if not pew_ring_config.get(key, {}).get("enabled"): return
        if not is_user_active(user_id) or not is_user_allowed(user_id): return
        client = user_clients.get(int(user_id))
        if not client or not client.is_connected():
            client = await ensure_user_client(user_id)
            if not client: return
        try:
            sent_obj = await client.send_message(chat_id, "پیو رینگ")
            sent_msg_id = sent_obj.id
        except Exception as e:
            log_error(f"pew_ring send {user_id}: {_translate_bot_errors(e)}"); return
        msg = await _pew_ring_get_response(user_id, chat_id, sent_msg_id, timeout=20)
        if not msg:
            log_error(f"pew ring no reply {user_id}"); return
        text = msg.raw_text or ""
        energy, max_energy = parse_pew_ring_energy(text)
        upgrades = parse_pew_ring_upgrades(text)
        state["last_energy"] = energy
        state["last_max"] = max_energy
        state["last_upgrades"] = upgrades
        state["last_ts"] = time.time()
        pew_ring_state[key] = state
        schedule_save_runtime()
        log_error(f"🏋️ pew ring check: user={user_id} chat={chat_id} "
                  f"energy={energy} max={max_energy} upgrades={upgrades}")
        if energy is None or not upgrades:
            log_error(f"⚠️ pew ring parse failed: energy={energy} ups={upgrades}")
            return
        affordable = [(k, v) for k, v in upgrades.items() if v <= energy]
        if not affordable:
            min_cost = min(upgrades.values())
            log_error(f"⏸ pew ring wait: energy={energy} < min_cost={min_cost}")
            return
        min_cost = min(v for _, v in affordable)
        cheapest = [(k, v) for k, v in affordable if v == min_cost]
        stat_key, cost = random.choice(cheapest)
        label = PEW_RING_STAT_LABEL[stat_key]
        log_error(f"⬆️ ارتقا: {label} (cost={min_cost}, energy={energy})")
        try:
            await client.send_message(chat_id, f"پیو رینگ {label}")
        except FloodWaitError as e:
            log_error(f"upgrade flood: {e.seconds}s")
            await asyncio.sleep(e.seconds)
            continue
        except Exception as e:
            log_error(f"upgrade send fail: {_translate_bot_errors(e)}")
            return
        await asyncio.sleep(6)

async def pew_ring_loop(user_id, chat_id):
    key = (int(user_id), int(chat_id))
    log_error(f"🚀 loop STARTED: {user_id}")
    try:
        await asyncio.sleep(3)
        while True:
            cfg = pew_ring_config.get(key, {})
            if not cfg.get("enabled"):
                log_error(f"⏹ disabled: {user_id}")
                break
            if not is_user_active(user_id) or not is_user_allowed(user_id):
                log_error(f"⏹ inactive: {user_id}")
                break

            cl = user_clients.get(int(user_id))
            if not cl or not cl.is_connected():
                cl = await ensure_user_client(user_id)
            if not cl:
                await asyncio.sleep(60); continue

            # ۱) پیام پیو رینگ بفرست
            try:
                sent = await cl.send_message(chat_id, "پیو رینگ")
                log_error(f"📤 sent ring: id={sent.id}")
            except Exception as e:
                log_error(f"send fail: {_translate_bot_errors(e)}")
                await asyncio.sleep(60); continue

            # ۲) ۵ ثانیه صبر، بعد پیام‌های اخیر رو بخون
            await asyncio.sleep(6)
            resp = None
            try:
                msgs = await cl.get_messages(chat_id, limit=10)
                for m in msgs:
                    if m.id <= sent.id: continue
                    try: snd = await m.get_sender()
                    except: snd = None
                    if not is_pew_bot_sender(snd): continue
                    t = m.raw_text or ""
                    if "انرژی" in t and ("رینگ" in t or "مهارت" in t or "سرعت" in t):
                        resp = t
                        log_error(f"📥 got ring msg: {t[:80]}")
                        break
            except Exception as e:
                log_error(f"read fail: {_translate_bot_errors(e)}")

            if not resp:
                log_error(f"⚠️ no ring reply: {user_id}")
                waited = 0
                while waited < 3600:
                    await asyncio.sleep(min(30, 3600-waited)); waited += 30
                    if not pew_ring_config.get(key, {}).get("enabled"): return
                continue

            # ۳) parse
            energy, _ = parse_pew_ring_energy(resp)
            upgrades = parse_pew_ring_upgrades(resp)
            log_error(f"🔍 energy={energy} ups={upgrades}")

            if energy is None or not upgrades:
                log_error("⚠️ parse fail")
                waited = 0
                while waited < 3600:
                    await asyncio.sleep(min(30, 3600-waited)); waited += 30
                    if not pew_ring_config.get(key, {}).get("enabled"): return
                continue

            # ۴) کدوم ممکنه؟
            affordable = {k: v for k, v in upgrades.items() if v <= energy}
            if not affordable:
                log_error(f"⏸ no affordable (energy={energy})")
                waited = 0
                while waited < 3600:
                    await asyncio.sleep(min(30, 3600-waited)); waited += 30
                    if not pew_ring_config.get(key, {}).get("enabled"): return
                continue

            # ۵) ارتقا بده
            min_cost = min(affordable.values())
            cheapest = [k for k, v in affordable.items() if v == min_cost]
            stat_key = random.choice(cheapest)
            label = PEW_RING_STAT_LABEL[stat_key]
            log_error(f"⬆️ upgrade: {label} ({min_cost})")
            try:
                await cl.send_message(chat_id, f"پیو رینگ {label}")
                await asyncio.sleep(6)
            except Exception as e:
                log_error(f"upgrade fail: {_translate_bot_errors(e)}")

            # ۶) فوری برگرد بالا، دوباره پیو رینگ
            log_error("🔁 loop again")
    except asyncio.CancelledError: pass
    except Exception as e:
        log_error(f"pew_ring_loop {user_id}: {_translate_bot_errors(e)}")
    finally:
        log_error(f"⏹ loop stopped: {user_id}")
        pew_ring_tasks.pop(key, None)

def start_pew_ring_task(user_id, chat_id):
    key = (int(user_id), int(chat_id))
    t = pew_ring_tasks.get(key)
    if t and not t.done(): return False
    pew_ring_tasks[key] = asyncio.create_task(pew_ring_loop(user_id, chat_id))
    return True

def stop_pew_ring_task(user_id, chat_id=None):
    if chat_id is not None:
        key = (int(user_id), int(chat_id))
        t = pew_ring_tasks.pop(key, None)
        if t and not t.done(): t.cancel()
    else:
        for k in [k for k in list(pew_ring_tasks.keys()) if k[0] == int(user_id)]:
            t = pew_ring_tasks.pop(k, None)
            if t and not t.done(): t.cancel()

def stop_all_pew_ring_for_user(user_id):
    stop_pew_ring_task(user_id)
    uid = int(user_id)
    for k in [k for k in list(pew_ring_config.keys()) if k[0] == uid]:
        del pew_ring_config[k]
    for k in [k for k in list(pew_ring_state.keys()) if k[0] == uid]:
        del pew_ring_state[k]
    schedule_save_runtime()

# ═══════════════════════════════════════════════════════
# Pew Target
# ═══════════════════════════════════════════════════════
def _pew_target_key(uid, chat_id, target_id):
    return (int(uid), int(chat_id), int(target_id))

def is_pew_target_death(text):
    if not text: return False
    t = _normalize_persian(text)
    if "RIP" in t: return True
    if "مرده می‌مونه" in t or "مرده میمونه" in t: return True
    if "دقیقه دیگه مرده" in t: return True
    if "سلامتی کامل زنده می‌شه" in t: return True
    if "سلامتی کامل زنده میشه" in t: return True
    if "کشته شد" in t and "دقیقه" in t: return True
    return False

def is_pew_target_cooldown(text):
    if not text: return False
    t = _normalize_persian(text)
    if "تازه شلیک کردی" in t: return True
    if "استان" in t and "cooldown" in t.lower(): return True
    if "استان" in t and "شلیک" in t: return True
    if "cooldown" in t.lower() and "شلیک" in t: return True
    if "ثانیه دیگه صبر کن" in t: return True
    if "ثانیه بیشتره" in t: return True
    return False

def parse_pew_target_cooldown(text):
    if not text: return None
    t = _normalize_persian(normalize_digits(text))
    m = re.search(r'(\d+)\s*ثانیه\s*دیگه\s*صبر', t)
    if m:
        try: return int(m.group(1))
        except: pass
    m = re.search(r'cooldown[^\d]*(\d+)\s*ثانیه', t)
    if m:
        try: return int(m.group(1))
        except: pass
    m = re.search(r'(\d+)\s*ثانیه', t)
    if m:
        try: return int(m.group(1))
        except: pass
    return None

def is_pew_target_shot_success(text):
    if not text: return False
    t = _normalize_persian(text)
    if "شلیک کرد و" in t and "دمیج زد" in t: return True
    if "شلیک کرد" in t and "دمیج" in t: return True
    return False

def is_pew_target_bleed(text):
    if not text: return False
    t = _normalize_persian(text)
    return "خونریزی" in t

async def _resolve_pew_target(client, event):
    def _build_info(ent):
        first = (getattr(ent, 'first_name', '') or '').strip()
        last  = (getattr(ent, 'last_name', '') or '').strip()
        uname = (getattr(ent, 'username', '') or '').strip()
        full  = (first + " " + last).strip()
        return {
            "id": int(getattr(ent, 'id')),
            "first_name": first,
            "last_name": last,
            "username": uname,
            "display": full or (("@" + uname) if uname else str(getattr(ent, 'id')))
        }
    try:
        replied = await event.get_reply_message()
        if replied and replied.sender_id and int(replied.sender_id) != event.sender_id:
            tid = int(replied.sender_id)
            try:
                ent = await client.get_entity(tid)
                info = _build_info(ent)
                log_error(f"✅ resolve reply: {info}")
                return info
            except Exception as e:
                log_error(f"resolve reply entity fail: {_translate_bot_errors(e)}")
                return {"id": tid, "first_name": "", "last_name": "",
                        "username": "", "display": str(tid)}
    except Exception as e:
        log_error(f"get_reply fail: {_translate_bot_errors(e)}")
    txt = (event.raw_text or "").strip()
    if not txt: return None
    txt = txt.lstrip("،., ").strip()
    log_error(f"🔍 resolve input: '{txt}'")
    if txt.startswith("@"):
        uname = txt[1:].strip()
        if not uname: return None
        try:
            res = await client(ResolveUsernameRequest(uname))
            if res and res.users:
                u = res.users[0]
                if getattr(u, 'bot', False): return None
                info = _build_info(u)
                log_error(f"✅ resolve ResolveUsername: {info}")
                return info
            if res and res.chats: return None
        except Exception as e:
            log_error(f"ResolveUsername fail: {type(e).__name__}: {_translate_bot_errors(e)}")
        try:
            ent = await client.get_entity("@" + uname)
            if getattr(ent, 'bot', False): return None
            info = _build_info(ent)
            return info
        except Exception as e:
            log_error(f"get_entity fail: {type(e).__name__}: {_translate_bot_errors(e)}")
        try:
            peer = await client.get_input_entity("@" + uname)
            uid = None
            if hasattr(peer, "user_id"): uid = int(peer.user_id)
            if uid:
                return {"id": uid, "first_name": "", "last_name": "",
                        "username": uname, "display": "@" + uname}
        except: pass
        return None
    norm = normalize_digits(txt)
    if norm.lstrip("-").isdigit():
        tid = int(norm)
        try:
            ent = await client.get_entity(tid)
            if getattr(ent, 'bot', False): return None
            info = _build_info(ent)
            return info
        except Exception as e:
            log_error(f"id entity fail: {_translate_bot_errors(e)}")
            return None
    return None

async def _pew_target_on_target_msg(uid, chat_id, target_id, event):
    key = _pew_target_key(uid, chat_id, target_id)
    if key not in pew_target_config: return
    if not pew_target_config[key].get("enabled"): return
    state = pew_target_state.setdefault(key, {"phase": "shooting", "last_target_msg_id": 0})
    state["last_target_msg_id"] = event.message.id
    pew_target_state[key] = state
    t = pew_target_tasks.get(key)
    if not t or t.done():
        start_pew_target_task(uid, chat_id, target_id)

async def _handle_pew_target_death(uid, chat_id, target_id, text):
    key = _pew_target_key(uid, chat_id, target_id)
    if key not in pew_target_config: return
    if not pew_target_config[key].get("enabled"): return
    state = pew_target_state.setdefault(key, {"phase": "shooting"})
    if state.get("phase") == "dead_wait": return
    state["phase"] = "dead_wait"
    state["death_ts"] = time.time()
    pew_target_state[key] = state
    schedule_save_runtime()
    name = pew_target_config[key].get("name", str(target_id))
    log_error(f"💀 pew target died: {key}")
    try:
        await _notify_user(uid,
            f"💀 هدف کشته شد: {name}\n⏳ ۱۱ دقیقه صبر، بعد دوباره شلیک می‌کنم.")
    except: pass

async def pew_target_shoot_loop(uid, chat_id, target_id):
    key = _pew_target_key(uid, chat_id, target_id)
    try:
        while True:
            cfg = pew_target_config.get(key)
            if not cfg or not cfg.get("enabled"): break
            if not is_user_active(uid) or not is_user_allowed(uid): break
            state = pew_target_state.setdefault(key, {"phase": "shooting", "last_target_msg_id": 0})
            if state.get("phase") == "dead_wait":
                left = PEW_TARGET_DEATH_WAIT - (time.time() - state.get("death_ts", 0))
                if left > 0:
                    await asyncio.sleep(min(30, left))
                    if not pew_target_config.get(key, {}).get("enabled"): return
                    continue
                state["phase"] = "shooting"
                pew_target_state[key] = state
                schedule_save_runtime()
                log_error(f"🎯 pew target resume after death: {key}")
            last_msg_id = state.get("last_target_msg_id", 0)
            if not last_msg_id:
                await asyncio.sleep(5); continue
            client = user_clients.get(int(uid))
            if not client or not client.is_connected():
                client = await ensure_user_client(uid)
                if not client:
                    await asyncio.sleep(15); continue
            send_ts = time.time()
            try:
                await client.send_message(chat_id, PEW_TARGET_SHOOT_CMD, reply_to=last_msg_id)
                state["last_shoot_ts"] = time.time()
                pew_target_state[key] = state
                log_error(f"🎯 pew target shot → {chat_id} target={target_id}")
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds); continue
            except Exception as e:
                log_error(f"pew target shoot {key}: {_translate_bot_errors(e)}")
                await asyncio.sleep(PEW_TARGET_SHOOT_INTERVAL); continue
            wait_extra = 0
            try:
                await asyncio.sleep(4)
                msgs = await client.get_messages(chat_id, limit=8)
                for m in msgs:
                    if not m.date: continue
                    try: mt = m.date.timestamp()
                    except: continue
                    if mt < send_ts - 2: continue
                    try: snd = await m.get_sender()
                    except: snd = None
                    if not is_pew_bot_sender(snd): continue
                    txt = m.raw_text or ""
                    if is_pew_target_shot_success(txt):
                        log_error(f"✅ pew target shot success: {key}")
                    if is_pew_target_bleed(txt):
                        log_error(f"🩸 pew target bleed: {key}")
                    if is_pew_target_cooldown(txt):
                        cd = parse_pew_target_cooldown(txt)
                        if cd and cd > 0:
                            wait_extra = cd + 2
                            log_error(f"⏸ pew target cooldown {cd}s for {key}")
                    if is_pew_target_death(txt):
                        log_error(f"💀 pew target death (from loop): {key}")
                        state["phase"] = "dead_wait"
                        state["death_ts"] = time.time()
                        pew_target_state[key] = state
                        schedule_save_runtime()
                        break
            except Exception as e:
                log_error(f"pew target read: {_translate_bot_errors(e)}")
            if pew_target_state.get(key, {}).get("phase") == "dead_wait":
                continue
            wait_total = max(PEW_TARGET_SHOOT_INTERVAL, wait_extra)
            waited = 0
            while waited < wait_total:
                await asyncio.sleep(min(3, wait_total - waited))
                waited += 3
                if not pew_target_config.get(key, {}).get("enabled"): return
                if pew_target_state.get(key, {}).get("phase") == "dead_wait": break
    except asyncio.CancelledError: pass
    except Exception as e: log_error(f"pew_target_shoot_loop {key}: {_translate_bot_errors(e)}")
    finally: pew_target_tasks.pop(key, None)

def start_pew_target_task(uid, chat_id, target_id):
    key = _pew_target_key(uid, chat_id, target_id)
    t = pew_target_tasks.get(key)
    if t and not t.done(): return False
    pew_target_tasks[key] = asyncio.create_task(pew_target_shoot_loop(uid, chat_id, target_id))
    return True

def stop_pew_target_task(uid, chat_id=None, target_id=None):
    if chat_id is not None and target_id is not None:
        key = _pew_target_key(uid, chat_id, target_id)
        t = pew_target_tasks.pop(key, None)
        if t and not t.done(): t.cancel()
    else:
        uid = int(uid)
        for k in [k for k in list(pew_target_tasks.keys()) if k[0] == uid]:
            t = pew_target_tasks.pop(k, None)
            if t and not t.done(): t.cancel()

def stop_all_pew_target_for_user(uid):
    stop_pew_target_task(uid)
    uid = int(uid)
    for k in [k for k in list(pew_target_config.keys()) if k[0] == uid]:
        del pew_target_config[k]
    for k in [k for k in list(pew_target_state.keys()) if k[0] == uid]:
        del pew_target_state[k]
    schedule_save_runtime()

# ═══════════════════════════════════════════════════════
# Pew Dog
# ═══════════════════════════════════════════════════════
def is_pew_dog_msg(text):
    if not text: return False
    t = _normalize_persian(text)
    if "غذا بعدی" in t: return True
    if "هنوز سیره" in t: return True
    if "پوست:" in t and "قدرت:" in t: return True
    if "/dog feed" in text: return True
    return False

def parse_pew_dog_next_feed(text):
    if not text: return None
    t = _normalize_persian(normalize_digits(text))
    m = re.search(r'(\d+)\s*دقیقه\s*(?:دیگه|دیگر)?\s*صبر', t)
    if m:
        try: return int(m.group(1))
        except: pass
    m = re.search(r'غذا\s+بعدی[:\s]*(\d+)\s*دقیقه', t)
    if m:
        try: return int(m.group(1))
        except: pass
    m = re.search(r'(\d+)\s*دقیقه', t)
    if m:
        try: return int(m.group(1))
        except: pass
    return None

def is_pew_dog_feed_success(text):
    if not text: return False
    t = _normalize_persian(text)
    if "با اشتهای کامل" in t: return True
    if "اشتهای کامل غذا" in t: return True
    if "کامل غذا رو خورد" in t: return True
    return False

async def _pew_dog_get_response(user_id, chat_id, sent_msg_id, timeout=20):
    client = user_clients.get(int(user_id))
    if not client or not client.is_connected():
        client = await ensure_user_client(user_id)
        if not client: return None
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            msgs = await client.get_messages(chat_id, limit=15)
            for m in msgs:
                if not m.date: continue
                if not m.reply_to_msg_id or int(m.reply_to_msg_id) != int(sent_msg_id):
                    continue
                try: snd = await m.get_sender()
                except: snd = None
                if not is_pew_bot_sender(snd): continue
                if is_pew_dog_msg(m.raw_text or ""): return m
        except Exception as e:
            log_error(f"_pew_dog_get_response {user_id}: {_translate_bot_errors(e)}")
        await asyncio.sleep(2)
    return None

async def run_pew_dog_workflow(uid, chat_id):
    key = (int(uid), int(chat_id))
    cfg = pew_dog_config.get(key)
    if not cfg or not cfg.get("enabled"): return
    client = user_clients.get(int(uid))
    if not client or not client.is_connected():
        client = await ensure_user_client(uid)
        if not client: return
    try:
        sent_obj = await client.send_message(chat_id, "/dog feed")
        sent_msg_id = sent_obj.id
    except Exception as e:
        log_error(f"pew dog feed {uid}: {_translate_bot_errors(e)}"); return
    msg = await _pew_dog_get_response(uid, chat_id, sent_msg_id, timeout=20)
    state = pew_dog_state.setdefault(key, {})
    if not msg:
        state["next_feed_min"] = 30
        state["last_status"] = "no_reply"
        state["last_ts"] = time.time()
        pew_dog_state[key] = state
        schedule_save_runtime()
        return
    txt = msg.raw_text or ""
    next_min = parse_pew_dog_next_feed(txt)
    if next_min:
        state["next_feed_min"] = next_min
        state["last_status"] = "hungry"
        log_error(f"🐕 dog hungry {next_min}min")
    elif is_pew_dog_feed_success(txt):
        state["next_feed_min"] = 25
        state["last_status"] = "fed"
        log_error("🐕 dog fed ✓ → next 25min")
    else:
        state["next_feed_min"] = 30
        state["last_status"] = "unknown"
        log_error(f"🐕 dog unknown: {txt[:80]}")
    state["last_ts"] = time.time()
    pew_dog_state[key] = state
    schedule_save_runtime()

async def pew_dog_loop(uid, chat_id):
    key = (int(uid), int(chat_id))
    try:
        while True:
            cfg = pew_dog_config.get(key, {})
            if not cfg.get("enabled"): break
            if not is_user_active(uid) or not is_user_allowed(uid): break
            async with get_user_lock(uid):
                await run_pew_dog_workflow(uid, chat_id)
            wait_min = pew_dog_state.get(key, {}).get("next_feed_min", 30)
            wait_sec = max(60, wait_min * 60 + 60)
            waited = 0
            while waited < wait_sec:
                await asyncio.sleep(min(60, wait_sec - waited)); waited += 60
                if not pew_dog_config.get(key, {}).get("enabled"): return
    except asyncio.CancelledError: pass
    except Exception as e: log_error(f"pew_dog_loop {uid}: {_translate_bot_errors(e)}")
    finally: pew_dog_tasks.pop(key, None)

def start_pew_dog_task(uid, chat_id):
    key = (int(uid), int(chat_id))
    t = pew_dog_tasks.get(key)
    if t and not t.done(): return False
    pew_dog_tasks[key] = asyncio.create_task(pew_dog_loop(uid, chat_id))
    return True

def stop_pew_dog_task(uid, chat_id=None):
    if chat_id is not None:
        key = (int(uid), int(chat_id))
        t = pew_dog_tasks.pop(key, None)
        if t and not t.done(): t.cancel()
    else:
        for k in [k for k in list(pew_dog_tasks.keys()) if k[0] == int(uid)]:
            t = pew_dog_tasks.pop(k, None)
            if t and not t.done(): t.cancel()

def stop_all_pew_dog_for_user(uid):
    stop_pew_dog_task(uid)
    uid = int(uid)
    for k in [k for k in list(pew_dog_config.keys()) if k[0] == uid]:
        del pew_dog_config[k]
    for k in [k for k in list(pew_dog_state.keys()) if k[0] == uid]:
        del pew_dog_state[k]
    schedule_save_runtime()

# ═══════════════════════════════════════════════════════
# Pew Master
# ═══════════════════════════════════════════════════════
def get_pew_master(uid):
    return pew_master.setdefault(int(uid), {"ring": False, "target": False, "dog": False})

def set_pew_master(uid, key, on):
    m = get_pew_master(uid); m[key] = bool(on)
    schedule_save_runtime()
    # ═══════════════════════════════════════════════════════
# فروش
# ═══════════════════════════════════════════════════════
def _notification_is_on(user_id, key):
    notifs = users_db["users"].get(str(user_id), {}).get("notifications", {})
    return bool(notifs.get(key, True))


async def _notify_feature(user_id, key, msg):
    if _notification_is_on(user_id, key):
        await _notify_user(user_id, msg)


async def _notify_sell(user_id, msg):
    await _notify_feature(user_id, "sell", msg)


def _transfer_item_key(name):
    text = normalize_digits(_normalize_persian(str(name or "")))
    text = text.replace("ي", "ی").replace("ك", "ک")
    return re.sub(r"[\s\u200c\u200e\u200f]+", "", text).lower()


def _inventory_quantity_map(items):
    quantities = {}
    for item in items or []:
        key = _transfer_item_key(item.get("name", ""))
        if key:
            quantities[key] = quantities.get(key, 0) + max(0, int(item.get("qty", 0) or 0))
    return quantities


def _planned_transfer_amounts(user_id, category, inventory_items):
    cfg = (transfer_materials_config if category == "mat_trans" else transfer_items_config).get(user_id, {})
    if not cfg.get("enabled"):
        return {}, {}
    stock = _inventory_quantity_map(inventory_items)
    grouped = {}
    labels = {}
    for rule in cfg.get("rules", []):
        if not rule.get("enabled", True):
            continue
        name = str(rule.get("material", "")).strip()
        key = _transfer_item_key(name)
        if not key:
            continue
        grouped.setdefault(key, []).append(rule)
        labels.setdefault(key, name)
    planned = {}
    turn_state = cfg.get("turn_state", {})
    for key, rules in grouped.items():
        available = stock.get(key, 0)
        if available <= 0:
            continue
        start = int(turn_state.get(key, 0) or 0) % len(rules)
        ordered = rules[start:] + rules[:start]
        requested_total = 0
        for index, rule in enumerate(ordered):
            if available <= 0:
                break
            try: requested = int(rule.get("quantity", 0) or 0)
            except (TypeError, ValueError): requested = 0
            remaining_rules = len(ordered) - index
            amount = max(1, available // remaining_rules) if requested == 0 else min(requested, available)
            amount = max(0, amount)
            requested_total += amount
            available -= amount
        if requested_total:
            planned[key] = requested_total
    return planned, labels


async def _refresh_sell_inventory(user_id):
    await _drain_sell_queue(user_id, "sell")
    await asyncio.sleep(0.3)
    return await _sell_send_and_wait(user_id, "🎒 موجودی من", 30,
                                     is_inventory_message, "sell")


async def _pre_sale_transfer_category(user_id, category, inventory_items):
    """Run one configured transfer class and return fresh stock plus failed names."""
    planned, labels = _planned_transfer_amounts(user_id, category, inventory_items)
    if not planned:
        return inventory_items, set()
    executor = execute_material_transfers if category == "mat_trans" else execute_item_transfers
    try:
        await executor(user_id)
    except Exception as e:
        log_error(f"pre-sale {category} {user_id}: {_translate_bot_errors(e)}")
    refreshed = await _refresh_sell_inventory(user_id)
    failed = set()
    before = _inventory_quantity_map(inventory_items)
    if refreshed:
        after_items = parse_inventory_items(refreshed if isinstance(refreshed, str)
                                            else (refreshed.raw_text or ""))
        after = _inventory_quantity_map(after_items)
        for key, requested in planned.items():
            moved = max(0, before.get(key, 0) - after.get(key, 0))
            if moved < requested:
                failed.add(key)
                label = labels.get(key, key)
                await _notify_feature(
                    user_id, category,
                    f"⚠️ انتقال {label} کامل نشد ({moved}/{requested}).\n"
                    "برای جلوگیری از فروش اشتباهی، باقی‌ماندهٔ این مورد در این چرخه فروخته نمی‌شود.")
        return after_items, failed
    for key, requested in planned.items():
        failed.add(key)
        label = labels.get(key, key)
        await _notify_feature(
            user_id, category,
            f"⚠️ نتیجهٔ انتقال {label} قابل بررسی نبود (موجودی تازه دریافت نشد).\n"
            "برای ایمنی، این مورد در این چرخه فروخته نمی‌شود.")
    return inventory_items, failed


async def run_sell_workflow(user_id):
    if user_id not in sell_mode_users or not sell_mode_users[user_id].get("enabled"): return
    client = user_clients.get(int(user_id))
    if not client or not client.is_connected():
        client = await ensure_user_client(user_id)
        if not client: return

    # ─── 1. گرفتن موجودی ───
    await _drain_sell_queue(user_id, "sell"); await asyncio.sleep(0.5)
    log_error(f"🛒 SELL: درخواست موجودی برای {user_id}")
    inv_resp = await _sell_send_and_wait(user_id, "🎒 موجودی من", 30, is_inventory_message, "sell")
    if not inv_resp:
        log_error(f"❌ SELL: تایم‌اوت در دریافت موجودی برای {user_id}")
        await _notify_sell(user_id, "⚠️ بازی به دستور موجودی جواب نداد. دوباره تلاش می‌کنم...")
        return
    log_error(f"✅ SELL: موجودی دریافت شد برای {user_id}")
    
    inv_text = inv_resp if isinstance(inv_resp, str) else (inv_resp.raw_text or "")
    inv_items = parse_inventory_items(inv_text)
    no_sell = get_no_sell_list(user_id)

    # Transfer configured inventory before entering the shop. Verify each class
    # from the fresh inventory; if a requested transfer did not happen, protect
    # that item from sale for this cycle and tell the user in private.
    transfer_failed_names = set()
    for transfer_key in ("mat_trans", "item_trans"):
        cfg = (transfer_materials_config if transfer_key == "mat_trans"
               else transfer_items_config).get(user_id, {})
        if cfg.get("enabled") and any(r.get("enabled", True) for r in cfg.get("rules", [])):
            inv_items, failed_names = await _pre_sale_transfer_category(
                user_id, transfer_key, inv_items)
            transfer_failed_names.update(failed_names)

    protected_transfer_names = [
        str(rule.get("material", "")).strip()
        for cfg in (transfer_materials_config.get(user_id, {}),
                    transfer_items_config.get(user_id, {}))
        if cfg.get("enabled")
        for rule in cfg.get("rules", [])
        if rule.get("enabled", True)
        and _transfer_item_key(rule.get("material", "")) in transfer_failed_names
    ]
    sale_exclusions = list(no_sell) + protected_transfer_names
    items_to_sell = [it for it in inv_items
                     if not item_matches_no_sell(it["name"], sale_exclusions)]
    if not items_to_sell:
        log_error(f"sell: nothing to sell for {user_id}")
        await _notify_sell(user_id, "ℹ️ آیتمی برای فروش نبود.")
        return

    # ─── 2. گرفتن اطلاعات موقعیت ───
    await _drain_sell_queue(user_id, "sell"); await asyncio.sleep(0.5)
    info_resp = await _sell_send_and_wait(user_id, "🪶 اطلاعات من", 30, is_profile_message, "sell")
    
    was_outside = False
    if info_resp:
        info_text = info_resp if isinstance(info_resp, str) else (info_resp.raw_text or "")
        _, _, location = parse_profile_info(info_text)
        was_outside = not is_user_inside_city(location)

    # ─── 3. اگه بیرون بود، برگرد به شهر ───
    if was_outside:
        await _notify_sell(user_id, "🏰 برمی‌گردم شهر...")
        await _drain_sell_queue(user_id, "sell"); await asyncio.sleep(0.5)
        city_resp = await _sell_send_and_wait(user_id, "🏰 بازگشت به شهر", 45,
            lambda t: is_city_arrival_message(t) or is_distance_error_message(t), "sell")
        if city_resp and is_distance_error_message(city_resp):
            await asyncio.sleep(1)
            crystal_resp = await _sell_send_and_wait(user_id,
                "💎 استفاده از کریستال تلپورت اجباری", 45, is_crystal_success_message, "sell")
            if not crystal_resp:
                await _notify_sell(user_id, "❌ کریستال کمه، فروش لغو شد.")
                return
        await asyncio.sleep(1.5)

    # ─── 4. رفتن به فروشگاه ───
    await _drain_sell_queue(user_id, "sell"); await asyncio.sleep(0.5)
    await _send_game_cmd(user_id, "⚖️ فروشگاه شهر", tag="sell")
    shop_resp = await _wait_for_sell_message(user_id, 20, is_sell_list_message, "sell")
    
    total_sold = 0
    if shop_resp:
        shop_text = shop_resp if isinstance(shop_resp, str) else (shop_resp.raw_text or "")
        shop_items = parse_sell_list(shop_text)
        
        for item in shop_items:
            name = item["name"]
            qty = item["qty"]
            cmd = item["cmd"]
            
            if item_matches_no_sell(name, sale_exclusions):
                continue
            
            full_cmd = f"{cmd}_{qty}" if qty > 1 else cmd
            await _send_game_cmd(user_id, full_cmd, tag="sell")
            log_error(f"💸 sell cmd: {full_cmd} for {user_id}")
            total_sold += qty
            await asyncio.sleep(3)

    # ─── 5. چک نهایی موجودی (طبق خواسته تو) ───
    await _drain_sell_queue(user_id, "sell"); await asyncio.sleep(0.5)
    await _sell_send_and_wait(user_id, "🎒 موجودی من", 30, is_inventory_message, "sell")

    # ─── 6. خروج یا برگشت ───
    if was_outside:
        try: await _send_game_cmd(user_id, "🏰 خروج از شهر!", tag="sell")
        except: pass
    else:
        try: await _send_game_cmd(user_id, "🔙 برگشت به منو", tag="sell")
        except: pass

    if total_sold > 0:
        await _notify_sell(user_id, f"✅ {total_sold} آیتم فروخته شد.")
    else:
        await _notify_sell(user_id, "ℹ️ آیتمی فروخته نشد.")


async def sell_scheduler(user_id):
    try:
        async with get_user_lock(user_id):
            await run_sell_workflow(user_id)
        while True:
            await asyncio.sleep(SELL_CHECK_INTERVAL)
            if not sell_mode_users.get(user_id, {}).get("enabled"): break
            try:
                async with get_user_lock(user_id):
                    await run_sell_workflow(user_id)
            except Exception as e: log_error(f"sell_sched {user_id}: {_translate_bot_errors(e)}")
    except asyncio.CancelledError: pass
    except Exception as e: log_error(f"sell_scheduler {user_id}: {_translate_bot_errors(e)}")

def stop_sell_mode(user_id):
    data = sell_mode_users.pop(user_id, None)
    if data:
        t = data.get("scheduler_task")
        if t and not t.done(): t.cancel()
    for feat in ("sell", "escape", "return", "gift", "battle", "pewring"):
        if (user_id, feat) in sell_queues:
            del sell_queues[(user_id, feat)]
    schedule_save_runtime()

# ═══════════════════════════════════════════════════════
# فرار
# ═══════════════════════════════════════════════════════
async def run_escape_workflow(user_id, reason="🕵️ قاتل ناشناس جاسوسیت کرد"):
    if not is_escape_enabled(user_id): return
    client = user_clients.get(int(user_id))
    if not client or not client.is_connected():
        client = await ensure_user_client(user_id)
        if not client: return
    await _drain_sell_queue(user_id, "escape"); await asyncio.sleep(0.3)
    info_resp = await _sell_send_and_wait(user_id, "🪶 اطلاعات من", 45, is_profile_message, "escape")
    if not info_resp:
        await _notify_escape(user_id, f"⚠️ فرار\n{reason}.\n❌ اطلاعات نیامد."); return
    current_floor, max_floor, location = parse_profile_info(info_resp)
    inside_city = is_user_inside_city(location)
    if not inside_city:
        await _notify_escape(user_id, "🏰 برمی‌گردم شهر...")
        await _drain_sell_queue(user_id, "escape"); await asyncio.sleep(0.3)
        city_resp = await _sell_send_and_wait(user_id, "🏰 بازگشت به شهر", 45,
            lambda t: is_city_arrival_message(t) or is_distance_error_message(t), "escape")
        if city_resp and is_distance_error_message(city_resp):
            await asyncio.sleep(1)
            crystal_resp = await _sell_send_and_wait(user_id,
                "💎 استفاده از کریستال تلپورت اجباری", 45, is_crystal_success_message, "escape")
            if not crystal_resp:
                await _notify_escape(user_id, f"⚠️ فرار\n{reason}.\n❌ نتونستم برگردم."); return
        await asyncio.sleep(1.5)
    await _drain_sell_queue(user_id, "escape")
    tp_resp = await _sell_send_and_wait(user_id, "🌀 تلپورت به طبقات", 45, is_teleport_prompt, "escape")
    if not tp_resp:
        await _notify_escape(user_id, f"⚠️ فرار\n{reason}.\n❌ تلپورت نیامد."); return
    end = max_floor if max_floor > 0 else 100
    if end > 5:
        candidates = []
        for n in range(1, end + 1):
            if n == current_floor: continue
            if is_floor_banned_for_hunt(user_id, n): continue
            candidates.append(n)
        if not candidates:
            candidates = [n for n in range(1, end + 1) if n != current_floor]
        if not candidates:
            await _notify_escape(user_id, "❌ طبقه‌ای نیست."); return
        target = random.choice(candidates)
    else: target = 1
    await asyncio.sleep(0.7); await _drain_sell_queue(user_id, "escape"); await asyncio.sleep(0.3)
    result_resp = await _sell_send_and_wait(user_id, str(target), 45,
        lambda t: is_teleport_success(t) or is_teleport_fail_no_money(t), "escape")
    if not result_resp:
        await _notify_escape(user_id, "⚠️ فرار\nجواب تلپورت نیامد."); return
    if is_teleport_fail_no_money(result_resp):
        await _notify_escape(user_id, f"⚠️ فرار\n{reason}.\n❌ پول نیست."); return
    if is_teleport_success(result_resp):
        new_floor = parse_teleport_result_floor(result_resp) or target
        await asyncio.sleep(1.2)
        try: await _send_game_cmd(user_id, "🏰 خروج از شهر!", tag="escape")
        except: pass
        await _notify_escape(user_id,
            f"✅ فرار موفق\n{reason}.\n🏰 {current_floor} → 🌀 {new_floor}\n🚪 بیرون شهر")

async def run_escape_workflow_wrapper(user_id, reason="🕵️ قاتل ناشناس جاسوسیت کرد"):
    try:
        async with get_user_lock(user_id):
            await run_escape_workflow(user_id, reason)
    except Exception as e: log_error(f"escape_wrap {user_id}: {_translate_bot_errors(e)}")

# ═══════════════════════════════════════════════════════
# برگشت
# ═══════════════════════════════════════════════════════

async def _force_floor_update(uid):
    client = user_clients.get(int(uid))
    if not client or not client.is_connected():
        client = await ensure_user_client(uid)
    if client:
        await _send_game_cmd(uid, "🪶 اطلاعات من", tag="check_floor")

async def _pm_build_return_panel(uid):
    ret_on = is_return_enabled(uid)
    status = "🟢 روشن" if ret_on else "🔴 خاموش"
    rtype = return_config.get(uid, {}).get("type", "scatter")
    type_label = "📍 برگشت به همون طبقه" if rtype == "same" else "🎲 برگشت پراکنده"
    current_floor_memory = user_current_floor.get(uid)
    floor_text = f"📍 طبقه در حافظه: <b>{current_floor_memory}</b>" if current_floor_memory else "📍 طبقه در حافظه: <b>نامشخص</b>"
    text = (
        "🔙 پنل برگشت\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"📊 وضعیت فیچر: <b>{status}</b>\n"
        f"🎯 نوع برگشت فعلی: <b>{type_label}</b>\n"
        f"{floor_text}\n"
        "━━━━━━━━━━━━━━━━━\n"
        "👇 برای تغییر نوع برگشت، روی یکی از گزینه‌های زیر بزنید:"
    )
    kb = [
        [_cb(f"{'✅ ' if rtype == 'same' else '▫️ '}📍 برگشت به همون طبقه", "pn_ret_set_same")],
        [_cb(f"{'✅ ' if rtype == 'scatter' else '▫️ '}🎲 برگشت پراکنده", "pn_ret_set_scatter")],
        [_cb("🔍 بروزرسانی طبقه از بازی", "pn_ret_check_floor")],
        [_cb(f"{'🔴 خاموش کن' if ret_on else '🟢 روشن کن'}", "pn_ret_toggle")],
        [_cb("⚪ 🔙 بازگشت", "pn_cardinal_panel")],
    ]
    return text, kb

async def run_return_same_floor_workflow(user_id):
    if not is_return_enabled(user_id): return
    target_floor = user_current_floor.get(user_id)
    if not target_floor:
        client = user_clients.get(int(user_id))
        if not client or not client.is_connected():
            client = await ensure_user_client(user_id)
            if not client: return
        await _drain_sell_queue(user_id, "return"); await asyncio.sleep(0.3)
        info_resp = await _sell_send_and_wait(user_id, "🪶 اطلاعات من", 45, is_profile_message, "return")
        if info_resp:
            cf, mf, loc = parse_profile_info(info_resp)
            if cf > 0:
                target_floor = cf
                user_current_floor[user_id] = cf
            elif "بیرون" in loc and mf > 0:
                target_floor = mf
                user_current_floor[user_id] = mf
    if not target_floor:
        log_error(f"⏳ return_same: floor unknown for {user_id}.")
        return
        
    client = user_clients.get(int(user_id))
    if not client or not client.is_connected():
        client = await ensure_user_client(user_id)
        if not client: return
    await _drain_sell_queue(user_id, "return"); await asyncio.sleep(0.3)
    info_resp = await _sell_send_and_wait(user_id, "🪶 اطلاعات من", 45, is_profile_message, "return")
    if not info_resp: return
    current_floor, max_floor, location = parse_profile_info(info_resp)
    inside_city = is_user_inside_city(location)
    
    if not inside_city:
        await _notify_escape(user_id, "🏰 برمی‌گردم شهر...")
        await _drain_sell_queue(user_id, "return"); await asyncio.sleep(0.3)
        city_resp = await _sell_send_and_wait(user_id, "🏰 بازگشت به شهر", 45,
            lambda t: is_city_arrival_message(t) or is_distance_error_message(t), "return")
        if city_resp and is_distance_error_message(city_resp):
            await asyncio.sleep(1)
            crystal_resp = await _sell_send_and_wait(user_id,
                "💎 استفاده از کریستال تلپورت اجباری", 45, is_crystal_success_message, "return")
            if not crystal_resp:
                await _notify_escape(user_id, "⚠️ برگشت\n❌ نتونستم برگردم."); return
        await asyncio.sleep(1.5)
        
    await _drain_sell_queue(user_id, "return")
    tp_resp = await _sell_send_and_wait(user_id, "🌀 تلپورت به طبقات", 45, is_teleport_prompt, "return")
    if not tp_resp:
        await _notify_escape(user_id, "⚠️ برگشت\n❌ تلپورت نیامد."); return
        
    await asyncio.sleep(0.7); await _drain_sell_queue(user_id, "return"); await asyncio.sleep(0.3)
    result_resp = await _sell_send_and_wait(user_id, str(target_floor), 45,
        lambda t: is_teleport_success(t) or is_teleport_fail_no_money(t), "return")
    if not result_resp:
        await _notify_escape(user_id, "⚠️ جواب نیامد."); return
    if is_teleport_fail_no_money(result_resp):
        await _notify_escape(user_id, "⚠️ برگشت\n❌ پول نیست."); return
    if is_teleport_success(result_resp):
        new_floor = parse_teleport_result_floor(result_resp) or target_floor
        await asyncio.sleep(1.2)
        try: await _send_game_cmd(user_id, "🏰 خروج از شهر!", tag="return")
        except: pass
        await _notify_escape(user_id,
            f"✅ برگشت (همون طبقه)\n🏰 {current_floor} -> 🌀 {new_floor}\n🚪 بیرون")

async def run_return_same_floor_workflow_wrapper(user_id):
    try:
        async with get_user_lock(user_id):
            await run_return_same_floor_workflow(user_id)
    except Exception as e: log_error(f"return_same_wrap {user_id}: {e}")

async def run_return_workflow(user_id):
    if not is_return_enabled(user_id): return
    client = user_clients.get(int(user_id))
    if not client or not client.is_connected():
        client = await ensure_user_client(user_id)
        if not client: return
    await _drain_sell_queue(user_id, "return"); await asyncio.sleep(0.3)
    info_resp = await _sell_send_and_wait(user_id, "🪶 اطلاعات من", 45, is_profile_message, "return")
    if not info_resp:
        await _notify_escape(user_id, "⚠️ برگشت\n❌ اطلاعات نیامد."); return
    current_floor, max_floor, location = parse_profile_info(info_resp)
    inside_city = is_user_inside_city(location)
    if not inside_city:
        await _notify_escape(user_id, "🏰 برمی‌گردم شهر...")
        await _drain_sell_queue(user_id, "return"); await asyncio.sleep(0.3)
        city_resp = await _sell_send_and_wait(user_id, "🏰 بازگشت به شهر", 45,
            lambda t: is_city_arrival_message(t) or is_distance_error_message(t), "return")
        if city_resp and is_distance_error_message(city_resp):
            await asyncio.sleep(1)
            crystal_resp = await _sell_send_and_wait(user_id,
                "💎 استفاده از کریستال تلپورت اجباری", 45, is_crystal_success_message, "return")
            if not crystal_resp:
                await _notify_escape(user_id, "⚠️ برگشت\n❌ نتونستم برگردم."); return
        await asyncio.sleep(1.5)
    await _drain_sell_queue(user_id, "return")
    tp_resp = await _sell_send_and_wait(user_id, "🌀 تلپورت به طبقات", 45, is_teleport_prompt, "return")
    if not tp_resp:
        await _notify_escape(user_id, "⚠️ برگشت\n❌ تلپورت نیامد."); return
    end = max_floor if max_floor > 0 else 100
    candidates = []
    for n in range(2, end + 1):
        if n == current_floor: continue
        if is_floor_banned_for_hunt(user_id, n): continue
        candidates.append(n)
    if not candidates: candidates = [n for n in range(2, end + 1) if n != current_floor]
    if not candidates: candidates = [n for n in range(2, end + 1)]
    if not candidates:
        await _notify_escape(user_id, "❌ طبقه‌ای نیست."); return
    target = random.choice(candidates)
    await asyncio.sleep(0.7); await _drain_sell_queue(user_id, "return"); await asyncio.sleep(0.3)
    result_resp = await _sell_send_and_wait(user_id, str(target), 45,
        lambda t: is_teleport_success(t) or is_teleport_fail_no_money(t), "return")
    if not result_resp:
        await _notify_escape(user_id, "⚠️ جواب نیامد."); return
    if is_teleport_fail_no_money(result_resp):
        await _notify_escape(user_id, "⚠️ برگشت\n❌ پول نیست."); return
    if is_teleport_success(result_resp):
        new_floor = parse_teleport_result_floor(result_resp) or target
        await asyncio.sleep(1.2)
        try: await _send_game_cmd(user_id, "🏰 خروج از شهر!", tag="return")
        except: pass
        await _notify_escape(user_id,
            f"✅ برگشت\n🩸 شکست خوردی\n🏰 {current_floor} → 🌀 {new_floor}\n🚪 بیرون")

async def run_return_workflow_wrapper(user_id):
    try:
        async with get_user_lock(user_id):
            await run_return_workflow(user_id)
    except Exception as e: log_error(f"return_wrap {user_id}: {_translate_bot_errors(e)}")

# ═══════════════════════════════════════════════════════
# جایزه
# ═══════════════════════════════════════════════════════
def is_gift_response(text):
    if not text: return False
    t = _normalize_persian(text)
    keywords = ["جایزه", "جوایز روزانه", "پاداش روزانه", "امتیاز روزانه",
        "هدیه روزانه", "هدیه کاردینال", "سهمیه امروز",
        "قبلا دریافت", "قبلاً دریافت", "قبلا گرفته",
        "هنوز نرسیده", "ساعت دیگر", "ساعات دیگر", "بعدا بیا",
        "دریافت شد", "دریافت گردید", "موفق به دریافت",
        "واریز شد", "با موفقیت واریز"]
    return any(k in t for k in keywords)

def is_gift_taken(text):
    if not text: return False
    t = _normalize_persian(text)
    fail = ["قبلا دریافت", "قبلاً دریافت", "قبلا گرفته",
        "هنوز نرسیده", "ساعت دیگر", "ساعات دیگر", "بعدا بیا",
        "امکان پذیر نیست", "نمی توانید", "نمی تونید"]
    if any(k in t for k in fail): return False
    success = ["دریافت شد", "دریافت گردید", "موفق به دریافت", "گرفتی",
        "جایزه دریافت", "پاداش دریافت",
        "واریز شد", "با موفقیت واریز", "سهمیه امروز شما"]
    return any(k in t for k in success)

async def daily_gift_loop(user_id):
    tid = int(user_id)
    try:
        while True:
            if not daily_gift_status.get(user_id, False): return
            if not is_user_active(user_id) or not is_user_allowed(user_id): return
            async with get_user_lock(user_id):
                client = user_clients.get(tid)
                if not client or not client.is_connected():
                    client = await ensure_user_client(user_id)
                    if not client:
                        await asyncio.sleep(60); continue
                await _drain_sell_queue(user_id, "gift"); await asyncio.sleep(0.3)
                info_resp = await _sell_send_and_wait(user_id, "🪶 اطلاعات من", 45, is_profile_message, "gift")
                was_inside = False
                if info_resp:
                    _c, _m, location = parse_profile_info(info_resp)
                    was_inside = is_user_inside_city(location)
                if not was_inside:
                    await asyncio.sleep(0.5); await _drain_sell_queue(user_id, "gift")
                    city_resp = await _sell_send_and_wait(user_id, "🏰 بازگشت به شهر", 45,
                        lambda t: is_city_arrival_message(t) or is_distance_error_message(t), "gift")
                    if city_resp and is_distance_error_message(city_resp):
                        await asyncio.sleep(1)
                        crystal_resp = await _sell_send_and_wait(user_id,
                            "💎 استفاده از کریستال تلپورت اجباری", 45, is_crystal_success_message, "gift")
                        if not crystal_resp:
                            await asyncio.sleep(3600); continue
                    await asyncio.sleep(1.5)
                await _drain_sell_queue(user_id, "gift")
                gift_resp = await _sell_send_and_wait(user_id, "🎁 جوایز روزانه", 45, is_gift_response, "gift")
                await asyncio.sleep(2)
                gift_taken = False
                if gift_resp: gift_taken = is_gift_taken(gift_resp)
                else: await asyncio.sleep(3)
                if (not was_inside) and gift_taken:
                    await asyncio.sleep(1)
                    try: await _send_game_cmd(user_id, "🏰 خروج از شهر!", tag="daily_gift_out")
                    except: pass
                    await asyncio.sleep(2)
            waited = 0
            while waited < DAILY_GIFT_INTERVAL:
                await asyncio.sleep(min(60, DAILY_GIFT_INTERVAL - waited)); waited += 60
                if not daily_gift_status.get(user_id, False): return
    except asyncio.CancelledError: pass
    except Exception as e: log_error(f"daily_gift_loop {user_id}: {_translate_bot_errors(e)}")
    finally: daily_gift_tasks.pop(tid, None)

def start_daily_gift(user_id):
    tid = int(user_id); task = daily_gift_tasks.get(tid)
    if task and not task.done(): return False
    daily_gift_status[user_id] = True
    daily_gift_tasks[tid] = asyncio.create_task(daily_gift_loop(user_id))
    schedule_save_runtime()
    return True

def stop_daily_gift(user_id):
    daily_gift_status[user_id] = False
    task = daily_gift_tasks.pop(int(user_id), None)
    if task and not task.done(): task.cancel()
    schedule_save_runtime()

# ═══════════════════════════════════════════════════════
# ارسال خودکار
# ═══════════════════════════════════════════════════════
async def auto_send_loop(user_id, key):
    cfg = AUTO_SEND_CONFIG[key]; tid = (int(user_id), key)
    try:
        while True:
            if not auto_send_status.get(user_id, {}).get(key, False): return
            if not is_user_active(user_id) or not is_user_allowed(user_id): return
            async with get_user_lock(user_id):
                client = user_clients.get(int(user_id))
                if not client or not client.is_connected():
                    client = await ensure_user_client(user_id)
                    if not client:
                        await asyncio.sleep(30); continue
                try: await safe_send(client, user_id, GAME_BOT_ID, cfg["command"], tag=f"auto_{key}")
                except Exception as e: log_error(f"auto_send '{key}' {user_id}: {_translate_bot_errors(e)}")
            total = cfg["interval"]; step = 5; waited = 0
            while waited < total:
                await asyncio.sleep(min(step, total - waited)); waited += step
                if not auto_send_status.get(user_id, {}).get(key, False): return
    except asyncio.CancelledError: pass
    except Exception as e: log_error(f"auto_send_loop '{key}' {user_id}: {_translate_bot_errors(e)}")
    finally: auto_send_tasks.pop(tid, None)

def start_auto_send(user_id, key):
    tid = (int(user_id), key); task = auto_send_tasks.get(tid)
    if task and not task.done(): return False
    auto_send_status.setdefault(user_id, {})[key] = True
    auto_send_tasks[tid] = asyncio.create_task(auto_send_loop(user_id, key))
    schedule_save_runtime()
    return True

def stop_auto_send(user_id, key):
    auto_send_status.setdefault(user_id, {})[key] = False
    task = auto_send_tasks.pop((int(user_id), key), None)
    if task and not task.done(): task.cancel()
    schedule_save_runtime()

def stop_all_auto_sends(user_id):
    if user_id in auto_send_status:
        for key in list(auto_send_status[user_id].keys()): stop_auto_send(user_id, key)

# ═══════════════════════════════════════════════════════
# انتقال سکه
# ═══════════════════════════════════════════════════════
def _get_transfer_queue(user_id):
    if user_id not in transfer_queues:
        transfer_queues[user_id] = asyncio.Queue(maxsize=QUEUE_MAX_SIZE)
    return transfer_queues[user_id]

async def _notify_transfer(user_id, msg): await _notify_user(user_id, msg)

async def _wait_for_transfer_message(user_id, timeout, predicate):
    q = _get_transfer_queue(user_id); deadline = time.time() + timeout
    while True:
        remaining = deadline - time.time()
        if remaining <= 0: return None
        try: msg = await asyncio.wait_for(q.get(), timeout=remaining)
        except asyncio.TimeoutError: return None
        if predicate(msg): return msg

async def _transfer_send_and_wait(user_id, cmd, timeout, predicate):
    send_task = asyncio.create_task(_send_game_cmd(user_id, cmd, tag="transfer"))
    result = await _wait_for_transfer_message(user_id, timeout, predicate)
    try: await send_task
    except: pass
    return result

def is_transfer_start_prompt(text):
    t = _normalize_persian(text)
    return ("انتقال وجه کاردینالت" in t) or \
           ("شناسه کاردینال" in t and "مقصد" in t) or \
           ("C_ID" in text and "مقصد" in t)

def is_transfer_amount_prompt(text):
    t = _normalize_persian(text)
    return ("مبلغ انتقالی" in t) or \
           ("وضعیت مالیاتی" in t and "موجودی فعلی" in t) or \
           ("لطفاً مبلغ" in t and "عدد" in t)

def is_transfer_success(text): return "انتقال وجه با موفقیت" in _normalize_persian(text)
def is_transfer_insufficient(text): return "موجودی کافی نیست" in _normalize_persian(text)

def is_transfer_invalid_id(text):
    t = _normalize_persian(text)
    if "بازیکن مقصد یافت نشد" in t: return True
    if "شناسه کاردینال معتبری" in t: return True
    if "کاربر وجود ندارد" in t: return True
    if "یافت نشد" in t and "مقصد" in t: return True
    return False

def parse_tax_from_prompt(text):
    t = _normalize_persian(normalize_digits(text))
    for p in [r'وضعیت\s+مالیاتی\s+شما[:\s]+([\d.]+)\s*%',
              r'مالیات\s*(?:کسر\s*شده)?[:\s]+([\d.]+)\s*%',
              r'([\d.]+)\s*%\s*مالیات']:
        m = re.search(p, t)
        if m:
            try: return float(m.group(1))
            except: pass
    return None

def parse_balance_from_prompt(text):
    t = _normalize_persian(normalize_digits(text))
    for p in [r'موجودی\s+فعلی\s+شما[:\s]+(\d+)',
              r'موجودی\s+شما[:\s]+(\d+)',
              r'موجودی[:\s]+(\d+)\s*سکه']:
        m = re.search(p, t)
        if m:
            try: return int(m.group(1))
            except: pass
    return None

def parse_needed_from_error(text):
    m = re.search(r'نیاز\s+به\s+(\d+)\s*C', _normalize_persian(normalize_digits(text)))
    return int(m.group(1)) if m else None

async def run_transfer_workflow(user_id, notify=True):
    if user_id not in transfer_configs: return "disabled"
    cfg = transfer_configs[user_id]
    if not cfg.get("enabled"): return "disabled"
    c_id = cfg.get("c_id"); desired = cfg.get("desired")
    if not c_id or not desired: return "error"
    client = user_clients.get(int(user_id))
    if not client or not client.is_connected():
        client = await ensure_user_client(user_id)
        if not client: return "error"
    await asyncio.sleep(1)
    prompt1 = await _transfer_send_and_wait(user_id, "💸 انتقال سکه", 30, is_transfer_start_prompt)
    if not prompt1: return "error"
    await asyncio.sleep(1)
    prompt2 = await _transfer_send_and_wait(user_id, str(c_id), 30,
        lambda t: is_transfer_amount_prompt(t) or is_transfer_invalid_id(t))
    if not prompt2: return "error"
    if is_transfer_invalid_id(prompt2):
        await asyncio.sleep(1)
        try: await _send_game_cmd(user_id, "🔙 برگشت به منو", tag="transfer")
        except: pass
        if notify: await _notify_transfer(user_id, f"❌ انتقال ناموفق\n👤 C_ID: {c_id}")
        return "invalid_id"
    tax_percent = parse_tax_from_prompt(prompt2) or 15.0
    balance = parse_balance_from_prompt(prompt2)
    if balance is None: return "error"
    needed = int(desired * (1 + tax_percent / 100.0))
    if balance < needed:
        await asyncio.sleep(1)
        try: await _send_game_cmd(user_id, "🔙 برگشت به منو", tag="transfer")
        except: pass
        if notify:
            await _notify_transfer(user_id,
                f"⚠️ انتقال نشد\n👤 {c_id}\n💰 {desired:,}\n"
                f"📊 مالیات {tax_percent}%\n💳 نیاز {needed:,}\n💵 موجود {balance:,}")
        return "not_enough"
    await asyncio.sleep(1)
    result = await _transfer_send_and_wait(user_id, str(desired), 30,
        lambda t: is_transfer_success(t) or is_transfer_insufficient(t) or is_transfer_invalid_id(t))
    if not result: return "error"
    if is_transfer_invalid_id(result):
        await asyncio.sleep(1)
        try: await _send_game_cmd(user_id, "🔙 برگشت به منو", tag="transfer")
        except: pass
        if notify: await _notify_transfer(user_id, "❌ C_ID معتبر نیست.")
        return "invalid_id"
    if is_transfer_insufficient(result):
        await asyncio.sleep(1)
        try: await _send_game_cmd(user_id, "🔙 برگشت به منو", tag="transfer")
        except: pass
        if notify:
            actual = parse_needed_from_error(result) or needed
            await _notify_transfer(user_id, f"⚠️ موجودی نیست\n💳 نیاز: {actual:,}")
        return "not_enough"
    if notify:
        await _notify_transfer(user_id,
            f"✅ انتقال موفق\n👤 {c_id}\n💰 {desired:,}\n"
            f"📊 مالیات {tax_percent}%\n💳 کسر {needed:,}")
    return "success"

async def transfer_scheduler(user_id):
    try:
        while True:
            if user_id not in transfer_configs or not transfer_configs[user_id].get("enabled"): return
            try:
                async with get_user_lock(user_id):
                    result = await run_transfer_workflow(user_id)
            except Exception as e:
                log_error(f"transfer_sched {user_id}: {_translate_bot_errors(e)}"); result = "error"
            if result == "disabled": return
            cfg = transfer_configs.get(user_id, {}); mode = cfg.get("mode", "fast")
            if result == "success":
                mode = "slow"; sleep_seconds = TRANSFER_SLOW_DELAY
            elif result == "not_enough":
                sleep_seconds = TRANSFER_SLOW_DELAY if mode == "slow" else TRANSFER_FAST_DELAY
            elif result == "invalid_id":
                mode = "fast"; sleep_seconds = TRANSFER_INVALID_ID_RETRY
            else:
                mode = "fast"; sleep_seconds = TRANSFER_FAST_DELAY
            if user_id in transfer_configs: transfer_configs[user_id]["mode"] = mode
            await asyncio.sleep(sleep_seconds)
            if user_id not in transfer_configs or not transfer_configs[user_id].get("enabled"): return
    except asyncio.CancelledError: pass
    except Exception as e: log_error(f"transfer_scheduler {user_id}: {_translate_bot_errors(e)}")
    finally:
        if user_id in transfer_configs: transfer_configs[user_id]["task"] = None

def stop_transfer(user_id):
    cfg = transfer_configs.pop(user_id, None)
    if cfg:
        t = cfg.get("task")
        if t and not t.done(): t.cancel()
    transfer_queues.pop(user_id, None)
    schedule_save_runtime()

# ═══════════════════════════════════════════════════════
# تبچی
# ═══════════════════════════════════════════════════════
def get_user_banners(user_id):
    uid = str(user_id)
    if uid not in banners_db: banners_db[uid] = {}
    return banners_db[uid]

def get_banner_stats(user_id, name):
    uid = str(user_id)
    if uid not in stats_db: stats_db[uid] = {}
    if name not in stats_db[uid]:
        stats_db[uid][name] = {"sent_count": 0, "last_sent": None}
    return stats_db[uid][name]

def update_banner_stats(user_id, name):
    stats = get_banner_stats(user_id, name)
    stats["sent_count"] += 1; stats["last_sent"] = datetime.now().isoformat()
    save_json(STATS_FILE, stats_db)

async def _send_banner_to(client, user_id, name, banner, chat_id):
    text = banner.get("text", "") or ""
    btype = banner.get("type", "text")
    mode = banner.get("mode", "copy")
    media_file = banner.get("media_file")
    reply_to_id = banner.get("reply_to_msg_id")

    def _kwargs():
        k = {}
        if reply_to_id: k["reply_to"] = reply_to_id
        return k

    if mode == "forward" and banner.get("source_chat_id") and banner.get("source_msg_id"):
        try:
            await client.forward_messages(chat_id, banner["source_msg_id"],
                from_peer=banner["source_chat_id"], **_kwargs())
            return
        except Exception as e: log_error(f"banner fwd fail: {_translate_bot_errors(e)}")

    if btype == "text":
        try:
            await client.send_message(chat_id, text or "بدون متن", **_kwargs())
        except Exception as e:
            log_error(f"text send fail {chat_id}: {_translate_bot_errors(e)}")
            try: await client.send_message(chat_id, text or "بدون متن")
            except: pass
        return

    if not (media_file and os.path.exists(media_file)):
        try: await client.send_message(chat_id, text or "بدون متن", **_kwargs())
        except: pass
        return

    try:
        if btype == "voice":
            await client.send_file(chat_id, media_file, caption=text or None,
                voice_note=True, **_kwargs())
        elif btype == "audio":
            await client.send_file(chat_id, media_file, caption=text or None, **_kwargs())
        elif btype == "gif":
            try:
                await client.send_file(chat_id, media_file, caption=text or None,
                    supports_streaming=True, attributes=[], **_kwargs())
            except Exception:
                await client.send_file(chat_id, media_file, caption=text or None, **_kwargs())
        elif btype == "video":
            try:
                await client.send_file(chat_id, media_file, caption=text or None,
                    supports_streaming=True, **_kwargs())
            except Exception:
                await client.send_file(chat_id, media_file, caption=text or None, **_kwargs())
        elif btype == "sticker":
            await client.send_file(chat_id, media_file, force_document=False, **_kwargs())
        elif btype == "photo":
            await client.send_file(chat_id, media_file, caption=text or None, **_kwargs())
        else:
            await client.send_file(chat_id, media_file, caption=text or None, **_kwargs())
    except Exception as e:
        log_error(f"media send fail {btype} {chat_id}: {_translate_bot_errors(e)}")
        try: await client.send_file(chat_id, media_file, caption=text or None)
        except Exception as e2:
            log_error(f"media send fallback fail: {e2}")
            try: await client.send_message(chat_id, text or "بدون متن")
            except: pass

async def banner_loop(user_id, name):
    key = (int(user_id), name)
    try:
        while True:
            if not is_user_active(user_id) or not is_user_allowed(user_id): break
            client = user_clients.get(int(user_id))
            if not client or not client.is_connected():
                client = await ensure_user_client(user_id)
                if not client: break
            banners = get_user_banners(user_id); banner = banners.get(name)
            if not banner or not banner.get("active", False): break
            targets = list(banner.get("targets", []))
            if not targets: break
            for chat_id in targets:
                try:
                    await _send_banner_to(client, user_id, name, banner, chat_id)
                    update_banner_stats(user_id, name)
                except Exception as e: log_error(f"banner send {name}→{chat_id}: {_translate_bot_errors(e)}")
            banners = get_user_banners(user_id); banner = banners.get(name)
            if not banner: break
            interval = max(30, int(banner.get("interval", 60)))
            await asyncio.sleep(interval)
    except asyncio.CancelledError: pass
    except Exception as e: log_error(f"banner_loop {user_id}: {_translate_bot_errors(e)}")
    finally: broadcast_tasks.pop(key, None)

async def start_banner_task(user_id, name):
    key = (int(user_id), name); task = broadcast_tasks.get(key)
    if task and not task.done(): return False
    broadcast_tasks[key] = asyncio.create_task(banner_loop(user_id, name))
    return True

async def stop_banner_task(user_id, name):
    task = broadcast_tasks.pop((int(user_id), name), None)
    if task:
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass

async def stop_all_user_banners(user_id):
    keys = [k for k in list(broadcast_tasks.keys()) if k[0] == int(user_id)]
    for k in keys: await stop_banner_task(k[0], k[1])
    # ═══════════════════════════════════════════════════════
# Battle
# ═══════════════════════════════════════════════════════
FORBIDDEN_NAME_WORDS = {"با","به","از","یک","در","را","که","این","آن","بازیکن","اتحاد",
    "تیمی","موفقیت","پیوست","فراخوان","نبرد","طبقه","غول","نابودی","تهاجمی","ایجاد",
    "کرد","اعلان","قرمز","سیستم","آغاز","ملحق","فرمان","لیدر","عضو","اعضا","حماسه",
    "جدیدی","خلق","شد","فتح","پاداش","طلا"}

def get_battle_chats():
    if "chats" not in battle_db: battle_db["chats"] = {}
    return battle_db["chats"]

def get_chat_battle(chat_id):
    chats = get_battle_chats(); key = str(chat_id)
    if key not in chats:
        chats[key] = {"commanders": {}, "allies": {}, "ally_nicknames": {},
            "ally_cooldowns": {}, "orphan_teams": {}, "ally_join_status": {},
            "ally_max_floor": {}, "commander_floor_change_for": ""}
    for k in ("commanders","allies","ally_nicknames","ally_cooldowns","orphan_teams",
              "ally_join_status","ally_max_floor"):
        if k not in chats[key]: chats[key][k] = {}
    if "commander_floor_change_for" not in chats[key]:
        chats[key]["commander_floor_change_for"] = ""
    return chats[key]

def save_battle(): save_json(BATTLE_FILE, battle_db)

def add_commander(user_id, chat_id, nickname=""):
    c = get_chat_battle(chat_id)
    if str(user_id) in c.get("allies", {}): return
    if str(user_id) not in c["commanders"]:
        c["commanders"][str(user_id)] = {
            "nickname": nickname, "nickname_manual": False,
            "enabled_at": datetime.now().isoformat(),
            "last_code": "", "last_alert": "", "floor": 0, "state": "idle",
            "next_farakhans_at": "", "cooldown_seconds": 0,
            "auto_enabled": True, "city_retry_count": 0, "start_attempts": 0}
    else:
        c["commanders"][str(user_id)]["auto_enabled"] = True
    save_battle()

def remove_commander(user_id, chat_id):
    c = get_chat_battle(chat_id); cinfo = c["commanders"].pop(str(user_id), None)
    if "orphan_teams" not in c: c["orphan_teams"] = {}
    team_allies = [aid for aid, cmid in c["allies"].items() if str(cmid) == str(user_id)]
    if team_allies and cinfo is not None:
        c["orphan_teams"][str(user_id)] = {
            "nickname": cinfo.get("nickname", ""),
            "floor": cinfo.get("floor", 0),
            "left_at": datetime.now().isoformat()}
    save_battle()
    return cinfo, team_allies

def get_orphan_team_of_ally(chat_id, ally_id):
    c = get_chat_battle(chat_id); team_id = c["allies"].get(str(ally_id))
    if team_id is None: return None
    return str(team_id) if str(team_id) in c.get("orphan_teams", {}) else None

def get_active_team_of_ally(chat_id, ally_id):
    c = get_chat_battle(chat_id); team_id = c["allies"].get(str(ally_id))
    if team_id is None: return None
    return str(team_id) if str(team_id) in c.get("commanders", {}) else None

def revive_orphan_team(chat_id, new_commander_id, old_commander_id):
    c = get_chat_battle(chat_id)
    if str(old_commander_id) not in c.get("orphan_teams", {}): return False
    team_info = c["orphan_teams"].pop(str(old_commander_id))
    c["commanders"][str(new_commander_id)] = {
        "nickname": team_info.get("nickname", ""), "nickname_manual": False,
        "enabled_at": datetime.now().isoformat(), "last_code": "", "last_alert": "",
        "floor": team_info.get("floor", 0), "state": "idle",
        "next_farakhans_at": "", "cooldown_seconds": 0,
        "auto_enabled": True, "city_retry_count": 0, "start_attempts": 0}
    for aid in list(c["allies"].keys()):
        if str(c["allies"][aid]) == str(old_commander_id):
            c["allies"][aid] = int(new_commander_id)
    c["allies"].pop(str(new_commander_id), None)
    save_battle()
    return True

def cleanup_orphan_team_if_empty(chat_id, team_id):
    c = get_chat_battle(chat_id)
    if str(team_id) not in c.get("orphan_teams", {}): return
    if not any(str(cmid) == str(team_id) for cmid in c["allies"].values()):
        del c["orphan_teams"][str(team_id)]; save_battle()

def add_ally(ally_id, commander_id, chat_id):
    c = get_chat_battle(chat_id); existing = c["allies"].get(str(ally_id))
    if existing is not None and int(existing) != int(commander_id):
        return False, "already_in_other_team", int(existing)
    if existing is not None and int(existing) == int(commander_id):
        return True, int(commander_id)
    current_count = sum(1 for _, cmid in c["allies"].items() if str(cmid) == str(commander_id))
    if current_count >= MAX_ALLIES_PER_TEAM:
        return False, "team_full", current_count
    c["allies"][str(ally_id)] = int(commander_id)
    c.setdefault("ally_join_status", {})[str(ally_id)] = False
    save_battle()
    return True, int(commander_id)

def remove_ally(ally_id, chat_id):
    c = get_chat_battle(chat_id)
    team_id = c["allies"].pop(str(ally_id), None)
    c.get("ally_nicknames", {}).pop(str(ally_id), None)
    c.get("ally_join_status", {}).pop(str(ally_id), None)
    c.get("ally_max_floor", {}).pop(str(ally_id), None)
    save_battle()
    return team_id

def is_commander(user_id, chat_id):
    return str(user_id) in get_chat_battle(chat_id)["commanders"]

def get_ally_commander(ally_id, chat_id):
    return get_chat_battle(chat_id)["allies"].get(str(ally_id))

def is_ally(user_id, chat_id):
    return get_ally_commander(user_id, chat_id) is not None

def set_ally_cooldown(chat_id, ally_id, seconds):
    c = get_chat_battle(chat_id)
    c["ally_cooldowns"][str(ally_id)] = {
        "until": (datetime.now() + timedelta(seconds=seconds)).isoformat(),
        "seconds": seconds, "set_at": datetime.now().isoformat()}
    save_battle()

def get_max_ally_cooldown_remaining(chat_id):
    c = get_chat_battle(chat_id); ac = c.get("ally_cooldowns", {})
    if not ac: return 0
    now = datetime.now(); max_rem = 0
    for _aid, info in ac.items():
        try:
            rem = int((datetime.fromisoformat(info["until"]) - now).total_seconds())
            if rem > max_rem: max_rem = rem
        except: pass
    return max_rem

def clear_expired_ally_cooldowns(chat_id):
    c = get_chat_battle(chat_id); ac = c.get("ally_cooldowns", {}); now = datetime.now()
    for aid in list(ac.keys()):
        try:
            if datetime.fromisoformat(ac[aid]["until"]) < now: del ac[aid]
        except: del ac[aid]
    save_battle()

def parse_persian_duration(text):
    t = _normalize_persian(normalize_digits(text)); total = 0
    for pat, mult in [(r'(\d+)\s*ساعت', 3600), (r'(\d+)\s*دقیقه', 60), (r'(\d+)\s*ثانیه', 1)]:
        m = re.search(pat, t)
        if m: total += int(m.group(1)) * mult
    return total if total > 0 else None

def extract_join_code(text):
    m = re.search(r'ملحق\s+(\d+)', _normalize_persian(normalize_digits(text)))
    return m.group(1) if m else None

def extract_start_code(text):
    m = re.search(r'آغاز\s+نبرد\s+(\d+)', _normalize_persian(normalize_digits(text)))
    return m.group(1) if m else None

def extract_defense_code(text):
    m = re.search(r'ملحق\s+(\d+)', _normalize_persian(normalize_digits(text)))
    return m.group(1) if m else None

def extract_floor_number(text):
    m = re.search(r'طبقه\s+(\d+)', _normalize_persian(normalize_digits(text)))
    return int(m.group(1)) if m else None

def is_alert_message(text):
    t = _normalize_persian(text)
    return "اعلان قرمز" in t and "فراخوان" in t

def is_cooldown_message(text):
    t = _normalize_persian(text)
    return "زمان باقی" in t and "دقیقه" in t

def is_battle_result(text):
    t = _normalize_persian(text)
    return ("حماسه جدیدی خلق شد" in t) or ("فتح طبقه" in t and ("به زانو" in t or "🏆" in t))

def is_join_confirmation(text):
    return "به اتحاد تیمی پیوست" in _normalize_persian(text)

def is_city_restriction_message(text):
    t = _normalize_persian(text)
    return "شهر" in t and "نمی" in t and ("خروج" in t or "خارج" in t)

def is_valid_player_name(name):
    if not name: return False
    name = name.strip()
    if not (1 <= len(name) <= 30): return False
    if name in FORBIDDEN_NAME_WORDS or name.lower() in FORBIDDEN_NAME_WORDS: return False
    return True

def extract_join_name(text):
    m = re.search(r'بازیکن\s+(.+?)\s+با\s+موفقیت\s+به\s+اتحاد\s+تیمی\s+پیوست', _normalize_persian(text))
    if m:
        name = m.group(1).strip()
        if is_valid_player_name(name): return name
    return None

def extract_alert_name(text):
    m = re.search(r'بازیکن\s+(.+?)\s+یک\s+فراخوان', _normalize_persian(text))
    if m:
        name = m.group(1).strip()
        if is_valid_player_name(name): return name
    return None

def format_countdown(seconds):
    if seconds < 0: seconds = 0
    d, rem = divmod(int(seconds), 86400); h, rem = divmod(rem, 3600); m, s = divmod(rem, 60)
    if d > 0: return f"{d} روز و {h} ساعت"
    if h > 0: return f"{h} ساعت و {m} دقیقه"
    if m > 0: return f"{m} دقیقه و {s} ثانیه"
    return f"{s} ثانیه"

def get_time_until_next(cinfo):
    nfa = cinfo.get("next_farakhans_at")
    if not nfa: return None
    try: return max(0, int((datetime.fromisoformat(nfa) - datetime.now()).total_seconds()))
    except: return None

# ═══════════════════════════════════════════════════════
# Team attack helpers
# ═══════════════════════════════════════════════════════
def get_team_dict(chat_id): return team_attack_ready.setdefault(str(chat_id), {})

def get_team_members(chat_id, team_name):
    t = get_team_dict(chat_id).get(team_name, {})
    return [int(uid) for uid, v in t.items() if v]

def is_in_team(chat_id, team_name, user_id):
    return get_team_dict(chat_id).get(team_name, {}).get(str(user_id), False)

def join_team(chat_id, team_name, user_id):
    get_team_dict(chat_id).setdefault(team_name, {})[str(user_id)] = True

def leave_team(chat_id, team_name, user_id):
    if team_name in get_team_dict(chat_id):
        get_team_dict(chat_id)[team_name].pop(str(user_id), None)

def get_user_team_in_chat(chat_id, user_id):
    for tn, members in get_team_dict(chat_id).items():
        if members.get(str(user_id)): return tn
    return None

def delete_team(chat_id, team_name): get_team_dict(chat_id).pop(team_name, None)

def extract_join_code_full(text):
    t = _normalize_persian(normalize_digits(text))
    join_code = None; start_code = None
    for p in [r'ملحق\s+(\d+)', r'پیوستن[:\s]+\s*ملحق\s+(\d+)']:
        m = re.search(p, t)
        if m: join_code = m.group(1); break
    for p in [r'آغاز\s+نبرد\s+(\d+)', r'فرمان\s+آغاز[:\s]+\s*آغاز\s+نبرد\s+(\d+)']:
        m = re.search(p, t)
        if m: start_code = m.group(1); break
    if not start_code and join_code: start_code = join_code
    return join_code, start_code

# ═══════════════════════════════════════════════════════
# Relocate + Prepare commander
# ═══════════════════════════════════════════════════════
async def relocate_and_rejoin(user_id, chat_id, code, target_floor=0, is_commander=False):
    try:
        if not is_user_active(user_id): return
        async with get_user_lock(user_id):
            await _relocate_inner(user_id, chat_id, code, target_floor, is_commander)
    except Exception as e: log_error(f"relocate_and_rejoin {user_id}: {_translate_bot_errors(e)}")

async def _relocate_inner(user_id, chat_id, code, target_floor=0, is_commander=False):
    try:
        client = user_clients.get(int(user_id))
        if not client or not client.is_connected():
            client = await ensure_user_client(user_id)
            if not client: return
        await _notify_user(user_id, "🔄 می‌رم سر طبقه...")
        await _drain_sell_queue(user_id, "battle"); await asyncio.sleep(0.5)
        info_resp = await _sell_send_and_wait(user_id, "🪶 اطلاعات من", 45, is_profile_message, "battle")
        if not info_resp:
            await _notify_user(user_id, "❌ اطلاعات نیامد"); return
        cur_floor, max_floor, location = parse_profile_info(info_resp)
        inside_city = is_user_inside_city(location)
        if target_floor > 0 and max_floor > 0 and max_floor < target_floor:
            c = get_chat_battle(chat_id)
            c.setdefault("ally_max_floor", {})[str(user_id)] = max_floor
            save_battle()
            await _notify_user(user_id, f"❌ مرز {max_floor}، نمی‌تونم {target_floor}")
            try:
                nm = await get_plain_name(bot_client, user_id)
                role_str = "فرمانده" if is_commander else "یار"
                await bot_client.send_message(chat_id,
                    f"⚠️ {role_str}: {nm}\n📍 مرز من: طبقه {max_floor}\n🎯 هدف: طبقه {target_floor}\n"
                    f"❌ نمی‌تونم برسم\n💡 همه بریم طبقه {max_floor}")
            except: pass
            return
        need_teleport = (target_floor > 0 and cur_floor != target_floor)
        if need_teleport:
            if not inside_city:
                await _notify_user(user_id, "🏰 برمی‌گردم شهر...")
                await _drain_sell_queue(user_id, "battle"); await asyncio.sleep(0.3)
                city_resp = await _sell_send_and_wait(user_id, "🏰 بازگشت به شهر", 45,
                    lambda t: is_city_arrival_message(t) or is_distance_error_message(t), "battle")
                if city_resp and is_distance_error_message(city_resp):
                    await asyncio.sleep(1)
                    crystal_resp = await _sell_send_and_wait(user_id,
                        "💎 استفاده از کریستال تلپورت اجباری", 45, is_crystal_success_message, "battle")
                    if not crystal_resp:
                        try:
                            nm = await get_plain_name(bot_client, user_id)
                            await bot_client.send_message(chat_id, f"⚠️ {nm}\n💎 کریستال کافی نیست")
                        except: pass
                        return
                await asyncio.sleep(1.5)
            await _drain_sell_queue(user_id, "battle")
            tp_prompt = await _sell_send_and_wait(user_id, "🌀 تلپورت به طبقات", 45, is_teleport_prompt, "battle")
            if not tp_prompt:
                await _notify_user(user_id, "❌ منوی تلپورت باز نشد"); return
            await asyncio.sleep(1); await _drain_sell_queue(user_id, "battle")
            tp_result = await _sell_send_and_wait(user_id, str(target_floor), 45,
                lambda t: is_teleport_success(t) or is_teleport_fail_no_money(t), "battle")
            if not tp_result or is_teleport_fail_no_money(tp_result):
                await _notify_user(user_id, f"❌ تلپورت به {target_floor} نشد"); return
            await asyncio.sleep(1.5)
            inside_city = True
        if inside_city:
            exit_resp = await _sell_send_and_wait(user_id, "🏰 خروج از شهر!", 45, is_city_exit_message, "battle")
            if not exit_resp:
                await _drain_sell_queue(user_id, "battle")
                try: await _send_game_cmd(user_id, "🏰 خروج از شهر!", tag="relocate_out")
                except: pass
                await asyncio.sleep(3)
            else:
                await asyncio.sleep(1)
        if is_commander:
            await asyncio.sleep(5)
            if await safe_send(client, user_id, chat_id, "فراخوان فتح طبقه", tag="relocate_farakhans"):
                recent_farakhans[(chat_id, user_id)] = time.time()
                await _notify_user(user_id, f"📢 فراخوان از طبقه {target_floor or cur_floor}")
        else:
            if code:
                await asyncio.sleep(2)
                await safe_send(client, user_id, chat_id, f"ملحق {code}", tag="relocate_join")
                try:
                    nm = await get_plain_name(bot_client, user_id)
                    await bot_client.send_message(chat_id, f"✅ یار {nm} رسید طبقه {target_floor or cur_floor}")
                except: pass
            else:
                await _notify_user(user_id, f"✅ رسیدم طبقه {target_floor or cur_floor}")
                try:
                    nm = await get_plain_name(bot_client, user_id)
                    await bot_client.send_message(chat_id, f"✅ یار {nm} رسید طبقه {target_floor or cur_floor}")
                except: pass
    except Exception as e: log_error(f"_relocate_inner {user_id}: {_translate_bot_errors(e)}")

async def ally_prepare_for_battle(ally_id, chat_id, code, target_floor):
    await relocate_and_rejoin(ally_id, chat_id, code, target_floor, is_commander=False)

async def prepare_commander_for_farakhans(user_id, chat_id, forced_floor=0):
    try:
        client = user_clients.get(int(user_id))
        if not client or not client.is_connected():
            client = await ensure_user_client(user_id)
            if not client: return
        await _drain_sell_queue(user_id, "battle"); await asyncio.sleep(0.3)
        info_resp = await _sell_send_and_wait(user_id, "🪶 اطلاعات من", 45, is_profile_message, "battle")
        if not info_resp:
            await _notify_user(user_id, "❌ اطلاعات نیامد"); return
        cur_floor, max_floor, location = parse_profile_info(info_resp)
        inside_city = is_user_inside_city(location)
        if forced_floor > 0:
            target_floor = forced_floor
        else:
            target_floor = max_floor if max_floor > 0 else cur_floor
        if target_floor <= 0: return
        need_move = (cur_floor != target_floor) or inside_city
        if need_move:
            await _notify_user(user_id,
                f"🔄 آماده‌سازی فراخوان\n📍 الان: {cur_floor} ({'داخل' if inside_city else 'بیرون'})\n🎯 هدف: {target_floor}")
            if not inside_city and cur_floor != target_floor:
                await _drain_sell_queue(user_id, "battle")
                city_resp = await _sell_send_and_wait(user_id, "🏰 بازگشت به شهر", 45,
                    lambda t: is_city_arrival_message(t) or is_distance_error_message(t), "battle")
                if city_resp and is_distance_error_message(city_resp):
                    await asyncio.sleep(1)
                    crystal_resp = await _sell_send_and_wait(user_id,
                        "💎 استفاده از کریستال تلپورت اجباری", 45, is_crystal_success_message, "battle")
                    if not crystal_resp:
                        await _notify_user(user_id, "❌ کریستال کمه")
                        try: await bot_client.send_message(chat_id, "⚠️ فرمانده نمی‌تونه برگرده شهر، نبرد لغو")
                        except: pass
                        return
                await asyncio.sleep(1.5)
                inside_city = True
            if cur_floor != target_floor:
                await _drain_sell_queue(user_id, "battle")
                tp_prompt = await _sell_send_and_wait(user_id, "🌀 تلپورت به طبقات", 45, is_teleport_prompt, "battle")
                if not tp_prompt:
                    await _notify_user(user_id, "❌ منوی تلپورت نیامد"); return
                await asyncio.sleep(1); await _drain_sell_queue(user_id, "battle")
                tp_result = await _sell_send_and_wait(user_id, str(target_floor), 45,
                    lambda t: is_teleport_success(t) or is_teleport_fail_no_money(t), "battle")
                if not tp_result or is_teleport_fail_no_money(tp_result):
                    await _notify_user(user_id, f"❌ تلپورت {target_floor} نشد"); return
                await asyncio.sleep(1.5)
                inside_city = True
            if inside_city:
                exit_resp = await _sell_send_and_wait(user_id, "🏰 خروج از شهر!", 45, is_city_exit_message, "battle")
                if not exit_resp:
                    try: await _send_game_cmd(user_id, "🏰 خروج از شهر!", tag="prep_out")
                    except: pass
                    await asyncio.sleep(3)
                else:
                    await asyncio.sleep(1)
            await _notify_user(user_id, f"✅ بیرون شهر تو طبقه {target_floor}")
    except Exception as e: log_error(f"prepare_commander {user_id}: {_translate_bot_errors(e)}")

# ═══════════════════════════════════════════════════════
# Battle Tasks
# ═══════════════════════════════════════════════════════
async def send_scheduled_farakhans(user_id, chat_id, delay):
    key = (int(user_id), int(chat_id), "farakhans")
    try:
        await asyncio.sleep(delay)
        c = get_chat_battle(chat_id)
        cinfo = c["commanders"].get(str(user_id), {})
        if not cinfo.get("auto_enabled", True): return
        if cinfo.get("state") == "paused_by_user": return
        if not is_commander(user_id, chat_id): return
        await prepare_commander_for_farakhans(user_id, chat_id)
        await asyncio.sleep(5)
        client = user_clients.get(int(user_id))
        if not client or not client.is_connected():
            client = await ensure_user_client(user_id)
            if not client: return
        if await safe_send(client, user_id, chat_id, "فراخوان فتح طبقه", tag="farakhans"):
            recent_farakhans[(chat_id, user_id)] = time.time()
            await _notify_user(user_id, f"📢 فراخوان ارسال شد\n🆔 {chat_id}")
    except asyncio.CancelledError: pass
    except Exception as e: log_error(f"sched_farakhans: {_translate_bot_errors(e)}")
    finally: pending_battle_tasks.pop(key, None)

async def send_auto_farakhans(user_id, chat_id, delay):
    key = (int(user_id), int(chat_id), "auto_farakhans")
    try:
        await asyncio.sleep(delay)
        c = get_chat_battle(chat_id)
        cinfo = c["commanders"].get(str(user_id), {})
        if not cinfo.get("auto_enabled", True): return
        if cinfo.get("state") == "paused_by_user": return
        if not is_commander(user_id, chat_id): return
        await prepare_commander_for_farakhans(user_id, chat_id)
        await asyncio.sleep(5)
        client = user_clients.get(int(user_id))
        if not client or not client.is_connected():
            client = await ensure_user_client(user_id)
            if not client: return
        if await safe_send(client, user_id, chat_id, "فراخوان فتح طبقه", tag="auto_farakhans"):
            recent_farakhans[(chat_id, user_id)] = time.time()
            await _notify_user(user_id, f"📢 فراخوان خودکار\n🆔 {chat_id}")
    except asyncio.CancelledError: pass
    except Exception as e: log_error(f"auto_farakhans: {_translate_bot_errors(e)}")
    finally: pending_battle_tasks.pop(key, None)

async def send_start_battle(user_id, chat_id, code, delay=240):
    key = (int(user_id), int(chat_id), "start_battle")
    try:
        clear_expired_ally_cooldowns(chat_id)
        ally_cd = get_max_ally_cooldown_remaining(chat_id)
        if ally_cd > 0:
            pending_battle_tasks.pop(key, None)
            schedule_start_battle(user_id, chat_id, code, ally_cd + 10); return
        await asyncio.sleep(delay)
        clear_expired_ally_cooldowns(chat_id)
        ally_cd = get_max_ally_cooldown_remaining(chat_id)
        if ally_cd > 0:
            pending_battle_tasks.pop(key, None)
            schedule_start_battle(user_id, chat_id, code, ally_cd + 10); return
        c = get_chat_battle(chat_id)
        cinfo = c["commanders"].get(str(user_id), {})
        if not cinfo.get("auto_enabled", True): return
        if cinfo.get("state") == "paused_by_user": return
        target_floor = cinfo.get("floor", 0)
        my_allies = [aid for aid, cmid in c.get("allies", {}).items() if str(cmid) == str(user_id)]
        allies_max = c.get("ally_max_floor", {})
        changed_code = c.get("commander_floor_change_for", "")
        if my_allies and target_floor > 0 and changed_code != code:
            min_floor = None
            for aid in my_allies:
                mf = allies_max.get(str(aid), 0)
                if mf > 0 and (min_floor is None or mf < min_floor):
                    min_floor = mf
            if min_floor is not None and min_floor < target_floor:
                c["commander_floor_change_for"] = code
                save_battle()
                try:
                    nm = "?"
                    for aid in my_allies:
                        if allies_max.get(str(aid), 0) == min_floor:
                            nm = await get_plain_name(bot_client, int(aid)); break
                    await bot_client.send_message(chat_id,
                        f"⚠️ تغییر طبقه\n👥 یار ({nm}) تا طبقه {min_floor}\n🏰 فرمانده {target_floor}\n✅ همه می‌ریم {min_floor}")
                except: pass
                _spawn(relocate_and_rejoin(user_id, chat_id, "", min_floor, is_commander=True))
                return
        missing = []
        if my_allies:
            js = c.setdefault("ally_join_status", {})
            for aid in my_allies:
                if not js.get(aid, False): missing.append(aid)
        if missing:
            attempts = cinfo.get("start_attempts", 0)
            if attempts < 5:
                cinfo["start_attempts"] = attempts + 1
                c["commanders"][str(user_id)] = cinfo
                save_battle()
                try:
                    names = []
                    for aid in missing:
                        nm = await get_plain_name(bot_client, int(aid)); names.append(nm)
                    miss_str = "، ".join(names)
                    await _notify_user(user_id, f"⏳ منتظر {len(missing)} یار\n👥 {miss_str}\n🔄 تلاش {attempts+1}/5")
                    try: await bot_client.send_message(chat_id, f"⏳ منتظر یارها: {miss_str}")
                    except: pass
                except: pass
                schedule_start_battle(user_id, chat_id, code, 30)
                return
            else:
                try:
                    names = []
                    for aid in missing:
                        nm = await get_plain_name(bot_client, int(aid)); names.append(nm)
                    miss_str = "، ".join(names)
                    await bot_client.send_message(chat_id, f"⛔ نبرد لغو شد\n❌ نیامدن: {miss_str}")
                    await _notify_user(user_id, f"⛔ لغو شد. نیامدن: {miss_str}")
                except: pass
                cinfo["state"] = "idle"; cinfo["start_attempts"] = 0
                c["commanders"][str(user_id)] = cinfo
                save_battle()
                _spawn(scatter_all_allies_of_commander(chat_id, user_id, False))
                return
        cinfo["start_attempts"] = 0
        c["commanders"][str(user_id)] = cinfo
        save_battle()
        client = user_clients.get(int(user_id))
        if not client or not client.is_connected():
            client = await ensure_user_client(user_id)
            if not client: return
        if await safe_send(client, user_id, chat_id, f"آغاز نبرد {code}", tag="start_battle"):
            await _notify_user(user_id, f"⚔️ آغاز نبرد ارسال شد\n🔑 {code}\n👥 {len(my_allies)}")
    except asyncio.CancelledError: pass
    except Exception as e: log_error(f"start_battle: {_translate_bot_errors(e)}")
    finally: pending_battle_tasks.pop(key, None)

def _cancel_old_task(key):
    old = pending_battle_tasks.get(key)
    if old and not old.done(): old.cancel()

def schedule_farakhans(user_id, chat_id, delay):
    key = (int(user_id), int(chat_id), "farakhans")
    _cancel_old_task(key)
    pending_battle_tasks[key] = asyncio.create_task(send_scheduled_farakhans(user_id, chat_id, delay))

def schedule_auto_farakhans(user_id, chat_id, delay):
    key = (int(user_id), int(chat_id), "auto_farakhans")
    _cancel_old_task(key)
    pending_battle_tasks[key] = asyncio.create_task(send_auto_farakhans(user_id, chat_id, delay))

def schedule_start_battle(user_id, chat_id, code, delay=240):
    key = (int(user_id), int(chat_id), "start_battle")
    _cancel_old_task(key)
    pending_battle_tasks[key] = asyncio.create_task(send_start_battle(user_id, chat_id, code, delay))

def cancel_user_battle_tasks(user_id, chat_id=None):
    count = 0
    for key in list(pending_battle_tasks.keys()):
        if key[0] == int(user_id):
            if chat_id is None or key[1] == int(chat_id):
                t = pending_battle_tasks.pop(key); t.cancel(); count += 1
    return count

# ═══════════════════════════════════════════════════════
# City retry
# ═══════════════════════════════════════════════════════
async def send_city_exit_command(user_id):
    client = user_clients.get(int(user_id))
    if not client or not client.is_connected():
        client = await ensure_user_client(user_id)
        if not client: return False
    return await safe_send(client, user_id, GAME_BOT_ID, CITY_EXIT_COMMAND, tag="city_exit")

async def city_exit_retry_task(user_id, chat_id, role, code="", retry_count=0):
    key = (int(user_id), int(chat_id), f"city_retry_{role}")
    try:
        await send_city_exit_command(user_id)
        await asyncio.sleep(CITY_RETRY_DELAY)
        if role == "commander":
            if not is_commander(user_id, chat_id): return
            c = get_chat_battle(chat_id)
            cinfo = c["commanders"].get(str(user_id), {})
            if not cinfo.get("auto_enabled", True): return
            if retry_count >= CITY_MAX_RETRIES:
                try: await bot_client.send_message(int(user_id), f"⚠️ بعد از {CITY_MAX_RETRIES} تلاش نتونستم خارج شم.")
                except: pass
                await asyncio.sleep(CITY_WARNING_DELAY)
                pending_battle_tasks.pop(key, None)
                if is_commander(user_id, chat_id):
                    schedule_city_exit_retry(user_id, chat_id, "commander", "", 0)
                return
            client = user_clients.get(int(user_id))
            if client and client.is_connected():
                if await safe_send(client, user_id, chat_id, "فراخوان فتح طبقه", tag="city_cmd"):
                    recent_farakhans[(chat_id, user_id)] = time.time()
                    cinfo["state"] = "city_retry"
                    cinfo["city_retry_count"] = retry_count + 1
                    c["commanders"][str(user_id)] = cinfo
                    save_battle()
        elif role == "ally":
            cm_id = get_ally_commander(user_id, chat_id)
            if cm_id is None: return
            if retry_count >= CITY_MAX_RETRIES:
                try:
                    ally_name = await get_plain_name(bot_client, user_id)
                    await bot_client.send_message(int(cm_id), f"⚠️ یار {ally_name} نتونست از شهر خارج شه.")
                except: pass
                await asyncio.sleep(CITY_WARNING_DELAY)
                pending_battle_tasks.pop(key, None)
                if get_ally_commander(user_id, chat_id) is not None:
                    schedule_city_exit_retry(user_id, chat_id, "ally", code, 0)
                return
            if code:
                client = user_clients.get(int(user_id))
                if client and client.is_connected():
                    if await safe_send(client, user_id, chat_id, f"ملحق {code}", tag="city_ally"):
                        recent_ally_joins[(chat_id, user_id)] = time.time()
    except asyncio.CancelledError: pass
    except Exception as e: log_error(f"city_exit_retry: {_translate_bot_errors(e)}")
    finally: pending_battle_tasks.pop(key, None)

def schedule_city_exit_retry(user_id, chat_id, role, code="", retry_count=0):
    key = (int(user_id), int(chat_id), f"city_retry_{role}")
    _cancel_old_task(key)
    pending_battle_tasks[key] = asyncio.create_task(
        city_exit_retry_task(user_id, chat_id, role, code, retry_count))

# ═══════════════════════════════════════════════════════
# Team attack functions
# ═══════════════════════════════════════════════════════
async def send_member_join(user_id, chat_id, code):
    try:
        if not is_user_active(user_id): return False
        client = user_clients.get(int(user_id))
        if not client or not client.is_connected():
            client = await ensure_user_client(user_id)
            if not client: return False
        return await safe_send(client, user_id, chat_id, f"ملحق {code}", tag="team_join")
    except Exception as e:
        log_error(f"send_member_join {user_id}: {_translate_bot_errors(e)}"); return False

async def return_member_to_city(user_id, chat_id):
    try:
        if not is_user_active(user_id): return
        client = user_clients.get(int(user_id))
        if not client or not client.is_connected():
            client = await ensure_user_client(user_id)
            if not client: return
        await _drain_sell_queue(user_id, "battle"); await asyncio.sleep(0.5)
        info_resp = await _sell_send_and_wait(user_id, "🪶 اطلاعات من", 45, is_profile_message, "battle")
        if info_resp:
            _cur, _max, location = parse_profile_info(info_resp)
            if is_user_inside_city(location): return
        try: await _send_game_cmd(user_id, "🏰 بازگشت به شهر", tag="team_cancel_city")
        except: pass
        await asyncio.sleep(3)
    except Exception as e: log_error(f"return_member_to_city {user_id}: {_translate_bot_errors(e)}")

async def return_all_members_to_city(chat_id, team_name, reason=""):
    try:
        chat_pending = team_attack_pending.get(str(chat_id), {})
        pending = chat_pending.get(team_name)
        members = pending.get("members", []) if pending else get_team_members(chat_id, team_name)
        if not members: return
        for mid in members:
            _spawn(return_member_to_city(mid, chat_id))
            await asyncio.sleep(3)
    except Exception as e: log_error(f"return_all: {_translate_bot_errors(e)}")

async def check_and_finalize_team_attack(chat_id, team_name, initiator):
    try:
        chat_str = str(chat_id)
        chat_pending = team_attack_pending.get(chat_str, {})
        pending = chat_pending.get(team_name)
        if not pending or pending.get("started") or pending.get("cancelled"): return
        js = pending.setdefault("join_status", {})
        members = pending.get("members", [])
        start_code = pending.get("start_code", "")
        all_conf = bool(members) and all(js.get(str(mid)) == "confirmed" for mid in members)
        if all_conf:
            pending["started"] = True
            await asyncio.sleep(2)
            client = user_clients.get(int(initiator))
            if not client or not client.is_connected():
                client = await ensure_user_client(initiator)
            if client:
                await safe_send(client, initiator, chat_id, f"آغاز نبرد {start_code}", tag="team_start")
            await asyncio.sleep(180)
            if chat_pending.get(team_name) is pending:
                chat_pending.pop(team_name, None)
            return
        elapsed = time.time() - pending["created_at"]
        if elapsed > TEAM_ATTACK_JOIN_TIMEOUT:
            pending["cancelled"] = True
            _spawn(return_all_members_to_city(chat_id, team_name, f"{len(members)} نفر"))
            try:
                missing = [mid for mid in members if js.get(str(mid)) != "confirmed"]
                names = []
                for mid in missing:
                    nm = await get_plain_name(bot_client, mid); names.append(nm)
                miss_str = "، ".join(names)
                await bot_client.send_message(chat_id, f"⛔ تیم «{team_name}» لغو شد\n❌ نیامدن: {miss_str}")
            except: pass
            await asyncio.sleep(2)
            chat_pending.pop(team_name, None)
        else:
            await asyncio.sleep(TEAM_ATTACK_JOIN_RETRY)
            await check_and_finalize_team_attack(chat_id, team_name, initiator)
    except Exception as e: log_error(f"check_finalize {chat_id}/{team_name}: {_translate_bot_errors(e)}")

# ═══════════════════════════════════════════════════════
# Defense
# ═══════════════════════════════════════════════════════
async def _cleanup_defense_pending(chat_str, cmdr_id_str, delay):
    try:
        await asyncio.sleep(delay)
        chat_defenses = defense_pending.get(chat_str, {})
        if cmdr_id_str in chat_defenses: chat_defenses.pop(cmdr_id_str, None)
    except: pass

async def _prepare_defense_commander(user_id, chat_id, target_floor):
    try:
        client = user_clients.get(int(user_id))
        if not client or not client.is_connected():
            client = await ensure_user_client(user_id)
            if not client: return
        async with get_user_lock(user_id):
            await _drain_sell_queue(user_id, "battle"); await asyncio.sleep(0.3)
            info_resp = await _sell_send_and_wait(user_id, "🪶 اطلاعات من", 45, is_profile_message, "battle")
            if not info_resp:
                await _notify_user(user_id, "❌ اطلاعات نیامد"); return
            cur_floor, max_floor, location = parse_profile_info(info_resp)
            inside_city = is_user_inside_city(location)
            if max_floor > 0 and max_floor < target_floor:
                await _notify_user(user_id, f"❌ مرز {max_floor}، نمی‌تونم {target_floor}")
                defense_pending.get(str(chat_id), {}).pop(str(user_id), None)
                return
            if cur_floor != target_floor:
                if not inside_city:
                    await _drain_sell_queue(user_id, "battle")
                    city_resp = await _sell_send_and_wait(user_id, "🏰 بازگشت به شهر", 45,
                        lambda t: is_city_arrival_message(t) or is_distance_error_message(t), "battle")
                    if city_resp and is_distance_error_message(city_resp):
                        await asyncio.sleep(1)
                        cr = await _sell_send_and_wait(user_id, "💎 استفاده از کریستال تلپورت اجباری",
                            45, is_crystal_success_message, "battle")
                        if not cr: return
                    await asyncio.sleep(1.5)
                    inside_city = True
                await _drain_sell_queue(user_id, "battle")
                tp_prompt = await _sell_send_and_wait(user_id, "🌀 تلپورت به طبقات", 45, is_teleport_prompt, "battle")
                if tp_prompt:
                    await asyncio.sleep(1); await _drain_sell_queue(user_id, "battle")
                    tp_res = await _sell_send_and_wait(user_id, str(target_floor), 45,
                        lambda t: is_teleport_success(t) or is_teleport_fail_no_money(t), "battle")
                    if tp_res and is_teleport_success(tp_res):
                        await asyncio.sleep(1.5); inside_city = True
                    else: return
            if inside_city:
                exit_resp = await _sell_send_and_wait(user_id, "🏰 خروج از شهر!", 45, is_city_exit_message, "battle")
                if not exit_resp:
                    try: await _send_game_cmd(user_id, "🏰 خروج از شهر!", tag="defense_out")
                    except: pass
                    await asyncio.sleep(3)
                else: await asyncio.sleep(1)
            await asyncio.sleep(1)
            if await safe_send(client, user_id, chat_id, f"دفاع تیمی {target_floor}", tag="defense_team"):
                await _notify_user(user_id, f"🛡️ دفاع تیمی فعال شد\n🎯 طبقه: {target_floor}")
    except Exception as e: log_error(f"_prepare_defense_commander {user_id}: {_translate_bot_errors(e)}")

async def _prepare_defense_ally(ally_id, chat_id, target_floor):
    try:
        if not is_user_active(ally_id) or not is_user_allowed(ally_id): return
        if is_ally_paused(chat_id, ally_id): return
        client = user_clients.get(int(ally_id))
        if not client or not client.is_connected():
            client = await ensure_user_client(ally_id)
            if not client: return
        async with get_user_lock(ally_id):
            await _drain_sell_queue(ally_id, "battle"); await asyncio.sleep(0.3)
            info_resp = await _sell_send_and_wait(ally_id, "🪶 اطلاعات من", 45, is_profile_message, "battle")
            if not info_resp: return
            cur_floor, max_floor, location = parse_profile_info(info_resp)
            inside_city = is_user_inside_city(location)
            if max_floor > 0 and max_floor < target_floor: return
            if cur_floor != target_floor:
                if not inside_city:
                    await _drain_sell_queue(ally_id, "battle")
                    city_resp = await _sell_send_and_wait(ally_id, "🏰 بازگشت به شهر", 45,
                        lambda t: is_city_arrival_message(t) or is_distance_error_message(t), "battle")
                    if city_resp and is_distance_error_message(city_resp):
                        await asyncio.sleep(1)
                        cr = await _sell_send_and_wait(ally_id, "💎 استفاده از کریستال تلپورت اجباری",
                            45, is_crystal_success_message, "battle")
                        if not cr: return
                    await asyncio.sleep(1.5); inside_city = True
                await _drain_sell_queue(ally_id, "battle")
                tp_prompt = await _sell_send_and_wait(ally_id, "🌀 تلپورت به طبقات", 45, is_teleport_prompt, "battle")
                if tp_prompt:
                    await asyncio.sleep(1); await _drain_sell_queue(ally_id, "battle")
                    tp_res = await _sell_send_and_wait(ally_id, str(target_floor), 45,
                        lambda t: is_teleport_success(t) or is_teleport_fail_no_money(t), "battle")
                    if not (tp_res and is_teleport_success(tp_res)): return
                    await asyncio.sleep(1.5); inside_city = True
            if inside_city:
                exit_resp = await _sell_send_and_wait(ally_id, "🏰 خروج از شهر!", 45, is_city_exit_message, "battle")
                if not exit_resp:
                    try: await _send_game_cmd(ally_id, "🏰 خروج از شهر!", tag="defense_ally_out")
                    except: pass
                    await asyncio.sleep(3)
            await _notify_user(ally_id, f"🛡️ آماده دفاع طبقه {target_floor}\n⏳ منتظر اعلان آبی...")
    except Exception as e: log_error(f"_prepare_defense_ally {ally_id}: {_translate_bot_errors(e)}")

# ═══════════════════════════════════════════════════════
# Scatter
# ═══════════════════════════════════════════════════════
async def scatter_ally_after_battle(user_id, chat_id, is_win=True):
    try:
        if not is_user_active(user_id) or not is_user_allowed(user_id): return
        async with get_user_lock(user_id):
            await _scatter_ally_inner(user_id, chat_id, is_win)
    except Exception as e: log_error(f"scatter_ally_after_battle {user_id}: {_translate_bot_errors(e)}")

async def _scatter_ally_inner(user_id, chat_id, is_win=True):
    try:
        client = user_clients.get(int(user_id))
        if not client or not client.is_connected():
            client = await ensure_user_client(user_id)
            if not client: return
        await _notify_user(user_id, f"{'🏆' if is_win else '💀'} نتیجه نبرد\n🔄 پراکنده می‌شم...")
        await asyncio.sleep(4 if is_win else 3)
        await _drain_sell_queue(user_id, "battle"); await asyncio.sleep(0.5)
        info_resp = await _sell_send_and_wait(user_id, "🪶 اطلاعات من", 45, is_profile_message, "battle")
        if not info_resp: return
        current_floor, max_floor, location = parse_profile_info(info_resp)
        inside_city = is_user_inside_city(location)
        if not inside_city:
            await asyncio.sleep(1); await _drain_sell_queue(user_id, "battle"); await asyncio.sleep(0.3)
            city_resp = await _sell_send_and_wait(user_id, "🏰 بازگشت به شهر", 45,
                lambda t: is_city_arrival_message(t) or is_distance_error_message(t), "battle")
            if city_resp and is_distance_error_message(city_resp):
                await asyncio.sleep(1)
                crystal_resp = await _sell_send_and_wait(user_id,
                    "💎 استفاده از کریستال تلپورت اجباری", 45, is_crystal_success_message, "battle")
                if not crystal_resp: return
            await asyncio.sleep(1.5)
        await _drain_sell_queue(user_id, "battle")
        tp_prompt = await _sell_send_and_wait(user_id, "🌀 تلپورت به طبقات", 45, is_teleport_prompt, "battle")
        if not tp_prompt: return
        end = max_floor if max_floor > 0 else 100
        if end > 5:
            candidates = [n for n in range(1, end + 1) if n != current_floor]
            if not candidates: candidates = [1]
            target = random.choice(candidates)
        else: target = 1
        await asyncio.sleep(1); await _drain_sell_queue(user_id, "battle"); await asyncio.sleep(0.3)
        result_resp = await _sell_send_and_wait(user_id, str(target), 45,
            lambda t: is_teleport_success(t) or is_teleport_fail_no_money(t), "battle")
        if not result_resp: return
        if is_teleport_fail_no_money(result_resp): return
        if is_teleport_success(result_resp):
            new_floor = parse_teleport_result_floor(result_resp) or target
            await asyncio.sleep(1.5)
            await _sell_send_and_wait(user_id, "🏰 خروج از شهر!", 45, is_city_exit_message, "battle")
            await _notify_user(user_id, f"✅ پراکنده شدم\n🏰 {current_floor} → 🌀 {new_floor}")
    except Exception as e: log_error(f"_scatter_ally_inner {user_id}: {_translate_bot_errors(e)}")

async def scatter_all_allies_of_commander(chat_id, commander_id, is_win=True):
    try:
        c = get_chat_battle(chat_id)
        allies = [aid for aid, cmid in c.get("allies", {}).items() if str(cmid) == str(commander_id)]
        all_members = allies + [str(commander_id)]
        try:
            await bot_client.send_message(chat_id,
                f"{'🏆' if is_win else '💀'} نتیجه نبرد\n👥 {len(all_members)} نفر در حال پراکنده شدن...")
        except: pass
        _spawn(scatter_ally_after_battle(int(commander_id), chat_id, is_win))
        await asyncio.sleep(2)
        for aid in allies:
            _spawn(scatter_ally_after_battle(int(aid), chat_id, is_win))
            await asyncio.sleep(2)
    except Exception as e: log_error(f"scatter_all: {_translate_bot_errors(e)}")

async def team_attack_escape_all(chat_id, members, is_win):
    try:
        if not members: return
        for mid in members:
            _spawn(scatter_ally_after_battle(mid, chat_id, is_win))
            await asyncio.sleep(2)
    except Exception as e: log_error(f"team_attack_escape_all: {_translate_bot_errors(e)}")

# ═══════════════════════════════════════════════════════
# Login
# ═══════════════════════════════════════════════════════
async def start_cmd(event):
    user_id = event.sender_id
    _ensure_user(str(user_id)); save_json(USERS_FILE, users_db)
    if not is_user_allowed(user_id):
        await event.reply("❌ تحریم."); return
    await event.reply(
        "🎉 به ربات سلف ساز خوش آمدید!\n\n"
        f"• ورود: /login\n"
        f"• پنل: {CMD}پنل")

async def login_cmd(event):
    user_id = event.sender_id
    if not is_user_allowed(user_id):
        await event.reply("❌ تحریم."); return
    old_state = login_states.pop(user_id, None)
    if old_state:
        oc = old_state.get("client")
        if oc:
            try: await oc.disconnect()
            except: pass
    if user_id in user_clients:
        try: await user_clients[user_id].disconnect()
        except: pass
        del user_clients[user_id]
    session_path = SESSION_DIR / str(user_id)
    if os.path.exists(str(session_path) + ".session"):
        test_client = TelegramClient(str(session_path), API_ID, API_HASH)
        try:
            await test_client.connect()
            if await test_client.is_user_authorized():
                await event.reply(f"✅ لاگین هستی.\n\n{CMD}پنل",
                    buttons=types.ReplyKeyboardHide())
                set_user_active(user_id, True)
                set_user_locally_disabled(user_id, False)
                await test_client.disconnect()
                await create_user_client(user_id)
                return
            await test_client.disconnect()
        except: pass
    login_states[user_id] = {"step": "awaiting_phone", "phone": "", "code": "",
        "password": "", "client": None, "message_id": None, "chat_id": event.chat_id}
    kb = types.ReplyKeyboardMarkup(
        rows=[
            types.KeyboardButtonRow(buttons=[
                types.KeyboardButtonRequestPhone("📱 ارسال شماره من")]),
            types.KeyboardButtonRow(buttons=[types.KeyboardButton("❌ لغو")]),
        ], resize=True, single_use=False)
    msg = await event.reply(
        "📱 <b>ورود به حساب</b>\n"
        "شماره را دستی وارد کن یا دکمهٔ پایین را بزن تا شماره‌ات ارسال شود.\n"
        "• ایران: بدون صفر و پیش‌شماره (نمونه: 989123456789)\n"
        "• لغو ورود: دکمهٔ «❌ لغو» را بزن یا «لغو» بفرست.",
        buttons=kb, parse_mode="html")
    login_states[user_id]["message_id"] = msg.id
    login_states[user_id]["phone_msg_id"] = msg.id

async def handle_login_input(event):
    user_id = event.sender_id
    if user_id not in login_states: return
    if event.raw_text and event.raw_text.startswith("/") and event.raw_text.strip().lower() != "/cancel": return
    state = login_states[user_id]
    step = state.get("step")
    text = normalize_digits((event.raw_text or "").strip())
    if step == "awaiting_phone":
        raw_text = (event.raw_text or "").strip()
        if raw_text in ("❌ لغو", "لغو", "کنسل", "/cancel"):
            login_states.pop(user_id, None)
            try:
                await event.reply("🔙 لغو شد.\n/login",
                    buttons=types.ReplyKeyboardHide())
            except: pass
            return
        contact = getattr(event.message, 'contact', None)
        if contact and getattr(contact, 'phone_number', None):
            phone = re.sub(r'[^\d]', '', str(contact.phone_number))
            if phone.startswith("00"): phone = phone[2:]
            if not phone.startswith("98") and len(phone) == 11 and phone.startswith("09"):
                phone = "98" + phone[1:]
            elif not phone.startswith("98") and len(phone) == 10 and phone.startswith("9"):
                phone = "98" + phone
            if not phone.isdigit() or len(phone) < 10:
                await event.reply("❌ شماره نامعتبر.")
                return
        else:
            if not text: return
            if not text.isdigit():
                await event.reply("❌ اعداد بفرست یا روی دکمه بزن.")
                return
            phone = text
        state["phone"] = phone
        session_path = SESSION_DIR / str(user_id)
        client = TelegramClient(str(session_path), API_ID, API_HASH)
        try:
            await client.connect()
            await client.send_code_request(phone)
            state.update({"client": client, "step": "awaiting_code", "code": ""})
            login_states[user_id] = state
            kb = generate_number_keyboard("awaiting_code", "")
            new_msg = await event.reply("✅ کد ۵ رقمی.", buttons=kb)
            try:
                await event.reply("👇 کد رو با دکمه‌های زیر وارد کن",
                    buttons=types.ReplyKeyboardHide())
            except: pass
            state["message_id"] = new_msg.id
            state["chat_id"] = event.chat_id
            login_states[user_id] = state
        except Exception as e:
            try: await client.disconnect()
            except: pass
            await event.reply(f"❌ {_translate_bot_errors(e)}")
            login_states.pop(user_id, None)
    elif step == "awaiting_code":
        if not text or not text.isdigit() or len(text) < 4:
            await event.reply("❌ حداقل ۴ رقم."); return
        client = state.get("client")
        if not client:
            login_states.pop(user_id, None); return
        try:
            await client.sign_in(state.get("phone", ""), text)
            pwp = state.get("phone", "")
            if not pwp.startswith("+"): pwp = "+" + pwp
            set_user_phone(user_id, pwp)
            me = await client.get_me()
            name = (me.first_name or "")
            if me.last_name: name += " " + me.last_name
            set_user_name(user_id, name.strip())
            await client.disconnect()
            login_states.pop(user_id, None)
            set_user_active(user_id, True)
            set_user_locally_disabled(user_id, False)
            await create_user_client(user_id)
            await event.reply(f"✅ ورود!\n\n{CMD}پنل",
                buttons=types.ReplyKeyboardHide())
        except SessionPasswordNeededError:
            await event.reply("🔐 رمز دو مرحله‌ای.",
                buttons=types.ReplyKeyboardHide())
            state["step"] = "awaiting_password"
            login_states[user_id] = state
        except Exception as e:
            try: await client.disconnect()
            except: pass
            await event.reply(f"❌ {_translate_bot_errors(e)}")
            login_states.pop(user_id, None)
    elif step == "awaiting_password":
        password = (event.raw_text or "").strip()
        client = state.get("client")
        if not client or not password:
            login_states.pop(user_id, None); return
        try:
            await client.sign_in(password=password)
            pwp = state.get("phone", "")
            if pwp and not pwp.startswith("+"): pwp = "+" + pwp
            set_user_phone(user_id, pwp)
            me = await client.get_me()
            name = (me.first_name or "")
            if me.last_name: name += " " + me.last_name
            set_user_name(user_id, name.strip())
            await client.disconnect()
            login_states.pop(user_id, None)
            set_user_active(user_id, True)
            set_user_locally_disabled(user_id, False)
            await create_user_client(user_id)
            await event.reply(f"✅ ورود!\n\n{CMD}پنل",
                buttons=types.ReplyKeyboardHide())
        except Exception as e:
            try: await client.disconnect()
            except: pass
            await event.reply(f"❌ {_translate_bot_errors(e)}")
            login_states.pop(user_id, None)

async def login_callback_handler(event):
    user_id = event.sender_id
    try: data = event.data.decode()
    except: return
    if data == "relogin_start":
        try: await event.answer("⏳ در حال ارسال کد...")
        except: pass
        old_state = login_states.pop(user_id, None)
        if old_state and old_state.get("client"):
            try: await old_state["client"].disconnect()
            except: pass
        if user_id in user_clients:
            try: await user_clients[user_id].disconnect()
            except: pass
            del user_clients[user_id]
        saved_phone = users_db["users"].get(str(user_id), {}).get("phone", "")
        phone = re.sub(r'[^\d]', '', saved_phone or "")
        if phone.startswith("00"): phone = phone[2:]
        if not phone.startswith("98") and len(phone) == 11 and phone.startswith("09"):
            phone = "98" + phone[1:]
        elif not phone.startswith("98") and len(phone) == 10 and phone.startswith("9"):
            phone = "98" + phone
        if not phone or len(phone) < 10:
            login_states[user_id] = {"step": "awaiting_phone", "phone": "", "code": "",
                "password": "", "client": None, "message_id": event.message_id,
                "chat_id": event.chat_id}
            try:
                await event.edit(
                    "📱 شماره‌ت رو بفرست:\n"
                    "━━━━━━━━━━━━━━━━━\n"
                    "• با دکمهٔ پایین شماره را بفرست یا دستی وارد کن\n"
                    "• لغو: دکمهٔ «❌ لغو» یا نوشتن «لغو»\n"
                    "📌 نمونه: 989123456789",
                    buttons=types.ReplyKeyboardMarkup(
                        rows=[
                            types.KeyboardButtonRow(buttons=[
                                types.KeyboardButtonRequestPhone("📱 ارسال شماره من")]),
                            types.KeyboardButtonRow(buttons=[types.KeyboardButton("❌ لغو")]),
                        ], resize=True, single_use=False))
            except: pass
            return
        session_path = SESSION_DIR / str(user_id)
        if os.path.exists(str(session_path) + ".session"):
            try: os.remove(str(session_path) + ".session")
            except: pass
        client = TelegramClient(str(session_path), API_ID, API_HASH)
        try:
            await client.connect()
            await client.send_code_request(phone)
            login_states[user_id] = {"step": "awaiting_code", "phone": phone, "code": "",
                "client": client, "message_id": event.message_id, "chat_id": event.chat_id}
            kb = generate_number_keyboard("awaiting_code", "")
            try:
                await event.edit(
                    "✅ کد به شماره‌ات فرستاده شد.\n"
                    "━━━━━━━━━━━━━━━━━\n"
                    "👇 کد رو با دکمه‌های زیر وارد کن:",
                    buttons=kb)
            except: pass
            try: await event.answer("✅ کد فرستاده شد")
            except: pass
        except FloodWaitError as e:
            try: await event.answer(f"⏱ {e.seconds} ثانیه صبر کن", alert=True)
            except: pass
            try: await client.disconnect()
            except: pass
            login_states.pop(user_id, None)
        except Exception as e:
            log_error(f"relogin_start send_code {user_id}: {type(e).__name__}: {_translate_bot_errors(e)}")
            try: await event.answer(f"❌ خطا: {_translate_bot_errors(e)}", alert=True)
            except: pass
            try: await client.disconnect()
            except: pass
            login_states.pop(user_id, None)
        return
    if user_id not in login_states:
        try: await event.answer("❌ نشست نیست.", alert=True)
        except: pass
        return
    state = login_states[user_id]
    if state.get("step") != "awaiting_code":
        try: await event.answer("⚠️ این مرحله.", alert=True)
        except: pass
        return
    if data == "resend_code":
        client = state.get("client"); phone = state.get("phone", "")
        if not client or not phone:
            try: await event.answer("❌ اول شماره.", alert=True)
            except: pass
            return
        try:
            await client.send_code_request(phone)
            state["code"] = ""; login_states[user_id] = state
            kb = generate_number_keyboard("awaiting_code", "")
            try: await event.client.edit_message(event.chat_id, event.message_id, "✅ کد جدید.", buttons=kb)
            except: pass
            try: await event.answer("✅")
            except: pass
        except FloodWaitError as e:
            try: await event.answer(f"⏱ {e.seconds}s", alert=True)
            except: pass
        except Exception as e:
            try: await event.answer(f"❌ {_translate_bot_errors(e)}", alert=True)
            except: pass
        return
    cur = state.get("code", "")
    if data.startswith("num_"):
        if len(cur) >= 10:
            try: await event.answer("❌ طولانی!", alert=True)
            except: pass
            return
        state["code"] = cur + data.split("_")[1]; login_states[user_id] = state
        kb = generate_number_keyboard("awaiting_code", state["code"])
        try:
            await event.client.edit_message(event.chat_id, event.message_id,
                render_login_message("awaiting_code", state["code"]), buttons=kb)
        except: pass
        try: await event.answer()
        except: pass
    elif data == "clear":
        state["code"] = cur[:-1]; login_states[user_id] = state
        kb = generate_number_keyboard("awaiting_code", state["code"])
        try:
            await event.client.edit_message(event.chat_id, event.message_id,
                render_login_message("awaiting_code", state["code"]), buttons=kb)
        except: pass
        try: await event.answer()
        except: pass
    elif data == "done":
        code = state.get("code", "")
        if len(code) < 4:
            try: await event.answer("❌ حداقل ۴.", alert=True)
            except: pass
            return
        client = state.get("client")
        if not client:
            login_states.pop(user_id, None); return
        try:
            await client.sign_in(state.get("phone", ""), code)
            pwp = state.get("phone", "")
            if not pwp.startswith("+"): pwp = "+" + pwp
            set_user_phone(user_id, pwp)
            me = await client.get_me()
            name = (me.first_name or "")
            if me.last_name: name += " " + me.last_name
            set_user_name(user_id, name.strip())
            await client.disconnect()
            login_states.pop(user_id, None)
            set_user_active(user_id, True)
            set_user_locally_disabled(user_id, False)
            await create_user_client(user_id)
            await event.client.edit_message(event.chat_id, event.message_id, f"✅ ورود!\n\n{CMD}پنل")
            try:
                await bot_client.send_message(event.chat_id, "✅",
                    buttons=types.ReplyKeyboardHide())
            except: pass
            try: await event.answer("✅")
            except: pass
        except SessionPasswordNeededError:
            await event.client.edit_message(event.chat_id, event.message_id, "🔐 رمز دو مرحله‌ای.")
            state["step"] = "awaiting_password"; login_states[user_id] = state
            try: await event.answer("رمز.", alert=True)
            except: pass
        except Exception as e:
            try: await client.disconnect()
            except: pass
            login_states.pop(user_id, None)
            try: await event.answer(f"❌ {_translate_bot_errors(e)}", alert=True)
            except: pass
    elif data == "done_disabled":
        try: await event.answer("⚠️ کامل نیست!", alert=True)
        except: pass

def render_login_message(step, current_input):
    if step == "awaiting_code":
        return f"✅ کد:\n\nکد: `{current_input if current_input else '—'}`"
    return ""

def generate_number_keyboard(step, current_input):
    if step != "awaiting_code": return None
    rows = [
        [types.KeyboardButtonCallback("1", data="num_1"),
         types.KeyboardButtonCallback("2", data="num_2"),
         types.KeyboardButtonCallback("3", data="num_3")],
        [types.KeyboardButtonCallback("4", data="num_4"),
         types.KeyboardButtonCallback("5", data="num_5"),
         types.KeyboardButtonCallback("6", data="num_6")],
        [types.KeyboardButtonCallback("7", data="num_7"),
         types.KeyboardButtonCallback("8", data="num_8"),
         types.KeyboardButtonCallback("9", data="num_9")],
        [types.KeyboardButtonCallback("⌫", data="clear"),
         types.KeyboardButtonCallback("0", data="num_0"),
         types.KeyboardButtonCallback("✅", data="done")],
        [types.KeyboardButtonCallback("💠 ارسال مجدد کد", data="resend_code")]
    ]
    if len(current_input) < 4:
        rows[3][2] = types.KeyboardButtonCallback("✅ (کامل کنید)", data="done_disabled")
    return rows

# ═══════════════════════════════════════════════════════
# Battle handler
# ═══════════════════════════════════════════════════════
async def battle_incoming_handler(event, user_id):
    try:
        _snd = await event.get_sender()
        _uname = (getattr(_snd, 'username', '') or '').lower().lstrip("@")
        _txt = (event.raw_text or "")[:80].replace("\n", " ")
        log_error(f"📨 RAW [{user_id}] {_uname}: {_txt}")
    except: pass
    if event.sender_id == user_id: return
    if not is_user_active(user_id) or not is_user_allowed(user_id): return
    if event.is_private:
        try:
            cfg = get_ttl_config(user_id)
            if cfg["enabled"]:
                await _try_ttl_save(user_id, event)
        except Exception as _e:
            log_error(f"ttl hook {user_id}: {_e}")
    _pt = event.raw_text or ""
    if user_id in pony_waiting and _pt and is_pony_profile_message(_pt):
        try:
            _sender = await event.get_sender()
            _sid = getattr(_sender, 'id', None)
            if _sid == user_id: pass
            elif event.is_private:
                await handle_pony_response(event, user_id); return
            elif event.reply_to_msg_id:
                try:
                    _replied = await event.client.get_messages(event.chat_id, ids=event.reply_to_msg_id)
                    if _replied and _replied.sender_id == user_id:
                        await handle_pony_response(event, user_id); return
                except: pass
            else:
                _my_names = set()
                try:
                    _n1 = users_db["users"].get(str(user_id), {}).get("name", "")
                    if _n1: _my_names.add(_n1.strip())
                except: pass
                try:
                    _n2 = await get_plain_name(event.client, user_id)
                    if _n2: _my_names.add(_n2.strip())
                except: pass
                try:
                    _me = await event.client.get_me()
                    if _me:
                        if getattr(_me, 'first_name', None): _my_names.add(_me.first_name.strip())
                        if getattr(_me, 'last_name', None): _my_names.add(_me.last_name.strip())
                except: pass
                _pt_norm = _normalize_persian(_pt).lower()
                for _nm in _my_names:
                    if not _nm: continue
                    if _normalize_persian(_nm).lower() in _pt_norm:
                        await handle_pony_response(event, user_id); return
        except: pass
    if user_id in dungeon_waiting:
        try:
            if await handle_dungeon_response(event, user_id): return
        except: pass
    try:
        _now = time.time()
        for _k in [k for k, v in recent_ally_joins.items() if _now - v > 1800]: recent_ally_joins.pop(_k, None)
        for _k in [k for k, v in recent_farakhans.items() if _now - v > 1800]: recent_farakhans.pop(_k, None)
    except: pass
    try:
        sender = await event.get_sender()
        sender_uname = (getattr(sender, 'username', '') or '').lower()
        sender_id_val = getattr(sender, 'id', None)
        text_val = event.raw_text or ""
        # ─── بررسی خودکار انتقال مواد در موجودی ───
        if transfer_materials_config.get(user_id, {}).get("enabled"):
            try: _get_queue(user_id, "mat_inv").put_nowait(text_val)
            except: pass







        if text_val:
            log_error(f"📥 [{user_id}] {sender_uname} ({sender_id_val}): {text_val[:70]}")

        is_pew_sender = (sender_uname and sender_uname == PEW_BOT_USERNAME.lower().lstrip("@"))
        # Detect the fan-art announcement from any sender, in any group, when enabled.
        # It is not tied to a bot username because these announcements vary by group.
        if is_pew_art_group_prompt(user_id, event, text_val):
            log_error(f"🎨 pew art prompt detected in group {event.chat_id} for {user_id}")
            await _pew_art_catch(user_id, event)
            return
        if is_pew_sender and text_val:
            if is_pew_art_win(text_val) or is_pew_art_loss(text_val):
                await _pew_art_result(user_id, event)
                return

        if sender_id_val == GAME_BOT_ID or (sender_uname and sender_uname == GAME_BOT_USERNAME.lower()):
            if text_val:
                detected_floor = extract_floor_generic(text_val)
                if detected_floor and detected_floor > 0:
                    user_current_floor[user_id] = detected_floor

                await _route_game_bot_message(user_id, text_val)
                normalized_game_text = _normalize_persian(text_val)
                if ("کریستال شانس" in normalized_game_text
                        and "این شکار" in normalized_game_text
                        and "استفاده" in normalized_game_text):
                    try:
                        await event.client.send_message(event.chat_id, "✅ بله، استفاده شود")
                        log_error(f"🔮 lucky crystal accepted for {user_id}")
                    except Exception as e:
                        log_error(f"lucky crystal reply {user_id}: {_translate_bot_errors(e)}")
                    return
                if is_forbidden_equipment_prompt(text_val):
                    try:
                        await event.client.send_message(event.chat_id, "❌ خیر، بدون معجون")
                    except: pass
                    return
                if is_yes_no_retry_prompt(text_val):
                    st = yes_retry_state.setdefault(user_id, {"count": 0, "last_ts": 0})
                    now = time.time()
                    if now - st["last_ts"] > 60: st["count"] = 0
                    st["count"] += 1; st["last_ts"] = now
                    if st["count"] >= 2:
                        try:
                            await event.client.send_message(event.chat_id, "❌ خیر، بدون معجون")
                        except: pass
                        yes_retry_state.pop(user_id, None); return
                    yes_reply = get_yes_reply(text_val)
                    if yes_reply:
                        try: await event.client.send_message(GAME_BOT_ID, yes_reply)
                        except: pass
                        return
                if is_dungeon_hunt_loss(text_val):
                    log_error(f"🏰 dungeon loss ignored for {user_id}")
                    return
                if is_hunt_success(text_val) or is_hunt_cooldown(text_val):
                    hunt_fail_counter.pop(user_id, None)
                if is_hunt_failure_return_city(text_val):
                    max_f = get_max_fails(user_id)
                    cnt = hunt_fail_counter.get(user_id, 0) + 1
                    hunt_fail_counter[user_id] = cnt
                    if cnt < max_f:
                        try:
                            await _notify_user(user_id,
                                f"🩸 شکار ناموفق ({cnt}/{max_f})\n"
                                f"⏳ یه بار دیگه امتحان می‌کنم...")
                        except: pass
                        _spawn(_retry_hunt_once(user_id))
                    else:
                        hunt_fail_counter[user_id] = 0
                        if not is_floor_test_enabled(user_id):
                            try:
                                await _notify_user(user_id,
                                    f"🩸 {cnt}/{max_f} باخت پشت سر هم\n"
                                    f"🔴 جابه‌جایی طبقه خاموشه — همین‌جا می‌مونم")
                            except: pass
                            return
                        _spawn(_handle_hunt_failure(user_id, event.chat_id, "🦖 شکار هیولا"))
                    return
                yes_reply = get_yes_reply(text_val)
                if yes_reply:
                    try:
                        await event.client.send_message(GAME_BOT_ID, yes_reply)
                    except: pass
                    return
            _is_team_result = bool(text_val) and (is_team_attack_win(text_val) or is_team_attack_loss(text_val))
            if text_val and not _is_team_result and (is_spy_warning(text_val) or is_defense_win_message(text_val)):
                trigger_reason = "🕵️ قاتل ناشناس جاسوسیت کرد" if is_spy_warning(text_val) else "🛡️ مهاجمت رو شکست دادی"
                if is_escape_enabled(user_id):
                    _spawn(run_escape_workflow_wrapper(user_id, trigger_reason))
                else:
                    try:
                        await bot_client.send_message(int(user_id),
                            f"⚠️ گزارش امنیتی\n{trigger_reason}.\n🔴 فرار خاموشه\n💡 {CMD}فرار روشن")
                    except: pass
            if text_val and not _is_team_result and is_kill_message(text_val):
                if is_return_enabled(user_id):
                    _spawn(run_return_workflow_wrapper(user_id))
                else:
                    try:
                        await bot_client.send_message(int(user_id),
                            "⚠️ گزارش برگشت\n🩸 تیم مهاجم شکستت داد.\n💡 .،برگشت روشن")
                    except: pass
    except Exception as e: log_error(f"route {user_id}: {_translate_bot_errors(e)}")
    chat_id = event.chat_id; text = event.raw_text or ""
    if not text: return
    chat_str = str(chat_id)
    chat_pending = team_attack_pending.get(chat_str, {})
    for team_name, pending in list(chat_pending.items()):
        if is_not_same_floor_error(text):
            _spawn(return_all_members_to_city(chat_id, team_name, "فرمانده و هدف هم‌طبقه نبودن"))
            try: await bot_client.send_message(chat_id, f"⛔ تیم «{team_name}» لغو شد")
            except: pass
            await asyncio.sleep(2); chat_pending.pop(team_name, None); return
        if is_target_in_safe_zone(text):
            _spawn(return_all_members_to_city(chat_id, team_name, "هدف در منطقه امن"))
            try: await bot_client.send_message(chat_id, f"⛔ تیم «{team_name}» لغو شد")
            except: pass
            await asyncio.sleep(2); chat_pending.pop(team_name, None); return
        if is_join_wrong_floor(text):
            rej = None
            if event.reply_to_msg_id:
                try:
                    replied = await event.client.get_messages(chat_id, ids=event.reply_to_msg_id)
                    if replied and replied.sender_id: rej = replied.sender_id
                except: pass
            target = rej if rej else user_id
            required = get_required_floor_from_reject(text)
            if str(target) in [str(m) for m in pending.get("members", [])] and required:
                code = pending.get("join_code", "")
                js = pending.setdefault("join_status", {})
                js[str(target)] = "need_floor"
                _spawn(relocate_and_rejoin(int(target), chat_id, code, required, is_commander=False))
                return
        if is_join_need_outside(text):
            rej = None
            if event.reply_to_msg_id:
                try:
                    replied = await event.client.get_messages(chat_id, ids=event.reply_to_msg_id)
                    if replied and replied.sender_id: rej = replied.sender_id
                except: pass
            target = rej if rej else user_id
            if str(target) in [str(m) for m in pending.get("members", [])]:
                code = pending.get("join_code", "")
                js = pending.setdefault("join_status", {})
                js[str(target)] = "need_outside"
                _spawn(relocate_and_rejoin(int(target), chat_id, code, 0, is_commander=False))
                return
        if not pending.get("join_code"):
            if time.time() - pending["created_at"] > TEAM_ATTACK_JOIN_TIMEOUT:
                _spawn(return_all_members_to_city(chat_id, team_name, "بازی کد نداد"))
                try: await bot_client.send_message(chat_id, f"⛔ تیم «{team_name}» لغو")
                except: pass
                await asyncio.sleep(2); chat_pending.pop(team_name, None); return
            jc, sc = extract_join_code_full(text)
            if jc:
                pending["join_code"] = jc; pending["start_code"] = sc or jc
                members = pending.get("members", [])
                for mid in members:
                    pending.setdefault("join_status", {})[str(mid)] = "waiting"
                    _spawn(send_member_join(mid, chat_id, jc))
                    await asyncio.sleep(3)
                _spawn(check_and_finalize_team_attack(chat_id, team_name, pending["initiator"]))
        if is_join_confirmation(text):
            reply_id = event.reply_to_msg_id; confirmed_id = None
            if reply_id:
                try:
                    replied = await event.client.get_messages(chat_id, ids=reply_id)
                    if replied and replied.sender_id: confirmed_id = replied.sender_id
                except: pass
            if confirmed_id and str(confirmed_id) in [str(m) for m in pending.get("members", [])]:
                js = pending.setdefault("join_status", {})
                js[str(confirmed_id)] = "confirmed"
    if text and is_defense_alert_message(text):
        defense_code = extract_defense_code(text)
        defense_floor = extract_floor_number(text)
        chat_defenses = defense_pending.get(chat_str, {})
        if chat_defenses and defense_code:
            my_commander = None
            for cmdr_id_str, dp in chat_defenses.items():
                if str(user_id) in [str(m) for m in dp.get("members", [])]:
                    my_commander = cmdr_id_str; break
            if my_commander is None: return
            dp = chat_defenses[my_commander]
            if dp.get("started"): return
            if is_ally_paused(chat_id, user_id): return
            dp["code"] = defense_code
            if defense_floor: dp["floor"] = defense_floor
            dp["started"] = True
            members = dp.get("members", [])
            for mid in members:
                if is_ally_paused(chat_id, mid): continue
                _spawn(relocate_and_rejoin(int(mid), chat_id, defense_code, dp.get("floor", 0), is_commander=False))
                await asyncio.sleep(3)
            _spawn(_cleanup_defense_pending(chat_str, my_commander, 180))
        return
    if text and (is_team_attack_win(text) or is_team_attack_loss(text)):
        is_win = is_team_attack_win(text)
        if chat_pending:
            for team_name, p in list(chat_pending.items()):
                members = p.get("members", [])
                chat_pending.pop(team_name, None)
                _spawn(team_attack_escape_all(chat_id, members, is_win))
            return
    am_commander = is_commander(user_id, chat_id)
    ally_commander_id = get_ally_commander(user_id, chat_id)
    am_ally = ally_commander_id is not None
    if not am_commander and not am_ally: return
    if am_ally and is_ally_paused(chat_id, user_id): return
    if am_commander:
        c_chk = get_chat_battle(chat_id)
        cinfo_chk = c_chk["commanders"].get(str(user_id), {})
        if cinfo_chk.get("state") == "paused_by_user": return
    if is_city_restriction_message(text):
        if am_commander:
            cinfo = get_chat_battle(chat_id)["commanders"].get(str(user_id), {})
            schedule_city_exit_retry(user_id, chat_id, "commander", "", cinfo.get("city_retry_count", 0)); return
        if am_ally:
            commander_info = get_chat_battle(chat_id)["commanders"].get(str(ally_commander_id), {})
            schedule_city_exit_retry(user_id, chat_id, "ally", commander_info.get("last_code", ""), 0); return
    if is_join_rejected(text):
        rejected_id = None
        if event.reply_to_msg_id:
            try:
                replied = await event.client.get_messages(chat_id, ids=event.reply_to_msg_id)
                if replied and replied.sender_id: rejected_id = replied.sender_id
            except: pass
        target = rejected_id if rejected_id else user_id
        required = get_required_floor_from_reject(text)
        if target == user_id and required > 0:
            c = get_chat_battle(chat_id)
            c.setdefault("ally_join_status", {})[str(user_id)] = False
            save_battle()
            recent_ally_joins.pop((chat_id, user_id), None)
            if am_commander:
                cinfo = c["commanders"].get(str(user_id), {})
                code = cinfo.get("last_code", "")
                if code: _spawn(relocate_and_rejoin(user_id, chat_id, code, required, is_commander=False))
            elif am_ally and ally_commander_id:
                cinfo = c["commanders"].get(str(ally_commander_id), {})
                code = cinfo.get("last_code", "")
                if code: _spawn(relocate_and_rejoin(user_id, chat_id, code, required, is_commander=False))
        return
    if is_join_need_outside(text):
        rejected_id = None
        if event.reply_to_msg_id:
            try:
                replied = await event.client.get_messages(chat_id, ids=event.reply_to_msg_id)
                if replied and replied.sender_id: rejected_id = replied.sender_id
            except: pass
        target = rejected_id if rejected_id else user_id
        if target == user_id:
            if am_commander:
                cinfo = get_chat_battle(chat_id)["commanders"].get(str(user_id), {})
                code = cinfo.get("last_code", ""); tgt_floor = cinfo.get("floor", 0)
                if code: _spawn(relocate_and_rejoin(user_id, chat_id, code, tgt_floor, is_commander=False))
            elif am_ally and ally_commander_id:
                cinfo = get_chat_battle(chat_id)["commanders"].get(str(ally_commander_id), {})
                code = cinfo.get("last_code", ""); tgt_floor = cinfo.get("floor", 0)
                if code: _spawn(relocate_and_rejoin(user_id, chat_id, code, tgt_floor, is_commander=False))
        return
    if is_join_confirmation(text):
        join_name = extract_join_name(text)
        reply_id = event.reply_to_msg_id; confirmed_ally_id = None
        if reply_id:
            try:
                replied = await event.client.get_messages(chat_id, ids=reply_id)
                if replied and replied.sender_id: confirmed_ally_id = replied.sender_id
            except: pass
        if confirmed_ally_id == user_id:
            c = get_chat_battle(chat_id)
            if str(user_id) in c.get("ally_cooldowns", {}): del c["ally_cooldowns"][str(user_id)]
            c.setdefault("ally_join_status", {})[str(user_id)] = True
            save_battle()
            recent_ally_joins.pop((chat_id, user_id), None)
        if confirmed_ally_id and join_name:
            cc = get_chat_battle(chat_id)
            if str(confirmed_ally_id) in cc["allies"]:
                cc["ally_nicknames"][str(confirmed_ally_id)] = join_name
                save_battle()
        if am_commander:
            clear_expired_ally_cooldowns(chat_id)
            still_waiting = get_max_ally_cooldown_remaining(chat_id)
            cinfo = get_chat_battle(chat_id)["commanders"].get(str(user_id), {})
            last_code = cinfo.get("last_code", "")
            if last_code and still_waiting == 0 and cinfo.get("state") == "waiting_start":
                _cancel_old_task((int(user_id), int(chat_id), "start_battle"))
                schedule_start_battle(user_id, chat_id, last_code, 10)
        return
    if am_ally and is_cooldown_message(text):
        key = (chat_id, user_id)
        if key in recent_ally_joins and time.time() - recent_ally_joins[key] < 180:
            cooldown = parse_persian_duration(text)
            if cooldown and cooldown > 5: set_ally_cooldown(chat_id, user_id, cooldown)
        return
    if am_commander:
        c = get_chat_battle(chat_id); cinfo = c["commanders"].get(str(user_id))
        if not cinfo: return
        if not cinfo.get("nickname") and not cinfo.get("nickname_manual") and is_alert_message(text):
            alert_name = extract_alert_name(text)
            if alert_name:
                now = time.time()
                other_recent = [(uid, ts) for (cid, uid), ts in recent_farakhans.items()
                                if cid == chat_id and uid != user_id and (now - ts) < 180]
                if not other_recent:
                    cinfo["nickname"] = alert_name; cinfo["nickname_manual"] = False
                else:
                    matched = False
                    for ouid, _ in other_recent:
                        oinfo = c["commanders"].get(str(ouid), {})
                        onick = oinfo.get("nickname", "")
                        if onick and onick in alert_name: matched = True; break
                    if not matched:
                        cinfo["nickname"] = alert_name; cinfo["nickname_manual"] = False
        auto_on = cinfo.get("auto_enabled", True)
        if is_cooldown_message(text):
            cooldown = parse_persian_duration(text)
            if cooldown and cooldown > 5:
                clear_expired_ally_cooldowns(chat_id)
                total_cd = max(cooldown, get_max_ally_cooldown_remaining(chat_id))
                cinfo["cooldown_seconds"] = cooldown
                cinfo["next_farakhans_at"] = (datetime.now() + timedelta(seconds=total_cd + 15)).isoformat()
                cinfo["state"] = "waiting_cooldown"; cinfo["city_retry_count"] = 0
                c["commanders"][str(user_id)] = cinfo; save_battle()
                await _notify_user(user_id, f"⏱ کول‌داون\n⏳ فراخوان بعدی: {format_countdown(total_cd + 15)}")
                if auto_on: schedule_farakhans(user_id, chat_id, total_cd + 15)
                return
        if is_alert_message(text):
            code = extract_start_code(text); floor = extract_floor_number(text)
            prev_state = cinfo.get("state")
            if code: cinfo["last_code"] = code
            if floor: cinfo["floor"] = floor
            cinfo["last_alert"] = datetime.now().isoformat()
            cinfo["state"] = "waiting_start"
            cinfo["next_farakhans_at"] = ""; cinfo["cooldown_seconds"] = 0
            cinfo["city_retry_count"] = 0; cinfo["start_attempts"] = 0
            c["commanders"][str(user_id)] = cinfo
            if prev_state != "waiting_start":
                for aid in list(c.get("allies", {}).keys()):
                    c.setdefault("ally_join_status", {})[aid] = False
                c["ally_max_floor"] = {}
                c["commander_floor_change_for"] = ""
            save_battle()
            await _notify_user(user_id, f"🚨 اعلان قرمز\n🔑 {code or '؟'}\n🏰 {floor or '؟'}")
            if auto_on and code: schedule_start_battle(user_id, chat_id, code, 240)
            return
        if is_battle_result(text):
            cinfo["state"] = "idle"; cinfo["next_farakhans_at"] = ""
            cinfo["cooldown_seconds"] = 0; cinfo["city_retry_count"] = 0
            cinfo["start_attempts"] = 0
            c["commanders"][str(user_id)] = cinfo
            c["ally_cooldowns"] = {}
            c["commander_floor_change_for"] = ""
            save_battle()
            await _notify_user(user_id, "✅ فتح شد\n🔄 همه پراکنده می‌شن...")
            _spawn(scatter_all_allies_of_commander(chat_id, user_id, True))
            if auto_on: schedule_auto_farakhans(user_id, chat_id, 15)
            return
    if am_ally and is_alert_message(text):
        c = get_chat_battle(chat_id)
        commander_info = c["commanders"].get(str(ally_commander_id), {})
        commander_nick = (commander_info.get("nickname") or "").strip()
        player_name = extract_alert_name(text)
        my_commander_recent = (chat_id, int(ally_commander_id)) in recent_farakhans and \
                              (time.time() - recent_farakhans[(chat_id, int(ally_commander_id))] < 180)
        all_recent = [uid for (cid, uid), ts in recent_farakhans.items() if cid == chat_id and time.time() - ts < 180]
        if len(all_recent) > 1:
            if commander_nick:
                if not player_name or commander_nick not in player_name: return
            elif not my_commander_recent: return
        else:
            if commander_nick:
                if not player_name or commander_nick not in player_name: return
            elif not my_commander_recent: return
        code = extract_join_code(text); floor = extract_floor_number(text)
        if code: _spawn(ally_prepare_for_battle(user_id, chat_id, code, floor or 0))

def make_battle_handler(user_id):
    async def battle_handler(event):
        try: await battle_incoming_handler(event, user_id)
        except Exception as e: log_error(f"battle_handler {user_id}: {_translate_bot_errors(e)}")
    return battle_handler

# ═══════════════════════════════════════════════════════
# پنل‌های متنی
# ═══════════════════════════════════════════════════════
async def panel_main(event, user_id):
    name = users_db["users"].get(str(user_id), {}).get("name", "کاربر")[:20]
    up = int(time.time() - STATS_START_TIME)
    d, rem = divmod(up, 86400); h, rem = divmod(rem, 3600); m, _ = divmod(rem, 60)
    if d: up_str = f"{d}d {h}h"
    elif h: up_str = f"{h}h {m}m"
    else: up_str = f"{m}m"
    lines = []
    lines.append("╔══════════════════╗")
    lines.append("║  🎛  پنل سلف‌بات  ║")
    lines.append("╚══════════════════╝")
    lines.append("")
    lines.append(f"👤 <b>{name}</b>  ·  <code>{user_id}</code>")
    lines.append(f"⏱ آپ‌تایم: <b>{up_str}</b>  ·  🐍 {sys.version.split()[0]}")
    lines.append("")
    lines.append(_p_sep())
    lines.append("  🎯 <b>پنل‌ها:</b>")
    lines.append(_p_sep())
    lines.append("")
    lines.append(f"  🎮  <code>{CMD}پنل بازی</code>")
    lines.append("       <i>کاردینال · پونی · پیو</i>")
    lines.append("")
    lines.append(f"  📢  <code>{CMD}پنل تبچی</code>")
    lines.append("       <i>پیام خودکار تو گروه‌ها</i>")
    lines.append("")
    lines.append(f"  📊  <code>{CMD}وضعیت</code>")
    lines.append("       <i>خلاصه وضعیت همه فیچرها</i>")
    lines.append("")
    lines.append(_p_sep())
    lines.append("  📚 <b>راهنماها:</b>")
    lines.append(_p_sep())
    lines.append(f"  <code>{CMD}راهنما تبچی</code>  ·  <code>{CMD}راهنما پونی</code>")
    lines.append(f"  <code>{CMD}راهنما کاردینال</code>")
    if is_grp_owner(user_id):
        lines.append("")
        lines.append(_p_sep())
        lines.append("  👑 <b>بخش مالک:</b>")
        lines.append(_p_sep())
        lines.append(f"  <code>{CMD}کاربران</code>  ·  <code>{CMD}ویژه</code>  ·  <code>{CMD}پیام همگانی</code>")
        lines.append(f"  <code>{CMD}پینگ</code>  ·  <code>{CMD}تحریم &lt;id&gt;</code>")
    await safe_edit(event, "\n".join(lines), parse_mode="html")

async def panel_games(event, user_id):
    lines = []
    lines.append("╔══════════════════╗")
    lines.append("║  🎮  پنل بازی‌ها  ║")
    lines.append("╚══════════════════╝")
    lines.append("")
    lines.append("  👇 یکی رو انتخاب کن:")
    lines.append("")
    lines.append(f"  ⚔️  <code>{CMD}پنل کاردینال</code>")
    lines.append("       <i>فروش · شکار · فرار · جایزه · انتقال · نبرد</i>")
    lines.append("")
    lines.append(f"  🐴  <code>{CMD}پنل پونی</code>")
    lines.append("       <i>پونی · ارتقا · دانجن</i>")
    lines.append("")
    lines.append(f"  🔫  <code>{CMD}پنل پیو</code>")
    lines.append("       <i>رینگ · هدف · سگ · فن‌آرت</i>")
    lines.append("")
    lines.append(_p_foot())
    await safe_edit(event, "\n".join(lines), parse_mode="html")

async def panel_cardinal(event, user_id):
    sell_on = user_id in sell_mode_users and sell_mode_users[user_id].get("enabled")
    esc_on = is_escape_enabled(user_id)
    ret_on = is_return_enabled(user_id)
    gift_on = daily_gift_status.get(user_id, False)
    shkar_on = auto_send_status.get(user_id, {}).get("شکار", False)
    siah_on = auto_send_status.get(user_id, {}).get("سیاه", False)
    tcfg = transfer_configs.get(user_id, {})
    transfer_on = tcfg.get("enabled", False)
    ft_on = is_floor_test_enabled(user_id)
    ft_max = get_max_fails(user_id)
    no_sell = get_no_sell_list(user_id)
    lines = []
    lines.append("╔══════════════════╗")
    lines.append("║  ⚔️  پنل کاردینال  ║")
    lines.append("╚══════════════════╝")
    lines.append("")
    lines.append(_p_status_line("💰 فروش خودکار", sell_on,
        extra=f"نفروش: {len(no_sell)}", hint=f"{CMD}فروش روشن"))
    lines.append(f"     📋 <code>{CMD}نفروش &lt;اسم&gt;</code> · <code>{CMD}لیست نفروش</code>")
    lines.append("")
    lines.append("  🎯 <b>ارسال خودکار:</b>")
    lines.append(_p_status_line("🎯 شکار", shkar_on, hint=f"{CMD}شکار روشن"))
    lines.append(_p_status_line("💀 سیاه‌چال", siah_on, hint=f"{CMD}سیاه روشن"))
    lines.append("")
    lines.append("  🏃 <b>واکنش‌های خودکار:</b>")
    lines.append(_p_status_line("🏃 فرار", esc_on, hint=f"{CMD}فرار روشن"))
    lines.append(_p_status_line("🔙 برگشت", ret_on, hint=f"{CMD}برگشت روشن"))
    lines.append("")
    lines.append(_p_status_line("🎁 جایزه روزانه", gift_on, hint=f"{CMD}جایزه روشن"))
    lines.append("")
    c_id = tcfg.get("c_id", "—")
    desired = tcfg.get("desired", 0)
    extra = f"→ {c_id} ({desired:,})" if tcfg.get("c_id") else ""
    lines.append(_p_status_line("💸 انتقال خودکار", transfer_on, extra=extra, hint=f"{CMD}انتقال روشن"))
    lines.append(f"     📋 <code>{CMD}انتقال تنظیم &lt;C_ID&gt; &lt;مبلغ&gt;</code>")
    lines.append("")
    lines.append(_p_status_line("🏰 جابه‌جایی خودکار", ft_on, extra=f"مرگ: {ft_max}", hint=f"{CMD}طبقات روشن"))
    lines.append(f"     📋 <code>{CMD}طبقات</code> · <code>{CMD}مرگ &lt;عدد&gt;</code> · <code>{CMD}تست طبقه &lt;شماره&gt;</code>")
    lines.append("")
    lines.append(_p_sep())
    lines.append("  ⚔️ <b>نبرد (تو گروه مقصد):</b>")
    lines.append(_p_sep())
    lines.append(f"  👑 <code>{CMD}فرمانده</code>  ·  <code>{CMD}فراخوان</code>")
    lines.append(f"  🤝 ریپلای + <code>{CMD}یار</code>  ·  <code>{CMD}یار خارج</code>")
    lines.append(f"  🎯 <code>{CMD}همه طبقه &lt;شماره&gt;</code>  ·  <code>{CMD}همه پراکندگی</code>")
    lines.append(f"  🛡 <code>{CMD}دفاع تیمی &lt;شماره&gt;</code>")
    lines.append(f"  📖 <code>{CMD}راهنما کاردینال</code>  →  آموزش کامل")
    lines.append("")
    mat_on = transfer_materials_config.get(user_id, {}).get("enabled", False)
    mat_rules = len(transfer_materials_config.get(user_id, {}).get("rules", []))
    lines.append("")
    mat_on = transfer_materials_config.get(user_id, {}).get("enabled", False)
    mat_rules = len(transfer_materials_config.get(user_id, {}).get("rules", []))
    lines.append("")

    lines.append("")
    lines.append("  📦 <b>انتقال مواد اولیه:</b>")
    mat_on = transfer_materials_config.get(user_id, {}).get("enabled", False)
    mat_rules = len(transfer_materials_config.get(user_id, {}).get("rules", []))
    toggle_hint = f"{CMD}انتقال مواد {'خاموش' if mat_on else 'روشن'}"
    lines.append(_p_status_line("📦 انتقال مواد", mat_on, extra=f"قوانین: {mat_rules}"))
    lines.append(f"     💡 <code>{toggle_hint}</code>  ·  <code>{CMD}لیست انتقال مواد</code>")
    lines.append(f"     📋 <code>{CMD}افزودن انتقال مواد &lt;آیدی بازی&gt; &lt;اسم ماده&gt; &lt;تعداد&gt;</code>")
    lines.append(f"     📋 <code>{CMD}حذف انتقال مواد &lt;آیدی&gt; &lt;اسم ماده&gt;</code>")

    lines.append("")
    lines.append("  🎁 <b>انتقال کالا/آیتم:</b>")
    item_on = transfer_items_config.get(user_id, {}).get("enabled", False)
    item_rules = len(transfer_items_config.get(user_id, {}).get("rules", []))
    toggle_hint_item = f"{CMD}انتقال کالا {'خاموش' if item_on else 'روشن'}"
    lines.append(_p_status_line("🎁 انتقال کالا", item_on, extra=f"قوانین: {item_rules}"))
    lines.append(f"     💡 <code>{toggle_hint_item}</code>  ·  <code>{CMD}لیست انتقال کالا</code>")
    lines.append(f"     📋 <code>{CMD}افزودن انتقال کالا &lt;آیدی بازی&gt; &lt;اسم کالا&gt; &lt;تعداد&gt;</code>")
    lines.append(f"     📋 <code>{CMD}حذف انتقال کالا &lt;آیدی&gt; &lt;اسم کالا&gt;</code>")
    
    lines.append(_p_foot())



    await safe_edit(event, "\n".join(lines), parse_mode="html")

async def panel_banner(event, user_id):
    lines = []
    lines.append("╔══════════════════╗")
    lines.append("║  📢  پنل تبچی خودکار  ║")
    lines.append("╚══════════════════╝")
    lines.append("")
    lines.append(_p_sep())
    lines.append("  🎯 <b>مدیریت بنر:</b>")
    lines.append(_p_sep())
    lines.append(f"  ▸ <code>{CMD}تبچی افزودن &lt;نام&gt;</code> + ریپلای")
    lines.append(f"  ▸ <code>{CMD}تبچی افزودن &lt;نام&gt; فوروارد</code>")
    lines.append(f"  ▸ <code>{CMD}تبچی اطلاعات &lt;نام&gt;</code>")
    lines.append(f"  ▸ <code>{CMD}تبچی حذف &lt;نام&gt;</code>")
    lines.append(f"  ▸ <code>{CMD}تبچی لیست</code>")
    lines.append("")
    lines.append(_p_sep())
    lines.append("  ⚙️ <b>تنظیمات:</b>")
    lines.append(_p_sep())
    lines.append(f"  ▸ <code>{CMD}تبچی هدف &lt;نام&gt;</code>")
    lines.append(f"  ▸ <code>{CMD}تبچی بازه &lt;نام&gt; &lt;مدت&gt;</code>")
    lines.append("     <i>(s=ثانیه · m=دقیقه · h=ساعت · d=روز)</i>")
    lines.append(f"  ▸ <code>{CMD}تبچی ریپلای &lt;نام&gt;</code> + ریپلای")
    lines.append("")
    lines.append(_p_sep())
    lines.append("  ▶️ <b>کنترل:</b>")
    lines.append(_p_sep())
    lines.append(f"  ▸ <code>{CMD}تبچی روشن &lt;نام&gt;</code>")
    lines.append(f"  ▸ <code>{CMD}تبچی خاموش &lt;نام&gt;</code>")
    lines.append(f"  ▸ <code>{CMD}تبچی ارسال &lt;نام&gt;</code>  →  فوری")
    lines.append("")
    lines.append("  💡 <i>راهنمای کامل: ." + CMD + "راهنما تبچی</i>")
    await safe_edit(event, "\n".join(lines), parse_mode="html")

async def panel_help_banner(event):
    lines = []
    lines.append("╔══════════════════╗")
    lines.append("║  📚  راهنمای تبچی  ║")
    lines.append("╚══════════════════╝")
    lines.append("")
    lines.append("  📝 <b>قدم به قدم:</b>")
    lines.append(_p_sep())
    lines.append("")
    lines.append("  <b>1️⃣ ساخت بنر:</b>")
    lines.append("     روی پیام مورد نظر ریپلای کن و بزن:")
    lines.append(f"     <code>{CMD}تبچی افزودن پونی</code>")
    lines.append("")
    lines.append("  <b>2️⃣ انتخاب گروه‌های مقصد:</b>")
    lines.append("     تو هر گروه بزن:")
    lines.append(f"     <code>{CMD}تبچی هدف پونی</code>")
    lines.append("")
    lines.append("  <b>3️⃣ تعیین بازه:</b>")
    lines.append(f"     <code>{CMD}تبچی بازه پونی 10m</code>")
    lines.append("     <i>(هر ۱۰ دقیقه یه بار بفرست)</i>")
    lines.append("")
    lines.append("  <b>4️⃣ روشن کردن:</b>")
    lines.append(f"     <code>{CMD}تبچی روشن پونی</code>")
    lines.append("")
    lines.append(_p_sep())
    lines.append("  🔥 <b>ریپلای کردن (اختیاری):</b>")
    lines.append("     تو گروه مقصد روی یه پیام ریپلای کن:")
    lines.append(f"     <code>{CMD}تبچی ریپلای پونی</code>")
    lines.append("")
    lines.append("  ⚡ <i>فوروارد به‌جای کپی:</i>")
    lines.append(f"     <code>{CMD}تبچی افزودن پونی فوروارد</code>")
    await safe_edit(event, "\n".join(lines), parse_mode="html")

async def panel_help_ghunt(event):
    lines = []
    lines.append("╔══════════════════╗")
    lines.append("║  📚  راهنمای شکار گروهی  ║")
    lines.append("╚══════════════════╝")
    lines.append("")
    lines.append("  🛡 <b>شکار گروهی چیه؟</b>")
    lines.append(_p_sep())
    lines.append("  • می‌تونی یه گروه بسازی و بقیه ملحق بشن")
    lines.append("  • وقتی یکی می‌نویسه <code>شلیک</code> یا <code>پیو هیل</code>")
    lines.append("  • بقیه اعضا هم دقیقاً همون پیام رو می‌فرستن")
    lines.append("")
    lines.append("  🎯 <b>دستورات:</b>")
    lines.append(_p_sep())
    lines.append(f"  ▸ <code>{CMD}شکار گروهی روشن</code>")
    lines.append(f"  ▸ <code>{CMD}شکار گروهی خاموش</code>")
    lines.append(f"  ▸ <code>{CMD}شکار گروهی وضعیت</code>")
    lines.append("")
    lines.append("  ⚙️ <b>مدیریت (سازنده):</b>")
    lines.append(_p_sep())
    lines.append("  • اخراج عضو")
    lines.append("  • انتقال سازندگی")
    lines.append("  • منحل کردن گروه")
    lines.append("")
    lines.append("  💡 <i>همه چیز از پنل شیشه‌ای هم قابل دسترسیه</i>")
    await safe_edit(event, "\n".join(lines), parse_mode="html")

async def panel_help_pony(event):
    lines = []
    lines.append("╔══════════════════╗")
    lines.append("║  📚  راهنمای پونی  ║")
    lines.append("╚══════════════════╝")
    lines.append("")
    lines.append("  🐴 <b>پونی خودکار:</b>")
    lines.append(_p_sep())
    lines.append("  • ربات خودش هر ۱ دقیقه پیام پونی رو چک می‌کنه")
    lines.append("  • اولین بار که پونی ۱۰۰٪ شد، زمانش رو یاد می‌گیره")
    lines.append("  • از این به بعد سر وقت می‌فرسته")
    lines.append("")
    lines.append("  ⬆️ <b>ارتقای خودکار:</b>")
    lines.append(_p_sep())
    lines.append("  • وقتی موجودی کافی شد، خودکار ارتقا می‌ده")
    lines.append("  • اگه پونی به آخرین سطح رسید، بهت خبر می‌ده")
    lines.append("")
    lines.append("  🏰 <b>دانجن:</b>")
    lines.append(_p_sep())
    lines.append("  • هر ۱۵ دقیقه یه بار می‌زنه")
    lines.append("  • اول از قوی‌ترین، اگه باخت → ضعیف‌تر")
    lines.append("  • اگه برد → می‌مونه رو همون")
    lines.append("")
    lines.append("  🎯 <b>شروع سریع:</b>")
    lines.append(f"  ▸ <code>{CMD}پونی روشن</code>")
    lines.append(f"  ▸ <code>{CMD}ارتقا روشن</code>")
    lines.append(f"  ▸ <code>{CMD}دانجن روشن</code>")
    await safe_edit(event, "\n".join(lines), parse_mode="html")

async def panel_help_cardinal(event):
    lines = []
    lines.append("╔══════════════════╗")
    lines.append("║  📚  راهنمای کاردینال  ║")
    lines.append("╚══════════════════╝")
    lines.append("")
    lines.append("  🚪 <b>شهر و موقعیت:</b>")
    lines.append(_p_sep())
    lines.append("  • 🏰 خروج از شهر! → بیرون شهر")
    lines.append("  • 🏰 بازگشت به شهر → داخل")
    lines.append("  • 🪶 اطلاعات من → طبقه و مرز")
    lines.append("  • 🌀 تلپورت به طبقات → جابه‌جایی")
    lines.append("")
    lines.append("  🦖 <b>شکار و نبرد:</b>")
    lines.append(_p_sep())
    lines.append("  • 🦖 شکار هیولا → شکار عادی")
    lines.append("  • 💀 سیاه‌چال مخفی → شکار دانجن")
    lines.append("  • ⚔️ فراخوان فتح طبقه → نبرد تیمی")
    lines.append("  • ⚔️ آغاز نبرد &lt;کد&gt;")
    lines.append("  • 🔗 ملحق &lt;کد&gt;")
    lines.append("")
    lines.append("  💰 <b>پول:</b>")
    lines.append(_p_sep())
    lines.append("  • ⚖️ فروشگاه شهر → باز کردن")
    lines.append("  • 💰 فروش آیتم → فروش")
    lines.append("  • 💸 انتقال سکه → به بازیکن دیگه")
    lines.append("  • 🎁 جوایز روزانه → جایزه روزانه")
    lines.append("")
    lines.append("  💎 <b>کریستال:</b>")
    lines.append(_p_sep())
    lines.append("  • 💎 استفاده از کریستال تلپورت اجباری")
    lines.append("    <i>(وقتی نمی‌تونی برگردی شهر)</i>")
    await safe_edit(event, "\n".join(lines), parse_mode="html")

async def panel_pony_text(event, user_id):
    cfg = get_pony_cfg(user_id, event.chat_id)
    dcfg = get_dungeon_cfg(user_id, event.chat_id)
    d_on = dcfg.get("enabled", False)
    d_idx = dcfg.get("current_idx", 0); w_idx = dcfg.get("working_idx", -1)
    d_cur = DUNGEON_MONSTERS[d_idx] if 0 <= d_idx < len(DUNGEON_MONSTERS) else "—"
    d_work = DUNGEON_MONSTERS[w_idx] if 0 <= w_idx < len(DUNGEON_MONSTERS) else "—"
    testing = dcfg.get("test_mode", False)
    p_on = cfg.get("collect", False)
    u_on = cfg.get("upgrade", False)
    lines = []
    lines.append("╔══════════════════╗")
    lines.append("║  🐴  پنل پونی و دانجن  ║")
    lines.append("╚══════════════════╝")
    lines.append("")
    lines.append(_p_status_line("🐴 پونی", p_on, hint=f"{CMD}پونی روشن"))
    lines.append(_p_status_line("⬆️ ارتقای خودکار", u_on, hint=f"{CMD}ارتقا روشن"))
    lines.append(_p_status_line("🏰 دانجن", d_on, extra="در حال تست" if testing else "", hint=f"{CMD}دانجن روشن"))
    lines.append(_p_sep())
    lines.append("")
    lines.append("  🎯 <b>کنترل:</b>")
    lines.append(f"  ▸ <code>{CMD}پونی روشن</code>  /  <code>{CMD}پونی خاموش</code>")
    lines.append(f"  ▸ <code>{CMD}ارتقا روشن</code>  /  <code>{CMD}ارتقا خاموش</code>")
    lines.append(f"  ▸ <code>{CMD}دانجن روشن</code>  /  <code>{CMD}دانجن خاموش</code>")
    lines.append(f"  ▸ <code>{CMD}دانجن تست</code>  →  ریست از قوی‌ترین")
    lines.append("")
    lines.append(_p_sep())
    lines.append("  📊 <b>وضعیت دانجن:</b>")
    lines.append(f"  🎯 الان: <b>{d_cur}</b>")
    lines.append(f"  🏆 انتخاب‌شده: <b>{d_work}</b>")
    await safe_edit(event, "\n".join(lines), parse_mode="html")

async def panel_pew_text(event, user_id):
    art_on = is_pew_art_enabled(user_id)
    ring_c = sum(1 for k, v in pew_ring_config.items() if k[0] == int(user_id) and v.get("enabled"))
    ring_t = sum(1 for k in pew_ring_config if k[0] == int(user_id))
    tgt_c = sum(1 for k, v in pew_target_config.items() if k[0] == int(user_id) and v.get("enabled"))
    tgt_t = sum(1 for k in pew_target_config if k[0] == int(user_id))
    dog_c = sum(1 for k, v in pew_dog_config.items() if k[0] == int(user_id) and v.get("enabled"))
    dog_t = sum(1 for k in pew_dog_config if k[0] == int(user_id))
    lines = []
    lines.append("╔══════════════════╗")
    lines.append("║  🔫  پنل پیو پیو  ║")
    lines.append("╚══════════════════╝")
    lines.append("")
    lines.append(_p_status_line("🎨 فن‌آرت", art_on, hint="از پنل شیشه‌ای روشن"))
    lines.append(_p_status_line("🏋️ پیو رینگ", ring_c > 0, extra=f"{ring_c}/{ring_t} گروه", hint="از پنل شیشه‌ای"))
    lines.append(_p_status_line("🎯 پیو هدف", tgt_c > 0, extra=f"{tgt_c}/{tgt_t} هدف", hint="از پنل شیشه‌ای"))
    lines.append(_p_status_line("🐕 پیو سگ", dog_c > 0, extra=f"{dog_c}/{dog_t} گروه", hint="از پنل شیشه‌ای"))
    lines.append("")
    lines.append(_p_foot())
    lines.append(f"  💡 همه‌ی تنظیمات از پنل شیشه‌ای <code>{CMD}پنل</code>")
    await safe_edit(event, "\n".join(lines), parse_mode="html")

async def panel_tools(event, user_id):
    u = users_db["users"].get(str(user_id), {})
    html_on = u.get("html_style_on", False)
    font_on = u.get("font_on", False)
    html_cur = HTML_STYLES.get(u.get("html_style", "bold"), HTML_STYLES["bold"])["label"]
    font_cur = ENGLISH_FONTS.get(u.get("font", "none"), ENGLISH_FONTS["none"])["label"]
    lines = []
    lines.append("╔══════════════════╗")
    lines.append("║  🛠  پنل ابزارها  ║")
    lines.append("╚══════════════════╝")
    lines.append("")
    lines.append(_p_status_line("🎨 استایل HTML", html_on, extra=html_cur, hint=f"{CMD}استایل روشن"))
    lines.append(_p_status_line("🔤 فونت انگلیسی", font_on, extra=font_cur, hint=f"{CMD}فونت روشن"))
    lines.append("")
    lines.append(_p_sep())
    lines.append("  🎯 <b>کنترل استایل:</b>")
    lines.append(f"  ▸ <code>{CMD}استایل روشن</code>  /  <code>{CMD}استایل خاموش</code>")
    lines.append(f"  ▸ <code>{CMD}پنل استایل</code>  →  انتخاب استایل")
    lines.append("")
    lines.append("  🎯 <b>کنترل فونت:</b>")
    lines.append(f"  ▸ <code>{CMD}فونت روشن</code>  /  <code>{CMD}فونت خاموش</code>")
    lines.append(f"  ▸ <code>{CMD}پنل فونت</code>  →  انتخاب فونت")
    lines.append("")
    if is_media_allowed(user_id):
        ttl_cfg = get_ttl_config(user_id)
        ttl_target = "پیام‌های ذخیره شده" if ttl_cfg["target"] == "me" else str(ttl_cfg["target"])
        lines.append(_p_sep())
        lines.append("  🔥 <b>TTL (رسانه ناپدیدشونده):</b>")
        lines.append(_p_status_line("ذخیره خودکار", ttl_cfg["enabled"], hint=f"{CMD}تی تی ال روشن"))
        lines.append(f"     🎯 مقصد: <code>{ttl_target}</code>")
        lines.append(f"  ▸ <code>{CMD}تی تی ال</code>  →  مشاهده")
        lines.append(f"  ▸ <code>{CMD}تی تی ال روشن</code>  /  خاموش")
        lines.append(f"  ▸ <code>{CMD}تی تی ال هدف</code>  →  تنظیم مقصد")
        lines.append("")
        lines.append(_p_sep())
        lines.append("  📥 <b>ذخیره رسانه:</b>")
        lines.append(f"  ▸ <code>{CMD}ذخیره &lt;لینک&gt;</code>  →  دانلود از لینک")
        lines.append(f"  ▸ ریپلای روی پیام + <code>{CMD}ذخیره</code>")
        lines.append("  ▸ ذخیره می‌شه تو: <b>پیام‌های ذخیره شده</b>")
        lines.append("")
    lines.append(_p_foot())
    lines.append(f"  💡 از پنل شیشه‌ای هم: <code>{CMD}پنل</code> → ابزارها")
    await safe_edit(event, "\n".join(lines), parse_mode="html")

async def panel_html_text(event, user_id):
    u = users_db["users"].get(str(user_id), {})
    on = u.get("html_style_on", False)
    cur = u.get("html_style", "bold")
    lines = []
    lines.append("╔══════════════════╗")
    lines.append("║  🎨  پنل استایل HTML  ║")
    lines.append("╚══════════════════╝")
    lines.append("")
    lines.append(_p_status_line("🎨 استایل", on, extra=HTML_STYLES[cur]["label"]))
    lines.append("")
    lines.append(_p_sep())
    lines.append("  🎯 <b>کنترل:</b>")
    lines.append(f"  ▸ <code>{CMD}استایل روشن</code>")
    lines.append(f"  ▸ <code>{CMD}استایل خاموش</code>")
    lines.append("")
    lines.append(_p_sep())
    lines.append("  📋 <b>انتخاب استایل:</b> هر بار فقط یک استایل فعال است.")
    lines.append(f"  ▸ برای انتخاب، بنویس: <code>{CMD}استایل &lt;نام استایل&gt;</code>؛ فارسی یا انگلیسی.")
    lines.append("  ▸ از آن به بعد پیام عادی‌ات ویرایش می‌شود و استایل می‌گیرد.")
    lines.append("")
    for key, s in HTML_STYLES.items():
        if key in ("none", "pre"): continue  # خاموشی دکمهٔ جدا دارد؛ pre هم نام قدیمی است.
        mark = "✅" if key == cur else "▫️"
        sample = "سلام" if key == "kashida" else "Sample"
        preview = f"{s['open']}{html_lib.escape(sample)}{s['close']}" if s["open"] else _preview_style_text(key, sample)
        key_preview = _preview_style_text(key, sample)
        aliases = STYLE_ALIASES.get(key, [])
        fa_name = aliases[0] if aliases else ""
        lines.append(f"  {mark} <code>{CMD}استایل {key}</code>")
        lines.append(f"       <i>پیش‌نمایش:</i> {preview}  ·  {key_preview}")
        if fa_name:
            lines.append(f"       <i>فارسی:</i> <code>{CMD}استایل {fa_name}</code>")
    lines.append("")
    lines.append(_p_foot())
    await safe_edit(event, "\n".join(lines), parse_mode="html")

async def panel_font_text(event, user_id):
    u = users_db["users"].get(str(user_id), {})
    on = u.get("font_on", False)
    cur = u.get("font", "none")
    lines = []
    lines.append("╔══════════════════╗")
    lines.append("║  🔤  پنل فونت انگلیسی  ║")
    lines.append("╚══════════════════╝")
    lines.append("")
    lines.append(_p_status_line("🔤 فونت", on, extra=ENGLISH_FONTS[cur]["label"]))
    lines.append("")
    lines.append(_p_sep())
    lines.append("  🎯 <b>کنترل:</b>")
    lines.append(f"  ▸ <code>{CMD}فونت روشن</code>")
    lines.append(f"  ▸ <code>{CMD}فونت خاموش</code>")
    lines.append("")
    lines.append(_p_sep())
    lines.append("  📋 <b>انتخاب فونت:</b>  <i>(هر فونت با خودش)</i>")
    lines.append("")
    for key, s in ENGLISH_FONTS.items():
        mark = "✅" if key == cur else "▫️"
        key_preview = _preview_font_text(key, key)
        sample_en = _preview_font_text(key, "Sample") if key != "none" else "Sample"
        lines.append(f"  {mark} <code>{CMD}فونت {key}</code>  →  <b>{key_preview}</b>")
        lines.append(f"       <i>نمونه:</i> {sample_en}")
        aliases = FONT_ALIASES.get(key, [])
        if aliases:
            lines.append(f"       <i>فارسی:</i> <code>{aliases[0]}</code>")
    lines.append("")
    lines.append(_p_foot())
    await safe_edit(event, "\n".join(lines), parse_mode="html")

async def panel_status(event, user_id):
    chat_id = event.chat_id
    c = get_chat_battle(chat_id)
    lines = []
    lines.append("╔══════════════════╗")
    lines.append("║  📊  وضعیت این چت  ║")
    lines.append("╚══════════════════╝")
    lines.append("")
    is_here_commander = str(user_id) in c["commanders"]
    ally_of = c["allies"].get(str(user_id))
    ally_nicks = c.get("ally_nicknames", {})
    if is_here_commander:
        cinfo = c["commanders"][str(user_id)]
        lines.append("  👑 <b>فرمانده این چت</b>")
        lines.append(_p_sep())
        nick = cinfo.get("nickname") or ""
        if nick: lines.append(f"  🎮 نام بازی: <b>{nick}</b>")
        floor = cinfo.get("floor", 0)
        if floor: lines.append(f"  🏰 طبقه هدف: <b>{floor}</b>")
        code = cinfo.get("last_code") or ""
        if code: lines.append(f"  🔑 کد آخر: <code>{code}</code>")
        if cinfo.get("state") == "paused_by_user":
            lines.append("  🔴 فتح: خاموش")
        else:
            auto_on = cinfo.get("auto_enabled", True)
            if not auto_on: lines.append("  🟡 اتو: خاموش")
            else:
                t = get_time_until_next(cinfo)
                if t is not None and t > 0:
                    lines.append(f"  ⏳ تا فراخوان بعدی: <b>{format_countdown(t)}</b>")
                elif cinfo.get("state") == "waiting_start":
                    lines.append("  ⏳ در انتظار آغاز...")
        allies = [(aid, cmid) for aid, cmid in c["allies"].items() if str(cmid) == str(user_id)]
        lines.append("")
        if allies:
            lines.append(f"  🤝 <b>یارها ({len(allies)}/{MAX_ALLIES_PER_TEAM}):</b>")
            for aid, _ in allies:
                name = await get_plain_name(event.client, int(aid))
                joined = "🟢" if c.get("ally_join_status", {}).get(str(aid), False) else "🔴"
                gname = ally_nicks.get(str(aid), "")
                extra = f" · 🎮 {gname}" if gname else ""
                lines.append(f"     {joined} {name}{extra}")
        else:
            lines.append("  🤝 یار: خالی")
    elif ally_of:
        cinfo = c["commanders"].get(str(ally_of), {})
        is_orphan = str(ally_of) in c.get("orphan_teams", {})
        if is_orphan:
            lines.append("  🤝 <b>یار تیم رهاشده</b>")
            lines.append("")
            lines.append(f"  💡 <code>{CMD}فرمانده</code> بزن تا فرمانده بشی.")
        else:
            cm_name = await get_plain_name(event.client, int(ally_of))
            lines.append(f"  🤝 <b>یار {cm_name}</b>")
            lines.append(f"  🆔 فرمانده: <code>{ally_of}</code>")
    else:
        lines.append("  📭 تو تو این چت نقشی نداری")
        lines.append(f"  🆔 آیدی: <code>{user_id}</code>")
        lines.append("")
        lines.append(f"  💡 <code>{CMD}فرمانده</code> بزن یا ریپلای + <code>{CMD}یار</code>")
    await safe_edit(event, "\n".join(lines), parse_mode="html")

async def panel_status_private(event, user_id):
    lines = []
    lines.append("╔══════════════════╗")
    lines.append("║  📊  وضعیت کلی شما  ║")
    lines.append("╚══════════════════╝")
    lines.append("")
    sell_on = user_id in sell_mode_users and sell_mode_users[user_id].get("enabled")
    esc_on = is_escape_enabled(user_id)
    ret_on = is_return_enabled(user_id)
    gift_on = daily_gift_status.get(user_id, False)
    shkar_on = auto_send_status.get(user_id, {}).get("شکار", False)
    siah_on = auto_send_status.get(user_id, {}).get("سیاه", False)
    tcfg = transfer_configs.get(user_id, {})
    ft_on = is_floor_test_enabled(user_id)
    ft_max = get_max_fails(user_id)
    lines.append("  ⚔️ <b>کاردینال:</b>")
    lines.append(_p_sep())
    lines.append(_p_status_line("💰 فروش", sell_on))
    lines.append(_p_status_line("🎯 شکار", shkar_on))
    lines.append(_p_status_line("💀 سیاه‌چال", siah_on))
    lines.append(_p_status_line("🏃 فرار", esc_on))
    lines.append(_p_status_line("🔙 برگشت", ret_on))
    lines.append(_p_status_line("🎁 جایزه", gift_on))
    lines.append(_p_status_line("💸 انتقال", tcfg.get("enabled", False)))
    lines.append(_p_status_line("🏰 تست طبقه", ft_on, f"{ft_max} مرگ"))
    lines.append("")
    p_any = any(c.get("collect") for k, c in pony_config.items() if k[0] == int(user_id))
    d_any = any(c.get("enabled") for k, c in dungeon_config.items() if k[0] == int(user_id))
    ring_any = any(c.get("enabled") for k, c in pew_ring_config.items() if k[0] == int(user_id))
    tgt_any = any(c.get("enabled") for k, c in pew_target_config.items() if k[0] == int(user_id))
    dog_any = any(c.get("enabled") for k, c in pew_dog_config.items() if k[0] == int(user_id))
    art_any = is_pew_art_enabled(user_id)
    if p_any or d_any or ring_any or tgt_any or dog_any or art_any:
        lines.append("  🎮 <b>بازی:</b>")
        lines.append(_p_sep())
        if p_any: lines.append(_p_status_line("🐴 پونی", True))
        if d_any: lines.append(_p_status_line("🏰 دانجن", True))
        if ring_any: lines.append(_p_status_line("🏋️ پیو رینگ", True))
        if tgt_any: lines.append(_p_status_line("🎯 پیو هدف", True))
        if dog_any: lines.append(_p_status_line("🐕 پیو سگ", True))
        if art_any: lines.append(_p_status_line("🎨 پیو آرت", True))
        lines.append("")
    no_sell = get_no_sell_list(user_id)
    if no_sell:
        lines.append(f"  🚫 نفروش: <b>{len(no_sell)}</b> آیتم")
        lines.append("")
    banners = get_user_banners(user_id)
    active_b = [n for n, b in banners.items() if b.get("active")]
    if banners:
        lines.append(f"  📢 تبچی: {len(active_b)} فعال از {len(banners)}")
        lines.append("")
    lines.append(_p_foot())
    lines.append(f"  🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    await safe_edit(event, "\n".join(lines), parse_mode="html")

async def panel_ping(event, client):
    import shutil as _sh
    start = time.time()
    try:
        await client.get_me(); ping_ms = (time.time() - start) * 1000
    except: ping_ms = -1
    uptime_sec = int(time.time() - STATS_START_TIME)
    d, rem = divmod(uptime_sec, 86400); h, rem = divmod(rem, 3600); m, s = divmod(rem, 60)
    if d > 0: uptime_str = f"{d} روز و {h} ساعت"
    elif h > 0: uptime_str = f"{h} ساعت و {m} دقیقه"
    else: uptime_str = f"{m} دقیقه و {s} ثانیه"
    if ping_ms < 0: ping_icon = "❌"; ping_str = "خطا"
    elif ping_ms < 100: ping_icon = "🟢"; ping_str = f"{ping_ms:.0f} ms"
    elif ping_ms < 300: ping_icon = "🟡"; ping_str = f"{ping_ms:.0f} ms"
    else: ping_icon = "🔴"; ping_str = f"{ping_ms:.0f} ms"
    lines = []
    lines.append("╔══════════════════╗")
    lines.append("║  🏓  پینگ و وضعیت  ║")
    lines.append("╚══════════════════╝")
    lines.append("")
    lines.append(f"  {ping_icon} پینگ: <b>{ping_str}</b>")
    lines.append(f"  ⏱ آپ‌تایم: <b>{uptime_str}</b>")
    lines.append("")
    lines.append(_p_sep())
    try:
        du = _sh.disk_usage('.')
        pct = du.percent
        bar = _p_bar(pct)
        lines.append(f"  💾 دیسک:  {bar}  <b>{pct}%</b>")
    except: pass
    try:
        import psutil
        mem = psutil.virtual_memory()
        pct = mem.percent
        bar = _p_bar(pct)
        lines.append(f"  🧠 رم:    {bar}  <b>{pct}%</b>")
    except: pass
    lines.append(_p_sep())
    lines.append(f"  🐍 پایتون {sys.version.split()[0]}")
    lines.append(f"  🖥 {platform.system()}")
    await safe_edit(event, "\n".join(lines), parse_mode="html")

async def panel_owner_dashboard(event, owner_id, client):
    total_users = len(users_db["users"])
    active_users = banned = disabled = 0
    for _, info in users_db["users"].items():
        if info.get("banned"): banned += 1
        elif info.get("locally_disabled"): disabled += 1
        elif info.get("active"): active_users += 1
    sessions = list(SESSION_DIR.glob("*.session"))
    connected = sum(1 for c in user_clients.values() if c.is_connected())
    lines = []
    lines.append("╔══════════════════╗")
    lines.append("║  👑  داشبورد مالک  ║")
    lines.append("╚══════════════════╝")
    lines.append("")
    lines.append("  👥 <b>کاربران:</b>")
    lines.append(_p_sep())
    lines.append(f"  📊 کل:      <b>{total_users}</b>")
    lines.append(f"  🟢 فعال:    <b>{active_users}</b>")
    lines.append(f"  🚫 بن:      <b>{banned}</b>")
    lines.append(f"  🔇 خاموش:   <b>{disabled}</b>")
    lines.append("")
    lines.append("  💾 <b>سشن‌ها:</b>")
    lines.append(_p_sep())
    lines.append(f"  📁 موجود:   <b>{len(sessions)}</b>")
    lines.append(f"  🔗 متصل:    <b>{connected}</b>")
    lines.append("")
    lines.append("  ⚙️ <b>تسک‌های فعال:</b>")
    lines.append(_p_sep())
    lines.append(f"  💰 فروش:    <b>{len(sell_mode_users)}</b>")
    lines.append(f"  🐴 پونی:    <b>{len(pony_tasks)}</b>")
    lines.append(f"  🏰 دانجن:   <b>{len(dungeon_tasks)}</b>")
    lines.append(f"  💸 انتقال:  <b>{len(transfer_configs)}</b>")
    lines.append(f"  📢 بنر:     <b>{len(broadcast_tasks)}</b>")
    lines.append(f"  ⚔️ نبرد:    <b>{len(pending_battle_tasks)}</b>")
    lines.append("")
    lines.append(_p_foot())
    lines.append(f"  🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    await safe_edit(event, "\n".join(lines), parse_mode="html")

async def send_broadcast_to_all(owner_id, src_msg, header_text=""):
    if not bot_client: return 0, 0
    success = failed = 0
    for uid, info in list(users_db["users"].items()):
        if info.get("banned"): continue
        try:
            if src_msg.media:
                data = await src_msg.download_media(file=bytes)
                if data:
                    f = io.BytesIO(data)
                    ext = ".jpg" if src_msg.photo else ".mp4" if src_msg.video else ".ogg" if src_msg.voice else ".mp3" if src_msg.audio else ".bin"
                    f.name = f"bc_{uid}{ext}"
                    caption = src_msg.text or src_msg.raw_text or ""
                    if header_text: caption = f"{header_text}\n\n{caption}" if caption else header_text
                    try: await bot_client.send_file(int(uid), f, caption=caption, voice_note=bool(src_msg.voice), silent=True)
                    except TypeError: await bot_client.send_file(int(uid), f, caption=caption, voice_note=bool(src_msg.voice), silent=True)
                else:
                    text = src_msg.text or src_msg.raw_text or ""
                    if header_text: text = f"{header_text}\n\n{text}" if text else header_text
                    await bot_client.send_message(int(uid), text, silent=True)
            else:
                text = src_msg.text or src_msg.raw_text or ""
                if header_text: text = f"{header_text}\n\n{text}" if text else header_text
                await bot_client.send_message(int(uid), text, silent=True)
            success += 1; await asyncio.sleep(0.3)
        except FloodWaitError as e: await asyncio.sleep(e.seconds); failed += 1
        except Exception as e:
            failed += 1; log_error(f"broadcast {uid}: {_translate_bot_errors(e)}")
    return success, failed

# ═══════════════════════════════════════════════════════
# COMMAND_HINTS
# ═══════════════════════════════════════════════════════
COMMAND_HINTS = [
    "پنل", "راهنما", "بازی", "ابزارها",
    "پنل بازی", "پنل کاردینال", "کاردینال",
    "پنل پونی", "پونی",
    "پنل پیو", "پیو",
    "پنل تبچی", "تبچی",
    "پنل ابزار", "پنل ابزارها",
    "پنل فونت", "پنل استایل", "راهنمای استایل", "استایل",
    "پنل پایش", "پایش", "پایش افزودن", "پایش حذف", "لیست پایش",
    "پنل ویس", "پنل صدا", "ویس", "گوش کن",
    "پروفایل رندوم", "پروفایل رندوم روشن", "پروفایل رندوم خاموش",
    "فونت روشن", "فونت خاموش",
    "استایل روشن", "استایل خاموش",
    "تی تی ال", "تی تی ال روشن", "تی تی ال خاموش", "تی تی ال هدف",
    "ذخیره",
    "فراخوان", "فرمانده", "فرمانده خارج", "فتح خاموش",
    "یار", "یار خارج", "اخراج",
    "پونی روشن", "پونی خاموش", "ارتقا روشن", "ارتقا خاموش",
    "دانجن روشن", "دانجن خاموش", "دانجن تست",
    "فروش روشن", "فروش خاموش",
    "فرار روشن", "فرار خاموش", "برگشت روشن", "برگشت خاموش",
    "جایزه روشن", "جایزه خاموش",
    "شکار روشن", "شکار خاموش", "سیاه روشن", "سیاه خاموش",
    "وضعیت", "وضعیت نبرد", "لغو نبرد",
    "همه طبقه", "همه پراکندگی", "دفاع تیمی",
    "حمله تیمی لیست", "تبچی لیست",
    "انتقال وضعیت", "انتقال روشن", "انتقال خاموش",
    "نفروش", "لیست نفروش", "حذف نفروش",
    "راهنما تبچی", "راهنما پونی", "راهنما کاردینال",
    "طبقات", "طبقات روشن", "طبقات خاموش", "مرگ", "تست طبقه",
    "شکار گروهی روشن", "شکار گروهی خاموش", "شکار گروهی وضعیت", "راهنما شکار گروهی",
    "اجازه", "لغو اجازه", "لیست اجازه",
]

def make_user_handler(user_id):
    async def user_handler(event):
        if event.sender_id != user_id: return
        if event.is_private and event.chat_id == BOT_SELF_ID: return
        text = event.raw_text.strip() if event.raw_text else ""
        if text:
            text = re.sub(r'\s+', ' ', text).strip().replace('ي', 'ی').replace('ك', 'ک')
            if text.startswith(CMD) and len(text) > len(CMD) and text[len(CMD)] == " ":
                text = CMD + text[len(CMD):].lstrip()
        if not is_user_allowed(user_id):
            if text.startswith(CMD):
                try: await safe_edit(event, "🔒 دسترسی این حساب توسط مالک قفل شده است.")
                except: pass
            return
        if user_id in broadcast_waiting:
            if not is_grp_owner(user_id):
                broadcast_waiting.pop(user_id, None); return
            if text and text.startswith(CMD): pass
            else:
                src = await event.get_reply_message()
                if not src: src = event.message
                broadcast_waiting.pop(user_id, None)
                try:
                    await event.reply("⏳ در حال ارسال...")
                    success, failed = await send_broadcast_to_all(user_id, src, "")
                    await event.reply(f"✅ ارسال شد.\n✔️ {success}\n❌ {failed}")
                except Exception as e:
                    log_error(f"broadcast {user_id}: {_translate_bot_errors(e)}")
                    try: await event.reply(f"❌ خطا: {_translate_bot_errors(e)}")
                    except: pass
                return
        own_pending_state = pm_banner_states.get(user_id)
        routed_state_uid = (user_id if own_pending_state is not None
                            and own_pending_state.get("panel_actor_id", int(user_id)) == int(user_id)
                            else None)
        if routed_state_uid is None:
            for target_uid, pending_state in list(pm_banner_states.items()):
                if (pending_state.get("panel_actor_id") == int(user_id)
                        and pending_state.get("prompt_chat_id") in (None, event.chat_id)):
                    routed_state_uid = target_uid
                    break
        if routed_state_uid is not None:
            st_mode = pm_banner_states[routed_state_uid].get("mode", "")
            if st_mode.startswith("mat_") or st_mode.startswith("item_"):
                handled = await _pm_mat_state_input(event, routed_state_uid)
            else:
                handled = await _pm_banner_state_input(event, routed_state_uid)
            updated_state = pm_banner_states.get(routed_state_uid)
            if updated_state is not None and int(routed_state_uid) != int(user_id):
                updated_state["panel_actor_id"] = int(user_id)
            if handled: return
        # Apply selected font/HTML style to ordinary outgoing user text. Commands
        # and workflow replies must remain unchanged so their parsing still works.
        if (text and getattr(event, "out", False)
                and not text.startswith((CMD, "/"))
                and routed_state_uid is None
                and user_id not in pm_banner_states
                and user_id not in broadcast_waiting):
            user_cfg = users_db["users"].get(str(user_id), {})
            if user_cfg.get("font_on") or user_cfg.get("html_style_on"):
                styled_text = apply_user_style(user_id, event.raw_text or "")
                if styled_text != (event.raw_text or ""):
                    try:
                        await event.edit(styled_text, parse_mode="html")
                        return
                    except Exception as e:
                        log_error(f"apply user style {user_id}: {_translate_bot_errors(e)}")
        if not event.raw_text or event.raw_text.startswith("/"): return
        try:
            if text.startswith(f"{CMD}افزودن انتقال مواد "):
                raw = text.replace(f"{CMD}افزودن انتقال مواد ", "", 1).strip()
                parts = raw.split()
                if len(parts) < 3:
                    await safe_edit(event, f"❌ فرمت: {CMD}افزودن انتقال مواد [آیدی ۴ رقمی] [نام ماده] [تعداد]"); return
                cid = normalize_digits(parts[0])
                qty_str = normalize_digits(parts[-1])
                name = " ".join(parts[1:-1])
                if not cid.isdigit() or not (1 <= len(cid) <= 5):
                    await safe_edit(event, "❌ آیدی باید بین ۱ تا ۵ رقم باشد."); return
                if not qty_str.isdigit():
                    await safe_edit(event, "❌ تعداد باید عدد باشد. (0 برای همه)"); return
                cfg = transfer_materials_config.setdefault(user_id, {"enabled": False, "rules": []})
                cfg["rules"].append({"cid": cid, "material": name, "quantity": int(qty_str)})
                schedule_save_runtime()
                await safe_edit(event, f"✅ اضافه شد:\n📦 {name} ➡️ {cid}\n🔢 {qty_str if qty_str!='0' else 'همه'}")
                return
                
            if text.startswith(f"{CMD}حذف انتقال مواد "):
                raw = text.replace(f"{CMD}حذف انتقال مواد ", "", 1).strip()
                parts = raw.split()
                if len(parts) < 2:
                    await safe_edit(event, f"❌ فرمت: {CMD}حذف انتقال مواد [آیدی] [نام ماده]"); return
                cid = normalize_digits(parts[0])
                name = " ".join(parts[1:])
                cfg = transfer_materials_config.get(user_id, {})
                rules = cfg.get("rules", [])
                new_rules = [r for r in rules if not (r["cid"] == cid and name in r["material"])]
                if len(new_rules) == len(rules):
                    await safe_edit(event, "❌ چنین قانونی پیدا نشد."); return
                cfg["rules"] = new_rules
                schedule_save_runtime()
                await safe_edit(event, "✅ حذف شد.")
                return
                
            if text == f"{CMD}لیست انتقال مواد":
                cfg = transfer_materials_config.get(user_id, {})
                rules = cfg.get("rules", [])
                if not rules:
                    await safe_edit(event, "📭 لیست خالی است."); return
                lines = ["📋 <b>لیست انتقال مواد:</b>"]
                for i, r in enumerate(rules, 1):
                    lines.append(f"{i}. 📦 {r['material']} | 🔢 {r['quantity'] if r['quantity']>0 else 'همه'} | 👤 {r['cid']}")
                await safe_edit(event, "\n".join(lines), parse_mode="html")
                return

            if text == f"{CMD}پنل":
                if not is_user_active(user_id):
                    try: await event.edit("❌ برای استفاده اول لاگین کن:\n/login")
                    except Exception:
                        try: await event.respond("❌ برای استفاده اول لاگین کن:\n/login")
                        except: pass
                    return
                try: await event.edit("✅ پنل باز شد")
                except Exception:
                    try: await event.respond("✅ پنل باز شد")
                    except: pass
                ok = await send_panel_via_helper(user_id, event.chat_id)
                if not ok: log_error(f"group panel failed {user_id}")
                return
            if text == f"{CMD}راهنما": await panel_main(event, user_id); return
            if text in (f"{CMD}راهنما تبچی", f"{CMD}راهنما بنر"): await panel_help_banner(event); return
            if text in (f"{CMD}راهنما پونی", f"{CMD}راهنما دانجن"): await panel_help_pony(event); return
            if text in (f"{CMD}راهنما شکار گروهی", f"{CMD}راهنما پیو"): await panel_help_ghunt(event); return
            if text in (f"{CMD}راهنما کاردینال", f"{CMD}راهنما بازی"): await panel_help_cardinal(event); return
            if not is_user_allowed(user_id): return
            if is_user_locally_disabled(user_id):
                try: await event.edit("⚠️ ربات خاموشه! /login")
                except Exception:
                    try: await event.respond("⚠️ ربات خاموشه! /login")
                    except: pass
                return
            if not is_user_active(user_id):
                try: await event.edit("⛔ غیرفعال. /login")
                except Exception:
                    try: await event.respond("⛔ غیرفعال. /login")
                    except: pass
                return
            if text == f"{CMD}خاموش شو":
                set_user_locally_disabled(user_id, True)
                await safe_edit(event, "🔴 خاموش شد."); return
            # فرمانده
            if text == f"{CMD}فرمانده":
                orphan_id = get_orphan_team_of_ally(event.chat_id, user_id)
                if orphan_id:
                    revive_orphan_team(event.chat_id, user_id, orphan_id)
                    await safe_edit(event, "👑 فرمانده تیم قبلی شدی!"); return
                active_team = get_active_team_of_ally(event.chat_id, user_id)
                if active_team and not is_commander(user_id, event.chat_id):
                    cm_name = await get_plain_name(bot_client, int(active_team))
                    await safe_edit(event, f"❌ یار {cm_name} هستی.\n{CMD}یار خارج"); return
                if is_commander(user_id, event.chat_id):
                    c = get_chat_battle(event.chat_id)
                    cinfo = c["commanders"].get(str(user_id), {})
                    was_paused = cinfo.get("state") == "paused_by_user"
                    cinfo["auto_enabled"] = True; cinfo["state"] = "idle"
                    cinfo["next_farakhans_at"] = ""; cinfo["start_attempts"] = 0
                    c["commanders"][str(user_id)] = cinfo; save_battle()
                    n = unpause_all_allies_of_commander(event.chat_id, user_id)
                    if was_paused:
                        await safe_edit(event, f"🟢 فتح روشن شد.\n👥 {n} یار هم فعال شدن.\n💡 {CMD}فراخوان")
                    else: await safe_edit(event, "👑 فرمانده هستی.")
                    return
                add_commander(user_id, event.chat_id)
                await safe_edit(event, f"👑 فرمانده شدی.\n💡 {CMD}فراخوان"); return
            if text == f"{CMD}فتح خاموش":
                cancel_user_battle_tasks(user_id, event.chat_id)
                c = get_chat_battle(event.chat_id)
                if str(user_id) in c["commanders"]:
                    cinfo = c["commanders"][str(user_id)]
                    cinfo["auto_enabled"] = False; cinfo["state"] = "paused_by_user"
                    cinfo["next_farakhans_at"] = ""; cinfo["cooldown_seconds"] = 0
                    cinfo["start_attempts"] = 0; cinfo["last_code"] = ""; cinfo["floor"] = 0
                    c["commanders"][str(user_id)] = cinfo
                    for aid in list(c.get("allies", {}).keys()):
                        c.setdefault("ally_join_status", {})[aid] = False
                    c["ally_max_floor"] = {}; c["commander_floor_change_for"] = ""
                    save_battle()
                n = pause_all_allies_of_commander(event.chat_id, user_id)
                await safe_edit(event, f"🔴 فتح خاموش شد.\n👥 {n} یار پاز شدن.\n💡 روشن: {CMD}فرمانده"); return
            if text in (f"{CMD}فرمانده خارج", f"{CMD}فرمانده خاموش"):
                if not is_commander(user_id, event.chat_id):
                    await safe_edit(event, "❌ فرمانده نیستی."); return
                cancel_user_battle_tasks(user_id, event.chat_id)
                for aid, cmid in list(get_chat_battle(event.chat_id).get("allies", {}).items()):
                    if str(cmid) == str(user_id):
                        ally_paused.pop((int(event.chat_id), int(aid)), None)
                cinfo, freed = remove_commander(user_id, event.chat_id)
                if freed:
                    await safe_edit(event, f"🔴 خارج شدی.\n👥 {len(freed)} یار موندن.")
                else: await safe_edit(event, "🔴 خارج شدی.")
                return
            # یار
            if text == f"{CMD}یار" or (text.startswith(f"{CMD}یار ") and not text.startswith(f"{CMD}یار اخراج")):
                arg = text.replace(f"{CMD}یار", "", 1).strip()
                if arg in ("خارج", "خاموش", "off"):
                    c = get_chat_battle(event.chat_id)
                    team_id = c["allies"].get(str(user_id))
                    if team_id is None:
                        await safe_edit(event, "❌ تیمی نیستی."); return
                    is_orphan = str(team_id) in c.get("orphan_teams", {})
                    remove_ally(user_id, event.chat_id)
                    if is_orphan: cleanup_orphan_team_if_empty(event.chat_id, team_id)
                    await safe_edit(event, "🔴 خارج شدی."); return
                client = await ensure_user_client(user_id)
                if not client: await safe_edit(event, "🔌 اتصال نیست."); return
                target_id = await resolve_user_arg(event, client, arg)
                if not target_id:
                    await safe_edit(event, "❌ ریپلای/آیدی."); return
                if target_id == user_id:
                    await safe_edit(event, "❌ خودت."); return
                if not is_commander(target_id, event.chat_id):
                    await safe_edit(event, "❌ فرمانده نیست."); return
                result = add_ally(user_id, target_id, event.chat_id)
                ok = result[0]; reason = result[1] if len(result) > 1 else None
                info = result[2] if len(result) > 2 else None
                if not ok:
                    if reason == "already_in_other_team":
                        name = await get_plain_name(client, info)
                        await safe_edit(event, f"❌ یار {name}.\n{CMD}یار خارج")
                    elif reason == "team_full":
                        await safe_edit(event, f"❌ پر ({info}/{MAX_ALLIES_PER_TEAM})")
                    else: await safe_edit(event, "❌ نشد.")
                    return
                cm_name = await get_plain_name(client, target_id)
                cnt = sum(1 for _, cmid in get_chat_battle(event.chat_id)["allies"].items() if str(cmid) == str(target_id))
                await safe_edit(event, f"🤝 یار {cm_name}.\n👥 {cnt}/{MAX_ALLIES_PER_TEAM}"); return
            # اخراج
            if text == f"{CMD}اخراج" or text.startswith(f"{CMD}اخراج "):
                if not is_commander(user_id, event.chat_id):
                    await safe_edit(event, "❌ فقط فرمانده."); return
                arg = text.replace(f"{CMD}اخراج", "", 1).strip()
                if arg == "همه":
                    c = get_chat_battle(event.chat_id)
                    my_allies = [aid for aid, cmid in c["allies"].items() if str(cmid) == str(user_id)]
                    if not my_allies:
                        await safe_edit(event, "📭 خالی."); return
                    for aid in my_allies:
                        c["allies"].pop(aid, None)
                        c.get("ally_nicknames", {}).pop(aid, None)
                        c.get("ally_join_status", {}).pop(aid, None)
                        c.get("ally_max_floor", {}).pop(aid, None)
                    save_battle()
                    await safe_edit(event, f"✅ {len(my_allies)} یار."); return
                client = await ensure_user_client(user_id)
                if not client: await safe_edit(event, "🔌 اتصال نیست."); return
                target_id = await resolve_user_arg(event, client, arg)
                if not target_id:
                    await safe_edit(event, "❌ ریپلای/آیدی."); return
                c = get_chat_battle(event.chat_id)
                ally_cm = c["allies"].get(str(target_id))
                if ally_cm is None or int(ally_cm) != int(user_id):
                    await safe_edit(event, "❌ یار تو نیست."); return
                c["allies"].pop(str(target_id), None)
                c.get("ally_nicknames", {}).pop(str(target_id), None)
                c.get("ally_join_status", {}).pop(str(target_id), None)
                c.get("ally_max_floor", {}).pop(str(target_id), None)
                save_battle()
                t_name = await get_plain_name(client, target_id)
                await safe_edit(event, f"✅ {t_name}."); return
            # همه طبقه
            if text.startswith(f"{CMD}همه طبقه ") and is_commander(user_id, event.chat_id):
                parts = text.split()
                if len(parts) != 3:
                    await safe_edit(event, f"❌ {CMD}همه طبقه <شماره>"); return
                target_str = normalize_digits(parts[2])
                if not target_str.isdigit():
                    await safe_edit(event, "❌ عدد باشه."); return
                target_floor = int(target_str)
                c = get_chat_battle(event.chat_id)
                my_allies = [aid for aid, cmid in c.get("allies", {}).items() if str(cmid) == str(user_id)]
                if not my_allies:
                    await safe_edit(event, "📭 یاری نداری."); return
                await safe_edit(event, f"📢 دستور به {len(my_allies)} یار\n🎯 طبقه {target_floor}")
                try:
                    await bot_client.send_message(event.chat_id,
                        f"📢 دستور فرمانده\n🎯 همه بیان طبقه {target_floor}\n🚪 و از شهر خارج بشن")
                except: pass
                for aid in my_allies:
                    _spawn(relocate_and_rejoin(int(aid), event.chat_id, "", target_floor, is_commander=False))
                    await asyncio.sleep(3)
                return
            # همه پراکندگی
            if text == f"{CMD}همه پراکندگی" and is_commander(user_id, event.chat_id):
                c = get_chat_battle(event.chat_id)
                my_allies = [aid for aid, cmid in c.get("allies", {}).items() if str(cmid) == str(user_id)]
                if not my_allies:
                    await safe_edit(event, "📭 یاری نداری."); return
                await safe_edit(event, f"📢 دستور به {len(my_allies)} یار\n🎲 پراکنده بشن")
                for aid in my_allies:
                    _spawn(scatter_ally_after_battle(int(aid), event.chat_id, True))
                    await asyncio.sleep(3)
                return
            # دفاع تیمی
            if text == f"{CMD}دفاع تیمی" or text.startswith(f"{CMD}دفاع تیمی "):
                if is_ally(user_id, event.chat_id):
                    await safe_edit(event, "❌ فقط فرمانده."); return
                if not is_commander(user_id, event.chat_id):
                    await safe_edit(event, f"❌ اول {CMD}فرمانده"); return
                arg = text.replace(f"{CMD}دفاع تیمی", "", 1).strip()
                if not arg:
                    await safe_edit(event, f"❌ {CMD}دفاع تیمی <شماره>"); return
                arg_norm = normalize_digits(arg).split()[0] if arg else ""
                if not arg_norm.isdigit():
                    await safe_edit(event, "❌ عدد باشه."); return
                target_floor = int(arg_norm)
                c = get_chat_battle(event.chat_id)
                my_allies = [int(aid) for aid, cmid in c.get("allies", {}).items() if str(cmid) == str(user_id)]
                all_members = [user_id] + my_allies
                defense_pending.setdefault(str(event.chat_id), {})[str(user_id)] = {
                    "code": "", "floor": target_floor, "members": all_members,
                    "created_at": time.time(), "initiator": int(user_id), "started": False}
                save_battle()
                await safe_edit(event, f"🛡️ دفاع تیمی\n🎯 طبقه: {target_floor}\n👥 {len(all_members)} عضو")
                _spawn(_prepare_defense_commander(user_id, event.chat_id, target_floor))
                for aid in my_allies:
                    _spawn(_prepare_defense_ally(aid, event.chat_id, target_floor))
                    await asyncio.sleep(3)
                return
            # فراخوان
            if text == f"{CMD}فراخوان" or text.startswith(f"{CMD}فراخوان "):
                forced_floor = 0
                if text.startswith(f"{CMD}فراخوان "):
                    arg = text.replace(f"{CMD}فراخوان", "", 1).strip()
                    arg_norm = normalize_digits(arg).split()[0] if arg else ""
                    if not arg_norm.isdigit():
                        await safe_edit(event, f"❌ {CMD}فراخوان <شماره طبقه>"); return
                    forced_floor = int(arg_norm)
                if is_ally(user_id, event.chat_id):
                    await safe_edit(event, "❌ یاری."); return
                if not is_commander(user_id, event.chat_id):
                    add_commander(user_id, event.chat_id)
                else:
                    c = get_chat_battle(event.chat_id)
                    cinfo = c["commanders"].get(str(user_id), {})
                    if cinfo.get("state") == "paused_by_user":
                        await safe_edit(event, f"🔴 فتح خاموشه.\n💡 اول: {CMD}فرمانده"); return
                    cinfo["auto_enabled"] = True; cinfo["city_retry_count"] = 0
                    c["commanders"][str(user_id)] = cinfo; save_battle()
                unpause_all_allies_of_commander(event.chat_id, user_id)
                if forced_floor > 0:
                    await safe_edit(event, f"🔄 آماده‌سازی فراخوان برای طبقه {forced_floor}...")
                else:
                    await safe_edit(event, "🔄 آماده‌سازی فراخوان (بالاترین مرز)...")
                _spawn(prepare_commander_for_farakhans(user_id, event.chat_id, forced_floor))
                return
            if text == f"{CMD}لغو نبرد":
                count = cancel_user_battle_tasks(user_id)
                await safe_edit(event, f"✅ {count} تسک."); return
            # حمله تیمی
            if text.startswith(f"{CMD}حمله تیمی ایجاد "):
                team_name = text.replace(f"{CMD}حمله تیمی ایجاد ", "", 1).strip()
                if not team_name:
                    await safe_edit(event, f"❌ {CMD}حمله تیمی ایجاد <اسم>"); return
                teams = get_team_dict(event.chat_id)
                if team_name in teams:
                    await safe_edit(event, "❌ وجود داره."); return
                if get_user_team_in_chat(event.chat_id, user_id):
                    await safe_edit(event, "❌ تو تیم دیگه‌ای هستی."); return
                join_team(event.chat_id, team_name, user_id)
                await safe_edit(event, f"✅ تیم «{team_name}» ساخته شد.\n👥 1/{MAX_TEAM_ATTACK_MEMBERS}"); return
            if text.startswith(f"{CMD}حمله تیمی روشن "):
                team_name = text.replace(f"{CMD}حمله تیمی روشن ", "", 1).strip()
                teams = get_team_dict(event.chat_id)
                if team_name not in teams:
                    await safe_edit(event, "❌ نیست."); return
                if is_in_team(event.chat_id, team_name, user_id):
                    await safe_edit(event, "⚠️ هستی."); return
                if get_user_team_in_chat(event.chat_id, user_id):
                    await safe_edit(event, "❌ تو تیم دیگه‌ای هستی."); return
                cnt = len(get_team_members(event.chat_id, team_name))
                if cnt >= MAX_TEAM_ATTACK_MEMBERS:
                    await safe_edit(event, f"❌ پره ({cnt}/{MAX_TEAM_ATTACK_MEMBERS})"); return
                join_team(event.chat_id, team_name, user_id)
                cnt = len(get_team_members(event.chat_id, team_name))
                await safe_edit(event, f"✅ پیوستی.\n👥 {cnt}/{MAX_TEAM_ATTACK_MEMBERS}"); return
            if text.startswith(f"{CMD}حمله تیمی خاموش "):
                team_name = text.replace(f"{CMD}حمله تیمی خاموش ", "", 1).strip()
                if not is_in_team(event.chat_id, team_name, user_id):
                    await safe_edit(event, "❌ نیستی."); return
                leave_team(event.chat_id, team_name, user_id)
                cnt = len(get_team_members(event.chat_id, team_name))
                if cnt == 0:
                    delete_team(event.chat_id, team_name)
                    await safe_edit(event, "🔴 حذف شد."); return
                await safe_edit(event, f"🔴 خارج شدی.\n👥 {cnt}/{MAX_TEAM_ATTACK_MEMBERS}"); return
            if text.startswith(f"{CMD}حمله تیمی به "):
                raw = text.replace(f"{CMD}حمله تیمی به ", "", 1).strip()
                parts = raw.split()
                if len(parts) < 2:
                    await safe_edit(event, f"❌ {CMD}حمله تیمی به <اسم> <C_ID>"); return
                team_name = parts[0]; target_id_str = normalize_digits(parts[1])
                if not target_id_str.isdigit():
                    await safe_edit(event, "❌ C_ID باید بین ۱ تا ۵ رقم باشد."); return
                if not is_in_team(event.chat_id, team_name, user_id):
                    await safe_edit(event, "❌ نیستی."); return
                members = get_team_members(event.chat_id, team_name)
                if not members:
                    await safe_edit(event, "❌ خالیه."); return
                if team_name in team_attack_pending.get(str(event.chat_id), {}):
                    await safe_edit(event, "⚠️ در حال حمله‌ست."); return
                team_attack_pending.setdefault(str(event.chat_id), {})[team_name] = {
                    "initiator": int(user_id), "members": members,
                    "join_code": "", "start_code": "",
                    "created_at": time.time(), "started": False, "cancelled": False,
                    "target": target_id_str, "join_status": {}}
                client = user_clients.get(int(user_id))
                if not client or not client.is_connected():
                    client = await ensure_user_client(user_id)
                if not client:
                    team_attack_pending[str(event.chat_id)].pop(team_name, None)
                    await safe_edit(event, "❌ اتصال نیست."); return
                ok = await safe_send(client, user_id, event.chat_id,
                    f"حمله تیمی به {target_id_str}", tag="team_attack")
                if ok:
                    await safe_edit(event, f"⚔️ تیم «{team_name}»\n🎯 هدف: {target_id_str}\n⏳ منتظر کد...")
                else:
                    team_attack_pending[str(event.chat_id)].pop(team_name, None)
                    await safe_edit(event, "❌ ارسال نشد.")
                return
            if text in (f"{CMD}حمله تیمی لیست", f"{CMD}پنل حمله تیمی"):
                client = user_clients.get(int(user_id))
                if not client or not client.is_connected():
                    client = await ensure_user_client(user_id)
                teams = get_team_dict(event.chat_id)
                lines = ["⚔️ تیم‌های حمله", "━━━━━━━━━━━━━━━━━", ""]
                if not teams:
                    lines.append("📭 هیچ تیمی نیست")
                    lines.append(f"\n💡 {CMD}حمله تیمی ایجاد <اسم>")
                else:
                    for tn in teams:
                        ms = get_team_members(event.chat_id, tn)
                        pending = team_attack_pending.get(str(event.chat_id), {}).get(tn)
                        status = "🔥" if pending else "🟢"
                        lines.append(f"📌 «{tn}» — {status} ({len(ms)}/{MAX_TEAM_ATTACK_MEMBERS})")
                        for mid in ms:
                            try: nm = await get_plain_name(client, mid)
                            except: nm = str(mid)
                            me = " (تو)" if mid == user_id else ""
                            lines.append(f"      • {nm} — 🆔 {mid}{me}")
                        lines.append("")
                await safe_edit(event, "\n".join(lines)); return
            if text in (f"{CMD}حمله تیمی ایجاد", f"{CMD}حمله تیمی روشن", f"{CMD}حمله تیمی خاموش", f"{CMD}حمله تیمی به"):
                _sub = text.replace(f"{CMD}حمله تیمی ", "", 1)
                await safe_edit(event, f"❌ {CMD}حمله تیمی {_sub} <اسم>"); return
            # تبچی ریپلای
            if text.startswith(f"{CMD}تبچی ریپلای "):
                bname = text.replace(f"{CMD}تبچی ریپلای ", "", 1).strip()
                banners = get_user_banners(user_id)
                if bname not in banners: await safe_edit(event, "❌ بنر نیست."); return
                targets = banners[bname].get("targets", [])
                if not targets: await safe_edit(event, "❌ هدف نداره."); return
                replied = await event.get_reply_message()
                if not replied: await safe_edit(event, "❌ روی پیام ریپلای کن."); return
                client = await ensure_user_client(user_id)
                if not client: return
                try:
                    await client.send_message(targets[0], "🔗 تست ریپلای", reply_to=replied.id)
                    banners[bname]["reply_to_msg_id"] = replied.id
                    save_json(BANNERS_FILE, banners_db)
                    await safe_edit(event, "✅ ریپلای تنظیم شد.")
                except Exception as e:
                    await safe_edit(event, f"❌ {_translate_bot_errors(e)}")
                return
            # 🔒 گیت قفل بخش‌ها: دستور متنی بخش قفل‌شده اجرا نمی‌شود
            _locked_lbl = _locked_command_label(user_id, text)
            if _locked_lbl:
                _lmsg = f"🔒 بخش «{_locked_lbl}» توسط مالک قفل شده است."
                try: await safe_edit(event, _lmsg)
                except Exception:
                    try: await event.respond(_lmsg)
                    except Exception: pass
                return
            # پنل‌های متنی
            if text in (f"{CMD}پنل بازی", f"{CMD}بازی"):
                await panel_games(event, user_id); return
            if text in (f"{CMD}پنل کاردینال", f"{CMD}کاردینال"):
                await panel_cardinal(event, user_id); return
            if text in (f"{CMD}پنل پونی", f"{CMD}پونی"):
                await panel_pony_text(event, user_id); return
            if text in (f"{CMD}پنل پیو", f"{CMD}پیو"):
                await panel_pew_text(event, user_id); return
            if text in (f"{CMD}پنل تبچی", f"{CMD}تبچی"):
                await panel_banner(event, user_id); return
            if text in (f"{CMD}پنل ابزار", f"{CMD}ابزارها", f"{CMD}پنل ابزارها"):
                await panel_tools(event, user_id); return
            if text in (f"{CMD}پنل استایل", f"{CMD}پنل HTML",
                        f"{CMD}راهنمای استایل", f"{CMD}استایل"):
                await panel_html_text(event, user_id); return
            if text in (f"{CMD}پنل فونت",):
                await panel_font_text(event, user_id); return
            # وضعیت
            if text in (f"{CMD}وضعیت", f"{CMD}وضعیت من"):
                if event.is_group or event.is_channel:
                    await panel_status(event, user_id)
                else:
                    await panel_status_private(event, user_id)
                return
            # پونی/دانجن
            if text == f"{CMD}پونی روشن":
                cfg = get_pony_cfg(user_id, event.chat_id)
                if cfg.get("collect"):
                    await safe_edit(event, "⚠️ از قبل روشنه."); return
                cfg["collect"] = True
                pony_state[(int(user_id), int(event.chat_id))] = {
                    "phase": "learning", "samples": [],
                    "learned": None, "start_ts": time.time(), "last_fill": 0}
                start_pony_task(user_id, event.chat_id)
                schedule_save_runtime()
                await safe_edit(event, "🟢 پونی روشن شد.\n🔬 در حال یادگیری زمان پر شدن پونی...")
                return
            if text == f"{CMD}پونی خاموش":
                cfg = get_pony_cfg(user_id, event.chat_id)
                if not cfg.get("collect"):
                    await safe_edit(event, "⚠️ از قبل خاموشه."); return
                cfg["collect"] = False
                stop_pony_task(user_id, event.chat_id)
                pony_state.pop((int(user_id), int(event.chat_id)), None)
                st = pony_waiting.pop(user_id, None)
                if st and st.get("retry_task"):
                    rt = st["retry_task"]
                    if not rt.done(): rt.cancel()
                schedule_save_runtime()
                await safe_edit(event, "🔴 پونی خاموش شد."); return
            if text == f"{CMD}ارتقا روشن":
                cfg = get_pony_cfg(user_id, event.chat_id)
                if cfg.get("upgrade"):
                    await safe_edit(event, "⚠️ از قبل روشنه."); return
                cfg["upgrade"] = True
                if not cfg.get("collect"): cfg["collect"] = True
                pony_state.setdefault((int(user_id), int(event.chat_id)),
                    {"phase": "learning", "samples": [],
                     "learned": None, "start_ts": time.time(), "last_fill": 0})
                start_pony_task(user_id, event.chat_id)
                schedule_save_runtime()
                await safe_edit(event, "🟢 ارتقا روشن شد.\n+ پونی روشن شد."); return
            if text == f"{CMD}ارتقا خاموش":
                cfg = get_pony_cfg(user_id, event.chat_id)
                if not cfg.get("upgrade"):
                    await safe_edit(event, "⚠️ از قبل خاموشه."); return
                cfg["upgrade"] = False
                schedule_save_runtime()
                await safe_edit(event, "🔴 ارتقا خاموش شد."); return
            if text == f"{CMD}دانجن روشن":
                cfg = get_dungeon_cfg(user_id, event.chat_id)
                if cfg.get("enabled"):
                    await safe_edit(event, "⚠️ از قبل روشنه."); return
                cfg["enabled"] = True; cfg["test_mode"] = True
                cfg["current_idx"] = 0; cfg["working_idx"] = -1
                start_dungeon_task(user_id, event.chat_id)
                schedule_save_runtime()
                await safe_edit(event, "🟢 دانجن روشن شد.\n🧪 اول تست از قوی‌ترین به ضعیف‌ترین..."); return
            if text == f"{CMD}دانجن خاموش":
                cfg = get_dungeon_cfg(user_id, event.chat_id)
                if not cfg.get("enabled"):
                    await safe_edit(event, "⚠️ از قبل خاموشه."); return
                cfg["enabled"] = False
                stop_dungeon_task(user_id, event.chat_id)
                schedule_save_runtime()
                await safe_edit(event, "🔴 دانجن خاموش شد."); return
            if text == f"{CMD}دانجن تست":
                await safe_edit(event, "🔄 ریست دانجن...\n🧪 از قوی‌ترین هیولا شروع می‌کنم.")
                stop_dungeon_task(user_id, event.chat_id)
                await asyncio.sleep(1)
                cfg = get_dungeon_cfg(user_id, event.chat_id)
                cfg["enabled"] = True; cfg["current_idx"] = 0
                cfg["working_idx"] = -1; cfg["test_mode"] = True
                start_dungeon_task(user_id, event.chat_id)
                schedule_save_runtime()
                return
            # فروش
            if text == f"{CMD}فروش روشن":
                if user_id in sell_mode_users and sell_mode_users[user_id].get("enabled"):
                    await safe_edit(event, "⚠️ روشن."); return
                sell_mode_users[user_id] = {"enabled": True, "scheduler_task": None}
                sell_mode_users[user_id]["scheduler_task"] = asyncio.create_task(sell_scheduler(user_id))
                schedule_save_runtime()
                await safe_edit(event, f"🟢 فروش روشن شد\n💡 خاموش: {CMD}فروش خاموش\n💡 وضعیت: {CMD}وضعیت")
                return
            if text == f"{CMD}فروش خاموش":
                if user_id not in sell_mode_users:
                    await safe_edit(event, "⚠️ خاموش."); return
                stop_sell_mode(user_id)
                _ensure_enabled_transfer_schedulers(user_id)
                await safe_edit(event, "🔴 خاموش شد."); return
            if text == f"{CMD}نفروش" or text.startswith(f"{CMD}نفروش "):
                arg = text.replace(f"{CMD}نفروش", "", 1).strip()
                if not arg:
                    await safe_edit(event,
                        f"❌ {CMD}نفروش <اسم آیتم>\n"
                        f"📎 مثال: {CMD}نفروش ارقام * گوشت * استخوان"); return
                if has_bad_separator(arg):
                    await safe_edit(event,
                        f"❌ بین نماد و اسم آیتم باید فاصله باشه.\n\n"
                        f"✅ درست: {CMD}نفروش ارقام * گوشت\n"
                        f"❌ غلط: {CMD}نفروش ارقام*گوشت"); return
                items = parse_no_sell_args(arg)
                if not items:
                    await safe_edit(event, "❌ اسم وارد کن."); return
                added, skipped = add_no_sell_items(user_id, items)
                lines = []
                if added:
                    lines.append(f"✅ اضافه شد ({len(added)}):")
                    for a in added: lines.append(f"   • {a}")
                if skipped:
                    lines.append(f"⚠️ از قبل بود: {', '.join(skipped)}")
                lines.append(f"\n📊 کل: {len(get_no_sell_list(user_id))}")
                await safe_edit(event, "\n".join(lines)); return
            if text in (f"{CMD}لیست نفروش", f"{CMD}نفروش لیست"):
                lst = get_no_sell_list(user_id)
                if not lst:
                    await safe_edit(event, f"📭 لیست خالیه.\n💡 {CMD}نفروش <اسم>"); return
                await safe_edit(event, "🔄 در حال گرفتن موجودی...")
                quantities = await fetch_inventory_quantities(user_id)
                lines = [f"🚫 لیست نفروش ({len(lst)})", "━━━━━━━━━━━━━━━━━", ""]
                for i, nm in enumerate(lst, 1):
                    qty = None
                    for k, v in quantities.items():
                        if nm.strip().lower() in k.strip().lower(): qty = v; break
                    lines.append(f"{i}. {nm} — 📦 {qty}" if qty is not None else f"{i}. {nm}")
                lines.append("")
                lines.append(f"💡 {CMD}حذف نفروش <اسم>")
                await safe_edit(event, "\n".join(lines)); return
            if text.startswith(f"{CMD}حذف نفروش "):
                arg = text.replace(f"{CMD}حذف نفروش ", "", 1).strip()
                if not arg:
                    await safe_edit(event, f"❌ {CMD}حذف نفروش <اسم>"); return
                items = parse_no_sell_args(arg)
                removed = remove_no_sell_items(user_id, items)
                if removed == 0:
                    await safe_edit(event, "❌ توی لیست نبود."); return
                await safe_edit(event, f"✅ {removed} حذف شد.\n📊 باقی: {len(get_no_sell_list(user_id))}"); return
            if text == f"{CMD}حذف نفروش":
                await safe_edit(event, f"❌ {CMD}حذف نفروش <اسم>"); return
            # فرار/برگشت/جایزه
            if text == f"{CMD}فرار روشن":
                if is_escape_enabled(user_id):
                    await safe_edit(event, "⚠️ از قبل روشنه."); return
                escape_config[user_id] = {"enabled": True}
                schedule_save_runtime()
                await safe_edit(event, "🟢 فرار روشن شد."); return
            if text == f"{CMD}فرار خاموش":
                if not is_escape_enabled(user_id):
                    await safe_edit(event, "⚠️ از قبل خاموشه."); return
                escape_config[user_id] = {"enabled": False}
                schedule_save_runtime()
                await safe_edit(event, "🔴 فرار خاموش شد."); return
            if text == f"{CMD}برگشت روشن":
                if is_return_enabled(user_id):
                    await safe_edit(event, "⚠️ از قبل روشنه."); return
                return_config[user_id] = {"enabled": True}
                schedule_save_runtime()
                await safe_edit(event, "🟢 برگشت روشن شد."); return
            if text == f"{CMD}برگشت خاموش":
                if not is_return_enabled(user_id):
                    await safe_edit(event, "⚠️ از قبل خاموشه."); return
                return_config[user_id] = {"enabled": False}
                schedule_save_runtime()
                await safe_edit(event, "🔴 برگشت خاموش شد."); return
            if text == f"{CMD}جایزه روشن":
                if daily_gift_status.get(user_id, False):
                    await safe_edit(event, "⚠️ روشن."); return
                start_daily_gift(user_id)
                await safe_edit(event, "🟢 جایزه روشن شد.\n⏱ هر ۲۵ ساعت"); return
            if text == f"{CMD}جایزه خاموش":
                if not daily_gift_status.get(user_id, False):
                    await safe_edit(event, "⚠️ خاموش."); return
                stop_daily_gift(user_id)
                await safe_edit(event, "🔴 جایزه خاموش شد."); return
            # پروفایل رندوم: چرخش بین عکس‌های موجود در گالری پروفایل تلگرام.
            if text == f"{CMD}پروفایل رندوم روشن":
                ok, result = await set_random_profile_enabled(user_id, True)
                await safe_edit(event, result); return
            if text == f"{CMD}پروفایل رندوم خاموش":
                _ok, result = await set_random_profile_enabled(user_id, False)
                await safe_edit(event, result); return
            if text == f"{CMD}پروفایل رندوم":
                cfg = get_random_profile_config(user_id)
                photos_count = len(cfg.get("photo_ids", []))
                try:
                    _client, photos = await _load_own_profile_photos(user_id)
                    photos_count = len(photos)
                    if not cfg.get("enabled"):
                        cfg["photo_ids"] = [photo_id for photo_id, _ in photos]
                        save_json(USERS_FILE, users_db)
                except Exception: pass
                iv = {60: "۱ دقیقه", 300: "۵ دقیقه", 600: "۱۰ دقیقه"}.get(
                    int(cfg.get("interval", 60) or 60), "۱ دقیقه")
                await safe_edit(event,
                    f"📷 پروفایل رندوم: {'🟢 روشن' if cfg.get('enabled') else '🔴 خاموش'}\n"
                    f"🖼 عکس‌های قابل‌چرخش: {photos_count}\n⏱ بازه: {iv}\n"
                    f"روشن: {CMD}پروفایل رندوم روشن\nخاموش: {CMD}پروفایل رندوم خاموش")
                return
            # پایش پروفایل، تبدیل متن/ویس و استایل‌ها؛ دستورهای متنی همگی با CMD (ویرگول فارسی) هستند.
            if text in (f"{CMD}پایش", f"{CMD}پنل پایش"):
                await safe_edit(event,
                    "👁 پایش پروفایل\n"
                    f"افزودن با ریپلای یا آیدی: <code>{CMD}پایش افزودن @username</code>\n"
                    f"حذف: <code>{CMD}پایش حذف @username</code>\n"
                    f"فهرست: <code>{CMD}لیست پایش</code>\n"
                    "برای روشن/خاموش‌کردن پایش کلی از دکمه‌های پنل ابزارها استفاده کن.",
                    parse_mode="html"); return
            if text.startswith(f"{CMD}پایش افزودن"):
                arg = text.replace(f"{CMD}پایش افزودن", "", 1).strip()
                ok, result = await _monitor_add_target(user_id, event, arg)
                await safe_edit(event, result); return
            if text.startswith(f"{CMD}پایش حذف"):
                arg = text.replace(f"{CMD}پایش حذف", "", 1).strip()
                client = user_clients.get(int(user_id))
                if not client or not client.is_connected(): client = await ensure_user_client(user_id)
                tid = await resolve_user_arg(event, client, arg) if client else None
                users = monitor_db.get(str(int(user_id)), {}).get("users", {})
                if tid and str(int(tid)) in users:
                    users.pop(str(int(tid)), None); _save_monitor_db()
                    await safe_edit(event, f"✅ {tid} از فهرست پایش حذف شد."); return
                await safe_edit(event, "❌ فرد در فهرست پایش پیدا نشد."); return
            if text == f"{CMD}لیست پایش":
                cfg = monitor_db.get(str(int(user_id)), {})
                targets = cfg.get("users", {})
                if not targets:
                    await safe_edit(event, "📭 فهرست پایش خالی است."); return
                lines = [f"👁 فهرست پایش ({len(targets)} نفر):"]
                for tid, info in list(targets.items())[:50]:
                    icon = "🟢" if info.get("enabled", True) else "🔴"
                    uname = f" · @{info['last_uname']}" if info.get("last_uname") else ""
                    lines.append(f"{icon} {info.get('last_name') or tid}{uname} — {tid}")
                await safe_edit(event, "\n".join(lines)); return
            if text in (f"{CMD}پنل ویس", f"{CMD}پنل صدا"):
                await safe_edit(event,
                    "🔊 تبدیل متن و ویس\n"
                    f"{CMD}ویس <متن>\n{CMD}ویس زن <متن>\n{CMD}ویس مرد <متن>\n"
                    f"روی ویس ریپلای کن و بنویس {CMD}گوش کن")
                return
            if text == f"{CMD}گوش کن":
                await _transcribe_voice_reply(event); return
            if text == f"{CMD}ویس" or text.startswith(f"{CMD}ویس "):
                body = text[len(f"{CMD}ویس"):].strip()
                gender = None
                if body == "زن" or body.startswith("زن "):
                    gender = "female"; body = body[2:].strip()
                elif body == "مرد" or body.startswith("مرد "):
                    gender = "male"; body = body[3:].strip()
                if not body:
                    try:
                        replied = await event.get_reply_message()
                        body = (replied.raw_text or "").strip() if replied else ""
                    except: body = ""
                await _send_tts_voice(event, body, gender); return

            # ابزارها
            if text == f"{CMD}استایل روشن":

                if users_db["users"].get(str(user_id), {}).get("html_style_on"):
                    await safe_edit(event, "⚠️ از قبل روشنه."); return
                set_user_html_style_on(user_id, True)
                await safe_edit(event, "🟢 استایل روشن شد."); return
            if text == f"{CMD}استایل خاموش":
                if not users_db["users"].get(str(user_id), {}).get("html_style_on"):
                    await safe_edit(event, "⚠️ از قبل خاموشه."); return
                set_user_html_style_on(user_id, False)
                await safe_edit(event, "🔴 استایل خاموش شد."); return
            if text.startswith(f"{CMD}استایل "):
                raw = text.replace(f"{CMD}استایل ", "", 1).strip()
                key = _find_style_key(raw)
                if not key:
                    keys_list = " · ".join(k for k in HTML_STYLES if k != "pre")
                    await safe_edit(event,
                        f"❌ استایل نامعتبر.\n\n"
                        f"💡 انگلیسی: <code>{keys_list}</code>\n"
                        f"💡 فارسی: پررنگ · کج · پررنگ و کج · زیرخط‌دار · خط‌خورده · اسپویلر · تک‌عرض · بلوک کد · نقل‌قول · کشیده")
                    return
                set_user_html_style(user_id, key)
                if key == "none":
                    set_user_html_style_on(user_id, False)
                else:
                    set_user_html_style_on(user_id, True)
                if key == "none":
                    await safe_edit(event, "🔴 استایل خاموش شد."); return
                await safe_edit(event,
                    f"✅ استایل «{HTML_STYLES[key]['label']}» انتخاب و روشن شد.\n"
                    "از این به بعد پیام‌های عادی‌ات ویرایش می‌شوند و استایل می‌گیرند."); return
            if text == f"{CMD}فونت روشن":
                if users_db["users"].get(str(user_id), {}).get("font_on"):
                    await safe_edit(event, "⚠️ از قبل روشنه."); return
                set_user_font_on(user_id, True)
                await safe_edit(event, "🟢 فونت روشن شد."); return
            if text == f"{CMD}فونت خاموش":
                if not users_db["users"].get(str(user_id), {}).get("font_on"):
                    await safe_edit(event, "⚠️ از قبل خاموشه."); return
                set_user_font_on(user_id, False)
                await safe_edit(event, "🔴 فونت خاموش شد."); return
            if text.startswith(f"{CMD}فونت "):
                raw = text.replace(f"{CMD}فونت ", "", 1).strip()
                key = _find_font_key(raw)
                if not key:
                    keys_list = " · ".join(ENGLISH_FONTS.keys())
                    await safe_edit(event,
                        f"❌ فونت نامعتبر.\n\n"
                        f"💡 انگلیسی: <code>{keys_list}</code>\n"
                        f"💡 فارسی: بولد · کج · دست نویس · دایره · پهن · مونو")
                    return
                set_user_font(user_id, key)
                if key != "none":
                    set_user_font_on(user_id, True)
                await safe_edit(event, f"✅ فونت → {ENGLISH_FONTS[key]['label']}"); return
            # TTL
            if text == f"{CMD}تی تی ال":
                if not is_media_allowed(user_id):
                    await safe_edit(event, "🔒 این بخش خصوصی است."); return
                cfg = get_ttl_config(user_id)
                st = "🟢 روشن" if cfg["enabled"] else "🔴 خاموش"
                tname = "پیام‌های ذخیره شده" if cfg["target"] == "me" else str(cfg["target"])
                await safe_edit(event,
                    f"🔥 TTL (رسانه ناپدیدشونده)\n"
                    f"━━━━━━━━━━━━━━━━━\n"
                    f"وضعیت: {st}\n"
                    f"🎯 مقصد: <code>{tname}</code>\n"
                    f"━━━━━━━━━━━━━━━━━\n"
                    f"{CMD}تی تی ال روشن\n"
                    f"{CMD}تی تی ال خاموش\n"
                    f"{CMD}تی تی ال هدف")
                return
            if text == f"{CMD}تی تی ال روشن":
                if not is_media_allowed(user_id):
                    await safe_edit(event, "🔒 این بخش خصوصی است."); return
                set_ttl_config(user_id, "enabled", True)
                await safe_edit(event, "🟢 TTL روشن شد.\n💡 رسانه‌های ناپدیدشونده خودکار ذخیره می‌شن.")
                return
            if text == f"{CMD}تی تی ال خاموش":
                if not is_media_allowed(user_id):
                    await safe_edit(event, "🔒 این بخش خصوصی است."); return
                set_ttl_config(user_id, "enabled", False)
                await safe_edit(event, "🔴 TTL خاموش شد."); return
            if text == f"{CMD}تی تی ال هدف":
                if not is_media_allowed(user_id):
                    await safe_edit(event, "🔒 این بخش خصوصی است."); return
                chat = await event.get_chat()
                name = getattr(chat, "title", None) or getattr(chat, "first_name", None) or str(event.chat_id)
                set_ttl_config(user_id, "target", event.chat_id)
                await safe_edit(event, f"✅ مقصد TTL → {name}"); return
            # ذخیره
            if text == f"{CMD}ذخیره" or text.startswith(f"{CMD}ذخیره "):
                if not is_media_allowed(user_id):
                    await safe_edit(event, "🔒 این بخش خصوصی است."); return
                raw_arg = text.replace(f"{CMD}ذخیره", "", 1).strip()
                await _handle_save_command(event, user_id, raw_arg)
                return
            # ارسال خودکار
            matched_auto = False
            for as_key, as_cfg in AUTO_SEND_CONFIG.items():
                if text == f"{CMD}{as_key} روشن":
                    matched_auto = True
                    if auto_send_status.get(user_id, {}).get(as_key):
                        await safe_edit(event, "⚠️ روشن."); return
                    start_auto_send(user_id, as_key)
                    await safe_edit(event, f"🟢 {as_key} روشن ({format_interval_short(as_cfg['interval'])})."); return
                if text == f"{CMD}{as_key} خاموش":
                    matched_auto = True
                    if not auto_send_status.get(user_id, {}).get(as_key):
                        await safe_edit(event, "⚠️ خاموش."); return
                    stop_auto_send(user_id, as_key)
                    await safe_edit(event, f"🔴 {as_key} خاموش."); return
            if matched_auto: return
            # انتقال
            if text.startswith(f"{CMD}انتقال تنظیم"):
                raw = text.replace(f"{CMD}انتقال تنظیم", "", 1).strip()
                parts = raw.split()
                if len(parts) != 2:
                    await safe_edit(event, f"❌ {CMD}انتقال تنظیم <C_ID> <مبلغ>"); return
                c_id_str, amount_str = parts
                c_id_clean = normalize_digits(c_id_str).replace(",", "").strip()
                if not c_id_clean.isdigit() or not (1 <= len(c_id_clean) <= 5):
                    await safe_edit(event, "❌ C_ID باید بین ۱ تا ۵ رقم باشد."); return
                amount = parse_money_amount(amount_str)
                if not amount or amount <= 0:
                    await safe_edit(event, "❌ مبلغ. مثال: 100k"); return
                old = transfer_configs.get(user_id, {})
                old_task = old.get("task")
                if old_task and not old_task.done(): old_task.cancel()
                transfer_configs[user_id] = {"c_id": c_id_clean, "desired": amount,
                    "enabled": False, "task": None, "mode": "fast"}
                schedule_save_runtime()
                await safe_edit(event, f"✅ تنظیم شد.\n👤 {c_id_clean}\n💰 {amount:,}\n💡 {CMD}انتقال روشن"); return
            if text == f"{CMD}انتقال روشن":
                if user_id not in transfer_configs or not transfer_configs[user_id].get("c_id"):
                    await safe_edit(event, f"❌ اول {CMD}انتقال تنظیم"); return
                if transfer_configs[user_id].get("enabled"):
                    await safe_edit(event, "⚠️ روشن."); return
                transfer_configs[user_id]["enabled"] = True
                transfer_configs[user_id]["mode"] = "fast"
                transfer_configs[user_id]["task"] = asyncio.create_task(transfer_scheduler(user_id))
                schedule_save_runtime()
                await safe_edit(event, "🟢 انتقال روشن."); return
            if text == f"{CMD}انتقال خاموش":
                if user_id not in transfer_configs:
                    await safe_edit(event, "⚠️ خاموش."); return
                stop_transfer(user_id)
                await safe_edit(event, "🔴 خاموش شد."); return

            if text == f"{CMD}لیست انتقال کالا":
                cfg = transfer_items_config.get(user_id, {})
                rules = cfg.get("rules", [])
                if not rules:
                    await safe_edit(event, "📭 لیست خالی است."); return
                lines = ["📋 <b>لیست انتقال کالاها:</b>"]
                for i, r in enumerate(rules, 1):
                    icon = "🟢" if r.get("enabled", True) else "🔴"
                    lines.append(f"{i}. {icon} 🎁 {r['material']} | 🔢 {r['quantity'] if r['quantity']>0 else 'همه'} | 👤 {r['cid']}")
                await safe_edit(event, "\n".join(lines), parse_mode="html")
                return

            if text.startswith(f"{CMD}افزودن انتقال کالا "):
                raw = text.replace(f"{CMD}افزودن انتقال کالا ", "", 1).strip()
                parts = raw.split()
                if len(parts) < 3:
                    await safe_edit(event, f"❌ فرمت: {CMD}افزودن انتقال کالا [آیدی ۴ رقمی] [نام کالا] [تعداد]"); return
                cid = normalize_digits(parts[0])
                qty_str = normalize_digits(parts[-1])
                name = " ".join(parts[1:-1])
                if not cid.isdigit() or not (1 <= len(cid) <= 5):
                    await safe_edit(event, "❌ آیدی باید بین ۱ تا ۵ رقم باشد."); return
                if not qty_str.isdigit():
                    await safe_edit(event, "❌ تعداد باید عدد باشد. (0 برای همه)"); return
                cfg = transfer_items_config.setdefault(user_id, {"enabled": False, "rules": []})
                cfg["rules"].append({"cid": cid, "material": name, "quantity": int(qty_str), "enabled": True})
                schedule_save_runtime()
                await safe_edit(event, f"✅ اضافه شد:\n🎁 {name} ➡️ {cid}\n🔢 {qty_str if qty_str!='0' else 'همه'}")
                return

            if text.startswith(f"{CMD}حذف انتقال کالا "):
                raw = text.replace(f"{CMD}حذف انتقال کالا ", "", 1).strip()
                parts = raw.split()
                if len(parts) < 2:
                    await safe_edit(event, f"❌ فرمت: {CMD}حذف انتقال کالا [آیدی] [نام کالا]"); return
                cid = normalize_digits(parts[0])
                name = " ".join(parts[1:])
                cfg = transfer_items_config.get(user_id, {})
                rules = cfg.get("rules", [])
                new_rules = [r for r in rules if not (r["cid"] == cid and name in r["material"])]
                if len(new_rules) == len(rules):
                    await safe_edit(event, "❌ چنین قانونی پیدا نشد."); return
                cfg["rules"] = new_rules
                schedule_save_runtime()
                await safe_edit(event, "✅ حذف شد.")
                return

            if text == f"{CMD}انتقال کالا روشن":
                cfg = transfer_items_config.setdefault(user_id, {"enabled": False, "rules": []})
                if cfg.get("enabled"):
                    await safe_edit(event, "⚠️ از قبل روشنه."); return
                cfg["enabled"] = True
                schedule_save_runtime()
                _ensure_transfer_scheduler(user_id, "item")
                if not sell_mode_users.get(user_id, {}).get("enabled"):
                    async def _run_imm_item_cmd(uid):
                        async with get_user_lock(uid):
                            if not sell_mode_users.get(uid, {}).get("enabled"):
                                await execute_item_transfers(uid)
                    _spawn(_run_imm_item_cmd(user_id))
                await safe_edit(event, "🟢 انتقال کالا روشن شد.\n💡 خاموش: " + CMD + "انتقال کالا خاموش")
                return
                
            if text == f"{CMD}انتقال کالا خاموش":
                cfg = transfer_items_config.get(user_id, {})
                if not cfg.get("enabled"):
                    await safe_edit(event, "⚠️ از قبل خاموشه."); return
                cfg["enabled"] = False
                schedule_save_runtime()
                await safe_edit(event, "🔴 انتقال کالا خاموش شد.")
                return

            if text.startswith(f"{CMD}افزودن انتقال کالا "):
                raw = text.replace(f"{CMD}افزودن انتقال کالا ", "", 1).strip()
                parts = raw.split()
                if len(parts) < 3:
                    await safe_edit(event, f"❌ فرمت: {CMD}افزودن انتقال کالا [آیدی ۴ رقمی] [نام کالا] [تعداد]"); return
                cid = normalize_digits(parts[0])
                qty_str = normalize_digits(parts[-1])
                name = " ".join(parts[1:-1])
                if not cid.isdigit() or not (1 <= len(cid) <= 5):
                    await safe_edit(event, "❌ آیدی باید بین ۱ تا ۵ رقم باشد."); return
                if not qty_str.isdigit():
                    await safe_edit(event, "❌ تعداد باید عدد باشد. (0 برای همه)"); return
                cfg = transfer_items_config.setdefault(user_id, {"enabled": False, "rules": []})
                cfg["rules"].append({"cid": cid, "material": name, "quantity": int(qty_str), "enabled": True})
                schedule_save_runtime()
                await safe_edit(event, f"✅ اضافه شد:\n🎁 {name} ➡️ {cid}\n🔢 {qty_str if qty_str!='0' else 'همه'}")
                return
                
            if text == f"{CMD}لیست انتقال کالا":
                cfg = transfer_items_config.get(user_id, {})
                rules = cfg.get("rules", [])
                if not rules:
                    await safe_edit(event, "📭 لیست خالی است."); return
                lines = ["📋 <b>لیست انتقال کالاها:</b>"]
                for i, r in enumerate(rules, 1):
                    icon = "🟢" if r.get("enabled", True) else "🔴"
                    lines.append(f"{i}. {icon} 🎁 {r['material']} | 🔢 {r['quantity'] if r['quantity']>0 else 'همه'} | 👤 {r['cid']}")
                await safe_edit(event, "\n".join(lines), parse_mode="html")
                return

            if text == f"{CMD}انتقال مواد روشن":
                cfg = transfer_materials_config.setdefault(user_id, {"enabled": False, "rules": []})
                if cfg.get("enabled"):
                    await safe_edit(event, "⚠️ از قبل روشنه."); return
                cfg["enabled"] = True
                schedule_save_runtime()
                _ensure_transfer_scheduler(user_id, "material")
                if not sell_mode_users.get(user_id, {}).get("enabled"):
                    async def _run_immediate_transfer(uid):
                        async with get_user_lock(uid):
                            if not sell_mode_users.get(uid, {}).get("enabled"):
                                await execute_material_transfers(uid)
                    _spawn(_run_immediate_transfer(user_id))
                await safe_edit(event, "🟢 انتقال مواد روشن شد.\n💡 خاموش کردن: " + CMD + "انتقال مواد خاموش")
                return
                
            if text == f"{CMD}انتقال مواد خاموش":
                cfg = transfer_materials_config.get(user_id, {})
                if not cfg.get("enabled"):
                    await safe_edit(event, "⚠️ از قبل خاموشه."); return
                cfg["enabled"] = False
                schedule_save_runtime()
                await safe_edit(event, "🔴 انتقال مواد خاموش شد.")
                return
            # طبقات
            if text == f"{CMD}طبقات":
                on = is_floor_test_enabled(user_id)
                mf = get_max_fails(user_id)
                await safe_edit(event,
                    f"🏰 تنظیمات تست طبقه\n━━━━━━━━━━━━━━━━━\n"
                    f"وضعیت: {'🟢 روشن' if on else '🔴 خاموش'}\n"
                    f"💀 مرگ قبل جابه‌جایی: {mf}\n━━━━━━━━━━━━━━━━━\n"
                    f"{CMD}طبقات روشن / {CMD}طبقات خاموش\n"
                    f"{CMD}مرگ <عدد>  (1 تا 10)\n"
                    f"{CMD}تست طبقه <شماره>")
                return
            if text == f"{CMD}طبقات روشن":
                if is_floor_test_enabled(user_id):
                    await safe_edit(event, "⚠️ از قبل روشنه."); return
                save_floor_test(user_id, True)
                await safe_edit(event, "🟢 جابه‌جایی خودکار طبقه روشن شد."); return
            if text == f"{CMD}طبقات خاموش":
                if not is_floor_test_enabled(user_id):
                    await safe_edit(event, "⚠️ از قبل خاموشه."); return
                save_floor_test(user_id, False)
                await safe_edit(event, f"🔴 جابه‌جایی خودکار خاموش شد.\n💡 تست دستی: {CMD}تست طبقه <شماره>"); return
            if text.startswith(f"{CMD}مرگ "):
                arg = text.replace(f"{CMD}مرگ", "", 1).strip()
                arg_n = normalize_digits(arg).split()[0] if arg else ""
                if not arg_n.isdigit():
                    await safe_edit(event, f"❌ {CMD}مرگ <عدد>  (1 تا 10)"); return
                n = int(arg_n)
                if n < 1 or n > 10:
                    await safe_edit(event, "❌ عدد بین ۱ و ۱۰."); return
                save_max_fails(user_id, n)
                await safe_edit(event, f"✅ مرگ قبل جابه‌جایی → {n}"); return
            if text == f"{CMD}تست طبقه" or text.startswith(f"{CMD}تست طبقه "):
                arg = text.replace(f"{CMD}تست طبقه", "", 1).strip()
                if not arg:
                    await safe_edit(event, f"❌ {CMD}تست طبقه <شماره>"); return
                arg_n = normalize_digits(arg).split()[0]
                if not arg_n.isdigit():
                    await safe_edit(event, "❌ شماره عدد باشه."); return
                target = int(arg_n)
                await safe_edit(event, f"🔄 تست طبقه {target}...\n📋 نتیجه تو پیوی میاد.")
                _spawn(_manual_floor_test(user_id, target)); return
            # خروج
            if text == f"{CMD}خروج از اکانت":
                sp = SESSION_DIR / str(user_id)
                if os.path.exists(str(sp) + ".session"):
                    try: os.remove(str(sp) + ".session")
                    except: pass
                set_user_active(user_id, False)
                set_user_locally_disabled(user_id, False)
                stop_sell_mode(user_id); stop_all_auto_sends(user_id)
                stop_transfer(user_id); stop_daily_gift(user_id)
                stop_all_pony_for_user(user_id); stop_all_dungeon_for_user(user_id)
                stop_all_pew_ring_for_user(user_id)
                stop_all_pew_target_for_user(user_id)
                stop_all_pew_dog_for_user(user_id)
                await stop_all_user_banners(user_id); cancel_user_battle_tasks(user_id)
                await disconnect_user_client(user_id)
                await safe_edit(event, "🚪 خارج شدی.\n/login"); return
            # مالک
            if text.startswith(f"{CMD}تحریم ") and is_grp_owner(user_id):
                parts = normalize_digits(text).split()
                if len(parts) == 2:
                    try:
                        target = int(parts[1])
                        if target == OWNER_ID:
                            await safe_edit(event, "⚠️ مالک."); return
                        _ensure_user(str(target))
                        users_db["users"][str(target)]["banned"] = True
                        users_db["users"][str(target)]["active"] = False
                        save_json(USERS_FILE, users_db)
                        stop_sell_mode(target); stop_all_auto_sends(target)
                        stop_transfer(target); stop_daily_gift(target)
                        stop_all_pony_for_user(target); stop_all_dungeon_for_user(target)
                        stop_all_pew_ring_for_user(target); stop_all_pew_target_for_user(target)
                        stop_all_pew_dog_for_user(target)
                        await stop_all_user_banners(target)
                        cancel_user_battle_tasks(target)
                        await disconnect_user_client(target)
                        await safe_edit(event, f"⛔ {target} تحریم.")
                    except: await safe_edit(event, "❌ آیدی.")
                return
            # ─── اجازه TTL ───
            if text == f"{CMD}اجازه" or text.startswith(f"{CMD}اجازه "):
                if not is_grp_owner(user_id):
                    await safe_edit(event, "❌ فقط مالک."); return
                arg = text.replace(f"{CMD}اجازه", "", 1).strip()
                client = await ensure_user_client(user_id)
                if not client: await safe_edit(event, "🔌 اتصال نیست."); return
                target = await resolve_user_arg(event, client, arg)
                if not target:
                    await safe_edit(event,
                        f"❌ .{CMD}اجازه &lt;آیدی/یوزرنیم&gt;\n"
                        f"یا ریپلای + <code>.{CMD}اجازه</code>"); return
                if is_grp_owner(target):
                    await safe_edit(event, "⚠️ مالک از قبل دسترسی داره."); return
                set_media_allowed(target, True)
                nm = await get_plain_name(client, target)
                await safe_edit(event,
                    f"✅ دسترسی TTL/ذخیره داده شد\n"
                    f"👤 {nm}\n🆔 <code>{target}</code>", parse_mode="html"); return

            # ─── لغو اجازه ───
            if text == f"{CMD}لغو اجازه" or text.startswith(f"{CMD}لغو اجازه "):
                if not is_grp_owner(user_id):
                    await safe_edit(event, "❌ فقط مالک."); return
                arg = text.replace(f"{CMD}لغو اجازه", "", 1).strip()
                client = await ensure_user_client(user_id)
                if not client: await safe_edit(event, "🔌 اتصال نیست."); return
                target = await resolve_user_arg(event, client, arg)
                if not target:
                    await safe_edit(event,
                        f"❌ .{CMD}لغو اجازه &lt;آیدی/یوزرنیم&gt;\n"
                        f"یا ریپلای + <code>.{CMD}لغو اجازه</code>"); return
                set_media_allowed(target, False)
                nm = await get_plain_name(client, target)
                await safe_edit(event,
                    f"🔴 دسترسی گرفته شد\n"
                    f"👤 {nm}\n🆔 <code>{target}</code>", parse_mode="html"); return

            # ─── لیست اجازه ───
            if text == f"{CMD}لیست اجازه":
                if not is_grp_owner(user_id):
                    await safe_edit(event, "❌ فقط مالک."); return
                users = get_media_allowed_users()
                if not users:
                    await safe_edit(event,
                        f"📭 لیست خالیه\n\n"
                        f"💡 .{CMD}اجازه &lt;user&gt;"); return
                client = await ensure_user_client(user_id)
                lines = [f"📋 کاربران مجاز ({len(users)}):", "━━━━━━━━━━━━━━━━━"]
                for i, u in enumerate(users, 1):
                    try: nm = await get_plain_name(client, u) if client else str(u)
                    except: nm = str(u)
                    lines.append(f"{i}. {nm} — <code>{u}</code>")
                lines.append("")
                lines.append(f"💡 حذف: .{CMD}لغو اجازه &lt;user&gt;")
                await safe_edit(event, "\n".join(lines), parse_mode="html"); return

            # ═══ دستورات مالک ═══
            if text == f"{CMD}تحریم" or text.startswith(f"{CMD}تحریم "):
                if not is_grp_owner(user_id):
                    await safe_edit(event, "❌ فقط مالک."); return
                arg = text.replace(f"{CMD}تحریم", "", 1).strip()
                client = await ensure_user_client(user_id)
                if not client: await safe_edit(event, "🔌 اتصال نیست."); return
                target = await resolve_user_arg(event, client, arg)
                if not target:
                    await safe_edit(event,
                        f"❌ .{CMD}تحریم &lt;آیدی/یوزرنیم&gt;\n"
                        f"یا ریپلای + <code>.{CMD}تحریم</code>"); return
                if is_grp_owner(target):
                    await safe_edit(event, "⚠️ مالک."); return
                _ensure_user(str(target))
                users_db["users"][str(target)]["banned"] = True
                users_db["users"][str(target)]["active"] = False
                save_json(USERS_FILE, users_db)
                stop_sell_mode(target); stop_all_auto_sends(target)
                stop_transfer(target); stop_daily_gift(target)
                stop_all_pony_for_user(target); stop_all_dungeon_for_user(target)
                stop_all_pew_ring_for_user(target); stop_all_pew_target_for_user(target)
                stop_all_pew_dog_for_user(target)
                await stop_all_user_banners(target)
                cancel_user_battle_tasks(target)
                await disconnect_user_client(target)
                nm = await get_plain_name(client, target)
                await safe_edit(event,
                    f"⛔ کاربر تحریم شد\n👤 {nm}\n🆔 <code>{target}</code>",
                    parse_mode="html"); return

            if text == f"{CMD}رفع تحریم" or text.startswith(f"{CMD}رفع تحریم "):
                if not is_grp_owner(user_id):
                    await safe_edit(event, "❌ فقط مالک."); return
                arg = text.replace(f"{CMD}رفع تحریم", "", 1).strip()
                client = await ensure_user_client(user_id)
                if not client: await safe_edit(event, "🔌 اتصال نیست."); return
                target = await resolve_user_arg(event, client, arg)
                if not target:
                    await safe_edit(event,
                        f"❌ .{CMD}رفع تحریم &lt;آیدی/یوزرنیم&gt;\n"
                        f"یا ریپلای + <code>.{CMD}رفع تحریم</code>"); return
                _ensure_user(str(target))
                users_db["users"][str(target)]["banned"] = False
                save_json(USERS_FILE, users_db)
                nm = await get_plain_name(client, target)
                await safe_edit(event,
                    f"🟢 کاربر از تحریم خارج شد\n👤 {nm}\n🆔 <code>{target}</code>",
                    parse_mode="html"); return

            if text == f"{CMD}اجازه" or text.startswith(f"{CMD}اجازه "):
                if not is_grp_owner(user_id):
                    await safe_edit(event, "❌ فقط مالک."); return
                arg = text.replace(f"{CMD}اجازه", "", 1).strip()
                client = await ensure_user_client(user_id)
                if not client: await safe_edit(event, "🔌 اتصال نیست."); return
                target = await resolve_user_arg(event, client, arg)
                if not target:
                    await safe_edit(event,
                        f"❌ .{CMD}اجازه &lt;آیدی/یوزرنیم&gt;\n"
                        f"یا ریپلای + <code>.{CMD}اجازه</code>"); return
                if is_grp_owner(target):
                    await safe_edit(event, "⚠️ مالک از قبل دسترسی داره."); return
                set_media_allowed(target, True)
                nm = await get_plain_name(client, target)
                await safe_edit(event,
                    f"✅ دسترسی TTL/ذخیره داده شد\n"
                    f"👤 {nm}\n🆔 <code>{target}</code>", parse_mode="html"); return

            if text == f"{CMD}منع" or text.startswith(f"{CMD}منع "):
                if not is_grp_owner(user_id):
                    await safe_edit(event, "❌ فقط مالک."); return
                arg = text.replace(f"{CMD}منع", "", 1).strip()
                client = await ensure_user_client(user_id)
                if not client: await safe_edit(event, "🔌 اتصال نیست."); return
                target = await resolve_user_arg(event, client, arg)
                if not target:
                    await safe_edit(event,
                        f"❌ .{CMD}منع &lt;آیدی/یوزرنیم&gt;\n"
                        f"یا ریپلای + <code>.{CMD}منع</code>"); return
                set_media_allowed(target, False)
                nm = await get_plain_name(client, target)
                await safe_edit(event,
                    f"🚫 دسترسی گرفته شد\n"
                    f"👤 {nm}\n🆔 <code>{target}</code>", parse_mode="html"); return

            if text == f"{CMD}لیست اجازه":
                if not is_grp_owner(user_id):
                    await safe_edit(event, "❌ فقط مالک."); return
                users = get_media_allowed_users()
                if not users:
                    await safe_edit(event,
                        f"📭 لیست خالیه\n\n"
                        f"💡 .{CMD}اجازه &lt;user&gt;"); return
                client = await ensure_user_client(user_id)
                lines = [f"📋 کاربران مجاز ({len(users)}):", "━━━━━━━━━━━━━━━━━"]
                for i, u in enumerate(users, 1):
                    try: nm = await get_plain_name(client, u) if client else str(u)
                    except: nm = str(u)
                    lines.append(f"{i}. {nm} — <code>{u}</code>")
                lines.append("")
                lines.append(f"💡 حذف: .{CMD}منع &lt;user&gt;")
                await safe_edit(event, "\n".join(lines), parse_mode="html"); return

            if text == f"{CMD}ویژه" and is_grp_owner(user_id):
                client = await ensure_user_client(user_id)
                if client: await panel_owner_dashboard(event, user_id, client)
                return
            if text == f"{CMD}کاربران" and is_grp_owner(user_id):
                try:
                    t, kb = await _pm_build_users_full(user_id, 0)
                    await event.edit(t, buttons=kb)
                except Exception as e:
                    log_error(f"pm users cmd: {_translate_bot_errors(e)}")
                    try: await event.respond(_translate_bot_errors(e))
                    except: pass
                return
            if text == f"{CMD}پیام همگانی" and is_grp_owner(user_id):
                broadcast_waiting[user_id] = True
                await safe_edit(event, "📢 پیام بفرست یا ریپلای کن.\nلغو: هر دستوری با ویرگول.")
                return
            if text == f"{CMD}پینگ":
                if not (is_grp_owner(user_id) or is_manager(user_id)):
                    await safe_edit(event, "❌ دسترسی."); return
                client = await ensure_user_client(user_id)
                if not client: await safe_edit(event, "🔌 اتصال نیست."); return
                await panel_ping(event, client); return
            # لغو
            if text in (f"{CMD}لغو", f"{CMD}کنسل", f"{CMD}cancel"):
                had = False
                if user_id in pm_banner_states:
                    pm_banner_states.pop(user_id, None); had = True
                if user_id in login_states:
                    st = login_states.pop(user_id, None)
                    if st and st.get("client"):
                        try: await st["client"].disconnect()
                        except: pass
                    had = True
                if user_id in broadcast_waiting:
                    broadcast_waiting.pop(user_id, None); had = True
                await safe_edit(event, "✅ لغو شد." if had else "ℹ️ چیزی برای لغو نبود.")
                return
            if text == f"{CMD}دستورات":
                tool_parts = "فونت، استایل"
                if is_media_allowed(user_id): tool_parts += "، TTL، ذخیره"
                help_lines = [
                    "📚 <b>دستورات پرکاربرد</b>", "━━━━━━━━━━━━━━━━━",
                    f"🎛 <code>{CMD}پنل</code> — پنل شیشه‌ای",
                    f"🎮 <code>{CMD}پنل بازی</code> — بخش بازی‌ها",
                    f"⚔️ <code>{CMD}پنل کاردینال</code> · 🐴 <code>{CMD}پنل پونی</code>",
                    f"🔫 <code>{CMD}پنل پیو</code> · 📢 <code>{CMD}پنل تبچی</code>",
                    f"🛠 <code>{CMD}پنل ابزار</code> — {tool_parts}",
                    f"📊 <code>{CMD}وضعیت</code> — وضعیت قابلیت‌ها",
                    f"📚 <code>{CMD}راهنما</code> — راهنمای اصلی",
                ]
                if is_media_allowed(user_id):
                    help_lines.extend([
                        "━━━━━━━━━━━━━━━━━",
                        "🔥 <b>TTL — ذخیرهٔ خودکار رسانه‌های ناپدیدشونده</b>",
                        f"<code>{CMD}تی تی ال</code> — دیدن وضعیت و مقصد",
                        f"<code>{CMD}تی تی ال روشن</code> — روشن‌کردن ذخیرهٔ خودکار",
                        f"<code>{CMD}تی تی ال خاموش</code> — خاموش‌کردن",
                        f"<code>{CMD}تی تی ال هدف</code> — انتخاب همین گفتگو به‌عنوان مقصد",
                        "📥 <b>ذخیرهٔ دستی</b>",
                        f"ریپلای روی رسانه + <code>{CMD}ذخیره</code>؛ یا <code>{CMD}ذخیره &lt;لینک&gt;</code>",
                    ])
                help_lines.extend([
                    "━━━━━━━━━━━━━━━━━",
                    f"🔙 <code>{CMD}لغو</code> — لغو عملیات",
                    f"🚪 <code>{CMD}خروج از اکانت</code>",
                ])
                await safe_edit(event, "\n".join(help_lines), parse_mode="html")
                return
            # پیشنهاد فرمان‌ها؛ دستورات رسانه‌ای برای حساب بدون مجوز پنهان می‌مانند.
            if text and text.startswith(CMD) and len(text) > len(CMD):
                raw = text[len(CMD):].strip()
                if raw:
                    hints = COMMAND_HINTS
                    if not is_media_allowed(user_id):
                        media_commands = {"تی تی ال", "تی تی ال روشن", "تی تی ال خاموش", "تی تی ال هدف", "ذخیره"}
                        hints = [command for command in COMMAND_HINTS if command not in media_commands]
                    matches = get_close_matches(raw, hints, n=3, cutoff=0.45)
                    if matches:
                        hint = "\n".join([f"   • {CMD}{m}" for m in matches])
                        await safe_edit(event, f"❓ «{CMD}{raw}» پیدا نشد\n💡 شاید:\n{hint}")
                    else:
                        await safe_edit(event, f"❓ نامعتبر.\nراهنما: {CMD}راهنما")
                    return
        except Exception as e:
            log_error(f"user_handler {user_id}: {_translate_bot_errors(e)}")
            try: await safe_edit(event, f"❌ {_translate_bot_errors(e)}")
            except: pass
    return user_handler

# ═══════════════════════════════════════════════════════
# PM builders
# ═══════════════════════════════════════════════════════
def _cb(t, d): return types.KeyboardButtonCallback(t, data=d)

async def _pm_get_user_groups(uid, limit=200):
    client = user_clients.get(int(uid))
    if not client or not client.is_connected():
        client = await ensure_user_client(uid)
        if not client: return []
    groups = []
    try:
        async for d in client.iter_dialogs(limit=400):
            try: ent = d.entity
            except: ent = None
            is_real_group = False
            if d.is_group: is_real_group = True
            elif d.is_channel and getattr(ent, 'megagroup', False): is_real_group = True
            if not is_real_group: continue
            title = (d.title or str(d.id))[:60]
            groups.append({"id": d.id, "title": title})
            if len(groups) >= limit: break
    except: pass
    return groups

async def _pm_build_main(uid):
    up = int(time.time() - STATS_START_TIME)
    d, rem = divmod(up, 86400); h, rem = divmod(rem, 3600); m, _ = divmod(rem, 60)
    if d: up_str = f"{d}d {h}h"
    elif h: up_str = f"{h}h {m}m"
    else: up_str = f"{m}m"
    on_list = []; off_list = []
    sell_on = uid in sell_mode_users and sell_mode_users[uid].get("enabled")
    (on_list if sell_on else off_list).append("💰 فروش")
    shkar_on = auto_send_status.get(uid, {}).get("شکار", False)
    (on_list if shkar_on else off_list).append("🎯 شکار")
    siah_on = auto_send_status.get(uid, {}).get("سیاه", False)
    (on_list if siah_on else off_list).append("💀 سیاه")
    esc_on = is_escape_enabled(uid)
    (on_list if esc_on else off_list).append("🏃 فرار")
    ret_on = is_return_enabled(uid)
    (on_list if ret_on else off_list).append("🔙 برگشت")
    gift_on = daily_gift_status.get(uid, False)
    (on_list if gift_on else off_list).append("🎁 جایزه")
    transfer_on = uid in transfer_configs and transfer_configs[uid].get("enabled")
    (on_list if transfer_on else off_list).append("💸 انتقال")
    ft_on = is_floor_test_enabled(uid)
    (on_list if ft_on else off_list).append("🏰 تست‌طبقه")
    art_on = is_pew_art_enabled(uid)
    (on_list if art_on else off_list).append("🎨 پیوآرت")
    pony_c = sum(1 for k, v in pony_config.items() if k[0] == int(uid) and v.get("collect"))
    if pony_c: on_list.append(f"🐴 پونی×{pony_c}")
    naz_c = sum(1 for k, v in pony_config.items() if k[0] == int(uid) and v.get("naz_enabled"))
    if naz_c: on_list.append(f"💞 ناز خودکار×{naz_c}")
    dgn_c = sum(1 for k, v in dungeon_config.items() if k[0] == int(uid) and v.get("enabled"))
    if dgn_c: on_list.append(f"🏰 دانجن×{dgn_c}")
    ring_c = sum(1 for k, v in pew_ring_config.items() if k[0] == int(uid) and v.get("enabled"))
    if ring_c: on_list.append(f"🏋️ رینگ×{ring_c}")
    tgt_c = sum(1 for k, v in pew_target_config.items() if k[0] == int(uid) and v.get("enabled"))
    if tgt_c: on_list.append(f"🎯 هدف×{tgt_c}")
    dog_c = sum(1 for k, v in pew_dog_config.items() if k[0] == int(uid) and v.get("enabled"))
    if dog_c: on_list.append(f"🐕 سگ×{dog_c}")
    banners_active = sum(1 for _, b in get_user_banners(uid).items() if b.get("active"))
    if banners_active: on_list.append(f"📢 تبچی×{banners_active}")
    f_active = len(on_list)
    c = user_clients.get(int(uid))
    if c and c.is_connected():
        try:
            ok = await c.is_user_authorized()
            conn_str = "🟢 آنلاین" if ok else "🟡 ناشناس"
        except: conn_str = "🔴 قطع"
    else: conn_str = "🔴 قطع"
    info = users_db["users"].get(str(uid), {})
    name = html_lib.escape((info.get("name") or "—")[:18])
    lines = []
    lines.append("<b>🎛 پنل مدیریت</b>")
    lines.append("<code>━━━━━━━━━━━━━━━</code>")
    lines.append(f"👤 {name} · <code>{uid}</code>")
    lines.append(f"{conn_str} · ⏱ {up_str} · ⚙️ {f_active} فعال")
    lines.append("<code>━━━━━━━━━━━━━━━</code>")
    text = "\n".join(lines)
    kb = [
        [_cb("📊 وضعیت", "pn_status_panel")],
        [_cb("🎮 بازی", "pn_games")],
        [_cb("📢 تبچی", "pn_banner_main")],
        [_cb("⚙️ تنظیمات", "pn_settings")],
        [_cb("🛠 ابزارها", "pn_tools")],
        [_cb("🟡 بروزرسانی 🔄", "pn_refresh")],
    ]
    if is_grp_owner(uid):
        kb.append([_cb("👑 پنل مالک", "pn_owner")])
    elif is_manager(uid):
        kb.append([_cb("👮 مدیر", "pn_owner")])
    kb.append([_cb("🔴 بستن پنل", "pn_close")])
    return text, kb

async def _pm_build_status_panel(uid):
    uid = int(uid)
    sell_on = uid in sell_mode_users and sell_mode_users[uid].get("enabled", False)
    shkar_on = auto_send_status.get(uid, {}).get("شکار", False)
    siah_on = auto_send_status.get(uid, {}).get("سیاه", False)
    esc_on = is_escape_enabled(uid)
    ret_on = is_return_enabled(uid)
    gift_on = daily_gift_status.get(uid, False)
    transfer_on = transfer_configs.get(uid, {}).get("enabled", False)
    materials_on = transfer_materials_config.get(uid, {}).get("enabled", False)
    items_on = transfer_items_config.get(uid, {}).get("enabled", False)
    ft_on = is_floor_test_enabled(uid)

    pony_on = any(c.get("collect") for k, c in pony_config.items()
                  if k[0] == uid)
    naz_on = any(c.get("naz_enabled") for k, c in pony_config.items()
                 if k[0] == uid)
    dungeon_on = any(c.get("enabled") for k, c in dungeon_config.items()
                     if k[0] == uid)
    art_on = is_pew_art_enabled(uid)
    ring_on = any(v.get("enabled") for k, v in pew_ring_config.items()
                  if k[0] == uid)
    target_on = any(v.get("enabled") for k, v in pew_target_config.items()
                    if k[0] == uid)
    dog_on = any(v.get("enabled") for k, v in pew_dog_config.items()
                 if k[0] == uid)

    user_cfg = users_db.get("users", {}).get(str(uid), {})
    tools = [
        ("استایل HTML", user_cfg.get("html_style_on", False)),
        ("فونت انگلیسی", user_cfg.get("font_on", False)),
    ]
    if is_media_allowed(uid):
        tools.append(("ذخیرهٔ خودکار TTL", get_ttl_config(uid)["enabled"]))
    tools.extend([
        ("پایش پروفایل", monitor_db.get(str(uid), {}).get("enabled", False)),
        ("چرخش ایموجی اسم", get_name_emoji_config(uid).get("enabled", False)),
        ("چرخش عکس پروفایل", get_random_profile_config(uid).get("enabled", False)),
    ])

    banners = get_user_banners(uid)
    active_banners = [name for name, cfg in banners.items() if cfg.get("active")]

    client = user_clients.get(uid)
    if client and client.is_connected():
        try:
            connected = await client.is_user_authorized()
            conn_str = "آنلاین" if connected else "نیازمند ورود"
        except Exception:
            conn_str = "وضعیت نامشخص"
    else:
        conn_str = "قطع"
    uptime = format_interval_persian(int(time.time() - STATS_START_TIME))
    uptime = uptime.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))

    lines = [
        "📊 <b>وضعیت قابلیت‌ها</b>",
        "━━━━━━━━━━━━━━━━━",
        f"🔌 اتصال اکانت: <b>{conn_str}</b>",
        f"⏱ مدت اجرای ربات: <b>{uptime}</b>",
        "━━━━━━━━━━━━━━━━━",
    ]

    def add_status_group(title, features):
        enabled = [name for name, state in features if state]
        disabled = [name for name, state in features if not state]
        lines.append("")
        lines.append(f"<b>{title}</b>")
        lines.append("🟢 روشن: " + ("، ".join(enabled) if enabled else "—"))
        lines.append("🔴 خاموش: " + ("، ".join(disabled) if disabled else "—"))

    add_status_group("⚔️ کاردینال", [
        ("فروش", sell_on), ("شکار", shkar_on), ("سیاه‌چال", siah_on),
        ("فرار", esc_on), ("برگشت", ret_on), ("جایزه", gift_on),
        ("انتقال", transfer_on), ("انتقال مواد", materials_on),
        ("انتقال کالا", items_on), ("تست طبقه", ft_on),
    ])
    add_status_group("🐴 پونی‌لند", [
        ("پونی", pony_on), ("ناز خودکار", naz_on), ("دانجن", dungeon_on),
    ])
    add_status_group("🔫 پیوپیو", [
        ("شکار فن‌آرت", art_on), ("پیو رینگ", ring_on),
        ("پیو هدف", target_on), ("پیو سگ", dog_on),
    ])
    add_status_group("🧰 ابزارها", tools)

    lines.append("")
    lines.append("<b>📢 تبچی</b>")
    if active_banners:
        count = str(len(active_banners)).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))
        lines.append(f"🟢 روشن: {count} بنر فعال")
    else:
        lines.append("🔴 خاموش: بنری در حال ارسال نیست")
    lines.append("━━━━━━━━━━━━━━━━━")

    text = "\n".join(lines)
    kb = [
        [_cb("🔄 بروزرسانی وضعیت", "pn_status_panel")],
        [_cb("⚪ 🔙 بازگشت", "pn_refresh")],
    ]
    return text, kb

async def _pm_build_games(uid):
    active = []
    if any(c.get("collect") for k, c in pony_config.items() if k[0] == int(uid)): active.append("🐴 پونی")
    if any(c.get("enabled") for k, c in dungeon_config.items() if k[0] == int(uid)): active.append("🏰 دانجن")
    if is_pew_art_enabled(uid): active.append("🎯 شکار آرت")
    if any(v.get("enabled") for k, v in pew_ring_config.items() if k[0] == int(uid)): active.append("🏋️ پیو رینگ")
    active_str = " · ".join(active) if active else "—"
    text = (
        "🎮 بازی\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"🟢 فعال: {active_str}\n"
        "━━━━━━━━━━━━━━━━━\n"
        "👇 یکی رو انتخاب کن:"
    )
    # Isolate Latin labels from the surrounding RTL interface so emojis stay with their button.
    kb = [
        [_cb("\u2066Cardinal⚔️\u2069", "pn_cardinal_panel")],
        [_cb("\u2066Pony🐴\u2069", "pn_pony_main")],
        [_cb("\u2066PewPew🔫\u2069", "pn_pew_panel")],
        [_cb("⚪ 🔙 بازگشت", "pn_refresh")],
    ]
    return text, kb



async def _pm_build_cardinal_panel(uid):
    sell_on = uid in sell_mode_users and sell_mode_users[uid].get("enabled")
    esc_on = is_escape_enabled(uid)
    gift_on = daily_gift_status.get(uid, False)
    shkar_on = auto_send_status.get(uid, {}).get("شکار", False)
    siah_on = auto_send_status.get(uid, {}).get("سیاه", False)
    ft_on = is_floor_test_enabled(uid)
    ft_max = get_max_fails(uid)
    lines = ["⚔ کاردینال", "━━━━━━━━━━━━━━━━━", "👇 یه بخش انتخاب کن:"]
    kb = [
        [_cb(f"{'🟢' if sell_on else '🔴'} 💰 فروش", "pn_sell_toggle"),
         _cb("🔵 🚫 نفروش", "pn_nosell_panel")],
        [_cb(f"{'🟢' if shkar_on else '🔴'} 🎯 شکار", "pn_shkar_toggle"),
         _cb(f"{'🟢' if siah_on else '🔴'} 💀 سیاه", "pn_siah_toggle")],
        [_cb(f"{'🟢' if esc_on else '🔴'} 🏃 فرار", "pn_esc_toggle"),
         _cb("🔙 پنل برگشت", "pn_return_panel")],
        [_cb(f"{'🟢' if fishing_status.get(uid, False) else '🔴'} 🎣 ماهی‌گیری", "pn_fishing_toggle"), _cb(f"{'🟢' if gift_on else '🔴'} 🎁 جایزه", "pn_gift_toggle")],
        [_cb("💸 بخش انتقال", "pn_transfer_menu")],
        [_cb(f"{'🟢' if ft_on else '🔴'} 🏰 تست طبقه", "pn_floortest_toggle")],
        [_cb(f"🔵 💀 مرگ: {ft_max}", "pn_floortest_max")],
        [_cb("🔵 ⚔ نبرد و حمله", "pn_war_panel")],
        [_cb("⚪ 🔙 بازگشت", "pn_games")],
    ]
    return "\n".join(lines), kb

async def _pm_build_floortest_max_panel(uid):
    cur = get_max_fails(uid)
    bar = ""
    for i in range(1, 11):
        bar += "🟥" if i <= cur else "⬛️"
    text = (
        "💀 تنظیم مرگ قبل جابه‌جایی\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"📊 مقدار فعلی: <b>{cur}</b>\n"
        f"{bar}\n"
        "━━━━━━━━━━━━━━━━━\n"
        "💡 هر چند بار باخت پشت سر هم →\n"
        "   بره طبقه پایین‌تر تست کنه\n"
        "━━━━━━━━━━━━━━━━━\n"
        "📌 مقدار بین ۱ تا ۱۰"
    )
    kb = [
        [_cb("➖ کم کن", "pn_ftmax_dec"),
         _cb(f"🎯 {cur}", "pn_noop"),
         _cb("➕ زیاد کن", "pn_ftmax_inc")],
        [_cb("🟢 ✅ تایید و بازگشت", "pn_ftmax_save")],
        [_cb("⚪ 🔙 بازگشت بدون ذخیره", "pn_cardinal_panel")],
    ]
    return text, kb

async def _pm_build_war_panel(uid):
    lines = ["⚔ نبرد و حمله", "━━━━━━━━━━━━━━━━━", "👇 یه بخش انتخاب کن:"]
    kb = [
        [_cb("🔵 🏰 فتح طبقه", "pn_war_battle")],
        [_cb("🔵 🗡 حمله تیمی", "pn_war_attack")],
        [_cb("🔵 🛡 دفاع تیمی", "pn_war_defense")],
        [_cb("⚪ 🔙 بازگشت", "pn_cardinal_panel")],
    ]
    return "\n".join(lines), kb

async def _pm_build_war_battle(uid):
    text = (
        "🏰 فتح طبقه\n━━━━━━━━━━━━━━━━━\n"
        "🎯 کاربرد:\n"
        "تیمی می‌ری یه طبقه بالاتر و با غول‌ها می‌جنگی.\n"
        "فرمانده فراخوان می‌زنه، یارها ملحق می‌شن، بعد نبرد شروع می‌شه.\n"
        "━━━━━━━━━━━━━━━━━\n"
        "📋 دستورات (توی گروه مقصد):\n\n"
        f"👑 فرمانده شدن:\n   {CMD}فرمانده\n\n"
        f"📢 فراخوان زدن:\n   {CMD}فراخوان\n   {CMD}فراخوان <شماره طبقه>\n\n"
        f"🤝 یار شدن:\n   روی پیام فرمانده ریپلای کن → {CMD}یار\n   {CMD}یار خارج ← خروج از تیم\n\n"
        f"🎯 کنترل یارها (فرمانده):\n   {CMD}همه طبقه <شماره>\n   {CMD}همه پراکندگی\n   {CMD}اخراج / {CMD}اخراج همه\n\n"
        f"⏹ خاموش کردن:\n   {CMD}فتح خاموش\n   {CMD}فرمانده خارج"
    )
    kb = [[_cb("⚪ 🔙 بازگشت", "pn_war_panel")]]
    return text, kb

async def _pm_build_war_attack(uid):
    text = (
        "🗡 حمله تیمی\n━━━━━━━━━━━━━━━━━\n"
        "🎯 به یه بازیکن (C_ID) تیمی حمله می‌کنی.\n"
        "━━━━━━━━━━━━━━━━━\n"
        "📋 دستورات (توی گروه مقصد):\n\n"
        f"🎬 ساختن تیم:\n   {CMD}حمله تیمی ایجاد <اسم>\n\n"
        f"✅ پیوستن:\n   {CMD}حمله تیمی روشن <اسم>\n   {CMD}حمله تیمی خاموش <اسم>  ← خروج\n\n"
        f"⚔️ حمله:\n   {CMD}حمله تیمی به &lt;اسم&gt; &lt;C_ID&gt;\n\n"
        f"📊 مشاهده:\n   {CMD}حمله تیمی لیست\n\n"
        "⚠️ حداکثر ۷ نفر تو هر تیم"
    )
    kb = [[_cb("⚪ 🔙 بازگشت", "pn_war_panel")]]
    return text, kb

async def _pm_build_war_defense(uid):
    text = (
        "🛡 دفاع تیمی\n━━━━━━━━━━━━━━━━━\n"
        "🎯 از یه طبقه خاص دفاع می‌کنی.\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"🛡 فعال‌سازی:\n   {CMD}دفاع تیمی <شماره طبقه>\n\n"
        f"🔹 باید اول فرمانده باشی:\n   {CMD}فرمانده\n\n"
        "💡 جریان کار:\n"
        "1️⃣ فرمانده طبقه رو تعیین می‌کنه\n"
        "2️⃣ ربات همه یارها رو می‌بره اون طبقه\n"
        "3️⃣ همه از شهر خارج می‌شن\n"
        "4️⃣ منتظر اعلان آبی\n"
        "5️⃣ اعلان که اومد → ربات همه رو ملحق می‌کنه"
    )
    kb = [[_cb("⚪ 🔙 بازگشت", "pn_war_panel")]]
    return text, kb

async def _pm_build_pew_panel(uid):
    art_on = pew_art_config.get(int(uid), {}).get("enabled", False)
    ring_count = sum(1 for k, v in pew_ring_config.items() if k[0] == int(uid) and v.get("enabled"))
    ring_total = sum(1 for k in pew_ring_config if k[0] == int(uid))
    tgt_count = sum(1 for k, v in pew_target_config.items() if k[0] == int(uid) and v.get("enabled"))
    tgt_total = sum(1 for k in pew_target_config if k[0] == int(uid))
    dog_count = sum(1 for k, v in pew_dog_config.items() if k[0] == int(uid) and v.get("enabled"))
    dog_total = sum(1 for k in pew_dog_config if k[0] == int(uid))
    text = (
        "پیو پیو 🔫\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"🎯 شکار آرت: {'🟢 روشن' if art_on else '🔴 خاموش'}\n"
        f"🏋️ پیو رینگ: {'🟢' if ring_count else '🔴'} {ring_count}/{ring_total}\n"
        f"🎯 هدف: {'🟢' if tgt_count else '🔴'} {tgt_count}/{tgt_total}\n"
        f"🐕 سگ: {'🟢' if dog_count else '🔴'} {dog_count}/{dog_total}\n"
        "━━━━━━━━━━━━━━━━━"
    )
    kb = [
        [_cb("🎯 شکار آرت", "pn_pew_art_panel")],
        [_cb("🏋️ پیو رینگ", "pn_pewring_master_panel")],
        [_cb("🛡 شکار گروهی", "pn_ghunt_panel")],
        [_cb("🐕 سگ", "pn_dog_master_panel")],
        [_cb("⚪ 🔙 بازگشت", "pn_games")],
    ]
    return text, kb

async def _pm_build_pew_art_panel(uid):
    on = pew_art_config.get(int(uid), {}).get("enabled", False)
    stats = pew_art_stats.get(int(uid), {"grabbed": 0, "missed": 0})
    text = (
        "🎯 شکار آرت\n━━━━━━━━━━━━━━━━━\n"
        f"وضعیت: {'🟢 روشن' if on else '🔴 خاموش'}\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"🎉 گرفتی: {stats['grabbed']}\n🕸 دیر رسیدی: {stats['missed']}\n"
        "━━━━━━━━━━━━━━━━━\n"
        "وقتی روشنه، در هر گروه پیام‌هایی مثل\n«یه فن‌آرت جدید اومد» یا «افتاد» رو\nبا هر اسم کاراکتری تشخیص می‌ده؛ سپس\nروی همان پیام ریپلای می‌کنه و /art می‌فرسته.\n"
        "━━━━━━━━━━━━━━━━━"
    )
    kb = [
        [_cb(f"{'🔴 خاموش کن' if on else '🟢 روشن کن'}", "pn_pew_toggle")],
        [_cb("🔄 ریست آمار", "pn_pew_reset")],
        [_cb("بازگشت 🔙", "pn_pew_panel")],
    ]
    return text, kb

async def _pm_build_pewring_master_panel(uid, page=0):
    groups = await _pm_get_user_groups(uid, limit=200)
    items = []
    for g in groups:
        cfg = pew_ring_config.get((int(uid), int(g["id"])), {})
        items.append({"id": g["id"], "title": g["title"], "enabled": cfg.get("enabled", False)})
    active = sum(1 for it in items if it["enabled"])
    total = len(items)
    per_page = 10
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    chunk = items[start:start + per_page]
    lines = [
        "🏋️ پیو رینگ — مدیریت",
        "━━━━━━━━━━━━━━━━━",
        f"📊 {active}/{total} گروه فعال",
        f"📄 صفحه {page+1} از {total_pages}",
    ]
    kb = []
    cur_chat = pm_panel_chat.get(int(uid))
    if cur_chat:
        cur_item = next((it for it in items if int(it["id"]) == int(cur_chat)), None)
        if cur_item:
            cur_title = cur_item["title"]; cur_on = cur_item["enabled"]
        else:
            cur_title = str(cur_chat); cur_on = False
            try:
                c = user_clients.get(int(uid))
                if c:
                    ent = await c.get_entity(cur_chat)
                    cur_title = getattr(ent, 'title', None) or cur_title
            except: pass
        icon = "🟢" if cur_on else "🔴"
        kb.append([_cb(f"📍 {icon} محل فعلی: {cur_title[:28]}", f"pn_pewring_sel_{cur_chat}")])
        lines.append("━━━━━━━━━━━━━━━━━")
    if chunk:
        lines.append("👇 روی گروه بزن:")
        for it in chunk:
            if cur_chat and int(it["id"]) == int(cur_chat): continue
            icon = "🟢" if it["enabled"] else "🔴"
            kb.append([_cb(f"{icon} {it['title'][:28]}", f"pn_pewring_sel_{it['id']}")])
    else:
        if not cur_chat: lines.append("❌ گروهی نیست")
    nav = []
    if page > 0: nav.append(_cb("⬅️ قبلی", f"pn_pewring_page_{page-1}"))
    if page < total_pages - 1: nav.append(_cb("بعدی ➡️", f"pn_pewring_page_{page+1}"))
    if nav: kb.append(nav)
    kb.append([_cb("🟢 روشن همه", "pn_pewring_master_on"),
               _cb("🔴 خاموش همه", "pn_pewring_master_off")])
    kb.append([_cb("⚪ 🔙 بازگشت", "pn_pew_panel")])
    return "\n".join(lines), kb

async def _pm_build_dog_master_panel(uid, page=0):
    groups = await _pm_get_user_groups(uid, limit=200)
    items = []
    for g in groups:
        cfg = pew_dog_config.get((int(uid), int(g["id"])), {})
        items.append({"id": g["id"], "title": g["title"], "enabled": cfg.get("enabled", False)})
    active = sum(1 for it in items if it["enabled"])
    total = len(items)
    per_page = 10
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    chunk = items[start:start + per_page]
    lines = [
        "🐕 سگ — مدیریت",
        "━━━━━━━━━━━━━━━━━",
        f"📊 {active}/{total} گروه فعال",
        f"📄 صفحه {page+1} از {total_pages}",
    ]
    kb = []
    cur_chat = pm_panel_chat.get(int(uid))
    if cur_chat:
        cur_item = next((it for it in items if int(it["id"]) == int(cur_chat)), None)
        if cur_item:
            cur_title = cur_item["title"]; cur_on = cur_item["enabled"]
        else:
            cur_title = str(cur_chat); cur_on = False
            try:
                c = user_clients.get(int(uid))
                if c:
                    ent = await c.get_entity(cur_chat)
                    cur_title = getattr(ent, 'title', None) or cur_title
            except: pass
        icon = "🟢" if cur_on else "🔴"
        kb.append([_cb(f"📍 {icon} محل فعلی: {cur_title[:28]}", f"pn_dog_sel_{cur_chat}")])
        lines.append("━━━━━━━━━━━━━━━━━")
    if chunk:
        lines.append("👇 روی گروه بزن:")
        for it in chunk:
            if cur_chat and int(it["id"]) == int(cur_chat): continue
            icon = "🟢" if it["enabled"] else "🔴"
            kb.append([_cb(f"{icon} {it['title'][:28]}", f"pn_dog_sel_{it['id']}")])
    else:
        if not cur_chat: lines.append("❌ گروهی نیست")
    nav = []
    if page > 0: nav.append(_cb("⬅️ قبلی", f"pn_dog_page_{page-1}"))
    if page < total_pages - 1: nav.append(_cb("بعدی ➡️", f"pn_dog_page_{page+1}"))
    if nav: kb.append(nav)
    kb.append([_cb("🟢 روشن همه", "pn_dog_master_on"),
               _cb("🔴 خاموش همه", "pn_dog_master_off")])
    kb.append([_cb("⚪ 🔙 بازگشت", "pn_pew_panel")])
    return "\n".join(lines), kb

async def _pm_build_pewring_panel(uid, cid):
    cfg = pew_ring_config.get((int(uid), int(cid)), {"enabled": False})
    on = cfg.get("enabled", False)
    state = pew_ring_state.get((int(uid), int(cid)), {})
    energy = state.get("last_energy"); max_energy = state.get("last_max")
    ups = state.get("last_upgrades", {}); last_ts = state.get("last_ts", 0)
    title = str(cid)
    try:
        c = user_clients.get(int(uid))
        if c:
            ent = await c.get_entity(cid)
            title = getattr(ent, 'title', None) or title
    except: pass
    e_str = f"{energy:.1f}" if energy is not None else "—"
    m_str = f"{max_energy}" if max_energy is not None else "—"
    lines = [f"🏋️ پیو رینگ — {title[:30]}", "━━━━━━━━━━━━━━━━━",
        f"وضعیت: {'🟢 روشن' if on else '🔴 خاموش'}", f"⚡️ انرژی: {e_str} / {m_str}"]
    if ups:
        lines.append("━━━━━━━━━━━━━━━━━")
        lines.append("📊 ارتقای بعدی:")
        for key in ("skill","speed","power","health"):
            if key in ups:
                lines.append(f"  • {PEW_RING_STAT_LABEL[key]}: {ups[key]:.0f}⚡️")
    if last_ts:
        try:
            ago = int(time.time() - last_ts)
            if ago < 60: ago_s = f"{ago}s پیش"
            elif ago < 3600: ago_s = f"{ago//60}m پیش"
            else: ago_s = f"{ago//3600}h پیش"
            lines.append(f"🕐 آخرین بروزرسانی: {ago_s}")
        except: pass
    lines.append("━━━━━━━━━━━━━━━━━")
    kb = [
        [_cb(f"{'🔴 خاموش کن' if on else '🟢 روشن کن'}", f"pn_pewring_t_{cid}")],
        [_cb("🔄 گروه‌ها", "pn_pewring_master_panel")],
        [_cb("⚪ 🔙 بازگشت", "pn_pew_panel")],
    ]
    return "\n".join(lines), kb

async def _pm_build_pew_dog_view(uid, chat_id):
    key = (int(uid), int(chat_id))
    cfg = pew_dog_config.get(key, {"enabled": False})
    on = cfg.get("enabled", False)
    state = pew_dog_state.get(key, {})
    next_min = state.get("next_feed_min")
    last_ts = state.get("last_ts", 0)
    title = str(chat_id)
    try:
        c = user_clients.get(int(uid))
        if c:
            ent = await c.get_entity(chat_id)
            title = getattr(ent, "title", None) or title
    except: pass
    nf_str = f"{next_min} دقیقه" if next_min else "—"
    last_str = "—"
    if last_ts:
        try:
            ago = int(time.time() - last_ts)
            if ago < 60: last_str = f"{ago}s پیش"
            elif ago < 3600: last_str = f"{ago//60}m پیش"
            else: last_str = f"{ago//3600}h پیش"
        except: pass
    text = (
        f"🐕 سگ — {title[:30]}\n━━━━━━━━━━━━━━━━━\n"
        f"📊 وضعیت: {'🟢 روشن' if on else '🔴 خاموش'}\n"
        f"⏱ غذا بعدی: {nf_str}\n🕐 آخرین غذا: {last_str}\n"
        "━━━━━━━━━━━━━━━━━"
    )
    kb = [
        [_cb("🔴 خاموش" if on else "🟢 روشن", f"pn_dog_t_{chat_id}")],
        [_cb("🔄 گروه‌ها", "pn_dog_master_panel")],
        [_cb("⚪ 🔙 بازگشت", "pn_pew_panel")],
    ]
    return text, kb

async def _pm_build_group_hunt_panel(uid):
    is_owner = False

    code = pew_user_group.get(uid)
    if not code:
        text = "🛡 شکار گروهی\n━━━━━━━━━━━━━━━━━\nشما در هیچ گروهی نیستید."
        kb = [
            [_cb("➕ ساخت گروه", "pn_ghunt_create")],
            [_cb("🔗 ملحق به گروه", "pn_ghunt_join")],
            [_cb("⚪ 🔙 بازگشت", "pn_pew_panel")]
        ]
        return text, kb
    
    grp = pew_hunt_groups.get(code)
    if not grp:
        pew_user_group.pop(uid, None)
        return await _pm_build_group_hunt_panel(uid)
    
    members = grp.get("members", [])
    disabled = grp.get("disabled_users", [])
    is_owner = (grp.get("owner") == uid)
    user_active = uid not in disabled
    
    st_txt = "🟢 روشن" if user_active else "🔴 خاموش"
    role_txt = "👑 سازنده" if is_grp_owner else "👤 عضو"
    
    text = f"🛡 شکار گروهی\n━━━━━━━━━━━━━━━━━\n🔑 کد گروه: <code>{code}</code>\n🎭 نقش شما: {role_txt}\n📊 وضعیت شما: <b>{st_txt}</b>\n👥 اعضا ({len(members)}):\n"
    for m in members:
        try: nm = await get_plain_name(bot_client, m)
        except: nm = str(m)
        icon = "👑" if m == grp.get("owner") else "👤"
        off_icon = " (خاموش)" if m in disabled else ""
        text += f" {icon} {nm}{off_icon}\n"
    text += "━━━━━━━━━━━━━━━━━\n💡 برای سینک شدن، هر دستوری تو گروه بفرستید."
    
    btn_txt = "🔴 خاموش کن (برای من)" if user_active else "🟢 روشن کن (برای من)"
    kb = [
        [_cb(btn_txt, "pn_ghunt_toggle")],
        [_cb("📊 وضعیت", "pn_ghunt_status"), _cb("🔴 خروج", "pn_ghunt_leave_ask")]
    ]
    if is_owner:
        kb.append([_cb("👑 مدیریت اعضا", "pn_ghunt_mgmt")])
    kb.append([_cb("⚪ 🔙 بازگشت", "pn_pew_panel")])
    return text, kb

async def _pm_build_ghunt_mgmt(uid):
    code = pew_user_group.get(uid)
    grp = pew_hunt_groups.get(code)
    if not grp or grp.get("owner") != uid:
        return ("❌ دسترسی ندارید", [[_cb("⚪ 🔙", "pn_ghunt_panel")]])
    text = "👑 مدیریت گروه\n━━━━━━━━━━━━━━━━━\nیک گزینه را انتخاب کنید:"
    kb = [
        [_cb("🗑 اخراج عضو", "pn_ghunt_kick_list")],
        [_cb("👑 انتقال سازندگی", "pn_ghunt_prom_list")],
        [_cb("🔴 منحل کردن گروه", "pn_ghunt_del_ask")],
        [_cb("⚪ 🔙 بازگشت", "pn_ghunt_panel")]
    ]
    return text, kb

async def _sync_hunt_handler(event, user_id):
    if not event.out or event.sender_id != user_id: return
    if user_id in _syncing_users: return
    if user_id not in pew_user_group: return
    
    text = (event.raw_text or "").strip()
    if not text: return
    
    norm = _normalize_persian(text).replace("ي", "ی").replace("ك", "ک").lower().strip()
    # Only mirror a dedicated keyword message, never a sentence that merely contains it.
    keywords = {"شلیک", "پیو هیل", "پیو باس حمله", "جیز"}
    if norm not in keywords: return
    
    code = pew_user_group[user_id]
    grp = pew_hunt_groups.get(code)
    if not grp: return
    
    members = [m for m in grp["members"] if m != user_id]
    if not members: return
    disabled = grp.get("disabled_users", [])
    
    _syncing_users.add(user_id)
    for mid in members:
        if mid in disabled: continue  # کاربر خاموش کرده، براش نفرست
        cl = user_clients.get(mid)
        if not cl or not cl.is_connected(): continue  # آفلاین یا تو چت نیست
        
        _syncing_users.add(mid)
        try:
            reply_to = event.reply_to_msg_id if event.reply_to_msg_id else None
            await cl.send_message(event.chat_id, text, reply_to=reply_to)
            await asyncio.sleep(1)
        except Exception:
            pass  # بی‌صدا رد شو اگه تو گروه نبود یا بلاک بود
        finally:
            _syncing_users.discard(mid)
    _syncing_users.discard(user_id)

def make_sync_handler(user_id):
    async def sync_handler(event):
        try: await _sync_hunt_handler(event, user_id)
        except Exception as e: log_error(f"sync_handler {user_id}: {_translate_bot_errors(e)}")
    return sync_handler

async def _pm_build_pew_target_panel(uid):
    total = sum(1 for k in pew_target_config if k[0] == int(uid))
    active = sum(1 for k, v in pew_target_config.items() if k[0] == int(uid) and v.get("enabled"))
    text = (
        "🎯 پیو — هدف\n━━━━━━━━━━━━━━━━━\n"
        f"📊 کل: {total}  ·  🟢 فعال: {active}\n"
        "━━━━━━━━━━━━━━━━━\n"
        "هر ۱۵ ثانیه ریپلای «شلیک» می‌ره\nتا بمیره. بعد مرگ ۱۱ دقیقه صبر.\n"
        "━━━━━━━━━━━━━━━━━"
    )
    kb = [
        [_cb("➕ افزودن هدف", "pn_tgt_add")],
        [_cb(f"📋 لیست اهداف ({total})", "pn_tgt_list_0")],
        [_cb("🗑 حذف هدف", "pn_tgt_del_0")],
        [_cb("⚪ 🔙 بازگشت", "pn_pew_panel")],
    ]
    return text, kb

async def _pm_build_pew_target_list(uid, page=0):
    items = [(k, v) for k, v in pew_target_config.items() if k[0] == int(uid)]
    per_page = 6
    total = len(items)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    chunk = items[start:start + per_page]
    lines = [f"📋 اهداف — {total}  ·  {page+1}/{total_pages}"]
    kb = []
    for (u_, cid, tid), cfg in chunk:
        icon = "🟢" if cfg.get("enabled") else "🔴"
        name = (cfg.get("name") or str(tid))[:20]
        kb.append([_cb(f"{icon} {name} · {tid}", f"pn_tgt_v_{cid}_{tid}")])
    nav = []
    if page > 0: nav.append(_cb("🔵 ⬅️", f"pn_tgt_list_{page-1}"))
    if page < total_pages - 1: nav.append(_cb("🔵 ➡️", f"pn_tgt_list_{page+1}"))
    if nav: kb.append(nav)
    kb.append([_cb("➕ افزودن", "pn_tgt_add")])
    kb.append([_cb("⚪ 🔙 بازگشت", "pn_tgt_panel")])
    return "\n".join(lines), kb

async def _pm_build_pew_target_view(uid, chat_id, target_id):
    key = _pew_target_key(uid, chat_id, target_id)
    cfg = pew_target_config.get(key)
    if not cfg: return "❌ هدف نیست.", [[_cb("⚪ 🔙 بازگشت", "pn_tgt_list_0")]]
    name = cfg.get("name", str(target_id))
    enabled = cfg.get("enabled", False)
    uname = cfg.get("username", "")
    uname_str = f"@{uname}" if uname else "—"
    title = str(chat_id)
    try:
        c = user_clients.get(int(uid))
        if c:
            ent = await c.get_entity(chat_id)
            title = getattr(ent, "title", None) or title
    except: pass
    state = pew_target_state.get(key, {})
    phase = state.get("phase", "—")
    phase_label = {"shooting": "🎯 در حال شلیک", "dead_wait": "⏳ صبر بعد مرگ"}.get(phase, phase)
    last_ts = state.get("last_shoot_ts", 0)
    last_str = "—"
    if last_ts:
        try:
            ago = int(time.time() - last_ts)
            if ago < 60: last_str = f"{ago}s پیش"
            elif ago < 3600: last_str = f"{ago//60}m پیش"
            else: last_str = f"{ago//3600}h پیش"
        except: pass
    text = (
        f"🎯 هدف: {name}\n━━━━━━━━━━━━━━━━━\n"
        f"🔗 یوزرنیم: {uname_str}\n"
        f"🆔 <code>{target_id}</code>\n"
        f"💬 گروه: {title[:30]}\n"
        f"📊 وضعیت: {'🟢 فعال' if enabled else '🔴 خاموش'}\n"
        f"🎬 فاز: {phase_label}\n"
        f"🕐 آخرین شلیک: {last_str}\n"
        "━━━━━━━━━━━━━━━━━"
    )
    kb = [
        [_cb("🔴 خاموش" if enabled else "🟢 روشن", f"pn_tgt_t_{chat_id}_{target_id}")],
        [_cb("🔀 تغییر گروه", f"pn_tgt_chg_grp_{chat_id}_{target_id}")],
        [_cb("🗑 حذف", f"pn_tgt_del_ask_{chat_id}_{target_id}")],
        [_cb("⚪ 🔙 بازگشت", "pn_tgt_list_0")],
    ]
    return text, kb

async def _pm_build_pew_target_del_list(uid, page=0):
    items = [(k, v) for k, v in pew_target_config.items() if k[0] == int(uid)]
    per_page = 6
    total = len(items)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    chunk = items[start:start + per_page]
    lines = [f"🗑 حذف هدف — {total}  ·  {page+1}/{total_pages}", "👇 یکی رو انتخاب کن:"]
    kb = []
    for (u_, cid, tid), cfg in chunk:
        name = (cfg.get("name") or str(tid))[:20]
        kb.append([_cb(f"🔴 {name}", f"pn_tgt_del_ask_{cid}_{tid}")])
    nav = []
    if page > 0: nav.append(_cb("🔵 ⬅️", f"pn_tgt_del_{page-1}"))
    if page < total_pages - 1: nav.append(_cb("🔵 ➡️", f"pn_tgt_del_{page+1}"))
    if nav: kb.append(nav)
    kb.append([_cb("⚪ 🔙 بازگشت", "pn_tgt_panel")])
    return "\n".join(lines), kb

async def _pm_build_pew_target_del_confirm(uid, chat_id, target_id):
    key = _pew_target_key(uid, chat_id, target_id)
    cfg = pew_target_config.get(key)
    if not cfg: return "❌ هدف نیست.", [[_cb("⚪ 🔙 بازگشت", "pn_tgt_panel")]]
    name = cfg.get("name", str(target_id))
    text = f"🗑 حذف هدف\n📛 {name}\n🆔 <code>{target_id}</code>\n\n⚠️ مطمئنی؟"
    kb = [
        [_cb("✅ بله حذف کن", f"pn_tgt_del_yes_{chat_id}_{target_id}")],
        [_cb("🔴 لغو", f"pn_tgt_v_{chat_id}_{target_id}")],
    ]
    return text, kb

async def _pm_build_pew_target_confirm(uid, info):
    tid = info["id"]
    first = info.get("first_name", "") or ""
    last  = info.get("last_name", "") or ""
    uname = info.get("username", "") or ""
    full  = (first + " " + last).strip() or "—"
    uname_str = f"@{uname}" if uname else "—"
    text = (
        "🎯 افزودن هدف\n━━━━━━━━━━━━━━━━━\n"
        f"👤 اسم: <b>{full}</b>\n"
        f"🔗 یوزرنیم: {uname_str}\n"
        f"🆔 آیدی عددی: <code>{tid}</code>\n"
        "━━━━━━━━━━━━━━━━━\n"
        "❓ آیا هدف تایید می‌شود؟"
    )
    kb = [[_cb("✅ بله", "pn_tgt_yes"), _cb("❌ خیر", "pn_tgt_no")]]
    return text, kb

async def _pm_build_pew_target_group_picker(uid, tid, page=0, old_cid=None, mode="add"):
    groups = await _pm_get_user_groups(uid, limit=200)
    title = "🎯 انتخاب گروه" if mode == "add" else "🔀 تغییر گروه"
    back_data = "pn_tgt_no" if mode == "add" else f"pn_tgt_v_{old_cid}_{tid}"
    if not groups:
        return "\n".join([title, "━━━━━━━━━━━━━━━━━", "❌ گروهی نیست."]), \
               [[_cb("بازگشت 🔙", back_data)]]
    per_page = 10
    total = len(groups)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    chunk = groups[start:start + per_page]
    lines = [
        title, "━━━━━━━━━━━━━━━━━",
        f"📊 صفحه {page+1} از {total_pages}  ·  {total} گروه",
        "━━━━━━━━━━━━━━━━━",
        "👇 یکی رو انتخاب کن:",
    ]
    kb = []
    cur_chat = pm_panel_chat.get(int(uid))
    if cur_chat and mode == "add":
        cur_title = str(cur_chat)
        try:
            c = user_clients.get(int(uid))
            if c:
                ent = await c.get_entity(cur_chat)
                cur_title = getattr(ent, 'title', None) or cur_title
        except: pass
        kb.append([_cb(f"📍 محل فعلی: {cur_title[:30]}", f"pn_tgt_grp_{tid}_{cur_chat}")])
        lines.append("━━━━━━━━━━━━━━━━━")
    lines.append("👇 روی گروه بزن:")
    for g in chunk:
        if cur_chat and mode == "add" and int(g["id"]) == int(cur_chat): continue
        short = g['title'][:35]
        if mode == "add":
            cb = f"pn_tgt_grp_{tid}_{g['id']}"
        else:
            cb = f"pn_tgt_chg_set_{old_cid}_{tid}_{g['id']}"
        kb.append([_cb(f"💬 {short}", cb)])
    nav = []
    if page > 0:
        if mode == "add": nav.append(_cb("⬅️ قبلی", f"pn_tgt_grp_page_{tid}_{page-1}"))
        else: nav.append(_cb("⬅️ قبلی", f"pn_tgt_chg_page_{old_cid}_{tid}_{page-1}"))
    if page < total_pages - 1:
        if mode == "add": nav.append(_cb("بعدی ➡️", f"pn_tgt_grp_page_{tid}_{page+1}"))
        else: nav.append(_cb("بعدی ➡️", f"pn_tgt_chg_page_{old_cid}_{tid}_{page+1}"))
    if nav: kb.append(nav)
    if mode == "add":
        kb.append([_cb("🔗 لینک/آیدی دستی", f"pn_tgt_manual_{tid}")])
    else:
        kb.append([_cb("🔗 لینک/آیدی دستی", f"pn_tgt_chg_manual_{old_cid}_{tid}")])
    kb.append([_cb("لغو 🔙", back_data)])
    return "\n".join(lines), kb

def get_user_notifs(uid):
    user = users_db.setdefault("users", {}).setdefault(str(int(uid)), {})
    notifs = user.setdefault("notifications", {})
    defaults = {"mat_trans": True, "item_trans": True, "sell": True,
                "monitor": True, "emoji_name": True}
    for key, value in defaults.items():
        notifs.setdefault(key, value)
    return notifs


def save_user_notifs(uid):
    get_user_notifs(uid)
    save_json(USERS_FILE, users_db)


def _save_monitor_db():
    save_json(MONITOR_FILE, monitor_db)


async def _read_monitor_profile(client, target_id):
    entity = await client.get_entity(int(target_id))
    input_peer = await client.get_input_entity(entity)
    input_user = types.InputUser(user_id=input_peer.user_id,
                                 access_hash=input_peer.access_hash)
    full = await client(GetFullUserRequest(input_user))
    full_users = list(getattr(full, "users", []) or [])
    user = next((item for item in full_users
                 if int(getattr(item, "id", 0)) == int(target_id)), None)
    if user is None and full_users:
        user = full_users[0]
    if user is None:
        raise ValueError("پروفایل قابل خواندن نیست")
    full_info = getattr(full, "full_user", None)
    return {
        "name": " ".join(x for x in [getattr(user, "first_name", ""),
                                      getattr(user, "last_name", "")] if x).strip(),
        "username": getattr(user, "username", "") or "",
        "bio": getattr(full_info, "about", "") or "",
    }


async def _monitor_add_target(uid, event, arg=""):
    client = user_clients.get(int(uid))
    if not client or not client.is_connected():
        client = await ensure_user_client(uid)
    if not client:
        return False, "❌ اکانت متصل نیست."
    try:
        target_id = await resolve_user_arg(event, client, arg)
        if not target_id:
            return False, f"❌ فرد پیدا نشد. آیدی/یوزرنیم بفرست یا روی پیامش ریپلای کن. نمونه: {CMD}پایش افزودن @username"
        entity = await client.get_entity(int(target_id))
        if getattr(entity, "bot", False):
            return False, "❌ برای پایش، یک حساب کاربری انتخاب کن؛ بات پذیرفته نیست."
        snap = await _read_monitor_profile(client, target_id)
        cfg = monitor_db.setdefault(str(int(uid)), {"enabled": False, "users": {}})
        users = cfg.setdefault("users", {})
        tid = str(int(target_id))
        if tid in users:
            return False, "⚠️ این فرد از قبل در فهرست پایش است."
        users[tid] = {
            "enabled": True, "history": [], "last_name": snap["name"],
            "last_uname": snap["username"], "last_bio": snap["bio"]}
        _save_monitor_db()
        uname = f"@{snap['username']}" if snap["username"] else "—"
        return True, (f"✅ به فهرست پایش اضافه شد.\n👤 {snap['name'] or target_id}"
                      f"\n🔗 {uname}\n🆔 {target_id}")
    except Exception as e:
        log_error(f"monitor add {uid}: {_translate_bot_errors(e)}")
        return False, f"❌ دریافت پروفایل ناموفق بود: {_translate_bot_errors(e)}"


async def profile_monitor_loop(uid):
    uid = int(uid)
    key = str(uid)
    task = asyncio.current_task()
    try:
        while monitor_db.get(key, {}).get("enabled", False):
            await asyncio.sleep(600)
            cfg = monitor_db.get(key, {})
            if not cfg.get("enabled", False):
                break
            if not is_user_active(uid) or not is_user_allowed(uid):
                break
            client = user_clients.get(uid)
            if not client or not client.is_connected():
                client = await ensure_user_client(uid)
            if not client:
                continue
            changed_any = False
            for target_id, data in list(cfg.get("users", {}).items()):
                if not data.get("enabled", True):
                    continue
                try:
                    current = await _read_monitor_profile(client, target_id)
                    changes = []
                    old_name = data.get("last_name", "")
                    old_username = data.get("last_uname", "")
                    old_bio = data.get("last_bio", "")
                    if old_name != current["name"]:
                        changes.append(f"نام: {old_name or '—'} ➡️ {current['name'] or '—'}")
                    if old_username != current["username"]:
                        before = f"@{old_username}" if old_username else "—"
                        after = f"@{current['username']}" if current["username"] else "—"
                        changes.append(f"یوزرنیم: {before} ➡️ {after}")
                    if old_bio != current["bio"]:
                        changes.append("بیو تغییر کرد")
                    data["last_name"] = current["name"]
                    data["last_uname"] = current["username"]
                    data["last_bio"] = current["bio"]
                    if changes:
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
                        history = data.setdefault("history", [])
                        for change in reversed(changes):
                            history.insert(0, {"time": now_str, "change": change})
                        data["history"] = history[:5]
                        changed_any = True
                        if get_user_notifs(uid).get("monitor", True):
                            name = current["name"] or str(target_id)
                            await _notify_user(uid,
                                f"👁 پایش پروفایل\n👤 {name}\n" + "\n".join(changes))
                except Exception as e:
                    log_error(f"profile monitor {uid}/{target_id}: {_translate_bot_errors(e)}")
            if changed_any:
                _save_monitor_db()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        log_error(f"profile_monitor_loop {uid}: {_translate_bot_errors(e)}")
    finally:
        if monitor_tasks.get(key) is task:
            monitor_tasks.pop(key, None)


def start_monitor_task(uid):
    key = str(int(uid))
    task = monitor_tasks.get(key)
    if task and not task.done():
        return False
    monitor_tasks[key] = asyncio.create_task(profile_monitor_loop(int(uid)))
    return True


def stop_monitor_task(uid):
    key = str(int(uid))
    task = monitor_tasks.pop(key, None)
    if task and not task.done():
        task.cancel()


async def _pm_build_monitor_main(uid):
    cfg = monitor_db.setdefault(str(int(uid)), {"enabled": False, "users": {}})
    is_on = bool(cfg.get("enabled", False))
    count = len(cfg.get("users", {}))
    text = (
        "👁 <b>پایش پروفایل</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"📊 وضعیت سراسری: {'🟢 روشن' if is_on else '🔴 خاموش'}\n"
        f"👥 افراد در فهرست: {count}\n"
        "━━━━━━━━━━━━━━━━━\n"
        "پروفایل افراد منتخب هر ۱۰ دقیقه بررسی می‌شود."
    )
    kb = [
        [_cb("🔴 خاموش کن" if is_on else "🟢 روشن کن", "pn_mon_toggle_all")],
        [_cb("➕ افزودن فرد", "pn_mon_add"), _cb("📋 فهرست افراد", "pn_mon_list_0")],
        [_cb("⚪ 🔙 بازگشت", "pn_tools")],
    ]
    return text, kb


async def _pm_build_monitor_list(uid, page=0):
    cfg = monitor_db.get(str(int(uid)), {"users": {}})
    users = list(cfg.get("users", {}).items())
    per_page = 6
    total = len(users)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(int(page), total_pages - 1))
    chunk = users[page * per_page:(page + 1) * per_page]
    lines = [f"📋 <b>فهرست پایش</b> — {total} نفر",
             f"📄 صفحه {page+1}/{total_pages}", "━━━━━━━━━━━━━━━━━"]
    kb = []
    for tid, data in chunk:
        icon = "🟢" if data.get("enabled", True) else "🔴"
        name = data.get("last_name") or str(tid)
        uname = f" · @{data['last_uname']}" if data.get("last_uname") else ""
        kb.append([_cb(f"{icon} {name[:22]}{uname[:20]}", f"pn_mon_v_{tid}")])
    nav = []
    if page > 0: nav.append(_cb("⬅️ قبلی", f"pn_mon_list_{page-1}"))
    if page < total_pages - 1: nav.append(_cb("بعدی ➡️", f"pn_mon_list_{page+1}"))
    if nav: kb.append(nav)
    kb.append([_cb("➕ افزودن فرد", "pn_mon_add")])
    kb.append([_cb("⚪ 🔙 بازگشت", "pn_mon_main")])
    return "\n".join(lines), kb


async def _pm_build_monitor_view(uid, target_id):
    cfg = monitor_db.get(str(int(uid)), {}).get("users", {})
    data = cfg.get(str(target_id))
    if not data:
        return "❌ فرد در فهرست پایش نیست.", [[_cb("🔙 بازگشت", "pn_mon_list_0")]]
    name = html_lib.escape(data.get("last_name") or str(target_id))
    username = html_lib.escape("@" + data["last_uname"] if data.get("last_uname") else "—")
    bio = html_lib.escape(data.get("last_bio") or "—")
    history = "".join(
        f"• [{html_lib.escape(str(item.get('time', '')))}] {html_lib.escape(str(item.get('change', '')))}\n"
        for item in data.get("history", [])[:5]) or "تغییری ثبت نشده.\n"
    enabled = bool(data.get("enabled", True))
    text = (
        f"👤 <b>{name}</b>\n🆔 <code>{target_id}</code>\n🔗 {username}\n"
        f"📝 بیو: {bio[:120]}\n📊 وضعیت: {'🟢 فعال' if enabled else '🔴 خاموش'}\n"
        "━━━━━━━━━━━━━━━━━\n🕒 <b>آخرین تغییرها</b>\n" + history
    )
    kb = [
        [_cb("🔴 خاموش کن" if enabled else "🟢 روشن کن", f"pn_mon_t_{target_id}")],
        [_cb("🗑 حذف از فهرست", f"pn_mon_del_{target_id}")],
        [_cb("⚪ 🔙 بازگشت", "pn_mon_list_0")],
    ]
    return text, kb


async def _pm_build_tts_panel(uid):
    gender = users_db["users"].get(str(uid), {}).get("voice_gender", "female")
    gender_label = "👩 زن" if gender == "female" else "👨 مرد"
    text = (
        "🔊 <b>تبدیل متن و ویس</b>\n━━━━━━━━━━━━━━━━━\n"
        f"🎙 صدای پیش‌فرض: {gender_label}\n━━━━━━━━━━━━━━━━━\n"
        "از دکمه‌های زیر هم می‌توانی متن را ویس یا ویس را متن کنی.\n"
        "📌 دستورهای متنی با ویرگول فارسی شروع می‌شوند:\n"
        f"• <code>{CMD}ویس &lt;متن&gt;</code>\n"
        f"• <code>{CMD}ویس زن &lt;متن&gt;</code> / <code>{CMD}ویس مرد &lt;متن&gt;</code>\n"
        f"• روی ویس ریپلای کن و بنویس <code>{CMD}گوش کن</code> برای تبدیل به متن."
    )
    kb = [
        [_cb("👩 صدای پیش‌فرض: زن", "pn_tts_set_female"),
         _cb("👨 صدای پیش‌فرض: مرد", "pn_tts_set_male")],
        [_cb("📝 متن را ویس کن", "pn_tts_text_start"),
         _cb("🎧 ویس را متن کن", "pn_tts_voice_start")],
        [_cb("⚪ 🔙 بازگشت", "pn_tools")],
    ]
    return text, kb


async def _send_tts_voice(event, text, gender=None):
    text = (text or "").strip()
    if not text:
        await event.reply(f"متن را هم بنویس. نمونه: <code>{CMD}ویس سلام</code>", parse_mode="html")
        return
    if len(text) > 1500:
        await event.reply("❌ متن برای تبدیل صوتی خیلی طولانی است؛ حداکثر ۱۵۰۰ نویسه بفرست.")
        return
    gender = gender or users_db["users"].get(str(event.sender_id), {}).get("voice_gender", "female")
    voice = "fa-IR-DilaraNeural" if gender == "female" else "fa-IR-FaridNeural"
    path = None
    try:
        import tempfile
        import edge_tts
        fd, path = tempfile.mkstemp(prefix="tts_", suffix=".mp3")
        os.close(fd)
        await edge_tts.Communicate(text, voice).save(path)
        await event.client.send_file(event.chat_id, path, voice_note=True,
                                     reply_to=getattr(event, "id", None))
    except Exception as e:
        log_error(f"tts {event.sender_id}: {_translate_bot_errors(e)}")
        await event.reply(f"❌ تبدیل متن به صدا انجام نشد: {_translate_bot_errors(e)}")
    finally:
        if path:
            try: os.remove(path)
            except: pass


async def _transcribe_voice_message(event, voice_message):
    if not voice_message or not (getattr(voice_message, "voice", None) or getattr(voice_message, "audio", None)):
        await event.reply("❌ ویس یا فایل صوتی قابل‌خواندن نیست.")
        return
    size = getattr(getattr(voice_message, "file", None), "size", 0) or 0
    if size > 20 * 1024 * 1024:
        await event.reply("❌ فایل صوتی بزرگ است؛ حداکثر ۲۰ مگابایت پشتیبانی می‌شود.")
        return
    try:
        import tempfile
        import speech_recognition as sr
        with tempfile.TemporaryDirectory(prefix="stt_") as tmp:
            source_path = os.path.join(tmp, "source.ogg")
            wav_path = os.path.join(tmp, "audio.wav")
            downloaded = await event.client.download_media(voice_message, file=source_path)
            if not downloaded:
                await event.reply("❌ دانلود ویس ناموفق بود.")
                return
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-nostdin", "-y", "-i", str(downloaded),
                "-ac", "1", "-ar", "16000", wav_path,
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
            await proc.communicate()
            if proc.returncode != 0 or not os.path.exists(wav_path):
                await event.reply("❌ تبدیل ویس ناموفق بود؛ نصب بودن ffmpeg را بررسی کن.")
                return
            recognizer = sr.Recognizer()
            with sr.AudioFile(wav_path) as source:
                audio = recognizer.record(source, duration=120)
            transcript = recognizer.recognize_google(audio, language="fa-IR")
            await event.reply("📝 متن ویس:\n" + transcript)
    except FileNotFoundError:
        await event.reply("❌ برای تبدیل ویس، ffmpeg باید روی سرور نصب باشد.")
    except Exception as e:
        log_error(f"voice recognition {event.sender_id}: {_translate_bot_errors(e)}")
        await event.reply(f"❌ تشخیص گفتار انجام نشد: {_translate_bot_errors(e)}")


async def _transcribe_voice_reply(event):
    reply = await event.get_reply_message()
    if not reply or not (getattr(reply, "voice", None) or getattr(reply, "audio", None)):
        await event.reply(f"روی یک ویس/فایل صوتی ریپلای کن و بنویس <code>{CMD}گوش کن</code>.", parse_mode="html")
        return
    await _transcribe_voice_message(event, reply)


def get_name_emoji_config(uid):
    user = users_db.setdefault("users", {}).setdefault(str(int(uid)), {})
    cfg = user.setdefault("name_emoji", {})
    cfg.setdefault("enabled", False)
    cfg.setdefault("emojis", list(NAME_EMOJI_PRESETS[:5]))
    cfg.setdefault("custom_emojis", [])
    cfg.setdefault("current_index", 0)
    cfg.setdefault("position", "start")
    cfg.setdefault("interval", 60)
    cfg.setdefault("profile_saved", False)
    cfg.setdefault("original_first_name", "")
    cfg.setdefault("original_last_name", "")
    return cfg


async def _update_name_with_emoji(uid, emoji):
    client = user_clients.get(int(uid))
    if not client or not client.is_connected():
        client = await ensure_user_client(uid)
    if not client:
        return False
    cfg = get_name_emoji_config(uid)
    if not cfg.get("profile_saved"):
        me = await client.get_me()
        cfg["original_first_name"] = getattr(me, "first_name", "") or ""
        cfg["original_last_name"] = getattr(me, "last_name", "") or ""
        cfg["profile_saved"] = True
    first_name = str(cfg.get("original_first_name", "") or "")
    last_name = str(cfg.get("original_last_name", "") or "")
    if cfg.get("position", "start") == "start":
        first_name = f"{emoji} {first_name}".strip()[:64]
    else:
        last_name = f"{last_name} {emoji}".strip()[:64]
    await client(UpdateProfileRequest(first_name=first_name, last_name=last_name))
    return True


async def _restore_original_profile_name(uid):
    cfg = get_name_emoji_config(uid)
    if not cfg.get("profile_saved"):
        return True
    client = user_clients.get(int(uid))
    if not client or not client.is_connected():
        client = await ensure_user_client(uid)
    if not client:
        return False
    await client(UpdateProfileRequest(
        first_name=str(cfg.get("original_first_name", "")),
        last_name=str(cfg.get("original_last_name", "") or "")))
    return True


async def name_emoji_loop(user_id):
    uid = int(user_id)
    task = asyncio.current_task()
    try:
        while True:
            cfg = get_name_emoji_config(uid)
            if not cfg.get("enabled") or not is_user_active(uid) or not is_user_allowed(uid):
                break
            emojis = list(dict.fromkeys(cfg.get("emojis", [])))
            if not emojis:
                await asyncio.sleep(5)
                continue
            index = int(cfg.get("current_index", 0) or 0) % len(emojis)
            emoji = emojis[index]
            try:
                ok = await _update_name_with_emoji(uid, emoji)
                if ok:
                    cfg["current_index"] = (index + 1) % len(emojis)
                    cfg["last_error_notice"] = 0
                    save_json(USERS_FILE, users_db)
            except asyncio.CancelledError:
                raise
            except FloodWaitError as e:
                wait_seconds = max(60, int(getattr(e, "seconds", 60) or 60))
                log_error(f"name emoji FloodWait {uid}: waiting {wait_seconds}s")
                await _notify_name_emoji_failure(uid, f"تلگرام محدودیت موقت گذاشت؛ {wait_seconds} ثانیه صبر می‌کنم.")
                await asyncio.sleep(wait_seconds)
            except Exception as e:
                log_error(f"name emoji {uid}: {_translate_bot_errors(e)}")
                await _notify_name_emoji_failure(uid, _translate_bot_errors(e))
            # Apply interval/position changes from the panel during the current wait.
            sent_at = time.monotonic()
            while get_name_emoji_config(uid).get("enabled"):
                interval = max(60, int(get_name_emoji_config(uid).get("interval", 60) or 60))
                remaining = interval - (time.monotonic() - sent_at)
                if remaining <= 0:
                    break
                await asyncio.sleep(min(1, remaining))
    except asyncio.CancelledError:
        pass
    except Exception as e:
        log_error(f"name_emoji_loop {uid}: {_translate_bot_errors(e)}")
    finally:
        if name_emoji_tasks.get(uid) is task:
            name_emoji_tasks.pop(uid, None)


def start_name_emoji_task(user_id):
    uid = int(user_id)
    task = name_emoji_tasks.get(uid)
    if task and not task.done():
        return False
    name_emoji_tasks[uid] = asyncio.create_task(name_emoji_loop(uid))
    return True


def stop_name_emoji_task(user_id):
    uid = int(user_id)
    task = name_emoji_tasks.pop(uid, None)
    if task and not task.done():
        task.cancel()


async def _notify_name_emoji_failure(uid, reason):
    cfg = get_name_emoji_config(uid)
    now = time.time()
    if now - float(cfg.get("last_error_notice", 0) or 0) < 3600:
        return
    cfg["last_error_notice"] = now
    save_json(USERS_FILE, users_db)
    await _notify_feature(uid, "emoji_name", f"⚠️ تغییر ایموجی اسم انجام نشد: {reason}")


def get_random_profile_config(uid):
    user = users_db.setdefault("users", {}).setdefault(str(int(uid)), {})
    cfg = user.setdefault("random_profile", {})
    cfg.setdefault("enabled", False)
    cfg.setdefault("interval", 60)
    cfg.setdefault("photo_ids", [])
    cfg.setdefault("next_index", 0)
    cfg.setdefault("last_error_notice", 0)
    return cfg


def _as_input_profile_photo(photo):
    photo_id = getattr(photo, "id", None)
    access_hash = getattr(photo, "access_hash", None)
    if photo_id is None or access_hash is None:
        return None
    return types.InputPhoto(
        id=int(photo_id), access_hash=int(access_hash),
        file_reference=bytes(getattr(photo, "file_reference", b"") or b""))


async def _load_own_profile_photos(uid):
    client = user_clients.get(int(uid))
    if not client or not client.is_connected():
        client = await ensure_user_client(uid)
    if not client:
        raise RuntimeError("اکانت تلگرام متصل نیست.")
    photos = await client.get_profile_photos("me")
    valid = [(int(p.id), p) for p in photos if _as_input_profile_photo(p)]
    return client, valid


async def set_random_profile_enabled(uid, enabled):
    cfg = get_random_profile_config(uid)
    if not enabled:
        cfg["enabled"] = False
        save_json(USERS_FILE, users_db)
        stop_random_profile_task(uid)
        return True, "🔴 چرخش عکس پروفایل خاموش شد؛ عکس فعلی دست‌نخورده می‌ماند."
    try:
        _client, photos = await _load_own_profile_photos(uid)
    except Exception as e:
        return False, f"❌ دریافت عکس‌های پروفایل ممکن نشد: {_translate_bot_errors(e)}"
    photo_ids = [photo_id for photo_id, _ in photos]
    if len(photo_ids) < 2:
        cfg["enabled"] = False
        cfg["photo_ids"] = photo_ids
        save_json(USERS_FILE, users_db)
        return False, f"❌ حداقل ۲ عکس در گالری پروفایل لازم است؛ اکنون {len(photo_ids)} عکس پیدا شد."
    cfg["photo_ids"] = photo_ids
    cfg["next_index"] = 0
    cfg["interval"] = int(cfg.get("interval", 60) or 60)
    if cfg["interval"] not in (60, 300, 600):
        cfg["interval"] = 60
    cfg["enabled"] = True
    save_json(USERS_FILE, users_db)
    start_random_profile_task(uid)
    return True, f"🟢 چرخش روشن شد؛ {len(photo_ids)} عکس به‌ترتیب گالری بررسی می‌شوند."


async def _notify_random_profile_issue(uid, message):
    cfg = get_random_profile_config(uid)
    now = time.time()
    if now - float(cfg.get("last_error_notice", 0) or 0) < 3600:
        return
    cfg["last_error_notice"] = now
    save_json(USERS_FILE, users_db)
    await _notify_user(uid, message)


async def random_profile_loop(user_id):
    uid = int(user_id)
    task = asyncio.current_task()
    try:
        while True:
            cfg = get_random_profile_config(uid)
            if not cfg.get("enabled") or not is_user_active(uid) or not is_user_allowed(uid):
                break
            try:
                client, photos = await _load_own_profile_photos(uid)
                photo_map = {photo_id: photo for photo_id, photo in photos}
                photo_ids = [int(x) for x in cfg.get("photo_ids", [])]
                if not photo_ids:
                    photo_ids = [photo_id for photo_id, _ in photos]
                photo_ids = [photo_id for photo_id in photo_ids if photo_id in photo_map]
                if len(photo_ids) < 2:
                    cfg["enabled"] = False
                    cfg["photo_ids"] = photo_ids
                    save_json(USERS_FILE, users_db)
                    await _notify_random_profile_issue(
                        uid, "⚠️ چرخش عکس پروفایل خاموش شد؛ برای ادامه حداقل ۲ عکس در گالری لازم است.")
                    break
                cfg["photo_ids"] = photo_ids
                index = int(cfg.get("next_index", 0) or 0) % len(photo_ids)
                photo_id = photo_ids[index]
                await client(UpdateProfilePhotoRequest(id=_as_input_profile_photo(photo_map[photo_id])))
                cfg["next_index"] = (index + 1) % len(photo_ids)
                cfg["last_applied_photo_id"] = photo_id
                cfg["last_error_notice"] = 0
                save_json(USERS_FILE, users_db)
            except asyncio.CancelledError:
                raise
            except FloodWaitError as e:
                wait_seconds = max(1, int(getattr(e, "seconds", 1) or 1))
                log_error(f"random profile FloodWait {uid}: {wait_seconds}s")
                await _notify_random_profile_issue(
                    uid, f"⚠️ تلگرام برای تغییر عکس {wait_seconds} ثانیه مکث خواست.")
                await asyncio.sleep(wait_seconds)
                continue
            except Exception as e:
                log_error(f"random profile {uid}: {_translate_bot_errors(e)}")
                await _notify_random_profile_issue(
                    uid, f"⚠️ تغییر عکس پروفایل انجام نشد: {_translate_bot_errors(e)}")
            started = time.monotonic()
            while get_random_profile_config(uid).get("enabled"):
                interval = int(get_random_profile_config(uid).get("interval", 60) or 60)
                if interval not in (60, 300, 600):
                    interval = 60
                remaining = interval - (time.monotonic() - started)
                if remaining <= 0:
                    break
                await asyncio.sleep(min(1, remaining))
    except asyncio.CancelledError:
        pass
    except Exception as e:
        log_error(f"random_profile_loop {uid}: {_translate_bot_errors(e)}")
    finally:
        if random_profile_tasks.get(uid) is task:
            random_profile_tasks.pop(uid, None)


def start_random_profile_task(uid):
    uid = int(uid)
    task = random_profile_tasks.get(uid)
    if task and not task.done():
        return False
    random_profile_tasks[uid] = asyncio.create_task(random_profile_loop(uid))
    return True


def stop_random_profile_task(uid):
    task = random_profile_tasks.pop(int(uid), None)
    if task and not task.done():
        task.cancel()


async def _pm_build_random_profile_panel(uid):
    cfg = get_random_profile_config(uid)
    count = len(cfg.get("photo_ids", []))
    if not cfg.get("enabled"):
        try:
            _client, photos = await _load_own_profile_photos(uid)
            cfg["photo_ids"] = [photo_id for photo_id, _ in photos]
            count = len(cfg["photo_ids"])
            save_json(USERS_FILE, users_db)
        except Exception:
            count = len(cfg.get("photo_ids", []))
    interval = int(cfg.get("interval", 60) or 60)
    labels = {60: "۱ دقیقه", 300: "۵ دقیقه", 600: "۱۰ دقیقه"}
    if interval not in labels:
        interval = 60
        cfg["interval"] = interval
    count_label = str(count) if count else "قابل‌خواندن نیست"
    text = (
        "📷 <b>پروفایل رندوم</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"وضعیت: {'🟢 روشن' if cfg.get('enabled') else '🔴 خاموش'}\n"
        f"عکس‌های گالری پروفایل: {count_label}\n"
        f"بازه: هر {labels[interval]}\n"
        "━━━━━━━━━━━━━━━━━\n"
        "عکس‌های موجود در گالری پروفایل را به‌ترتیب جدیدترین تا قدیمی‌ترین، یکی‌یکی «اصلی» می‌کند؛ سپس از اول تکرار می‌شود.\n"
        "برای روشن‌کردن حداقل ۲ عکس لازم است. فهرست هنگام روشن‌شدن ثبت می‌شود؛ برای افزودن عکس‌های جدید خاموش و دوباره روشن کن.\n"
        f"دستورها: <code>{CMD}پروفایل رندوم روشن</code> · <code>{CMD}پروفایل رندوم خاموش</code>"
    )
    kb = [[_cb("🔴 خاموش کن" if cfg.get("enabled") else "🟢 روشن کن", "pn_random_profile_toggle")]]
    kb.append([
        _cb(f"{'✅ ' if interval == 60 else '⏱ '}۱ دقیقه", "pn_random_profile_iv_60"),
        _cb(f"{'✅ ' if interval == 300 else '⏱ '}۵ دقیقه", "pn_random_profile_iv_300"),
        _cb(f"{'✅ ' if interval == 600 else '⏱ '}۱۰ دقیقه", "pn_random_profile_iv_600"),
    ])
    kb.extend([
        [_cb("🔄 بازخوانی پنل", "pn_random_profile_panel")],
        [_cb("⚪ 🔙 بازگشت", "pn_tools")],
    ])
    return text, kb


async def _pm_build_tools(uid):
    u = users_db["users"].get(str(uid), {})
    html_on = u.get("html_style_on", False)
    font_on = u.get("font_on", False)
    html_cur = HTML_STYLES.get(u.get("html_style", "bold"), HTML_STYLES["bold"])["label"]
    font_cur = ENGLISH_FONTS.get(u.get("font", "none"), ENGLISH_FONTS["none"])["label"]
    allowed = is_media_allowed(uid)
    name_emoji_on = get_name_emoji_config(uid).get("enabled", False)
    monitor_on = monitor_db.get(str(int(uid)), {}).get("enabled", False)
    random_profile_on = get_random_profile_config(uid).get("enabled", False)
    active_list = []
    if html_on: active_list.append(f"🎨 ({html_cur})")
    if font_on: active_list.append(f"🔤 ({font_cur})")
    if name_emoji_on: active_list.append("😀 ایموجی اسم")
    if monitor_on: active_list.append("👁 پایش پروفایل")
    if random_profile_on: active_list.append("📷 پروفایل رندوم")
    off_list = []
    if not html_on: off_list.append("🎨")
    if not font_on: off_list.append("🔤 فونت")
    if not name_emoji_on: off_list.append("😀 ایموجی اسم")
    if not monitor_on: off_list.append("👁 پایش پروفایل")
    if not random_profile_on: off_list.append("📷 پروفایل رندوم")
    if allowed:
        tcfg = get_ttl_config(uid)
        if tcfg.get("enabled"): active_list.append("🔥 TTL")
        else: off_list.append("🔥 TTL")
    active_str = " · ".join(active_list) if active_list else "—"
    off_str = " · ".join(off_list) if off_list else "—"
    text = (
        "🛠 ابزارها\n━━━━━━━━━━━━━━━━━\n"
        f"🟢 فعال: {active_str}\n🔴 خاموش: {off_str}\n"
        "━━━━━━━━━━━━━━━━━"
    )
    kb = [[_cb("🎨 استایل HTML", "pn_html_panel"), _cb("🔤 فونت", "pn_font_panel")]]
    if allowed:
        kb.append([_cb("🔥 TTL", "pn_ttl_panel"), _cb("📥 ذخیره", "pn_save_panel")])
    kb.extend([
        [_cb("🔊 تبدیل متن و ویس", "pn_tts_panel"), _cb("👁 پایش پروفایل", "pn_mon_main")],
        [_cb("😀 ایموجی اسم", "pn_name_emoji_panel"),
         _cb("📷 پروفایل رندوم", "pn_random_profile_panel")],
        [_cb("⚪ 🔙 بازگشت", "pn_refresh")],
    ])
    return text, kb

async def _pm_build_name_emoji_panel(uid):
    cfg = get_name_emoji_config(uid)
    selected = list(dict.fromkeys(cfg.get("emojis", [])))
    custom = list(dict.fromkeys(cfg.get("custom_emojis", [])))
    all_emojis = list(dict.fromkeys(NAME_EMOJI_PRESETS + custom))
    position = cfg.get("position", "start")
    interval = int(cfg.get("interval", 60) or 60)
    interval_label = {60: "۱ دقیقه", 300: "۵ دقیقه", 600: "۱۰ دقیقه"}.get(interval, f"{interval} ثانیه")
    text = (
        "😀 <b>پنل ایموجی اسم</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"📊 وضعیت: {'🟢 روشن' if cfg.get('enabled') else '🔴 خاموش'}\n"
        f"📍 موقعیت: {'ابتدای اسم' if position == 'start' else 'انتهای اسم'}\n"
        f"⏱ زمان‌بندی: هر {interval_label}\n"
        f"✨ ایموجی‌های انتخاب‌شده: {' '.join(html_lib.escape(x) for x in selected) if selected else '—'}\n"
        "━━━━━━━━━━━━━━━━━\n"
        "ایموجی‌ها به نام پروفایل تلگرامت اضافه می‌شوند و می‌چرخند."
    )
    kb = [[_cb("🔴 خاموش کن" if cfg.get("enabled") else "🟢 روشن کن", "pn_name_emoji_toggle")]]
    kb.append([
        _cb(f"{'✅ ' if position == 'start' else ''}📍 ابتدا", "pn_emoji_pos_start"),
        _cb(f"{'✅ ' if position == 'end' else ''}📍 انتها", "pn_emoji_pos_end"),
    ])
    kb.append([
        _cb(f"{'✅ ' if interval == 60 else '⏱ '}۱ دقیقه", "pn_emoji_iv_60"),
        _cb(f"{'✅ ' if interval == 300 else '⏱ '}۵ دقیقه", "pn_emoji_iv_300"),
        _cb(f"{'✅ ' if interval == 600 else '⏱ '}۱۰ دقیقه", "pn_emoji_iv_600"),
    ])
    for i in range(0, len(all_emojis), 4):
        row = []
        for emoji in all_emojis[i:i+4]:
            mark = "✅" if emoji in selected else "▫️"
            row.append(_cb(f"{mark} {emoji}", f"pn_name_emoji_pick_{all_emojis.index(emoji)}"))
        kb.append(row)
    kb.append([_cb("➕ افزودن ایموجی دلخواه", "pn_name_emoji_add")])
    kb.append([_cb("⚪ 🔙 بازگشت", "pn_tools")])
    return text, kb


async def _pm_build_html_panel(uid):
    u = users_db["users"].get(str(uid), {})
    on = u.get("html_style_on", False)
    cur = u.get("html_style", "bold")
    text = (
        "🎨 استایل HTML\n━━━━━━━━━━━━━━━━━\n"
        f"وضعیت: {'🟢 روشن' if on else '🔴 خاموش'}\n"
        f"فعلی: {HTML_STYLES[cur]['label']}\n\n"
        f"💡 هر استایل با خودش نمایش داده شده"
    )
    kb = [[_cb(f"{'🔴 خاموش کن' if on else '🟢 روشن کن'}", "pn_html_toggle")]]
    items = [(k, v) for k, v in HTML_STYLES.items() if k not in ("none", "pre")]
    for i in range(0, len(items), 2):
        row = []
        for j in range(2):
            idx = i + j
            if idx < len(items):
                k, s = items[idx]
                mark = "✅" if k == cur else "▫️"
                row.append(_cb(f"{mark} {k}", f"pn_html_pick_{k}"))
        if row: kb.append(row)
    kb.append([_cb("⚪ 🔙 بازگشت", "pn_tools")])
    return text, kb

async def _pm_build_font_panel(uid):
    u = users_db["users"].get(str(uid), {})
    on = u.get("font_on", False)
    cur = u.get("font", "none")
    text = (
        "🔤 فونت انگلیسی\n━━━━━━━━━━━━━━━━━\n"
        f"وضعیت: {'🟢 روشن' if on else '🔴 خاموش'}\n"
        f"فعلی: {ENGLISH_FONTS[cur]['label']}\n\n"
        f"💡 هر فونت با خودش نمایش داده شده"
    )
    kb = [[_cb(f"{'🔴 خاموش کن' if on else '🟢 روشن کن'}", "pn_font_toggle")]]
    items = list(ENGLISH_FONTS.items())
    for i in range(0, len(items), 2):
        row = []
        for j in range(2):
            idx = i + j
            if idx < len(items):
                k, s = items[idx]
                mark = "✅" if k == cur else "▫️"
                row.append(_cb(f"{mark} {k}", f"pn_font_pick_{k}"))
        if row: kb.append(row)
    kb.append([_cb("⚪ 🔙 بازگشت", "pn_tools")])
    return text, kb

async def _pm_build_ttl_panel(uid):
    if not is_media_allowed(uid):
        return ("🔒 این بخش در دسترس نیست.", [[_cb("⚪ 🔙 بازگشت", "pn_tools")]])
    cfg = get_ttl_config(uid)
    on = cfg["enabled"]
    target = cfg["target"]
    tname = "پیام‌های ذخیره شده" if target == "me" else str(target)
    text = (
        "🔥 ذخیره رسانه ناپدیدشونده\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"وضعیت: {'🟢 روشن' if on else '🔴 خاموش'}\n"
        f"🎯 مقصد: <b>{tname}</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        "💡 وقتی روشن باشه، عکس/ویدیوهای خودتخریب\n"
        "که برات میاد، قبل ناپدید شدن ذخیره می‌شن.\n"
        "━━━━━━━━━━━━━━━━━"
    )
    kb = [
        [_cb(f"{'🔴 خاموش کن' if on else '🟢 روشن کن'}", "pn_ttl_toggle")],
        [_cb("🏠 مقصد پیش‌فرض (Saved)", "pn_ttl_reset_target")],
        [_cb("⚪ 🔙 بازگشت", "pn_tools")],
    ]
    return text, kb

async def _pm_build_save_panel(uid):
    if not is_media_allowed(uid):
        return ("🔒 این بخش در دسترس نیست.", [[_cb("⚪ 🔙 بازگشت", "pn_tools")]])
    text = (
        "📥 ذخیره رسانه\n"
        "━━━━━━━━━━━━━━━━━\n"
        "💡 <b>دو روش داره:</b>\n\n"
        "1️⃣ روی یه پیام ریپلای کن و بنویس:\n"
        f"   <code>{CMD}ذخیره</code>\n\n"
        "2️⃣ لینک تلگرامی بفرست:\n"
        f"   <code>{CMD}ذخیره https://t.me/c/xxx/123</code>\n"
        f"   <code>{CMD}ذخیره https://t.me/username/456</code>\n"
        "━━━━━━━━━━━━━━━━━\n"
        "📝 اگر رسانه کپشن/نوشته داشته باشه، همون متن همراهش ذخیره می‌شه.\n"
        "🖼 اگر پیام آلبوم چندرسانه‌ای باشه، همهٔ رسانه‌های آلبوم ذخیره می‌شن.\n"
        "━━━━━━━━━━━━━━━━━\n"
        "🎯 رسانه ذخیره می‌شه تو:\n"
        "   <b>پیام‌های ذخیره شده (Saved Messages)</b>"
    )
    kb = [[_cb("⚪ 🔙 بازگشت", "pn_tools")]]
    return text, kb

async def _pm_build_media_access_panel(uid):
    if not is_grp_owner(uid):
        return ("🔒 فقط مالک", [[_cb("⚪ 🔙", "pn_refresh")]])
    users = get_media_allowed_users()
    lines = ["🔐 دسترسی‌های ویژه TTL/ذخیره", "━━━━━━━━━━━━━━━━━"]
    if not users:
        lines.append("")
        lines.append("📭 هنوز کسی دسترسی نداره")
        lines.append("")
        lines.append("💡 <code>،اجازه &lt;user&gt;</code>")
        lines.append("💡 یا ریپلای + <code>،اجازه</code>")
    else:
        lines.append(f"📊 {len(users)} کاربر مجاز")
        lines.append("")
        cl = user_clients.get(int(uid))
        for i, u in enumerate(users, 1):
            try: nm = await get_plain_name(cl, u) if cl else str(u)
            except: nm = str(u)
            lines.append(f"{i}. {nm}")
            lines.append(f"   🆔 <code>{u}</code>")
            lines.append(f"   <code>،لغو اجازه {u}</code>")
    kb = [
        [_cb("➕ افزودن دسترسی ویژه", "pn_media_grant_list_0")],
        [_cb("🗑 حذف از لیست ویژه", "pn_media_remove_list_0")],
        [_cb("🔄 بروزرسانی", "pn_media_panel")],
        [_cb("⚪ 🔙 بازگشت", "pn_owner")],
    ]
    return "\n".join(lines), kb


def _get_media_grant_candidates():
    """اعضای ربات که هنوز دسترسی ویژه (TTL/ذخیره) ندارند."""
    candidates = []
    for raw_uid, info in users_db.get("users", {}).items():
        try: target = int(raw_uid)
        except (TypeError, ValueError): continue
        if is_grp_owner(target) or info.get("media_allowed", False): continue
        if info.get("banned"):
            icon = "🚫"
        elif info.get("active"):
            icon = "🟢"
        else:
            icon = "🔴"
        candidates.append((target, str(info.get("name") or target), icon))
    candidates.sort(key=lambda item: (item[2], item[1].casefold()))
    return candidates


async def _pm_build_media_grant_list(uid, page=0, notice=None):
    if not is_grp_owner(uid):
        return ("🔒 فقط مالک", [[_cb("⚪ 🔙", "pn_owner")]])
    candidates = _get_media_grant_candidates()
    per_page = 15
    page_count = max(1, (len(candidates) + per_page - 1) // per_page)
    page = max(0, min(int(page), page_count - 1))
    start = page * per_page
    shown = candidates[start:start + per_page]
    lines = ["➕ افزودن دسترسی ویژه", "━━━━━━━━━━━━━━━━━"]
    if notice:
        lines.extend([notice, ""])
    if not candidates:
        lines.append("📭 کاربری بدون دسترسی برای افزودن پیدا نشد.")
    else:
        lines.append(f"📊 {len(candidates)} عضو بدون دسترسی ویژه")
        lines.append(f"👇 روی دکمهٔ هر عضو بزنید تا تأیید بگیرید. ({page + 1}/{page_count})")
    kb = []
    for target, name, icon in shown:
        label = " ".join(name.split())[:24] or str(target)
        kb.append([_cb(f"{icon} {label} · {target}", f"pn_media_grant_pick_{target}_{page}")])
    if page_count > 1:
        nav = []
        if page > 0: nav.append(_cb("⬅️ قبلی", f"pn_media_grant_list_{page - 1}"))
        if page + 1 < page_count: nav.append(_cb("بعدی ➡️", f"pn_media_grant_list_{page + 1}"))
        if nav: kb.append(nav)
    kb.extend([
        [_cb("🔙 بازگشت به دسترسی‌های ویژه", "pn_media_panel")],
        [_cb("⚪ بازگشت به پنل مالک", "pn_owner")],
    ])
    return "\n".join(lines), kb


async def _pm_build_media_grant_confirm(uid, target, page=0):
    if not is_grp_owner(uid):
        return ("🔒 فقط مالک", [[_cb("⚪ 🔙", "pn_owner")]])
    target = int(target)
    info = users_db.get("users", {}).get(str(target))
    if not info or is_grp_owner(target) or is_media_allowed(target):
        return await _pm_build_media_grant_list(
            uid, page, "ℹ️ این کاربر دیگر برای افزودن در دسترس نیست."
        )
    name = html_lib.escape(" ".join(str(info.get("name") or target).split()))
    text = (
        "⚠️ تأیید افزودن دسترسی ویژه\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"کاربر: {name}\n🆔 <code>{target}</code>\n\n"
        "آیا دسترسی TTL/ذخیره به این کاربر داده شود؟"
    )
    kb = [[_cb("✅ بله، اضافه کن", f"pn_media_grant_yes_{target}_{page}"),
           _cb("❌ خیر", f"pn_media_grant_no_{page}")]]
    return text, kb


async def _pm_build_media_remove_list(uid, page=0, notice=None):
    if not is_grp_owner(uid):
        return ("🔒 فقط مالک", [[_cb("⚪ 🔙", "pn_owner")]])
    users = [u for u in get_media_allowed_users() if not is_grp_owner(u)]
    per_page = 15
    page_count = max(1, (len(users) + per_page - 1) // per_page)
    page = max(0, min(int(page), page_count - 1))
    start = page * per_page
    shown = users[start:start + per_page]
    lines = ["🗑 حذف دسترسی ویژه", "━━━━━━━━━━━━━━━━━"]
    if notice:
        lines.extend([notice, ""])
    if not users:
        lines.append("📭 کاربری در فهرست دسترسی ویژه نیست.")
    else:
        lines.append(f"برای انتخاب کاربر روی دکمهٔ نامش بزنید. ({page + 1}/{page_count})")
    kb = []
    cl = user_clients.get(int(uid))
    for target in shown:
        try:
            name = await get_plain_name(cl, target) if cl else str(target)
        except Exception:
            name = str(target)
        name = " ".join(str(name).split())[:24] or str(target)
        kb.append([_cb(f"👤 {name} · {target}", f"pn_media_remove_pick_{target}_{page}")])
    if page_count > 1:
        nav = []
        if page > 0:
            nav.append(_cb("⬅️ قبلی", f"pn_media_remove_list_{page - 1}"))
        if page + 1 < page_count:
            nav.append(_cb("بعدی ➡️", f"pn_media_remove_list_{page + 1}"))
        if nav:
            kb.append(nav)
    kb.extend([
        [_cb("🔙 بازگشت به دسترسی‌های ویژه", "pn_media_panel")],
        [_cb("⚪ بازگشت به پنل مالک", "pn_owner")],
    ])
    return "\n".join(lines), kb


async def _pm_build_media_remove_confirm(uid, target, page=0):
    if not is_grp_owner(uid):
        return ("🔒 فقط مالک", [[_cb("⚪ 🔙", "pn_owner")]])
    target = int(target)
    if is_grp_owner(target) or not is_media_allowed(target):
        return await _pm_build_media_remove_list(
            uid, page, "ℹ️ این کاربر دیگر در فهرست افراد مجاز نیست."
        )
    cl = user_clients.get(int(uid))
    try:
        name = await get_plain_name(cl, target) if cl else str(target)
    except Exception:
        name = str(target)
    safe_name = html_lib.escape(" ".join(str(name).split()))
    text = (
        "⚠️ تأیید حذف دسترسی ویژه\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"کاربر: {safe_name}\n🆔 <code>{target}</code>\n\n"
        "آیا دسترسی TTL/ذخیرهٔ این کاربر حذف شود؟"
    )
    kb = [
        [_cb("✅ بله، حذف کن", f"pn_media_remove_yes_{target}_{page}"),
         _cb("❌ خیر", f"pn_media_remove_no_{page}")],
    ]
    return text, kb


async def _pm_build_notif_panel(uid):
    notifs = get_user_notifs(uid)
    mat_on = notifs.get("mat_trans", True)
    item_on = notifs.get("item_trans", True)
    sell_on = notifs.get("sell", True)
    monitor_on = notifs.get("monitor", True)
    emoji_on = notifs.get("emoji_name", True)
    
    text = (
        "🔔 <b>مدیریت اعلان‌ها</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        "این دکمه‌ها فقط اعلان‌های پی‌وی را کنترل می‌کنند، نه خود عملیات را.\n"
        "📦 انتقال مواد / 🎁 انتقال کالا: اعلانِ ناموفق‌بودن انتقال پیش از فروش\n"
        "💰 گزارش فروش: پیام‌های وضعیت فروش\n"
        "👁 پایش و 😀 ایموجی اسم: اعلان‌های مربوط به این قابلیت‌ها\n"
        "🟢 = اعلان روشن  ·  🔴 = اعلان خاموش\n"
    )
    kb = [
        [_cb(f"{'🟢' if mat_on else '🔴'} انتقال مواد", "pn_notif_toggle_mat")],
        [_cb(f"{'🟢' if item_on else '🔴'} انتقال کالا", "pn_notif_toggle_item")],
        [_cb(f"{'🟢' if sell_on else '🔴'} گزارش فروش", "pn_notif_toggle_sell")],
        [_cb(f"{'🟢' if monitor_on else '🔴'} پایش پروفایل", "pn_notif_toggle_mon")],
        [_cb(f"{'🟢' if emoji_on else '🔴'} ایموجی اسم", "pn_notif_toggle_emoji")],
        [_cb("⚪ 🔙 بازگشت", "pn_settings")],
    ]
    return text, kb

async def _pm_build_settings_panel(uid):
    g = get_user_gender(uid)
    bid = get_user_banner_id(uid)
    b = get_gender_banner_by_id(bid) if bid else None
    banner_status = "✅ انتخاب شده" if b else "❌ بدون عکس"
    lines = [
        "⚙️ تنظیمات", "━━━━━━━━━━━━━━━━━",
        f"👤 جنسیت: {'🩷 دختر' if g=='girl' else '💙 پسر' if g=='boy' else '❓ نامشخص'}",
        f"🖼 عکس: {banner_status}",
        "━━━━━━━━━━━━━━━━━",
    ]
    kb = [
        [_cb("👤 تغییر جنسیت", "pn_gender_panel")],
        [_cb("🖼 انتخاب عکس", "pn_banner_picker")],
        [_cb("🔔 مدیریت اعلان‌ها", "pn_notif_panel")],
        [_cb("⚪ 🔙 بازگشت", "pn_refresh")],
    ]
    return "\n".join(lines), kb

async def _pm_build_gender_panel(uid):
    cur = get_user_gender(uid)
    cur_label = {"girl": "🩷 دختر", "boy": "💙 پسر"}.get(cur, "❓ نامشخص")
    lines = ["👤 انتخاب جنسیت", "━━━━━━━━━━━━━━━━━", f"فعلی: {cur_label}"]
    kb = [
        [_cb("🩷 دختر", "pn_gender_set_girl"), _cb("💙 پسر", "pn_gender_set_boy")],
        [_cb("❓ نامشخص", "pn_gender_set_none")],
        [_cb("⚪ 🔙 بازگشت", "pn_settings")],
    ]
    return "\n".join(lines), kb

async def _pm_build_banner_picker(uid, page=0):
    g = get_user_gender(uid)
    if not g:
        return ("❌ اول جنسیتت رو انتخاب کن.",
                [[_cb("👤 انتخاب جنسیت", "pn_gender_panel")],
                 [_cb("⚪ 🔙 بازگشت", "pn_settings")]])
    banners = gender_banners_db.get(g, [])
    per_page = 5
    total = len(banners)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    chunk = banners[start:start + per_page]
    cur_bid = get_user_banner_id(uid)
    g_label = "🩷 دختر" if g == "girl" else "💙 پسر"
    lines = [f"🖼 انتخاب عکس ({g_label})", f"📊 مجموع: {total}  ·  📄 {page+1}/{total_pages}"]
    kb = []
    for i, b in enumerate(chunk, start=start+1):
        likes = len(b.get("likes_by", []))
        dislikes = len(b.get("dislikes_by", []))
        mark = "✅" if b["id"] == cur_bid else "⬜"
        kb.append([_cb(f"{mark} عکس {i}  ·  👍{likes} 👎{dislikes}",
                       f"pn_banner_preview_{b['id']}")])
    nav = []
    if page > 0: nav.append(_cb("🔵 ⬅️", f"pn_banner_picker_{page-1}"))
    if page < total_pages - 1: nav.append(_cb("🔵 ➡️", f"pn_banner_picker_{page+1}"))
    if nav: kb.append(nav)
    kb.append([_cb("🚫 بدون عکس", "pn_banner_clear")])
    kb.append([_cb("⚪ 🔙 بازگشت", "pn_settings")])
    return "\n".join(lines), kb

async def _pm_build_banner_preview(uid, bid):
    b = get_gender_banner_by_id(bid)
    if not b:
        return "❌ بنر پیدا نشد.", [[_cb("⚪ 🔙 بازگشت", "pn_banner_picker")]], None
    likes = len(b.get("likes_by", []))
    dislikes = len(b.get("dislikes_by", []))
    users_count = len(b.get("users", []))
    cur_bid = get_user_banner_id(uid)
    is_chosen = (cur_bid == bid)
    i_liked = int(uid) in b.get("likes_by", [])
    i_disliked = int(uid) in b.get("dislikes_by", [])
    text = (
        f"🖼 پیش‌نمایش عکس\n━━━━━━━━━━━━━━━━━\n"
        f"👍 لایک: {likes}\n👎 دیس‌لایک: {dislikes}\n"
        f"👥 انتخاب‌کنندگان: {users_count}\n"
        f"وضعیت: {'✅ انتخاب‌شده' if is_chosen else '⬜ انتخاب نشده'}"
    )
    like_txt = f"{'✅ ' if i_liked else ''}👍 لایک"
    dis_txt = f"{'✅ ' if i_disliked else ''}👎 دیس‌لایک"
    kb = [
        [_cb(like_txt, f"pn_blike_{bid}"), _cb(dis_txt, f"pn_bdislike_{bid}")],
        [_cb("✅ انتخاب" if not is_chosen else "🗑 لغو", f"pn_bchoose_{bid}")],
        [_cb("⚪ 🔙 بازگشت", "pn_banner_picker")],
    ]
    return text, kb, b["file"]

async def _pm_build_nosell_panel(uid):
    lst = get_no_sell_list(uid)
    text = f"🚫 نفروش — {len(lst)} آیتم"
    kb = [
        [_cb("🟢 ➕ افزودن", "pn_nosell_add")],
        [_cb(f"🔵 📋 مشاهده ({len(lst)})", "pn_nosell_view")],
        [_cb("🔴 🗑 حذف", "pn_nosell_remove_0")],
        [_cb("⚪ 🔙 بازگشت", "pn_cardinal_panel")],
    ]
    return text, kb

async def _pm_build_nosell_view(uid):
    lst = get_no_sell_list(uid)
    lines = [f"📋 نفروش ({len(lst)})", "━━━━━━━━━━━━━━━━━"]
    if not lst: lines.append("📭 خالی")
    else:
        for i, nm in enumerate(lst, 1): lines.append(f"{i}. {nm}")
    kb = [
        [_cb("🟢 ➕", "pn_nosell_add"), _cb("🔴 🗑", "pn_nosell_remove_0")],
        [_cb("⚪ 🔙 بازگشت", "pn_nosell_panel")],
    ]
    return "\n".join(lines), kb

async def _pm_build_nosell_remove_list(uid, page=0):
    lst = get_no_sell_list(uid)
    total = len(lst)
    per_page = 8
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    chunk = lst[start:start + per_page]
    lines = [f"🗑 حذف — {page+1}/{total_pages}"]
    kb = []
    for idx, nm in enumerate(chunk, start=start):
        short = nm if len(nm) <= 25 else nm[:22] + "..."
        kb.append([_cb(f"🔴 {short}", f"pn_nosell_rm_{idx}")])
    nav = []
    if page > 0: nav.append(_cb("🔵 ⬅️", f"pn_nosell_remove_{page-1}"))
    if page < total_pages - 1: nav.append(_cb("🔵 ➡️", f"pn_nosell_remove_{page+1}"))
    if nav: kb.append(nav)
    kb.append([_cb("⚪ 🔙 بازگشت", "pn_nosell_panel")])
    return "\n".join(lines), kb

async def _pm_build_nosell_rm_confirm(uid, idx):
    lst = get_no_sell_list(uid)
    if idx < 0 or idx >= len(lst): return "❌ نیست.", [[_cb("⚪ 🔙 بازگشت", "pn_nosell_panel")]]
    item = lst[idx]
    text = f"🗑 حذف\n📛 {item}\n❓ مطمئنی؟"
    kb = [[_cb("🟢 ✅", f"pn_nosell_rm_yes_{idx}")], [_cb("🔴 🔙", "pn_nosell_panel")]]
    return text, kb

async def _pm_build_pony_pick(uid, page=0):
    groups = await _pm_get_user_groups(uid, limit=200)
    per_page = 10
    total = len(groups)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    chunk = groups[start:start + per_page]
    lines = [
        "🐴 انتخاب گروه", "━━━━━━━━━━━━━━━━━",
        f"📄 صفحه {page+1} از {total_pages}  ·  {total} گروه",
    ]
    kb = []
    cur_chat = pm_panel_chat.get(int(uid))
    if cur_chat:
        cur_title = str(cur_chat)
        try:
            c = user_clients.get(int(uid))
            if c:
                ent = await c.get_entity(cur_chat)
                cur_title = getattr(ent, 'title', None) or cur_title
        except: pass
        kb.append([_cb(f"📍 محل فعلی: {cur_title[:30]}", f"pn_pony_sel_{cur_chat}")])
        lines.append("━━━━━━━━━━━━━━━━━")
    if chunk:
        lines.append("👇 روی گروه بزن:")
        for g in chunk:
            if cur_chat and int(g["id"]) == int(cur_chat): continue
            kb.append([_cb(f"💬 {g['title'][:35]}", f"pn_pony_sel_{g['id']}")])
    else:
        if not cur_chat: lines.append("❌ گروهی نیست.")
    nav = []
    if page > 0: nav.append(_cb("⬅️ قبلی", f"pn_pony_pg_{page-1}"))
    if page < total_pages - 1: nav.append(_cb("بعدی ➡️", f"pn_pony_pg_{page+1}"))
    if nav: kb.append(nav)
    kb.append([_cb("⚪ 🔙 بازگشت", "pn_pony_main")])
    return "\n".join(lines), kb

async def _pm_build_pony_main(uid):
    """Pony section entry point; keep users in the section before group selection."""
    cid = pm_panel_chat.get(int(uid))
    if cid is None:
        text = (
            "🐴 پنل پونی و دانجن\n━━━━━━━━━━━━━━━━━\n"
            "هنوز گروهی انتخاب نشده.\n"
            "از دکمهٔ «تغییر گروه» یک گروه انتخاب کن.")
        kb = [
            [_cb("🔀 انتخاب / تغییر گروه", "pn_pony_pick")],
            [_cb("⚪ 🔙 بازگشت", "pn_games")],
        ]
        return text, kb
    return await _pm_build_pony_panel(uid, int(cid))


async def _pm_build_pony_ctrl(uid, cid):
    key = (int(uid), int(cid))
    cfg = pony_config.get(key, {"collect": False, "upgrade": False})
    is_on = bool(cfg.get("collect", False))
    interval = int(cfg.get("interval_mins", 15) or 15)
    interval_labels = {5: "۵", 10: "۱۰", 15: "۱۵", 20: "۲۰"}
    interval_label = interval_labels.get(interval, str(interval))
    title = str(cid)
    try:
        client = user_clients.get(int(uid))
        if client:
            ent = await client.get_entity(cid)
            title = getattr(ent, "title", None) or title
    except: pass
    title = html_lib.escape(str(title))
    text = (
        "🐴 تنظیمات پونی\n"
        f"📍 گروه انتخاب‌شده: <b>{title[:50]}</b>\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"وضعیت: {'🟢 روشن' if is_on else '🔴 خاموش'}\n"
        f"⏱ بازهٔ ارسال: {interval_label} دقیقه\n"
        "━━━━━━━━━━━━━━━━━\n"
        "بازهٔ انتخابی، فاصلهٔ اجرای خودکار پونی است."
    )
    def interval_button(minutes):
        label = interval_labels[minutes]
        mark = "✅ " if interval == minutes else "⏱ "
        return _cb(f"{mark}{label} دقیقه", f"pn_pony_interval_{cid}_{minutes}")
    kb = [
        [_cb("🔴 خاموش کن" if is_on else "🟢 روشن کن", f"pn_pony_t_{cid}")],
        [interval_button(5), interval_button(10)],
        [interval_button(15), interval_button(20)],
        [_cb("⚪ 🔙 بازگشت", f"pn_pony_sel_{cid}")],
    ]
    return text, kb


async def _pm_build_pony_panel(uid, cid):
    cfg = pony_config.get((int(uid), int(cid)), {"collect": False, "upgrade": False})
    dcfg = dungeon_config.get((int(uid), int(cid)), {"enabled": False, "current_idx": 0, "working_idx": -1})
    p_on = cfg.get("collect", False); u_on = cfg.get("upgrade", False)
    d_on = dcfg.get("enabled", False)
    w_idx = dcfg.get("working_idx", -1)
    d_work = DUNGEON_MONSTERS[w_idx] if 0 <= w_idx < len(DUNGEON_MONSTERS) else "—"
    title = str(cid)
    try:
        c = user_clients.get(int(uid))
        if c:
            ent = await c.get_entity(cid)
            title = getattr(ent, 'title', None) or title
    except: pass
    title = html_lib.escape(str(title))
    lines = [
        "🐴 پنل پونی و دانجن",
        f"📍 گروه انتخاب‌شده: <b>{title[:50]}</b>",
        f"پونی: {'🟢' if p_on else '🔴'}",
        f"ارتقا: {'🟢' if u_on else '🔴'}",
        f"دانجن: {'🟢' if d_on else '🔴'} · {d_work}",
        f"ناز خودکار: {'🟢 روشن' if cfg.get('naz_enabled') else '🔴 خاموش'} · "
        f"{int(cfg.get('naz_interval_mins', 3) or 3)} دقیقه و ۱۰ ثانیه",
    ]
    kb = [
        [_cb("🐴 پونی", f"pn_pony_ctrl_{cid}")],
        [_cb(f"{'🔴' if u_on else '🟢'} ارتقا", f"pn_up_t_{cid}")],
        [_cb("🔵 🏰 دانجن", f"pn_dgn_panel_{cid}")],
        [_cb("🔵 🔀 گروه", "pn_pony_pick")],
        [_cb("💞 ناز خودکار", f"pn_pony_naz_panel_{cid}")],
        [_cb("⚪ 🔙 بازگشت", "pn_games")],
    ]
    return "\n".join(lines), kb

async def _pm_build_naz_auto_panel(uid, cid):
    cfg = pony_config.get((int(uid), int(cid)), {})
    enabled = bool(cfg.get("naz_enabled", False))
    interval = int(cfg.get("naz_interval_mins", 3) or 3)
    if interval not in (3, 5):
        interval = 3
    title = str(cid)
    try:
        client = user_clients.get(int(uid))
        if client:
            entity = await client.get_entity(cid)
            title = getattr(entity, "title", None) or title
    except: pass
    title = html_lib.escape(str(title))
    interval_label = "۳" if interval == 3 else "۵"
    text = (
        "💞 <b>ناز خودکار</b>\n"
        f"📍 گروه: <b>{title[:50]}</b>\n"
        f"وضعیت: {'🟢 روشن' if enabled else '🔴 خاموش'}\n"
        f"⏱ بازهٔ انتخاب‌شده: هر {interval_label} دقیقه و ۱۰ ثانیه\n"
        "━━━━━━━━━━━━━━━━━\n"
        "در حالت روشن، پیام «ناز» در همین گروه ارسال می‌شود."
    )
    def interval_button(minutes):
        label = "۳" if minutes == 3 else "۵"
        mark = "✅ " if interval == minutes else "⏱ "
        return _cb(f"{mark}{label} دقیقه و ۱۰ ثانیه", f"pn_pony_naz_interval_{cid}_{minutes}")
    kb = [
        [_cb("🔴 خاموش کن" if enabled else "🟢 روشن کن", f"pn_pony_naz_toggle_{cid}")],
        [interval_button(3), interval_button(5)],
        [_cb("⚪ 🔙 بازگشت", f"pn_pony_sel_{cid}")],
    ]
    return text, kb


async def _pm_build_dungeon_panel(uid, cid):
    dcfg = dungeon_config.get((int(uid), int(cid)),
        {"enabled": False, "current_idx": 0, "working_idx": -1,
         "test_mode": False, "mode": "auto", "manual_idx": 0})
    d_on = dcfg.get("enabled", False)
    mode = dcfg.get("mode", "auto")
    manual_idx = dcfg.get("manual_idx", 0)
    current_idx = dcfg.get("current_idx", 0)
    working_idx = dcfg.get("working_idx", -1)
    if mode == "manual": playing_idx = manual_idx
    else: playing_idx = current_idx if 0 <= current_idx < len(DUNGEON_MONSTERS) else 0
    playing_monster = DUNGEON_MONSTERS[playing_idx]
    work_monster = DUNGEON_MONSTERS[working_idx] if 0 <= working_idx < len(DUNGEON_MONSTERS) else "—"
    lines = [
        "🏰 پنل دانجن",
        f"وضعیت: {'🟢' if d_on else '🔴'}",
        f"حالت: {'🤖' if mode == 'auto' else '✋'}",
        f"🎯 الان: {playing_monster}",
        f"🏆 انتخاب‌شده: {work_monster}",
    ]
    kb = [
        [_cb(f"{'🔴' if d_on else '🟢'} دانجن", f"pn_dgn_t_{cid}")],
        [_cb(f"{'✅ ' if mode == 'auto' else ''}🤖 اتومات", f"pn_dgn_mode_auto_{cid}"),
         _cb(f"{'✅ ' if mode == 'manual' else ''}✋ دستی", f"pn_dgn_mode_manual_{cid}")],
    ]
    if mode == "manual":
        for i in range(0, len(DUNGEON_MONSTERS), 2):
            row = []
            for j in range(2):
                mi = i + j
                if mi < len(DUNGEON_MONSTERS):
                    mark = "✅" if mi == manual_idx else "⬜"
                    row.append(_cb(f"{mark} {DUNGEON_MONSTERS[mi]}", f"pn_dgn_pick_{cid}_{mi}"))
            if row: kb.append(row)
    else:
        kb.append([_cb("🔵 🔄 ریست", f"pn_dgn_test_{cid}")])
    kb.append([_cb("⚪ 🔙 بازگشت", f"pn_pony_sel_{cid}")])
    return "\n".join(lines), kb

async def _pm_build_transfer(uid):
    cfg = transfer_configs.get(uid, {})
    on = cfg.get("enabled", False)
    lines = [
        "💸 انتقال سکه",
        f"وضعیت: {'🟢' if on else '🔴'}",
        f"👤 گیرنده: {cfg.get('c_id', '—')}",
        f"💰 مبلغ: {cfg.get('desired', 0):,}" if cfg.get('desired') else "💰 مبلغ: —",
        "",
        f"{CMD}انتقال تنظیم &lt;C_ID&gt; &lt;مبلغ&gt;",
    ]
    kb = [
        [_cb("🟢 روشن" if not on else "🔴 خاموش", "pn_transfer_toggle")],
        [_cb("⚪ 🔙 بازگشت", "pn_cardinal_panel")],
    ]
    return "\n".join(lines), kb

async def _pm_build_owner_full(uid):
    total = len(users_db["users"])
    active = sum(1 for u in users_db["users"].values() if u.get("active") and not u.get("banned"))
    banned = sum(1 for u in users_db["users"].values() if u.get("banned"))
    sessions_total = len(list(SESSION_DIR.glob("*.session")))
    connected = sum(1 for c in user_clients.values() if c.is_connected())
    lines = [
        "\u200e👑 مالک",
        f"\u200e👥 کل: {total}",
        f"\u200e🟢 فعال: {active}",
        f"\u200e🚫 بن: {banned}",
        f"\u200e💾 سشن: {sessions_total} · 🔗 متصل: {connected}",
        f"\u200e🐴 پونی: {len(pony_tasks)}",
        f"\u200e🏰 دانجن: {len(dungeon_tasks)}",
        f"\u200e📢 بنر: {len(broadcast_tasks)}",
    ]
    kb = [
        [_cb("🔵 👥 کاربران", "pn_users_0"), _cb("🟡 👮 مدیران", "pn_managers")],
        [_cb("🔐 دسترسی‌های ویژه", "pn_media_panel")],
        [_cb("🖼 مدیریت بنرها", "pn_gb_panel")],
        [_cb("📢 پیام همگانی", "pn_broadcast")],
        [_cb("🔵 🏓 پینگ", "pn_ping")],
        [_cb("🔵 🔄", "pn_owner"), _cb("⚪ 🔙 بازگشت", "pn_refresh")],
    ]
    return "\n".join(lines), kb

async def _pm_build_managers_panel(uid):
    managers = get_managers()
    lines = [f"\u200e👮 مدیران — {len(managers)}"]
    kb = []
    for m in managers:
        info = users_db["users"].get(str(m), {})
        name = (info.get("name") or m)[:22]
        kb.append([_cb(f"🟡 {name} · {m}", f"pn_user_{m}")])
    kb.append([_cb("🔵 🔄", "pn_managers"), _cb("⚪ 🔙 بازگشت", "pn_owner")])
    return "\n".join(lines), kb

async def _pm_build_gender_banners_panel(uid):
    girl_count = len(gender_banners_db.get("girl", []))
    boy_count = len(gender_banners_db.get("boy", []))
    lines = [
        "🖼 مدیریت بنرها", "━━━━━━━━━━━━━━━━━",
        f"🩷 دختر: {girl_count} عکس",
        f"💙 پسر: {boy_count} عکس",
        "━━━━━━━━━━━━━━━━━",
    ]
    kb = [
        [_cb("➕ آپلود (دختر)", "pn_gb_up_girl"), _cb("➕ آپلود (پسر)", "pn_gb_up_boy")],
        [_cb(f"🩷 لیست دختر ({girl_count})", "pn_gb_list_girl_0")],
        [_cb(f"💙 لیست پسر ({boy_count})", "pn_gb_list_boy_0")],
        [_cb("⚪ 🔙 بازگشت", "pn_owner")],
    ]
    return "\n".join(lines), kb

async def _pm_build_gender_list(uid, gender, page=0):
    banners = gender_banners_db.get(gender, [])
    per_page = 5
    total = len(banners)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    chunk = banners[start:start + per_page]
    g_label = "🩷 دختر" if gender == "girl" else "💙 پسر"
    lines = [f"🖼 لیست بنرهای {g_label}", f"📊 مجموع: {total}  ·  📄 {page+1}/{total_pages}"]
    kb = []
    for i, b in enumerate(chunk, start=start+1):
        users_count = len(b.get("users", []))
        likes = len(b.get("likes_by", []))
        kb.append([_cb(f"▫️ #{i} · 👥{users_count} · 👍{likes}", f"pn_gb_view_{b['id']}")])
    nav = []
    if page > 0: nav.append(_cb("⬅️", f"pn_gb_list_{gender}_{page-1}"))
    if page < total_pages - 1: nav.append(_cb("➡️", f"pn_gb_list_{gender}_{page+1}"))
    if nav: kb.append(nav)
    kb.append([_cb("➕ آپلود جدید", f"pn_gb_up_{gender}")])
    kb.append([_cb("⚪ 🔙 بازگشت", "pn_gb_panel")])
    return "\n".join(lines), kb

async def _pm_build_gender_view(uid, bid):
    b = get_gender_banner_by_id(bid)
    if not b:
        return "❌ بنر پیدا نشد.", [[_cb("⚪ 🔙 بازگشت", "pn_gb_panel")]], None
    users_count = len(b.get("users", []))
    likes = len(b.get("likes_by", []))
    dislikes = len(b.get("dislikes_by", []))
    uploader = b.get("uploaded_by", "?")
    uploaded_at = b.get("uploaded_at", "")[:19]
    gender = "girl" if bid.startswith("girl_") else "boy"
    g_label = "🩷 دختر" if gender == "girl" else "💙 پسر"
    text = (
        f"🖼 پیش‌نمایش بنر ({g_label})\n━━━━━━━━━━━━━━━━━\n"
        f"🆔 <code>{bid}</code>\n"
        f"👥 انتخاب‌کنندگان: {users_count}\n"
        f"👍 {likes} · 👎 {dislikes}\n"
        f"👤 آپلودر: <code>{uploader}</code>\n"
        f"📅 {uploaded_at or '?'}\n"
    )
    kb = [
        [_cb("🗑 حذف", f"pn_gb_del_{bid}")],
        [_cb("⚪ 🔙 بازگشت", f"pn_gb_list_{gender}_0")],
    ]
    return text, kb, b["file"]

async def _pm_build_gender_del_confirm(uid, bid):
    b = get_gender_banner_by_id(bid)
    if not b: return "❌ نیست.", [[_cb("⚪ 🔙 بازگشت", "pn_gb_panel")]]
    users_count = len(b.get("users", []))
    text = (
        f"🗑 حذف بنر\n━━━━━━━━━━━━━━━━━\n"
        f"🆔 <code>{bid}</code>\n"
        f"👥 {users_count} کاربر اینو انتخاب کردن\n"
        f"⚠️ مطمئنی؟"
    )
    kb = [
        [_cb("✅ بله، حذف کن", f"pn_gb_del_yes_{bid}")],
        [_cb("🔴 لغو", f"pn_gb_view_{bid}")],
    ]
    return text, kb

async def _pm_build_banner_main(uid):
    banners = get_user_banners(uid)
    active_count = sum(1 for _, b in banners.items() if b.get("active"))
    off_count = len(banners) - active_count
    text = (
        "📢 پنل تبچی\n━━━━━━━━━━━━━━━━━\n"
        f"📊 تعداد بنرها: {len(banners)}\n"
        f"🟢 فعال: {active_count}  ·  🔴 خاموش: {off_count}\n"
        "━━━━━━━━━━━━━━━━━"
    )
    kb = [
        [_cb("🟢 ➕ افزودن تبچی", "pn_banner_add")],
        [_cb("📋 لیست تبچی‌ها", "pn_banner_list_0")],
        [_cb("✏️ ویرایش", "pn_banner_edit_0")],
        [_cb("🔄 بروزرسانی", "pn_banner_main"), _cb("⚪ 🔙 بازگشت", "pn_refresh")],
    ]
    return text, kb

async def _pm_build_banner_list(uid, page=0):
    banners = get_user_banners(uid)
    items = list(banners.items())
    per_page = 5
    total = len(items)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    chunk = items[start:start + per_page]
    lines = [f"📋 تبچی‌ها — {total}  ·  {page+1}/{total_pages}"]
    kb = []
    for bname, b in chunk:
        icon = "🟢" if b.get("active") else "🔴"
        tg = len(b.get("targets", []))
        iv = _fmt_iv(b.get("interval", 60))
        kb.append([_cb(f"{icon} {bname} · {tg}🎯 · {iv}", f"pn_banner_view_{bname}")])
    nav = []
    if page > 0: nav.append(_cb("🔵 ⬅️", f"pn_banner_list_{page-1}"))
    if page < total_pages - 1: nav.append(_cb("🔵 ➡️", f"pn_banner_list_{page+1}"))
    if nav: kb.append(nav)
    kb.append([_cb("🟢 ➕", "pn_banner_add")])
    kb.append([_cb("⚪ 🔙 بازگشت", "pn_banner_main")])
    return "\n".join(lines), kb

async def _pm_build_banner_edit_list(uid, page=0):
    banners = get_user_banners(uid)
    items = list(banners.items())
    per_page = 5
    total = len(items)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    chunk = items[start:start + per_page]
    lines = ["✏️ ویرایش تبچی", "━━━━━━━━━━━━━━━━━",
             f"📊 مجموع: {total}  ·  📄 {page+1}/{total_pages}"]
    kb = []
    if not chunk: lines.append("📭 هنوز بنری نساختی")
    else:
        for bname, b in chunk:
            icon = "🟢" if b.get("active") else "🔴"
            kb.append([_cb(f"{icon} {bname}", f"pn_banner_editpick_{bname}")])
    nav = []
    if page > 0: nav.append(_cb("🔵 ⬅️", f"pn_banner_edit_{page-1}"))
    if page < total_pages - 1: nav.append(_cb("🔵 ➡️", f"pn_banner_edit_{page+1}"))
    if nav: kb.append(nav)
    kb.append([_cb("⚪ 🔙 بازگشت", "pn_banner_main")])
    return "\n".join(lines), kb

async def _pm_build_banner_edit_menu(uid, bname):
    banners = get_user_banners(uid)
    if bname not in banners:
        return "❌ بنر پیدا نشد.", [[_cb("⚪ 🔙 بازگشت", "pn_banner_edit_0")]]
    b = banners[bname]
    targets = b.get("targets", [])
    text = (
        f"✏️ ویرایش بنر: {bname}\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"• نوع: {_type_label(b.get('type', 'text'))}\n"
        f"• وضعیت: {'🟢 روشن' if b.get('active') else '🔴 خاموش'}\n"
        f"• بازه: {_fmt_iv(b.get('interval', 60))}\n"
        f"• هدف‌ها: {len(targets)}\n"
        f"• ارسال: {b.get('sent_count', 0)}\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"چی رو می‌خوای عوض کنی؟"
    )
    kb = [
        [_cb("🟡 ✏️ نام", f"pn_banner_edit_name_{bname}"),
         _cb("🟡 ⏱ بازه", f"pn_banner_edit_interval_{bname}")],
        [_cb("🟡 🎯 هدف‌ها", f"pn_banner_targets_{bname}"),
         _cb("🟡 📄 محتوا", f"pn_banner_edit_content_{bname}")],
        [_cb("⚪ 🔙 بازگشت", "pn_banner_edit_0")],
    ]
    return text, kb

async def _pm_build_interval_slider(uid, bname, mode="edit"):
    st = pm_banner_states.get(uid, {})
    data = st.get("data", {})
    unit = data.get("unit", "m")
    value = data.get("value", 1)
    unit_label = {"s": "ثانیه", "m": "دقیقه", "h": "ساعت", "d": "روز"}[unit]
    total_sec = value * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    action = "تغییر" if mode == "edit" else "انتخاب"
    text = (
        f"⏱ {action} بازه بنر «{bname}»\n"
        "━━━━━━━━━━━━━━━━━\n"
        "🔹 واحد رو با ◀ ▶ انتخاب کن\n"
        "🔹 مقدار رو با ±1 یا ±10 عوض کن\n"
        "━━━━━━━━━━━━━━━━━\n"
        f"📊 الان: {value} {unit_label}  ({format_interval_short(total_sec)})"
    )
    kb = [
        [_cb("🔵 ◀", "pn_bi_unit_prev"),
         _cb(f"🔵 ⏱ {unit_label}", "pn_bi_noop"),
         _cb("🔵 ▶", "pn_bi_unit_next")],
        [_cb("🔵 −10", "pn_bi_dec10"),
         _cb("🔵 −1", "pn_bi_dec1"),
         _cb(f"🔵 {value}", "pn_bi_noop"),
         _cb("🔵 +1", "pn_bi_inc1"),
         _cb("🔵 +10", "pn_bi_inc10")],
        [_cb("🟢 ✅ تأیید", "pn_bi_confirm")],
        [_cb("⚪ 🔙 بازگشت", f"pn_banner_view_{bname}")],
    ]
    return text, kb

async def _pm_build_banner_view(uid, bname):
    banners = get_user_banners(uid)
    if bname not in banners:
        return "❌ بنر پیدا نشد.", [[_cb("⚪ 🔙 بازگشت", "pn_banner_main")]]
    b = banners[bname]
    targets = b.get("targets", [])
    t_lines = []
    for cid in targets:
        tname = str(cid)
        cl = user_clients.get(int(uid))
        if cl:
            try:
                ent = await cl.get_entity(cid)
                tname = getattr(ent, "title", None) or tname
            except: pass
        t_lines.append(f"   • {tname}")
    t_str = "\n".join(t_lines) if t_lines else "   • (خالی)"
    reply_msg = b.get("reply_to_msg_id")
    reply_str = f"🔗 ریپلای: <code>{reply_msg}</code>" if reply_msg else "🔗 ریپلای: تنظیم نشده"
    text = (
        f"📢 بنر: {bname}\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"• نوع: {_type_label(b.get('type', 'text'))}\n"
        f"• وضعیت: {'🟢 روشن' if b.get('active') else '🔴 خاموش'}\n"
        f"• بازه: {_fmt_iv(b.get('interval', 60))}\n"
        f"• ارسال شده: {b.get('sent_count', 0)}\n"
        f"• {reply_str}\n"
        f"• هدف‌ها ({len(targets)}):\n{t_str}\n"
        f"━━━━━━━━━━━━━━━━━"
    )
    kb = [
        [_cb("🔴 خاموش" if b.get("active") else "🟢 روشن", f"pn_banner_toggle_{bname}"),
         _cb("🔵 📨 ارسال فوری", f"pn_banner_send_{bname}")],
        [_cb("🟡 🎯 هدف‌ها", f"pn_banner_targets_{bname}"),
         _cb("🟡 ⏱ تغییر بازه", f"pn_banner_edit_interval_{bname}")],
        [_cb("🔗 ریپلای", f"pn_banner_reply_set_{bname}"),
         _cb("🚫 لغو ریپلای", f"pn_banner_reply_clear_{bname}")],
        [_cb("🔴 🗑 حذف بنر", f"pn_banner_del_{bname}")],
        [_cb("⚪ 🔙 بازگشت", "pn_banner_main")],
    ]
    return text, kb

async def _pm_build_banner_targets(uid, bname, page=0):
    banners = get_user_banners(uid)
    if bname not in banners: return "❌ نیست.", [[_cb("⚪ 🔙 بازگشت", "pn_banner_main")]]
    current = set(banners[bname].get("targets", []))
    groups = await _pm_get_user_groups(uid, limit=200)
    per_page = 10
    total = len(groups)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    chunk = groups[start:start + per_page]
    lines = [
        f"🎯 هدف‌های «{bname}»", "━━━━━━━━━━━━━━━━━",
        f"✅ انتخاب‌شده: {len(current)}  ·  📄 {page+1}/{total_pages}",
    ]
    kb = []
    cur_chat = pm_panel_chat.get(int(uid))
    if cur_chat:
        cur_title = str(cur_chat)
        try:
            c = user_clients.get(int(uid))
            if c:
                ent = await c.get_entity(cur_chat)
                cur_title = getattr(ent, 'title', None) or cur_title
        except: pass
        mark = "✅" if int(cur_chat) in current else "⬜"
        kb.append([_cb(f"📍 {mark} محل فعلی: {cur_title[:28]}", f"pn_banner_atg_{bname}_{cur_chat}")])
        lines.append("━━━━━━━━━━━━━━━━━")
    if chunk:
        lines.append("👇 روی گروه بزن:")
        for g in chunk:
            if cur_chat and int(g["id"]) == int(cur_chat): continue
            mark = "✅" if g["id"] in current else "⬜"
            kb.append([_cb(f"{mark} {g['title'][:32]}", f"pn_banner_atg_{bname}_{g['id']}")])
    else:
        if not cur_chat: lines.append("❌ گروهی نیست")
    nav = []
    if page > 0: nav.append(_cb("⬅️ قبلی", f"pn_banner_tpg_{bname}_{page-1}"))
    if page < total_pages - 1: nav.append(_cb("بعدی ➡️", f"pn_banner_tpg_{bname}_{page+1}"))
    if nav: kb.append(nav)
    kb.append([_cb("🟢 ✅ ذخیره", "pn_banner_done")])
    kb.append([_cb("⚪ 🔙 بازگشت", f"pn_banner_view_{bname}")])
    return "\n".join(lines), kb

async def _pm_build_banner_del_confirm(uid, bname):
    text = f"🗑 حذف بنر «{bname}»\n\n⚠️ مطمئنی؟"
    kb = [[_cb("🟢 ✅ بله", f"pn_banner_del_yes_{bname}")],
          [_cb("🔴 لغو 🔙", f"pn_banner_view_{bname}")]]
    return text, kb

async def _pm_build_users_full(uid, page=0):
    all_users = list(users_db["users"].items())
    users = []
    hidden = 0
    for u, info in all_users:
        has_session = os.path.exists(str(SESSION_DIR / f"{u}.session"))
        has_phone = bool((info.get("phone") or "").strip())
        is_active = info.get("active", False)
        is_banned = info.get("banned", False)
        if not has_session or not has_phone or (not is_active and not is_banned):
            hidden += 1; continue
        users.append((u, info))
    per_page = 6
    total = len(users)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(0, min(page, total_pages - 1))
    start = page * per_page
    chunk = users[start:start + per_page]
    active = sum(1 for _, u in users if u.get("active") and not u.get("banned"))
    banned = sum(1 for _, u in users if u.get("banned"))
    lines = [f"\u200e👥 کاربران — {total}",
             f"\u200e🟢 {active} · 🚫 {banned} · 👻 {hidden}",
             f"\u200e📄 {page+1}/{total_pages}"]
    kb = []
    for u_uid, info in chunk:
        banned_u = info.get("banned", False)
        active_u = info.get("active", False)
        st = "🚫" if banned_u else ("🟢" if active_u else "🔴")
        g = info.get("gender")
        g_icon = "🩷" if g == "girl" else ("💙" if g == "boy" else "❓")
        name = (info.get("name") or u_uid)[:22]
        kb.append([_cb(f"{st} {g_icon} {name} · {u_uid}", f"pn_user_{u_uid}")])
    nav = []
    if page > 0: nav.append(_cb("🔵 ⬅️", f"pn_users_{page-1}"))
    if page < total_pages - 1: nav.append(_cb("🔵 ➡️", f"pn_users_{page+1}"))
    if nav: kb.append(nav)
    kb.append([_cb("🔵 🔄", f"pn_users_{page}"), _cb("⚪ 🔙 بازگشت", "pn_refresh")])
    return "\n".join(lines), kb

def _pm_wrap_access_proxy_result(owner_id, target, result, notice=None, current_raw=None):
    """پنل کاربر را با دکمه‌های «پروکسی» + کنترل قفل همان بخش برمی‌گرداند."""
    file_path = None
    if isinstance(result, tuple) and len(result) == 3:
        text, kb, file_path = result
    elif isinstance(result, tuple) and len(result) == 2:
        text, kb = result
    else:
        return result
    if notice:
        text = f"{notice}\n━━━━━━━━━━━━━━━━━\n{text}"
    target = int(target)
    target_locks = get_locked_sections(target)
    wrapped = []
    for row in kb or []:
        new_row = []
        for button in row:
            raw = getattr(button, "data", b"")
            if isinstance(raw, bytes): raw = raw.decode(errors="ignore")
            raw = str(raw or "")
            if not raw:
                new_row.append(button)
                continue
            if raw in ("pn_owner", "pn_close"):
                continue
            label = button.text
            if raw in target_locks:
                label = f"🔒 {label}"
            new_row.append(_cb(label, f"pn_access_as_{target}_{raw}"))
        if new_row: wrapped.append(new_row)
    current_raw = str(current_raw or "")
    if _is_lockable_panel(current_raw):
        is_locked = current_raw in target_locks
        sec_label = _panel_lock_label(current_raw, text)
        wrapped.append([_cb(
            f"🔓 بازکردن «{sec_label}»" if is_locked else f"🔒 قفل «{sec_label}»",
            f"pn_access_seclk_{target}_{current_raw}")])
        wrapped.append([_cb("🧩 قفل/بازکردن دکمه‌های همین صفحه",
                            f"pn_access_items_{target}_{current_raw}")])
    if current_raw in ("", "pn_refresh", "pn_owner"):
        locked_all = bool(users_db.get("users", {}).get(str(target), {}).get("all_access_locked", False))
        lock_count = len(target_locks)
        wrapped.append([_cb(
            f"📋 قفل‌های بخش‌ها ({lock_count})" if lock_count else "📋 قفل‌های بخش‌ها",
            f"pn_access_locks_{target}")])
        wrapped.append([_cb("🔓 بازکردن همهٔ دسترسی‌ها" if locked_all else "🔒 قفل همهٔ دسترسی‌ها",
                            f"pn_access_lock_{target}")])
    wrapped.append([_cb("↩️ خروج از دسترسی کاربر", f"pn_access_exit_{target}")])
    return (text, wrapped, file_path) if file_path else (text, wrapped)


async def _access_panel_items(event, target, panel_raw):
    """دکمه‌های یک صفحهٔ پنل کاربر را برای قفل‌کردن تک‌تک برمی‌گرداند."""
    panel_raw = str(panel_raw or "")
    try:
        result = await _dispatch_pn_core(event, int(target), panel_raw, actor_id=OWNER_ID)
    except Exception as e:
        log_error(f"_access_panel_items {target}/{panel_raw}: {_translate_bot_errors(e)}")
        return "", []
    text, kb = "", []
    if isinstance(result, tuple) and len(result) >= 2:
        text, kb = result[0], result[1]
    items, seen = [], set()
    for row in kb or []:
        for button in row:
            raw = getattr(button, "data", None)
            if isinstance(raw, bytes): raw = raw.decode(errors="ignore")
            raw = str(raw or "")
            if not raw or raw in _SECTION_LOCK_IGNORE or raw.startswith("pn_access_"):
                continue
            if raw in seen:
                continue
            seen.add(raw)
            label = re.sub(r"\s+", " ", str(getattr(button, "text", "") or raw)).strip()[:30] or raw
            items.append((raw, label))
    return text, items


async def _pm_build_access_item_menu(event, owner_id, target, panel_raw, notice=None):
    if not is_grp_owner(owner_id):
        return ("🔒 فقط مالک", [[_cb("⚪ 🔙", "pn_owner")]])
    target = int(target)
    panel_raw = str(panel_raw or "")
    panel_text, items = await _access_panel_items(event, target, panel_raw)
    locks = get_locked_sections(target)
    lines = ["🧩 قفل دکمه‌های این صفحه", "━━━━━━━━━━━━━━━━━",
             f"🗂 بخش: {_panel_lock_label(panel_raw, panel_text)}"]
    if notice:
        lines.extend(["", notice])
    lines.append("")
    if not items:
        lines.append("📭 دکمه‌ای برای قفل کردن در این صفحه نیست.")
    else:
        lines.append("👇 روی هر دکمه بزن تا 🔒/🟢 عوض شود.")
        lines.append("دکمه‌های 🔒 برای کاربر مخفی می‌شوند و کار نمی‌کنند.")
    kb = []
    if locks:
        kb.append([_cb(f"📋 قفل‌های فعال ({len(locks)})", f"pn_access_locks_{target}")])
    for idx, (raw, label) in enumerate(items):
        icon = "🔒" if raw in locks else "🟢"
        kb.append([_cb(f"{icon} {label}", f"pn_access_item_{target}_{idx}_{panel_raw}")])
    kb.append([_cb("⚪ 🔙 بازگشت به همان صفحه", f"pn_access_as_{target}_{panel_raw}")])
    return "\n".join(lines), kb


async def _pm_build_access_locks(owner_id, target, notice=None):
    if not is_grp_owner(owner_id):
        return ("🔒 فقط مالک", [[_cb("⚪ 🔙", "pn_owner")]])
    target = int(target)
    locks = get_locked_sections(target)
    lines = ["📋 قفل‌های بخش‌ها", "━━━━━━━━━━━━━━━━━"]
    if notice:
        lines.extend(["", notice])
    if not locks:
        lines.append("📭 هیچ بخشی برای این کاربر قفل نیست.")
    else:
        lines.append(f"🔒 {len(locks)} مورد قفل است و در پنل کاربر دیده نمی‌شود:")
        lines.append("")
    kb = []
    for key, label in sorted(locks.items(), key=lambda kv: kv[1]):
        kb.append([_cb(f"🔓 بازکردن: {label[:26]}", f"pn_access_unlk_{target}_{key}")])
    if len(locks) > 1:
        kb.append([_cb("🔓 بازکردن همهٔ قفل‌های بخش‌ها", f"pn_access_unlockall_{target}")])
    kb.append([_cb("⚪ 🔙 بازگشت به پنل کاربر", f"pn_access_as_{target}_pn_refresh")])
    return "\n".join(lines), kb


async def _pm_build_access_editor(owner_id, target, notice=None):
    if not is_grp_owner(owner_id):
        return ("🔒 فقط مالک", [[_cb("⚪ 🔙", "pn_owner")]])
    info = users_db.get("users", {}).get(str(target), {})
    if not info:
        return await _pm_build_user(owner_id, target)
    text, kb = await _pm_build_main(int(target))
    return _pm_wrap_access_proxy_result(owner_id, int(target), (text, kb), notice,
                                        current_raw="pn_refresh")


async def _pm_build_user(uid, target):
    info = users_db["users"].get(str(target), {})
    if not info: return "❌ نیست.", [[_cb("⚪ 🔙 بازگشت", "pn_users_0")]]
    banned = info.get("banned", False)
    active = info.get("active", False)
    disabled = info.get("locally_disabled", False)
    st = "🚫 بن" if banned else "🔇 خاموش" if disabled else "🟢 فعال" if active else "🔴 غیرفعال"
    is_mgr = int(target) in get_managers()
    g = info.get("gender")
    g_label = "🩷" if g == "girl" else ("💙" if g == "boy" else "❓")
    media_allowed = is_media_allowed(target)
    media_lbl = "🟢 داره" if media_allowed else "🔴 نداره"
    all_access_locked = bool(info.get("all_access_locked", False))
    lines = [
        "👤 کاربر", f"📛 {info.get('name', '—')}",
        f"🆔 {target}", f"📱 {info.get('phone', '—')}",
        f"⚧ {g_label}", f"📊 {st}",
        f"👮 {'✅' if is_mgr else '❌'}",
        f"🔐 TTL/ذخیره: {media_lbl}",
        f"🛡 قفل همهٔ دسترسی‌ها: {'🔒 فعال' if all_access_locked else '🔓 غیرفعال'}",
        f"🔐 بخش‌های قفل‌شده: {len(get_locked_sections(target))}",
    ]
    kb = [[_cb("🛠 ویرایش دسترسی", f"pn_access_edit_{target}")]]
    _locks_n = len(get_locked_sections(target))
    kb.append([_cb(f"🛡 قفل بخش‌ها ({_locks_n})" if _locks_n else "🛡 قفل بخش‌ها",
                   f"pn_access_locks_{target}")])
    if banned: kb.append([_cb("🟢 ✅ رفع بن", f"pn_unban_{target}")])
    else: kb.append([_cb("🔴 🚫 بن", f"pn_ban_{target}")])
    if is_mgr: kb.append([_cb("🔴 🗑 حذف مدیر", f"pn_rmmgr_{target}")])
    else: kb.append([_cb("🟡 👮 مدیر", f"pn_addmgr_{target}")])
    # ─── دکمه دسترسی TTL/ذخیره ───
    allowed = is_media_allowed(target)
    media_icon = "🟢" if allowed else "🔴"
    media_txt = "داره" if allowed else "نداره"
    kb.append([_cb(f"{media_icon} TTL/ذخیره: {media_txt}",
                   f"pn_media_t_{target}")])
    kb.append([_cb("🔴 🗑 سشن", f"pn_rmsess_{target}"),
               _cb("🔵 ♻️", f"pn_reload_{target}")])
    kb.append([_cb("⚪ 🔙 بازگشت", "pn_users_0")])
    return "\n".join(lines), kb

def _pm_banner_cancel_kb():
    return [[_cb("🔴 لغو 🔙", "pn_banner_cancel")]]

# ═══════════════════════════════════════════════════════
# _pm_banner_state_input
# ═══════════════════════════════════════════════════════
def _banner_prompt_key(text):
    text = re.sub(r"<[^>]*>", "", text or "")
    return re.sub(r"\s+", " ", _normalize_persian(text)).strip()


def _arm_banner_add_timeout(user_id, state, prompt_text=None, prompt_msg_id=None):
    old = pm_banner_add_timeout_tasks.pop(user_id, None)
    if old and not old.done(): old.cancel()
    if prompt_msg_id is not None: state["prompt_msg_id"] = prompt_msg_id
    if prompt_text is not None: state["prompt_text"] = prompt_text
    token = f"{time.monotonic_ns()}-{random.getrandbits(32)}"
    state["timeout_token"] = token
    state["expires_at"] = time.time() + 300
    pm_banner_states[user_id] = state
    async def expire():
        try:
            await asyncio.sleep(300)
            current = pm_banner_states.get(user_id)
            if not current or current.get("timeout_token") != token:
                return
            if current.get("mode") not in ("add_name", "add_wait_media", "add_forward_wait"):
                return
            pm_banner_states.pop(user_id, None)
            prompt_id = current.get("prompt_msg_id")
            chat_id = current.get("prompt_chat_id")
            timeout_text = "⏱ عملیات افزودن تبچی به‌دلیل عدم پاسخ در ۵ دقیقه لغو شد."
            if prompt_id is not None and _is_inline_id(prompt_id):
                await _try_inline_edit_global(prompt_id, timeout_text, [])
            elif prompt_id is not None and chat_id is not None:
                client = user_clients.get(int(user_id))
                if client and client.is_connected():
                    try: await client.edit_message(chat_id, prompt_id, timeout_text, buttons=None)
                    except Exception as e: log_error(f"banner add timeout edit {user_id}: {_translate_bot_errors(e)}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            log_error(f"banner add timeout {user_id}: {_translate_bot_errors(e)}")
    pm_banner_add_timeout_tasks[user_id] = asyncio.create_task(expire())


def _clear_banner_add_state(user_id):
    task = pm_banner_add_timeout_tasks.pop(user_id, None)
    if task and not task.done(): task.cancel()
    pm_banner_states.pop(user_id, None)


async def _pm_banner_state_input(event, user_id):
    st = pm_banner_states.get(user_id)
    if not st: return False
    mode = st.get("mode")
    _prompt_chat = st.get("prompt_chat_id")
    if _prompt_chat is not None:
        try:
            if int(event.chat_id) != int(_prompt_chat):
                return False
        except Exception:
            return False
    if mode in ("add_name", "add_wait_media", "add_forward_wait"):
        if time.time() >= st.get("expires_at", time.time() + 300):
            _clear_banner_add_state(user_id)
            return True
        try:
            replied = await event.get_reply_message()
        except Exception:
            replied = None
        if not replied:
            return True
        expected_id = st.get("prompt_msg_id")
        is_same_prompt = False
        if isinstance(expected_id, int):
            is_same_prompt = (getattr(event, "reply_to_msg_id", None) == expected_id)
        elif expected_id is not None:
            # Inline message IDs are opaque; verify the exact helper-bot prompt text.
            is_same_prompt = (
                (bool(getattr(replied, "via_bot_id", None)) or bool(getattr(replied, "out", False)))
                and _banner_prompt_key(replied.raw_text or "") ==
                    _banner_prompt_key(st.get("prompt_text", ""))
            )
        if not is_same_prompt:
            return True
    text = (event.raw_text or "").strip()
    try:
        if mode == "tts_text_input":
            if text.startswith(CMD):
                pm_banner_states.pop(user_id, None)
                return False
            if not text:
                await event.reply("❌ متن خالی است؛ متن را بفرست یا لغو کن.")
                return True
            gender = users_db["users"].get(str(user_id), {}).get("voice_gender", "female")
            pm_banner_states.pop(user_id, None)
            await _send_tts_voice(event, text, gender)
            return True
        if mode == "tts_voice_wait":
            if text.startswith(CMD):
                pm_banner_states.pop(user_id, None)
                return False
            message = getattr(event, "message", None)
            if message and (getattr(message, "voice", None) or getattr(message, "audio", None)):
                pm_banner_states.pop(user_id, None)
                await _transcribe_voice_message(event, message)
                return True
            await event.reply("🎧 حالا یک ویس یا فایل صوتی بفرست؛ یا با دکمهٔ لغو برگرد.")
            return True
        if mode == "mon_add":
            if text in (f"{CMD}لغو", f"{CMD}کنسل"):
                pm_banner_states.pop(user_id, None)
                await event.reply("✅ افزودن به پایش لغو شد.")
                return True
            monitor_arg = text
            if text.startswith(f"{CMD}پایش افزودن"):
                monitor_arg = text.replace(f"{CMD}پایش افزودن", "", 1).strip()
            ok, result = await _monitor_add_target(user_id, event, monitor_arg)
            pm_banner_states.pop(user_id, None)
            await event.reply(result)
            return True
        if mode == "name_emoji_add":
            if text.startswith(CMD):
                pm_banner_states.pop(user_id, None)
                return False
            emoji = "".join((event.raw_text or "").split())
            has_emoji_char = any(
                ord(ch) >= 0x1F000 or 0x2600 <= ord(ch) <= 0x27BF
                for ch in emoji)
            allowed_emoji_chars = all(
                ord(ch) >= 0x1F000 or 0x2600 <= ord(ch) <= 0x27BF
                or ch in "\u200d\ufe0e\ufe0f\u20e3"
                for ch in emoji)
            if not emoji or len(emoji) > 16 or not has_emoji_char or not allowed_emoji_chars:
                await event.reply("❌ فقط یک ایموجی بفرست.")
                return True
            cfg = get_name_emoji_config(user_id)
            if emoji not in cfg["custom_emojis"]:
                cfg["custom_emojis"].append(emoji)
            if emoji not in cfg["emojis"]:
                cfg["emojis"].append(emoji)
            pm_banner_states.pop(user_id, None)
            save_json(USERS_FILE, users_db)
            await event.reply(f"✅ ایموجی {emoji} اضافه و انتخاب شد. پنل ایموجی اسم را دوباره باز کن.")
            return True
        if mode == "add_name":
            if not text or len(text) > 40:
                await event.reply("❌ اسم ۱ تا ۴۰ حرف."); return True
            if text in get_user_banners(user_id):
                await event.reply(f"❌ بنر «{text}» وجود داره."); return True
            next_state = {"mode": "add_wait_media", "name": text,
                          "prompt_chat_id": st.get("prompt_chat_id") or event.chat_id}
            next_prompt = (
                f"✅ اسم: <b>{text}</b>\n\nحالا پیام/رسانه رو بفرست.\n"
                f"<i>(متن، عکس، ویدیو، ویس، استیکر...)</i>\n\n"
                f"🔴 لغو: <code>{CMD}لغو</code>")
            sent = await event.reply(next_prompt, parse_mode="html")
            _arm_banner_add_timeout(user_id, next_state, next_prompt,
                                    getattr(sent, "id", None))
            return True
        if mode == "add_wait_media":
            name = st["name"]; banners = get_user_banners(user_id)
            if name in banners:
                _clear_banner_add_state(user_id)
                await event.reply("❌ این اسم ثبت شد."); return True
            btype, ext = _detect_banner_type(event.message)
            media_file = None
            if btype != "text":
                try:
                    media_file = await event.download_media(
                        file=str(BANNER_MEDIA_DIR / f"{user_id}_{int(time.time())}{ext}"))
                except Exception as e:
                    await event.reply(f"❌ دانلود نشد: {_translate_bot_errors(e)}"); return True
            banners[name] = {"type": btype, "text": event.raw_text or "",
                "media_file": media_file, "mode": "copy", "targets": [],
                "interval": 60, "active": False, "sent_count": 0,
                "created_at": datetime.now().isoformat(),
                "reply_to_msg_id": None, "source_chat_id": None, "source_msg_id": None}
            save_json(BANNERS_FILE, banners_db)
            _clear_banner_add_state(user_id)
            await event.reply(
                f"✅ بنر «{name}» ساخته شد.\n📎 {_type_label(btype)}\n\n"
                f"از پنل: 🎯 هدف، ⏱ بازه، 🟢 روشن.", parse_mode="html")
            return True
        if mode == "add_forward_wait":
            name = st["name"]; banners = get_user_banners(user_id)
            if name in banners:
                _clear_banner_add_state(user_id)
                await event.reply("❌ ثبت شد."); return True
            reply = await event.get_reply_message()
            if not reply:
                await event.reply("❌ روی پیام مورد نظر ریپلای کن."); return True
            btype, _ = _detect_banner_type(reply)
            banners[name] = {"type": btype, "text": reply.raw_text or "",
                "media_file": None, "mode": "forward",
                "source_chat_id": event.chat_id, "source_msg_id": reply.id,
                "targets": [], "interval": 60, "active": False, "sent_count": 0,
                "created_at": datetime.now().isoformat(), "reply_to_msg_id": None}
            save_json(BANNERS_FILE, banners_db)
            _clear_banner_add_state(user_id)
            await event.reply(f"✅ بنر فوروارد «{name}» ساخته شد.\n📎 {_type_label(btype)}")
            return True
        if mode == "edit_name":
            new_name = text; old_name = st["old_name"]
            if not new_name or len(new_name) > 40:
                await event.reply("❌ اسم ۱ تا ۴۰ حرف."); return True
            banners = get_user_banners(user_id)
            if old_name not in banners:
                pm_banner_states.pop(user_id, None)
                await event.reply("❌ بنر نیست."); return True
            if new_name in banners and new_name != old_name:
                await event.reply("❌ این اسم وجود داره."); return True
            banners[new_name] = banners.pop(old_name)
            save_json(BANNERS_FILE, banners_db)
            pm_banner_states.pop(user_id, None)
            await event.reply(f"✅ نام: {old_name} → {new_name}")
            return True
        if mode == "edit_content":
            old_name = st["banner_name"]; banners = get_user_banners(user_id)
            if old_name not in banners:
                pm_banner_states.pop(user_id, None)
                await event.reply("❌ بنر نیست."); return True
            btype, ext = _detect_banner_type(event.message)
            old_file = banners[old_name].get("media_file")
            if old_file:
                try: os.remove(old_file)
                except: pass
            media_file = None
            if btype != "text":
                try:
                    media_file = await event.download_media(
                        file=str(BANNER_MEDIA_DIR / f"{user_id}_{int(time.time())}{ext}"))
                except Exception as e:
                    await event.reply(f"❌ دانلود نشد: {_translate_bot_errors(e)}"); return True
            banners[old_name].update({"type": btype, "text": event.raw_text or "",
                "media_file": media_file, "mode": "copy"})
            save_json(BANNERS_FILE, banners_db)
            pm_banner_states.pop(user_id, None)
            await event.reply(f"✅ محتوای «{old_name}» بروز شد.")
            return True
        if mode == "gb_upload":
            gender = st["gender"]
            if not event.photo:
                await event.reply("❌ یه عکس بفرست."); return True
            try:
                orig = await event.download_media(
                    file=str(GENDER_DIR / f"orig_{user_id}_{int(time.time())}.jpg"))
            except Exception as e:
                await event.reply(f"❌ دانلود نشد: {_translate_bot_errors(e)}"); return True
            final = str(GENDER_DIR / f"banner_{user_id}_{int(time.time())}.jpg")
            if _resize_banner_image(orig, final):
                try: os.remove(orig)
                except: pass
            else:
                final = orig
            add_gender_banner(gender, final, user_id)
            pm_banner_states.pop(user_id, None)
            await event.reply(f"✅ بنر {'🩷 دختر' if gender=='girl' else '💙 پسر'} اضافه شد.")
            return True
        if mode == "ghunt_join_code":
            code = text.strip()
            if code not in pew_hunt_groups:
                await event.reply("❌ کد نامعتبر است.")
                return True
            grp = pew_hunt_groups[code]
            if user_id in grp["members"]:
                await event.reply("❌ شما از قبل در این گروه هستید.")
                pm_banner_states.pop(user_id, None)
                return True
            grp["members"].append(user_id)
            pew_user_group[user_id] = code
            schedule_save_runtime()
            msg_id = st.get("msg_id")
            pm_banner_states.pop(user_id, None)
            
            success_text = f"✅ به گروه <code>{code}</code> ملحق شدید.\n👇 برای دیدن پنل و وضعیت (روشن/خاموش) روی دکمه زیر بزنید:"
            kb = [[_cb("👁 دیدن گروه", "pn_ghunt_panel")]]
            
            if msg_id:
                # ادیت کردن همون پیام پنل
                await _try_inline_edit_global(msg_id, success_text,
                                              _bind_panel_callbacks(kb, user_id))
            else:
                # اگر به هر دلیلی msg_id نبود
                await event.reply(success_text,
                                  buttons=_bind_panel_callbacks(kb, user_id),
                                  parse_mode="html")
            return True
        if mode == "nosell_add":
            if not text:
                await event.reply("❌ اسم آیتم بفرست."); return True
            if has_bad_separator(text):
                await event.reply("❌ بین نماد و اسم فاصله باشه."); return True
            items = parse_no_sell_args(text)
            added, skipped = add_no_sell_items(user_id, items)
            pm_banner_states.pop(user_id, None)
            lines = []
            if added:
                lines.append(f"✅ اضافه شد ({len(added)}):")
                for a in added: lines.append(f"   • {a}")
            if skipped:
                lines.append(f"⚠️ تکراری: {', '.join(skipped)}")
            await event.reply("\n".join(lines) or "ℹ️ چیزی اضافه نشد.")
            return True
        if mode == "pew_tgt_add_input":
            client = user_clients.get(int(user_id))
            if not client or not client.is_connected():
                client = await ensure_user_client(user_id)
            if not client:
                await event.reply("❌ اتصال نیست."); return True
            info = None
            try:
                replied = await event.get_reply_message()
                if replied and replied.sender_id and int(replied.sender_id) != user_id:
                    ent = await client.get_entity(int(replied.sender_id))
                    first = getattr(ent, 'first_name', '') or ''
                    last = getattr(ent, 'last_name', '') or ''
                    uname = getattr(ent, 'username', '') or ''
                    full = (first + " " + last).strip()
                    info = {"id": int(ent.id), "first_name": first, "last_name": last,
                            "username": uname,
                            "display": full or (("@" + uname) if uname else str(ent.id))}
            except Exception as e:
                log_error(f"pew_tgt_add reply: {_translate_bot_errors(e)}")
            if not info and text:
                raw = text.strip()
                try:
                    if raw.startswith("@"):
                        u = raw[1:].strip()
                        res = await client(ResolveUsernameRequest(u))
                        if res and res.users:
                            ent = res.users[0]
                            if not getattr(ent, 'bot', False):
                                first = getattr(ent, 'first_name', '') or ''
                                last = getattr(ent, 'last_name', '') or ''
                                uname = getattr(ent, 'username', '') or ''
                                full = (first + " " + last).strip()
                                info = {"id": int(ent.id), "first_name": first,
                                        "last_name": last, "username": uname,
                                        "display": full or ("@" + uname)}
                    elif normalize_digits(raw).lstrip("-").isdigit():
                        tid = int(normalize_digits(raw))
                        ent = await client.get_entity(tid)
                        if not getattr(ent, 'bot', False):
                            first = getattr(ent, 'first_name', '') or ''
                            last = getattr(ent, 'last_name', '') or ''
                            uname = getattr(ent, 'username', '') or ''
                            full = (first + " " + last).strip()
                            info = {"id": int(ent.id), "first_name": first,
                                    "last_name": last, "username": uname,
                                    "display": full or str(ent.id)}
                except Exception as e:
                    log_error(f"pew_tgt_add resolve: {_translate_bot_errors(e)}")
            if not info:
                await event.reply("❌ روی پیام طرف ریپلای کن یا @یوزرنیم/آیدی بفرست."); return True
            pm_banner_states[user_id] = {"mode": "pew_tgt_confirm", "info": info, "prompt_chat_id": st.get("prompt_chat_id") or event.chat_id}
            await event.reply(
                f"🎯 هدف: <b>{info['display']}</b>\n"
                f"🔗 یوزرنیم: {'@'+info['username'] if info['username'] else '—'}\n"
                f"🆔 <code>{info['id']}</code>\n\n"
                f"تایید می‌کنی؟ (<b>بله</b> / <b>خیر</b>)", parse_mode="html")
            return True
        if mode == "pew_tgt_confirm":
            if text.strip() in ("بله", "بلی", "اره", "آره", "yes", "✅"):
                info = st["info"]
                groups = await _pm_get_user_groups(user_id, 50)
                if not groups:
                    pm_banner_states.pop(user_id, None)
                    await event.reply("❌ گروهی نیست. اول تو یه گروه عضو شو."); return True
                lines = ["🎯 انتخاب گروه:", "━━━━━━━━━━━━━━━━━"]
                for i, g in enumerate(groups[:40], 1):
                    lines.append(f"{i}. {g['title'][:40]}")
                lines.append("")
                lines.append("💡 شماره گروه رو بفرست یا آیدی عددی.")
                pm_banner_states[user_id] = {"mode": "pew_tgt_pick_group",
                    "info": info, "groups": groups, "prompt_chat_id": st.get("prompt_chat_id") or event.chat_id}
                await event.reply("\n".join(lines))
            else:
                pm_banner_states.pop(user_id, None)
                await event.reply("❌ لغو شد.")
            return True
        if mode == "pew_tgt_pick_group":
            info = st["info"]; groups = st.get("groups", [])
            cid = None
            norm = normalize_digits(text.strip())
            if norm.isdigit() and len(norm) <= 3:
                idx = int(norm) - 1
                if 0 <= idx < len(groups):
                    cid = int(groups[idx]["id"])
            elif norm.lstrip("-").isdigit():
                cid = int(norm)
            if cid is None:
                await event.reply("❌ شماره یا آیدی معتبر بفرست."); return True
            tid = info["id"]
            key = _pew_target_key(user_id, cid, tid)
            if key in pew_target_config:
                pm_banner_states.pop(user_id, None)
                await event.reply("❌ قبلاً اضافه شده."); return True
            pew_target_config[key] = {"enabled": True,
                "name": info.get("display") or str(tid),
                "username": info.get("username", "")}
            pew_target_state[key] = {"phase": "shooting", "last_target_msg_id": 0}
            start_pew_target_task(user_id, cid, tid)
            schedule_save_runtime()
            pm_banner_states.pop(user_id, None)
            title = next((g["title"] for g in groups if int(g["id"]) == cid), str(cid))
            await event.reply(f"✅ هدف «{info['display']}» تو «{title}» اضافه و روشن شد.")
            return True
        if mode == "tgt_manual_input":
            mode_sub = st.get("mode_sub"); target_id = st["target_id"]
            old_cid = st.get("old_cid"); info = st.get("info", {})
            client = user_clients.get(int(user_id))
            if not client or not client.is_connected():
                client = await ensure_user_client(user_id)
            if not client:
                await event.reply("❌ اتصال نیست."); return True
            raw = text.strip(); ent = None
            try:
                if "t.me/" in raw:
                    m = re.search(r't\.me/(?:c/)?([^/?\s]+)', raw)
                    key = m.group(1) if m else ""
                    if key.isdigit():
                        ent = await client.get_entity(int("-100" + key))
                    elif key.startswith("+"):
                        await event.reply("❌ لینک خصوصی پشتیبانی نمی‌شه."); return True
                    else:
                        ent = await client.get_entity("@" + key)
                elif raw.startswith("@") or raw.lstrip("-").isdigit():
                    norm = normalize_digits(raw).strip()
                    if norm.lstrip("-").isdigit():
                        cid = int(norm)
                        if not str(cid).startswith("-100"):
                            cid = int("-100" + norm.lstrip("-"))
                        ent = await client.get_entity(cid)
                    else:
                        ent = await client.get_entity(raw)
            except Exception as e:
                await event.reply(f"❌ پیدا نشد: {_translate_bot_errors(e)}"); return True
            if not ent or not getattr(ent, 'megagroup', False):
                await event.reply("❌ باید گروه باشه."); return True
            cid = int(ent.id); title = (getattr(ent, 'title', 'f') or str(cid))[:40]
            if mode_sub == "add":
                key = _pew_target_key(user_id, cid, target_id)
                if key in pew_target_config:
                    pm_banner_states.pop(user_id, None)
                    await event.reply(f"❌ قبلاً تو «{title}» اضافه شده."); return True
                pew_target_config[key] = {"enabled": True,
                    "name": info.get("display") or str(target_id),
                    "username": info.get("username", "")}
                pew_target_state[key] = {"phase": "shooting", "last_target_msg_id": 0}
                start_pew_target_task(user_id, cid, target_id)
                schedule_save_runtime()
                await event.reply(f"✅ هدف تو «{title}» اضافه و روشن شد.")
            else:
                old_key = _pew_target_key(user_id, old_cid, target_id)
                old_cfg = pew_target_config.pop(old_key, None)
                old_state = pew_target_state.pop(old_key, None)
                stop_pew_target_task(user_id, old_cid, target_id)
                if old_cfg:
                    new_key = _pew_target_key(user_id, cid, target_id)
                    pew_target_config[new_key] = old_cfg
                    if old_state: pew_target_state[new_key] = old_state
                    if old_cfg.get("enabled"):
                        start_pew_target_task(user_id, cid, target_id)
                    schedule_save_runtime()
                    await event.reply(f"✅ هدف منتقل شد به «{title}».")
                else:
                    await event.reply("❌ هدف قدیمی نبود.")
            pm_banner_states.pop(user_id, None)
            return True
    except Exception as e:
        log_error(f"_pm_banner_state_input {user_id}/{mode}: {_translate_bot_errors(e)}")
        pm_banner_states.pop(user_id, None)
        try: await event.reply(f"❌ خطا: {_translate_bot_errors(e)}")
        except: pass
        return True
    return False

# ═══════════════════════════════════════════════════════
# _dispatch_pn
# ═══════════════════════════════════════════════════════
async def _fishing_loop(user_id):
    while fishing_status.get(user_id, False):
        # ۱. ارسال خروج از شهر
        try:
            await _send_game_cmd(user_id, "🏰 خروج از شهر!", tag="fishing_exit")
            log_error(f"🏰 Exit city sent for fishing {user_id}")
        except Exception as e:
            log_error(f"Fishing exit error {user_id}: {e}")

        # ۲. صبر ۱۰ ثانیه
        await asyncio.sleep(10)
        if not fishing_status.get(user_id, False): break

        # ۳. ارسال ماهیگیری
        try:
            await _send_game_cmd(user_id, "🎣 ماهی‌گیری", tag="fishing")
            log_error(f"🎣 Fishing sent for {user_id}")
        except Exception as e:
            log_error(f"Fishing error {user_id}: {e}")

        # ۴. صبر ۱۰ دقیقه (۶۰۰ ثانیه) برای چرخه بعدی
        await asyncio.sleep(600)







# ═══════════════════════════════════════════════════════
# 💎 PERFECT MATERIAL TRANSFER SYSTEM (BY USER LOGIC)
# ═══════════════════════════════════════════════════════


def _ensure_transfer_scheduler(user_id, kind):
    """Start at most one hourly scheduler for each user and transfer category."""
    uid = int(user_id)
    if kind not in ("item", "material"):
        return
    key = (uid, kind)
    task = transfer_scheduler_tasks.get(key)
    if task and not task.done():
        return
    runner = item_scheduler if kind == "item" else material_scheduler
    transfer_scheduler_tasks[key] = asyncio.create_task(runner(uid))


def _ensure_enabled_transfer_schedulers(user_id):
    uid = int(user_id)
    if transfer_items_config.get(uid, {}).get("enabled"):
        _ensure_transfer_scheduler(uid, "item")
    if transfer_materials_config.get(uid, {}).get("enabled"):
        _ensure_transfer_scheduler(uid, "material")


async def item_scheduler(user_id):
    key = (int(user_id), "item")
    this_task = asyncio.current_task()
    try:
        while True:
            await asyncio.sleep(SELL_CHECK_INTERVAL) # هر 1 ساعت
            cfg = transfer_items_config.get(user_id, {})
            if not cfg.get("enabled"): break
            if sell_mode_users.get(user_id, {}).get("enabled"):
                continue # فروش، انتقال را در چرخهٔ خودش انجام می‌دهد
            async with get_user_lock(user_id):
                await execute_item_transfers(user_id)
    except asyncio.CancelledError: pass
    except Exception as e: log_error(f"item_scheduler {user_id}: {_translate_bot_errors(e)}")
    finally:
        if transfer_scheduler_tasks.get(key) is this_task:
            transfer_scheduler_tasks.pop(key, None)




async def material_scheduler(user_id):
    key = (int(user_id), "material")
    this_task = asyncio.current_task()
    try:
        while True:
            await asyncio.sleep(SELL_CHECK_INTERVAL)
            cfg = transfer_materials_config.get(user_id, {})
            if not cfg.get("enabled"): break
            if sell_mode_users.get(user_id, {}).get("enabled"):
                continue
            async with get_user_lock(user_id):
                await execute_material_transfers(user_id)
    except asyncio.CancelledError: pass
    except Exception as e: log_error(f"material_scheduler {user_id}: {_translate_bot_errors(e)}")
    finally:
        if transfer_scheduler_tasks.get(key) is this_task:
            transfer_scheduler_tasks.pop(key, None)



async def _pm_mat_state_input(event, user_id):
    st = pm_banner_states.get(user_id)
    if not st: return False
    mode = st.get("mode")
    if not mode: return False

    # 🔥 شرط ریپلای: فقط وقتی که روی پیام هلپر بات ریپلای شده باشه
    if not getattr(event, 'reply_to_msg_id', None):
        return False

    try:
        replied = await event.get_reply_message()
        if not replied: return False
        
        # چون پیام هلپر بات با اکانت خود کاربر (اینلاین) فرستاده میشه، باید via_bot_id رو چک کنیم
        is_helper_msg = False
        if getattr(replied, 'via_bot_id', None): 
            is_helper_msg = True
        elif getattr(replied, 'out', False) and "از طریق ShabahHelper_bot" in (replied.raw_text or ""):
            is_helper_msg = True
            
        if not is_helper_msg:
            return False
            
    except Exception as e:
        log_error(f"reply check err: {e}")
        return False

    text = normalize_digits((event.raw_text or "").strip())
    
    if text.startswith(",") or text.startswith("،"):
        pm_banner_states.pop(user_id, None)
        return False

    async def edit_panel(new_text, new_kb, parse_mode=None):
        new_kb = _bind_panel_callbacks(new_kb, user_id)
        success = False
        try:
            await event.client.edit_message(event.chat_id, event.reply_to_msg_id, new_text, buttons=new_kb, parse_mode=parse_mode)
            success = True
        except Exception as e:
            log_error(f"edit state panel fail: {e}")
            
        if not success:
            try:
                await event.reply(new_text, buttons=new_kb, parse_mode=parse_mode)
            except Exception as e2:
                log_error(f"reply state panel fail: {e2}")

    try:
        if mode.startswith("mat_"):
            if mode == "mat_add_cid":
                if not text.isdigit() or not (1 <= len(text) <= 5):
                    await edit_panel("❌ آیدی باید بین ۱ تا ۵ رقم باشد. مجدد بفرستید:", [[_cb("🔴 لغو", "pn_transfer_materials")]])
                    return True
                st["cid"] = text; st["mode"] = "mat_add_name"; pm_banner_states[user_id] = st
                await edit_panel("✅ آیدی ثبت شد.\nحالا <b>نام ماده</b> را بفرستید:", [[_cb("🔴 لغو", "pn_transfer_materials")]], parse_mode="html")
                return True
            elif mode == "mat_add_name":
                if not text: return True
                st["name"] = text; st["mode"] = "mat_add_qty"; pm_banner_states[user_id] = st
                await edit_panel("✅ نام ثبت شد.\nحالا <b>تعداد</b> را بفرستید.\n(0 برای همه):", [[_cb("🔴 لغو", "pn_transfer_materials")]], parse_mode="html")
                return True
            elif mode == "mat_add_qty":
                if not text.isdigit():
                    await edit_panel("❌ فقط عدد بفرستید (0 برای همه):", [[_cb("🔴 لغو", "pn_transfer_materials")]])
                    return True
                cfg = transfer_materials_config.setdefault(user_id, {"enabled": False, "rules": []})
                cfg["rules"].append({"cid": st.get("cid"), "material": st.get("name"), "quantity": int(text), "enabled": True})
                schedule_save_runtime(); pm_banner_states.pop(user_id, None)
                await edit_panel(f"✅ قانون مواد ثبت شد.\n📦 {st.get('name')}", [[_cb("🔙 بازگشت", "pn_transfer_materials")]])
                return True
            elif mode == "mat_edit_cid":
                if not text.isdigit() or not (1 <= len(text) <= 5): return True
                cfg = transfer_materials_config.get(user_id, {}); idx = st.get("rule_idx")
                if 0 <= idx < len(cfg.get("rules", [])): cfg["rules"][idx]["cid"] = text; schedule_save_runtime()
                pm_banner_states.pop(user_id, None); await edit_panel("✅ ویرایش شد.", [[_cb("🔙 بازگشت", "pn_mat_list")]]); return True
            elif mode == "mat_edit_name":
                if not text: return True
                cfg = transfer_materials_config.get(user_id, {}); idx = st.get("rule_idx")
                if 0 <= idx < len(cfg.get("rules", [])): cfg["rules"][idx]["material"] = text; schedule_save_runtime()
                pm_banner_states.pop(user_id, None); await edit_panel("✅ ویرایش شد.", [[_cb("🔙 بازگشت", "pn_mat_list")]]); return True
            elif mode == "mat_edit_qty":
                if not text.isdigit(): return True
                cfg = transfer_materials_config.get(user_id, {}); idx = st.get("rule_idx")
                if 0 <= idx < len(cfg.get("rules", [])): cfg["rules"][idx]["quantity"] = int(text); schedule_save_runtime()
                pm_banner_states.pop(user_id, None); await edit_panel("✅ ویرایش شد.", [[_cb("🔙 بازگشت", "pn_mat_list")]]); return True

        if mode.startswith("item_"):
            if mode == "item_add_cid":
                if not text.isdigit() or not (1 <= len(text) <= 5):
                    await edit_panel("❌ آیدی باید بین ۱ تا ۵ رقم باشد. مجدد بفرستید:", [[_cb("🔴 لغو", "pn_transfer_items")]])
                    return True
                st["cid"] = text; st["mode"] = "item_add_name"; pm_banner_states[user_id] = st
                await edit_panel("✅ آیدی ثبت شد.\nحالا <b>نام کالا</b> را بفرستید:", [[_cb("🔴 لغو", "pn_transfer_items")]], parse_mode="html")
                return True
            elif mode == "item_add_name":
                if not text: return True
                st["name"] = text; st["mode"] = "item_add_qty"; pm_banner_states[user_id] = st
                await edit_panel("✅ نام ثبت شد.\nحالا <b>تعداد</b> را بفرستید.\n(0 برای همه):", [[_cb("🔴 لغو", "pn_transfer_items")]], parse_mode="html")
                return True
            elif mode == "item_add_qty":
                if not text.isdigit():
                    await edit_panel("❌ فقط عدد بفرستید (0 برای همه):", [[_cb("🔴 لغو", "pn_transfer_items")]])
                    return True
                cfg = transfer_items_config.setdefault(user_id, {"enabled": False, "rules": []})
                cfg["rules"].append({"cid": st.get("cid"), "material": st.get("name"), "quantity": int(text), "enabled": True})
                schedule_save_runtime(); pm_banner_states.pop(user_id, None)
                await edit_panel(f"✅ قانون کالا ثبت شد.\n🎁 {st.get('name')}", [[_cb("🔙 بازگشت", "pn_transfer_items")]])
                return True
            elif mode == "item_edit_cid":
                if not text.isdigit() or not (1 <= len(text) <= 5): return True
                cfg = transfer_items_config.get(user_id, {}); idx = st.get("rule_idx")
                if 0 <= idx < len(cfg.get("rules", [])): cfg["rules"][idx]["cid"] = text; schedule_save_runtime()
                pm_banner_states.pop(user_id, None); await edit_panel("✅ ویرایش شد.", [[_cb("🔙 بازگشت", "pn_item_list")]]); return True
            elif mode == "item_edit_name":
                if not text: return True
                cfg = transfer_items_config.get(user_id, {}); idx = st.get("rule_idx")
                if 0 <= idx < len(cfg.get("rules", [])): cfg["rules"][idx]["material"] = text; schedule_save_runtime()
                pm_banner_states.pop(user_id, None); await edit_panel("✅ ویرایش شد.", [[_cb("🔙 بازگشت", "pn_item_list")]]); return True
            elif mode == "item_edit_qty":
                if not text.isdigit(): return True
                cfg = transfer_items_config.get(user_id, {}); idx = st.get("rule_idx")
                if 0 <= idx < len(cfg.get("rules", [])): cfg["rules"][idx]["quantity"] = int(text); schedule_save_runtime()
                pm_banner_states.pop(user_id, None); await edit_panel("✅ ویرایش شد.", [[_cb("🔙 بازگشت", "pn_item_list")]]); return True

    except Exception as e:
        log_error(f"_pm_mat_state_input {user_id}: {_translate_bot_errors(e)}")
        pm_banner_states.pop(user_id, None)
        return True
    return False


def _panel_is_owner(target_user_id, actor_id=None):
    return is_grp_owner(target_user_id if actor_id is None else actor_id)


def _panel_is_manager(target_user_id, actor_id=None):
    return is_manager(target_user_id if actor_id is None else actor_id)


async def _dispatch_pn(event, user_id, data, actor_id=None):
    """گیت قفل بخش‌ها: هر دکمه/بخشی که مالک قفل کرده، برای کاربر اجرا نمی‌شود.

    مالک (وقتی از پنل مالک داخل پنل کاربر است) از این گیت عبور می‌کند.
    """
    try:
        acting_owner = (actor_id is not None and int(actor_id) != int(user_id)
                        and is_grp_owner(actor_id))
    except Exception:
        acting_owner = False
    key = str(data or "")
    if key and not acting_owner and is_section_locked(user_id, key):
        label = (get_locked_sections(user_id).get(key)
                 or SECTION_LOCK_TITLES.get(key) or key)
        return (f"🔒 «{label}» توسط مالک قفل شده است.\n"
                f"برای بازکردنش با مالک هماهنگ کن.",
                [[_cb("⚪ 🔙 بازگشت", "pn_refresh")]])
    return await _dispatch_pn_core(event, user_id, data, actor_id=actor_id)


async def _dispatch_pn_core(event, user_id, data, actor_id=None):
    # Owner-only view-as-user panel: every nested control is executed for target,
    # while the callback remains bound to the owner.
    if data.startswith("pn_access_as_"):
        if not _panel_is_owner(user_id, actor_id): return None
        try:
            target_s, nested = data.replace("pn_access_as_", "", 1).split("_", 1)
            target = int(target_s)
        except (ValueError, IndexError):
            return None
        if nested == "pn_close":
            return await _pm_build_user(user_id, target)
        result = await _dispatch_pn(event, target, nested, actor_id=actor_id)
        pending_state = pm_banner_states.get(target)
        if pending_state is not None and actor_id is not None:
            pending_state["panel_actor_id"] = int(actor_id)
        return _pm_wrap_access_proxy_result(user_id, target, result, current_raw=nested)
    if data.startswith("pn_access_seclk_"):
        # قفل/بازکردن کل همین بخشی که مالک داخلش است
        if not _panel_is_owner(user_id, actor_id): return None
        rest = data.replace("pn_access_seclk_", "", 1)
        target_s, _, panel_raw = rest.partition("_")
        try: target = int(target_s)
        except ValueError: return None
        if is_grp_owner(target): return None
        already = is_section_locked(target, panel_raw)
        label = get_locked_sections(target).get(panel_raw) or _panel_lock_label(panel_raw)
        set_section_locked(target, panel_raw, not already, label)
        notice = (f"🔓 «{label}» باز شد." if already
                  else f"🔒 «{label}» قفل شد و از پنل کاربر مخفی می‌شود.")
        nested_result = await _dispatch_pn(event, target, panel_raw, actor_id=actor_id)
        if nested_result is None:
            return await _pm_build_access_editor(user_id, target, notice)
        return _pm_wrap_access_proxy_result(user_id, target, nested_result, notice,
                                            current_raw=panel_raw)
    if data.startswith("pn_access_items_"):
        if not _panel_is_owner(user_id, actor_id): return None
        rest = data.replace("pn_access_items_", "", 1)
        target_s, _, panel_raw = rest.partition("_")
        try: target = int(target_s)
        except ValueError: return None
        return await _pm_build_access_item_menu(event, user_id, target, panel_raw)
    if data.startswith("pn_access_item_"):
        if not _panel_is_owner(user_id, actor_id): return None
        rest = data.replace("pn_access_item_", "", 1)
        parts = rest.split("_", 2)
        if len(parts) < 3: return None
        try:
            target, idx = int(parts[0]), int(parts[1])
        except ValueError:
            return None
        panel_raw = parts[2]
        _panel_text, items = await _access_panel_items(event, target, panel_raw)
        if not (0 <= idx < len(items)):
            return await _pm_build_access_item_menu(event, user_id, target, panel_raw,
                                                    "ℹ️ این دکمه دیگر در دسترس نیست.")
        raw, label = items[idx]
        now_locked = not is_section_locked(target, raw)
        set_section_locked(target, raw, now_locked, label)
        notice = (f"🔒 «{label}» قفل شد." if now_locked else f"🟢 «{label}» آزاد شد.")
        return await _pm_build_access_item_menu(event, user_id, target, panel_raw, notice)
    if data.startswith("pn_access_unlockall_"):
        if not _panel_is_owner(user_id, actor_id): return None
        try: target = int(data.replace("pn_access_unlockall_", "", 1))
        except ValueError: return None
        count = len(get_locked_sections(target))
        clear_section_locks(target)
        return await _pm_build_access_locks(
            user_id, target, f"🔓 {count} قفل باز شد." if count else "ℹ️ قفلی وجود نداشت.")
    if data.startswith("pn_access_unlk_"):
        if not _panel_is_owner(user_id, actor_id): return None
        rest = data.replace("pn_access_unlk_", "", 1)
        target_s, _, lock_key = rest.partition("_")
        try: target = int(target_s)
        except ValueError: return None
        label = get_locked_sections(target).get(lock_key, lock_key)
        set_section_locked(target, lock_key, False)
        return await _pm_build_access_locks(user_id, target, f"🟢 «{label}» آزاد شد.")
    if data.startswith("pn_access_locks_"):
        if not _panel_is_owner(user_id, actor_id): return None
        try: target = int(data.replace("pn_access_locks_", "", 1))
        except ValueError: return None
        return await _pm_build_access_locks(user_id, target)
    if data.startswith("pn_access_edit_"):
        if not _panel_is_owner(user_id, actor_id): return None
        try: target = int(data.replace("pn_access_edit_", "", 1))
        except ValueError: return None
        return await _pm_build_access_editor(user_id, target)
    if data.startswith("pn_access_exit_"):
        if not _panel_is_owner(user_id, actor_id): return None
        try: target = int(data.replace("pn_access_exit_", "", 1))
        except ValueError: return None
        return await _pm_build_user(user_id, target)
    if data.startswith("pn_access_lock_"):
        if not _panel_is_owner(user_id, actor_id): return None
        try: target = int(data.replace("pn_access_lock_", "", 1))
        except ValueError: return None
        if is_grp_owner(target): return None
        current = bool(users_db.get("users", {}).get(str(target), {}).get("all_access_locked", False))
        set_user_access_locked(target, not current)
        if current:
            try: _spawn(_restart_runtime_tasks())
            except Exception: pass
        notice = "🔒 دسترسی همهٔ بخش‌های کاربر قفل شد." if not current else "🔓 دسترسی کاربر باز شد."
        return await _pm_build_access_editor(user_id, target, notice)

    # ═══════════ Hook: Transfer Panels ═══════════
    tr_res = await _dispatch_transfer_pn(event, user_id, data)
    if tr_res is not None:
        return tr_res
    # ═════════════════════════════════════════════


    if data == "pn_notif_panel":
        return await _pm_build_notif_panel(user_id)
        
    if data.startswith("pn_notif_toggle_"):
        key = data.replace("pn_notif_toggle_", "")
        key_map = {"mat": "mat_trans", "item": "item_trans", "sell": "sell",
                   "mon": "monitor", "emoji": "emoji_name"}
        actual_key = key_map.get(key, key)
        notifs = get_user_notifs(user_id)
        notifs[actual_key] = not notifs.get(actual_key, True)
        save_user_notifs(user_id)
        return await _pm_build_notif_panel(user_id)


    if data == "pn_noop": return None
    if data == "pn_close":
        try:
            cl = user_clients.get(int(user_id))
            if cl and cl.is_connected():
                try:
                    await cl.delete_messages(event.query.peer, [event.query.msg_id])
                except Exception:
                    await _try_inline_edit_global(event.query.msg_id,
                        f"🔒 پنل بسته شد.\n\n💡 باز کردن: <code>{CMD}پنل</code>", None)
            else:
                await _try_inline_edit_global(event.query.msg_id,
                    "🔒 پنل بسته شد.", None)
        except Exception as e:
            log_error(f"pn_close: {_translate_bot_errors(e)}")
        return None
    if data == "pn_refresh":
        if actor_id is not None:
            broadcast_waiting.pop(int(actor_id), None)
        return await _pm_build_main(user_id)
    if data == "pn_status_panel": return await _pm_build_status_panel(user_id)
    if data == "pn_settings": return await _pm_build_settings_panel(user_id)
    if data == "pn_media_panel":
        if not _panel_is_owner(user_id, actor_id): return None
        return await _pm_build_media_access_panel(user_id)
    if data.startswith("pn_media_grant_list_"):
        if not _panel_is_owner(user_id, actor_id): return None
        try: page = int(data.rsplit("_", 1)[1])
        except (ValueError, IndexError): page = 0
        return await _pm_build_media_grant_list(user_id, page)
    if data.startswith("pn_media_grant_pick_"):
        if not _panel_is_owner(user_id, actor_id): return None
        try:
            target_s, page_s = data.replace("pn_media_grant_pick_", "", 1).rsplit("_", 1)
            target, page = int(target_s), int(page_s)
        except (ValueError, IndexError):
            return await _pm_build_media_grant_list(user_id, 0)
        return await _pm_build_media_grant_confirm(user_id, target, page)
    if data.startswith("pn_media_grant_no_"):
        if not _panel_is_owner(user_id, actor_id): return None
        try: page = int(data.rsplit("_", 1)[1])
        except (ValueError, IndexError): page = 0
        return await _pm_build_media_grant_list(user_id, page)
    if data.startswith("pn_media_grant_yes_"):
        if not _panel_is_owner(user_id, actor_id): return None
        try:
            target_s, page_s = data.replace("pn_media_grant_yes_", "", 1).rsplit("_", 1)
            target, page = int(target_s), int(page_s)
        except (ValueError, IndexError):
            return await _pm_build_media_grant_list(user_id, 0)
        if (is_grp_owner(target) or str(target) not in users_db.get("users", {})
                or is_media_allowed(target)):
            return await _pm_build_media_grant_list(
                user_id, page, "ℹ️ این کاربر دیگر برای افزودن در دسترس نیست."
            )
        set_media_allowed(target, True)
        return await _pm_build_media_grant_list(
            user_id, page, f"✅ دسترسی TTL/ذخیره به کاربر {target} داده شد."
        )
    if data.startswith("pn_media_remove_list_"):
        if not _panel_is_owner(user_id, actor_id): return None
        try: page = int(data.rsplit("_", 1)[1])
        except (ValueError, IndexError): page = 0
        return await _pm_build_media_remove_list(user_id, page)
    if data.startswith("pn_media_remove_pick_"):
        if not _panel_is_owner(user_id, actor_id): return None
        try:
            target_s, page_s = data.replace("pn_media_remove_pick_", "", 1).rsplit("_", 1)
            target, page = int(target_s), int(page_s)
        except (ValueError, IndexError):
            return await _pm_build_media_remove_list(user_id, 0)
        return await _pm_build_media_remove_confirm(user_id, target, page)
    if data.startswith("pn_media_remove_no_"):
        if not _panel_is_owner(user_id, actor_id): return None
        try: page = int(data.rsplit("_", 1)[1])
        except (ValueError, IndexError): page = 0
        return await _pm_build_media_remove_list(user_id, page)
    if data.startswith("pn_media_remove_yes_"):
        if not _panel_is_owner(user_id, actor_id): return None
        try:
            target_s, page_s = data.replace("pn_media_remove_yes_", "", 1).rsplit("_", 1)
            target, page = int(target_s), int(page_s)
        except (ValueError, IndexError):
            return await _pm_build_media_remove_list(user_id, 0)
        if is_grp_owner(target):
            return await _pm_build_media_remove_list(user_id, page, "⚠️ دسترسی مالک قابل حذف نیست.")
        if not is_media_allowed(target):
            return await _pm_build_media_remove_list(user_id, page, "ℹ️ این کاربر دیگر دسترسی ندارد.")
        set_media_allowed(target, False)
        return await _pm_build_media_remove_list(
            user_id, page, f"✅ دسترسی کاربر {target} حذف شد و TTL خودکار خاموش شد."
        )
    if data == "pn_tools": return await _pm_build_tools(user_id)
    if data == "pn_mon_main":
        if pm_banner_states.get(user_id, {}).get("mode") == "mon_add":
            pm_banner_states.pop(user_id, None)
        return await _pm_build_monitor_main(user_id)
    if data == "pn_mon_add":
        pm_banner_states[user_id] = {"mode": "mon_add", "prompt_chat_id": getattr(event, "chat_id", None)}
        return (f"👁 آیدی یا @یوزرنیم فرد را بفرست.\nبرای افزودن با ریپلای، در گروه روی پیام فرد ریپلای کن و بنویس <code>{CMD}پایش افزودن</code>",
                [[_cb("⚪ لغو", "pn_mon_main")]])
    if data == "pn_mon_toggle_all":
        cfg = monitor_db.setdefault(str(int(user_id)), {"enabled": False, "users": {}})
        cfg["enabled"] = not cfg.get("enabled", False)
        if cfg["enabled"]: start_monitor_task(user_id)
        else: stop_monitor_task(user_id)
        _save_monitor_db()
        return await _pm_build_monitor_main(user_id)
    if data.startswith("pn_mon_list_"):
        try: page = int(data.replace("pn_mon_list_", "", 1))
        except ValueError: page = 0
        return await _pm_build_monitor_list(user_id, page)
    if data.startswith("pn_mon_v_"):
        target_id = data.replace("pn_mon_v_", "", 1)
        return await _pm_build_monitor_view(user_id, target_id)
    if data.startswith("pn_mon_t_"):
        target_id = data.replace("pn_mon_t_", "", 1)
        users = monitor_db.get(str(int(user_id)), {}).get("users", {})
        if target_id in users:
            users[target_id]["enabled"] = not users[target_id].get("enabled", True)
            _save_monitor_db()
        return await _pm_build_monitor_view(user_id, target_id)
    if data.startswith("pn_mon_del_"):
        target_id = data.replace("pn_mon_del_", "", 1)
        users = monitor_db.get(str(int(user_id)), {}).get("users", {})
        users.pop(target_id, None)
        _save_monitor_db()
        return await _pm_build_monitor_list(user_id, 0)
    if data == "pn_random_profile_panel":
        return await _pm_build_random_profile_panel(user_id)
    if data == "pn_random_profile_toggle":
        cfg = get_random_profile_config(user_id)
        ok, message = await set_random_profile_enabled(user_id, not cfg.get("enabled", False))
        text, kb = await _pm_build_random_profile_panel(user_id)
        return (text if ok else message + "\n\n" + text), kb
    if data.startswith("pn_random_profile_iv_"):
        try: interval = int(data.rsplit("_", 1)[1])
        except ValueError: interval = 60
        if interval in (60, 300, 600):
            get_random_profile_config(user_id)["interval"] = interval
            save_json(USERS_FILE, users_db)
        return await _pm_build_random_profile_panel(user_id)
    if data == "pn_tts_panel":
        if pm_banner_states.get(user_id, {}).get("mode", "").startswith("tts_"):
            pm_banner_states.pop(user_id, None)
        return await _pm_build_tts_panel(user_id)
    if data == "pn_tts_cancel":
        pm_banner_states.pop(user_id, None)
        return await _pm_build_tts_panel(user_id)
    if data == "pn_tts_text_start":
        pm_banner_states[user_id] = {"mode": "tts_text_input", "prompt_chat_id": getattr(event, "chat_id", None)}
        return ("📝 متن موردنظر را در پیام بعدی بفرست تا به ویس تبدیلش کنم.",
                [[_cb("⚪ لغو", "pn_tts_cancel")]])
    if data == "pn_tts_voice_start":
        pm_banner_states[user_id] = {"mode": "tts_voice_wait", "prompt_chat_id": getattr(event, "chat_id", None)}
        return ("🎧 ویس یا فایل صوتی را در پیام بعدی بفرست تا متنش را استخراج کنم.",
                [[_cb("⚪ لغو", "pn_tts_cancel")]])
    if data in ("pn_tts_set_female", "pn_tts_set_male"):
        gender = "female" if data.endswith("female") else "male"
        users_db.setdefault("users", {}).setdefault(str(int(user_id)), {})["voice_gender"] = gender
        save_json(USERS_FILE, users_db)
        return await _pm_build_tts_panel(user_id)
    if data.startswith("pn_emoji_pos_"):
        position = data.replace("pn_emoji_pos_", "", 1)
        if position in ("start", "end"):
            get_name_emoji_config(user_id)["position"] = position
            save_json(USERS_FILE, users_db)
        return await _pm_build_name_emoji_panel(user_id)
    if data.startswith("pn_emoji_iv_"):
        try: interval = int(data.replace("pn_emoji_iv_", "", 1))
        except ValueError: interval = 60
        if interval in (60, 300, 600):
            cfg = get_name_emoji_config(user_id)
            cfg["interval"] = interval
            save_json(USERS_FILE, users_db)
        return await _pm_build_name_emoji_panel(user_id)
    if data == "pn_name_emoji_panel":
        if pm_banner_states.get(user_id, {}).get("mode") == "name_emoji_add":
            pm_banner_states.pop(user_id, None)
        return await _pm_build_name_emoji_panel(user_id)
    if data == "pn_name_emoji_cancel":
        pm_banner_states.pop(user_id, None)
        return await _pm_build_name_emoji_panel(user_id)
    if data == "pn_name_emoji_add":
        pm_banner_states[user_id] = {"mode": "name_emoji_add",
            "prompt_chat_id": getattr(event, "chat_id", None)}
        return ("➕ ایموجی دلخواه را بفرست. (نمونه: 🌟)",
                [[_cb("⚪ لغو", "pn_name_emoji_cancel")]])
    if data.startswith("pn_name_emoji_pick_"):
        cfg = get_name_emoji_config(user_id)
        all_emojis = list(dict.fromkeys(NAME_EMOJI_PRESETS + cfg.get("custom_emojis", [])))
        try: idx = int(data.replace("pn_name_emoji_pick_", "", 1))
        except ValueError: idx = -1
        if 0 <= idx < len(all_emojis):
            emoji = all_emojis[idx]
            selected = list(cfg.get("emojis", []))
            if emoji in selected: selected.remove(emoji)
            else: selected.append(emoji)
            cfg["emojis"] = selected
            if cfg.get("enabled") and selected:
                cfg["current_index"] = 0
            if not selected and cfg.get("enabled"):
                cfg["enabled"] = False
                stop_name_emoji_task(user_id)
                try: await _restore_original_profile_name(user_id)
                except Exception as e: log_error(f"name emoji restore {user_id}: {_translate_bot_errors(e)}")
            save_json(USERS_FILE, users_db)
        return await _pm_build_name_emoji_panel(user_id)
    if data == "pn_name_emoji_toggle":
        cfg = get_name_emoji_config(user_id)
        if cfg.get("enabled"):
            cfg["enabled"] = False
            stop_name_emoji_task(user_id)
            try:
                restored = await _restore_original_profile_name(user_id)
                if not restored:
                    log_error(f"name emoji restore: no client for {user_id}")
            except Exception as e:
                log_error(f"name emoji restore {user_id}: {_translate_bot_errors(e)}")
        else:
            if not cfg.get("emojis"):
                return ("❌ اول حداقل یک ایموجی انتخاب کن.",
                        [[_cb("🔙 بازگشت", "pn_name_emoji_panel")]])
            try:
                client = user_clients.get(int(user_id))
                if not client or not client.is_connected():
                    client = await ensure_user_client(user_id)
                if not client:
                    return ("❌ اتصال اکانت برقرار نیست.",
                            [[_cb("🔙 بازگشت", "pn_name_emoji_panel")]])
                me = await client.get_me()
                cfg["original_first_name"] = getattr(me, "first_name", "") or ""
                cfg["original_last_name"] = getattr(me, "last_name", "") or ""
                cfg["profile_saved"] = True
                cfg["enabled"] = True
                start_name_emoji_task(user_id)
            except Exception as e:
                return (f"❌ روشن نشد: {_translate_bot_errors(e)}",
                        [[_cb("🔙 بازگشت", "pn_name_emoji_panel")]])
        save_json(USERS_FILE, users_db)
        return await _pm_build_name_emoji_panel(user_id)
    if data == "pn_games": return await _pm_build_games(user_id)
    if data == "pn_cardinal_panel": return await _pm_build_cardinal_panel(user_id)
    if data == "pn_pew_panel": return await _pm_build_pew_panel(user_id)
    if data == "pn_war_panel": return await _pm_build_war_panel(user_id)
    if data == "pn_war_battle": return await _pm_build_war_battle(user_id)
    if data == "pn_war_attack": return await _pm_build_war_attack(user_id)
    if data == "pn_war_defense": return await _pm_build_war_defense(user_id)
    if data == "pn_sell_toggle":
        if user_id in sell_mode_users and sell_mode_users[user_id].get("enabled"):
            stop_sell_mode(user_id)
            _ensure_enabled_transfer_schedulers(user_id)
        else:
            sell_mode_users[user_id] = {"enabled": True, "scheduler_task": None}
            sell_mode_users[user_id]["scheduler_task"] = asyncio.create_task(sell_scheduler(user_id))
            schedule_save_runtime()
        return await _pm_build_cardinal_panel(user_id)
    if data == "pn_shkar_toggle":
        (stop_auto_send if auto_send_status.get(user_id, {}).get("شکار") else start_auto_send)(user_id, "شکار")
        return await _pm_build_cardinal_panel(user_id)
    if data == "pn_siah_toggle":
        (stop_auto_send if auto_send_status.get(user_id, {}).get("سیاه") else start_auto_send)(user_id, "سیاه")
        return await _pm_build_cardinal_panel(user_id)
    if data == "pn_fishing_toggle":
        is_on = fishing_status.get(user_id, False)
        fishing_status[user_id] = not is_on
        if not is_on:
            if user_id not in fishing_tasks or fishing_tasks[user_id].done():
                fishing_tasks[user_id] = asyncio.create_task(_fishing_loop(user_id))
        return await _pm_build_cardinal_panel(user_id)

    if data == "pn_esc_toggle":
        escape_config[user_id] = {"enabled": not is_escape_enabled(user_id)}
        schedule_save_runtime()
        return await _pm_build_cardinal_panel(user_id)
    if data == "pn_ret_set_same":
        return_config.setdefault(user_id, {})["type"] = "same"
        schedule_save_runtime()
        return await _pm_build_return_panel(user_id)
    if data == "pn_return_panel":
        return await _pm_build_return_panel(user_id)
    if data == "pn_ret_check_floor":
        _spawn(_force_floor_update(user_id))
        return ("⏳ در حال استعلام از بازی...\nلطفاً ۳ ثانیه صبر کنید و سپس دکمه زیر را بزنید.", [[_cb("🔄 مشاهده نتیجه", "pn_return_panel")]])
    if data == "pn_ret_toggle":
        return_config[user_id] = {"enabled": not is_return_enabled(user_id)}
        schedule_save_runtime()
        return await _pm_build_cardinal_panel(user_id)
    if data == "pn_gift_toggle":
        (stop_daily_gift if daily_gift_status.get(user_id, False) else start_daily_gift)(user_id)
        return await _pm_build_cardinal_panel(user_id)
    if data == "pn_transfer_materials":
        pm_banner_states.pop(user_id, None)
        return await _pm_build_materials_panel_v2(user_id)
        
    if data == "pn_mat_toggle":
        cfg = transfer_materials_config.setdefault(user_id, {"enabled": False, "rules": []})
        cfg["enabled"] = not cfg.get("enabled", False)
        schedule_save_runtime()
        if cfg["enabled"] and not sell_mode_users.get(user_id, {}).get("enabled"):
            _spawn(material_scheduler(user_id))
        return await _pm_build_materials_panel_v2(user_id)
        
    if data == "pn_mat_add":
        q = getattr(event, 'query', None)
        msg_id = getattr(q, 'msg_id', None) if q else getattr(event, 'message_id', None)
        pm_banner_states[user_id] = {"mode": "mat_add_cid", "prompt_id": msg_id}
        return ("📦 افزودن قانون انتقال\n━━━━━━━━━━━━━━━━━\nلطفاً <b>آیدی عددی بازیکن (C_ID)</b> مقصد را بفرستید.\n(باید ۱ تا ۵ رقمی باشد)", [[_cb("🔴 لغو", "pn_transfer_materials")]])
        
    if data == "pn_mat_list" or data == "pn_mat_refresh":
        cfg = transfer_materials_config.get(user_id, {})
        rules = cfg.get("rules", [])
        if not rules:
            return ("📋 لیست انتقال‌ها\n━━━━━━━━━━━━━━━━━\n❌ هیچ قانونی ثبت نشده است.", [[_cb("🔙 بازگشت", "pn_transfer_materials")]])
        
        kb = []
        for i, r in enumerate(rules):
            is_on = r.get("enabled", True)
            icon = "🟢" if is_on else "🔴"
            name = r.get('material', '')
            qty = r['quantity'] if r['quantity']>0 else 'همه'
            cid = r['cid']
            
            kb.append([_cb(f"{icon} {name} ({qty}) ➡️ {cid}", f"pn_mat_toggle_{i}")])
            kb.append([_cb("✏️ گیرنده", f"pn_mat_edit_cid_{i}"), _cb("✏️ اسم", f"pn_mat_edit_name_{i}"), _cb("✏️ تعداد", f"pn_mat_edit_qty_{i}")])
            kb.append([_cb("🗑 حذف", f"pn_mat_del_ask_{i}")])
            
        kb.append([_cb("🔙 بازگشت", "pn_transfer_materials")])
        return ("📋 لیست انتقال‌ها\n━━━━━━━━━━━━━━━━━\nبرای تغییر وضعیت روی دکمه رنگی بزنید:", kb)

    if data.startswith("pn_mat_toggle_"):
        idx = int(data.replace("pn_mat_toggle_", ""))
        cfg = transfer_materials_config.get(user_id, {})
        rules = cfg.get("rules", [])
        if 0 <= idx < len(rules):
            rules[idx]["enabled"] = not rules[idx].get("enabled", True)
            schedule_save_runtime()
        return await _dispatch_pn(event, user_id, "pn_mat_list")

    if data.startswith("pn_mat_del_ask_"):
        idx = int(data.replace("pn_mat_del_ask_", ""))
        cfg = transfer_materials_config.get(user_id, {})
        rules = cfg.get("rules", [])
        if idx < 0 or idx >= len(rules): return await _pm_build_materials_panel_v2(user_id)
        r = rules[idx]
        txt = f"⚠️ آیا از حذف این قانون مطمئنید؟\n\n📦 {r['material']} ➡️ {r['cid']}"
        return (txt, [[_cb("✅ بله، حذف شود", f"pn_mat_del_yes_{idx}")], [_cb("❌ خیر", "pn_transfer_materials")]])
        
    if data.startswith("pn_mat_del_yes_"):
        idx = int(data.replace("pn_mat_del_yes_", ""))
        cfg = transfer_materials_config.get(user_id, {})
        if "rules" in cfg and idx < len(cfg["rules"]):
            cfg["rules"].pop(idx)
            schedule_save_runtime()
        return ("✅ قانون با موفقیت حذف شد.", [[_cb("🔙 بازگشت به لیست", "pn_mat_list")]])
        
    if data.startswith("pn_mat_edit_cid_"):
        idx = int(data.replace("pn_mat_edit_cid_", ""))
        pm_banner_states[user_id] = {"mode": "mat_edit_cid", "rule_idx": idx}
        return ("✏️ <b>ویرایش گیرنده</b>\nلطفاً آیدی جدید (۱ تا ۵ رقمی) را بفرستید:", [[_cb("🔴 لغو", "pn_mat_list")]])
        
    if data.startswith("pn_mat_edit_name_"):
        idx = int(data.replace("pn_mat_edit_name_", ""))
        pm_banner_states[user_id] = {"mode": "mat_edit_name", "rule_idx": idx}
        return ("✏️ <b>ویرایش نام ماده</b>\nلطفاً نام جدید ماده را بفرستید:", [[_cb("🔴 لغو", "pn_mat_list")]])
        
    if data.startswith("pn_mat_edit_qty_"):
        idx = int(data.replace("pn_mat_edit_qty_", ""))
        pm_banner_states[user_id] = {"mode": "mat_edit_qty", "rule_idx": idx}
        return ("✏️ <b>ویرایش تعداد</b>\nلطفاً تعداد جدید را بفرستید. (0 برای همه):", [[_cb("🔴 لغو", "pn_mat_list")]])

    # ─── کالاها ───
    if data == "pn_transfer_items":
        pm_banner_states.pop(user_id, None)
        return await _pm_build_materials_panel_v2(user_id)
        
    if data == "pn_item_toggle":
        cfg = transfer_items_config.setdefault(user_id, {"enabled": False, "rules": []})
        cfg["enabled"] = not cfg.get("enabled", False)
        schedule_save_runtime()
        if cfg["enabled"] and not sell_mode_users.get(user_id, {}).get("enabled"):
            _spawn(item_scheduler(user_id))
        return await _pm_build_items_panel(user_id)
        
    if data == "pn_item_add":
        q = getattr(event, 'query', None)
        msg_id = getattr(q, 'msg_id', None) if q else getattr(event, 'message_id', None)
        pm_banner_states[user_id] = {"mode": "item_add_cid", "prompt_id": msg_id}
        return ("🎁 افزودن قانون انتقال کالا\n━━━━━━━━━━━━━━━━━\nلطفاً <b>آیدی عددی بازیکن (C_ID)</b> مقصد را بفرستید.\n(باید ۱ تا ۵ رقمی باشد)", [[_cb("🔴 لغو", "pn_transfer_items")]])
        
    if data == "pn_item_list" or data == "pn_item_refresh":
        cfg = transfer_items_config.get(user_id, {})
        rules = cfg.get("rules", [])
        if not rules:
            return ("📋 لیست انتقال کالاها\n━━━━━━━━━━━━━━━━━\n❌ هیچ قانونی ثبت نشده است.", [[_cb("🔙 بازگشت", "pn_transfer_items")]])
        
        kb = []
        for i, r in enumerate(rules):
            is_on = r.get("enabled", True)
            icon = "🟢" if is_on else "🔴"
            name = r.get('material', '')
            qty = r['quantity'] if r['quantity']>0 else 'همه'
            cid = r['cid']
            
            kb.append([_cb(f"{icon} {name} ({qty}) ➡️ {cid}", f"pn_item_toggle_{i}")])
            kb.append([_cb("✏️ گیرنده", f"pn_item_edit_cid_{i}"), _cb("✏️ اسم", f"pn_item_edit_name_{i}"), _cb("✏️ تعداد", f"pn_item_edit_qty_{i}")])
            kb.append([_cb("🗑 حذف", f"pn_item_del_ask_{i}")])
            
        kb.append([_cb("🔙 بازگشت", "pn_transfer_items")])
        return ("📋 لیست انتقال کالاها\n━━━━━━━━━━━━━━━━━\nبرای تغییر وضعیت روی دکمه رنگی بزنید:", kb)

    if data.startswith("pn_item_toggle_"):
        idx = int(data.replace("pn_item_toggle_", ""))
        cfg = transfer_items_config.get(user_id, {})
        rules = cfg.get("rules", [])
        if 0 <= idx < len(rules):
            rules[idx]["enabled"] = not rules[idx].get("enabled", True)
            schedule_save_runtime()
        return await _dispatch_pn(event, user_id, "pn_item_list")

    if data.startswith("pn_item_del_ask_"):
        idx = int(data.replace("pn_item_del_ask_", ""))
        cfg = transfer_items_config.get(user_id, {})
        rules = cfg.get("rules", [])
        if idx < 0 or idx >= len(rules): return await _pm_build_items_panel(user_id)
        r = rules[idx]
        txt = f"⚠️ آیا از حذف این قانون مطمئنید؟\n\n🎁 {r['material']} ➡️ {r['cid']}"
        return (txt, [[_cb("✅ بله، حذف شود", f"pn_item_del_yes_{idx}")], [_cb("❌ خیر", "pn_transfer_items")]])
        
    if data.startswith("pn_item_del_yes_"):
        idx = int(data.replace("pn_item_del_yes_", ""))
        cfg = transfer_items_config.get(user_id, {})
        if "rules" in cfg and idx < len(cfg["rules"]):
            cfg["rules"].pop(idx)
            schedule_save_runtime()
        return ("✅ قانون با موفقیت حذف شد.", [[_cb("🔙 بازگشت به لیست", "pn_item_list")]])
        
    if data.startswith("pn_item_edit_cid_"):
        idx = int(data.replace("pn_item_edit_cid_", ""))
        pm_banner_states[user_id] = {"mode": "item_edit_cid", "rule_idx": idx}
        return ("✏️ <b>ویرایش گیرنده</b>\nلطفاً آیدی جدید (۱ تا ۵ رقمی) را بفرستید:", [[_cb("🔴 لغو", "pn_item_list")]])
        
    if data.startswith("pn_item_edit_name_"):
        idx = int(data.replace("pn_item_edit_name_", ""))
        pm_banner_states[user_id] = {"mode": "item_edit_name", "rule_idx": idx}
        return ("✏️ <b>ویرایش نام کالا</b>\nلطفاً نام جدید کالا را بفرستید:", [[_cb("🔴 لغو", "pn_item_list")]])
        
    if data.startswith("pn_item_edit_qty_"):
        idx = int(data.replace("pn_item_edit_qty_", ""))
        pm_banner_states[user_id] = {"mode": "item_edit_qty", "rule_idx": idx}
        return ("✏️ <b>ویرایش تعداد</b>\nلطفاً تعداد جدید را بفرستید. (0 برای همه):", [[_cb("🔴 لغو", "pn_item_list")]])

    if data == "pn_transfer_menu":
        return await _pm_build_transfer_menu(user_id)

    if data == "pn_ftmax_save":
        return await _pm_build_cardinal_panel(user_id)
    if data == "pn_nosell_panel": return await _pm_build_nosell_panel(user_id)
    if data == "pn_nosell_view": return await _pm_build_nosell_view(user_id)
    if data == "pn_nosell_add":
        pm_banner_states[user_id] = {"mode": "nosell_add", "prompt_chat_id": event.chat_id}
        return ("➕ افزودن نفروش\n━━━━━━━━━━━━━━━━━\n"
                "اسم آیتم‌ها رو بفرست:\n"
                "• یکی: <code>شمشیر</code>\n"
                "• چندتا: <code>شمشیر * سپر * زره</code>",
                [[_cb("🔴 لغو", "pn_nosell_panel")]])
    if data.startswith("pn_nosell_remove_"):
        pg = int(data.replace("pn_nosell_remove_", "") or 0)
        return await _pm_build_nosell_remove_list(user_id, pg)
    if data.startswith("pn_nosell_rm_yes_"):
        idx = int(data.replace("pn_nosell_rm_yes_", ""))
        lst = get_no_sell_list(user_id)
        if 0 <= idx < len(lst):
            remove_no_sell_items(user_id, [lst[idx]])
        return await _pm_build_nosell_panel(user_id)
    if data.startswith("pn_nosell_rm_"):
        idx = int(data.replace("pn_nosell_rm_", ""))
        return await _pm_build_nosell_rm_confirm(user_id, idx)
    if data == "pn_html_panel": return await _pm_build_html_panel(user_id)
    if data == "pn_font_panel": return await _pm_build_font_panel(user_id)
    if data == "pn_ttl_panel":
        if not is_media_allowed(user_id):
            return ("🔒 <i>این بخش خصوصی است</i>", [[_cb("⚪ 🔙", "pn_tools")]])
        return await _pm_build_ttl_panel(user_id)
    if data == "pn_save_panel":
        if not is_media_allowed(user_id):
            return ("🔒 <i>این بخش خصوصی است</i>", [[_cb("⚪ 🔙", "pn_tools")]])
        return await _pm_build_save_panel(user_id)
    if data == "pn_html_toggle":
        cur = users_db["users"].get(str(user_id), {}).get("html_style_on", False)
        set_user_html_style_on(user_id, not cur)
        return await _pm_build_html_panel(user_id)
    if data.startswith("pn_html_pick_"):
        key = data.replace("pn_html_pick_", "")
        set_user_html_style(user_id, key)
        if key != "none": set_user_html_style_on(user_id, True)
        return await _pm_build_html_panel(user_id)
    if data == "pn_font_toggle":
        cur = users_db["users"].get(str(user_id), {}).get("font_on", False)
        set_user_font_on(user_id, not cur)
        return await _pm_build_font_panel(user_id)
    if data.startswith("pn_font_pick_"):
        key = data.replace("pn_font_pick_", "")
        set_user_font(user_id, key)
        if key != "none": set_user_font_on(user_id, True)
        return await _pm_build_font_panel(user_id)
    if data == "pn_ttl_toggle":
        if not is_media_allowed(user_id):
            return ("🔒 این بخش در دسترس نیست.", [[_cb("⚪ 🔙 بازگشت", "pn_tools")]])
        cfg = get_ttl_config(user_id)
        set_ttl_config(user_id, "enabled", not cfg["enabled"])
        return await _pm_build_ttl_panel(user_id)
    if data == "pn_ttl_reset_target":
        if not is_media_allowed(user_id):
            return ("🔒 این بخش در دسترس نیست.", [[_cb("⚪ 🔙 بازگشت", "pn_tools")]])
        set_ttl_config(user_id, "target", "me")
        return await _pm_build_ttl_panel(user_id)
    if data == "pn_gender_panel": return await _pm_build_gender_panel(user_id)
    if data.startswith("pn_gender_set_"):
        g = data.replace("pn_gender_set_", "")
        if g == "none": g = None
        set_user_gender(user_id, g)
        return await _pm_build_gender_panel(user_id)
    if data == "pn_banner_clear":
        set_user_banner_id(user_id, None)
        return await _pm_build_banner_picker(user_id)
    if data == "pn_banner_picker":
        return await _pm_build_banner_picker(user_id, 0)
    if data.startswith("pn_banner_picker_"):
        pg = int(data.replace("pn_banner_picker_", "") or 0)
        return await _pm_build_banner_picker(user_id, pg)
    if data.startswith("pn_banner_preview_"):
        bid = data.replace("pn_banner_preview_", "")
        return await _pm_build_banner_preview(user_id, bid)
    if data.startswith("pn_blike_"):
        bid = data.replace("pn_blike_", "")
        b = get_gender_banner_by_id(bid)
        if b:
            uid = int(user_id)
            if uid in b.get("dislikes_by", []): b["dislikes_by"].remove(uid)
            if uid in b.get("likes_by", []): b["likes_by"].remove(uid)
            else: b["likes_by"].append(uid)
            _save_gb()
        return await _pm_build_banner_preview(user_id, bid)
    if data.startswith("pn_bdislike_"):
        bid = data.replace("pn_bdislike_", "")
        b = get_gender_banner_by_id(bid)
        if b:
            uid = int(user_id)
            if uid in b.get("likes_by", []): b["likes_by"].remove(uid)
            if uid in b.get("dislikes_by", []): b["dislikes_by"].remove(uid)
            else: b["dislikes_by"].append(uid)
            _save_gb()
        return await _pm_build_banner_preview(user_id, bid)
    if data.startswith("pn_bchoose_"):
        bid = data.replace("pn_bchoose_", "")
        cur = get_user_banner_id(user_id)
        if cur == bid: set_user_banner_id(user_id, None)
        else: set_user_banner_id(user_id, bid)
        return await _pm_build_banner_preview(user_id, bid)
    if data == "pn_owner":
        if not (_panel_is_owner(user_id, actor_id) or _panel_is_manager(user_id, actor_id)): return None
        return await _pm_build_owner_full(user_id)
    if data == "pn_managers":
        if not _panel_is_owner(user_id, actor_id): return None
        return await _pm_build_managers_panel(user_id)
    if data.startswith("pn_users_"):
        if not _panel_is_owner(user_id, actor_id): return None
        pg = int(data.replace("pn_users_", "") or 0)
        return await _pm_build_users_full(user_id, pg)
    if data.startswith("pn_user_"):
        if not _panel_is_owner(user_id, actor_id): return None
        tid = data.replace("pn_user_", "")
        try: tid = int(tid)
        except: return None
        return await _pm_build_user(user_id, tid)
    if data.startswith("pn_ban_"):
        if not _panel_is_owner(user_id, actor_id): return None
        tid = int(data.replace("pn_ban_", ""))
        _ensure_user(str(tid))
        users_db["users"][str(tid)]["banned"] = True
        users_db["users"][str(tid)]["active"] = False
        save_json(USERS_FILE, users_db)
        stop_sell_mode(tid); stop_all_auto_sends(tid); stop_transfer(tid)
        stop_daily_gift(tid); stop_all_pony_for_user(tid); stop_all_dungeon_for_user(tid)
        stop_all_pew_ring_for_user(tid); stop_all_pew_target_for_user(tid)
        stop_all_pew_dog_for_user(tid); cancel_user_battle_tasks(tid)
        return await _pm_build_user(user_id, tid)
    if data.startswith("pn_unban_"):
        if not _panel_is_owner(user_id, actor_id): return None
        tid = int(data.replace("pn_unban_", ""))
        _ensure_user(str(tid))
        users_db["users"][str(tid)]["banned"] = False
        save_json(USERS_FILE, users_db)
        return await _pm_build_user(user_id, tid)
    if data.startswith("pn_addmgr_"):
        if not _panel_is_owner(user_id, actor_id): return None
        tid = int(data.replace("pn_addmgr_", ""))
        if not is_manager(tid): toggle_manager(tid)
        return await _pm_build_user(user_id, tid)
    if data.startswith("pn_rmmgr_"):
        if not _panel_is_owner(user_id, actor_id): return None
        tid = int(data.replace("pn_rmmgr_", ""))
        if is_manager(tid): toggle_manager(tid)
        return await _pm_build_user(user_id, tid)
    if data.startswith("pn_rmsess_"):
        if not _panel_is_owner(user_id, actor_id): return None
        tid = int(data.replace("pn_rmsess_", ""))
        sp = SESSION_DIR / str(tid)
        if os.path.exists(str(sp) + ".session"):
            try: os.remove(str(sp) + ".session")
            except: pass
        set_user_active(tid, False)
        await disconnect_user_client(tid)
        return await _pm_build_user(user_id, tid)
    if data.startswith("pn_reload_"):
        if not _panel_is_owner(user_id, actor_id): return None
        tid = int(data.replace("pn_reload_", ""))
        return await _pm_build_user(user_id, tid)
    if data.startswith("pn_media_t_"):
        if not _panel_is_owner(user_id, actor_id): return None
        tid = int(data.replace("pn_media_t_", ""))
        if tid == OWNER_ID:
            return await _pm_build_user(user_id, tid)
        cur = is_media_allowed(tid)
        set_media_allowed(tid, not cur)
        return await _pm_build_user(user_id, tid)
    if data == "pn_broadcast":
        if not _panel_is_owner(user_id, actor_id): return None
        broadcast_waiting[actor_id if actor_id is not None else user_id] = True
        return ("📢 پیام همگانی\n━━━━━━━━━━━━━━━━━\n"
                "پیام یا ریپلای بفرست.\nلغو: <code>،لغو</code>",
                [[_cb("🔴 لغو", "pn_refresh")]])
    if data == "pn_ping":
        if not (_panel_is_owner(user_id, actor_id) or _panel_is_manager(user_id, actor_id)): return None
        client = await ensure_user_client(user_id)
        if not client: return ("❌ اتصال نیست.", [[_cb("⚪ 🔙", "pn_owner")]])
        t0 = time.time()
        try:
            await client.get_me(); ping_ms = (time.time() - t0) * 1000
        except: ping_ms = -1
        up = int(time.time() - STATS_START_TIME)
        d, rem = divmod(up, 86400); h, rem = divmod(rem, 3600); m, _ = divmod(rem, 60)
        up_str = f"{d}d {h}h" if d else (f"{h}h {m}m" if h else f"{m}m")
        lines = ["🏓 پینگ", "━━━━━━━━━━━━━━━━━",
                 f"📡 {ping_ms:.0f} ms" if ping_ms >= 0 else "❌ خطا",
                 f"⏱ {up_str}", f"🐍 {sys.version.split()[0]}",
                 f"🖥 {platform.system()}"]
        return ("\n".join(lines), [[_cb("🔄", "pn_ping"), _cb("⚪ 🔙", "pn_owner")]])
    if data == "pn_gb_panel":
        if not _panel_is_owner(user_id, actor_id): return None
        return await _pm_build_gender_banners_panel(user_id)
    if data == "pn_gb_up_girl":
        if not _panel_is_owner(user_id, actor_id): return None
        pm_banner_states[user_id] = {"mode": "gb_upload", "gender": "girl", "prompt_chat_id": event.chat_id}
        return ("🖼 آپلود بنر دخترانه\n━━━━━━━━━━━━━━━━━\nیه عکس بفرست.",
                [[_cb("🔴 لغو", "pn_gb_panel")]])
    if data == "pn_gb_up_boy":
        if not _panel_is_owner(user_id, actor_id): return None
        pm_banner_states[user_id] = {"mode": "gb_upload", "gender": "boy", "prompt_chat_id": event.chat_id}
        return ("🖼 آپلود بنر پسرانه\n━━━━━━━━━━━━━━━━━\nیه عکس بفرست.",
                [[_cb("🔴 لغو", "pn_gb_panel")]])
    if data.startswith("pn_gb_list_"):
        if not _panel_is_owner(user_id, actor_id): return None
        rest = data.replace("pn_gb_list_", "")
        parts = rest.rsplit("_", 1)
        gender = parts[0]; pg = int(parts[1]) if len(parts) > 1 else 0
        return await _pm_build_gender_list(user_id, gender, pg)
    if data.startswith("pn_gb_view_"):
        if not _panel_is_owner(user_id, actor_id): return None
        bid = data.replace("pn_gb_view_", "")
        return await _pm_build_gender_view(user_id, bid)
    if data.startswith("pn_gb_del_yes_"):
        if not _panel_is_owner(user_id, actor_id): return None
        bid = data.replace("pn_gb_del_yes_", "")
        delete_gender_banner(bid)
        gender = "girl" if bid.startswith("girl_") else "boy"
        return await _pm_build_gender_list(user_id, gender, 0)
    if data.startswith("pn_gb_del_"):
        if not _panel_is_owner(user_id, actor_id): return None
        bid = data.replace("pn_gb_del_", "")
        return await _pm_build_gender_del_confirm(user_id, bid)
    if data == "pn_banner_main": return await _pm_build_banner_main(user_id)
    if data.startswith("pn_banner_list_"):
        pg = int(data.replace("pn_banner_list_", "") or 0)
        return await _pm_build_banner_list(user_id, pg)
    if data == "pn_banner_add":
        prompt = ("➕ بنر جدید\n━━━━━━━━━━━━━━━━━\n"
                  "اسم بنر رو بفرست:\n<i>مثال: پونی، فراخوان، اعلان</i>")
        state = {"mode": "add_name", "prompt_chat_id": event.chat_id}
        _arm_banner_add_timeout(user_id, state, prompt,
                                getattr(getattr(event, "query", None), "msg_id", None))
        return (prompt, [[_cb("🔴 لغو", "pn_banner_cancel")]])
    if data.startswith("pn_banner_editpick_"):
        bname = data.replace("pn_banner_editpick_", "")
        return await _pm_build_banner_edit_menu(user_id, bname)
    if data.startswith("pn_banner_edit_name_"):
        bname = data.replace("pn_banner_edit_name_", "")
        if bname not in get_user_banners(user_id): return None
        pm_banner_states[user_id] = {"mode": "edit_name", "old_name": bname, "prompt_chat_id": event.chat_id}
        return (f"✏️ نام جدید بنر «{bname}» رو بفرست:",
                [[_cb("🔴 لغو", f"pn_banner_editpick_{bname}")]])
    if data.startswith("pn_banner_edit_content_"):
        bname = data.replace("pn_banner_edit_content_", "")
        if bname not in get_user_banners(user_id): return None
        pm_banner_states[user_id] = {"mode": "edit_content", "banner_name": bname, "prompt_chat_id": event.chat_id}
        return (f"📄 محتوای جدید «{bname}» رو بفرست.\n(متن یا رسانه)",
                [[_cb("🔴 لغو", f"pn_banner_editpick_{bname}")]])
    if data.startswith("pn_banner_edit_interval_"):
        bname = data.replace("pn_banner_edit_interval_", "")
        b = get_user_banners(user_id).get(bname)
        if not b: return None
        sec = int(b.get("interval", 60))
        unit, value = "m", max(1, sec // 60)
        if sec % 3600 == 0 and sec >= 3600: unit, value = "h", sec // 3600
        elif sec % 86400 == 0 and sec >= 86400: unit, value = "d", sec // 86400
        elif sec < 60: unit, value = "s", sec
        pm_banner_states[user_id] = {"mode": "edit_interval",
            "data": {"unit": unit, "value": value}, "banner_name": bname}
        return await _pm_build_interval_slider(user_id, bname, "edit")
    if data.startswith("pn_banner_edit_"):
        pg = int(data.replace("pn_banner_edit_", "") or 0)
        return await _pm_build_banner_edit_list(user_id, pg)
    if data == "pn_bi_noop": return None
    if data in ("pn_bi_unit_prev", "pn_bi_unit_next"):
        st = pm_banner_states.get(user_id, {})
        d = st.get("data", {})
        units = ["s", "m", "h", "d"]
        cur = d.get("unit", "m")
        idx = units.index(cur) if cur in units else 1
        d["unit"] = units[(idx - 1) % 4] if data == "pn_bi_unit_prev" else units[(idx + 1) % 4]
        st["data"] = d; pm_banner_states[user_id] = st
        return await _pm_build_interval_slider(user_id, st.get("banner_name", ""), "edit")
    if data in ("pn_bi_dec1", "pn_bi_dec10", "pn_bi_inc1", "pn_bi_inc10"):
        st = pm_banner_states.get(user_id, {})
        d = st.get("data", {})
        val = d.get("value", 1)
        if data == "pn_bi_dec1": val = max(1, val - 1)
        elif data == "pn_bi_dec10": val = max(1, val - 10)
        elif data == "pn_bi_inc1": val = min(999, val + 1)
        else: val = min(999, val + 10)
        d["value"] = val; st["data"] = d; pm_banner_states[user_id] = st
        return await _pm_build_interval_slider(user_id, st.get("banner_name", ""), "edit")
    if data == "pn_bi_confirm":
        st = pm_banner_states.get(user_id, {})
        bname = st.get("banner_name", "")
        d = st.get("data", {})
        mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}[d.get("unit", "m")]
        sec = max(30, d.get("value", 1) * mult)
        banners = get_user_banners(user_id)
        if bname in banners:
            banners[bname]["interval"] = sec
            save_json(BANNERS_FILE, banners_db)
        pm_banner_states.pop(user_id, None)
        return await _pm_build_banner_view(user_id, bname)
    if data.startswith("pn_banner_view_"):
        bname = data.replace("pn_banner_view_", "")
        return await _pm_build_banner_view(user_id, bname)
    if data.startswith("pn_banner_toggle_"):
        bname = data.replace("pn_banner_toggle_", "")
        banners = get_user_banners(user_id)
        if bname in banners:
            new_state = not banners[bname].get("active", False)
            banners[bname]["active"] = new_state
            save_json(BANNERS_FILE, banners_db)
            if new_state: await start_banner_task(user_id, bname)
            else: await stop_banner_task(user_id, bname)
        return await _pm_build_banner_view(user_id, bname)
    if data.startswith("pn_banner_send_"):
        bname = data.replace("pn_banner_send_", "")
        banners = get_user_banners(user_id)
        b = banners.get(bname)
        if b:
            client = user_clients.get(int(user_id))
            if not client or not client.is_connected():
                client = await ensure_user_client(user_id)
            if client:
                for cid in b.get("targets", []):
                    try:
                        await _send_banner_to(client, user_id, bname, b, cid)
                        update_banner_stats(user_id, bname)
                    except: pass
        return await _pm_build_banner_view(user_id, bname)
    if data.startswith("pn_banner_reply_clear_"):
        bname = data.replace("pn_banner_reply_clear_", "")
        banners = get_user_banners(user_id)
        if bname in banners:
            banners[bname]["reply_to_msg_id"] = None
            save_json(BANNERS_FILE, banners_db)
        return await _pm_build_banner_view(user_id, bname)
    if data.startswith("pn_banner_reply_set_"):
        bname = data.replace("pn_banner_reply_set_", "")
        return await _pm_build_banner_view(user_id, bname)
    if data.startswith("pn_banner_del_yes_"):
        bname = data.replace("pn_banner_del_yes_", "")
        banners = get_user_banners(user_id)
        if bname in banners:
            media = banners[bname].get("media_file")
            if media and os.path.exists(media):
                try: os.remove(media)
                except: pass
            banners.pop(bname)
            save_json(BANNERS_FILE, banners_db)
            await stop_banner_task(user_id, bname)
        return await _pm_build_banner_main(user_id)
    if data.startswith("pn_banner_del_"):
        bname = data.replace("pn_banner_del_", "")
        return await _pm_build_banner_del_confirm(user_id, bname)
    if data.startswith("pn_banner_targets_"):
        bname = data.replace("pn_banner_targets_", "")
        pm_banner_states[user_id] = pm_banner_states.get(user_id, {})
        pm_banner_states[user_id]["bname"] = bname
        return await _pm_build_banner_targets(user_id, bname)
    if data.startswith("pn_banner_tpg_"):
        rest = data.replace("pn_banner_tpg_", ""); parts = rest.rsplit("_", 1)
        pm_banner_states[user_id] = pm_banner_states.get(user_id, {})
        pm_banner_states[user_id]["bname"] = parts[0]
        return await _pm_build_banner_targets(user_id, parts[0], int(parts[1]))
    if data.startswith("pn_banner_atg_"):
        rest = data.replace("pn_banner_atg_", ""); parts = rest.rsplit("_", 1)
        bname = parts[0]; cid = int(parts[1])
        pm_banner_states[user_id] = pm_banner_states.get(user_id, {})
        pm_banner_states[user_id]["bname"] = bname
        banners = get_user_banners(user_id)
        if bname in banners:
            targets = banners[bname].setdefault("targets", [])
            if cid in targets: targets.remove(cid)
            else: targets.append(cid)
            save_json(BANNERS_FILE, banners_db)
        return await _pm_build_banner_targets(user_id, bname)
    if data == "pn_banner_done": return await _pm_build_banner_main(user_id)
    if data == "pn_banner_cancel":
        _clear_banner_add_state(user_id)
        return await _pm_build_banner_main(user_id)
    if data == "pn_tools_naz":
        cid = pm_panel_chat.get(int(user_id))
        if cid is not None:
            return await _pm_build_naz_auto_panel(user_id, int(cid))
        return ("💞 اول گروه موردنظر را انتخاب کن تا «ناز» در همان گروه فرستاده شود.",
                [[_cb("🔀 انتخاب گروه", "pn_pony_pick")],
                 [_cb("⚪ 🔙 بازگشت به ابزارها", "pn_tools")]])
    if data == "pn_pony_main": return await _pm_build_pony_main(user_id)
    if data == "pn_pony_pick": return await _pm_build_pony_pick(user_id)
    if data.startswith("pn_pony_pg_"):
        pg = int(data.replace("pn_pony_pg_", "") or 0)
        return await _pm_build_pony_pick(user_id, pg)
    if data.startswith("pn_pony_sel_"):
        cid = int(data.replace("pn_pony_sel_", ""))
        pm_panel_chat[int(user_id)] = cid
        schedule_save_runtime()
        return await _pm_build_pony_panel(user_id, cid)
    if data.startswith("pn_pony_naz_panel_"):
        cid = int(data.replace("pn_pony_naz_panel_", "", 1))
        return await _pm_build_naz_auto_panel(user_id, cid)
    if data.startswith("pn_pony_naz_interval_"):
        raw = data.replace("pn_pony_naz_interval_", "", 1)
        try:
            cid_str, minutes_str = raw.rsplit("_", 1)
            cid, minutes = int(cid_str), int(minutes_str)
        except (TypeError, ValueError):
            return ("❌ بازه نامعتبر است.", [[_cb("⚪ 🔙 بازگشت", "pn_pony_main")]])
        if minutes not in (3, 5):
            return ("❌ بازه نامعتبر است.", [[_cb("⚪ 🔙 بازگشت", f"pn_pony_naz_panel_{cid}")]])
        cfg = get_pony_cfg(user_id, cid)
        cfg["naz_interval_mins"] = minutes
        pm_panel_chat[int(user_id)] = cid
        schedule_save_runtime()
        return await _pm_build_naz_auto_panel(user_id, cid)
    if data.startswith("pn_pony_naz_toggle_"):
        cid = int(data.replace("pn_pony_naz_toggle_", "", 1))
        cfg = get_pony_cfg(user_id, cid)
        cfg.setdefault("naz_interval_mins", 3)
        cfg["naz_enabled"] = not cfg.get("naz_enabled", False)
        pm_panel_chat[int(user_id)] = cid
        if cfg["naz_enabled"]:
            start_naz_auto_task(user_id, cid)
        else:
            stop_naz_auto_task(user_id, cid)
        schedule_save_runtime()
        return await _pm_build_naz_auto_panel(user_id, cid)
    if data.startswith("pn_pony_ctrl_"):
        cid = int(data.replace("pn_pony_ctrl_", ""))
        return await _pm_build_pony_ctrl(user_id, cid)
    if data.startswith("pn_pony_interval_"):
        raw = data.replace("pn_pony_interval_", "", 1)
        try:
            cid_str, minutes_str = raw.rsplit("_", 1)
            cid, minutes = int(cid_str), int(minutes_str)
        except (TypeError, ValueError):
            return ("❌ بازه نامعتبر است.", [[_cb("⚪ 🔙 بازگشت", "pn_pony_main")]])
        if minutes not in (5, 10, 15, 20):
            return ("❌ بازه نامعتبر است.", [[_cb("⚪ 🔙 بازگشت", f"pn_pony_ctrl_{cid}")]])
        cfg = get_pony_cfg(user_id, cid)
        cfg["interval_mins"] = minutes
        pony_config[(int(user_id), cid)] = cfg
        pm_panel_chat[int(user_id)] = cid
        schedule_save_runtime()
        return await _pm_build_pony_ctrl(user_id, cid)
    if data.startswith("pn_pony_t_"):
        cid = int(data.replace("pn_pony_t_", ""))
        cfg = pony_config.get((int(user_id), cid), {"collect": False, "upgrade": False})
        if cfg.get("collect"):
            cfg["collect"] = False
            stop_pony_task(user_id, cid)
            pony_state.pop((int(user_id), cid), None)
        else:
            cfg["collect"] = True
            pony_state[(int(user_id), cid)] = {"phase": "learning", "samples": [],
                "learned": None, "start_ts": time.time(), "last_fill": 0}
            start_pony_task(user_id, cid)
        pony_config[(int(user_id), cid)] = cfg
        schedule_save_runtime()
        return await _pm_build_pony_ctrl(user_id, cid)
    if data.startswith("pn_up_t_"):
        cid = int(data.replace("pn_up_t_", ""))
        cfg = pony_config.get((int(user_id), cid), {"collect": False, "upgrade": False})
        cfg["upgrade"] = not cfg.get("upgrade", False)
        if cfg["upgrade"] and not cfg.get("collect"):
            cfg["collect"] = True
            pony_state.setdefault((int(user_id), cid),
                {"phase": "learning", "samples": [], "learned": None,
                 "start_ts": time.time(), "last_fill": 0})
            start_pony_task(user_id, cid)
        pony_config[(int(user_id), cid)] = cfg
        schedule_save_runtime()
        return await _pm_build_pony_panel(user_id, cid)
    if data.startswith("pn_dgn_panel_"):
        cid = int(data.replace("pn_dgn_panel_", ""))
        return await _pm_build_dungeon_panel(user_id, cid)
    if data.startswith("pn_dgn_t_"):
        cid = int(data.replace("pn_dgn_t_", ""))
        cfg = dungeon_config.get((int(user_id), cid),
            {"enabled": False, "current_idx": 0, "working_idx": -1,
             "test_mode": False, "mode": "auto", "manual_idx": 0})
        if cfg.get("enabled"):
            cfg["enabled"] = False
            stop_dungeon_task(user_id, cid)
        else:
            cfg["enabled"] = True; cfg["test_mode"] = True
            cfg["current_idx"] = 0; cfg["working_idx"] = -1
            start_dungeon_task(user_id, cid)
        dungeon_config[(int(user_id), cid)] = cfg
        schedule_save_runtime()
        return await _pm_build_dungeon_panel(user_id, cid)
    if data.startswith("pn_dgn_mode_auto_"):
        cid = int(data.replace("pn_dgn_mode_auto_", ""))
        cfg = dungeon_config.get((int(user_id), cid), {})
        cfg["mode"] = "auto"; cfg["test_mode"] = True
        cfg["current_idx"] = 0; cfg["working_idx"] = -1
        dungeon_config[(int(user_id), cid)] = cfg
        schedule_save_runtime()
        return await _pm_build_dungeon_panel(user_id, cid)
    if data.startswith("pn_dgn_mode_manual_"):
        cid = int(data.replace("pn_dgn_mode_manual_", ""))
        cfg = dungeon_config.get((int(user_id), cid), {})
        cfg["mode"] = "manual"; cfg["manual_idx"] = cfg.get("manual_idx", 0)
        dungeon_config[(int(user_id), cid)] = cfg
        schedule_save_runtime()
        return await _pm_build_dungeon_panel(user_id, cid)
    if data.startswith("pn_dgn_pick_"):
        rest = data.replace("pn_dgn_pick_", ""); parts = rest.rsplit("_", 1)
        cid = int(parts[0]); idx = int(parts[1])
        cfg = dungeon_config.get((int(user_id), cid), {})
        cfg["mode"] = "manual"; cfg["manual_idx"] = idx
        dungeon_config[(int(user_id), cid)] = cfg
        schedule_save_runtime()
        return await _pm_build_dungeon_panel(user_id, cid)
    if data.startswith("pn_dgn_test_"):
        cid = int(data.replace("pn_dgn_test_", ""))
        stop_dungeon_task(user_id, cid)
        cfg = dungeon_config.get((int(user_id), cid), {})
        cfg["enabled"] = True; cfg["current_idx"] = 0
        cfg["working_idx"] = -1; cfg["test_mode"] = True
        dungeon_config[(int(user_id), cid)] = cfg
        start_dungeon_task(user_id, cid)
        schedule_save_runtime()
        return await _pm_build_dungeon_panel(user_id, cid)
    if data == "pn_pew_art_panel": return await _pm_build_pew_art_panel(user_id)
    if data == "pn_pew_toggle":
        cur = pew_art_config.get(int(user_id), {}).get("enabled", False)
        pew_art_config[int(user_id)] = {"enabled": not cur}
        schedule_save_runtime()
        return await _pm_build_pew_art_panel(user_id)
    if data == "pn_pew_reset":
        pew_art_stats[int(user_id)] = {"grabbed": 0, "missed": 0}
        schedule_save_runtime()
        return await _pm_build_pew_art_panel(user_id)
    if data == "pn_pewring_master_panel": return await _pm_build_pewring_master_panel(user_id)
    if data.startswith("pn_pewring_page_"):
        pg = int(data.replace("pn_pewring_page_", "") or 0)
        return await _pm_build_pewring_master_panel(user_id, pg)
    if data.startswith("pn_pewring_sel_"):
        cid = int(data.replace("pn_pewring_sel_", ""))
        return await _pm_build_pewring_panel(user_id, cid)
    if data.startswith("pn_pewring_t_"):
        cid = int(data.replace("pn_pewring_t_", ""))
        key = (int(user_id), cid)
        cfg = pew_ring_config.get(key, {"enabled": False})
        if cfg.get("enabled"):
            cfg["enabled"] = False
            stop_pew_ring_task(user_id, cid)
        else:
            cfg["enabled"] = True
            start_pew_ring_task(user_id, cid)
        pew_ring_config[key] = cfg
        schedule_save_runtime()
        return await _pm_build_pewring_panel(user_id, cid)
    if data == "pn_pewring_master_on":
        for g in await _pm_get_user_groups(user_id, 200):
            key = (int(user_id), int(g["id"]))
            cfg = pew_ring_config.get(key, {"enabled": False})
            if not cfg.get("enabled"):
                cfg["enabled"] = True
                pew_ring_config[key] = cfg
                start_pew_ring_task(user_id, int(g["id"]))
        schedule_save_runtime()
        return await _pm_build_pewring_master_panel(user_id)
    if data == "pn_pewring_master_off":
        stop_all_pew_ring_for_user(user_id)
        return await _pm_build_pewring_master_panel(user_id)
    if data == "pn_dog_master_panel": return await _pm_build_dog_master_panel(user_id)
    if data.startswith("pn_dog_page_"):
        pg = int(data.replace("pn_dog_page_", "") or 0)
        return await _pm_build_dog_master_panel(user_id, pg)
    if data.startswith("pn_dog_sel_"):
        cid = int(data.replace("pn_dog_sel_", ""))
        return await _pm_build_pew_dog_view(user_id, cid)
    if data.startswith("pn_dog_t_"):
        cid = int(data.replace("pn_dog_t_", ""))
        key = (int(user_id), cid)
        cfg = pew_dog_config.get(key, {"enabled": False})
        if cfg.get("enabled"):
            cfg["enabled"] = False
            stop_pew_dog_task(user_id, cid)
        else:
            cfg["enabled"] = True
            start_pew_dog_task(user_id, cid)
        pew_dog_config[key] = cfg
        schedule_save_runtime()
        return await _pm_build_pew_dog_view(user_id, cid)
    if data == "pn_dog_master_on":
        for g in await _pm_get_user_groups(user_id, 200):
            key = (int(user_id), int(g["id"]))
            cfg = pew_dog_config.get(key, {"enabled": False})
            if not cfg.get("enabled"):
                cfg["enabled"] = True
                pew_dog_config[key] = cfg
                start_pew_dog_task(user_id, int(g["id"]))
        schedule_save_runtime()
        return await _pm_build_dog_master_panel(user_id)
    if data == "pn_dog_master_off":
        stop_all_pew_dog_for_user(user_id)
        return await _pm_build_dog_master_panel(user_id)
    if data == "pn_ghunt_panel":
        return await _pm_build_group_hunt_panel(user_id)
    if data == "pn_ghunt_create":
        if user_id in pew_user_group:
            return ("❌ شما از قبل در یک گروه هستید.", [[_cb("⚪ 🔙", "pn_ghunt_panel")]])
        code = str(random.randint(10000, 99999))
        pew_hunt_groups[code] = {"owner": user_id, "members": [user_id], "disabled_users": []}
        pew_user_group[user_id] = code
        schedule_save_runtime()
        return await _pm_build_group_hunt_panel(user_id)
    if data == "pn_ghunt_join":
        if user_id in pew_user_group:
            return ("❌ شما از قبل در یک گروه هستید.", [[_cb("⚪ 🔙", "pn_ghunt_panel")]])
        pm_banner_states[user_id] = {"mode": "ghunt_join_code", "msg_id": event.query.msg_id, "prompt_chat_id": event.chat_id}
        return ("🔗 ملحق شدن به گروه\n━━━━━━━━━━━━━━━━━\nلطفاً کد گروه را ارسال کنید:", [[_cb("🔴 لغو", "pn_ghunt_panel")]])
    if data == "pn_ghunt_toggle":
        code = pew_user_group.get(user_id)
        if code and code in pew_hunt_groups:
            grp = pew_hunt_groups[code]
            grp.setdefault("disabled_users", [])
            if user_id in grp["disabled_users"]:
                grp["disabled_users"].remove(user_id)
            else:
                grp["disabled_users"].append(user_id)
            schedule_save_runtime()
        return await _pm_build_group_hunt_panel(user_id)
    if data == "pn_ghunt_leave_ask":
        return ("⚠️ آیا از خروج از گروه مطمئن هستید؟", [
            [_cb("✅ بله، خارج شو", "pn_ghunt_leave")],
            [_cb("🔴 لغو", "pn_ghunt_panel")]
        ])
    if data == "pn_ghunt_leave":
        code = pew_user_group.pop(user_id, None)
        if code and code in pew_hunt_groups:
            grp = pew_hunt_groups[code]
            if user_id in grp["members"]:
                grp["members"].remove(user_id)
            if grp.get("owner") == user_id and grp["members"]:
                grp["owner"] = grp["members"][0]
            if not grp["members"]:
                del pew_hunt_groups[code]
        schedule_save_runtime()
        return await _pm_build_group_hunt_panel(user_id)
    if data == "pn_ghunt_status":
        code = pew_user_group.get(user_id)
        if not code: return ("❌ شما در هیچ گروهی نیستید.", [[_cb("🔙 بازگشت", "pn_ghunt_panel")]])
        grp = pew_hunt_groups.get(code)
        if not grp: return ("❌ گروه یافت نشد.", [[_cb("🔙 بازگشت", "pn_ghunt_panel")]])
        
        members = grp.get("members", [])
        disabled = grp.get("disabled_users", [])
        is_owner = (grp.get("owner") == user_id)
        role_txt = "👑 سازنده" if is_owner else "👤 عضو"
        user_active = user_id not in disabled
        st_txt = "🟢 روشن" if user_active else "🔴 خاموش"
        
        online_count = sum(1 for m in members if user_clients.get(m) and user_clients.get(m).is_connected())
        
        text = (
            f"📊 اطلاعات دقیق گروه\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"🔑 کد گروه: <code>{code}</code>\n"
            f"🎭 نقش شما: {role_txt}\n"
            f"📡 وضعیت شما: <b>{st_txt}</b>\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"👥 کل اعضا: {len(members)}\n"
            f"🟢 آنلاین: {online_count}\n"
            f"🔴 آفلاین: {len(members) - online_count}\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"💡 برای سینک شدن، هر دستوری تو گروه بفرستید."
        )
        return text, [[_cb("🔙 بازگشت", "pn_ghunt_panel")]]
    if data == "pn_ghunt_mgmt":
        return await _pm_build_ghunt_mgmt(user_id)
    if data == "pn_ghunt_del_ask":
        return ("⚠️ آیا از منحل کردن کل گروه مطمئن هستید؟", [
            [_cb("✅ بله، منحل کن", "pn_ghunt_del_yes")],
            [_cb("🔴 لغو", "pn_ghunt_mgmt")]
        ])
    if data == "pn_ghunt_del_yes":
        code = pew_user_group.get(user_id)
        if code in pew_hunt_groups:
            for m in pew_hunt_groups[code]["members"]:
                pew_user_group.pop(m, None)
            del pew_hunt_groups[code]
        schedule_save_runtime()
        return ("🔴 گروه با موفقیت منحل شد.", [[_cb("🔙 بازگشت", "pn_ghunt_panel")]])
    if data == "pn_ghunt_kick_list":
        code = pew_user_group.get(user_id)
        grp = pew_hunt_groups.get(code, {})
        kb = []
        for m in grp.get("members", []):
            if m == user_id: continue
            try: nm = await get_plain_name(bot_client, m)
            except: nm = str(m)
            kb.append([_cb(f"❌ {nm}", f"pn_ghunt_kick_{m}")])
        kb.append([_cb("⚪ 🔙", "pn_ghunt_mgmt")])
        return ("🗑 چه کسی را اخراج کنیم؟", kb)
    if data.startswith("pn_ghunt_kick_") and not data.startswith("pn_ghunt_kick_yes_") and data != "pn_ghunt_kick_list":
        target = int(data.split("_")[-1])
        return ("⚠️ آیا از اخراج این کاربر مطمئنید؟", [
            [_cb("✅ بله", f"pn_ghunt_kick_yes_{target}")],
            [_cb("🔴 لغو", "pn_ghunt_mgmt")]
        ])
    if data.startswith("pn_ghunt_kick_yes_"):
        target = int(data.split("_")[-1])
        code = pew_user_group.get(user_id)
        if code in pew_hunt_groups:
            if target in pew_hunt_groups[code]["members"]:
                pew_hunt_groups[code]["members"].remove(target)
            pew_user_group.pop(target, None)
        schedule_save_runtime()
        return ("✅ عضو با موفقیت اخراج شد.", [[_cb("🔙 بازگشت به مدیریت", "pn_ghunt_mgmt")]])
    if data == "pn_ghunt_prom_list":
        code = pew_user_group.get(user_id)
        grp = pew_hunt_groups.get(code, {})
        kb = []
        for m in grp.get("members", []):
            if m == user_id: continue
            try: nm = await get_plain_name(bot_client, m)
            except: nm = str(m)
            kb.append([_cb(f"👑 {nm}", f"pn_ghunt_prom_{m}")])
        kb.append([_cb("⚪ 🔙", "pn_ghunt_mgmt")])
        return ("👑 چه کسی سازنده جدید شود؟", kb)
    if data.startswith("pn_ghunt_prom_") and not data.startswith("pn_ghunt_prom_yes_") and data != "pn_ghunt_prom_list":
        target = int(data.split("_")[-1])
        return ("⚠️ آیا از انتقال سازندگی مطمئنید؟", [
            [_cb("✅ بله", f"pn_ghunt_prom_yes_{target}")],
            [_cb("🔴 لغو", "pn_ghunt_mgmt")]
        ])
    if data.startswith("pn_ghunt_prom_yes_"):
        target = int(data.split("_")[-1])
        code = pew_user_group.get(user_id)
        if code in pew_hunt_groups:
            pew_hunt_groups[code]["owner"] = target
        schedule_save_runtime()
        return ("✅ سازندگی با موفقیت منتقل شد.\n(شما دیگر سازنده نیستید)", [[_cb("🔙 بازگشت", "pn_ghunt_panel")]])
    
    if data == "pn_tgt_panel": return await _pm_build_pew_target_panel(user_id)
    if data == "pn_tgt_add":
        pm_banner_states[user_id] = {"mode": "pew_tgt_add_input", "prompt_chat_id": event.chat_id}
        return ("🎯 افزودن هدف\n━━━━━━━━━━━━━━━━━\n"
                "روی پیام طرف ریپلای کن یا:\n"
                "• <code>@username</code>\n• آیدی عددی\n\n"
                "🔴 لغو: <code>،لغو</code>",
                [[_cb("🔴 لغو", "pn_tgt_panel")]])
    if data == "pn_tgt_yes":
        pm_banner_states.pop(user_id, None)
        return await _pm_build_pew_target_panel(user_id)
    if data == "pn_tgt_no":
        pm_banner_states.pop(user_id, None)
        return await _pm_build_pew_target_panel(user_id)
    if data.startswith("pn_tgt_list_"):
        pg = int(data.replace("pn_tgt_list_", "") or 0)
        return await _pm_build_pew_target_list(user_id, pg)
    if data.startswith("pn_tgt_del_"):
        pg = int(data.replace("pn_tgt_del_", "") or 0)
        return await _pm_build_pew_target_del_list(user_id, pg)
    if data.startswith("pn_tgt_v_"):
        rest = data.replace("pn_tgt_v_", ""); parts = rest.split("_")
        return await _pm_build_pew_target_view(user_id, int(parts[0]), int(parts[1]))
    if data.startswith("pn_tgt_t_"):
        rest = data.replace("pn_tgt_t_", ""); parts = rest.split("_")
        cid = int(parts[0]); tid = int(parts[1])
        key = _pew_target_key(user_id, cid, tid)
        cfg = pew_target_config.get(key)
        if cfg:
            if cfg.get("enabled"):
                cfg["enabled"] = False
                stop_pew_target_task(user_id, cid, tid)
            else:
                cfg["enabled"] = True
                start_pew_target_task(user_id, cid, tid)
            schedule_save_runtime()
        return await _pm_build_pew_target_view(user_id, cid, tid)
    if data.startswith("pn_tgt_del_ask_"):
        rest = data.replace("pn_tgt_del_ask_", ""); parts = rest.split("_")
        return await _pm_build_pew_target_del_confirm(user_id, int(parts[0]), int(parts[1]))
    if data.startswith("pn_tgt_del_yes_"):
        rest = data.replace("pn_tgt_del_yes_", ""); parts = rest.split("_")
        cid = int(parts[0]); tid = int(parts[1])
        key = _pew_target_key(user_id, cid, tid)
        stop_pew_target_task(user_id, cid, tid)
        pew_target_config.pop(key, None); pew_target_state.pop(key, None)
        schedule_save_runtime()
        return await _pm_build_pew_target_list(user_id, 0)
    if data.startswith("pn_tgt_chg_grp_"):
        rest = data.replace("pn_tgt_chg_grp_", ""); parts = rest.split("_")
        return await _pm_build_pew_target_group_picker(user_id, int(parts[1]), 0, int(parts[0]), "change")
    if data.startswith("pn_tgt_chg_page_"):
        rest = data.replace("pn_tgt_chg_page_", ""); parts = rest.split("_")
        return await _pm_build_pew_target_group_picker(user_id, int(parts[1]), int(parts[2]), int(parts[0]), "change")
    if data.startswith("pn_tgt_chg_set_"):
        rest = data.replace("pn_tgt_chg_set_", ""); parts = rest.split("_")
        old_cid = int(parts[0]); tid = int(parts[1]); new_cid = int(parts[2])
        old_key = _pew_target_key(user_id, old_cid, tid)
        old_cfg = pew_target_config.pop(old_key, None)
        old_state = pew_target_state.pop(old_key, None)
        stop_pew_target_task(user_id, old_cid, tid)
        if old_cfg:
            new_key = _pew_target_key(user_id, new_cid, tid)
            pew_target_config[new_key] = old_cfg
            if old_state: pew_target_state[new_key] = old_state
            if old_cfg.get("enabled"):
                start_pew_target_task(user_id, new_cid, tid)
            schedule_save_runtime()
        return await _pm_build_pew_target_list(user_id, 0)
    if data.startswith("pn_tgt_chg_manual_"):
        rest = data.replace("pn_tgt_chg_manual_", ""); parts = rest.split("_")
        old_cid = int(parts[0]); tid = int(parts[1])
        pm_banner_states[user_id] = {"mode": "tgt_manual_input",
            "mode_sub": "change", "target_id": tid, "old_cid": old_cid, "prompt_chat_id": event.chat_id}
        return ("🔀 گروه جدید رو بفرست:\n• لینک\n• @username\n• آیدی عددی",
                [[_cb("🔴 لغو", "pn_tgt_panel")]])
    if data.startswith("pn_tgt_grp_"):
        rest = data.replace("pn_tgt_grp_", ""); parts = rest.split("_")
        tid = int(parts[0]); cid = int(parts[1])
        key = _pew_target_key(user_id, cid, tid)
        if key in pew_target_config:
            return await _pm_build_pew_target_list(user_id, 0)
        pew_target_config[key] = {"enabled": True, "name": str(tid), "username": ""}
        pew_target_state[key] = {"phase": "shooting", "last_target_msg_id": 0}
        start_pew_target_task(user_id, cid, tid)
        schedule_save_runtime()
        return await _pm_build_pew_target_list(user_id, 0)
    if data.startswith("pn_tgt_grp_page_"):
        rest = data.replace("pn_tgt_grp_page_", ""); parts = rest.split("_")
        return await _pm_build_pew_target_group_picker(user_id, int(parts[0]), int(parts[1]), None, "add")
    if data.startswith("pn_tgt_manual_"):
        tid = int(data.replace("pn_tgt_manual_", ""))
        pm_banner_states[user_id] = {"mode": "tgt_manual_input",
            "mode_sub": "add", "target_id": tid, "info": {"id": tid, "display": str(tid)}, "prompt_chat_id": event.chat_id}
        return ("🔗 لینک/آیدی گروه رو بفرست:\n• <code>@username</code>\n• آیدی عددی\n• لینک t.me",
                [[_cb("🔴 لغو", "pn_tgt_panel")]])
    return None

# ═══════════════════════════════════════════════════════
# Helper bot
# ═══════════════════════════════════════════════════════
async def start_helper_bot():
    global helper_bot
    if not HELPER_BOT_TOKEN:
        log_error("⚠️ HELPER_BOT_TOKEN خالیه"); return
    session_path = str(SESSION_DIR / "helper_bot_session")
    try:
        helper_bot = TelegramClient(session_path, API_ID, API_HASH)
        await helper_bot.start(bot_token=HELPER_BOT_TOKEN)
        helper_bot.add_event_handler(helper_inline_handler, events.InlineQuery)
        helper_bot.add_event_handler(helper_callback_handler, events.CallbackQuery)
        me = await helper_bot.get_me()
        log_error(f"✅ helper_bot started: @{me.username} ({me.id})")
        print(f"✅ Helper bot: @{me.username}")
    except Exception as e:
        log_error(f"start_helper_bot: {_translate_bot_errors(e)}")
        print(f"❌ Helper bot failed: {_translate_bot_errors(e)}")

async def helper_inline_handler(event):
    try:
        query_text = (event.query.query or "").strip()
        if query_text != INLINE_SECRET:
            try: await event.answer([], cache_time=0)
            except: pass
            return
        user_id = event.sender_id
        if not is_user_active(user_id):
            try:
                await event.answer([], cache_time=0,
                    switch_pm="❌ اول لاگین کن: /login",
                    switch_pm_param="login")
            except Exception:
                try: await event.answer([], cache_time=0)
                except: pass
            return
        if not is_user_allowed(user_id):
            try: await event.answer([], cache_time=0)
            except: pass
            return

        text, kb = await _pm_build_main(user_id)
        kb = _bind_panel_callbacks(kb, user_id)
        markup = _kb_to_inline_markup(kb)

        try:
            from telethon.extensions import html as _thtml
            msg_text, entities = _thtml.parse(text)
        except Exception:
            msg_text, entities = text, []

        from telethon.tl.types import (
            InputBotInlineResult, InputBotInlineMessageText,
            InputBotInlineMessageMediaAuto, InputMediaUploadedPhoto,
        )

        banner = get_user_display_banner(user_id)

        # ─── با عکس ───
        # نکته: InputBotInlineMessageMediaAuto در تلگرام پارامتر media نمی‌گیرد
        # (مدیای نتیجهٔ اینلاین باید URL باشد، نه فایل محلی). قبلاً همین‌جا
        # همیشه TypeError می‌خورد و بنر پنل هیچ‌وقت نمایش داده نمی‌شد.
        # حالا فقط اگر نسخهٔ کتابخانه پشتیبانی کند تلاش می‌کنیم، وگرنه بی‌صدا
        # پنل متنی فرستاده می‌شود (بدون خطای تکراری در لاگ).
        send_msg = InputBotInlineMessageText(
            message=msg_text,
            entities=entities or None,
            reply_markup=markup)
        if banner and os.path.exists(banner) and _INLINE_MEDIA_SUPPORTED:
            try:
                uploaded = await helper_bot.upload_file(banner)
                _media_kw = {"media": InputMediaUploadedPhoto(
                    file=uploaded, ttl_seconds=None)}
                send_msg = InputBotInlineMessageMediaAuto(
                    message=msg_text,
                    entities=entities or None,
                    reply_markup=markup,
                    **_media_kw,
                )
                log_error(f"📸 inline with photo for {user_id}")
            except Exception as ue:
                log_error(f"inline banner fallback to text: {_translate_bot_errors(ue)}")
                send_msg = InputBotInlineMessageText(
                    message=msg_text,
                    entities=entities or None,
                    reply_markup=markup)

        result = InputBotInlineResult(
            id="1", type="article",
            title="🎛 پنل سلف‌بات",
            description="مدیریت کامل",
            send_message=send_msg)

        try:
            await event.answer([result], cache_time=0, private=True)
            log_error(f"✅ inline answered for {user_id} (photo={'yes' if banner else 'no'})")
        except Exception as e:
            log_error(f"inline answer: {_translate_bot_errors(e)}")
    except Exception as e:
        log_error(f"helper_inline_handler: {_translate_bot_errors(e)}")



async def helper_callback_handler(event):
    try:
        data = event.data.decode() if event.data else ""
    except Exception:
        return
    actor_id = event.query.user_id
    if not data.startswith("pc_"):
        # Older or unbound panel buttons are rejected rather than risking cross-account actions.
        try:
            if data.startswith("pn_"):
                await event.answer("⚠️ این دکمه منقضی است؛ پنل را دوباره باز کن.", alert=True)
            else:
                await event.answer()
        except: pass
        return
    binding = panel_callback_tokens.get(data)
    if not binding or time.time() - binding[2] > 8 * 3600:
        panel_callback_tokens.pop(data, None)
        try: await event.answer("⚠️ این دکمه منقضی است؛ پنل را دوباره باز کن.", alert=True)
        except: pass
        return
    user_id, data, _created_at = binding
    if int(actor_id) != int(user_id) and not is_grp_owner(actor_id):
        try: await event.answer("❌ این پنل فقط برای صاحبش قابل استفاده است.", alert=True)
        except: pass
        return
    if data.startswith(("pn_owner", "pn_users_", "pn_user_", "pn_ban_",
                        "pn_unban_", "pn_addmgr_", "pn_rmmgr_", "pn_rmsess_",
                        "pn_reload_", "pn_managers", "pn_gb_", "pn_broadcast",
                        "pn_media_remove_", "pn_media_grant_", "pn_access_")):
        if not is_grp_owner(actor_id):
            try: await event.answer("❌ دسترسی", alert=True)
            except: pass
            return
    if not is_user_active(user_id):
        try: await event.answer("❌ این حساب فعال نیست.", alert=True)
        except: pass
        return
    if not is_user_allowed(user_id):
        try: await event.answer("🔒 دسترسی این حساب توسط مالک قفل شده است.", alert=True)
        except: pass
        return
    state_before = repr(pm_banner_states.get(user_id))
    try:
        result = await _dispatch_pn(event, user_id, data, actor_id=actor_id)
    except Exception as e:
        log_error(f"_dispatch_pn {user_id}/{data}: {_translate_bot_errors(e)}")
        try: await event.answer(f"❌ {_translate_bot_errors(e)}", alert=True)
        except: pass
        return
    state_after = pm_banner_states.get(user_id)
    if state_after is not None and repr(state_after) != state_before:
        if int(actor_id) != int(user_id):
            state_after["panel_actor_id"] = int(actor_id)
        else:
            state_after.pop("panel_actor_id", None)
    if result is None:
        try: await event.answer()
        except: pass
        return
    file_path = None
    if isinstance(result, tuple) and len(result) == 3:
        text, kb, file_path = result
    elif isinstance(result, tuple) and len(result) == 2:
        text, kb = result
    else:
        try: await event.answer()
        except: pass
        return
    kb = _bind_panel_callbacks(kb, user_id)
    try: imid = event.query.msg_id
    except: imid = None
    # Inline callbacks carry no normal peer; some Telethon versions expose
    # their message id as an int, so check the query kind as well as the id.
    is_inline_msg = _is_inline_id(imid) or getattr(event.query, "peer", None) is None

    # Inline panel messages are edited only through the helper bot. Never fall back
    # to sending a duplicate into Saved Messages or the current chat.
    try:
        if is_inline_msg:
            ok = await _try_inline_edit_global(imid, text, kb)
            if ok:
                log_error(f"✅ inline edited: {imid}")
                try: await event.answer()
                except: pass
            else:
                try: await event.answer("❌ پنل به‌روزرسانی نشد؛ دوباره پنل را باز کن.", alert=True)
                except: pass
            return

        cl = user_clients.get(int(user_id))
        if not cl or not cl.is_connected():
            cl = await ensure_user_client(user_id)
        kwargs = {"buttons": kb, "parse_mode": "html"}
        if file_path:
            if os.path.exists(file_path): kwargs["file"] = file_path
            else: text += "\n\n<i>⚠️ عکس پیدا نشد</i>"

        # Non-inline panels are edited in place; no delete-and-send duplicate fallback.
        if cl:
            try:
                await cl.edit_message(event.chat_id, imid, text, **kwargs)
                log_error(f"✅ edited same msg: {imid}")
                try: await event.answer()
                except: pass
                return
            except Exception as ee:
                log_error(f"edit same failed: {_translate_bot_errors(ee)}")

        try:
            await event.edit(text, **kwargs)
            try: await event.answer()
            except: pass
            return
        except Exception as e:
            log_error(f"callback edit failed: {_translate_bot_errors(e)}")
        # تلاش دوم با متن ساده (بدون HTML) تا پنل به‌هرحال آپدیت شود
        try:
            plain = html_lib.unescape(re.sub(r"<[^>]+>", "", str(text or "")))
            await event.edit(plain, buttons=kb)
            try: await event.answer()
            except: pass
            return
        except Exception as e:
            log_error(f"callback plain edit failed: {_translate_bot_errors(e)}")
        try: await event.answer("❌ نتوانستم همین پیام پنل را به‌روزرسانی کنم؛ پنل را دوباره باز کن.", alert=True)
        except: pass
    except Exception as e:
        log_error(f"helper_callback_handler update: {_translate_bot_errors(e)}")
        try: await event.answer(f"❌ {_translate_bot_errors(e)}", alert=True)
        except: pass

# ═══════════════════════════════════════════════════════
# Bot client handlers
# ═══════════════════════════════════════════════════════
async def _bot_start_handler(event):
    try: await start_cmd(event)
    except Exception as e: log_error(f"start_cmd: {_translate_bot_errors(e)}")

async def _bot_login_handler(event):
    try: await login_cmd(event)
    except Exception as e: log_error(f"login_cmd: {_translate_bot_errors(e)}")

async def _bot_login_input_handler(event):
    try: await handle_login_input(event)
    except Exception as e: log_error(f"login_input: {_translate_bot_errors(e)}")

async def _bot_login_callback_handler(event):
    try: await login_callback_handler(event)
    except Exception as e: log_error(f"login_cb: {_translate_bot_errors(e)}")

# ═══════════════════════════════════════════════════════
# main()
# ═══════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════
# ⚡ Transfer Panels - Modular & Safe
# ═══════════════════════════════════════════════════════



# ═══════════════════════════════════════════════════════
# ⚡ Transfer System - Final Clean & UI Fixed
# ═══════════════════════════════════════════════════════

async def _pm_build_transfer_menu(uid):
    transfer_on = uid in transfer_configs and transfer_configs[uid].get("enabled")
    text = "💸 <b>پنل انتقال</b>\n━━━━━━━━━━━━━━━━━\n👇 گزینه‌ای را انتخاب کنید:"
    kb = [
        [_cb(f"{'🟢' if transfer_on else '🔴'} 💰 انتقال پول", "pn_transfer_info")],
        [_cb("📦 انتقال مواد", "pn_transfer_materials")],
        [_cb("🎁 انتقال کالا/آیتم", "pn_transfer_items")],
        [_cb("🔙 بازگشت به کاردینال", "pn_cardinal_panel")]
    ]
    return text, kb

async def _pm_build_materials_panel_v2(uid):
    cfg = transfer_materials_config.get(uid, {"enabled": False, "rules": []})
    is_on = cfg.get("enabled", False)
    text = f"📦 <b>پنل انتقال مواد اولیه</b>\n━━━━━━━━━━━━━━━━━\n📊 وضعیت: <b>{'🟢 روشن' if is_on else '🔴 خاموش'}</b>\n🔢 قوانین: <b>{len(cfg.get('rules', []))}</b>"
    kb = [
        [_cb(f"{'🔴 خاموش کن' if is_on else '🟢 روشن کن'}", "pn_mat_toggle")],
        [_cb("➕ افزودن انتقال", "pn_mat_add"), _cb("📋 لیست انتقال‌ها", "pn_mat_list")],
        [_cb("🔙 بازگشت", "pn_transfer_menu")]
    ]
    return text, kb

async def _pm_build_items_panel(uid):
    cfg = transfer_items_config.get(uid, {"enabled": False, "rules": []})
    is_on = cfg.get("enabled", False)
    text = f"🎁 <b>پنل انتقال کالا/آیتم</b>\n━━━━━━━━━━━━━━━━━\n📊 وضعیت: <b>{'🟢 روشن' if is_on else '🔴 خاموش'}</b>\n🔢 قوانین: <b>{len(cfg.get('rules', []))}</b>"
    kb = [
        [_cb(f"{'🔴 خاموش کن' if is_on else '🟢 روشن کن'}", "pn_item_toggle")],
        [_cb("➕ افزودن انتقال", "pn_item_add"), _cb("📋 لیست انتقال‌ها", "pn_item_list")],
        [_cb("🔙 بازگشت", "pn_transfer_menu")]
    ]
    return text, kb

async def execute_material_transfers(user_id, force_check=False):
    cfg = transfer_materials_config.get(user_id, {})
    if not cfg.get("enabled") or not cfg.get("rules"): return False
    client = user_clients.get(int(user_id))
    if not client or not client.is_connected():
        client = await ensure_user_client(user_id)
        if not client: return False

    def clean_text(t):
        t = normalize_digits(_normalize_persian(t))
        t = t.replace('ي', 'ی').replace('ك', 'ک')
        return t.replace(" ", "").replace("\u200c", "")

    async def get_latest_msg_id():
        try:
            msgs = await client.get_messages(GAME_BOT_ID, limit=1)
            return msgs[0].id if msgs else 0
        except: return 0

    async def wait_for_new_reply(predicate, timeout=30, since_id=0):
        start_t = time.time()
        while time.time() - start_t < timeout:
            try:
                msgs = await client.get_messages(GAME_BOT_ID, limit=5)
                for m in msgs:
                    if not m.out and m.id > since_id:
                        text = m.raw_text or ""
                        if predicate(text): return text
            except: pass
            await asyncio.sleep(2)
        return None

    inv_text = None
    for attempt in range(3):
        sid = await get_latest_msg_id()
        await _send_game_cmd(user_id, "🎒 موجودی من", tag="mat_trans")
        inv_text = await wait_for_new_reply(is_inventory_message, timeout=30, since_id=sid)
        if inv_text: break
        if attempt < 2: await asyncio.sleep(30)
    if not inv_text: return False
        
    local_inv = {}
    for line in inv_text.split('\n'):
        m = re.search(r'^(\d+)\.\s*(.+?)\s*(?:-\s*)?\((\d+)\s*عدد\)', line)
        if m: local_inv[clean_text(m.group(2))] = int(m.group(3))
            
    grouped_rules = {}
    for rule in cfg["rules"]:
        if not rule.get("enabled", True): continue
        mat_clean = clean_text(rule.get("material", ""))
        grouped_rules.setdefault(mat_clean, []).append(rule)
    turn_state = cfg.setdefault("turn_state", {})

    for mat_clean, rules_list in grouped_rules.items():
        total_avail = local_inv.get(mat_clean, 0)
        if total_avail <= 0: continue

        start_idx = turn_state.get(mat_clean, 0) % len(rules_list)
        sorted_rules = rules_list[start_idx:] + rules_list[:start_idx]

        for i, rule in enumerate(sorted_rules):
            if total_avail <= 0: break
            target_cid = rule.get("cid")
            req_qty = int(rule.get("quantity", 0))
            remaining = len(sorted_rules) - i
            amount = max(1, total_avail // remaining) if req_qty == 0 else min(req_qty, total_avail)
            if amount <= 0: continue

            sid1 = await get_latest_msg_id()
            await _send_game_cmd(user_id, "📤 انتقال مواد اولیه", tag="mat_trans")
            resp1 = await wait_for_new_reply(lambda t: "شمارهردیف" in clean_text(t), timeout=30, since_id=sid1)
            
            row_idx = None
            if resp1:
                for line in resp1.split('\n'):
                    if mat_clean in clean_text(line):
                        m = re.search(r'^(\d+)\.', line.strip())
                        if m: row_idx = m.group(1); break
            
            if not row_idx: continue

            sid2 = await get_latest_msg_id()
            await _send_game_cmd(user_id, str(row_idx), tag="mat_trans")
            await wait_for_new_reply(lambda t: "تعدادموردنظر" in clean_text(t), timeout=30, since_id=sid2)
            
            sid3 = await get_latest_msg_id()
            await _send_game_cmd(user_id, str(amount), tag="mat_trans")
            await wait_for_new_reply(lambda t: "شناسهکاردینال" in clean_text(t) or "C_ID" in t, timeout=30, since_id=sid3)
                
            sid4 = await get_latest_msg_id()
            await _send_game_cmd(user_id, str(target_cid), tag="mat_trans")
            final_resp = await wait_for_new_reply(lambda t: "باموفقیت" in clean_text(t) or "ظرفیت" in t or "یافت" in t, timeout=20, since_id=sid4)
            
            if final_resp:
                res_text = _normalize_persian(final_resp)
                if "با موفقیت" in res_text or "رسید" in res_text:
                    total_avail -= amount
                    turn_state[mat_clean] = (start_idx + 1) % len(rules_list)
                    schedule_save_runtime()
                elif "ظرفیت" in res_text:
                    # ظرفیت پر است: اول برگشت به منو، بعد دونه دونه
                    await _send_game_cmd(user_id, "🔙 برگشت به منو", tag="mat_trans")
                    await asyncio.sleep(2)
                    
                    sent_count = 0
                    for _ in range(amount):
                        sid_r = await get_latest_msg_id()
                        await _send_game_cmd(user_id, "📤 انتقال مواد اولیه", tag="mat_trans")
                        r1 = await wait_for_new_reply(lambda t: "شمارهردیف" in clean_text(t), timeout=20, since_id=sid_r)
                        if not r1: break
                        
                        r_idx = None
                        for line in r1.split('\n'):
                            if mat_clean in clean_text(line):
                                m = re.search(r'^(\d+)\.', line.strip())
                                if m: r_idx = m.group(1); break
                        if not r_idx: break

                        sid_q = await get_latest_msg_id()
                        await _send_game_cmd(user_id, str(r_idx), tag="mat_trans")
                        await wait_for_new_reply(lambda t: "تعداد" in clean_text(t), timeout=20, since_id=sid_q)
                        
                        sid_a = await get_latest_msg_id()
                        await _send_game_cmd(user_id, "1", tag="mat_trans")
                        await wait_for_new_reply(lambda t: "شناسه" in clean_text(t), timeout=20, since_id=sid_a)
                        
                        sid_c = await get_latest_msg_id()
                        await _send_game_cmd(user_id, str(target_cid), tag="mat_trans")
                        res_1by1 = await wait_for_new_reply(lambda t: "باموفقیت" in clean_text(t) or "ظرفیت" in t, timeout=20, since_id=sid_c)
                        
                        if res_1by1 and ("با موفقیت" in _normalize_persian(res_1by1) or "رسید" in _normalize_persian(res_1by1)):
                            sent_count += 1
                            await _send_game_cmd(user_id, "🔙 برگشت به منو", tag="mat_trans")
                            await asyncio.sleep(1)
                        else:
                            await _send_game_cmd(user_id, "🔙 برگشت به منو", tag="mat_trans")
                            break
                    
                    if sent_count > 0:
                        total_avail -= sent_count
                        turn_state[mat_clean] = (start_idx + 1) % len(rules_list)
                        schedule_save_runtime()
                elif "یافت نشد" in res_text:
                    await _send_game_cmd(user_id, "🔙 برگشت به منو", tag="mat_trans")
    return True

async def execute_item_transfers(user_id, force_check=False):
    cfg = transfer_items_config.get(user_id, {})
    if not cfg.get("enabled") or not cfg.get("rules"): return False
    client = user_clients.get(int(user_id))
    if not client or not client.is_connected():
        client = await ensure_user_client(user_id)
        if not client: return False

    def clean_text(t):
        t = normalize_digits(_normalize_persian(t))
        t = t.replace('ي', 'ی').replace('ك', 'ک')
        return t.replace(" ", "").replace("\u200c", "")

    async def get_latest_msg_id():
        try:
            msgs = await client.get_messages(GAME_BOT_ID, limit=1)
            return msgs[0].id if msgs else 0
        except: return 0

    async def wait_for_new_reply(predicate, timeout=30, since_id=0):
        start_t = time.time()
        while time.time() - start_t < timeout:
            try:
                msgs = await client.get_messages(GAME_BOT_ID, limit=5)
                for m in msgs:
                    if not m.out and m.id > since_id:
                        text = m.raw_text or ""
                        if predicate(text): return text
            except: pass
            await asyncio.sleep(2)
        return None

    inv_text = None
    for attempt in range(3):
        sid = await get_latest_msg_id()
        await _send_game_cmd(user_id, "🎒 موجودی من", tag="item_trans")
        inv_text = await wait_for_new_reply(is_inventory_message, timeout=30, since_id=sid)
        if inv_text: break
        if attempt < 2: await asyncio.sleep(30)
    if not inv_text: return False
        
    local_inv = {}
    for line in inv_text.split('\n'):
        m = re.search(r'^(\d+)\.\s*(.+?)\s*(?:-\s*)?\((\d+)\s*عدد\)', line)
        if m: local_inv[clean_text(m.group(2))] = int(m.group(3))
            
    grouped_rules = {}
    for rule in cfg["rules"]:
        if not rule.get("enabled", True): continue
        mat_clean = clean_text(rule.get("material", ""))
        grouped_rules.setdefault(mat_clean, []).append(rule)
    turn_state = cfg.setdefault("turn_state", {})

    for mat_clean, rules_list in grouped_rules.items():
        total_avail = local_inv.get(mat_clean, 0)
        if total_avail <= 0: continue

        start_idx = turn_state.get(mat_clean, 0) % len(rules_list)
        sorted_rules = rules_list[start_idx:] + rules_list[:start_idx]

        for i, rule in enumerate(sorted_rules):
            if total_avail <= 0: break
            target_cid = rule.get("cid")
            req_qty = int(rule.get("quantity", 0))
            remaining = len(sorted_rules) - i
            amount = max(1, total_avail // remaining) if req_qty == 0 else min(req_qty, total_avail)
            if amount <= 0: continue

            sid1 = await get_latest_msg_id()
            await _send_game_cmd(user_id, "📦 انتقال کالا", tag="item_trans")
            resp1 = await wait_for_new_reply(lambda t: "شمارهردیف" in clean_text(t), timeout=30, since_id=sid1)
            
            row_idx = None
            if resp1:
                for line in resp1.split('\n'):
                    if mat_clean in clean_text(line):
                        m = re.search(r'^(\d+)\.', line.strip())
                        if m: row_idx = m.group(1); break
            
            if not row_idx: continue

            sid2 = await get_latest_msg_id()
            await _send_game_cmd(user_id, str(row_idx), tag="item_trans")
            await wait_for_new_reply(lambda t: "تعدادموردنظر" in clean_text(t), timeout=30, since_id=sid2)
            
            sid3 = await get_latest_msg_id()
            await _send_game_cmd(user_id, str(amount), tag="item_trans")
            await wait_for_new_reply(lambda t: "شناسهکاردینال" in clean_text(t) or "C_ID" in t, timeout=30, since_id=sid3)
                
            sid4 = await get_latest_msg_id()
            await _send_game_cmd(user_id, str(target_cid), tag="item_trans")
            final_resp = await wait_for_new_reply(lambda t: "باموفقیت" in clean_text(t) or "ظرفیت" in t or "یافت" in t, timeout=20, since_id=sid4)
            
            if final_resp:
                res_text = _normalize_persian(final_resp)
                if "با موفقیت" in res_text or "رسید" in res_text:
                    total_avail -= amount
                    turn_state[mat_clean] = (start_idx + 1) % len(rules_list)
                    schedule_save_runtime()
                elif "ظرفیت" in res_text:
                    # ظرفیت پر است: اول برگشت به منو، بعد دونه دونه
                    await _send_game_cmd(user_id, "🔙 برگشت به منو", tag="item_trans")
                    await asyncio.sleep(2)
                    
                    sent_count = 0
                    for _ in range(amount):
                        sid_r = await get_latest_msg_id()
                        await _send_game_cmd(user_id, "📦 انتقال کالا", tag="item_trans")
                        r1 = await wait_for_new_reply(lambda t: "شمارهردیف" in clean_text(t), timeout=20, since_id=sid_r)
                        if not r1: break
                        
                        r_idx = None
                        for line in r1.split('\n'):
                            if mat_clean in clean_text(line):
                                m = re.search(r'^(\d+)\.', line.strip())
                                if m: r_idx = m.group(1); break
                        if not r_idx: break

                        sid_q = await get_latest_msg_id()
                        await _send_game_cmd(user_id, str(r_idx), tag="item_trans")
                        await wait_for_new_reply(lambda t: "تعداد" in clean_text(t), timeout=20, since_id=sid_q)
                        
                        sid_a = await get_latest_msg_id()
                        await _send_game_cmd(user_id, "1", tag="item_trans")
                        await wait_for_new_reply(lambda t: "شناسه" in clean_text(t), timeout=20, since_id=sid_a)
                        
                        sid_c = await get_latest_msg_id()
                        await _send_game_cmd(user_id, str(target_cid), tag="item_trans")
                        res_1by1 = await wait_for_new_reply(lambda t: "باموفقیت" in clean_text(t) or "ظرفیت" in t, timeout=20, since_id=sid_c)
                        
                        if res_1by1 and ("با موفقیت" in _normalize_persian(res_1by1) or "رسید" in _normalize_persian(res_1by1)):
                            sent_count += 1
                            await _send_game_cmd(user_id, "🔙 برگشت به منو", tag="item_trans")
                            await asyncio.sleep(1)
                        else:
                            await _send_game_cmd(user_id, "🔙 برگشت به منو", tag="item_trans")
                            break
                    
                    if sent_count > 0:
                        total_avail -= sent_count
                        turn_state[mat_clean] = (start_idx + 1) % len(rules_list)
                        schedule_save_runtime()
                elif "یافت نشد" in res_text:
                    await _send_game_cmd(user_id, "🔙 برگشت به منو", tag="item_trans")
    return True

async def _dispatch_transfer_pn(event, user_id, data):
    # --- منوی اصلی انتقال ---
    if data == "pn_transfer_menu": return await _pm_build_transfer_menu(user_id)
    if data == "pn_transfer_materials": return await _pm_build_materials_panel_v2(user_id)
    if data == "pn_transfer_items": return await _pm_build_items_panel(user_id)
    if data == "pn_transfer_info": return await _pm_build_transfer(user_id)
    if data == "pn_transfer_toggle":
        cfg = transfer_configs.setdefault(user_id, {"enabled": False, "c_id": "", "desired": 0})
        cfg["enabled"] = not cfg.get("enabled", False)
        schedule_save_runtime()
        return await _pm_build_transfer(user_id)

    # --- مواد اولیه ---
    if data == "pn_mat_toggle":
        cfg = transfer_materials_config.setdefault(user_id, {"enabled": False, "rules": []})
        cfg["enabled"] = not cfg.get("enabled", False)
        schedule_save_runtime()
        if cfg["enabled"]:
            _ensure_transfer_scheduler(user_id, "material")
            if not sell_mode_users.get(user_id, {}).get("enabled"):
                async def _run_imm_mat(uid):
                    async with get_user_lock(uid):
                        if not sell_mode_users.get(uid, {}).get("enabled"):
                            await execute_material_transfers(uid)
                _spawn(_run_imm_mat(user_id))
        return await _pm_build_materials_panel_v2(user_id)
    
    if data == "pn_mat_add":
        q = getattr(event, 'query', None)
        msg_id = getattr(q, 'msg_id', None) if q else getattr(event, 'message_id', None)
        pm_banner_states[user_id] = {"mode": "mat_add_cid", "prompt_id": msg_id}
        return ("📦 افزودن قانون\nلطفاً آیدی (C_ID) مقصد را بفرستید:\n(۱ تا ۵ رقمی)", [[_cb("🔴 لغو", "pn_transfer_materials")]])
    
    if data in ("pn_mat_list", "pn_mat_refresh"):
        cfg = transfer_materials_config.get(user_id, {})
        rules = cfg.get("rules", [])
        if not rules: return ("📋 لیست خالی است.", [[_cb("🔙 بازگشت", "pn_transfer_materials")]])
        kb = []
        for i, r in enumerate(rules):
            icon = "🟢" if r.get("enabled", True) else "🔴"
            kb.append([_cb(f"{icon} {r.get('material','')}", f"pn_mat_manage_{i}")])
        kb.append([_cb("🔙 بازگشت", "pn_transfer_materials")])
        return ("📋 لیست مواد:\nروی هر مورد بزنید تا مدیریت کنید:", kb)
        
    if data.startswith("pn_mat_manage_"):
        idx = int(data.replace("pn_mat_manage_", ""))
        cfg = transfer_materials_config.get(user_id, {})
        r = cfg.get("rules", [])[idx]
        is_on = r.get("enabled", True)
        text = f"📦 <b>{r['material']}</b>\nوضعیت: {'🟢 روشن' if is_on else '🔴 خاموش'}\nگیرنده: {r['cid']}\nتعداد: {r['quantity'] if r['quantity']>0 else 'همه'}"
        kb = [
            [_cb(f"{'🔴 خاموش کن' if is_on else '🟢 روشن کن'}", f"pn_mat_toggle_{idx}")],
            [_cb("✏️ گیرنده", f"pn_mat_edit_cid_{idx}"), _cb("✏️ اسم", f"pn_mat_edit_name_{idx}"), _cb("✏️ تعداد", f"pn_mat_edit_qty_{idx}")],
            [_cb("🗑 حذف", f"pn_mat_del_ask_{idx}")],
            [_cb("🔙 بازگشت", "pn_mat_list")]
        ]
        return text, kb

    if data.startswith("pn_mat_toggle_"):
        idx = int(data.replace("pn_mat_toggle_", ""))
        cfg = transfer_materials_config.get(user_id, {})
        rules = cfg.get("rules", [])
        if 0 <= idx < len(rules):
            rules[idx]["enabled"] = not rules[idx].get("enabled", True)
            schedule_save_runtime()
        return await _dispatch_transfer_pn(event, user_id, f"pn_mat_manage_{idx}")
        
    if data.startswith("pn_mat_del_ask_"):
        idx = int(data.replace("pn_mat_del_ask_", ""))
        cfg = transfer_materials_config.get(user_id, {})
        rules = cfg.get("rules", [])
        if idx < 0 or idx >= len(rules): return await _pm_build_materials_panel_v2(user_id)
        return (f"⚠️ حذف؟\n📦 {rules[idx]['material']}", [[_cb("✅ بله", f"pn_mat_del_yes_{idx}")], [_cb("❌ خیر", f"pn_mat_manage_{idx}")]])
        
    if data.startswith("pn_mat_del_yes_"):
        idx = int(data.replace("pn_mat_del_yes_", ""))
        cfg = transfer_materials_config.get(user_id, {})
        if "rules" in cfg and idx < len(cfg["rules"]):
            cfg["rules"].pop(idx)
            schedule_save_runtime()
        return ("✅ حذف شد.", [[_cb("🔙 بازگشت", "pn_mat_list")]])
        
    if data.startswith("pn_mat_edit_cid_"):
        pm_banner_states[user_id] = {"mode": "mat_edit_cid", "rule_idx": int(data.replace("pn_mat_edit_cid_", ""))}
        return ("✏️ گیرنده جدید (۱ تا ۵ رقمی):", [[_cb("🔴 لغو", "pn_mat_list")]])
    if data.startswith("pn_mat_edit_name_"):
        pm_banner_states[user_id] = {"mode": "mat_edit_name", "rule_idx": int(data.replace("pn_mat_edit_name_", ""))}
        return ("✏️ اسم جدید:", [[_cb("🔴 لغو", "pn_mat_list")]])
    if data.startswith("pn_mat_edit_qty_"):
        pm_banner_states[user_id] = {"mode": "mat_edit_qty", "rule_idx": int(data.replace("pn_mat_edit_qty_", ""))}
        return ("✏️ تعداد جدید (0=همه):", [[_cb("🔴 لغو", "pn_mat_list")]])

    # --- کالا ---
    if data == "pn_item_toggle":
        cfg = transfer_items_config.setdefault(user_id, {"enabled": False, "rules": []})
        cfg["enabled"] = not cfg.get("enabled", False)
        schedule_save_runtime()
        if cfg["enabled"]:
            _ensure_transfer_scheduler(user_id, "item")
            if not sell_mode_users.get(user_id, {}).get("enabled"):
                async def _run_imm_item(uid):
                    async with get_user_lock(uid):
                        if not sell_mode_users.get(uid, {}).get("enabled"):
                            await execute_item_transfers(uid)
                _spawn(_run_imm_item(user_id))
        return await _pm_build_items_panel(user_id)
    
    if data == "pn_item_add":
        q = getattr(event, 'query', None)
        msg_id = getattr(q, 'msg_id', None) if q else getattr(event, 'message_id', None)
        pm_banner_states[user_id] = {"mode": "item_add_cid", "prompt_id": msg_id}
        return ("🎁 افزودن قانون\nلطفاً آیدی (C_ID) مقصد را بفرستید:\n(۱ تا ۵ رقمی)", [[_cb("🔴 لغو", "pn_transfer_items")]])
    
    if data in ("pn_item_list", "pn_item_refresh"):
        cfg = transfer_items_config.get(user_id, {})
        rules = cfg.get("rules", [])
        if not rules: return ("📋 لیست خالی است.", [[_cb("🔙 بازگشت", "pn_transfer_items")]])
        kb = []
        for i, r in enumerate(rules):
            icon = "🟢" if r.get("enabled", True) else "🔴"
            kb.append([_cb(f"{icon} {r.get('material','')}", f"pn_item_manage_{i}")])
        kb.append([_cb("🔙 بازگشت", "pn_transfer_items")])
        return ("📋 لیست کالاها:\nروی هر مورد بزنید تا مدیریت کنید:", kb)

    if data.startswith("pn_item_manage_"):
        idx = int(data.replace("pn_item_manage_", ""))
        cfg = transfer_items_config.get(user_id, {})
        r = cfg.get("rules", [])[idx]
        is_on = r.get("enabled", True)
        text = f"🎁 <b>{r['material']}</b>\nوضعیت: {'🟢 روشن' if is_on else '🔴 خاموش'}\nگیرنده: {r['cid']}\nتعداد: {r['quantity'] if r['quantity']>0 else 'همه'}"
        kb = [
            [_cb(f"{'🔴 خاموش کن' if is_on else '🟢 روشن کن'}", f"pn_item_toggle_{idx}")],
            [_cb("✏️ گیرنده", f"pn_item_edit_cid_{idx}"), _cb("✏️ اسم", f"pn_item_edit_name_{idx}"), _cb("✏️ تعداد", f"pn_item_edit_qty_{idx}")],
            [_cb("🗑 حذف", f"pn_item_del_ask_{idx}")],
            [_cb("🔙 بازگشت", "pn_item_list")]
        ]
        return text, kb
        
    if data.startswith("pn_item_toggle_"):
        idx = int(data.replace("pn_item_toggle_", ""))
        cfg = transfer_items_config.get(user_id, {})
        rules = cfg.get("rules", [])
        if 0 <= idx < len(rules):
            rules[idx]["enabled"] = not rules[idx].get("enabled", True)
            schedule_save_runtime()
        return await _dispatch_transfer_pn(event, user_id, f"pn_item_manage_{idx}")
        
    if data.startswith("pn_item_del_ask_"):
        idx = int(data.replace("pn_item_del_ask_", ""))
        cfg = transfer_items_config.get(user_id, {})
        rules = cfg.get("rules", [])
        if idx < 0 or idx >= len(rules): return await _pm_build_items_panel(user_id)
        return (f"⚠️ حذف؟\n🎁 {rules[idx]['material']}", [[_cb("✅ بله", f"pn_item_del_yes_{idx}")], [_cb("❌ خیر", f"pn_item_manage_{idx}")]])
        
    if data.startswith("pn_item_del_yes_"):
        idx = int(data.replace("pn_item_del_yes_", ""))
        cfg = transfer_items_config.get(user_id, {})
        if "rules" in cfg and idx < len(cfg["rules"]):
            cfg["rules"].pop(idx)
            schedule_save_runtime()
        return ("✅ حذف شد.", [[_cb("🔙 بازگشت", "pn_item_list")]])
        
    if data.startswith("pn_item_edit_cid_"):
        pm_banner_states[user_id] = {"mode": "item_edit_cid", "rule_idx": int(data.replace("pn_item_edit_cid_", ""))}
        return ("✏️ گیرنده جدید (۱ تا ۵ رقمی):", [[_cb("🔴 لغو", "pn_item_list")]])
    if data.startswith("pn_item_edit_name_"):
        pm_banner_states[user_id] = {"mode": "item_edit_name", "rule_idx": int(data.replace("pn_item_edit_name_", ""))}
        return ("✏️ اسم جدید:", [[_cb("🔴 لغو", "pn_item_list")]])
    if data.startswith("pn_item_edit_qty_"):
        pm_banner_states[user_id] = {"mode": "item_edit_qty", "rule_idx": int(data.replace("pn_item_edit_qty_", ""))}
        return ("✏️ تعداد جدید (0=همه):", [[_cb("🔴 لغو", "pn_item_list")]])

    return None


def extract_floor_generic(text):
    if not text: return None
    t = _normalize_persian(normalize_digits(text))
    m = re.search(r'موقعیت\s*فعلی[:\s]*طبقه\s*(\d+)', t)
    if m: return int(m.group(1))
    m = re.search(r'بیرون\s*از\s*شهر\s*-\s*طبقه\s*(\d+)', t)
    if m: return int(m.group(1))
    m = re.search(r'شهر\s*طبقه\s*(\d+)', t)
    if m: return int(m.group(1))
    m = re.search(r'طبقه\s*فعلی[:\s]*(\d+)', t)
    if m: return int(m.group(1))
    return None

async def main():
    global bot_client
    print("🚀 starting...")
    load_runtime()
    _load_floor_test_from_db()
    print(f"📦 users: {len(users_db['users'])}")
    await start_helper_bot()
    bot_session = str(SESSION_DIR / "bot_main")
    bot_client = TelegramClient(bot_session, API_ID, API_HASH)
    await bot_client.start(bot_token=BOT_TOKEN)
    me = await bot_client.get_me()
    globals()["BOT_SELF_ID"] = me.id
    log_error(f"✅ bot_client started: @{me.username}")
    print(f"✅ Bot: @{me.username}")
    bot_client.add_event_handler(_bot_start_handler,
        events.NewMessage(pattern=r'^/start$'))
    bot_client.add_event_handler(_bot_login_handler,
        events.NewMessage(pattern=r'^/login$'))
    bot_client.add_event_handler(_bot_login_input_handler,
        events.NewMessage(func=lambda e: e.sender_id in login_states
                          and not (e.raw_text or "").startswith("/")))
    bot_client.add_event_handler(_bot_login_callback_handler,
        events.CallbackQuery(data=b"relogin_start"))
    bot_client.add_event_handler(_bot_login_callback_handler,
        events.CallbackQuery(data=lambda d: d and d.decode().startswith(
            ("num_", "done", "clear", "resend_"))))
    for uid_s, info in list(users_db["users"].items()):
        try:
            uid = int(uid_s)
            if info.get("banned"): continue
            if info.get("active"):
                c = await create_user_client(uid)
                if c: print(f"  🔌 revived {uid}")
        except Exception as e:
            log_error(f"revive {uid_s}: {_translate_bot_errors(e)}")
    _spawn(_restart_runtime_tasks())
    _spawn(notify_users_on_startup())
    print("✅ ready.")
    await bot_client.run_until_disconnected()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 stopped.")
    except Exception as e:
        log_error(f"main crash: {_translate_bot_errors(e)}")
        print(f"❌ {_translate_bot_errors(e)}")
