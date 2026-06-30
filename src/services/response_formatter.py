import re
import os
import logging
from src.services.agy_brain import AgyBrain

logger = logging.getLogger(__name__)

def humanize_response(raw_text: str) -> dict:
    """
    Limpia y humaniza la respuesta del agente antes de enviarla a la UI.
    Retorna:
      {
        "subtitle": str, # Texto a mostrar en pantalla (con formato básico)
        "speech": str    # Texto limpio para el motor TTS
      }
    """
    if not raw_text or not raw_text.strip():
        return {"subtitle": "", "speech": ""}

    # 1. Eliminar residuos de formato de agente y muletillas robóticas al inicio
    text = raw_text
    text = re.sub(r'^(Thought:|Response:|\[MILO\])\s*', '', text, flags=re.IGNORECASE|re.MULTILINE)
    text = re.sub(r'^(aquí tienes|por supuesto,|claro,|entendido,|listo,|perfecto,|de acuerdo,)\s*', '', text, flags=re.IGNORECASE)
    text = text.strip()

    # 2. Recortar verbosidad (segunda pasada con AgyBrain si > 250 chars)
    if len(text) > 250:
        logger.info("Respuesta larga detectada. Invocando AgyBrain para resumir (anti-robótico).")
        brain = AgyBrain(os.getcwd())
        
        # OPTIMIZACIÓN DE TOKENS: No enviar todo el bloque gigante.
        text_for_summary = text[:1000] + ("\n...[truncado]" if len(text) > 1000 else "")
        
        prompt = (
            "Eres MILO. Toma el siguiente texto técnico y redacta una respuesta extremadamente directa, concisa y natural, "
            "óptima para ser leída por un sintetizador de voz. "
            "Sigue estas reglas estrictamente:\n"
            "1. Ve directo al grano sin preámbulos robóticos.\n"
            "2. No uses listas con viñetas ni numeradas.\n"
            "3. Limítate a máximo 1 o 2 oraciones muy cortas y conversacionales.\n"
            "4. Evita totalmente usar formato markdown (como asteriscos o hashtags).\n\n"
            "Texto original:\n\n" + text_for_summary
        )
        try:
            summary = brain.ask(prompt, mode="chat")
            # Volver a limpiar por si AgyBrain agregó "Response:" al inicio del resumen
            summary = re.sub(r'^(Thought:|Response:|\[MILO\])\s*', '', summary, flags=re.IGNORECASE|re.MULTILINE)
            summary = re.sub(r'^(aquí tienes|por supuesto,|claro,|entendido,|listo,|perfecto,|de acuerdo,)\s*', '', summary, flags=re.IGNORECASE)
            if summary.strip():
                text = summary.strip()
        except Exception as e:
            logger.error(f"Error resumiendo texto: {e}")

    # 3. Diferenciar subtitle vs speech
    subtitle_text = text
    
    # Speech: quitar URLs y markdown (asteriscos, negritas, código)
    speech_text = text
    # Reemplazar URLs largas por "un enlace"
    speech_text = re.sub(r'https?://[^\s]+', 'un enlace', speech_text)
    # Quitar markdown
    speech_text = re.sub(r'[*_#`~]+', '', speech_text)
    
    # Quitar emojis o reemplazarlos? gTTS a veces falla o los lee raro. Mejor ignorarlos por ahora o confiar en gTTS.
    
    return {
        "subtitle": subtitle_text,
        "speech": speech_text
    }
