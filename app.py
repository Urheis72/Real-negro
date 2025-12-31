import os
import asyncio
import threading
import base64
import requests
from flask import Flask, render_template_string, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient
from google.genai import GoogleGenAI

# --- CONFIGURAÇÕES ---
GEMINI_KEY = "AIzaSyAdekalYORl_qzNLGuayZv-7hEZ63ZeVd4"
ELEVEN_KEY = "80f20c0648bd28e0f7c7c77c6d41551f5e5e03109f94f40a9bf0176a981e5b8f"
VOICE_ID = "pNInz6obpgDQGcFmaJgB"
TG_API_ID = 34303434
TG_API_HASH = "5d521f53f9721a6376586a014b51173d"
TG_GROUP_ID = -1002421438612

app = Flask(__name__)
CORS(app)

# Inicializa o cliente conforme seu modelo
ai = GoogleGenAI(api_key=GEMINI_KEY)

# --- TELEGRAM SETUP ---
client_tg = TelegramClient('jarvis_session', TG_API_ID, TG_API_HASH)

def start_tg_background():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    with client_tg:
        client_tg.loop.run_forever()

threading.Thread(target=start_tg_background, daemon=True).start()

# --- LÓGICA DA IA (MODELO 2.5-FLASH) ---
async def get_gemini_response(message):
    try:
        # Usando exatamente o modelo que você pediu
        response = await ai.models.generate_content(
            model="gemini-2.5-flash", 
            contents=message
        )
        return response.text
    except Exception as e:
        # Fallback caso o 2.5 ainda dê 404 no seu servidor
        print(f"Erro no 2.5: {e}")
        response = await ai.models.generate_content(
            model="gemini-2.0-flash", 
            contents=message
        )
        return response.text

# --- LÓGICA DE VOZ ---
def generate_voice(text):
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {"xi-api-key": ELEVEN_KEY, "Content-Type": "application/json"}
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
    }
    try:
        r = requests.post(url, json=payload, headers=headers)
        if r.status_code == 200:
            return base64.b64encode(r.content).decode('utf-8')
    except:
        return None

# --- HTML INTERFACE ---
HTML_PAGE = """
<!DOCTYPE html>
<html>
<head>
    <title>JARVIS v2.5</title>
    <style>
        body { background: #000; color: #0ff; font-family: monospace; padding: 20px; text-transform: uppercase; }
        #console { height: 450px; overflow-y: auto; border: 1px solid #0ff; padding: 15px; background: rgba(0,255,255,0.05); margin-bottom: 20px; }
        .input-line { display: flex; gap: 10px; }
        input { flex: 1; background: #000; border: 1px solid #0ff; color: #0ff; padding: 10px; outline: none; }
        button { background: #0ff; color: #000; border: none; padding: 10px 20px; cursor: pointer; font-weight: bold; }
        .bot-msg { color: #fff; margin: 10px 0; border-left: 2px solid #0ff; padding-left: 10px; }
    </style>
</head>
<body>
    <div id="console">SISTEMA INICIALIZADO... AGUARDANDO COMANDO.</div>
    <form class="input-line" onsubmit="handle(event)">
        <input type="text" id="user_input" placeholder="DIGITE AQUI..." autocomplete="off">
        <button type="submit">EXECUTAR</button>
    </form>

    <script>
        async function handle(e) {
            e.preventDefault();
            const input = document.getElementById('user_input');
            const consoleBox = document.getElementById('console');
            const val = input.value;
            if(!val) return;

            consoleBox.innerHTML += `<div>> ${val}</div>`;
            input.value = '';

            const res = await fetch('/chat', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({message: val})
            });
            const data = await res.json();

            consoleBox.innerHTML += `<div class="bot-msg">${data.reply}</div>`;
            consoleBox.scrollTop = consoleBox.scrollHeight;

            if(data.audio) {
                const audio = new Audio("data:audio/mp3;base64," + data.audio);
                audio.play();
            }
        }
    </script>
</body>
</html>
"""

# --- ROTAS FLASK ---
@app.route('/')
def home():
    return render_template_string(HTML_PAGE)

@app.route('/chat', methods=['POST'])
def chat_endpoint():
    user_msg = request.json.get('message', '')
    
    # Executa a IA (Assíncrono dentro do Flask Síncrono)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    reply = loop.run_until_complete(get_gemini_response(user_msg))
    loop.close()

    # Gera Áudio
    audio_data = generate_voice(reply)

    return jsonify({"reply": reply, "audio": audio_data})

if __name__ == '__main__':
    # Porta 8080 é melhor para o Replit
    app.run(host='0.0.0.0', port=8080)
