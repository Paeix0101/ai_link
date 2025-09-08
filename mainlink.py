from flask import Flask, request
import os
import requests

app = Flask(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise SystemExit("Missing BOT_TOKEN environment variable")

# Use WEBHOOK_SECRET (cleaner than BOT_TOKEN as path)
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET", "ailink1")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"

LINKGUARD_MSG = (
    "<b>LinkGuard — Active ✨</b>\n\n"
    "<i>• This bot removes links sent by members</i>\n"
    "<i>• Admins / Owner are allowed to send links</i>\n"
    "<i>• Removes bot spam automatically</i>\n\n"
    "⚠️ <i>Make this bot an admin (can_delete_messages) so it can protect the group.</i>"
)

def send_message(chat_id: int, text: str, parse_mode: str = "HTML"):
    """Send a message via Telegram sendMessage."""
    payload = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    try:
        requests.post(f"{API_URL}/sendMessage", json=payload, timeout=10)
    except Exception:
        pass  # ignore network errors

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

    if text and text.strip().lower().startswith("/start") and chat_id:
        send_message(chat_id, LINKGUARD_MSG, parse_mode="HTML")

    return "ok"

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
