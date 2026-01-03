import os
import asyncio
import threading
import base64
import requests
from flask import Flask, render_template_string, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient

# SDK NOVO DO GEMINI
from google import genai
from google.genai import types

# ======================================================
# CONFIGURAÇÕES
# ======================================================

# ✅ SUA API KEY (já aplicada)
GEMINI_KEY = "AIzaSyCu7cyG4zuxx8hzG_4nbdsgIaKsfCPxx7k"

ELEVEN_KEY = "80f20c0648bd28e0f7c7c77c6d41551f5e5e03109f94f40a9bf0176a981e5b8f"
VOICE_ID = "pNInz6obpgDQGcFmaJgB"

TG_API_ID = 34303434
TG_API_HASH = "5d521f53f9721a6376586a014b51173d"
TG_BOT_TOKEN = "SEU_TOKEN_DO_BOTFATHER_AQUI"

# ======================================================
# GEMINI 2.x
# ======================================================

MODEL_NAME = "gemini-2.0-flash-exp"
# alternativa:
# MODEL_NAME = "gemini-2.5-chat"

client = genai.Client(api_key=GEMINI_KEY)

chat_memory = []

# ======================================================
# FLASK
# ======================================================

app = Flask(__name__)
CORS(app)

# ======================================================
# TELEGRAM (opcional)
# ======================================================

client_tg = TelegramClient("jarvis_bot_session", TG_API_ID, TG_API_HASH)

def start_telegram():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        if TG_BOT_TOKEN != "SEU_TOKEN_DO_BOTFATHER_AQUI":
            client_tg.start(bot_token=TG_BOT_TOKEN)
            print(">>> TELEGRAM ONLINE")
            client_tg.loop.run_forever()
    except Exception as e:
        print(f"Erro Telegram: {e}")

threading.Thread(target=start_telegram, daemon=True).start()

# ======================================================
# IA – GEMINI 2.x
# ======================================================

def get_ai_response(text):
    try:
        chat_memory.append({"role": "user", "content": text})

        history = "\n".join(
            [f"{m['role']}: {m['content']}" for m in chat_memory]
        )

        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(history)]
            )
        ]

        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=contents
        )

        reply = response.text
        chat_memory.append({"role": "assistant", "content": reply})

        return reply

    except Exception as e:
        return f"Erro Gemini 2.x: {str(e)}"

# ======================================================
# ELEVENLABS
# ======================================================

def get_voice(text):
    if not ELEVEN_KEY:
        return None

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {
        "xi-api-key": ELEVEN_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.8
        }
    }

    try:
        r = requests.post(url, json=data, headers=headers)
        if r.status_code == 200:
            return base64.b64encode(r.content).decode("utf-8")
    except:
        return None

# ======================================================
# ROTAS
# ======================================================

@app.route("/chat", methods=["POST"])
def chat():
    data = request.json
    msg = data.get("message")

    if not msg:
        return jsonify({"error": "Mensagem vazia"}), 400

    reply = get_ai_response(msg)
    audio = get_voice(reply)

    return jsonify({
        "reply": reply,
        "audio": audio
    })

# ======================================================
# FRONTEND
# (mantém o HTML original sem alterações)
# ======================================================

@app.route("/")
def home():
    return render_template_string(HTML_PAGE)

# ======================================================
# START
# ======================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
