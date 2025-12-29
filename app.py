import asyncio
import os
import threading
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from telethon import TelegramClient, events
from telethon.sessions import StringSession
from google import genai
import logging

# Configuração de Logging para Monitoramento
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='public')
CORS(app)

# Configurações de Ambiente
API_ID = 34303434
API_HASH = '5d521f53f9721a6376586a014b51173d'
TARGET_CHAT = -1002421438612
GEMINI_KEY = "AIzaSyA9a8QscXbFVLcVn6slY5ddmCHbpmQ5oFY"
SESSION_STRING = os.environ.get('SESSION_STRING', '')

# Inicialização de Clientes
genai_client = genai.Client(api_key=GEMINI_KEY)
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
tg_client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH, loop=loop)

async def start_tg():
    if not tg_client.is_connected():
        await tg_client.connect()

@app.route('/perguntar', methods=['POST'])
def perguntar():
    data = request.json
    pergunta = data.get('pergunta', '').strip()
    
    if not pergunta:
        return jsonify({'resposta': 'Sistema em standby. Aguardando entrada.'}), 400

    try:
        # Lógica de Comando vs IA
        if pergunta.startswith('/'):
            asyncio.run_coroutine_threadsafe(tg_client.send_message(TARGET_CHAT, pergunta), loop)
            return jsonify({'resposta': f'Comando [{pergunta}] executado e enviado ao terminal remoto.'})
        
        # Chamada Gemini 2.0
        response = genai_client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=f"Atue como Jarvis. Seja breve, técnico e prestativo: {pergunta}"
        )
        return jsonify({'resposta': response.text})

    except Exception as e:
        logger.error(f"Erro no processamento: {e}")
        return jsonify({'resposta': 'Falha nos sistemas centrais. Tente novamente.'}), 500

@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

def background_loop():
    loop.run_until_complete(start_tg())
    loop.run_forever()

if __name__ == '__main__':
    threading.Thread(target=background_loop, daemon=True).start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)
