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
import google.generativeai as genai

# --- 1. CONFIGURATION & KEYS ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger("JarvisSystem")

# KEYS (Provided in Prompt)
API_ID = int(os.environ.get("API_ID", "34303434"))
API_HASH = os.environ.get("API_HASH", "5d521f53f9721a6376586a014b51173d")
SESSION_STRING = os.environ.get('SESSION_STRING', '') # Ensure this is set in Env
GEMINI_KEY = "AIzaSyDByO6eYeg8vmb8v9HZ121RQnwdGkBLatk"
ELEVEN_KEY = "80f20c0648bd28e0f7c7c77c6d41551f5e5e03109f94f40a9bf0176a981e5b8f"
ELEVEN_VOICE_ID = "pNInz6obpgDQGcFmaJgB"

# TELEGRAM IDS
COMMAND_GROUP_ID = -1002421438612 # Where we SEND
RESULT_GROUP_ID = 7748071327      # Where we LISTEN

# INIT APPS
app = Flask(__name__, static_folder='public')
CORS(app)
genai.configure(api_key=GEMINI_KEY)

# --- 2. AI MEMORY ENGINE ---
class AIEngine:
    def __init__(self):
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
        self.histories = {} # {session_id: [messages]}

    def get_response(self, session_id, user_text):
        if session_id not in self.histories:
            self.histories[session_id] = []
        
        # Add context/persona
        history = self.histories[session_id]
        
        try:
            chat = self.model.start_chat(history=history)
            response = chat.send_message(user_text)
            
            # Update history (Gemini object handles it, but we persist for safety if needed)
            # self.histories[session_id].append(...) 
            return response.text
        except Exception as e:
            logger.error(f"AI Error: {e}")
            return "Erro ao processar resposta da IA."

    def clear_memory(self, session_id):
        if session_id in self.histories:
            del self.histories[session_id]

ai_engine = AIEngine()

# --- 3. VOICE ENGINE (ElevenLabs) ---
def generate_audio(text):
    if not text: return None
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE_ID}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVEN_KEY
    }
    data = {
        "text": text[:1000], # Limit length to save credits/latency
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
    }
    try:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 200:
            return base64.b64encode(response.content).decode('utf-8')
        else:
            logger.error(f"ElevenLabs Error: {response.text}")
            return None
    except Exception as e:
        logger.error(f"Voice Gen Error: {e}")
        return None

# --- 4. SMART COMMAND PARSER ---
class SmartParser:
    PATTERNS = [
        (r"(?i)(me fale tudo sobre|quero saber sobre|informações de|dados de|busca nome|pesquisa nome) (.+)", "/nome"),
        (r"(?i)(consulte o cpf|veja o cpf|puxe o cpf) (\d+)", "/cpf"),
        (r"(?i)(consulte a placa|veja a placa) ([a-zA-Z0-9]+)", "/placa")
    ]

    @staticmethod
    def parse(text):
        """Converts natural language to Telegram commands if matches."""
        for pattern, command_prefix in SmartParser.PATTERNS:
            match = re.search(pattern, text)
            if match:
                # Group 2 captures the actual data (name, cpf, etc)
                arg = match.group(2).strip()
                return f"{command_prefix} {arg}"
        return None

# --- 5. TELEGRAM MANAGER (Restored Logic) ---
class TelegramManager:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TelegramManager, cls).__new__(cls)
            cls._instance.loop = asyncio.new_event_loop()
            cls._instance.client = None
            cls._instance.is_ready = threading.Event()
            cls._instance.pending_request = None
        return cls._instance

    def start(self):
        t = threading.Thread(target=self._run_loop, daemon=True)
        t.start()
        self.is_ready.wait(timeout=30)

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._init_client())
        self.loop.run_forever()

    async def _init_client(self):
        try:
            session = StringSession(SESSION_STRING)
            self.client = TelegramClient(session, API_ID, API_HASH, loop=self.loop)
            await self.client.connect()
            
            # Listeners
            self.client.add_event_handler(self._on_result, events.NewMessage(chats=RESULT_GROUP_ID))
            self.client.add_event_handler(self._on_result, events.NewMessage(incoming=True, func=lambda e: e.is_private))
            
            logger.info("✅ Telegram Connected & Monitoring")
            self.is_ready.set()
        except Exception as e:
            logger.error(f"Telegram Init Error: {e}")
            self.is_ready.set()

    async def _on_result(self, event):
        if not self.pending_request or self.pending_request.done(): return
        
        # Check for Buttons logic (Restored from previous success)
        if event.message.buttons:
            for row in event.message.buttons:
                for btn in row:
                    if "Abrir resultado" in btn.text or "Abrir Link" in btn.text:
                        try:
                            logger.info("🔘 Button Found. Clicking...")
                            clicked = await event.message.click(btn)
                            url = clicked if isinstance(clicked, str) else getattr(btn, 'url', None)
                            
                            if url:
                                data = self._scrape(url)
                                self.pending_request.set_result(data)
                                return
                        except Exception as e:
                            logger.error(f"Button Click Error: {e}")

    def _scrape(self, url):
        try:
            r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
            return r.text[:3000] if r.status_code == 200 else "Erro no Link."
        except Exception as e: return str(e)

    async def _send_cmd(self, cmd):
        if not await self.client.is_user_authorized(): return "Erro: Telegram não conectado."
        self.pending_request = self.loop.create_future()
        try:
            await self.client.send_message(COMMAND_GROUP_ID, cmd)
            return await asyncio.wait_for(self.pending_request, timeout=20.0)
        except asyncio.TimeoutError: return "Erro: Bot não respondeu a tempo."
        except Exception as e: return f"Erro: {e}"

    def run_command_sync(self, cmd):
        return asyncio.run_coroutine_threadsafe(self._send_cmd(cmd), self.loop).result()

tg = TelegramManager()
tg.start()

# --- 6. ROUTES ---

@app.route('/')
def index(): return send_from_directory('public', 'index.html')

@app.route('/upload_face', methods=['POST'])
def upload_face():
    """Handles auto-captured photos from the frontend."""
    # Logic to save or process the face
    # In a real app, you would save this or run deeper recognition
    return jsonify({"status": "received", "message": "Face logada com sucesso."})

@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    user_text = data.get('message', '').strip()
    session_id = data.get('session_id', 'default')

    if not user_text: return jsonify({'text': '...'})

    response_text = ""
    
    # 1. SMART COMMAND CHECK (Portuguese -> Command)
    smart_command = SmartParser.parse(user_text)
    
    if smart_command:
        logger.info(f"🧠 Smart Command Detected: {user_text} -> {smart_command}")
        response_text = tg.run_command_sync(smart_command)
    
    # 2. EXPLICIT COMMAND CHECK
    elif user_text.startswith('/'):
        logger.info(f"⚡ Telegram Command: {user_text}")
        response_text = tg.run_command_sync(user_text)
        
    # 3. AI FALLBACK
    else:
        logger.info(f"🤖 AI Chat: {user_text}")
        response_text = ai_engine.get_response(session_id, user_text)

    # 4. VOICE GENERATION (ElevenLabs)
    # Generate audio for the final response
    audio_b64 = generate_audio(response_text)

    return jsonify({
        "text": response_text,
        "audio": audio_b64
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, use_reloader=False)
