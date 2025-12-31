import os
import asyncio
import threading
import base64
import requests
from flask import Flask, render_template_string, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient
from google import genai
from google.genai import types

# --- CONFIGURAÇÕES (Coloque suas chaves aqui) ---
GEMINI_KEY = "AIzaSyAdekalYORl_qzNLGuayZv-7hEZ63ZeVd4"
ELEVEN_KEY = "80f20c0648bd28e0f7c7c77c6d41551f5e5e03109f94f40a9bf0176a981e5b8f"
VOICE_ID = "pNInz6obpgDQGcFmaJgB"
TG_API_ID = 34303434
TG_API_HASH = "5d521f53f9721a6376586a014b51173d"
TG_GROUP_ID = -1002421438612

app = Flask(__name__)
CORS(app)

# --- CLIENTES ---
# 1. Gemini
client_gemini = genai.Client(api_key=GEMINI_KEY)

# 2. Telegram (Async rodando em Thread separada)
client_tg = TelegramClient('jarvis_session', TG_API_ID, TG_API_HASH)
loop = asyncio.new_event_loop()

def start_telegram():
    asyncio.set_event_loop(loop)
    with client_tg:
        client_tg.loop.run_forever()

threading.Thread(target=start_telegram, daemon=True).start()

# --- FUNÇÕES AUXILIARES ---

def get_audio_base64(text):
    """Gera áudio no ElevenLabs e converte para Base64 para o HTML tocar"""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {
        "xi-api-key": ELEVEN_KEY,
        "Content-Type": "application/json"
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}
    }
    try:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 200:
            return base64.b64encode(response.content).decode('utf-8')
    except Exception as e:
        print(f"Erro ElevenLabs: {e}")
    return None

async def telegram_flow(command):
    """Envia comando e espera o TXT"""
    async with client_tg:
        await client_tg.send_message(TG_GROUP_ID, command)
        # Tenta pegar resposta por 30 segundos
        for _ in range(30):
            await asyncio.sleep(1)
            msgs = await client_tg.get_messages(TG_GROUP_ID, limit=1)
            if msgs:
                m = msgs[0]
                if m.file and m.file.name.endswith('.txt'):
                    content = await client_tg.download_media(m, file=bytes)
                    return content.decode('utf-8', errors='ignore')
    return "O sistema de busca não retornou dados a tempo."

def gemini_flow(text):
    """Consulta o Gemini"""
    try:
        response = client_gemini.models.generate_content(
            model="gemini-1.5-flash",
            contents=text
        )
        return response.text
    except Exception as e:
        return f"Erro na IA: {str(e)}"

# --- FRONTEND EMBUTIDO (HTML) ---
HTML_PAGE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>JARVIS PYTHON CORE</title>
    <style>
        body { background: #0a0a0a; color: #00ffcc; font-family: 'Courier New', monospace; display: flex; flex-direction: column; height: 100vh; margin: 0; overflow: hidden; }
        #chat { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 15px; }
        .msg { max-width: 80%; padding: 10px 15px; border-radius: 8px; font-size: 14px; line-height: 1.4; }
        .user { align-self: flex-end; background: #004444; border: 1px solid #00ffcc; }
        .jarvis { align-self: flex-start; background: #111; border: 1px solid #333; color: #ccc; }
        .input-area { padding: 20px; background: #111; border-top: 1px solid #333; display: flex; gap: 10px; }
        input { flex: 1; background: #000; border: 1px solid #333; color: white; padding: 12px; border-radius: 4px; outline: none; }
        input:focus { border-color: #00ffcc; }
        button { background: #00ffcc; color: black; border: none; padding: 12px 24px; font-weight: bold; cursor: pointer; border-radius: 4px; }
        button:hover { background: #00ccaa; }
        /* Animação de carregando */
        .typing { font-size: 12px; color: #555; font-style: italic; }
    </style>
</head>
<body>
    <div id="chat">
        <div class="msg jarvis">Sistemas Online. Aguardando comando.</div>
    </div>
    <form class="input-area" onsubmit="send(event)">
        <input type="text" id="inp" placeholder="Digite aqui..." autocomplete="off">
        <button type="submit">ENVIAR</button>
    </form>

    <script>
        async function send(e) {
            e.preventDefault();
            const inp = document.getElementById('inp');
            const text = inp.value.trim();
            if (!text) return;

            addMsg(text, 'user');
            inp.value = '';
            
            const loadId = addMsg("Processando...", 'typing');

            try {
                const res = await fetch('/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ message: text })
                });
                const data = await res.json();
                
                // Remove loading e adiciona resposta
                document.getElementById(loadId).remove();
                addMsg(data.reply, 'jarvis');

                // Toca Áudio
                if (data.audio) {
                    const audio = new Audio("data:audio/mp3;base64," + data.audio);
                    audio.play();
                }

            } catch (err) {
                document.getElementById(loadId).innerText = "Erro de conexão.";
            }
        }

        function addMsg(text, type) {
            const div = document.createElement('div');
            const id = Math.random().toString(36).substr(2, 9);
            div.id = id;
            div.className = 'msg ' + type;
            div.innerText = text;
            document.getElementById('chat').appendChild(div);
            document.getElementById('chat').scrollTop = document.getElementById('chat').scrollHeight;
            return id;
        }
    </script>
</body>
</html>
"""

# --- ROTAS ---
@app.route('/')
def index():
    return render_template_string(HTML_PAGE)

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    msg = data.get('message', '')
    
    response_text = ""

    # 1. Decide quem responde (Telegram ou Gemini)
    if msg.startswith('/') or any(k in msg.lower() for k in ["busca", "dados de"]):
        # Vai pro Telegram
        future = asyncio.run_coroutine_threadsafe(telegram_flow(msg), loop)
        response_text = future.result()
    else:
        # Vai pro Gemini
        response_text = gemini_flow(msg)

    # 2. Gera o áudio (Backend Python faz o trabalho pesado)
    audio_b64 = get_audio_base64(response_text)

    return jsonify({
        "reply": response_text,
        "audio": audio_b64
    })

if __name__ == '__main__':
    print(">>> JARVIS RODANDO EM: http://localhost:5000")
    app.run(host='0.0.0.0', port=5000)
