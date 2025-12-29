import asyncio
import os
import threading
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from telethon import TelegramClient, errors
from telethon.sessions import StringSession

app = Flask(__name__, static_folder='public')
CORS(app)

# --- CONFIGURAÇÕES ---
API_ID = 34303434
API_HASH = '5d521f53f9721a6376586a014b51173d'

# Variáveis globais de controle de sessão
phone_code_hash = None
temp_phone = None
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

# Inicializa o cliente sem travar
SESSION_STRING = os.environ.get('SESSION_STRING', '')
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH, loop=loop)

# --- ROTA DE ENVIO DE CÓDIGO (CORRIGIDA) ---
@app.route('/auth/send_code', methods=['POST'])
def send_code():
    global phone_code_hash, temp_phone
    data = request.json
    phone = data.get('phone', '').strip()
    
    # Remove espaços, parênteses e traços (Deixa apenas + e números)
    phone = ''.join(c for c in phone if c.isdigit() or c == '+')
    
    if not phone.startswith('+'):
        return jsonify({'error': 'O número deve começar com + e o código do país (ex: +55...)'}), 400

    try:
        # Garante que o cliente está conectado antes de pedir o código
        if not client.is_connected():
            print("Conectando ao Telegram...")
            asyncio.run_coroutine_threadsafe(client.connect(), loop).result()
        
        print(f"Solicitando código para: {phone}")
        # Envia a requisição de código
        result = asyncio.run_coroutine_threadsafe(client.send_code_request(phone), loop).result()
        
        phone_code_hash = result.phone_code_hash
        temp_phone = phone
        
        print("Código enviado com sucesso pelo Telegram!")
        return jsonify({'status': 'sent'})

    except errors.FloodWaitError as e:
        return jsonify({'error': f'Muitas tentativas. Aguarde {e.seconds} segundos.'}), 429
    except Exception as e:
        print(f"Erro fatal no envio: {str(e)}")
        return jsonify({'error': str(e)}), 500

# --- ROTA DE LOGIN ---
@app.route('/auth/login', methods=['POST'])
def login():
    global phone_code_hash, temp_phone
    data = request.json
    code = data.get('code', '').strip()
    
    try:
        print(f"Tentando login com código: {code}")
        asyncio.run_coroutine_threadsafe(
            client.sign_in(phone=temp_phone, code=code, phone_code_hash=phone_code_hash), loop
        ).result()
        
        # Se logou, gera a string de sessão para você salvar no Render
        new_session = client.session.save()
        print("Login realizado com sucesso!")
        return jsonify({'status': 'success', 'session_string': new_session})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/')
def index(): return send_from_directory('public', 'index.html')

def start_telegram_loop():
    asyncio.set_event_loop(loop)
    loop.run_forever()

if __name__ == '__main__':
    t = threading.Thread(target=start_telegram_loop, daemon=True)
    t.start()
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
