import asyncio
import os
import threading
import logging
import re
import requests
import base64
import uuid
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError
import google.generativeai as genai

# --- CONFIGURATION ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger("JarvisCore")

# KEYS
API_ID = int(os.environ.get("API_ID", "34303434"))
API_HASH = os.environ.get("API_HASH", "5d521f53f9721a6376586a014b51173d")
GEMINI_KEY = "AIzaSyDByO6eYeg8vmb8v9HZ121RQnwdGkBLatk"
ELEVEN_KEY = "80f20c0648bd28e0f7c7c77c6d41551f5e5e03109f94f40a9bf0176a981e5b8f"
ELEVEN_VOICE_ID = "pNInz6obpgDQGcFmaJgB"

# TELEGRAM GROUPS (Strict Separation)
COMMAND_GROUP_ID = -1002421438612 
RESULT_GROUP_ID = 7748071327      

app = Flask(__name__, static_folder='public')
CORS(app)
genai.configure(api_key=GEMINI_KEY)

# --- 1. SMART COMMAND PARSER ---
class SmartParser:
    PATTERNS = [
        (r"(?i)(me fale tudo sobre|quero saber sobre|informações de|dados de|busca nome|pesquisa nome) (.+)", "/nome"),
        (r"(?i)(consulte o cpf|veja o cpf|puxe o cpf) (\d+)", "/cpf"),
        (r"(?i)(consulte a placa|veja a placa) ([a-zA-Z0-9]+)", "/placa")
    ]
    
    @staticmethod
    def parse(text):
        for pattern, cmd in SmartParser.PATTERNS:
            match = re.search(pattern, text)
            if match:
                return f"{cmd} {match.group(2).strip()}"
        return None

# --- 2. VOICE ENGINE ---
def generate_audio(text):
    if not text: return None
    try:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE_ID}"
        headers = {"xi-api-key": ELEVEN_KEY, "Content-Type": "application/json"}
        data = {
            "text": text[:1000],
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
        }
        r = requests.post(url, json=data, headers=headers, timeout=5)
        return base64.b64encode(r.content).decode('utf-8') if r.status_code == 200 else None
    except: return None

# --- 3. AI ENGINE (With Memory) ---
class AIEngine:
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
        self.chats = {} # Session storage

    def ask(self, session_id, prompt):
        if session_id not in self.chats:
            self.chats[session_id] = self.model.start_chat(history=[])
        try:
            return self.chats[session_id].send_message(prompt).text
        except: return "Erro na IA."

ai_engine = AIEngine()

# --- 4. TELEGRAM MANAGER (Auth + Execution) ---
class TelegramManager:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TelegramManager, cls).__new__(cls)
            cls._instance.loop = asyncio.new_event_loop()
            cls._instance.client = None
            cls._instance.phone = None
            cls._instance.phone_hash = None
            cls._instance.is_connected = False
            cls._instance.pending_request = None
        return cls._instance

    def start(self):
        t = threading.Thread(target=self._run_loop, daemon=True)
        t.start()

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    # --- AUTH FLOW ---
    async def _init_client(self):
        if not self.client:
            self.client = TelegramClient(StringSession(), API_ID, API_HASH, loop=self.loop)
            await self.client.connect()
            
            # Register Global Listener for Results
            self.client.add_event_handler(self._on_result, events.NewMessage(chats=RESULT_GROUP_ID))
            self.client.add_event_handler(self._on_result, events.NewMessage(incoming=True, func=lambda e: e.is_private))

    async def _send_code(self, phone):
        await self._init_client()
        self.phone = phone
        try:
            res = await self.client.send_code_request(phone)
            self.phone_hash = res.phone_code_hash
            return {"status": "sent", "message": "Código enviado!"}
        except Exception as e: return {"status": "error", "error": str(e)}

    async def _login(self, code):
        try:
            await self.client.sign_in(self.phone, code, phone_code_hash=self.phone_hash)
            self.is_connected = True
            return {"status": "success", "session": self.client.session.save()}
        except SessionPasswordNeededError:
            return {"status": "error", "error": "Senha 2FA necessária (não suportada nesta demo)."}
        except Exception as e: return {"status": "error", "error": str(e)}

    # --- EXECUTION FLOW ---
    async def _execute(self, cmd):
        if not self.is_connected: return "Erro: Login necessário."
        
        self.pending_request = self.loop.create_future()
        try:
            await self.client.send_message(COMMAND_GROUP_ID, cmd)
            return await asyncio.wait_for(self.pending_request, timeout=20.0)
        except asyncio.TimeoutError: return "Erro: Tempo esgotado (Timeout)."
        except Exception as e: return f"Erro: {e}"

    async def _on_result(self, event):
        if not self.pending_request or self.pending_request.done(): return

        # Button Logic
        if event.message.buttons:
            for row in event.message.buttons:
                for btn in row:
                    if "Abrir resultado" in btn.text or "Abrir Link" in btn.text:
                        try:
                            # Telethon click returns URL string for URL buttons
                            res = await event.message.click(btn)
                            url = res if isinstance(res, str) else getattr(btn, 'url', None)
                            if url:
                                data = self._scrape(url)
                                self.pending_request.set_result(data)
                                return
                        except: pass

    def _scrape(self, url):
        try:
            r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=10)
            return r.text[:3000] if r.status_code == 200 else "Erro Link."
        except Exception as e: return str(e)

    # --- PUBLIC SYNC WRAPPERS ---
    def send_code_sync(self, p): return asyncio.run_coroutine_threadsafe(self._send_code(p), self.loop).result()
    def login_sync(self, c): return asyncio.run_coroutine_threadsafe(self._login(c), self.loop).result()
    def run_cmd_sync(self, c): return asyncio.run_coroutine_threadsafe(self._execute(c), self.loop).result()

tg = TelegramManager()
tg.start()

# --- ROUTES ---

@app.route('/')
def index(): return send_from_directory('public', 'index.html')

@app.route('/auth/code', methods=['POST'])
def send_code(): return jsonify(tg.send_code_sync(request.json.get('phone')))

@app.route('/auth/login', methods=['POST'])
def login(): return jsonify(tg.login_sync(request.json.get('code')))

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    text = data.get('message', '').strip()
    session = data.get('session_id', 'default')

    if not text: return jsonify({})

    # 1. Check Smart Command
    cmd = SmartParser.parse(text)
    
    if cmd:
        # Detected Portuguese Keyword -> Telegram
        logger.info(f"Smart Command: {cmd}")
        resp = tg.run_cmd_sync(cmd)
    elif text.startswith('/'):
        # Explicit Command -> Telegram
        logger.info(f"Explicit Command: {text}")
        resp = tg.run_cmd_sync(text)
    else:
        # Natural Text -> AI
        logger.info(f"AI Chat: {text}")
        resp = ai_engine.ask(session, text)

    # 2. Generate Audio
    audio = generate_audio(resp)
    
    return jsonify({"text": resp, "audio": audio})

@app.route('/upload_face', methods=['POST'])
def upload():
    # Stub for face upload
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, use_reloader=False)
