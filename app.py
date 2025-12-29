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

# Configurações sensíveis
API_ID = 34303434
API_HASH = '5d521f53f9721a6376586a014b51173d'
TARGET_CHAT = -1002421438612
GEMINI_KEY = "AIzaSyA9a8QscXbFVLcVn6slY5ddmCHbpmQ5oFY"
genai_client = genai.Client(api_key=GEMINI_KEY)

SESSION_STRING = os.environ.get('SESSION_STRING', '')
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
client = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH, loop=loop)

@app.route('/perguntar', methods=['POST'])
def perguntar():
    data = request.json
    prompt = data.get('pergunta', '').strip()
    if not prompt: return jsonify({'resposta': 'Sistemas prontos. Aguardando entrada.'})

    if prompt.startswith('/'):
        asyncio.run_coroutine_threadsafe(client.send_message(TARGET_CHAT, prompt), loop)
        return jsonify({'resposta': f'Comando "{prompt}" transmitido com sucesso.'})

    try:
        response = genai_client.models.generate_content(
            model="gemini-2.0-flash-exp",
            contents=f"Aja como Jarvis, o assistente inteligente. Responda: {prompt}"
        )
        return jsonify({'resposta': response.text})
    except Exception as e:
        return jsonify({'resposta': f'Falha no processador central: {str(e)}'})

@app.route('/')
def index(): return send_from_directory('public', 'index.html')

def run_telethon():
    asyncio.set_event_loop(loop)
    loop.run_forever()

if __name__ == '__main__':
    threading.Thread(target=run_telethon, daemon=True).start()
    app.run(host='0.0.0.0', port=int(os.getenv('PORT', 5000)))
