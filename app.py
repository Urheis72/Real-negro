import asyncio
import os
import threading
import base64
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from google import genai
from elevenlabs.client import ElevenLabs

# Inicia Flask primeiro para o Render não dar timeout
app = Flask(__name__, static_folder='public')
CORS(app)

# --- CHAVES ---
API_ID = 34303434
API_HASH = '5d521f53f9721a6376586a014b51173d'
TARGET_CHAT = -1002421438612
GEMINI_KEY = "AIzaSyDByO6eYeg8vmb8v9HZ121RQnwdGkBLatk"
ELEVEN_KEY = "80f20c0648bd28e0f7c7c77c6d41551f5e5e03109f94f40a9bf0176a981e5b8f"

# Clientes
client_genai = genai.Client(api_key=GEMINI_KEY)
client_eleven = ElevenLabs(api_key=ELEVEN_KEY)
chat_memory = {}

# Configuração Segura do Telegram
SESSION_STRING = os.environ.get('SESSION_STRING', '')
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

if SESSION_STRING:
    client_telegram = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH, loop=loop)
else:
    client_telegram = TelegramClient(StringSession(), API_ID, API_HASH, loop=loop)

# --- LOGICA DE AUDIO ---
def gerar_audio_base64(texto):
    try:
        audio_gen = client_eleven.text_to_speech.convert(
            text=texto[:300],
            voice_id="pNInz6obpgDQGcFmaJgB",
            model_id="eleven_multilingual_v2"
        )
        return base64.b64encode(b"".join(audio_gen)).decode('utf-8')
    except: return None

# --- ROTAS ---
@app.route('/perguntar', methods=['POST'])
def perguntar():
    data = request.json
    pergunta = data.get('pergunta', '').strip()
    session_id = data.get('session_id', 'user1')

    try:
        if pergunta.startswith('/'):
            # Lógica simplificada de envio direto
            asyncio.run_coroutine_threadsafe(client_telegram.send_message(TARGET_CHAT, pergunta), loop)
            res_text = f"Comando {pergunta} enviado."
        else:
            # IA Gemini
            resp = client_genai.models.generate_content(model="gemini-2.0-flash-exp", contents=pergunta)
            res_text = resp.text

        return jsonify({'resposta': res_text, 'audio': gerar_audio_base64(res_text)})
    except Exception as e:
        return jsonify({'resposta': f"Erro: {str(e)}", 'audio': None})

@app.route('/auth/send_code', methods=['POST'])
def send_code():
    phone = request.json.get('phone')
    try:
        if not client_telegram.is_connected():
            asyncio.run_coroutine_threadsafe(client_telegram.connect(), loop).result()
        res = asyncio.run_coroutine_threadsafe(client_telegram.send_code_request(phone), loop).result()
        global phone_code_hash, temp_phone
        phone_code_hash = res.phone_code_hash
        temp_phone = phone
        return jsonify({'status': 'sent'})
    except Exception as e: return jsonify({'error': str(e)}), 400

@app.route('/auth/login', methods=['POST'])
def login():
    code = request.json.get('code')
    try:
        asyncio.run_coroutine_threadsafe(client_telegram.sign_in(temp_phone, code, phone_code_hash=phone_code_hash), loop).result()
        return jsonify({'status': 'success', 'session_string': client_telegram.session.save()})
    except Exception as e: return jsonify({'error': str(e)}), 400

@app.route('/')
def index(): return send_from_directory('public', 'index.html')

def start_telegram_loop():
    asyncio.set_event_loop(loop)
    loop.run_forever()

if __name__ == '__main__':
    t = threading.Thread(target=start_telegram_loop, daemon=True)
    t.start()
    port = int(os.getenv('PORT', 5000))
    # Importante: debug=False evita o crash do status 1 no Render
    app.run(host='0.0.0.0', port=port, debug=False)
