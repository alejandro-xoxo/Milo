# Historia: Fase 3 — Integración de OpenClaw (Motor Principal) y Mapeo de Marca Vulcan (Respaldo)

## ¿Qué queríamos hacer?
Integrar **OpenClaw** como el motor de inferencia principal (default) bajo la arquitectura "Zero API Keys" de MILO, y estructurar el acceso al CLI local (`agy`) renombrándolo como **Vulcan (CLI)** para que funcione únicamente como motor de respaldo (fallback) secundario si OpenClaw se desconecta o falla.

## ¿Por qué lo hicimos?
Para asegurar que OpenClaw actúe como el orquestador principal y gateway multi-proveedor por defecto de la aplicación, dejando a Vulcan (CLI) como una red de seguridad local de bajo nivel. Renombrar las herramientas a Vulcan unifica el diseño de UX ocultando el nombre de desarrollo 'agy', y permite a MILO reportar de forma transparente qué motor está procesando la consulta en el panel lateral de "Procesos Activos".

## ¿Cómo lo hicimos?

### 1. Inversión del Mecanismo de Fallback en `AgyBrain`
- Modificamos [agy_brain.py](file:///home/alejandro/Proyectos/Milo/src/services/agy_brain.py) para que la primera opción de consulta (`AgyBrain.ask`) sea llamar al gateway local de OpenClaw (`http://127.0.0.1:18789/v1/chat/completions`).
- Control por Circuit Breaker: se evalúa `check_circuit_breaker("openclaw")` al inicio.
- Si OpenClaw está desactivado en base de datos o su llamada HTTP falla, se registra la anomalía con `record_tool_failure("openclaw")` e `log_incident("openclaw", ...)` y se desvía la petición a Vulcan (CLI) mediante subprocess.

### 2. Telemetría de Motor Activo y UX de Procesos
- Añadimos `_log_active_engine(engine_name)` para almacenar qué motor respondió ('openclaw' o 'vulcan') en la tabla `tool_status` de SQLite.
- Modificamos [gemini_service.py](file:///home/alejandro/Proyectos/Milo/src/services/gemini_service.py) para obtener dinámicamente este proveedor activo, exponiendo la información correcta al frontend.
- Integramos un sistema de callbacks de estado (`status_callback`) en `AgyBrain.ask` para que reporte en tiempo real al panel lateral de la web qué motor está procesando la solicitud (ej. *"Invocando OpenClaw (Default)..."*, *"OpenClaw no disponible. Desviando a Vulcan (CLI)..."*, etc.).
- Modificamos [main.py](file:///home/alejandro/Proyectos/Milo/src/main.py) para que las advertencias e hilos de WebSocket apunten a la marca **Vulcan**.

### 3. Pruebas Unitarias Robustas
- Modificamos las pruebas unitarias en [test_agy_brain.py](file:///home/alejandro/Proyectos/Milo/tests/test_agy_brain.py) para:
  - Casos exitosos de OpenClaw (por defecto).
  - Fallback a Vulcan (CLI) al fallar la conexión de OpenClaw.
  - Activación del Circuit Breaker que puentea `openclaw` y consulta Vulcan de inmediato.
- Ejecutamos y validamos la suite completa (55 passed).

## ¿Para qué sirve?
Esto define a OpenClaw como el motor inteligente principal de MILO, manteniendo a Vulcan (CLI) como un respaldo ultra-seguro y local en caso de caídas o desconexiones. El panel lateral muestra al usuario en vivo cuál de los dos motores resolvió su petición, mejorando sustancialmente la UX de telemetría y transparencia del asistente.

## Archivos modificados/creados
- `src/services/agy_brain.py` (Modificado)
- `src/services/gemini_service.py` (Modificado)
- `src/main.py` (Modificado)
- `tests/test_agy_brain.py` (Modificado)

## Fecha
2026-06-30
