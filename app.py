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
from telethon.errors import SessionPasswordNeededError
from telethon.tl.types import DocumentAttributeFilename
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

# TELEGRAM GROUPS
# We send AND listen in this group now, based on the TXT file requirement
COMMAND_GROUP_ID = -1002421438612 

app = Flask(__name__, static_folder='public')
CORS(app)
genai.configure(api_key=GEMINI_KEY)

# --- 1. SMART COMMAND PARSER (Keep Existing) ---
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

# --- 2. VOICE ENGINE (Keep Existing) ---
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

# --- 3. AI ENGINE (Keep Existing) ---
class AIEngine:
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
        self.chats = {} 

    def ask(self, session_id, prompt):
        if session_id not in self.chats:
            self.chats[session_id] = self.model.start_chat(history=[])
        try:
            return self.chats[session_id].send_message(prompt).text
        except: return "Erro na IA."

ai_engine = AIEngine()

# --- 4. TELEGRAM MANAGER (UPDATED LOGIC) ---
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
            
            # --- NEW LISTENER LOGIC: TXT FILES ---
            # We listen in the COMMAND group for the bot's response
            self.client.add_event_handler(
                self._on_txt_file_response, 
                events.NewMessage(chats=COMMAND_GROUP_ID)
            )

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
            return {"status": "error", "error": "Senha 2FA necessária."}
        except Exception as e: return {"status": "error", "error": str(e)}

    # --- EXECUTION FLOW ---
    async def _execute(self, cmd):
        if not self.is_connected: return "Erro: Login necessário."
        
        # Reset future
        self.pending_request = self.loop.create_future()
        
        try:
            # 1. Send Command to the Bot Group
            logger.info(f"📤 Sending command '{cmd}' to {COMMAND_GROUP_ID}")
            await self.client.send_message(COMMAND_GROUP_ID, cmd)
            
            # 2. Wait for the TXT file response in the same group
            logger.info("⏳ Waiting for TXT file response...")
            result = await asyncio.wait_for(self.pending_request, timeout=30.0)
            return result

        except asyncio.TimeoutError:
            return "Erro: O bot demorou muito para gerar o arquivo TXT."
        except Exception as e:
            return f"Erro processando comando: {e}"

    # --- NEW EVENT HANDLER: TXT PARSER ---
    async def _on_txt_file_response(self, event):
        """
        Listens for messages with .txt files in the command group.
        Downloads, reads, and returns the content.
        """
        # Only proceed if we are waiting for a request
        if not self.pending_request or self.pending_request.done():
            return

        # Check if message has a file
        if event.message.file:
            # Check if it's a text file (mime type or extension)
            is_txt = False
            
            # Check MIME
            if 'text/plain' in event.message.file.mime_type:
                is_txt = True
            
            # Check Filename Extension
            if not is_txt:
                for attr in event.message.file.attributes:
                    if isinstance(attr, DocumentAttributeFilename):
                        if attr.file_name.lower().endswith('.txt'):
                            is_txt = True
                            break
            
            if is_txt:
                try:
                    logger.info(f"📄 TXT File detected: {event.message.id}. Downloading...")
                    
                    # Download to memory (bytes)
                    file_bytes = await event.message.download_media(file=bytes)
                    
                    # Decode content
                    content = file_bytes.decode('utf-8', errors='replace')
                    
                    logger.info("✅ File read successfully. Returning content.")
                    self.pending_request.set_result(content)
                except Exception as e:
                    logger.error(f"❌ Error reading file: {e}")
                    if not self.pending_request.done():
                        self.pending_request.set_exception(e)

    # --- SYNC WRAPPERS ---
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

    # 1. Smart Command Check
    cmd = SmartParser.parse(text)
    
    if cmd:
        logger.info(f"🧠 Smart Command: {cmd}")
        resp = tg.run_cmd_sync(cmd)
    elif text.startswith('/'):
        logger.info(f"⚡ Explicit Command: {text}")
        resp = tg.run_cmd_sync(text)
    else:
        logger.info(f"🤖 AI Chat: {text}")
        resp = ai_engine.ask(session, text)

    # 2. Voice
    audio = generate_audio(resp)
    
    return jsonify({"text": resp, "audio": audio})

@app.route('/upload_face', methods=['POST'])
def upload():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, use_reloader=False)
