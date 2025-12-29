import asyncio
import os
import threading
import base64
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from google import genai
from elevenlabs.client import ElevenLabs

# ================= CONFIGURAÇÕES =================
app = Flask(__name__, static_folder='public')
CORS(app)

# Chaves de API
API_ID = 34303434
API_HASH = '5d521f53f9721a6376586a014b51173d'
TARGET_CHAT = -1002421438612
GEMINI_KEY = "AIzaSyDByO6eYeg8vmb8v9HZ121RQnwdGkBLatk"
ELEVEN_KEY = "80f20c0648bd28e0f7c7c77c6d41551f5e5e03109f94f40a9bf0176a981e5b8f"

# Clientes
client_genai = genai.Client(api_key=GEMINI_KEY)
client_eleven = ElevenLabs(api_key=ELEVEN_KEY)

# Memória da IA (Dicionário simples por sessão)
sessions_memory = {}

# Configuração do Telegram e Loop de Eventos
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

SESSION_STRING = os.environ.get('SESSION_STRING', '')
client_tg = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH, loop=loop)

# Variáveis temporárias para login
auth_data = {"hash": None, "phone": None}

# ================= FUNÇÕES DE IA E VOZ =================

def get_ai_response(session_id, text):
    """Gera resposta com o Gemini mantendo histórico"""
    if session_id not in sessions_memory:
        sessions_memory[session_id] = []
    
    # Adiciona pergunta ao histórico
    sessions_memory[session_id].append({"role": "user", "parts": [text]})
    
    try:
        response = client_genai.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=sessions_memory[session_id]
        )
        answer = response.text
        # Adiciona resposta da IA ao histórico
        sessions_memory[session_id].append({"role": "model", "parts": [answer]})
        return answer
    except Exception as e:
        return f"Erro na IA: {str(e)}"

def text_to_speech_b64(text):
    """Converte texto em áudio Base64 via ElevenLabs"""
    try:
        audio_gen = client_eleven.text_to_speech.convert(
            text=text[:300], # Limite para rapidez
            voice_id="pNInz6obpgDQGcFmaJgB", # Voz Adam
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128"
        )
        audio_bytes = b"".join(audio_gen)
        return base64.b64encode(audio_bytes).decode('utf-8')
    except:
        return None

# ================= ROTAS DO SERVIDOR =================

@app.route('/')
def serve_index():
    return send_from_directory('public', 'index.html')

@app.route('/perguntar', methods=['POST'])
def perguntar():
    data = request.json
    pergunta = data.get('pergunta', '').strip()
    session_id = data.get('session_id', 'default_user')

    if not pergunta:
        return jsonify({'resposta': 'Sim?'})

    # LÓGICA DE COMANDO /
    if pergunta.startswith('/'):
        # Envia para o Telegram em background
        asyncio.run_coroutine_threadsafe(client_tg.send_message(TARGET_CHAT, pergunta), loop)
        res_text = f"Comando '{pergunta}' enviado ao Telegram."
    else:
        # Resposta via IA Gemini com memória
        res_text = get_ai_response(session_id, pergunta)

    # Gera áudio da resposta
    audio_data = text_to_speech_b64(res_text)

    return jsonify({
        'resposta': res_text,
        'audio': audio_data
    })

# ================= ROTAS DE AUTENTICAÇÃO =================

@app.route('/auth/send_code', methods=['POST'])
def send_code():
    phone = request.json.get('phone', '').strip()
    # Limpa o número para garantir formato +55...
    phone = '+' + ''.join(filter(str.isdigit, phone)) if not phone.startswith('+') else phone
    
    try:
        if not client_tg.is_connected():
            asyncio.run_coroutine_threadsafe(client_tg.connect(), loop).result()
        
        print(f"Solicitando código para {phone}...")
        result = asyncio.run_coroutine_threadsafe(client_tg.send_code_request(phone), loop).result()
        
        auth_data["hash"] = result.phone_code_hash
        auth_data["phone"] = phone
        return jsonify({'status': 'sent'})
    except Exception as e:
        print(f"Erro no envio: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/auth/login', methods=['POST'])
def login():
    code = request.json.get('code', '').strip()
    try:
        user = asyncio.run_coroutine_threadsafe(
            client_tg.sign_in(auth_data["phone"], code, phone_code_hash=auth_data["hash"]), 
            loop
        ).result()
        
        session_str = client_tg.session.save()
        return jsonify({'status': 'success', 'session_string': session_str})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

# ================= INICIALIZAÇÃO =================

def run_telegram():
    asyncio.set_event_loop(loop)
    loop.run_forever()

if __name__ == '__main__':
    # Inicia o Telegram numa thread separada
    threading.Thread(target=run_telegram, daemon=True).start()
    
    # Porta do Render
    port = int(os.getenv('PORT', 5000))
    # debug=False é obrigatório para não dar erro de loop no Render
    app.run(host='0.0.0.0', port=port, debug=False)
