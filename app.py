import asyncio
import os
import threading
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from telethon import TelegramClient, events, errors
from telethon.sessions import StringSession
from google import genai

app = Flask(__name__, static_folder='public')
CORS(app)

# Configurações
api_id = 34303434
api_hash = '5d521f53f9721a6376586a014b51173d'
target_chat = -1002421438612
GEMINI_API_KEY = "AIzaSyA9a8QscXbFVLcVn6slY5ddmCHbpmQ5oFY"
genai_client = genai.Client(api_key=GEMINI_API_KEY)

SESSION_STRING = os.environ.get('SESSION_STRING', '')
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
client = TelegramClient(StringSession(SESSION_STRING), api_id, api_hash, loop=loop)

@app.route('/perguntar', methods=['POST'])
def perguntar():
    dados = request.json
    pergunta = dados.get('pergunta', '').strip()
    
    if not pergunta:
        return jsonify({'resposta': 'Digite algo.'})

    # LÓGICA PEDIDA: Se começar com /, envia direto para o Telegram
    if pergunta.startswith('/'):
        asyncio.run_coroutine_threadsafe(client.send_message(target_chat, pergunta), loop)
        return jsonify({'resposta': f'🚀 Comando "{pergunta}" enviado ao grupo!'})

    # Caso contrário, pergunta para a IA Gemini
    try:
        response = genai_client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=f"Você é o Jarvis. Responda de forma prestativa: {pergunta}"
        )
        return jsonify({'resposta': response.text})
    except Exception as e:
        return jsonify({'resposta': f'Erro na IA: {str(e)}'})

# Rotas de Auth e Index (Mantidas)
@app.route('/')
def index(): return send_from_directory('public', 'index.html')

def start_telethon():
    asyncio.set_event_loop(loop)
    loop.run_forever()

if __name__ == '__main__':
    threading.Thread(target=start_telethon, daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
