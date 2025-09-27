from flask import Flask, request
import os
import requests
import re
import threading
import time

app = Flask(__name__)

# ---------- Config ----------
BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("❌ Missing BOT_TOKEN environment variable")

WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "ailink1")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# ✅ Your deployed app base URL
BASE_URL = "https://ai-link-tvxz.onrender.com"
WEBHOOK_URL = f"{BASE_URL}/webhook/{WEBHOOK_SECRET}"

# Owner Telegram ID
OWNER_ID = 8405313334

# ---------- Messages ----------
LINKGUARD_MSG = (
    "<b>🔗Anti-link-spam-bot </b>\n\n"
    "<i>🚫 Remove inline - button links</i>"
    "<i>🔒This bot removes all types of links sent by members</i>\n"
    "<i>🛡️Admins / Owner are allowed to send links</i>\n"
    "<i>🤖 Removes bot spam automatically</i>\n\n"
    "⚠️ <i>Make this bot an admin (can_delete_messages) so it can protect the group.</i>"
)

ANTILINK_MSG = (
    "<b>Anti Link Spam </b> @Anti_link_spam_bot \n"
    "<i>Hidden and Non hidden links are not allowed in this group </i>\n"
    "<i>Please contact an admin for any queries</i>"
)

ANTIBOT_MSG = (
    "<i>Anti-bot-Spam @Anti_link_spam_bot \n\n Warning\n Bot Spam is not allowed </i>"
)

ANTIFORWARD_MSG = (
    "<i>Anti-link-Spam @Anti_link_spam_bot \n\n</i><i>Foward from BOT / Public Groups / Channel is not allowed \n\n </i><i>Please</i> Hide Sender Name <i>and Foward</i>"
)

# Warning message for inline-button links
INLINE_BUTTON_WARNING = "<i>Anti-link-Spam @Anti_link_spam_bot </i>\n\n<i>Links with / without inline-Button is not allowed in group</i>\n <i>Contact an admin for any queries</i>"

# ---------- Helpers ----------
def send_message(chat_id: int, text: str, parse_mode: str = "HTML"):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    try:
        r = requests.post(f"{API_URL}/sendMessage", json=payload, timeout=10)
        if not r.ok:
            print("❌ Failed to send message:", r.text)
    except Exception as e:
        print("❌ send_message error:", e)

def delete_message(chat_id: int, message_id: int):
    try:
        r = requests.post(
            f"{API_URL}/deleteMessage",
            json={"chat_id": chat_id, "message_id": message_id},
            timeout=10,
        )
        if not r.ok:
            print("❌ Failed to delete message:", r.text)
    except Exception as e:
        print("❌ delete_message error:", e)

def is_admin(chat_id: int, user_id: int) -> bool:
    try:
        resp = requests.get(
            f"{API_URL}/getChatAdministrators",
            params={"chat_id": chat_id},
            timeout=10,
        ).json()
        if resp.get("ok"):
            return any(admin["user"]["id"] == user_id for admin in resp["result"])
    except Exception as e:
        print("❌ is_admin error:", e)
    return False

def contains_link(text: str) -> bool:
    if not text:
        return False
    link_pattern = re.compile(r"(https?://\S+|www\.\S+|\S+\.(com|net|org|info|io|me)|t\.me/\S+)", re.IGNORECASE)
    return bool(link_pattern.search(text))

def contains_bot_link(text: str) -> bool:
    if not text:
        return False
    # Match only mentions/links that end with 'bot' (case-insensitive)
    bot_link_pattern = re.compile(r"(?:@|t\.me/)[A-Za-z0-9_]*bot\b", re.IGNORECASE)
    return bool(bot_link_pattern.search(text))

def is_forbidden_forward(msg: dict) -> bool:
    if "forward_from" in msg:
        if msg["forward_from"].get("is_bot", False):
            return True
    if "forward_from_chat" in msg:
        forward_chat = msg["forward_from_chat"]
        chat_type = forward_chat.get("type", "")
        if chat_type == "channel":
            return True
        if chat_type in ["group", "supergroup"] and forward_chat.get("username"):
            return True
    return False

def has_forbidden_button(msg: dict) -> bool:
    """
    Detect inline keyboard buttons or hidden link entities that contain:
      - http(s) links
      - t.me links
      - usernames/links ending with 'bot'
    Also check button text for visible links or bot-like mentions.
    """
    # 1) Check reply_markup.inline_keyboard if present
    reply_markup = msg.get("reply_markup") or {}
    inline_kb = reply_markup.get("inline_keyboard", [])
    for row in inline_kb:
        for button in row:
            # URL property on button
            url = (button.get("url") or "").strip()
            if url:
                u = url.lower()
                if u.startswith("http://") or u.startswith("https://") or "t.me/" in u or u.endswith("bot"):
                    return True
            # Button text might itself contain a link or mention
            btn_text = (button.get("text") or "")
            if btn_text and (contains_link(btn_text) or contains_bot_link(btn_text)):
                return True

    # 2) Check message entities and caption_entities for text_link (hidden links)
    entities = msg.get("entities", []) or []
    caption_entities = msg.get("caption_entities", []) or []
    for e in entities + caption_entities:
        if e.get("type") == "text_link":
            url = (e.get("url") or "").lower()
            if url and (url.startswith("http://") or url.startswith("https://") or "t.me/" in url or url.endswith("bot")):
                return True
        # sometimes a 'url' entity references raw text; the 'type' might be 'url'
        if e.get("type") == "url":
            # the entity text would be part of message text; we fall back to contains_link check
            return True

    return False

# ---------- Routes ----------
@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    data = request.get_json(force=True, silent=True)
    print("📩 Update:", data)  # Debug log for Render logs
    if not data:
        return "ok"

    msg = data.get("message") or data.get("edited_message")
    if not msg:
        return "ok"

    chat = msg.get("chat", {}) or {}
    chat_id = chat.get("id")
    chat_type = chat.get("type", "")
    user = msg.get("from", {}) or {}
    user_id = user.get("id")
    message_id = msg.get("message_id")
    text = msg.get("text") or msg.get("caption") or ""

    # Send user_id to OWNER if message is in a group
    if chat_type in ["group", "supergroup"] and user_id:
        send_message(OWNER_ID, str(user_id))

    # Send new member IDs to OWNER
    if "new_chat_members" in msg:
        for member in msg["new_chat_members"]:
            send_message(OWNER_ID, str(member.get("id")))

    # /start in private
    if text and text.strip().lower().startswith("/start") and chat_id and chat_type == "private":
        send_message(chat_id, LINKGUARD_MSG, parse_mode="HTML")
        return "ok"

    # Group protections
    if chat_type in ["group", "supergroup"]:
        # Exempt admins and owner from automated deletions
        if not is_admin(chat_id, user_id) and str(user_id) != str(OWNER_ID):
            # 1) Inline-button / hidden link check (priority)
            if has_forbidden_button(msg):
                delete_message(chat_id, message_id)
                send_message(chat_id, INLINE_BUTTON_WARNING, parse_mode="HTML")
                return "ok"

            # 2) Forbidden forwards (bots/channels/public groups)
            if is_forbidden_forward(msg):
                delete_message(chat_id, message_id)
                send_message(chat_id, ANTIFORWARD_MSG, parse_mode="HTML")
                return "ok"

            # 3) Text/caption checks for links or bot mentions
            if text:
                if contains_bot_link(text):
                    delete_message(chat_id, message_id)
                    send_message(chat_id, ANTIBOT_MSG, parse_mode="HTML")
                    return "ok"
                elif contains_link(text):
                    delete_message(chat_id, message_id)
                    send_message(chat_id, ANTILINK_MSG, parse_mode="HTML")
                    return "ok"

    return "ok"

@app.route("/ping")
def ping():
    return "pong", 200

# ---------- Set webhook ----------
def set_webhook():
    try:
        # Remove old webhook first
        requests.get(f"{API_URL}/deleteWebhook", timeout=10)
        r = requests.get(f"{API_URL}/setWebhook", params={"url": WEBHOOK_URL}, timeout=10)
        print("✅ Webhook set:", r.json())
    except Exception as e:
        print("❌ Failed to set webhook:", e)

# ---------- Keep Alive ----------
def keep_alive():
    """Pings the app every 5 minutes to reduce sleeping (works only if pings originate externally)."""
    while True:
        try:
            requests.get(f"{BASE_URL}/ping", timeout=10)
            print("✅ Keep-alive ping sent.")
        except Exception as e:
            print("❌ Keep-alive failed:", e)
        time.sleep(300)  # 5 minutes

# ---------- Main ----------
if __name__ == "__main__":
    set_webhook()

    # Start keep-alive thread
    threading.Thread(target=keep_alive, daemon=True).start()

    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)