# [telegram_bot_resetbio.py]

from flask import Flask, request
import requests
import sqlite3
import os
import time

app = Flask(__name__)
BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
BOT_ID = int(requests.get(f"{API_URL}/getMe").json()["result"]["id"])

DB_FILE = "data.db"
WARNING_EXPIRY_SECONDS = 12 * 60 * 60
WELCOME_TEXT = (
    "This bot will delete message of bio link members\n"
    "COMMANDS :-\n"
    "/start - send this command to see all features and command details\n"
    "/mutebio - send this command for mute members have bio link after 3 warnings\n"
    "/unmutebio - send this command to end mutebio command\n"
    "/banbio - send this command for ban members have bio link after 3 warnings\n"
    "/unbanbio - send this command to end banbio command\n"
    "/resetbio all - reset warnings and punishment for all members.\n"
    "/resetbio ( reply to message , user name , user id ) - use this command for remove message for particular member"
)

# Database setup and helper functions omitted here for brevity
# ... (keep your DB functions, warnings logic, permission logic, etc.)

# ---------- WEBHOOK ----------
@app.route(f"/webhook/{WEBHOOK_SECRET}", methods=["POST"])
def webhook():
    data = request.get_json()
    if "message" in data:
        msg = data["message"]
        chat = msg["chat"]
        chat_id = chat["id"]
        chat_type = chat["type"]
        user = msg["from"]
        user_id = user["id"]
        message_id = msg["message_id"]
        text = msg.get("text", "")

        if user.get("is_bot"):
            return "ok"

        # Handle /resetbio command with reply, username, or user_id
        if text.startswith("/resetbio") and is_admin(chat_id, user_id):
            parts = text.split()
            target_id = None

            if len(parts) > 1 and parts[1].lower() == "all":
                reset_all_warnings(chat_id)
                send_message(chat_id, "✅ All warnings and punishments have been reset.")
                return "ok"

            if "reply_to_message" in msg:
                target_id = msg["reply_to_message"]["from"]["id"]

            elif len(parts) > 1:
                input_user = parts[1]
                try:
                    target_id = int(input_user)
                except ValueError:
                    uname = input_user.lstrip("@")
                    try:
                        r = requests.get(f"{API_URL}/getChatMember?chat_id={chat_id}&user_id=@{uname}").json()
                        if r.get("ok"):
                            target_id = r["result"]["user"]["id"]
                    except Exception as e:
                        print("getChatMember error:", e)

            if target_id:
                reset_warning(target_id, chat_id)
                send_message(chat_id, f"✅ Warnings and punishments reset for user ID {target_id}")
            else:
                send_message(chat_id, "❗ Could not find the user to reset warnings.")

        # Keep the rest of your bot logic (start command, mutebio, bans, message scan, etc.)

    return "ok"

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)



