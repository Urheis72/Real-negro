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

# ============ CONFIGURAÇÕES GERAIS ============
app = Flask(__name__, static_folder='public')
CORS(app)

# --- CHAVES DE API ---
# Telegram
API_ID = 34303434
API_HASH = '5d521f53f9721a6376586a014b51173d'
TARGET_CHAT = -1002421438612 # ID do Grupo/Chat alvo
BOT_ALVO = '@QueryBuscasBot' # Bot que responderá os comandos

# Google Gemini (IA)
GEMINI_KEY = "AIzaSyDByO6eYeg8vmb8v9HZ121RQnwdGkBLatk"
client_genai = genai.Client(api_key=GEMINI_KEY)

# ElevenLabs (Voz)
ELEVEN_KEY = "80f20c0648bd28e0f7c7c77c6d41551f5e5e03109f94f40a9bf0176a981e5b8f"
client_eleven = ElevenLabs(api_key=ELEVEN_KEY)

# Memória Volátil (Simples)
# Estrutura: { 'session_id': [ {'role': 'user', 'parts': ['...']}, ... ] }
chat_memory = {}

# Controle do Telegram
SESSION_STRING = os.environ.get('SESSION_STRING', '')
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)
client_telegram = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH, loop=loop)

# ============ FUNÇÕES AUXILIARES ============

def gerar_audio_base64(texto):
    """Gera áudio via ElevenLabs e retorna em Base64 para tocar no front"""
    try:
        if not texto: return None
        # Limita tamanho para economizar e ser rápido
        texto_limpo = texto[:400] 
        
        audio_generator = client_eleven.text_to_speech.convert(
            text=texto_limpo,
            voice_id="pNInz6obpgDQGcFmaJgB", # Voz do Adam (padrão Jarvis)
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",
        )
        
        # Consome o gerador de áudio para bytes
        audio_bytes = b"".join(audio_generator)
        audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
        return audio_b64
    except Exception as e:
        print(f"Erro ElevenLabs: {e}")
        return None

async def buscar_resposta_telegram(comando):
    """Envia comando e espera a resposta específica do bot"""
    if not client_telegram.is_connected():
        await client_telegram.connect()
    
    if not await client_telegram.is_user_authorized():
        return "ERRO: Telegram desconectado. Faça login novamente."

    entity = await client_telegram.get_entity(TARGET_CHAT)
    
    # Future para capturar a resposta
    resposta_futura = loop.create_future()

    @client_telegram.on(events.NewMessage(chats=entity))
    async def handler(event):
        # Verifica se é uma resposta do bot esperado ou texto novo
        # Ajuste a lógica aqui se precisar filtrar apenas respostas ao seu comando
        if not resposta_futura.done():
             # Pega texto ou descrição de arquivo
            texto = event.message.message or "Arquivo recebido."
            if event.message.document:
                 # Se for arquivo txt, tenta ler (simplificado)
                 pass 
            resposta_futura.set_result(texto)

    # Envia o comando
    await client_telegram.send_message(entity, comando)
    
    try:
        # Espera até 15 segundos pela resposta
        texto_resposta = await asyncio.wait_for(resposta_futura, timeout=15)
        client_telegram.remove_event_handler(handler)
        return texto_resposta
    except asyncio.TimeoutError:
        client_telegram.remove_event_handler(handler)
        return "O bot do Telegram demorou para responder."

def processar_ia_com_memoria(session_id, user_text):
    """Processa texto com Gemini mantendo contexto"""
    if session_id not in chat_memory:
        chat_memory[session_id] = [
            {"role": "user", "parts": ["Você é o Jarvis, um assistente AI sofisticado, direto e útil."]},
            {"role": "model", "parts": ["Entendido. Estou operante."]}
        ]
    
    # Adiciona msg do usuario
    chat_memory[session_id].append({"role": "user", "parts": [user_text]})
    
    # Mantém apenas as últimas 10 mensagens para não estourar token/memória
    if len(chat_memory[session_id]) > 12:
        chat_memory[session_id] = chat_memory[session_id][-12:]

    try:
        # Usa modelo Flash (mais rápido/barato)
        response = client_genai.models.generate_content(
            model="gemini-2.0-flash-exp", 
            contents=chat_memory[session_id]
        )
        resposta_ia = response.text
        
        # Salva resposta na memória
        chat_memory[session_id].append({"role": "model", "parts": [resposta_ia]})
        return resposta_ia
    except Exception as e:
        return f"Erro na IA: {str(e)}"

# ============ ROTAS ============

@app.route('/perguntar', methods=['POST'])
def endpoint_perguntar():
    dados = request.json
    pergunta = dados.get('pergunta', '').strip()
    session_id = dados.get('session_id', 'default') # Para memória

    if not pergunta:
        return jsonify({'resposta': 'Aguardando comando.', 'audio': None})

    texto_final = ""

    # 1. FLUXO TELEGRAM (Se começar com /)
    if pergunta.startswith('/'):
        # Executa no loop asyncio do Telegram
        fut = asyncio.run_coroutine_threadsafe(buscar_resposta_telegram(pergunta), loop)
        try:
            texto_final = fut.result(timeout=20)
        except:
            texto_final = "Erro de timeout interno no Telegram."
    
    # 2. FLUXO IA (Texto normal)
    else:
        texto_final = processar_ia_com_memoria(session_id, pergunta)

    # 3. GERAÇÃO DE VOZ (Para qualquer resposta)
    # Roda em thread separada ou direta (ElevenLabs é rápido, mas pode bloquear, idealmente async)
    audio_b64 = generar_audio_base64(texto_final)

    return jsonify({
        'resposta': texto_final,
        'audio': audio_b64
    })

# --- ROTAS DE AUTENTICAÇÃO (MANTIDAS) ---
@app.route('/auth/send_code', methods=['POST'])
def send_code():
    phone = request.json.get('phone')
    if not client_telegram.is_connected():
        asyncio.run_coroutine_threadsafe(client_telegram.connect(), loop).result()
    
    res = asyncio.run_coroutine_threadsafe(client_telegram.send_code_request(phone), loop).result()
    global phone_code_hash, temp_phone
    phone_code_hash = res.phone_code_hash
    temp_phone = phone
    return jsonify({'status': 'sent'})

@app.route('/auth/login', methods=['POST'])
def login():
    code = request.json.get('code')
    try:
        asyncio.run_coroutine_threadsafe(
            client_telegram.sign_in(temp_phone, code, phone_code_hash=phone_code_hash), loop
        ).result()
        return jsonify({'status': 'success', 'session_string': client_telegram.session.save()})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/')
def index(): return send_from_directory('public', 'index.html')

# ============ INICIALIZAÇÃO ============
def start_telegram_loop():
    asyncio.set_event_loop(loop)
    loop.run_forever()

if __name__ == '__main__':
    # Inicia Telegram em Background
    t = threading.Thread(target=start_telegram_loop, daemon=True)
    t.start()
    # Inicia Flask
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
