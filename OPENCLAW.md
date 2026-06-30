# Plan de Integración: OpenClaw → MILO CLI (MILO V3)

> **Documento de Contexto para Agentes de IA:** Este archivo complementa a `MILO_STATE.md`. Describe el plan para incorporar **OpenClaw** como capa de orquestación multi-proveedor (Anthropic, OpenAI, Gemini) dentro de la arquitectura "Zero API Keys" de MILO, optimizando el consumo de tokens del CLI y resolviendo la fragilidad documentada en la Sección 6 de `MILO_STATE.md` (dependencia de `agy`, cuotas 429).

---

## 1. Por qué OpenClaw

MILO actualmente depende de un único cerebro lógico (`Antigravity CLI` / `agy`), invocado por subprocess en `agy_brain.py`. Esto genera dos puntos de fragilidad ya conocidos:

* Dependencia estricta del stdout de `agy` (rompe si cambia el formato de salida).
* Sin failover real: si la cuenta de Google se queda sin cuota (`RESOURCE_EXHAUSTED 429`), la tarea se encola en SQLite y espera.

**OpenClaw** (`openclaw/openclaw`) es un gateway de asistente personal open-source que resuelve esto de forma nativa:

* Corre como daemon local (`openclaw onboard --install-daemon`), persistente vía systemd/launchd.
* Conecta con múltiples proveedores (Claude, GPT, Gemini, modelos locales) con **rotación automática de perfiles de auth y failover** entre modelos cuando uno falla o se agota.
* Sistema de **skills** propio (análogo a `.agents/skills/` que ya usa MILO con `skill_creator.py`).
* Memoria persistente y contexto por agente.
* Expone canales externos (Telegram, WhatsApp, Discord, Slack, etc.) si en el futuro se quiere sacar a MILO de la web local.

La idea **no es reemplazar a MILO**, sino que OpenClaw se convierta en la capa de orquestación de modelos por debajo de `AgyBrain`, dejando a MILO como fachada (FastAPI + frontend 3D) y dueño de la identidad/persona.

---

## 2. Arquitectura propuesta

```
┌─────────────────────────────┐
│  MILO Frontend (Three.js)   │
└──────────────┬───────────────┘
               │ WebSocket /ws/voice
┌──────────────▼───────────────┐
│  MILO Backend (FastAPI)      │
│  - response_formatter.py     │
│  - db_service.py (SQLite)    │
│  - proactive_engine.py       │
│  - circuit_breaker.py        │
└──────────────┬───────────────┘
               │ llamada local HTTP/MCP
┌──────────────▼───────────────┐
│  AgyBrain (orquestador)      │
│  decide motor según contexto │
└───────┬───────────────┬─────┘
        │               │
┌───────▼──────┐  ┌─────▼─────────────┐
│ agy (directo) │  │ OpenClaw Gateway   │
│ fallback local│  │ (daemon, :puerto)  │
└───────────────┘  │ - failover Claude/ │
                    │   GPT/Gemini       │
                    │ - clawo-mcp (tools)│
                    │ - skills propios   │
                    └────────────────────┘
```

Puntos clave:

* `AgyBrain` deja de ser un wrapper único de `agy` y pasa a tener **dos rutas**: la directa (`agy --dangerously-skip-permissions`, se mantiene como fallback de bajo nivel) y la nueva vía OpenClaw, que internamente decide qué proveedor usar.
* SQLite (`db_service.py`) sigue siendo la única fuente de verdad de tareas/skills/incidentes — OpenClaw no reemplaza la persistencia de MILO, solo el motor de inferencia.
* El `circuit_breaker.py` existente se reutiliza para decidir cuándo escalar de `agy` directo → OpenClaw (en vez de solo encolar en background).

---

## 3. Plan de implementación por fases

### Fase 1 — Instalación y aislamiento
1. Instalar OpenClaw en el mismo host (`npm install -g openclaw@latest`), Node 22.19+ o 24.
2. Ejecutar `openclaw onboard` (sin `--install-daemon` aún) para configurar workspace, autenticar proveedores (Claude, GPT, Gemini) y validar que el gateway responde localmente antes de tocar el código de MILO.
3. Definir un workspace dedicado para MILO (`~/.openclaw/workspaces/milo/`) para no mezclar contexto con otros usos del CLI.

### Fase 2 — Fusión de identidad
1. Copiar/adaptar las reglas de persona que ya viven en `AGENTS.md` (la fusión de identidad MILO=Antigravity) al formato de skill/persona de OpenClaw, para que el gateway responda igual de "humanizado" que exige `response_formatter.py` (1-2 oraciones, sin markdown, optimizado para TTS).
2. Migrar las herramientas activas del `TOOL_REGISTRY` (`web_search`, `fetch_page`, `list_workspace_files`, `read_local_file`, `get_current_weather`) a skills/MCP tools de OpenClaw para que estén disponibles también cuando el motor activo sea GPT o Gemini, no solo Antigravity.

### Fase 3 — Integración MCP (puente de herramientas)
1. Instalar `clawo-mcp` (de `claw-orchestrator`, plugin con soporte nativo OpenClaw) para exponer un runtime unificado sobre Claude Code, Gemini CLI, Codex y `agy` como motor "custom".
2. Registrar `clawo-mcp` en `~/.openclaw/openclaw.json` para que todos los agentes de OpenClaw compartan el mismo set de herramientas que MILO ya expone.
3. Esto habilita además el **proxy OpenAI-compatible** (`POST /v1/chat/completions`) de `clawo`, útil si en el futuro se quiere apuntar cualquier SDK estándar (OpenAI-shape) directo al cerebro de MILO sin tocar `agy_brain.py`.

### Fase 4 — Modificación de `agy_brain.py`
1. Añadir un cliente HTTP/MCP hacia el gateway de OpenClaw (puerto local del daemon).
2. Lógica de selección de motor:
   * Por defecto: intentar `agy` directo (latencia más baja, ya probado).
   * Si `circuit_breaker.py` detecta fallos consecutivos o un 429 → enrutar la misma petición a OpenClaw, que internamente rota a GPT o Gemini según el perfil de auth disponible.
   * Loguear en `tool_status` (SQLite) qué motor respondió, para telemetría en el panel lateral del frontend.
3. Mantener el contrato de salida igual (texto plano, sin `TOOL_CALL:` falsos) para que `response_formatter.py` no necesite cambios.

### Fase 5 — Daemon y resiliencia
1. Una vez validado en Fase 1-4, instalar el daemon real: `openclaw onboard --install-daemon` (systemd en Linux).
2. Configurar `openclaw doctor` como chequeo de salud, integrable al `proactive_engine.py` (ej. "OpenClaw gateway caído, usando solo `agy` directo").
3. Actualizar la Sección 6 de `MILO_STATE.md` ("Puntos Críticos") para reflejar que el 429 ya no bloquea: ahora hay failover real antes de encolar.

---

## 4. Optimización de tokens del CLI

Problema actual: cada llamada a `agy` probablemente reenvía contexto completo dado que SQLite guarda todo el historial y no hay mecanismo de sesión persistente a nivel de proceso.

Mitigaciones a implementar vía `clawo`/OpenClaw:

* **Sesiones persistentes (`SessionManager` de clawo):** en vez de invocar `agy --print` de cero en cada turno, mantener una sesión viva (`session-start` / `session-send`) que conserva contexto en el proceso del motor, reduciendo lo que hay que reenviar como prompt.
* **Recorte de historial en `db_service.py`:** antes de pasar contexto al motor, enviar solo los últimos N turnos relevantes + resumen comprimido de los anteriores (resumen generado una vez, cacheado, no recalculado en cada turno).
* **Prompt estricto ya existente:** mantener el umbral de 250 caracteres de `response_formatter.py` para respuestas de voz, que ya limita tokens de salida; extender el mismo criterio al tamaño del prompt de entrada.
* **Allowlist de herramientas MCP (`CLAWO_MCP_TOOLS`):** limitar qué herramientas se exponen por contexto de tarea (ej. no enviar el set completo de 65 tools en una pregunta simple de clima), reduciendo tokens de "system/tools" en cada llamada.
* **Routing barato-primero:** usar el motor más económico (Gemini Flash, ya en uso) para clasificación/triage de la intención del usuario, y reservar Claude/GPT solo para tareas que realmente lo requieran (código, investigación profunda vía `run_antigravity`).

---

## 5. Riesgos y validaciones pendientes

* **Latencia añadida:** un salto extra (MILO → OpenClaw → motor) puede sumar latencia perceptible en voz; medir antes de hacerlo default y dejar `agy` directo como camino rápido.
* **Duplicidad de herramientas:** evitar que `TOOL_REGISTRY` de MILO y las skills de OpenClaw definan la misma herramienta dos veces con comportamientos distintos.
* **Seguridad:** OpenClaw trata DMs/canales externos como input no confiable por diseño; si se conectan canales (Telegram, etc.) en el futuro, revisar políticas de pairing antes de exponer el workspace de MILO.
* **Pruebas:** correr `python -m pytest tests/` (83/83 actuales) tras cada fase; añadir tests nuevos para el path de failover (mock de 429 forzando el salto a OpenClaw).

---

## 6. Comandos de referencia

```bash
# Instalación OpenClaw
npm install -g openclaw@latest
openclaw onboard
openclaw doctor

# Instalación clawo (puente MCP multi-engine)
npm install -g @enderfga/claw-orchestrator
clawo serve   # dashboard en http://127.0.0.1:18796/dash

# Una vez validado: daemon persistente
openclaw onboard --install-daemon
```
