import os
import asyncio
import logging
import threading
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from telethon.errors import (
    SessionPasswordNeededError, 
    PhoneCodeInvalidError, 
    PhoneNumberInvalidError,
    FloodWaitError
)
import google.generativeai as genai

# --- 1. CONFIGURATION & LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load Environment Variables
API_ID = os.environ.get("API_ID", "34303434")  # Replace with real ID if not in env
API_HASH = os.environ.get("API_HASH", "5d521f53f9721a6376586a014b51173d")
# Target Chat ID where Jarvis/Bot is located (or group)
TARGET_CHAT = int(os.environ.get("TARGET_CHAT", "-1002421438612")) 
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyA9a8QscXbFVLcVn6slY5ddmCHbpmQ5oFY")
SESSION_STRING = os.environ.get('SESSION_STRING', '')

# Initialize Gemini
try:
    genai.configure(api_key=GEMINI_KEY)
    model = genai.GenerativeModel('gemini-2.0-flash-exp')
except Exception as e:
    logger.error(f"Failed to init Gemini: {e}")

app = Flask(__name__, static_folder='public')
CORS(app)

# --- 2. TELEGRAM MANAGER (The Core Logic) ---
class TelegramManager:
    """
    Singleton class to manage the Telethon client in a separate thread.
    This prevents Flask's synchronous nature from blocking the Asyncio loop.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TelegramManager, cls).__new__(cls)
            cls._instance.loop = asyncio.new_event_loop()
            cls._instance.client = None
            cls._instance.phone = None
            cls._instance.phone_code_hash = None
            cls._instance.is_connected = False
        return cls._instance

    def start_background_loop(self):
        """Starts the asyncio loop in a separate daemon thread."""
        def run():
            asyncio.set_event_loop(self.loop)
            self.loop.run_forever()
        
        t = threading.Thread(target=run, daemon=True)
        t.start()
        logger.info("Background AsyncIO Loop Started")

    def init_client(self):
        """Initializes the Telethon Client."""
        session = StringSession(SESSION_STRING)
        self.client = TelegramClient(session, API_ID, API_HASH, loop=self.loop)
        
        # Add event handlers
        self.client.add_event_handler(self.incoming_message_handler, events.NewMessage())

        # Connect immediately
        future = asyncio.run_coroutine_threadsafe(self.client.connect(), self.loop)
        future.add_done_callback(lambda f: self._check_connection())

    def _check_connection(self):
        """Callback to check if we are authorized."""
        async def check():
            if await self.client.is_user_authorized():
                self.is_connected = True
                me = await self.client.get_me()
                logger.info(f"Telegram Connected as: {me.first_name}")
                # Print session string for persistence if needed
                print(f"\n--- SESSION STRING (Save to Env Var) ---\n{self.client.session.save()}\n----------------------------------------\n")
            else:
                logger.info("Client connected but not authorized. Waiting for login.")
        
        asyncio.run_coroutine_threadsafe(check(), self.loop)

    async def incoming_message_handler(self, event):
        """Listens for incoming messages (Logic for Jarvis replies can go here)."""
        # Note: For a simple architecture, we are logging. 
        # To bridge back to HTTP, we would need a Future/Queue system.
        sender = await event.get_sender()
        logger.info(f"New Message from {sender.id}: {event.text}")

    # --- Auth Methods ---

    async def _send_code(self, phone):
        self.phone = phone
        try:
            sent = await self.client.send_code_request(phone)
            self.phone_code_hash = sent.phone_code_hash
            return {"status": "sent", "message": "Code sent via Telegram"}
        except FloodWaitError as e:
            return {"status": "error", "error": f"Flood wait: {e.seconds} seconds"}
        except PhoneNumberInvalidError:
            return {"status": "error", "error": "Invalid phone number"}
        except Exception as e:
            logger.error(f"Send Code Error: {e}")
            return {"status": "error", "error": str(e)}

    async def _login(self, code, password=None):
        try:
            if not self.phone or not self.phone_code_hash:
                return {"status": "error", "error": "Request code first"}

            await self.client.sign_in(
                self.phone, 
                code, 
                phone_code_hash=self.phone_code_hash
            )
            
            self.is_connected = True
            new_session = self.client.session.save()
            return {"status": "success", "session_string": new_session}

        except SessionPasswordNeededError:
            # If 2FA is enabled (not implemented in this simplified UI, but handled here)
            return {"status": "error", "error": "2FA required (Password not supported in this UI version)"}
        except PhoneCodeInvalidError:
            return {"status": "error", "error": "Invalid code"}
        except Exception as e:
            logger.error(f"Login Error: {e}")
            return {"status": "error", "error": str(e)}

    async def _send_message(self, chat_id, text):
        if not self.is_connected:
            raise Exception("Telegram not connected")
        await self.client.send_message(chat_id, text)

    # --- Thread-Safe Public Wrappers ---
    
    def request_code(self, phone):
        future = asyncio.run_coroutine_threadsafe(self._send_code(phone), self.loop)
        return future.result()

    def login(self, code):
        future = asyncio.run_coroutine_threadsafe(self._login(code), self.loop)
        return future.result()

    def send_msg(self, text, is_command=False):
        if is_command:
            # Send to Telegram Group
            asyncio.run_coroutine_threadsafe(self._send_message(TARGET_CHAT, text), self.loop)
        else:
            # Send to Gemini
            pass # Handled in Flask route

# Instantiate the Manager
tg_manager = TelegramManager()

# --- 3. FLASK ROUTES ---

@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

@app.route('/auth/send_code', methods=['POST'])
def auth_send_code():
    """Step 1: Receive phone, trigger Telegram code"""
    data = request.json
    phone = data.get('phone')
    
    if not phone:
        return jsonify({"status": "error", "error": "Phone required"}), 400

    result = tg_manager.request_code(phone)
    if result['status'] == 'error':
        return jsonify(result), 400
    
    return jsonify(result)

@app.route('/auth/login', methods=['POST'])
def auth_login():
    """Step 2: Receive code, complete login"""
    data = request.json
    code = data.get('code')
    
    if not code:
        return jsonify({"status": "error", "error": "Code required"}), 400

    result = tg_manager.login(code)
    if result['status'] == 'error':
        return jsonify(result), 401
    
    return jsonify(result)

@app.route('/perguntar', methods=['POST'])
def perguntar():
    """Main Chat Endpoint"""
    data = request.json
    prompt = data.get('pergunta', '').strip()

    if not prompt:
        return jsonify({'resposta': '...'}), 400

    # 1. Check if it's a command (starts with /)
    if prompt.startswith('/'):
        try:
            if not tg_manager.is_connected:
                return jsonify({'resposta': 'Erro: Telegram desconectado. Faça login novamente.'}), 503
            
            tg_manager.send_msg(prompt, is_command=True)
            return jsonify({'resposta': f'Comando "{prompt}" enviado ao sistema remoto.'})
        except Exception as e:
            return jsonify({'resposta': f'Erro ao enviar comando: {str(e)}'}), 500

    # 2. Otherwise, use Gemini IA
    try:
        response = model.generate_content(
            f"Você é J.A.R.V.I.S. Responda de forma curta, técnica e eficiente. Usuário diz: {prompt}"
        )
        return jsonify({'resposta': response.text})
    except Exception as e:
        logger.error(f"Gemini Error: {e}")
        return jsonify({'resposta': 'Erro no processamento da IA.'}), 500

# --- 4. INITIALIZATION ---

def start_app():
    # Start Telegram Loop
    tg_manager.start_background_loop()
    tg_manager.init_client()
    
    # Start Flask
    port = int(os.environ.get('PORT', 5000))
    # Use_reloader=False is crucial when using threads to avoid duplicating the loop
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

if __name__ == '__main__':
    start_app()
