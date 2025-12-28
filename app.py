import asyncio
import os
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession

app = Flask(__name__, static_folder='public')
CORS(app)

# ============ CONFIGURAÇÕES ============
api_id = 34303434
api_hash = '5d521f53f9721a6376586a014b51173d'
target_chat = -1002421438612
bot_confiavel = '@QueryBuscasBot'

# Tenta pegar da variável de ambiente (Render) ou string vazia
SESSION_STRING = os.environ.get('SESSION_STRING', '')

# Variáveis globais para controlar o estado do login
phone_code_hash = None
temp_phone = None

# Inicializa o cliente
if SESSION_STRING:
    client = TelegramClient(StringSession(SESSION_STRING), api_id, api_hash)
else:
    client = TelegramClient(StringSession(), api_id, api_hash)

# Função auxiliar para rodar async no Flask
def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# ============ ROTAS DE AUTENTICAÇÃO (LOGIN VIA WEB) ============

@app.route('/auth/status')
def auth_status():
    """Verifica se já está logado"""
    try:
        is_connected = client.is_connected()
        if not is_connected:
            run_async(client.connect())
        
        is_authorized = run_async(client.is_user_authorized())
        return jsonify({'logged_in': is_authorized})
    except Exception as e:
        return jsonify({'logged_in': False, 'error': str(e)})

@app.route('/auth/send_code', methods=['POST'])
def send_code():
    """Passo 1: Recebe o número e pede pro Telegram enviar o código"""
    global phone_code_hash, temp_phone
    dados = request.json
    phone = dados.get('phone')
    
    if not phone:
        return jsonify({'error': 'Telefone obrigatório'}), 400

    try:
        if not client.is_connected():
            run_async(client.connect())
            
        send_code_result = run_async(client.send_code_request(phone))
        phone_code_hash = send_code_result.phone_code_hash
        temp_phone = phone
        
        return jsonify({'status': 'sent', 'message': 'Código enviado para o Telegram/SMS'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/auth/login', methods=['POST'])
def login():
    """Passo 2: Recebe o código e a senha 2FA (se houver)"""
    global phone_code_hash, temp_phone
    dados = request.json
    code = dados.get('code')
    password = dados.get('password', '') # Opcional

    if not code:
        return jsonify({'error': 'Código obrigatório'}), 400

    try:
        # Tenta logar
        try:
            run_async(client.sign_in(phone=temp_phone, code=code, phone_code_hash=phone_code_hash))
        except errors.SessionPasswordNeededError:
            # Se precisar de senha 2FA
            if not password:
                return jsonify({'status': '2fa_required'}), 200
            run_async(client.sign_in(password=password))
        
        # Se chegou aqui, logou com sucesso
        new_session = client.session.save()
        
        return jsonify({
            'status': 'success', 
            'session_string': new_session,
            'message': 'Login realizado com sucesso! Copie a Session String.'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# ============ ROTAS DO CHAT (IGUAL ANTES) ============

async def buscar_no_telegram(mensagem_usuario):
    # Lógica idêntica ao seu código original, apenas garantindo conexão
    if not client.is_connected():
        await client.connect()
        
    if not await client.is_user_authorized():
        return "❌ ERRO: Servidor não autenticado no Telegram. Faça login na tela inicial."

    entity = await client.get_entity(target_chat)
    bot_entity = await client.get_entity(bot_confiavel)
    comando = mensagem_usuario if mensagem_usuario.startswith('/') else f"/{mensagem_usuario}"
    resposta_final = asyncio.Future()
    
    @client.on(events.NewMessage(chats=entity))
    async def handler(event):
        if event.message.document and event.sender_id == bot_entity.id:
            path = await event.download_media()
            conteudo = ""
            if path and path.endswith('.txt'):
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    conteudo = f.read()
                # Limpeza básica
                linhas = [l for l in conteudo.split('\n') if '@QueryBuscasBot' not in l and 'http' not in l]
                conteudo = '\n'.join(linhas).strip()
                try: os.remove(path)
                except: pass
            else:
                conteudo = "Arquivo recebido, mas não é texto."
            
            client.remove_event_handler(handler)
            if not resposta_final.done():
                resposta_final.set_result(conteudo)

    await client.send_message(entity, comando)
    
    try:
        return await asyncio.wait_for(resposta_final, timeout=45)
    except asyncio.TimeoutError:
        client.remove_event_handler(handler)
        return "⏱️ Timeout."
    except Exception as e:
        client.remove_event_handler(handler)
        return f"❌ Erro: {str(e)}"

@app.route('/perguntar', methods=['POST'])
def perguntar():
    dados = request.json
    pergunta = dados.get('pergunta', '')
    if not pergunta: return jsonify({'resposta': '❌ Vazio'}), 400
    
    try:
        resposta = run_async(buscar_no_telegram(pergunta))
        return jsonify({'resposta': resposta})
    except Exception as e:
        return jsonify({'resposta': f'❌ Erro: {str(e)}'}), 500

# Rotas de Arquivos Estáticos
@app.route('/')
def index(): return send_from_directory('public', 'index.html')

@app.route('/<path:path>')
def serve_static(path): return send_from_directory('public', path)

if __name__ == '__main__':
    # Tenta conectar ao iniciar para ver se a session string salva funciona
    try:
        run_async(client.connect())
    except:
        pass
    
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))