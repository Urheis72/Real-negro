import os
import asyncio
import threading
import base64
import requests
from flask import Flask, render_template_string, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient
from google.genai import GoogleGenAI  # Conforme seu modelo

# --- CONFIGURAÇÕES ---
GEMINI_KEY = "AIzaSyAdekalYORl_qzNLGuayZv-7hEZ63ZeVd4"
ELEVEN_KEY = "80f20c0648bd28e0f7c7c77c6d41551f5e5e03109f94f40a9bf0176a981e5b8f"
VOICE_ID = "pNInz6obpgDQGcFmaJgB"
TG_API_ID = 34303434
TG_API_HASH = "5d521f53f9721a6376586a014b51173d"
TG_GROUP_ID = -1002421438612

app = Flask(__name__)
CORS(app)

# Inicializa o Gemini com sua Key
ai = GoogleGenAI(api_key=GEMINI_KEY)

# --- TELEGRAM SETUP ---
client_tg = TelegramClient('jarvis_session', TG_API_ID, TG_API_HASH)
tg_loop = asyncio.new_event_loop()

def start_telegram():
    asyncio.set_event_loop(tg_loop)
    with client_tg:
        client_tg.loop.run_forever()

threading.Thread(target=start_telegram, daemon=True).start()

# --- LÓGICA DE IA (ASYNC conforme seu modelo) ---
async def call_gemini(message):
    try:
        # Alterado para 2.0-flash para evitar o erro 404
        response = await ai.models.generateContent(
            model="gemini-2.0-flash", 
            contents=message
        )
        return response.text
    except Exception as e:
        print(f"Erro Gemini: {e}")
        return f"Erro na IA: {str(e)}"

# --- LÓGICA DE VOZ ---
def get_audio_base64(text):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {"xi-api-key": ELEVEN_KEY, "Content-Type": "application/json"}
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}
    }
    try:
        res = requests.post(url, json=data, headers=headers)
        if res.status_code == 200:
            return base64.b64encode(res.content).decode('utf-8')
    except: return None

# --- FRONTEND (HTML + JS) ---
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>JARVIS</title>
    <style>
        body { background: #000; color: #0ff; font-family: monospace; padding: 20px; }
        #log { height: 400px; overflow-y: auto; border: 1px solid #333; padding: 10px; margin-bottom: 10px; }
        input { width: 80%; padding: 10px; background: #111; color: #0ff; border: 1px solid #0ff; }
        button { padding: 10px; cursor: pointer; background: #0ff; color: #000; border: none; font-weight: bold; }
    </style>
</head>
<body>
    <div id="log"></div>
    <form onsubmit="ask(event)">
        <input type="text" id="msg" placeholder="Comando ou Mensagem..." autocomplete="off">
        <button type="submit">EXECUTAR</button>
    </form>
    <script>
        async function ask(e) {
            e.preventDefault();
            const msg = document.getElementById('msg').value;
            document.getElementById('msg').value = '';
            const log = document.getElementById('log');
            log.innerHTML += `<div>> ${msg}</div>`;

            const res = await fetch('/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message: msg})
            });
            const data = await res.json();
            log.innerHTML += `<div style="color: #ccc">${data.reply}</div>`;
            log.scrollTop = log.scrollHeight;

            if (data.audio) {
                new Audio("data:audio/mp3;base64," + data.audio).play();
            }
        }
    </script>
</body>
</html>
"""

# --- ROTAS ---
@app.route('/')
def index(): return render_template_string(HTML_PAGE)

@app.route('/chat', methods=['POST'])
def chat():
    msg = request.json.get('message', '')
    
    # Se for comando, vai pro Telegram, senão Gemini
    if msg.startswith('/'):
        # Lógica simplificada de resposta do telegram
        reply = "Comando enviado ao Telegram." 
    else:
        # Chama a função async do Gemini
        reply = asyncio.run(call_gemini(msg))

    audio = get_audio_base64(reply)
    return jsonify({"reply": reply, "audio": audio})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
