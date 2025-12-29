import asyncio
import os
import threading
import logging
import re
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# --- CONFIGURATION & LOGGING ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger("JarvisBackend")

# Secrets
API_ID = int(os.environ.get("API_ID", "34303434"))
API_HASH = os.environ.get("API_HASH", "5d521f53f9721a6376586a014b51173d")
SESSION_STRING = os.environ.get('SESSION_STRING', '')
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "AIzaSyA9a8QscXbFVLcVn6slY5ddmCHbpmQ5oFY")

# --- STRICT GROUP SEPARATION ---
# 1. WHERE WE SEND COMMANDS
COMMAND_GROUP_ID = int("-1002421438612") 

# 2. WHERE WE LISTEN FOR RESULTS
RESULT_GROUP_ID = int("7748071327") 

app = Flask(__name__, static_folder='public')
CORS(app)

class TelegramManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TelegramManager, cls).__new__(cls)
            cls._instance.loop = asyncio.new_event_loop()
            cls._instance.client = None
            cls._instance.is_connected = False
            # Queue to hold the pending request future
            cls._instance.pending_request = None 
        return cls._instance

    def start(self):
        """Starts the AsyncIO loop in a separate daemon thread."""
        t = threading.Thread(target=self._run_loop, daemon=True)
        t.start()
        logger.info("✅ Background AsyncIO Loop Started")
        asyncio.run_coroutine_threadsafe(self._init_client(), self.loop)

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _init_client(self):
        """Initializes Telethon and registers the Result Listener."""
        try:
            session = StringSession(SESSION_STRING)
            self.client = TelegramClient(session, API_ID, API_HASH, loop=self.loop)
            await self.client.connect()
            
            if await self.client.is_user_authorized():
                self.is_connected = True
                me = await self.client.get_me()
                logger.info(f"✅ Telegram Connected as: {me.first_name}")

                # Register the Listener specifically for the RESULT GROUP
                self.client.add_event_handler(
                    self._on_result_message,
                    events.NewMessage(chats=RESULT_GROUP_ID)
                )
                logger.info(f"👀 Monitoring Result Group: {RESULT_GROUP_ID}")
                
                # Warm up cache for the Command Group
                try:
                    await self.client.get_entity(COMMAND_GROUP_ID)
                    logger.info(f"✅ Command Group Resolved: {COMMAND_GROUP_ID}")
                except Exception as e:
                    logger.error(f"⚠️ Could not resolve Command Group: {e}")

            else:
                logger.warning("⚠️ Session Invalid. Login required.")

        except Exception as e:
            logger.error(f"❌ Client Init Failed: {e}")

    # --- THE LISTENER (Result Group) ---
    async def _on_result_message(self, event):
        """
        Triggered ONLY when a new message appears in RESULT_GROUP_ID (7748071327).
        """
        if not self.pending_request or self.pending_request.done():
            return

        logger.info(f"📩 Result Group Message Detected: {event.message.id}")
        
        try:
            # 1. Detect Button
            if not event.message.buttons:
                logger.info("ℹ️ Message has no buttons. Ignoring.")
                return

            logger.info("🔘 Buttons found. Looking for 'Abrir resultado'...")

            # 2. Click/Resolve the Button
            # This simulates a user click. It returns the URL if it's a URL button.
            clicked = await event.message.click(text="Abrir resultado")
            
            final_url = None
            
            # Case A: Direct URL return
            if isinstance(clicked, str):
                final_url = clicked
            
            # Case B: Standard URL Button extraction
            if not final_url:
                # Iterate rows and buttons to find the specific URL
                for row in event.message.buttons:
                    for btn in row:
                        if btn.text == "Abrir resultado" and hasattr(btn, 'url'):
                            final_url = btn.url
                            break
            
            # 3. Extract & Finish
            if final_url:
                logger.info(f"🔗 Link Extracted: {final_url}")
                data = self._scrape_content(final_url)
                self.pending_request.set_result(data)
                logger.info("✅ Result returned to backend.")
            else:
                logger.warning("❌ 'Abrir resultado' button found but had no URL.")

        except Exception as e:
            logger.error(f"❌ Error processing result message: {e}")
            if not self.pending_request.done():
                self.pending_request.set_exception(e)

    def _scrape_content(self, url):
        """Helper to fetch the actual text content from the link."""
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            resp = requests.get(url, headers=headers, timeout=10)
            if resp.status_code == 200:
                # Return first 2000 chars to avoid payload limits
                return resp.text[:2000]
            return f"Erro HTTP {resp.status_code}"
        except Exception as e:
            return f"Erro de conexão: {str(e)}"

    # --- THE SENDER (Command Group) ---
    async def _execute_flow(self, command):
        """
        1. Setup Future.
        2. Send Command to Group A.
        3. Wait for Listener in Group B.
        """
        if not self.is_connected:
            return "Erro: Telegram não conectado."

        # Reset any previous pending request
        loop = asyncio.get_running_loop()
        self.pending_request = loop.create_future()

        try:
            # 1. Send Command (Group A)
            logger.info(f"📤 Sending command '{command}' to Group {COMMAND_GROUP_ID}")
            await self.client.send_message(COMMAND_GROUP_ID, command)
            
            # 2. Wait for Result (Group B)
            logger.info("⏳ Waiting for result in Group B...")
            result = await asyncio.wait_for(self.pending_request, timeout=15.0)
            return result

        except asyncio.TimeoutError:
            logger.error("❌ Timeout waiting for result.")
            self.pending_request = None
            return "Erro: O bot demorou muito para responder (Timeout)."
        except Exception as e:
            logger.error(f"❌ Execution Error: {e}")
            self.pending_request = None
            return f"Erro interno: {str(e)}"

    # --- BRIDGE TO FLASK ---
    def process_command_sync(self, command):
        future = asyncio.run_coroutine_threadsafe(
            self._execute_flow(command), 
            self.loop
        )
        return future.result()

    # --- AUTH HELPERS ---
    def request_code_sync(self, phone):
        async def _do():
            self.phone = phone
            s = await self.client.send_code_request(phone)
            self.phone_code_hash = s.phone_code_hash
            return {"status": "sent"}
        return asyncio.run_coroutine_threadsafe(_do(), self.loop).result()

    def login_sync(self, code):
        async def _do():
            await self.client.sign_in(self.phone, code, phone_code_hash=self.phone_code_hash)
            self.is_connected = True
            return {"status": "success", "session": self.client.session.save()}
        return asyncio.run_coroutine_threadsafe(_do(), self.loop).result()

# Init Singleton
tg = TelegramManager()
tg.start()

# --- FLASK ---

@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

@app.route('/perguntar', methods=['POST'])
def ask():
    data = request.json
    prompt = data.get('pergunta', '').strip()
    
    if not prompt: return jsonify({'resposta': '...'}), 400

    # Execute deterministic flow
    # This sends to Group A, waits for Group B, returns result.
    response_text = tg.process_command_sync(prompt)
    
    return jsonify({'resposta': response_text})

@app.route('/auth/send_code', methods=['POST'])
def send_code():
    return jsonify(tg.request_code_sync(request.json.get('phone')))

@app.route('/auth/login', methods=['POST'])
def login():
    return jsonify(tg.login_sync(request.json.get('code')))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
