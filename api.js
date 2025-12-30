/**
 * JARVIS CORE - API INTERFACE V3
 * Suporte a Vite, Webpack e Node.js
 */

import { GoogleGenerativeAI } from "@google/generative-ai";

// As chaves são lidas do ambiente (Vite usa import.meta.env, Node usa process.env)
const GEMINI_KEY = import.meta.env?.VITE_GEMINI_API_KEY || process.env.GEMINI_API_KEY;
const ELEVEN_KEY = import.meta.env?.VITE_ELEVENLABS_API_KEY || process.env.ELEVENLABS_API_KEY;
const VOICE_ID = "pNInz6obpgDQGcFmaJgB";

// Inicialização do Gemini
const genAI = new GoogleGenerativeAI(GEMINI_KEY);
const model = genAI.getGenerativeModel({ model: "gemini-1.5-flash" });

/**
 * Envia mensagem para o Gemini
 */
export async function sendMessageToGemini(message) {
  try {
    if (message.trim().startsWith("/")) return null;

    console.log("LOG: Solicitando resposta da IA...");
    const result = await model.generateContent(message);
    const response = await result.response;
    const text = response.text();
    
    console.log("LOG: Gemini respondeu com sucesso.");
    return text;
  } catch (error) {
    console.error("❌ ERRO GEMINI:", error.message);
    return "Desculpe, houve um erro ao processar minha inteligência.";
  }
}

/**
 * Converte texto em áudio e reproduz
 */
export async function speakWithElevenLabs(text) {
  try {
    if (!text || text.length < 2) return;

    console.log("LOG: Gerando voz ElevenLabs...");
    const response = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${VOICE_ID}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "xi-api-key": ELEVEN_KEY,
      },
      body: JSON.stringify({
        text: text,
        model_id: "eleven_multilingual_v2",
        voice_settings: { stability: 0.5, similarity_boost: 0.8 },
      }),
    });

    if (!response.ok) throw new Error(`Erro TTS: ${response.status}`);

    const audioBlob = await response.blob();
    const audioUrl = URL.createObjectURL(audioBlob);
    const audio = new Audio(audioUrl);
    
    return new Promise((resolve) => {
      audio.play();
      audio.onended = resolve;
    });
  } catch (error) {
    console.error("❌ ERRO ELEVENLABS:", error.message);
  }
}
