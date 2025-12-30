import os
import asyncio
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS
from google import genai
from google.genai import types
from telethon import TelegramClient, events
from telethon.sessions import StringSession

app = Flask(__name__)
CORS(app)

# --- CONFIGURAÇÕES ---
API_KEY = "AIzaSyA9a8QscXbFVLcVn6slY5ddmCHbpmQ5oFY"
TELEGRAM_API_ID = 34303434
TELEGRAM_API_HASH = "5d521f53f9721a6376586a014b51173d"
TARGET_GROUP = -1002421438612

client_gemini = genai.Client(api_key=API_KEY)
MODEL = "gemini-2.5-chat" 
chat_memory = []

# --- LÓGICA TELEGRAM (Async em Thread separada) ---
tg_client = TelegramClient(StringSession(), TELEGRAM_API_ID, TELEGRAM_API_HASH)
loop = asyncio.new_event_loop()

def run_tg_loop():
    asyncio.set_event_loop(loop)
    loop.run_until_complete(tg_client.connect())
    loop.run_forever()

threading.Thread(target=run_tg_loop, daemon=True).start()

async def send_tg_command(cmd):
    # Envia o comando e aguarda o arquivo TXT no grupo
    await tg_client.send_message(TARGET_GROUP, cmd)
    
    # Timeout de 30 segundos para o bot responder
    for _ in range(30):
        await asyncio.sleep(1)
        async for msg in tg_client.iter_messages(TARGET_GROUP, limit=1):
            if msg.file and msg.file.name.endswith('.txt'):
                path = await msg.download_media(file=bytes)
                return path.decode('utf-8', errors='ignore')
    return "Erro: Bot de busca não respondeu a tempo."

# --- ROTAS ---
@app.route("/chat", methods=["POST"])
def chat():
    global chat_memory
    data = request.json
    user_message = data.get("message", "")

    # SEPARAÇÃO DE LOGICA: COMANDO vs IA
    if user_message.startswith("/") or any(k in user_message.lower() for k in ["busca nome", "dados de"]):
        # Fluxo Telegram
        cmd = user_message if user_message.startswith("/") else f"/nome {user_message}"
        future = asyncio.run_coroutine_threadsafe(send_tg_command(cmd), loop)
        result = future.result()
        return jsonify({"reply": result, "type": "telegram"})

    # Fluxo Original Gemini
    chat_memory.append({"role": "user", "content": user_message})
    contents = [types.Content(role="user", parts=[types.Part.from_text("\n".join([f"{m['role']}: {m['content']}" for m in chat_memory]))])]
    generate_config = types.GenerateContentConfig(response_modalities=["TEXT"])

    try:
        response_text = ""
        for chunk in client_gemini.models.generate_content_stream(model=MODEL, contents=contents, config=generate_config):
            if chunk.candidates and chunk.candidates[0].content and chunk.candidates[0].content.parts:
                part = chunk.candidates[0].content.parts[0]
                if part.text: response_text += part.text

        chat_memory.append({"role": "king", "content": response_text})
        return jsonify({"reply": response_text, "type": "ai"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
