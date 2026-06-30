# Historial de Cambios: Integración Completa de OpenClaw y Enrutamiento Resiliente (Fase 6)

Este documento registra las decisiones de diseño y cambios técnicos realizados para la fase de integración completa de OpenClaw como motor principal y de Codex CLI como fallback resiliente.

## 1. Qué se quería hacer
* Configurar el gateway local de OpenClaw (`http://127.0.0.1:18789`) para que sea el motor conversacional principal.
* Resolver las fallas de autenticación e incompatibilidad de modelos en OpenClaw bajo un esquema local sin API keys globales obligatorias.
* Implementar un esquema de enrutamiento resiliente en `AgyBrain.ask()`: OpenClaw primero -> Fallback a Codex CLI -> Encolado de tareas en SQLite.
* Ejecutar y verificar la suite completa de pruebas unitarias para confirmar que no hay regresiones.

## 2. Por qué se hizo
* Para centralizar la gestión de agentes, MCPs y memoria a través de OpenClaw como el backend de orquestación final de MILO.
* Para asegurar un funcionamiento libre de interrupciones mediante un circuit breaker y fallback fluido a Codex CLI local si el daemon de OpenClaw se desconecta o falla.
* Para habilitar el uso del API key de Gemini gratuito disponible en `.env` dentro de OpenClaw, optimizando la latencia y la calidad de las respuestas sin incurrir en costos de suscripción de OpenAI.

## 3. Cómo se hizo
* **Configuración del Gateway (`openclaw.json`):**
  * Se habilitó el endpoint HTTP OpenAI-compatible en `http://127.0.0.1:18789/v1/chat/completions` mediante la propiedad `gateway.http.endpoints.chatCompletions.enabled = true`.
  * Se configuró el proveedor `google` con la API key de Gemini extraída de `.env` usando el driver `google-generative-ai`.
  * Se estableció el modelo por defecto del agente a `google/gemini-2.5-flash` en la sección `agents.defaults.model.primary`, ya que Gemini 1.5 Flash fue deprecado.
* **Cliente en AgyBrain (`_ask_openclaw`):**
  * Se implementó el cliente REST en `src/services/agy_brain.py` para consultar el endpoint del gateway usando el token de autenticación de MILO.
* **Enrutamiento y Triage Optimizado:**
  * `ask()` intenta consultar OpenClaw primero.
  * Si falla o el breaker de `openclaw` está activo, desvía al fallback local de Codex CLI.
  * Se optimizó el proceso para ejecutar la clasificación de intención (`_run_triage()`) solo una vez por turno, reutilizando el resultado tanto en OpenClaw como en Codex.
  * Se adaptó `_run_triage()` y `_summarize_text()` para preferir OpenClaw con fallback a Codex.
* **Pruebas Unitarias:**
  * Se actualizaron las pruebas en `tests/test_agy_brain.py` para validar los comportamientos de éxito en OpenClaw, fallbacks encadenados y el encolado final ante fallas múltiples.

## 4. Para qué sirve
* Proporciona un canal conversacional primario ágil y con contexto optimizado utilizando Gemini 2.5 Flash de forma transparente a través del gateway de OpenClaw.
* Otorga robustez al sistema ante caídas del daemon de OpenClaw usando Codex CLI como respaldo inmediato.
* Preserva la capacidad de invocar de forma explícita a Vulcan (`vulcan, ...`) en el host para cambios automáticos de código.
