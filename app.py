import asyncio
import os
import threading
import logging
import re
import requests
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from telethon import TelegramClient, events, Button
from telethon.sessions import StringSession
from telethon.tl.custom import Message
from telethon.errors import FloodWaitError

# --- CONFIGURATION ---
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

# NEW BOT & GROUP CONFIGURATION
BOT_USERNAME = "@SantSearchhBot" 
# Note: Ensure this ID is correct. If it's a supergroup, it might need -100 prefix.
# Used the exact ID provided in instructions.
RESULT_GROUP_ID = int(os.environ.get("RESULT_GROUP_ID", "7748071327")) 

app = Flask(__name__, static_folder='public')
CORS(app)

# --- TELEGRAM AUTOMATION MANAGER ---
class TelegramManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TelegramManager, cls).__new__(cls)
            cls._instance.loop = asyncio.new_event_loop()
            cls._instance.client = None
            cls._instance.is_connected = False
            cls._instance.pending_requests = {} # Map to store Futures for async results
        return cls._instance

    def start(self):
        t = threading.Thread(target=self._run_loop, daemon=True)
        t.start()
        logger.info("Background AsyncIO Thread Started")
        asyncio.run_coroutine_threadsafe(self._init_client(), self.loop)

    def _run_loop(self):
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    async def _init_client(self):
        try:
            session = StringSession(SESSION_STRING)
            self.client = TelegramClient(session, API_ID, API_HASH, loop=self.loop)
            await self.client.connect()
            
            if await self.client.is_user_authorized():
                self.is_connected = True
                me = await self.client.get_me()
                logger.info(f"✅ Telegram Connected as: {me.first_name}")
                
                # Pre-resolve entities to ensure we can send/read immediately
                logger.info("Resolving entities...")
                try:
                    await self.client.get_input_entity(BOT_USERNAME)
                    # Try resolving the group. If it fails, we might need to join it or check the ID.
                    # We continue even if this fails to allow runtime resolution.
                    await self.client.get_input_entity(RESULT_GROUP_ID)
                except Exception as e:
                    logger.warning(f"Entity resolution warning: {e}")

                # REGISTER LISTENERS
                self.client.add_event_handler(
                    self._handle_group_response, 
                    events.NewMessage(chats=RESULT_GROUP_ID)
                )
            else:
                logger.warning("⚠️ Login Required")

        except Exception as e:
            logger.error(f"❌ Client Init Error: {e}")

    # --- CORE EVENT LISTENER ---
    async def _handle_group_response(self, event):
        """
        Listens to the RESULT_GROUP_ID.
        When a message arrives, checks if it relates to a pending request.
        """
        # In a real high-traffic scenario, we would match IDs/Usernames.
        # For this implementation, we assume the latest message corresponds to the latest request (LIFO).
        if not self.pending_requests:
            return

        logger.info("📩 New message detected in Result Group")
        
        # We pick the oldest pending future to resolve (FIFO queue behavior)
        # Or simplistic: just pick the first one waiting.
        future = list(self.pending_requests.values())[0]
        
        try:
            # 1. Check for Buttons
            if event.message.buttons:
                logger.info("🔘 Buttons detected. Searching for 'Abrir resultado'...")
                
                # 2. Click the specific button
                # We assume the button triggers a callback or opens a URL directly
                # click() returns the result of the interaction
                # If the button is a URL button, it returns the URL string.
                # If it's a callback, it might edit the message.
                
                clicked_result = await event.message.click(text="Abrir resultado")
                
                final_url = None

                # Case A: click() returned a URL string directly (UrlButton)
                if isinstance(clicked_result, str):
                    final_url = clicked_result
                
                # Case B: It was a Callback button that edited the message or sent a new one
                # We might need to check the message again or the return object
                elif hasattr(clicked_result, 'message'):
                    # Sometimes the bot edits the message to show the link
                    final_url = self._extract_url_from_text(clicked_result.message)
                
                # Case C: Fallback - Scan the original message text if click didn't return URL
                if not final_url:
                    final_url = self._extract_url_from_text(event.message.message)
                
                if final_url:
                    logger.info(f"🔗 Link Found: {final_url}")
                    
                    # 3. Extract Data from Link
                    extracted_data = self._fetch_url_content(final_url)
                    
                    if not future.done():
                        future.set_result(extracted_data)
                        # Clean up
                        self.pending_requests.popitem()
                else:
                    logger.warning("No URL found after clicking button.")
            else:
                # No buttons, maybe the result is text-only?
                if not future.done():
                    future.set_result(event.message.message)
                    self.pending_requests.popitem()

        except Exception as e:
            logger.error(f"Error handling group response: {e}")
            if not future.done():
                future.set_exception(e)
                self.pending_requests.popitem()

    def _extract_url_from_text(self, text):
        """Regex to find http/https links"""
        url_match = re.search(r'(https?://[^\s]+)', text)
        return url_match.group(0) if url_match else None

    def _fetch_url_content(self, url):
        """Fetches the final result from the external link"""
        try:
            logger.info(f"🌍 Fetching content from: {url}")
            # Add headers to mimic a browser, avoiding some bot protections
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                # Return the text content. You might want to strip HTML tags if it's raw HTML.
                # For now, we return specific parts or the whole text.
                # Assuming the result is plain text or JSON on that page.
                return response.text[:2000] # Limit size
            else:
                return f"Erro ao acessar link: HTTP {response.status_code}"
        except Exception as e:
            return f"Falha na extração do link: {str(e)}"

    # --- PUBLIC METHODS ---

    async def _process_command_flow(self, command):
        """
        Full Async Flow: Send -> Wait -> Click -> Extract -> Return
        """
        if not self.is_connected:
            return "Erro: Sistema offline. Tente reconectar."

        # Create a Future to wait for the result
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        
        # Store future with a key (could use command ID, here using simple key)
        request_id = "req_latest"
        self.pending_requests[request_id] = future

        try:
            # 1. Send Command to Bot
            logger.info(f"📤 Sending command '{command}' to {BOT_USERNAME}")
            await self.client.send_message(BOT_USERNAME, command)

            # 2. Wait for the Event Handler to resolve the future
            # Timeout after 15 seconds to prevent hanging
            result = await asyncio.wait_for(future, timeout=20.0)
            return result

        except asyncio.TimeoutError:
            self.pending_requests.pop(request_id, None)
            return "Erro: Tempo limite excedido. O bot não respondeu ou o botão não foi encontrado."
        except Exception as e:
            self.pending_requests.pop(request_id, None)
            return f"Erro processando comando: {str(e)}"

    def execute_command_sync(self, command):
        """Thread-safe wrapper for Flask"""
        future = asyncio.run_coroutine_threadsafe(
            self._process_command_flow(command), 
            self.loop
        )
        try:
            return future.result()
        except Exception as e:
            return str(e)

    # --- AUTH METHODS (Kept from previous version) ---
    def request_code_sync(self, phone):
        async def _req():
            try:
                self.phone = phone
                sent = await self.client.send_code_request(phone)
                self.phone_code_hash = sent.phone_code_hash
                return {"status": "sent"}
            except Exception as e: return {"status": "error", "error": str(e)}
        return asyncio.run_coroutine_threadsafe(_req(), self.loop).result()

    def login_sync(self, code):
        async def _log():
            try:
                await self.client.sign_in(self.phone, code, phone_code_hash=self.phone_code_hash)
                self.is_connected = True
                return {"status": "success", "session": self.client.session.save()}
            except Exception as e: return {"status": "error", "error": str(e)}
        return asyncio.run_coroutine_threadsafe(_log(), self.loop).result()

# Init
tg = TelegramManager()
tg.start()

# --- FLASK ENDPOINTS ---

@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

@app.route('/perguntar', methods=['POST'])
def perguntar():
    data = request.json
    pergunta = data.get('pergunta', '').strip()

    if not pergunta:
        return jsonify({'resposta': 'Comando vazio.'}), 400

    # Execute the new flow for every message (assuming all are commands for the bot)
    # If you want to distinguish between AI chat and Bot commands, keep the "/" check.
    # Currently, adapting to user request: "Bot migration... Commands sent exactly as before"
    
    if pergunta.startswith('/'):
        # NEW FLOW: Send to Bot -> Wait for Group -> Extract
        logger.info(f"Processing Bot Command: {pergunta}")
        resultado = tg.execute_command_sync(pergunta)
        return jsonify({'resposta': resultado})
    
    # Fallback to AI for non-commands (optional, based on previous prompt)
    try:
        # Simple AI response for chat
        return jsonify({'resposta': f"Jarvis: Você disse '{pergunta}'. Para buscar dados, use comandos iniciados com /."})
    except:
        return jsonify({'resposta': 'Erro interno.'}), 500

# Auth Endpoints
@app.route('/auth/send_code', methods=['POST'])
def send_code():
    return jsonify(tg.request_code_sync(request.json.get('phone')))

@app.route('/auth/login', methods=['POST'])
def login():
    return jsonify(tg.login_sync(request.json.get('code')))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
