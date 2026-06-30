# Historia: Fase 3 — Integración de OpenClaw y Failover del Cerebro (AgyBrain)

## ¿Qué queríamos hacer?
Integrar la base para **OpenClaw** como capa de orquestación lógica y failover multi-proveedor bajo la arquitectura "Zero API Keys" de MILO, tal como se detalla en el archivo `OPENCLAW.md`. 

## ¿Por qué lo hicimos?
La dependencia directa del CLI de `agy` en `agy_brain.py` resultaba frágil ante límites de cuota (429) o fallos de conexión. La integración de un fallback automático a OpenClaw local permite desviar peticiones a otros motores (Claude, GPT, Gemini) mediante su gateway local antes de que las tareas queden encoladas por tiempo indefinido.

## ¿Cómo lo hicimos?

### 1. Cliente HTTP de OpenClaw en `agy_brain.py`
- Añadimos `_ask_openclaw(prompt)` en [agy_brain.py](file:///home/alejandro/Proyectos/Milo/src/services/agy_brain.py) que se conecta al gateway de OpenClaw local en `http://127.0.0.1:18789/v1/chat/completions` (OpenAI-compatible) usando la variable de entorno `OPENCLAW_URL` y el token opcional `OPENCLAW_TOKEN`.
- Añadimos control por Circuit Breaker: se llama a `check_circuit_breaker("agy")` antes de invocar la terminal.
- Si el comando local `agy` falla (código de salida != 0) o arroja error de cuota/429/exhausted, se registra un fallo en el circuit breaker con `record_tool_failure("agy")` e `log_incident("agy", ...)`, y se enruta de inmediato al gateway de OpenClaw.

### 2. Telemetría de Motor Activo
- Añadimos `_log_active_engine(engine_name)` para almacenar qué motor respondió ('agy' o 'openclaw') en la tabla `tool_status` de SQLite.
- Modificamos [gemini_service.py](file:///home/alejandro/Proyectos/Milo/src/services/gemini_service.py) para obtener dinámicamente este proveedor activo, exponiendo la información correcta al frontend.

### 3. Pruebas Unitarias Robustas
- Creamos el archivo de pruebas [test_agy_brain.py](file:///home/alejandro/Proyectos/Milo/tests/test_agy_brain.py) con tests mockeados para:
  - Casos exitosos de `agy` directo.
  - Fallback a OpenClaw al detectar errores de cuota (429).
  - Activación del Circuit Breaker que puentea `agy` y consulta OpenClaw de inmediato.
- Ejecutamos y validamos la suite completa (55 passed).

## ¿Para qué sirve?
Esto le otorga resiliencia a MILO: si el CLI de Google/Antigravity se queda sin cuota o tiene problemas de red, MILO recurre automáticamente a OpenClaw de forma transparente, rotando entre otros proveedores lógicos y previniendo la degradación del servicio.

## Archivos modificados/creados
- `src/services/agy_brain.py` (Modificado)
- `src/services/gemini_service.py` (Modificado)
- `tests/test_agy_brain.py` (Creado)

## Fecha
2026-06-30
