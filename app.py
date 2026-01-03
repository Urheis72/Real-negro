# backend.py
import os
from flask import Flask, request, jsonify
from google import genai
from google.genai import types

app = Flask(__name__)

# CHAVE ATUALIZADA (substituída conforme solicitado)
API_KEY = "SUA_NOVA_API_KEY_AQUI"

# Inicializa o cliente Gemini
client = genai.Client(api_key=API_KEY)

MODEL = "gemini-2.5-chat"  # modelo de chat atual (mantido exatamente)

chat_memory = []  # memória da conversa

@app.route("/chat", methods=["POST"])
def chat():
    global chat_memory
    data = request.json
    user_message = data.get("message")
    if not user_message:
        return jsonify({"error": "Mensagem é obrigatória"}), 400

    # Adiciona a mensagem do usuário à memória
    chat_memory.append({"role": "user", "content": user_message})

    # Prepara o conteúdo para a API
    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text("\n".join([f"{m['role']}: {m['content']}" for m in chat_memory]))]
        )
    ]

    generate_config = types.GenerateContentConfig(response_modalities=["TEXT"])

    try:
        response_text = ""
        for chunk in client.models.generate_content_stream(
            model=MODEL,
            contents=contents,
            config=generate_config
        ):
            if chunk.candidates and chunk.candidates[0].content and chunk.candidates[0].content.parts:
                part = chunk.candidates[0].content.parts[0]
                if part.text:
                    response_text += part.text

        # Adiciona resposta do King à memória
        chat_memory.append({"role": "king", "content": response_text})

        return jsonify({"reply": response_text})

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
