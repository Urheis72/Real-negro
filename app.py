import asyncio
import os
import threading
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from google import genai

# ============ CONFIGURAÇÕES ============
app = Flask(__name__, static_folder='public')
CORS(app)

# Telegram
api_id = 34303434
api_hash = '5d521f53f9721a6376586a014b51173d'
target_chat = -1002421438612
bot_confiavel = '@QueryBuscasBot'

# Gemini AI (Sua Key)
GEMINI_API_KEY = "AIzaSyA9a8QscXbFVLcVn6slY5ddmCHbpmQ5oFY"
genai_client = genai.Client(api_key=GEMINI_API_KEY)

SESSION_STRING = os.environ.get('SESSION_STRING', '')
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

client = TelegramClient(StringSession(SESSION_STRING), api_id, api_hash, loop=loop)

# ============ IA: GEMINI ============
def processar_com_gemini(pergunta, contexto):
    try:
        prompt = f"Você é o Jarvis. Responda à pergunta: '{pergunta}'. Use este contexto se útil: {contexto}"
        response = genai_client.models.generate_content(model="gemini-2.0-flash-exp", contents=prompt)
        return response.text
    except:
        return "Erro ao processar com Gemini."

# ============ BUSCA TELEGRAM ============
async def buscar_telegram(msg_usuario):
    if not client.is_connected(): await client.connect()
    if not await client.is_user_authorized(): return "ERRO_AUTH"
    
    entity = await client.get_entity(target_chat)
    bot_entity = await client.get_entity(bot_confiavel)
    resposta_fut = loop.create_future()

    @client.on(events.NewMessage(chats=entity))
    async def handler(event):
        if event.message.document and event.sender_id == bot_entity.id:
            path = await event.download_media()
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            os.remove(path)
            client.remove_event_handler(handler)
            if not resposta_fut.done(): resposta_fut.set_result(content)

    await client.send_message(entity, f"/{msg_usuario}")
    try: return await asyncio.wait_for(resposta_fut, timeout=40)
    except: return ""

# ============ ROTAS API ============
@app.route('/perguntar', methods=['POST'])
def perguntar():
    pergunta = request.json.get('pergunta', '')
    fut = asyncio.run_coroutine_threadsafe(buscar_telegram(pergunta), loop)
    contexto = fut.result(timeout=45)
    resposta_final = processar_com_gemini(pergunta, contexto)
    return jsonify({'resposta': resposta_final})

@app.route('/auth/status')
def status():
    is_auth = asyncio.run_coroutine_threadsafe(client.is_user_authorized(), loop).result()
    return jsonify({'logged_in': is_auth})

@app.route('/auth/send_code', methods=['POST'])
def send_code():
    p = request.json.get('phone')
    if not client.is_connected(): asyncio.run_coroutine_threadsafe(client.connect(), loop).result()
    res = asyncio.run_coroutine_threadsafe(client.send_code_request(p), loop).result()
    global phash, pnum; phash = res.phone_code_hash; pnum = p
    return jsonify({'status': 'sent'})

@app.route('/auth/login', methods=['POST'])
def login():
    d = request.json; c = d.get('code'); pwd = d.get('password', '')
    try:
        asyncio.run_coroutine_threadsafe(client.sign_in(pnum, c, phone_code_hash=phash), loop).result()
    except errors.SessionPasswordNeededError:
        asyncio.run_coroutine_threadsafe(client.sign_in(password=pwd), loop).result()
    return jsonify({'status': 'success', 'session_string': client.session.save()})

@app.route('/')
def index(): return send_from_directory('public', 'index.html')

def start_telethon():
    asyncio.set_event_loop(loop)
    loop.run_forever()

if __name__ == '__main__':
    threading.Thread(target=start_telethon, daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
