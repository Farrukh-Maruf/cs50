import sqlite3
import random
import datetime
import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.error import Forbidden, BadRequest

# Load token
with open("token.txt", "r") as f:
    TOKEN = f.read().strip()

# Quiet logging - no HTTP request noise in terminal
logging.basicConfig(level=logging.WARNING)
logging.getLogger("telegram").setLevel(logging.WARNING)
logging.getLogger("telegram.ext").setLevel(logging.WARNING)
try:
    import httpx
    logging.getLogger("httpx").setLevel(logging.WARNING)
except Exception:
    pass
try:
    import urllib3
    logging.getLogger("urllib3").setLevel(logging.WARNING)
except Exception:
    pass

DB_FILE = "korean_vocab.db"

# Simple keyboard
BTN_ADD = "➕ Add"
BTN_LIST = "📋 List"
BTN_QUIZ = "🧠 Quiz"
BTN_STOP = "⛔ Stop"
MAIN_KEYBOARD = ReplyKeyboardMarkup([[BTN_ADD, BTN_LIST], [BTN_QUIZ, BTN_STOP]], resize_keyboard=True)

# --- DB helpers (very small, reopens connection per call) ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS vocab (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            korean_word TEXT,
            english_meaning TEXT,
            example_sentence TEXT,
            date_added TEXT
        )
        """
    )
    conn.commit()
    conn.close()

def add_word(korean, english, sentence=""):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO vocab (korean_word, english_meaning, example_sentence, date_added) VALUES (?, ?, ?, ?)",
        (korean, english, sentence, str(datetime.date.today())),
    )
    conn.commit()
    conn.close()

def get_recent_words(limit=10):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "SELECT korean_word, english_meaning, example_sentence FROM vocab ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows

def get_random_words(limit=5):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "SELECT korean_word, english_meaning, example_sentence FROM vocab ORDER BY RANDOM() LIMIT ?",
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows

def get_random_word():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT korean_word, english_meaning FROM vocab ORDER BY RANDOM() LIMIT 1")
    row = cur.fetchone()
    conn.close()
    return row

def get_random_words_for_quiz(limit=50):
    """Get random words for quiz (only korean and english, no example sentences)"""
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute(
        "SELECT korean_word, english_meaning FROM vocab ORDER BY RANDOM() LIMIT ?",
        (limit,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows

# --- Safe send helper ---
async def safe_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, **kwargs) -> bool:
    """Send reply_text but catch Forbidden/BadRequest so the bot doesn't crash when blocked.
    
    Returns True if message was sent, False otherwise. This is faster than safe_send.
    """
    try:
        await update.message.reply_text(text, **kwargs)
        return True
    except Forbidden:
        user = update.effective_user.id if update.effective_user else "unknown"
        logging.warning("Forbidden: cannot send message to user %s (maybe blocked).", user)
        try:
            context.user_data.pop("mode", None)
        except Exception:
            pass
        return False
    except BadRequest as e:
        logging.warning("BadRequest when sending message: %s", e)
        return False
    except Exception:
        logging.warning("Unexpected error while sending message")
        return False

# --- BOT COMMANDS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await safe_reply(
        update,
        context,
        "안녕하세요! Korean Vocabulary Bot입니다!\n\n"
        "Use the buttons below to choose a function.\n"
        "You can stay in a mode until you press another button.\n\n"
        "Buttons: Add, List, Quiz, Stop",
        reply_markup=MAIN_KEYBOARD,
    )

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 2:
        await safe_reply(
            update,
            context,
            "❌ Usage: /add 사랑 love [optional example sentence]"
        )
        return

    korean = context.args[0]
    english = context.args[1]
    sentence = " ".join(context.args[2:]) if len(context.args) > 2 else ""

    add_word(korean, english, sentence)
    await safe_reply(update, context, f"✅ Added: {korean} = {english}")

async def list_words(update: Update, context: ContextTypes.DEFAULT_TYPE):
    recent = get_recent_words()
    random_words = get_random_words()

    text = "🆕 Latest 10 Words:\n \n"
    for w in recent:
        sent = f"\n   📘 {w[2]}" if w[2] else ""
        text += f"• {w[0]} → {w[1]}{sent}\n"

    text += "\n🎲 Random 5 Words:\n \n"
    for w in random_words:
        sent = f"\n   📘 {w[2]}" if w[2] else ""
        text += f"• {w[0]} → {w[1]}{sent}\n"

    await safe_reply(update, context, text)

async def _ask_quiz_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Pick a random word, store expected answer in user_data and send question."""
    # Try to get next from preloaded pool
    pool = context.user_data.get('quiz_pool')
    idx = context.user_data.get('quiz_index', 0)
    row = None
    if pool and idx < len(pool):
        row = pool[idx]
        context.user_data['quiz_index'] = idx + 1
    else:
        row = get_random_word()

    if not row:
        await safe_reply(update, context, "No words yet! Use Add to add some first.")
        context.user_data.pop("mode", None)
        return False

    korean, english = row
    if random.choice([True, False]):
        context.user_data["answer"] = english.lower().strip()
        await safe_reply(update, context, f"🧠 What does '{korean}' mean in English?")
    else:
        context.user_data["answer"] = korean.lower().strip()
        await safe_reply(update, context, f"🧠 How do you say '{english}' in Korean?")

    return True

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()

    # Button mode selection
    if text == BTN_ADD:
        context.user_data["mode"] = "add"
        await safe_reply(
            update,
            context,
            "➕ Add mode activated.\nSend words as: korean english [optional example sentence]\n"
            "Example: 사랑 love I love you\n\nPress '⛔ Stop' to exit.",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    if text == BTN_LIST:
        # show lists and keep the mode unchanged
        await list_words(update, context)
        return

    if text == BTN_QUIZ:
        context.user_data["mode"] = "quiz"
        await safe_reply(update, context, "🧠 Quiz mode activated. Send your answers or press '⛔ Stop' to exit.")
        # preload a quiz pool to reduce DB calls
        pool = get_random_words_for_quiz(limit=50)
        context.user_data['quiz_pool'] = pool
        context.user_data['quiz_index'] = 0
        # send first question
        ok = await _ask_quiz_question(update, context)
        if not ok:
            context.user_data.pop("mode", None)
        return

    if text == BTN_STOP:
        context.user_data.pop("mode", None)
        context.user_data.pop("answer", None)
        await safe_reply(update, context, "⛔ Stopped. Returning to menu.", reply_markup=MAIN_KEYBOARD)
        return

    # Not a button press: handle based on current mode
    mode = context.user_data.get("mode")
    if mode == "add":
        # expect: korean english [sentence]
        parts = text.split()
        if len(parts) < 2:
            await safe_reply(update, context, "❌ Usage: korean english [optional example sentence]")
            return
        korean = parts[0]
        english = parts[1]
        sentence = " ".join(parts[2:]) if len(parts) > 2 else ""
        add_word(korean, english, sentence)
        await safe_reply(update, context, f"✅ Added: {korean} = {english}")
        return

    if mode == "quiz":
        user_answer = text.lower().strip()
        correct = context.user_data.get("answer")
        if correct is None:
            await safe_reply(update, context, "No active question. Press 'Quiz' to start.")
            return
        if user_answer == correct:
            await safe_reply(update, context, "✅ Correct!")
        else:
            await safe_reply(update, context, f"❌ Wrong. Correct answer: {correct}")

        # next question
        ok = await _ask_quiz_question(update, context)
        if not ok:
            context.user_data.pop("mode", None)
        return

    # Default fallback when not in a mode
    await safe_reply(
        update,
        context,
        "Press a button to start (Add, List, Quiz, Stop).",
        reply_markup=MAIN_KEYBOARD
    )

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("mode", None)
    context.user_data.pop("answer", None)
    await safe_reply(
        update,
        context,
        "Stopped. Returning to menu...\n\n"
        "Commands:\n"
        "/add 사랑 love I love you — add a word\n"
        "/list — show recent words\n"
        "/quiz — show random quiz question\n"
        "/stop — stop and return to menu",
    )


if __name__ == '__main__':
    init_db()
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler('start', start))
    app.add_handler(CommandHandler('add', add))
    app.add_handler(CommandHandler('list', list_words))
    app.add_handler(CommandHandler('stop', stop))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    print("✅ Bot is running with clean terminal (no HTTP request logs)...")
    app.run_polling()
