// Configurações ElevenLabs
const ELEVEN_KEY = "80f20c0648bd28e0f7c7c77c6d41551f5e5e03109f94f40a9bf0176a981e5b8f";
const VOICE_ID = "pNInz6obpgDQGcFmaJgB";

export async function speak(text) {
    if(!text) return;
    try {
        const response = await fetch(`https://api.elevenlabs.io/v1/text-to-speech/${VOICE_ID}`, {
            method: "POST",
            headers: { "Content-Type": "application/json", "xi-api-key": ELEVEN_KEY },
            body: JSON.stringify({
                text: text.substring(0, 1000), // Limite para evitar erros
                model_id: "eleven_multilingual_v2"
            })
        });
        const blob = await response.blob();
        const audio = new Audio(URL.createObjectURL(blob));
        audio.play();
    } catch (e) { console.error("Erro na voz:", e); }
}

// Lógica da Câmera com Detecção de Rosto
export async function startCamera(videoElement, canvasElement) {
    const stream = await navigator.mediaDevices.getUserMedia({ video: true });
    videoElement.srcObject = stream;
    
    // Carregar face-api.js e desenhar retângulos (exemplo simplificado)
    setInterval(() => {
        const ctx = canvasElement.getContext('2d');
        ctx.clearRect(0, 0, canvasElement.width, canvasElement.height);
        // Aqui você adicionaria a lógica do face-api.js
        ctx.strokeStyle = "red";
        ctx.strokeRect(50, 50, 100, 100); // Placeholder do retângulo
    }, 100);
}
