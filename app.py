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

# --- CONFIGURATION ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    level=logging.INFO
)
logger = logging.getLogger("JarvisBackend")

# Secrets (Ensure these are set in your Environment Variables)
API_ID = int(os.environ.get("API_ID", "34303434"))
API_HASH = os.environ.get("API_HASH", "5d521f53f9721a6376586a014b51173d")
SESSION_STRING = os.environ.get('SESSION_STRING', '')

# IDs from your screenshots and instructions
COMMAND_GROUP_ID = -1002421438612 
RESULT_GROUP_ID = 7748071327 

app = Flask(__name__, static_folder='public')
CORS(app)

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
        """Starts the Telegram thread and waits for it to be ready."""
        t = threading.Thread(target=self._run_loop, daemon=True)
        t.start()
        # Wait up to 30 seconds for connection before letting Flask start
        ready = self.is_ready.wait(timeout=30)
        if not ready:
            logger.error("❌ Telegram failed to initialize in time.")
        else:
            logger.info("✅ Telegram Manager is fully synchronized.")

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._init_client())
        self.loop.run_forever()

    async def _init_client(self):
        try:
            session = StringSession(SESSION_STRING)
            self.client = TelegramClient(session, API_ID, API_HASH, loop=self.loop)
            await self.client.connect()
            
            # Global result listener (monitoring Group 7748071327)
            self.client.add_event_handler(
                self._on_result_message,
                events.NewMessage(chats=RESULT_GROUP_ID)
            )
            
            # Monitor DMs as fallback (based on Screenshot_20251229-164846_1.jpg)
            self.client.add_event_handler(
                self._on_result_message,
                events.NewMessage(incoming=True, func=lambda e: e.is_private)
            )

            authorized = await self.client.is_user_authorized()
            logger.info(f"Telegram Connection: {'AUTHORIZED' if authorized else 'WAITING FOR LOGIN'}")
            self.is_ready.set()
        except Exception as e:
            logger.error(f"Initialization Error: {e}")
            self.is_ready.set() # Release block even on error to see logs

    async def _on_result_message(self, event):
        """Processes messages from the result group or private DMs."""
        if not self.pending_request or self.pending_request.done():
            return

        # Handle the "Abrir resultado" button logic
        if event.message.buttons:
            for row in event.message.buttons:
                for btn in row:
                    if "Abrir resultado" in btn.text:
                        logger.info("🔘 Detected result button. Extracting link...")
                        # Telethon .click() on a URL button returns the URL string
                        link = await event.message.click(btn)
                        if isinstance(link, str):
                            data = self._fetch_external_data(link)
                            self.pending_request.set_result(data)
                            return

    def _fetch_external_data(self, url):
        """Scrapes the final result from the fdxapis.us link."""
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            r = requests.get(url, headers=headers, timeout=10)
            return r.text[:2500] if r.status_code == 200 else f"Erro Link: {r.status_code}"
        except Exception as e:
            return f"Erro na extração: {str(e)}"

    async def _execute_command(self, cmd):
        if not await self.client.is_user_authorized():
            return "Erro: Sistema não autenticado. Faça login no Telegram."
        
        self.pending_request = self.loop.create_future()
        try:
            # Send to Command Group
            await self.client.send_message(COMMAND_GROUP_ID, cmd)
            # Wait for Result Group Listener
            return await asyncio.wait_for(self.pending_request, timeout=20.0)
        except asyncio.TimeoutError:
            return "Erro: O bot não enviou o resultado no tempo limite."
        except Exception as e:
            return f"Erro: {str(e)}"

    # --- Sync Wrappers ---
    def run_command(self, cmd):
        return asyncio.run_coroutine_threadsafe(self._execute_command(cmd), self.loop).result()

    def send_auth_code(self, phone):
        async def _f():
            self.phone = phone
            res = await self.client.send_code_request(phone)
            self.hash = res.phone_code_hash
            return {"status": "sent"}
        return asyncio.run_coroutine_threadsafe(_f(), self.loop).result()

    def finalize_login(self, code):
        async def _f():
            await self.client.sign_in(self.phone, code, phone_code_hash=self.hash)
            return {"status": "success", "session": self.client.session.save()}
        return asyncio.run_coroutine_threadsafe(_f(), self.loop).result()

# Boot
tg = TelegramManager()
tg.start()

# --- ROUTES ---
@app.route('/')
def home(): return send_from_directory('public', 'index.html')

@app.route('/perguntar', methods=['POST'])
def ask():
    cmd = request.json.get('pergunta', '')
    if not cmd.startswith('/'):
        return jsonify({'resposta': 'Por favor, envie um comando válido (ex: /buscar nome).'})
    return jsonify({'resposta': tg.run_command(cmd)})

@app.route('/auth/send_code', methods=['POST'])
def auth_s(): return jsonify(tg.send_auth_code(request.json.get('phone')))

@app.route('/auth/login', methods=['POST'])
def auth_l(): return jsonify(tg.finalize_login(request.json.get('code')))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, use_reloader=False)
            
