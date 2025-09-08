import re
import json
from flask import Flask, request, jsonify
import requests


###############################
# Telegram Anti‑Link & Anti‑BOT Guard
#
# Files expected (Render):
# - mainlink.py (this file)
# - Procfile -> web: python mainlink.py
# - requirements.txt -> flask\nrequests
#
# ENV VARS required on Render:
# TELEGRAM_BOT_TOKEN -> your bot token from @BotFather
# WEBHOOK_URL -> public https URL to this app (e.g., from Render)
# # optional:
# WEBHOOK_SECRET_TOKEN -> if you want to validate Telegram webhook source
###############################


TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
API = f"https://api.telegram.org/bot{TOKEN}"
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "").strip().rstrip("/")
SECRET = os.getenv("WEBHOOK_SECRET_TOKEN") # Optional but recommended


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
app.run(host="0.0.0.0", port=port) # debug off by default