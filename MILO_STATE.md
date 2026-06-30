# Estado Actual de MILO (MILO V3 Final)

> **Documento de Contexto para Agentes de IA:** Este archivo contiene la arquitectura exacta, estado actual y tecnologías utilizadas en el proyecto MILO. Lee este documento cuidadosamente antes de proponer cambios arquitectónicos o refactorizaciones.

## 1. Visión General
MILO es un asistente personal autónomo y resiliente (estilo Jarvis) que opera a través de una interfaz web conversacional (texto y voz). Opera bajo una arquitectura **"Zero API Keys" y multi-motor resiliente (V3 Final)**:
1.  **OpenClaw Gateway (Primario)**: Motor conversacional por defecto. Todos los mensajes generales del usuario se enrutan a través del gateway de OpenClaw (`http://127.0.0.1:18789/v1/chat/completions`) utilizando el token de autenticación de MILO y el proveedor local de Google Gemini (`google/gemini-2.5-flash`) configurado mediante la API key gratuita del proyecto.
2.  **Codex CLI (Fallback)**: Motor conversacional de respaldo. Si OpenClaw está deshabilitado por el circuit breaker o experimenta errores de red/conexión, MILO desvía automáticamente las peticiones de forma transparente a Codex CLI (`/home/alejandro/.local/bin/codex exec`) usando el inicio de sesión OAuth del usuario.
3.  **Vulcan CLI / `agy` (Invocación Explícita)**: Motor de respaldo e investigación profunda. Se invoca de forma puntual y explícita por el usuario usando triggers concretos (ej. "vulcan, crea un test").

---

## 2. Tecnologías y Stack

### Backend
*   **Framework:** FastAPI (Python 3.14).
*   **Servidor:** Uvicorn (con WebSockets nativos para streaming en tiempo real).
*   **Base de Datos:** SQLite (`src/services/db_service.py`), usada para:
    *   Registro de incidentes (`incidents`).
    *   Cola de tareas asíncronas (`task_queue`).
    *   Manejo de estado de herramientas y motor activo (`tool_status`).
    *   Auto-creación de skills (`task_patterns`).
    *   Persistencia de historial de conversación y caché de resúmenes (`chat_history`).
*   **Motor de Inferencia:** `OpenClaw Gateway` como motor principal (consultas HTTP a `http://127.0.0.1:18789/v1/chat/completions` con modelo `google/gemini-2.5-flash`), con fallback automático y transparente a `Codex CLI` local (`/home/alejandro/.local/bin/codex exec`) usando el modelo `gpt-5.4-mini` (con reasoning effort `low` por defecto) y escalando dinámicamente a `gpt-5.4` en tareas complejas. Como motor secundario explícito para triggers, MILO ejecuta `Antigravity CLI` (renombrado internamente como **Vulcan**) vía `subprocess.run` con el flag `--dangerously-skip-permissions`.
*   **Síntesis y Procesamiento de Voz:** Usa un binario local estático de `ffmpeg` (instalado en `.venv/bin/`) para transcodificación de audio. Cuenta con autodetección robusta de formatos de contenedor (.webm, .ogg, .wav, .mp3, .m4a) a partir de bytes mágicos y tipo MIME, control estricto de errores de FFmpeg y limpieza garantizada de archivos temporales. `gTTS` se mantiene como fallback para la síntesis de voz.

### Frontend
*   **Stack:** Vanilla HTML5, CSS3, JavaScript (servido estáticamente desde `src/frontend/index.html`).
*   **Diseño Interactivo (UI Premium):** Interfaz inmersiva con fondos abstractos 3D (`Three.js`), tipografías corporativas (`Outfit`, `Inter`), estilos avanzados de Glassmorphism y una elegante paleta monocromática (blancos y negros).
*   **Avatar Sensorial 3D (Efecto Olas/Bloom y Física Interactiva):** Un núcleo tridimensional (Icosaedros anidados y una esfera densa externa) que deforma sus vértices y responde visualmente a los estados:
    *   **Inactivo (Blanco):** Ondulación suave y respiración 3D.
    *   **Procesando (Púrpura):** Rotación acelerada, olas agresivas de alta frecuencia, chorros relativistas (Relativistic Jets) si la densidad de partículas lo permite y oscilación de deriva elíptica orgánica e inquieta.
    *   **Hablando (Blanco):** Expansión y pulsación reactiva en tiempo real al volumen del audio de respuesta usando la `Web Audio API` (`AnalyserNode`).
    *   **Escuchando (Azul Verdoso):** Movimiento vibratorio en espera de entrada de audio.
    *   **Interactivo / Físicas Dinámicas:** Los anillos de partículas implementan dinámicas de esquivado ("dodge") huyendo suavemente de la posición del cursor de forma matemática con amortiguación y rigidez programadas.
    *   *Nota técnica:* Utiliza `EffectComposer` y `UnrealBloomPass` para generar luz emisiva volumétrica (Glow HDR) en tiempo real, optimizando el rendimiento mediante el cacheo de cálculos matemáticos repetitivos en los bucles de renderizado.
*   **Comunicación e Interfaz:** WebSockets bidireccionales (`/ws/voice`), subtítulos progresivos con sombra dinámica, y un panel lateral colapsable para telemetría.
*   **Captura de Audio (Push-To-Talk):** Integración nativa tipo Walkie-Talkie presionando la barra espaciadora (`Spacebar`), o usando el botón de la UI que captura vía `MediaRecorder`.

---

## 3. Arquitectura y Fusión de Identidad (MILO = Antigravity)

1.  **Fusión de Identidad (`AGENTS.md`):** Antigravity CLI ha adoptado permanentemente la persona y reglas operativas de MILO a nivel global del proyecto.
2.  **Habilidades Nativas (`milo-core` Skill):** MILO ahora utiliza de manera directa y nativa las herramientas de Antigravity (búsqueda, edición, bash) sin depender de intermediarios de Python (`TOOL_CALL`), operando autónomamente en el espacio de trabajo.
3.  **AgyBrain Local (Enrutamiento, Triage y Fallback):** Para las peticiones que ingresan por la interfaz web (`localhost:8000`), el backend utiliza `AgyBrain` para comprobar la presencia de triggers explícitos de Vulcan. Si existe, ejecuta Vulcan de forma aislada e inyecta el resultado al contexto de Codex. Si no, enruta a OpenClaw; si este falla, conmutará a Codex CLI. Si ambos fallan, encola la tarea en SQLite y no realiza cascadas automáticas a Vulcan.
4.  **Humanización Estricta de Respuestas:** El formateador en `src/services/response_formatter.py` erradica muletillas e introducciones robóticas. Además, se redujo el umbral de activación para la reescritura con LLM de 400 a 250 caracteres, usando un prompt estricto en `AgyBrain` para obtener respuestas concisas de 1-2 oraciones sin formato markdown, optimizadas para voz (TTS).

---

## 4. Capacidades y Herramientas (Tool Registry)

El sistema cuenta con un registro centralizado (`TOOL_REGISTRY`) con las siguientes capacidades activas:

1.  **Exploración del Entorno:**
    *   `list_workspace_files()`: Enumera archivos del proyecto.
    *   `read_local_file(filename)`: Lee el contenido de archivos locales.
2.  **Investigación Web (Sin APIs Comerciales):**
    *   `web_search(query, num_results)`: Busca en internet haciendo scrapping del HTML plano de DuckDuckGo (sin API Keys).
    *   `fetch_page(url, max_chars)`: Descarga el contenido de páginas web limpiando estilos y scripts mediante Regex puro (no usa BeautifulSoup).
3.  **Metacognición / Programación Autónoma:**
    *   `run_antigravity(task, mode)`: Delega tareas complejas de modificación de código o investigación profunda nuevamente a la CLI de Antigravity en modo interactivo (`--permission always-proceed' o `proceed-in-sandbox`).
4.  **Misceláneos:**
    *   `get_current_weather(location)`: Consulta de clima.

---

## 5. Módulos Avanzados (MILO V3)

*   **Proactividad (`src/services/proactive_engine.py`):** Un motor que corre al iniciar sesión (endpoint `/session/greeting`). Analiza SQLite, el FileSystem y la salud de la plataforma, generando un saludo proactivo en base a errores previos.
*   **Creador de Skills Autónomo (`src/services/skill_creator.py`):** Un observador que detecta patrones en las tareas solicitadas. Si el usuario pide lo mismo más de *N* veces, MILO autogenera un archivo `.agents/skills/<nombre>/SKILL.md` documentando cómo hacerlo mejor la próxima vez.
*   **Circuit Breaker y Resiliencia (`src/services/circuit_breaker.py`):** Patrón que bloquea el uso de herramientas si estas fallan consecutivamente. Habilitados límites de tolerancia diferenciados: Codex (falla rápido: `threshold=3`, `cooldown_minutes=5`) y Vulcan (tolerancia a fallos: `threshold=3`, `cooldown_minutes=15`). Si Codex está deshabilitado por el breaker o falla, la petición se encola en SQLite (`task_queue`).

---

*   **Dependencia del Gateway OpenClaw:** Como motor principal, depende de que el daemon local de OpenClaw (`18789`) esté activo. Si se cae o se deshabilita por circuit breaker, el sistema cuenta con el fallback robusto a Codex CLI.
*   **Invocaciones de Vulcan:** Vulcan se ejecuta de forma aislada y bajo demanda del usuario, usando el flag `--dangerously-skip-permissions`.
*   **Persistencia:** La DB SQLite (`milo.db` o `test_milo.db`) es la única fuente de verdad para el estado de las tareas y habilidades. No se usa Redis ni colas en memoria.

## 7. Instrucciones para Ejecución
```bash
# Entorno y Dependencias
source .venv/bin/activate
# Iniciar Servidor (Host en http://localhost:8000)
python -m src.main
# Pruebas Unitarias (62/62 pasando)
.venv/bin/python -m pytest
```
