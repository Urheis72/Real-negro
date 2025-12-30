import asyncio
import os
import threading
import logging
import re
import requests
import base64
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.tl.types import DocumentAttributeFilename
import google.generativeai as genai

# --- CONFIGURAÇÃO DE LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("JarvisEngine")

# --- CHAVES ---
API_ID = 34303434
API_HASH = "5d521f53f9721a6376586a014b51173d"
GEMINI_KEY = "AIzaSyDByO6eYeg8vmb8v9HZ121RQnwdGkBLatk"
ELEVEN_KEY = "80f20c0648bd28e0f7c7c77c6d41551f5e5e03109f94f40a9bf0176a981e5b8f"
VOICE_ID = "pNInz6obpgDQGcFmaJgB"

# --- TELEGRAM ---
COMMAND_GROUP_ID = -1002421438612

app = Flask(__name__, static_folder='public')
CORS(app)

# --- INICIALIZAÇÃO GEMINI ---
try:
    genai.configure(api_key=GEMINI_KEY)
    # Usando o modelo estável mais recente
    model = genai.GenerativeModel('gemini-1.5-flash')
    logger.info("✅ Gemini Configurado.")
except Exception as e:
    logger.error(f"❌ Erro Gemini: {e}")

# --- MEMÓRIA DA IA ---
chat_sessions = {}

# --- LÓGICA DE VOZ (ELEVENLABS) ---
def text_to_speech(text):
    if not text: return None
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {"xi-api-key": ELEVEN_KEY, "Content-Type": "application/json"}
    data = {
        "text": text[:1500],
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.4, "similarity_boost": 0.8}
    }
    try:
        response = requests.post(url, json=data, headers=headers, timeout=10)
        if response.status_code == 200:
            return base64.b64encode(response.content).decode('utf-8')
        logger.error(f"ElevenLabs Error: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"TTS Exception: {e}")
    return None

# --- MANAGER TELEGRAM ---
class TelegramManager:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TelegramManager, cls).__new__(cls)
            cls._instance.loop = asyncio.new_event_loop()
            cls._instance.client = None
            cls._instance.pending_request = None
            cls._instance.is_auth = False
        return cls._instance

    def start(self):
        threading.Thread(target=self._run_loop, daemon=True).start()

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def init_client(self):
        if not self.client:
            self.client = TelegramClient(StringSession(), API_ID, API_HASH, loop=self.loop)
            await self.client.connect()
            self.client.add_event_handler(self._on_txt, events.NewMessage(chats=COMMAND_GROUP_ID))

    async def _on_txt(self, event):
        if self.pending_request and not self.pending_request.done() and event.message.file:
            if event.message.file.name and event.message.file.name.endswith('.txt'):
                file_bytes = await event.message.download_media(file=bytes)
                content = file_bytes.decode('utf-8', errors='replace')
                self.pending_request.set_result(content)

    async def execute_command(self, cmd):
        self.pending_request = self.loop.create_future()
        await self.client.send_message(COMMAND_GROUP_ID, cmd)
        return await asyncio.wait_for(self.pending_request, timeout=35.0)

tg = TelegramManager()
tg.start()

# --- ROUTES ---
@app.route('/')
def index(): return send_from_directory('public', 'index.html')

@app.route('/auth/code', methods=['POST'])
def send_code():
    phone = request.json.get('phone')
    async def _task():
        await tg.init_client()
        res = await tg.client.send_code_request(phone)
        tg.phone = phone
        tg.phone_hash = res.phone_code_hash
        return {"status": "sent"}
    return jsonify(asyncio.run_coroutine_threadsafe(_task(), tg.loop).result())

@app.route('/auth/login', methods=['POST'])
def login():
    code = request.json.get('code')
    async def _task():
        await tg.client.sign_in(tg.phone, code, phone_code_hash=tg.phone_hash)
        tg.is_auth = True
        return {"status": "success"}
    return jsonify(asyncio.run_coroutine_threadsafe(_task(), tg.loop).result())

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    text = data.get('message', '').strip()
    session_id = data.get('session_id', 'default')

    # Lógica de Roteamento
    try:
        if text.startswith('/'):
            # Telegram Flow
            response_text = asyncio.run_coroutine_threadsafe(tg.execute_command(text), tg.loop).result()
        elif any(k in text.lower() for k in ["me fale tudo sobre", "quero saber sobre", "busca nome", "dados de"]):
            # Smart Command Flow
            name = text.split("sobre")[-1].strip() if "sobre" in text else text
            response_text = asyncio.run_coroutine_threadsafe(tg.execute_command(f"/nome {name}"), tg.loop).result()
        else:
            # Gemini AI Flow
            if session_id not in chat_sessions:
                chat_sessions[session_id] = model.start_chat(history=[])
            ai_res = chat_sessions[session_id].send_message(text)
            response_text = ai_res.text

        audio_b64 = text_to_speech(response_text)
        return jsonify({"text": response_text, "audio": audio_b64})
    
    except Exception as e:
        logger.error(f"Chat Error: {e}")
        return jsonify({"text": f"Ocorreu um erro no processamento: {str(e)}", "audio": None})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, use_reloader=False)
