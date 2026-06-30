# Estado Actual de MILO (MILO V2)

> **Documento de Contexto para Agentes de IA:** Este archivo contiene la arquitectura exacta, estado actual y tecnologías utilizadas en el proyecto MILO. Lee este documento cuidadosamente antes de proponer cambios arquitectónicos o refactorizaciones.

## 1. Visión General
MILO es un asistente personal autónomo y resiliente (estilo Jarvis) que opera a través de una interfaz web conversacional (texto y voz). Originalmente dependía de integraciones directas vía API con Gemini y Anthropic, pero **ha sido refactorizado a una arquitectura "Zero API Keys"**. 

Actualmente, el único cerebro lógico de MILO es la **Antigravity CLI (`agy`)**, la cual se ejecuta como un subproceso local autenticado con la cuenta de Google del usuario. MILO actúa como orquestador, proveedor de herramientas y servidor de la interfaz gráfica.

---

## 2. Tecnologías y Stack

### Backend
*   **Framework:** FastAPI (Python 3.14).
*   **Servidor:** Uvicorn (con WebSockets nativos para streaming en tiempo real).
*   **Base de Datos:** SQLite (`src/services/db_service.py`), usada para:
    *   Registro de incidentes (`incidents`).
    *   Cola de tareas asíncronas (`task_queue`).
    *   Manejo de estado de herramientas (`tool_status`).
    *   Auto-creación de skills (`task_patterns`).
*   **Motor de Inferencia:** `Antigravity CLI` (ejecutado vía `subprocess.run` con el flag `--dangerously-skip-permissions` para ejecución autónoma sin bloqueos). Emplea el modelo `"Gemini 3.5 Flash (Medium)"`. No existen dependencias directas de SDKs como `google-genai` ni `anthropic`.
*   **Síntesis y Procesamiento de Voz:** Usa un binario local estático de `ffmpeg` (instalado en `.venv/bin/`) para transcodificación de audio. Cuenta con autodetección robusta de formatos de contenedor (.webm, .ogg, .wav, .mp3, .m4a) a partir de bytes mágicos y tipo MIME, control estricto de errores de FFmpeg y limpieza garantizada de archivos temporales. `gTTS` se mantiene como fallback para la síntesis de voz.

### Frontend
*   **Stack:** Vanilla HTML5, CSS3, JavaScript (servido estáticamente desde `src/frontend/index.html`).
*   **Diseño Interactivo (UI Premium):** Interfaz inmersiva con fondos abstractos 3D (`Three.js`), tipografías corporativas (`Outfit`, `Inter`), estilos avanzados de Glassmorphism y una elegante paleta monocromática (blancos y negros).
*   **Avatar Sensorial 3D (Efecto Olas/Bloom y Física Interactiva):** Un núcleo tridimensional (Icosaedros anidados y una esfera densa externa) que deforma sus vértices y responde visualmente a los estados:
    *   **Inactivo (Cian):** Ondulación suave y respiración 3D.
    *   **Procesando (Púrpura):** Rotación acelerada, olas agresivas de alta frecuencia, chorros relativistas (Relativistic Jets) si la densidad de partículas lo permite y oscilación de deriva elíptica orgánica e inquieta.
    *   **Hablando (Azul):** Expansión y pulsación reactiva en tiempo real al volumen del audio de respuesta usando la `Web Audio API` (`AnalyserNode`).
    *   **Interactivo / Físicas Dinámicas:** Los anillos de partículas implementan dinámicas de esquivado ("dodge") huyendo suavemente de la posición del cursor de forma matemática con amortiguación y rigidez programadas.
    *   *Nota técnica:* Utiliza `EffectComposer` y `UnrealBloomPass` para generar luz emisiva volumétrica (Glow HDR) en tiempo real, optimizando el rendimiento mediante el cacheo de cálculos matemáticos repetitivos en los bucles de renderizado.
*   **Comunicación e Interfaz:** WebSockets bidireccionales (`/ws/voice`), subtítulos progresivos con sombra dinámica, y un panel lateral colapsable para telemetría.
*   **Captura de Audio (Push-To-Talk):** Integración nativa tipo Walkie-Talkie presionando la barra espaciadora (`Spacebar`), o usando el botón de la UI que captura vía `MediaRecorder`.

---

## 3. Arquitectura y Fusión de Identidad (MILO = Antigravity)

Históricamente, MILO dependía de un "Tool Orchestrator Local" en `agy_brain.py` que ejecutaba `agy --print` como un LLM ciego. **Actualmente la arquitectura ha dado un salto hacia la fusión total**:

1.  **Fusión de Identidad (`AGENTS.md`):** Antigravity CLI ha adoptado permanentemente la persona y reglas operativas de MILO a nivel global del proyecto.
2.  **Habilidades Nativas (`milo-core` Skill):** MILO ahora utiliza de manera directa y nativa las herramientas de Antigravity (búsqueda, edición, bash) sin depender de intermediarios de Python (`TOOL_CALL`), operando autónomamente en el espacio de trabajo.
3.  **AgyBrain Local (Fallback/UI Orchestration):** Para las peticiones que ingresan por la interfaz web (`localhost:8000`), el backend sigue utilizando `AgyBrain` (ejecutando subprocesos locales de `agy`) y orquestando respuestas JSON/Audio, pero la mente operante real ya no requiere "falsificar" llamadas de herramientas: si el usuario llama a Antigravity en la CLI, interactúa directamente con el cerebro de MILO.
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
    *   `run_antigravity(task, mode)`: Delega tareas complejas de modificación de código o investigación profunda nuevamente a la CLI de Antigravity en modo interactivo (`--permission always-proceed` o `proceed-in-sandbox`).
4.  **Misceláneos:**
    *   `get_current_weather(location)`: Consulta de clima.

---

## 5. Módulos Avanzados (MILO V2)

*   **Proactividad (`src/services/proactive_engine.py`):** Un motor que corre al iniciar sesión (endpoint `/session/greeting`). Analiza la base de datos de SQLite y el FileSystem para generar un mensaje espontáneo tipo: *"Mientras no estabas, ocurrieron 3 errores y tienes 1 tarea pendiente"*.
*   **Creador de Skills Autónomo (`src/services/skill_creator.py`):** Un observador que detecta patrones en las tareas solicitadas. Si el usuario pide lo mismo más de *N* veces, MILO autogenera un archivo `.agents/skills/<nombre>/SKILL.md` documentando cómo hacerlo mejor la próxima vez.
*   **Circuit Breaker y Resiliencia (`src/services/circuit_breaker.py`):** Patrón que bloquea el uso de herramientas si estas fallan consecutivamente, evitando bucles infinitos de la IA. Si el motor falla por cuotas (`RESOURCE_EXHAUSTED 429`), las peticiones se encolan en la base de datos (Background Task Queue).

---

## 6. Puntos Críticos y Fragilidades Conocidas

*   **Dependencia Estricta de la Salida de `agy`:** El orquestador depende de que Antigravity CLI no altere silenciosamente su stdout. Cambios abruptos en cómo `agy` devuelve texto pueden romper el Regex de `TOOL_CALL:`. La invocación se realiza con el flag `--dangerously-skip-permissions` para prevenir bloqueos interactivos por solicitudes de permisos.
*   **Latencia y Límites de Cuota (Error 429):** Dado que el razonamiento ocurre mediante la cuenta de Google vinculada al CLI de Antigravity, es posible agotar la cuota (e.g. uso de modelos pesados). Cuando esto ocurre (respuesta vacía o error 429), la UI de MILO intercepta el fallo vía evento WebSocket, muestra un estado visual de error en el Avatar y notifica al usuario informándole que "la tarea quedó en cola".
*   **Persistencia:** La DB SQLite (`milo.db` o `test_milo.db`) es la única fuente de verdad para el estado de las tareas y habilidades. No se usa Redis ni colas en memoria.

## 7. Instrucciones para Ejecución
```bash
# Entorno y Dependencias
source .venv/bin/activate
# Iniciar Servidor (Host en http://localhost:8000)
python -m src.main
# Pruebas Unitarias (83/83 pasando)
python -m pytest tests/
```
