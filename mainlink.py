import os
import re
import json
from flask import Flask, request, jsonify
import requests

###############################
# Telegram Anti‑Link & Anti‑BOT Guard
#
# Files expected (Render):
#   - mainlink.py  (this file)
#   - Procfile     ->  web: python mainlink.py
#   - requirements.txt -> flask\nrequests
#
# ENV VARS required on Render:
#   TELEGRAM_BOT_TOKEN   -> your bot token from @BotFather
#   WEBHOOK_URL          -> public https URL to this app (e.g., from Render)
#   # optional:
#   WEBHOOK_SECRET_TOKEN -> if you want to validate Telegram webhook source
###############################

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
API = f"https://api.telegram.org/bot{TOKEN}"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip().rstrip("/")
SECRET = os.getenv("WEBHOOK_SECRET_TOKEN")  # Optional but recommended

app = Flask(__name__)

# ====== Messages (HTML parse mode) ======
START_MSG = (
    "<b>✨ Anti‑Link & Anti‑BOT Guard ✨</b>\n"
    "<b>This bot remove link send by members</b>\n"
    "<b>Allow links send by admins</b>\n"
    "<b>Delete all BOT spam</b>\n\n"
    "<i>Make me admin with delete permissions for best results.</i>"
)

WARN_LINK_MSG = (
    "⚠️ <b>Warning</b>\n"
    "Hidden and non-hidden <b>Links</b> are not allowed in this group."
)

WARN_BOT_MSG = (
    "⛔ <b>BOT spam are not allowed</b>"
)

# ====== Utility helpers ======

def tg_api(method: str, params: dict = None, files: dict = None):
    """Call Telegram Bot API. Returns JSON or None on error."""
    url = f"{API}/{method}"
    headers = {}
    if SECRET:
        headers["X-Telegram-Bot-Api-Secret-Token"] = SECRET
    try:
        if files:
            resp = requests.post(url, data=params or {}, files=files, headers=headers, timeout=10)
        else:
            resp = requests.post(url, json=params or {}, headers=headers, timeout=10)
        if resp.ok:
            return resp.json()
    except Exception:
        pass
    return None


def send_message(chat_id, text, reply_to_message_id=None, disable_preview=True):
    params = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": bool(disable_preview),
    }
    if reply_to_message_id:
        params["reply_to_message_id"] = reply_to_message_id
        params["allow_sending_without_reply"] = True
    return tg_api("sendMessage", params)


def delete_message(chat_id, message_id):
    return tg_api("deleteMessage", {"chat_id": chat_id, "message_id": message_id})


def get_member_status(chat_id, user_id) -> str:
    """Return member status string: 'creator' | 'administrator' | 'member' | 'left' | 'kicked' | 'restricted' | 'unknown'"""
    res = tg_api("getChatMember", {"chat_id": chat_id, "user_id": user_id})
    try:
        return res["result"]["status"]
    except Exception:
        return "unknown"


# ====== Content checks ======
# URL recognizer: entities + regex + inline button URLs
TLD_RE = r"(?:com|net|org|io|co|in|xyz|me|ly|gg|ru|uk|app|dev|ai|info|shop|site|live|click|link|party|top|biz|tv|us|ca|de|fr|nl|it|es|au|pk|bd|lk)"
URL_RE = re.compile(
    rf"(?i)(?:https?://|www\.|t\.me/|telegram\.me/)[^\s]+|\b[\w-]+\.{TLD_RE}\b"
)
BOT_RE = re.compile(r"(?i)bot")  # any occurrence of the letters b-o-t together (case-insensitive)


def _has_url_entities(msg: dict) -> bool:
    for e in msg.get("entities", []) + msg.get("caption_entities", []):
        if e.get("type") in ("url", "text_link"):
            return True
    return False


def _has_inline_button_url(msg: dict) -> bool:
    kb = (msg.get("reply_markup") or {}).get("inline_keyboard") or []
    for row in kb:
        for btn in row:
            if isinstance(btn, dict) and btn.get("url"):
                return True
    return False


def _is_forwarded(msg: dict) -> bool:
    # New style (forward_origin) and legacy (forward_from, forward_from_chat)
    if msg.get("forward_origin"):
        return True
    if msg.get("forward_from") or msg.get("forward_from_chat"):
        return True
    return False


def contains_link_like(msg: dict) -> bool:
    text = msg.get("text") or msg.get("caption") or ""
    if not text and not (_has_inline_button_url(msg)) and not _has_url_entities(msg):
        # No text/caption and no inline buttons or entities
        return False
    if _has_url_entities(msg):
        return True
    if URL_RE.search(text or ""):
        return True
    if _has_inline_button_url(msg):
        return True
    # Treat forwarded content as potentially promotional (often includes button links)
    if _is_forwarded(msg):
        return True
    return False


def contains_bot_sequence(msg: dict) -> bool:
    text = msg.get("text") or msg.get("caption") or ""
    return bool(BOT_RE.search(text))


def is_from_admin(chat_id: int, msg: dict) -> bool:
    user = msg.get("from") or {}
    uid = user.get("id")
    if not uid:
        # Channel posts don't include a user; treat as admin/originator
        return True
    status = get_member_status(chat_id, uid)
    return status in ("administrator", "creator")


# ====== Core moderation logic ======

def handle_update(update: dict):
    # We only act on message updates in groups/supergroups
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        # Ignore channel_post and other update types for this simple bot
        return

    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    chat_type = chat.get("type")
    if chat_type not in ("group", "supergroup"):
        # For private chats, just respond to /start
        text = (msg.get("text") or "").strip()
        if text.startswith("/start"):
            send_message(chat_id, START_MSG)
        return

    # In groups/supergroups
    text = (msg.get("text") or msg.get("caption") or "").strip()
    message_id = msg.get("message_id")

    # /start in group -> show info
    if text.startswith("/start"):
        send_message(chat_id, START_MSG)
        return

    # Skip admins/owner
    if is_from_admin(chat_id, msg):
        return

    # Evaluate violations (member only)
    link_like = contains_link_like(msg)
    bot_like = contains_bot_sequence(msg)

    if link_like or bot_like:
        # Try to delete the offending message
        delete_message(chat_id, message_id)

        # Craft a small mention of the user (safe even if first_name has HTML)
        user = msg.get("from") or {}
        first = (user.get("first_name") or "User").replace("<", "&lt;").replace(">", "&gt;")
        mention = f"<a href=\"tg://user?id={user.get('id', 0)}\">{first}</a>"

        if link_like:
            send_message(chat_id, f"{mention} {WARN_LINK_MSG}")
        elif bot_like:
            send_message(chat_id, f"{mention} {WARN_BOT_MSG}")


# ====== Flask routes ======
@app.get("/")
def index():
    return jsonify({
        "ok": True,
        "message": "Telegram anti-link bot is running.",
        "setwebhook": "/setwebhook",
        "health": "/health",
    })


@app.get("/health")
def health():
    return "ok", 200


@app.get("/setwebhook")
def set_webhook():
    if not TOKEN or not WEBHOOK_URL:
        return ("Missing TELEGRAM_BOT_TOKEN or WEBHOOK_URL env var", 400)

    params = {
        "url": f"{WEBHOOK_URL}/webhook",
        # Request only what we need
        "allowed_updates": json.dumps(["message", "edited_message"]),
    }
    if SECRET:
        params["secret_token"] = SECRET

    res = tg_api("setWebhook", params)
    return jsonify(res or {"ok": False})


@app.post("/webhook")
def webhook():
    # Optional source validation via secret token
    if SECRET:
        hdr = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if hdr != SECRET:
            return "forbidden", 403

    try:
        update = request.get_json(force=True, silent=True) or {}
        handle_update(update)
    except Exception:
        # Never fail Telegram delivery because of our errors
        pass
    return "OK", 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))  # Render gives PORT automatically
    app.run(host="0.0.0.0", port=port)

