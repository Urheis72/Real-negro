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

# Credenciais
API_ID = 34303434
API_HASH = '5d521f53f9721a6376586a014b51173d'
TARGET_CHAT = -1002421438612 # Grupo alvo
BOT_BUSCA = '@QueryBuscasBot' # Bot de busca
GEMINI_KEY = "AIzaSyA9a8QscXbFVLcVn6slY5ddmCHbpmQ5oFY"

# Clientes
genai_client = genai.Client(api_key=GEMINI_KEY)
SESSION_STRING = os.environ.get('SESSION_STRING', '')

# Loop de Eventos Global
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

if SESSION_STRING:
    client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH, loop=loop)
else:
    client = TelegramClient(StringSession(), API_ID, API_HASH, loop=loop)

# ============ LÓGICA DE NEGÓCIO ============
async def enviar_telegram(mensagem):
    """Envia mensagem direta para o grupo (começa com /)"""
    if not client.is_connected(): await client.connect()
    await client.send_message(TARGET_CHAT, mensagem)
    return "Comando enviado com sucesso."

async def buscar_e_processar(pergunta):
    """Busca no bot, pega o TXT e passa para o Gemini"""
    if not client.is_connected(): await client.connect()
    
    entity = await client.get_entity(TARGET_CHAT)
    bot = await client.get_entity(BOT_BUSCA)
    
    # Future para aguardar a resposta do arquivo
    resposta_futura = loop.create_future()

    @client.on(events.NewMessage(chats=entity))
    async def handler(event):
        if event.message.document and event.sender_id == bot.id:
            path = await event.download_media()
            texto_arquivo = ""
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    texto_arquivo = f.read()
            finally:
                if os.path.exists(path): os.remove(path)
            
            client.remove_event_handler(handler)
            if not resposta_futura.done():
                resposta_futura.set_result(texto_arquivo)

    # Envia o comando de busca
    msg_comando = pergunta if pergunta.startswith('/') else f"/{pergunta}"
    await client.send_message(entity, msg_comando)

    try:
        # Espera o arquivo por até 40s
        contexto = await asyncio.wait_for(resposta_futura, timeout=40)
    except asyncio.TimeoutError:
        client.remove_event_handler(handler)
        contexto = "Nenhuma informação encontrada no banco de dados."

    return contexto

# ============ ROTAS ============
@app.route('/perguntar', methods=['POST'])
def perguntar():
    dados = request.json
    msg = dados.get('pergunta', '').strip()
    
    if not msg: return jsonify({'resposta': 'Por favor, fale algo.'})

    # Rota 1: Comando Direto (começa com /)
    if msg.startswith('/'):
        asyncio.run_coroutine_threadsafe(enviar_telegram(msg), loop)
        return jsonify({'resposta': f'✅ Comando "{msg}" executado.'})

    # Rota 2: Inteligência Artificial
    try:
        # Busca contexto no Telegram
        fut = asyncio.run_coroutine_threadsafe(buscar_e_processar(msg), loop)
        contexto = fut.result(timeout=45)
        
        # Processa no Gemini
        prompt = f"""
        Você é o J.A.R.V.I.S. Responda de forma executiva, direta e em Português.
        PERGUNTA DO USUÁRIO: {msg}
        DADOS ENCONTRADOS NO SISTEMA: {contexto}
        """
        response = genai_client.models.generate_content(model="gemini-2.0-flash-exp", contents=prompt)
        return jsonify({'resposta': response.text})
        
    except Exception as e:
        return jsonify({'resposta': f'⚠️ Erro no processamento: {str(e)}'})

# Rotas de Autenticação (Login)
@app.route('/auth/send_code', methods=['POST'])
def send_code():
    phone = request.json.get('phone')
    if not client.is_connected(): asyncio.run_coroutine_threadsafe(client.connect(), loop).result()
    res = asyncio.run_coroutine_threadsafe(client.send_code_request(phone), loop).result()
    global phone_hash, temp_phone
    phone_hash = res.phone_code_hash
    temp_phone = phone
    return jsonify({'status': 'sent'})

@app.route('/auth/login', methods=['POST'])
def login():
    code = request.json.get('code')
    password = request.json.get('password', '')
    try:
        try:
            asyncio.run_coroutine_threadsafe(client.sign_in(temp_phone, code, phone_code_hash=phone_hash), loop).result()
        except errors.SessionPasswordNeededError:
            asyncio.run_coroutine_threadsafe(client.sign_in(password=password), loop).result()
        return jsonify({'status': 'success', 'session': client.session.save()})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/')
def index(): return send_from_directory('public', 'index.html')

# Inicialização
def start_bot():
    asyncio.set_event_loop(loop)
    loop.run_forever()

if __name__ == '__main__':
    threading.Thread(target=start_bot, daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
