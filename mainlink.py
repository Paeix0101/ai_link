import os
import re
import requests
from flask import Flask, request

app = Flask(__name__)

# --- CONFIG ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # set this in Render / Env
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "super-secret-path")  # set this in Render / Env
OWNER_ID = int(os.environ.get("OWNER_ID", "8141547148"))  # change to your telegram id if needed

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN environment variable is required")

API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

# --- Pretty messages (HTML formatting) ---
WELCOME_TEXT = (
    "<b>✨ LinkGuard — Active ✨</b>\n\n"
    "<b>• This bot removes links sent by members</b>\n"
    "<i>• Admins / Owner are allowed to send links</i>\n"
    "<b>• Removes bot spam automatically</b>\n\n"
    "⚠️ <i>Make this bot an admin (can_delete_messages) so it can protect the group.</i>"
)

LINK_WARNING = (
    "<b>🚨 Warning — Links not allowed</b>\n\n"
    "Hidden and non-hidden links are not allowed in this group.\n\n"
    "Please contact an admin if you believe this was a mistake."
)

SPAM_WARNING = (
    "<b>🚨 Warning — Bot Spam</b>\n\n"
    "BOT spam (repeating letters / patterns) are not allowed in this group.\n\n"
    "Please behave or contact an admin."
)

# --- Helper functions ---
def send_message(chat_id, text, parse_mode="HTML", reply_to_message_id=None):
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_to_message_id:
        payload["reply_to_message_id"] = reply_to_message_id
    try:
        requests.post(f"{API_URL}/sendMessage", json=payload, timeout=10)
    except Exception as e:
        print("send_message error:", e)

def delete_message(chat_id, message_id):
    try:
        requests.post(f"{API_URL}/deleteMessage", json={"chat_id": chat_id, "message_id": message_id}, timeout=10)
    except Exception as e:
        print("delete_message error:", e)

def get_chat_member(chat_id, user_id):
    try:
        r = requests.get(f"{API_URL}/getChatMember", params={"chat_id": chat_id, "user_id": user_id}, timeout=10).json()
        return r.get("result")
    except Exception as e:
        print("get_chat_member error:", e)
        return None

def is_admin(chat_id, user_id):
    member = get_chat_member(chat_id, user_id)
    if not member:
        return False
    return member.get("status") in ("administrator", "creator")

# get bot id at startup
def _get_bot_id():
    try:
        r = requests.get(f"{API_URL}/getMe", timeout=10).json()
        return r.get("result", {}).get("id")
    except Exception as e:
        print("getMe error:", e)
        return None

BOT_ID = _get_bot_id()

def is_bot_admin(chat_id):
    if not BOT_ID:
        return False
    return is_admin(chat_id, BOT_ID)

# --- Detection logic ---
def message_contains_link(msg):
    # Entities (text/caption)
    for ent in msg.get("entities", []) + msg.get("caption_entities", []):
        if ent.get("type") in ("url", "text_link"):
            return True

    # Inline keyboard with url (rare in user-sent, but check)
    reply_markup = msg.get("reply_markup")
    if reply_markup:
        inline_kb = reply_markup.get("inline_keyboard", [])
        for row in inline_kb:
            for button in row:
                if button.get("url"):
                    return True

    # Raw textual patterns (.com, http, t.me etc.)
    text = (msg.get("text") or msg.get("caption") or "")
    if re.search(r"(https?://|t\.me/|telegram\.me/|\.\w{2,4}\b)", text, flags=re.I):
        return True

    return False

def message_is_forwarded_channel_video(msg):
    # If forwarded from a chat (channel) and contains media (video/document/photo/animation)
    if msg.get("forward_from_chat"):
        if any(k in msg for k in ("video", "animation", "document", "photo", "video_note")):
            return True
    return False

def has_triple_letter_spam(msg_text):
    if not msg_text:
        return False
    s = msg_text.lower()
    # any letter repeated 3 times consecutively (aaa / bbb / Aaa etc.)
    return bool(re.search(r"([a-z])\1\1", s))

# --- Webhook endpoint ---
@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    data = request.get_json(force=True, silent=True)
    if not data:
        return "ok"

    # Prefer 'message' or 'edited_message'
    msg = data.get("message") or data.get("edited_message")
    if not msg:
        return "ok"

    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    chat_type = chat.get("type")
    user = msg.get("from", {})
    user_id = user.get("id")
    text = msg.get("text") or msg.get("caption") or ""
    message_id = msg.get("message_id")

    # Private start command -> decorated welcome
    if chat_type == "private" and text and text.strip() == "/start":
        send_message(chat_id, WELCOME_TEXT)
        return "ok"

    # Only enforce rules inside groups / supergroups
    if chat_type in ("group", "supergroup"):
        # allow admins and owner to post anything
        if is_admin(chat_id, user_id) or user_id == OWNER_ID:
            return "ok"

        # bot must be admin to be able to delete messages
        if not is_bot_admin(chat_id):
            # do nothing (can't delete) — you may optionally notify owner to grant admin
            print("bot is not admin in", chat_id)
            return "ok"

        # 1) Link checks (visible + hidden (text_link) + inline keyboard urls)
        if message_contains_link(msg) or message_is_forwarded_channel_video(msg):
            # delete and warn
            try:
                delete_message(chat_id, message_id)
            except Exception as e:
                print("Failed to delete link message:", e)
            send_message(chat_id, LINK_WARNING)
            return "ok"

        # 2) Triple-letter bot-spam check
        if has_triple_letter_spam(text):
            try:
                delete_message(chat_id, message_id)
            except Exception as e:
                print("Failed to delete spam message:", e)
            send_message(chat_id, SPAM_WARNING)
            return "ok"

    return "ok"


# --- Run server ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"[INFO] LinkGuard running on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port)
