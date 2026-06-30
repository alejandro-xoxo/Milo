# Reporte de Estado y Arquitectura: Codex, Vulcan y OpenClaw (MILO V3)

Este documento detalla el estado actual de la implementación de los motores conversacionales en MILO, qué se ha completado, qué está pendiente y la factibilidad de las siguientes tareas.

---

## 1. Estado Actual de la Implementación (MILO V3 Intermedio)

### ✅ Completado e Integrado
* **Codex CLI como Motor Principal:** Todos los mensajes de conversación normales pasan por `/home/alejandro/.local/bin/codex exec` con control dinámico de temperatura/modelo (`gpt-5.4-mini` para tareas simples y `gpt-5.4` para complejas).
* **Bypass de OpenClaw y Cascada de Fallos:** Se removió OpenClaw y el fallback automático a Vulcan del flujo principal. Si Codex falla, la tarea se registra en la base de datos `task_queue` de SQLite para procesamiento diferido (background/nocturno) y no hay saltos silenciosos.
* **Vulcan (agy) como Herramienta Explícita:** Vulcan ahora solo responde a comandos que contienen palabras clave/triggers explícitos (ej. `vulcan`, `usa vulcan`, `activa vulcan`), limpiando el trigger y ejecutando la CLI en un sandbox.
* **Suite de Pruebas Unificadas:** Los tests unitarios en `tests/test_agy_brain.py` y `tests/test_proactive.py` se actualizaron para validar este comportamiento y pasan al 100% de forma aislada.

---

## 2. Estado de OpenClaw en el Sistema

* **Daemon Local Activo:** El binario de OpenClaw está instalado en `/home/alejandro/.nvm/versions/node/v24.18.0/bin/openclaw` y el servidor responde correctamente en el puerto local `18789` (retorna el dashboard / Control UI HTML).
* **Desacoplado de MILO:** Actualmente, `openclaw.json` no tiene registrado ningún servidor MCP (`clawo-mcp` está vacío) y `agy_brain.py` no realiza llamadas a OpenClaw para evitar la cascada automática e interferencias con Codex.

---

## 3. ¿Qué Falta por Hacer para Integrar OpenClaw Completamente?

Si se decide retomar el plan de `OPENCLAW.md`, las tareas pendientes son:

1. **Configurar Credenciales/Modelos en OpenClaw:** Autenticar proveedores externos (Anthropic Claude, OpenAI, etc.) dentro del daemon de OpenClaw.
2. **Re-conectar `clawo-mcp`:** Registrar el plugin de orquestación en `~/.openclaw/openclaw.json` para que OpenClaw tenga acceso al workspace de MILO.
3. **Modificar `agy_brain.py`:** Cambiar el cliente principal de Codex CLI a llamadas HTTP a la API de OpenClaw local (`POST /v1/chat/completions`).

---

## 4. Factibilidad de Configuración: ¿Agente o Usuario?

Para la configuración y puesta a punto de OpenClaw, **es mucho más factible que lo realices tú (el usuario)** debido a las siguientes restricciones del sandbox del agente:

> [!IMPORTANT]
> **Autenticación e Interactividad:**
> Comandos como `openclaw onboard` o la configuración de API keys/OAuth requieren interactuar con prompts interactivos en la terminal o abrir pestañas del navegador web. Dado que mi entorno de ejecución de terminal no es interactivo, estos procesos fallarán o se quedarán colgados esperando respuesta.
> 
> **Recomendación:**
> Te sugiero que ejecutes tú la configuración inicial de proveedores en OpenClaw:
> ```bash
> openclaw onboard
> ```
> Y configures los modelos que deseas usar. Una vez que el daemon de OpenClaw tenga acceso a las APIs necesarias y responda llamadas, yo puedo encargarme de programar el cliente HTTP y el router de resiliencia en `agy_brain.py`.
