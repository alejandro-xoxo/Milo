# Registro Histórico: Fase 3 — Optimización de Tokens y Orquestación Avanzada de OpenClaw

## 📌 Qué
Implementación de la persistencia de sesión por turnos, optimización de tokens en prompts mediante recorte y resúmenes de contexto en SQLite, enrutamiento barato-primero (triage), umbrales diferenciados en el Circuit Breaker y monitoreo proactivo del daemon de OpenClaw.

## 📌 Por qué
- **Consumo de tokens:** Antes del cambio, cada consulta procesaba de forma stateless la sesión completa repitiendo prompts redundantes.
- **Orquestación y costos:** Habilitar un clasificador rápido e inteligente antes de consultar modelos potentes ahorra tokens en system messages al bloquear/restringir el set de herramientas.
- **Seguridad y robustez:** Si el gateway primario (OpenClaw) cae, el sistema debe saberlo proactivamente para alertar al usuario y operar de forma segura usando el motor de respaldo (Vulcan/agy).

## 📌 Cómo
1. **Historial de Conversación en SQLite (`db_service.py`):**
   - Agregada la tabla `chat_history` para almacenar el histórico de roles (`user`, `assistant`), contenidos, marcas de tiempo y el resumen comprimido cacheado.
2. **Optimización de Contexto y Resúmenes (`agy_brain.py`):**
   - Implementado el método `get_optimized_context(session_id, max_turns)`.
   - Si los turnos exceden el umbral, se condensan los turnos antiguos usando una llamada stateless de resumen, cacheando el resultado de forma acumulativa y evitando recalcularlo cada turno.
3. **Routing Barato-Primero / Triage (`agy_brain.py`):**
   - Implementado `_run_triage(prompt)` consultando un modelo económico (`Gemini 3.5 Flash` / `openclaw/default`).
   - Clasifica la intención como `SIMPLE` (saludos, charla) o `COMPLEX` (código, shell).
   - Para intenciones `SIMPLE`, se inyecta una instrucción restrictiva en el system prompt del contexto del sistema para que no invoque herramientas MCP complejas y se reduce la ventana activa a 4 turnos. Para `COMPLEX` se habilita la ventana completa de 6 turnos y todas las herramientas.
4. **Daemon Supervisado y Salud Proactiva (`proactive_engine.py`):**
   - Configurado OpenClaw como servicio systemd de usuario (`openclaw-gateway.service`), garantizando su persistencia.
   - Implementada la función `_check_openclaw_health` que sondea el puerto `18789` usando un timeout ultra-rápido de 1.0s. Si la conexión falla, se genera el trigger `openclaw_offline` de severidad `medium` al iniciar sesión.
5. **Circuit Breaker Diferenciado (`agy_brain.py`):**
   - Ajustados los umbrales de fallos y cooldown: OpenClaw (triage rápido, falla rápido: `threshold=2`, `cooldown_minutes=3`) y Vulcan (tolerancia a cuota 429: `threshold=3`, `cooldown_minutes=30`).
6. **Tests y Cobertura (`tests/`):**
   - Añadidos tests para OpenClaw offline y comprobaciones de salud en `test_proactive.py`.
   - Modificados y sincronizados los tests de fallback en `test_agy_brain.py` con el flujo de triage.
   - **Paso exitoso de los 58 tests de la suite completa.**

## 📌 Para qué sirve
Garantiza un consumo óptimo y plano de tokens sin importar la duración de la conversación, automatiza el balance de costos y herramientas según la complejidad del input, asegura una conmutación de fallos instantánea y transparente, y provee telemetría directa al usuario sobre la integridad del daemon.
