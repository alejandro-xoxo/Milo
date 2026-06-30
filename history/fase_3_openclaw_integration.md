# Historia: Fase 3 — Integración de OpenClaw y Mapeo de Marca Vulcan (AgyBrain)

## ¿Qué queríamos hacer?
Integrar la base para **OpenClaw** como capa de orquestación lógica y failover multi-proveedor bajo la arquitectura "Zero API Keys" de MILO, y estructurar el acceso a las herramientas lógicas renombrando `agy` bajo el nombre de marca **Vulcan (CLI)** para mejorar la experiencia de usuario (UX).

## ¿Por qué lo hicimos?
La dependencia directa del CLI de `agy` en `agy_brain.py` resultaba frágil ante límites de cuota (429) o fallos de conexión. Renombrar las herramientas internas y la telemetría a **Vulcan** ayuda a independizar la terminología interna de desarrollo ("agy"/"Antigravity") de la interfaz limpia que el usuario ve, y permite a MILO reportar de forma transparente en su panel de "Procesos Activos" qué motor está resolviendo cada prompt en tiempo real.

## ¿Cómo lo hicimos?

### 1. Cliente HTTP de OpenClaw y Mapeo "Vulcan"
- Añadimos `_ask_openclaw(prompt)` en [agy_brain.py](file:///home/alejandro/Proyectos/Milo/src/services/agy_brain.py) que se conecta al gateway de OpenClaw local en `http://127.0.0.1:18789/v1/chat/completions` (OpenAI-compatible) usando la variable de entorno `OPENCLAW_URL` y el token opcional `OPENCLAW_TOKEN`.
- Mapeamos toda la telemetría, el circuit breaker y la gestión de incidentes bajo la clave `"vulcan"` en la base de datos de SQLite (tabla `tool_status`).
- Si la terminal `agy` falla (código de salida != 0) o arroja error de cuota/429/exhausted, se registra un fallo en el circuit breaker con `record_tool_failure("vulcan")` e `log_incident("vulcan", ...)`, y se enruta de inmediato al gateway de OpenClaw.

### 2. Telemetría de Motor Activo y UX de Procesos
- Añadimos `_log_active_engine(engine_name)` para almacenar qué motor respondió ('vulcan' o 'openclaw') en la tabla `tool_status` de SQLite.
- Modificamos [gemini_service.py](file:///home/alejandro/Proyectos/Milo/src/services/gemini_service.py) para obtener dinámicamente este proveedor activo, exponiendo la información correcta al frontend.
- Integramos un sistema de callbacks de estado (`status_callback`) en `AgyBrain.ask` para que reporte en tiempo real al panel lateral de la web qué motor está procesando la solicitud (ej. *"Invocando Vulcan (CLI)..."*, *"Vulcan sin cuota. Desviando a OpenClaw..."*, etc.).
- Modificamos [main.py](file:///home/alejandro/Proyectos/Milo/src/main.py) para que las advertencias e hilos de WebSocket apunten a la marca **Vulcan**.

### 3. Pruebas Unitarias Robustas
- Creamos el archivo de pruebas [test_agy_brain.py](file:///home/alejandro/Proyectos/Milo/tests/test_agy_brain.py) con tests mockeados para:
  - Casos exitosos de `agy` (Vulcan) directo.
  - Fallback a OpenClaw al detectar errores de cuota (429).
  - Activación del Circuit Breaker que puentea `vulcan` y consulta OpenClaw de inmediato.
- Ejecutamos y validamos la suite completa (55 passed).

## ¿Para qué sirve?
Esto le otorga resiliencia e identidad a MILO: si el CLI de Google/Antigravity se queda sin cuota, MILO recurre automáticamente a OpenClaw de forma transparente, rotando entre otros proveedores lógicos y previniendo la degradación del servicio. Además, el panel lateral de procesos activos de la interfaz web muestra de forma elegante si las consultas están siendo resueltas por "Vulcan (CLI)" o por "OpenClaw".

## Archivos modificados/creados
- `src/services/agy_brain.py` (Modificado)
- `src/services/gemini_service.py` (Modificado)
- `src/main.py` (Modificado)
- `tests/test_agy_brain.py` (Creado)

## Fecha
2026-06-30
