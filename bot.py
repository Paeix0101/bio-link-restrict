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
    "FREE BIO HUNT\n"
    "/start - send this command to see all features and command details\n"
    "/mutebio - send this command for mute members have bio link after 3 warnings\n"
    "/unmutebio - send this command to end mutebio command\n"
    "/banbio - send this command for ban members have bio link after 3 warnings\n"
    "/unbanbio - send this command to end banbio command\n"
    "/resetbio all - reset warnings and punishment for all members.\n"
    "/resetbio ( reply to message , user name ) - use this command for remove message for particular member"
)

# ---------- DATABASE ----------
def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS warnings (
                        user_id INTEGER,
                        chat_id INTEGER,
                        count INTEGER,
                        last_warning_time INTEGER,
                        PRIMARY KEY (user_id, chat_id)
                    )''')
        c.execute('''CREATE TABLE IF NOT EXISTS group_settings (
                        chat_id INTEGER PRIMARY KEY,
                        mutebio INTEGER DEFAULT 0,
                        banbio INTEGER DEFAULT 0
                    )''')
        c.execute('''CREATE TABLE IF NOT EXISTS groups (
                        chat_id INTEGER PRIMARY KEY
                    )''')
        c.execute('''CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY
                    )''')
        conn.commit()

# ---------- HELPERS ----------
def send_message(chat_id, text, silent=False):
    payload = {"chat_id": chat_id, "text": text, "disable_notification": silent}
    try:
        r = requests.post(f"{API_URL}/sendMessage", json=payload).json()
        if r.get("error_code") in [400, 403]:
            remove_group(chat_id)
    except Exception as e:
        print("send_message error:", e)

def delete_message(chat_id, message_id):
    try:
        requests.post(f"{API_URL}/deleteMessage", json={"chat_id": chat_id, "message_id": message_id})
    except Exception as e:
        print("delete_message error:", e)

def get_user_bio(user_id):
    try:
        r = requests.get(f"{API_URL}/getChat?chat_id={user_id}").json()
        return r.get("result", {}).get("bio", "")
    except Exception as e:
        print("get_user_bio error:", e)
        return ""

def is_admin(chat_id, user_id):
    try:
        r = requests.get(f"{API_URL}/getChatAdministrators?chat_id={chat_id}").json()
        return any(admin["user"]["id"] == user_id for admin in r.get("result", []))
    except:
        return False

def save_group(chat_id):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO groups (chat_id) VALUES (?)", (chat_id,))
        c.execute("INSERT OR IGNORE INTO group_settings (chat_id) VALUES (?)", (chat_id,))
        conn.commit()

def save_user(user_id):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()

def remove_group(chat_id):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM groups WHERE chat_id=?", (chat_id,))
        c.execute("DELETE FROM group_settings WHERE chat_id=?", (chat_id,))
        c.execute("DELETE FROM warnings WHERE chat_id=?", (chat_id,))
        conn.commit()

def clean_old_warnings():
    now = int(time.time())
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM warnings WHERE ? - last_warning_time > ?", (now, WARNING_EXPIRY_SECONDS))
        conn.commit()

def get_warning_count(user_id, chat_id):
    clean_old_warnings()
    now = int(time.time())
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT count, last_warning_time FROM warnings WHERE user_id=? AND chat_id=?", (user_id, chat_id))
        row = c.fetchone()
        if row:
            count, last_time = row
            if now - last_time > WARNING_EXPIRY_SECONDS:
                c.execute("DELETE FROM warnings WHERE user_id=? AND chat_id=?", (user_id, chat_id))
                conn.commit()
                return 0
            return count
        return 0

def increment_warning(user_id, chat_id):
    now = int(time.time())
    count = get_warning_count(user_id, chat_id) + 1
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("REPLACE INTO warnings (user_id, chat_id, count, last_warning_time) VALUES (?, ?, ?, ?)",
                  (user_id, chat_id, count, now))
        conn.commit()
    return count

def reset_warning(user_id, chat_id):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("DELETE FROM warnings WHERE user_id=? AND chat_id=?", (user_id, chat_id))
        conn.commit()
    try:
        requests.post(f"{API_URL}/restrictChatMember", json={
            "chat_id": chat_id,
            "user_id": user_id,
            "permissions": {
                "can_send_messages": True,
                "can_send_media_messages": True,
                "can_send_polls": True,
                "can_send_other_messages": True,
                "can_add_web_page_previews": True,
                "can_change_info": False,
                "can_invite_users": True,
                "can_pin_messages": False
            }
        })
    except Exception as e:
        print("unrestrict error:", e)

def reset_all_warnings(chat_id):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM warnings WHERE chat_id=?", (chat_id,))
        users = c.fetchall()
        c.execute("DELETE FROM warnings WHERE chat_id=?", (chat_id,))
        conn.commit()
    for (user_id,) in users:
        reset_warning(user_id, chat_id)

def get_group_setting(chat_id, key):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(f"SELECT {key} FROM group_settings WHERE chat_id=?", (chat_id,))
        row = c.fetchone()
        return row[0] if row else 0

def set_group_setting(chat_id, key, value):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute(f"UPDATE group_settings SET {key}=? WHERE chat_id=?", (value, chat_id))
        conn.commit()

def broadcast_private(msg):
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id FROM users")
        for (user_id,) in c.fetchall():
            payload = {"chat_id": user_id, "disable_notification": True}
            try:
                if "photo" in msg:
                    payload["photo"] = msg["photo"][-1]["file_id"]
                    payload["caption"] = msg.get("caption", "")
                    requests.post(f"{API_URL}/sendPhoto", json=payload)
                else:
                    payload["text"] = msg.get("text", "")
                    requests.post(f"{API_URL}/sendMessage", json=payload)
            except Exception as e:
                print(f"broadcast_private error to {user_id}: {e}")

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

        if chat_type == "private" or (chat_type in ["group", "supergroup"] and is_admin(chat_id, user_id)):
            if text == "/start":
                send_message(chat_id, WELCOME_TEXT)
                return "ok"

        if chat_type == "private":
            save_user(user_id)

        if chat_type in ["group", "supergroup"]:
            save_group(chat_id)

        if "left_chat_member" in msg and msg["left_chat_member"]["id"] == BOT_ID:
            remove_group(chat_id)
            return "ok"

        if text.startswith("/mutebio") and is_admin(chat_id, user_id):
            set_group_setting(chat_id, "mutebio", 1)
            send_message(chat_id, "✅ MuteBio enabled")
        elif text.startswith("/unmutebio") and is_admin(chat_id, user_id):
            set_group_setting(chat_id, "mutebio", 0)
            send_message(chat_id, "❌ MuteBio disabled")
        elif text.startswith("/banbio") and is_admin(chat_id, user_id):
            set_group_setting(chat_id, "banbio", 1)
            send_message(chat_id, "✅ BanBio enabled")
        elif text.startswith("/unbanbio") and is_admin(chat_id, user_id):
            set_group_setting(chat_id, "banbio", 0)
            send_message(chat_id, "❌ BanBio disabled")
        elif text.startswith("/resetbio") and is_admin(chat_id, user_id):
            parts = text.split()
            if len(parts) > 1 and parts[1].lower() == "all":
                reset_all_warnings(chat_id)
                send_message(chat_id, "✅ All warnings and restrictions have been reset.")
            else:
                target_id = None
                if "reply_to_message" in msg:
                    target_id = msg["reply_to_message"]["from"]["id"]
                elif len(parts) > 1:
                    uname = parts[1].lstrip("@")
                    try:
                        r = requests.get(f"{API_URL}/getChat?chat_id=@{uname}").json()
                        if r.get("ok"):
                            target_id = r["result"]["id"]
                    except:
                        try:
                            target_id = int(parts[1])
                        except:
                            pass
                if target_id:
                    reset_warning(target_id, chat_id)
                    send_message(chat_id, f"✅ Bio warnings reset for user ID {target_id}")
                else:
                    send_message(chat_id, "❗ Could not find user to reset warnings.")
        elif text.startswith("/venyriyu") and chat_type == "private":
            if "reply_to_message" in msg:
                broadcast_private(msg["reply_to_message"])
                send_message(chat_id, "✅ Message broadcasted to all users")
            else:
                send_message(chat_id, "❗ Please reply to a message to broadcast.")
        elif chat_type in ["group", "supergroup"] and not is_admin(chat_id, user_id):
            bio = get_user_bio(user_id)
            if any(link in bio.lower() for link in ["http://", "https://", "t.me", "@"]):
                delete_message(chat_id, message_id)
                count = increment_warning(user_id, chat_id)
                send_message(chat_id, f"⚠️ WARNING {count}/3: Remove bio link\n or you will be punished by bot")

                if get_group_setting(chat_id, "banbio") and count >= 3:
                    requests.post(f"{API_URL}/kickChatMember", json={"chat_id": chat_id, "user_id": user_id})
                elif get_group_setting(chat_id, "mutebio") and count >= 3:
                    requests.post(f"{API_URL}/restrictChatMember", json={
                        "chat_id": chat_id,
                        "user_id": user_id,
                        "permissions": {"can_send_messages": False}
                    })

    return "ok"

# ---------- RUN ----------
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)