# Histórico de Desarrollo: Fase 4 (Voz y Jarvis-Mode)

Este documento detalla las decisiones técnicas y la implementación de la interfaz de voz conversacional para MILO.

---

### 1. ¿Qué queríamos hacer?
*   Habilitar una forma natural e interactiva de hablar con MILO por medio de la voz, de forma similar al asistente "Jarvis" de Iron Man.
*   Poder enviarle comandos por micrófono desde la terminal y recibir la respuesta sintetizada en voz a través de los parlantes.
*   Permitir que las consultas de voz utilicen las mismas herramientas de resiliencia y ejecución de código ya desarrolladas en las fases previas.

### 2. ¿Por qué lo hicimos?
*   **Aumentar la interactividad:** Escribir en la terminal es funcional, pero hablar por voz permite una experiencia de uso mucho más fluida, inmersiva y de manos libres.
*   **Multimodalidad Nativa:** Gemini 2.5-Flash soporta la recepción directa de archivos de audio, lo cual elimina la necesidad de tener un pesado modelo de Speech-to-Text local en el PC.
*   **Robustez de ejecución:** Queremos que el cliente de voz funcione tanto en una terminal de escritorio (usando captura de teclado) como en terminales remotas o headless (usando una interfaz interactiva de consola).

### 3. ¿Cómo lo hicimos?
*   **Servidor FastAPI (`src/main.py` y `src/services/gemini_service.py`):**
    *   Creamos el endpoint `POST /chat/audio` que acepta subidas de archivos en formato Multipart (`UploadFile`).
    *   Para procesar multipart, añadimos la dependencia `python-multipart` a `requirements.txt`.
    *   Creamos la función `generate_audio_response()` que recibe los bytes de audio y los pasa directamente como un objeto `Part` de bytes multimodales en el método `chats.create` del SDK de Gemini.
    *   Gemini escucha el archivo de audio directamente, decide qué herramientas ejecutar en un bucle recursivo y retorna la respuesta de texto.
*   **Cliente Local de Voz (`src/voice_client.py`):**
    *   Implementamos la captura de audio usando `sounddevice` y `soundfile` a 16000 Hz en formato mono WAV (óptimo para Gemini).
    *   Instalamos `gTTS` (Google Text-to-Speech) para sintetizar las respuestas de texto de MILO a archivos MP3.
    *   **Fallback de teclado:** Si el sistema tiene sesión gráfica y cuenta con soporte para `pynput` (que captura teclado sin privilegios de root), se activa la tecla **`m`** como conmutador (presionar `m` para iniciar grabación, y presionar `m` de nuevo para detener y enviar). Si `pynput` no se puede compilar (debido a falta de cabeceras de Python en el SO local) o no hay pantalla activa, el script conmuta de forma automática y transparente a **modo consola (ENTER)**, evitando fallos.
    *   **Reproducción de voz resiliente:** El script busca reproductores de audio estándar en Linux como `mpg123`, `mpv`, `play` (sox), `aplay` o `paplay` en cascada. Si no encuentra ninguno, le da un consejo amigable al usuario sobre cómo instalar `mpg123` en su distribución.
*   **Prueba de Integración (`tests/test_main.py`):**
    *   Creamos `test_chat_audio_endpoint` mockeando el backend de audio de Gemini para verificar la correcta integración de subida de archivos multipart en FastAPI.

### 4. ¿Para qué sirve?
*   Permite controlar a MILO por voz, solicitándole que examine archivos del workspace o realice tareas locales en tu PC con un solo botón o tecla en la terminal.
*   Facilita la evolución de MILO hacia una verdadera interfaz Jarvis, lista para acoplarse con altavoces inteligentes o clientes web de escritorio.
