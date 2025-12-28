import asyncio
import os
import threading
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession

# ============ CONFIGURAÇÕES INICIAIS ============
app = Flask(__name__, static_folder='public')
CORS(app)

api_id = 34303434
api_hash = '5d521f53f9721a6376586a014b51173d'
target_chat = -1002421438612
bot_confiavel = '@QueryBuscasBot'

# Variáveis globais de controle
SESSION_STRING = os.environ.get('SESSION_STRING', '')
phone_code_hash = None
temp_phone = None

# Criação do loop global único
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# Inicializa o cliente Telethon
if SESSION_STRING:
    client = TelegramClient(StringSession(SESSION_STRING), api_id, api_hash, loop=loop)
else:
    client = TelegramClient(StringSession(), api_id, api_hash, loop=loop)

# ============ LÓGICA DE BUSCA (ASYNC) ============
async def buscar_no_telegram_async(mensagem_usuario):
    if not client.is_connected():
        await client.connect()
    
    if not await client.is_user_authorized():
        return "❌ Usuário não autenticado. Faça login primeiro."

    entity = await client.get_entity(target_chat)
    bot_entity = await client.get_entity(bot_confiavel)
    comando = mensagem_usuario if mensagem_usuario.startswith('/') else f"/{mensagem_usuario}"
    
    # Future para aguardar a resposta do bot alvo
    resposta_final = loop.create_future()
    
    @client.on(events.NewMessage(chats=entity))
    async def handler(event):
        if event.message.document and event.sender_id == bot_entity.id:
            path = await event.download_media()
            conteudo = ""
            if path and path.endswith('.txt'):
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    conteudo = f.read()
                # Filtragem de publicidade
                linhas = [l for l in conteudo.split('\n') if '@QueryBuscasBot' not in l and 't.me/' not in l]
                conteudo = '\n'.join(linhas).strip()
                if os.path.exists(path): os.remove(path)
            
            client.remove_event_handler(handler)
            if not resposta_final.done():
                resposta_final.set_result(conteudo)
    
    await client.send_message(entity, comando)
    
    try:
        return await asyncio.wait_for(resposta_final, timeout=45)
    except asyncio.TimeoutError:
        client.remove_event_handler(handler)
        return "⏱️ Tempo esgotado. O bot não respondeu a tempo."

# ============ ROTAS DA API (FLASK) ============

@app.route('/auth/status')
def auth_status():
    is_auth = asyncio.run_coroutine_threadsafe(client.is_user_authorized(), loop).result()
    return jsonify({'logged_in': is_auth})

@app.route('/auth/send_code', methods=['POST'])
def send_code():
    global phone_code_hash, temp_phone
    phone = request.json.get('phone')
    try:
        if not client.is_connected():
            asyncio.run_coroutine_threadsafe(client.connect(), loop).result()
        
        result = asyncio.run_coroutine_threadsafe(client.send_code_request(phone), loop).result()
        phone_code_hash = result.phone_code_hash
        temp_phone = phone
        return jsonify({'status': 'sent'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/auth/login', methods=['POST'])
def login():
    global phone_code_hash, temp_phone
    dados = request.json
    code, password = dados.get('code'), dados.get('password', '')
    try:
        try:
            asyncio.run_coroutine_threadsafe(
                client.sign_in(phone=temp_phone, code=code, phone_code_hash=phone_code_hash), loop
            ).result()
        except errors.SessionPasswordNeededError:
            if not password: return jsonify({'status': '2fa_required'})
            asyncio.run_coroutine_threadsafe(client.sign_in(password=password), loop).result()
        
        return jsonify({'status': 'success', 'session_string': client.session.save()})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/perguntar', methods=['POST'])
def perguntar():
    pergunta = request.json.get('pergunta', '')
    try:
        # Envia a tarefa para o loop do Telethon que está em outra thread
        fut = asyncio.run_coroutine_threadsafe(buscar_no_telegram_async(pergunta), loop)
        resposta = fut.result(timeout=50) 
        return jsonify({'resposta': resposta})
    except Exception as e:
        return jsonify({'resposta': f'❌ Erro: {str(e)}'}), 500

@app.route('/')
def index(): return send_from_directory('public', 'index.html')

@app.route('/<path:path>')
def serve_static(path): return send_from_directory('public', path)

# ============ INICIALIZAÇÃO MULTI-THREAD ============
def start_telethon():
    """Roda o loop do Telethon permanentemente"""
    asyncio.set_event_loop(loop)
    loop.run_forever()

if __name__ == '__main__':
    # Inicia o Telethon em uma thread separada
    t = threading.Thread(target=start_telethon, daemon=True)
    t.start()
    
    # Inicia o Flask na thread principal
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
