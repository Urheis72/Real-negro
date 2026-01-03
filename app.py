import os
import asyncio
import threading
import base64
import requests
from flask import Flask, render_template_string, request, jsonify
from flask_cors import CORS
from telethon import TelegramClient
import google.generativeai as genai

# ======================================================
# CONFIGURAÇÕES - COLOQUE SUAS CHAVES AQUI
# ======================================================
GEMINI_KEY = "AIzaSyAdekalYORl_qzNLGuayZv-7hEZ63ZeVd4"
ELEVEN_KEY = "80f20c0648bd28e0f7c7c77c6d41551f5e5e03109f94f40a9bf0176a981e5b8f"
VOICE_ID = "pNInz6obpgDQGcFmaJgB"

# Dados do Telegram (Se for usar o BOT)
TG_API_ID = 34303434 
TG_API_HASH = "5d521f53f9721a6376586a014b51173d"
TG_BOT_TOKEN = "SEU_TOKEN_DO_BOTFATHER_AQUI" 

# Modelo Gemini 2.0 Flash Experimental
MODEL_NAME = 'gemini-2.0-flash-exp'

# ======================================================
# BACKEND (PYTHON)
# ======================================================

app = Flask(__name__)
CORS(app)

# Configura IA com Gemini 2.0
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel(model_name=MODEL_NAME)

# Configura Telegram (Bot Mode para estabilidade)
client_tg = TelegramClient('jarvis_bot_session', TG_API_ID, TG_API_HASH)

def start_telegram():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        if TG_BOT_TOKEN != "SEU_TOKEN_DO_BOTFATHER_AQUI":
            client_tg.start(bot_token=TG_BOT_TOKEN)
            print(">>> TELEGRAM ONLINE")
            client_tg.loop.run_forever()
    except Exception as e:
        print(f"Erro Telegram: {e}")

threading.Thread(target=start_telegram, daemon=True).start()

# Funções Auxiliares
def get_ai_response(text):
    try:
        # Usando Gemini 2.0 Flash Experimental
        response = model.generate_content(text)
        return response.text
    except Exception as e:
        return f"Erro no processamento neural (Gemini 2.0): {str(e)}"

def get_voice(text):
    if not ELEVEN_KEY: return None
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
    headers = {"xi-api-key": ELEVEN_KEY, "Content-Type": "application/json"}
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.8}
    }
    try:
        r = requests.post(url, json=data, headers=headers)
        if r.status_code == 200:
            return base64.b64encode(r.content).decode('utf-8')
    except:
        return None

# Rotas API
@app.route('/chat', methods=['POST'])
def chat():
    data = request.json
    msg = data.get('message')
    
    # 1. Pega resposta da IA (Gemini 2.0)
    reply = get_ai_response(msg)
    
    # 2. Gera áudio
    audio = get_voice(reply)
    
    return jsonify({"reply": reply, "audio": audio})

# ======================================================
# FRONTEND (VISUAL "KING" INTEGRADO)
# ======================================================
HTML_PAGE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>King AI Interface</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700&family=Inter:wght@300;400;600&display=swap" rel="stylesheet">
    
    <style>
        body { font-family: 'Inter', sans-serif; overflow: hidden; }
        h1, h2, .font-king { font-family: 'Cinzel', serif; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: #fbbf24; border-radius: 3px; }
        
        .particle {
            position: absolute; width: 4px; height: 4px; background: #fbbf24;
            border-radius: 50%; opacity: 0.3; pointer-events: none;
            animation: floatUp linear infinite;
        }
        @keyframes floatUp {
            0% { transform: translateY(0) rotate(0deg); opacity: 0; }
            50% { opacity: 0.5; }
            100% { transform: translateY(-100vh) rotate(360deg); opacity: 0; }
        }
        .message-king {
            background: linear-gradient(135deg, #1a1a1a 0%, #000000 100%);
            border: 1px solid #fbbf24; color: #fbbf24;
            box-shadow: 0 0 15px rgba(251, 191, 36, 0.1);
        }
        .message-user { background: #27272a; color: white; border: 1px solid #3f3f46; }
        .crown-badge {
            position: absolute; top: -10px; left: -10px; background: #fbbf24;
            width: 24px; height: 24px; border-radius: 50%; display: flex;
            align-items: center; justify-content: center; box-shadow: 0 0 10px #fbbf24; z-index: 20;
        }
        .typing-dot {
            width: 6px; height: 6px; background: #fbbf24; border-radius: 50%;
            animation: typing 1.4s infinite ease-in-out both;
        }
        .typing-dot:nth-child(1) { animation-delay: -0.32s; }
        .typing-dot:nth-child(2) { animation-delay: -0.16s; }
        @keyframes typing { 0%, 80%, 100% { transform: scale(0); } 40% { transform: scale(1); } }
        .hidden { display: none !important; }
    </style>
</head>
<body class="bg-gradient-to-br from-slate-900 via-black to-slate-800 h-screen w-screen text-white relative">

    <div id="particles" class="absolute inset-0 z-0 pointer-events-none"></div>

    <div id="loadingOverlay" class="fixed inset-0 z-50 bg-black/90 flex flex-col items-center justify-center hidden">
        <div class="animate-spin text-yellow-400 text-5xl mb-4"><i class="fas fa-circle-notch"></i></div>
        <p class="text-yellow-400 font-king tracking-widest">PROCESSANDO...</p>
    </div>

    <div id="loginScreen" class="absolute inset-0 z-40 flex items-center justify-center p-4">
        <div class="bg-black/60 backdrop-blur-md p-8 rounded-3xl border border-yellow-500/30 shadow-2xl max-w-md w-full text-center crown-glow">
            <div class="text-6xl text-yellow-400 mb-6"><i class="fas fa-crown"></i></div>
            <h1 class="text-4xl text-yellow-400 mb-2 font-bold tracking-wider">KING AI</h1>
            <p class="text-gray-400 mb-2">Gemini 2.0 Flash Experimental</p>
            <p class="text-gray-500 text-sm mb-8">Conectado ao Servidor Python</p>
            <button onclick="enterChat()" class="w-full bg-yellow-500 hover:bg-yellow-400 text-black font-bold py-4 rounded-xl transition-all hover:scale-105 shadow-[0_0_20px_rgba(234,179,8,0.5)]">
                ENTRAR NO SISTEMA
            </button>
        </div>
    </div>

    <div id="chatScreen" class="absolute inset-0 z-10 flex flex-col hidden">
        <header class="bg-black/50 backdrop-blur-md border-b border-yellow-500/20 p-4 flex justify-between items-center">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 bg-yellow-500 rounded-full flex items-center justify-center">
                    <i class="fas fa-crown text-black"></i>
                </div>
                <div>
                    <h2 class="text-yellow-400 font-bold text-lg leading-none">King AI</h2>
                    <span class="text-xs text-green-400 flex items-center gap-1">● Gemini 2.0 Flash</span>
                </div>
            </div>
            <button onclick="location.reload()" class="text-yellow-400 hover:text-white"><i class="fas fa-sync"></i></button>
        </header>

        <main id="chatMessages" class="flex-1 overflow-y-auto p-4 scroll-smooth"></main>

        <footer class="p-4 bg-black/50 backdrop-blur-md border-t border-yellow-500/20">
            <div class="flex items-end gap-2 max-w-4xl mx-auto relative">
                <textarea id="messageInput" rows="1" placeholder="Digite sua ordem..." class="w-full bg-white/5 border border-yellow-500/30 rounded-2xl px-4 py-3 text-white focus:outline-none focus:border-yellow-500 resize-none max-h-32"></textarea>
                <button onclick="sendMessage()" id="sendBtn" class="bg-yellow-500 hover:bg-yellow-400 text-black w-12 h-12 rounded-full flex items-center justify-center transition-all">
                    <i class="fas fa-paper-plane"></i>
                </button>
            </div>
        </footer>
    </div>

    <script>
        // EFEITOS VISUAIS
        function createParticles() {
            const container = document.getElementById('particles');
            for (let i = 0; i < 20; i++) {
                const p = document.createElement('div');
                p.className = 'particle';
                p.style.left = Math.random() * 100 + '%';
                p.style.top = Math.random() * 100 + '%';
                p.style.animationDuration = (2 + Math.random() * 3) + 's';
                container.appendChild(p);
            }
        }
        createParticles();

        function enterChat() {
            document.getElementById('loginScreen').style.display = 'none';
            document.getElementById('chatScreen').classList.remove('hidden');
            document.getElementById('chatScreen').style.display = 'flex';
            addMessage("Sistema Gemini 2.0 online. Aguardando comandos.", 'king');
        }

        async function sendMessage() {
            const input = document.getElementById('messageInput');
            const text = input.value.trim();
            if(!text) return;

            addMessage(text, 'user');
            input.value = '';
            showTyping(true);

            try {
                // CHAMA O BACKEND PYTHON
                const response = await fetch('/chat', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({message: text})
                });
                const data = await response.json();

                showTyping(false);
                addMessage(data.reply, 'king');

                // TOCA O ÁUDIO SE TIVER
                if(data.audio) {
                    const audio = new Audio("data:audio/mp3;base64," + data.audio);
                    audio.play();
                }

            } catch (e) {
                showTyping(false);
                addMessage("Erro ao conectar com servidor Python.", 'king');
            }
        }

        function addMessage(text, sender) {
            const container = document.getElementById('chatMessages');
            const div = document.createElement('div');
            div.className = `flex ${sender === 'king' ? 'justify-start' : 'justify-end'} mb-4 px-2`;
            
            let content = `
                <div class="relative px-4 py-3 rounded-2xl max-w-[85%] shadow-lg ${sender === 'king' ? 'message-king rounded-tl-none' : 'message-user rounded-tr-none'}">
                    ${sender === 'king' ? '<div class="crown-badge"><i class="fas fa-crown text-black text-xs"></i></div>' : ''}
                    <p class="relative z-10 font-medium leading-relaxed whitespace-pre-wrap">${text}</p>
                </div>
            `;
            
            div.innerHTML = content;
            container.appendChild(div);
            container.scrollTop = container.scrollHeight;
        }

        function showTyping(show) {
            const container = document.getElementById('chatMessages');
            const existing = document.getElementById('typing-indicator');
            if(existing) existing.remove();

            if(show) {
                const div = document.createElement('div');
                div.id = 'typing-indicator';
                div.className = 'flex justify-start mb-4 px-2';
                div.innerHTML = `
                    <div class="relative px-4 py-3 rounded-2xl message-king rounded-tl-none">
                        <div class="crown-badge"><i class="fas fa-crown text-black text-xs"></i></div>
                        <div class="flex gap-2 items-center h-5">
                            <div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>
                        </div>
                    </div>`;
                container.appendChild(div);
                container.scrollTop = container.scrollHeight;
            }
        }
        
        // Enviar com Enter
        document.getElementById('messageInput').addEventListener('keypress', function (e) {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
            }
        });
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return render_template_string(HTML_PAGE)

if __name__ == '__main__':
    print("="*50)
    print("🤖 King AI - Gemini 2.0 Flash Experimental")
    print("="*50)
    print(f"Modelo: {MODEL_NAME}")
    print("Servidor rodando em: http://localhost:5000")
    print("="*50)
    # Roda o servidor
    app.run(host='0.0.0.0', port=5000, debug=True)
