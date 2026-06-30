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
*   **Motor de Inferencia:** `Antigravity CLI` (ejecutado vía `subprocess.run`). No existen dependencias de SDKs como `google-genai` ni `anthropic`.
*   **Síntesis y Procesamiento de Voz:** Usa un binario local estático de `ffmpeg` (instalado en `.venv/bin/`) para transcodificación de audio de forma autónoma sin depender del sistema operativo. `gTTS` se mantiene como fallback para la síntesis de voz, documentado como transitorio frente a `Piper TTS` (por la actual ausencia local de `espeak-ng` y el peso de los modelos `.onnx`).

### Frontend
*   **Stack:** Vanilla HTML5, CSS3, JavaScript (servido estáticamente desde `src/frontend/index.html`).
*   **Diseño Interactivo (UI):** UI inmersiva con fondo espacial 3D (`Three.js`), cursor personalizado con destello lumínico (glow) y estilo Dark Mode / Glassmorphism importado del proyecto "Portafolio".
*   **Avatar Sensorial:** El círculo central posee 3 estados ("Escuchando", "Procesando", "Hablando"). Reacciona en vivo a la amplitud del audio de respuesta utilizando la `Web Audio API` (`AnalyserNode`).
*   **Comunicación:** WebSockets bidireccionales (`/ws/voice`). Implementa subtítulos progresivos sincronizados y un **panel lateral colapsable** que expone la telemetría del backend y herramientas activas (brindando transparencia sobre qué hace Agy en segundo plano).
*   **Captura de Audio:** `MediaRecorder` API del navegador nativo.

---

## 3. Arquitectura "Zero API Keys" (`AgyBrain`)

Todo el flujo lógico y de procesamiento de lenguaje natural ha sido aislado en `src/services/agy_brain.py`.

*   **Flujo de Inferencia:** Cuando el usuario habla o escribe, el prompt se inyecta en un contexto y se invoca como: `subprocess.run(["agy", "--print", prompt], ...)`.
*   **Tool Orchestrator Local:** MILO fuerza a la CLI a usar un formato predeterminado para las herramientas (`TOOL_CALL: nombre_herramienta(param="valor")`).
*   **Ejecución:** Si `AgyBrain` devuelve un `TOOL_CALL`, `gemini_service.py` (ahora actuando como orquestador general) parsea el string usando `ast`, ejecuta la herramienta (con tolerancia a fallos), inyecta el resultado al historial, y vuelve a invocar a `AgyBrain`.

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

*   **Dependencia Estricta de la Salida de `agy`:** El orquestador depende de que Antigravity CLI no altere silenciosamente su stdout. Cambios abruptos en cómo `agy --print` devuelve texto pueden romper el Regex de `TOOL_CALL:`.
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
