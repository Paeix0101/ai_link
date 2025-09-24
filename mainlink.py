from flask import Flask, request
import os
import requests
import re

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("Missing BOT_TOKEN environment variable")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "ailink1")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# Welcome text
LINKGUARD_MSG = (
    "<b>LinkGuard — Active ✨</b>\n\n"
    "<i>• This bot removes links sent by members</i>\n"
    "<i>• Admins / Owner are allowed to send links</i>\n"
    "<i>• Removes bot spam automatically</i>\n\n"
    "⚠️ <i>Make this bot an admin (can_delete_messages) so it can protect the group.</i>"
)

# Anti-link warning
ANTILINK_MSG = (
    "<b>Anti Link Spam </b>\n"
    "<i>Hidden and Non hidden links are not allowed in this group </i>\n"
    "Please contact an admin for any queries"
)

# Anti-bot-link warning
ANTIBOT_MSG = (
    "<i>Anti-bot-Spam \n\n Warning\n Bot Spam is not allowed </i>"
)

# ---------- Helpers ----------
def send_message(chat_id: int, text: str, parse_mode: str = "HTML"):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    try:
        requests.post(f"{API_URL}/sendMessage", json=payload, timeout=10)
    except Exception:
        pass

def delete_message(chat_id: int, message_id: int):
    try:
        requests.post(
            f"{API_URL}/deleteMessage",
            json={"chat_id": chat_id, "message_id": message_id},
            timeout=10,
        )
    except Exception:
        pass

def is_admin(chat_id: int, user_id: int) -> bool:
    try:
        resp = requests.get(
            f"{API_URL}/getChatAdministrators",
            params={"chat_id": chat_id},
            timeout=10,
        ).json()
        if resp.get("ok"):
            return any(admin["user"]["id"] == user_id for admin in resp["result"])
    except Exception:
        return False
    return False

def contains_link(text: str) -> bool:
    # Simple regex to detect links/domains
    link_pattern = re.compile(r"(https?://\S+|www\.\S+|\S+\.(com|net|org|info|io|me)|t\.me/\S+)", re.IGNORECASE)
    return bool(link_pattern.search(text))

def contains_bot_link(text: str) -> bool:
    # Regex to detect bot links like @BotUsername or t.me/BotName
    bot_link_pattern = re.compile(r"(?:@|t\.me/)[A-Za-z0-9_]{5,32}\b", re.IGNORECASE)
    return bool(bot_link_pattern.search(text))

# ---------- Webhook ----------
@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    data = request.get_json(force=True, silent=True)
    if not data:
        return "ok"

    msg = data.get("message") or data.get("edited_message")
    if not msg:
        return "ok"

    text = msg.get("text", "") or ""
    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    chat_type = chat.get("type", "")
    user = msg.get("from", {})
    user_id = user.get("id")
    message_id = msg.get("message_id")

    # ✅ /start in private
    if text and text.strip().lower().startswith("/start") and chat_id and chat_type == "private":
        send_message(chat_id, LINKGUARD_MSG, parse_mode="HTML")
        return "ok"

    # ✅ Anti-link and anti-bot-link protection in groups
    if chat_type in ["group", "supergroup"] and text:
        if not is_admin(chat_id, user_id):
            if contains_link(text):
                delete_message(chat_id, message_id)
                send_message(chat_id, ANTILINK_MSG, parse_mode="HTML")
            elif contains_bot_link(text):
                delete_message(chat_id, message_id)
                send_message(chat_id, ANTIBOT_MSG, parse_mode="HTML")
        return "ok"

    return "ok"

# ---------- Set webhook (only once when starting locally/deploying) ----------
def set_webhook():
    url = f"https://ai-link.onrender.com/webhook/{WEBHOOK_SECRET}"
    try:
        r = requests.get(f"{API_URL}/setWebhook", params={"url": url}, timeout=10)
        print("Webhook set:", r.json())
    except Exception as e:
        print("Failed to set webhook:", e)

if __name__ == "__main__":
    set_webhook()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)