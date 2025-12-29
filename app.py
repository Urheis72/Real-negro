import asyncio
import os
import threading
import logging
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError, 
    PhoneCodeInvalidError, 
    PhoneNumberInvalidError,
    FloodWaitError,
    rpcbaseerrors
)
import google.generativeai as genai

# --- 1. LOGGING & CONFIGURATION ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger("JarvisBackend")

# Secrets
API_ID = int(os.environ.get("API_ID", "34303434"))
API_HASH = os.environ.get("API_HASH", "5d521f53f9721a6376586a014b51173d")
TARGET_CHAT = int(os.environ.get("TARGET_CHAT", "-1002421438612")) # Must be Integer
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyA9a8QscXbFVLcVn6slY5ddmCHbpmQ5oFY")
SESSION_STRING = os.environ.get('SESSION_STRING', '')

# Init Flask & Gemini
app = Flask(__name__, static_folder='public')
CORS(app)

try:
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash-exp')
except Exception as e:
    logger.error(f"Gemini Init Failed: {e}")

# --- 2. ROBUST TELEGRAM MANAGER ---
class TelegramManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TelegramManager, cls).__new__(cls)
            cls._instance.loop = asyncio.new_event_loop()
            cls._instance.client = None
            cls._instance.phone = None
            cls._instance.phone_code_hash = None
            cls._instance.is_connected = False
            cls._instance.me = None
        return cls._instance

    def start(self):
        """Starts the dedicated AsyncIO thread."""
        t = threading.Thread(target=self._run_loop, daemon=True)
        t.start()
        logger.info("Background AsyncIO Thread Started")
        
        # Initialize Client immediately
        asyncio.run_coroutine_threadsafe(self._init_client(), self.loop)

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _init_client(self):
        """Async initialization of the Telethon Client."""
        try:
            session = StringSession(SESSION_STRING)
            self.client = TelegramClient(session, API_ID, API_HASH, loop=self.loop)
            
            await self.client.connect()
            
            if await self.client.is_user_authorized():
                self.is_connected = True
                self.me = await self.client.get_me()
                logger.info(f"✅ Telegram Connected as: {self.me.first_name} (ID: {self.me.id})")
                
                # CRITICAL FIX: Populate Entity Cache
                # This ensures the client 'knows' about the target chat
                logger.info("Refreshing dialog list to resolve entities...")
                await self.client.get_dialogs(limit=100) 
            else:
                logger.warning("⚠️ Client connected but NOT authorized. Login required.")

        except Exception as e:
            logger.error(f"❌ Client Init Error: {e}")

    # --- CORE SENDING LOGIC (The Fix) ---
    async def _send_to_group_async(self, text):
        if not self.is_connected:
            raise Exception("Client is not connected/authorized.")

        try:
            # 1. Resolve Entity explicitly
            # If the ID is a number, Telethon needs to find it in its cache first
            try:
                entity = await self.client.get_entity(TARGET_CHAT)
            except ValueError:
                logger.warning(f"Entity {TARGET_CHAT} not found in cache. Fetching dialogs...")
                await self.client.get_dialogs() # Force refresh
                entity = await self.client.get_entity(TARGET_CHAT)

            # 2. Send Message
            await self.client.send_message(entity, text)
            logger.info(f"Message sent to {TARGET_CHAT}: {text}")
            return True

        except rpcbaseerrors.ForbiddenError:
            raise Exception(f"Bot/User was kicked from group {TARGET_CHAT} or lacks write permission.")
        except ValueError:
            raise Exception(f"Could not find chat with ID {TARGET_CHAT}. Is the user a member?")
        except Exception as e:
            logger.error(f"Send Failed: {e}")
            raise e

    # --- WRAPPERS FOR FLASK ---
    def send_message_sync(self, text):
        """Thread-safe wrapper called by Flask."""
        if not self.client:
            raise Exception("Telegram Client not initialized")
        
        future = asyncio.run_coroutine_threadsafe(
            self._send_to_group_async(text), 
            self.loop
        )
        return future.result() # Wait for result (Determinism)

    def request_code_sync(self, phone):
        future = asyncio.run_coroutine_threadsafe(self._request_code(phone), self.loop)
        return future.result()

    def login_sync(self, code):
        future = asyncio.run_coroutine_threadsafe(self._login(code), self.loop)
        return future.result()

    # --- AUTH LOGIC ---
    async def _request_code(self, phone):
        self.phone = phone
        try:
            sent = await self.client.send_code_request(phone)
            self.phone_code_hash = sent.phone_code_hash
            return {"status": "sent", "message": "Code sent"}
        except FloodWaitError as e:
            return {"status": "error", "error": f"Flood wait: {e.seconds}s"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    async def _login(self, code):
        try:
            await self.client.sign_in(self.phone, code, phone_code_hash=self.phone_code_hash)
            self.is_connected = True
            session_str = self.client.session.save()
            logger.info(f"Login Success. Session: {session_str}")
            
            # Refresh cache immediately after login
            await self.client.get_dialogs(limit=50)
            
            return {"status": "success", "session_string": session_str}
        except Exception as e:
            return {"status": "error", "error": str(e)}

# Initialize Singleton
tg = TelegramManager()
tg.start()

# --- 3. FLASK ENDPOINTS ---

@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

@app.route('/auth/send_code', methods=['POST'])
def send_code():
    data = request.json
    res = tg.request_code_sync(data.get('phone'))
    return jsonify(res), (200 if res['status'] == 'sent' else 400)

@app.route('/auth/login', methods=['POST'])
def login():
    data = request.json
    res = tg.login_sync(data.get('code'))
    return jsonify(res), (200 if res['status'] == 'success' else 400)

@app.route('/perguntar', methods=['POST'])
def ask():
    data = request.json
    prompt = data.get('pergunta', '').strip()

    if not prompt:
        return jsonify({'resposta': '...'}), 400

    # CASE A: Telegram Command
    if prompt.startswith('/'):
        try:
            tg.send_message_sync(prompt)
            return jsonify({'resposta': f'Comando "{prompt}" executado com sucesso no servidor remoto.'})
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return jsonify({'resposta': f'Falha no envio: {str(e)}'}), 500

    # CASE B: AI Chat
    try:
        response = model.generate_content(f"Seja o Jarvis. Curto e direto: {prompt}")
        return jsonify({'resposta': response.text})
    except Exception as e:
        return jsonify({'resposta': 'Erro nos sistemas de IA.'}), 500

if __name__ == '__main__':
    # Use reloader=False to prevent double-thread initialization
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
