# MILO — Continuación: Cero API Keys, Todo vía Antigravity CLI

> **Nota para el agente que lea este documento (Antigravity CLI / `agy`):** este archivo es una continuación directa de `MILO_plan.md` y de los documentos de extensión ya creados (`MILO_plan_extensiones_unificado.md`). Es una instrucción de arquitectura, no solo un resumen explicativo: a partir de aquí, MILO se construye y se mantiene SIN ninguna API key de Gemini, Anthropic ni ningún otro proveedor de LLM. Todo el razonamiento de MILO pasa exclusivamente por comandos ejecutados dentro de Antigravity CLI (`agy`), aprovechando la sesión ya autenticada con la cuenta de Google del usuario.

---

## 0. Regla no negociable de esta fase

**Prohibido:** cualquier código que use `requests`/`httpx`/SDK oficial contra `api.google.com`, `api.anthropic.com` o similares, con un header de `x-api-key` o `Authorization: Bearer`.

**Obligatorio:** toda inferencia de MILO se hace invocando `agy` como subproceso. Si `agy` falla, MILO encola la tarea o responde que no puede procesarla en ese momento — **no existe fallback con API key**. Esto es una decisión deliberada del usuario, no un descuido a corregir.

---

## 1. Arquitectura definitiva (reemplaza el cliente de API)

```
Usuario (texto o voz)
        │
MILO — Orquestador (FastAPI, sin cliente de API de LLM)
        │
        ▼
   AgyBrain (único punto de "inteligencia")
        │  ejecuta subprocess → agy run "<prompt>" --cwd <project_path>
        ▼
   Antigravity CLI (autenticado con cuenta Google, sesión ya abierta)
        │
        ▼
   Respuesta de texto → parseada → devuelta a MILO → al usuario (texto y/o voz)
```

`AgyBrain` es el **único** módulo que "piensa". No hay un segundo camino hacia ningún proveedor de LLM.

---

## 2. Implementación de `AgyBrain` (módulo central)

```python
import subprocess
import re
import json

class AgyBrain:
    """
    Único cerebro de MILO. No usa ninguna API key.
    Toda inferencia pasa por Antigravity CLI (agy), ya autenticado
    con la cuenta de Google del usuario.
    """

    def __init__(self, project_path: str):
        self.project_path = project_path

    def ask(self, prompt: str, mode: str = "chat") -> str:
        """
        mode='chat' -> conversación normal, sin tocar archivos del proyecto
        mode='code' -> permite que agy modifique el proyecto si la tarea lo requiere
        """
        permission = "proceed-in-sandbox" if mode == "chat" else "always-proceed"

        result = subprocess.run(
            ["agy", "run", prompt,
             "--cwd", self.project_path,
             "--permission", permission,
             "--no-interactive"],
            capture_output=True, text=True, timeout=300
        )

        if result.returncode != 0:
            # No hay fallback de API key. Se reporta el fallo tal cual.
            return f"[MILO] No pude completar esto con Antigravity CLI: {result.stderr.strip()}"

        return self._parse_output(result.stdout)

    def _parse_output(self, raw: str) -> str:
        # Preferir salida estructurada si la versión instalada de agy la soporta.
        # Revisar `agy run --help` para confirmar si existe --output-format json
        # en la versión actual; si existe, usarla en vez de este parser de texto.
        match = re.search(r"(?:Response:|Answer:)\s*(.+)", raw, re.DOTALL)
        return match.group(1).strip() if match else raw.strip()
```

**Instrucción para el agente que implemente esto:** antes de escribir el parser de texto definitivo, ejecutar `agy run --help` y `agy --help` en el entorno real para confirmar si existe un modo de salida estructurada (JSON). Si existe, usarlo en lugar de la expresión regular — es más confiable y menos frágil ante cambios de versión.

---

## 3. Voz, sin API key, vía `agy`

El flujo de voz definido en `MILO_plan_extensiones_unificado.md` (Parte II) se mantiene igual en cuanto a STT/TTS (Whisper + Piper, ambos locales/open-source, sin API key tampoco). Lo único que cambia es el paso de "razonamiento":

```
Voz del usuario
   │
Whisper (STT, local, sin API key)
   │
texto → AgyBrain.ask(texto, mode="chat")   ← aquí ya no hay llamada a Gemini API
   │
respuesta de agy
   │
Piper (TTS, local, sin API key)
   │
Voz de respuesta al usuario
```

No se requiere ningún cambio adicional en la capa de voz: ya estaba diseñada sin dependencias de pago, solo se reconecta el "cerebro" a `AgyBrain` en vez de a un cliente de API.

---

## 4. Function calling / Tool Orchestrator sin API nativa

Como no hay function calling nativo de una API, se usa el patrón de convención de texto ya definido en el documento de integración (`TOOL_CALL: nombre_herramienta(parametro="valor")`), incluido dentro del prompt que recibe `agy`:

```python
SYSTEM_CONTEXT = """
Eres el motor de razonamiento de MILO. Si necesitas usar una herramienta,
responde EXACTAMENTE así:
TOOL_CALL: nombre_herramienta(parametro1="valor1")

Herramientas disponibles:
- get_weather(city: str)
- web_search(query: str)
- run_antigravity_task(task: str, mode: str)  # tareas de código sobre el repo
"""

def ask_milo(user_input: str, brain: AgyBrain) -> str:
    full_prompt = SYSTEM_CONTEXT + f"\nUsuario: {user_input}"
    response = brain.ask(full_prompt, mode="chat")

    if response.startswith("TOOL_CALL:"):
        # Tool Orchestrator ejecuta la función real localmente,
        # y el resultado se reinyecta en un segundo turno a agy.
        tool_result = execute_tool_call(response)
        follow_up_prompt = f"Resultado de la herramienta: {tool_result}\nResponde al usuario."
        return brain.ask(follow_up_prompt, mode="chat")

    return response
```

---

## 5. Proactividad y skills, sin API key

Los módulos `proactive_engine.py` (Parte I) y la auto-creación de Skills también pasan a usar `AgyBrain.ask(...)` en vez de un cliente de API directo — no requieren ningún otro cambio de diseño, solo reemplazar el punto de llamada al modelo.

---

## 6. Lo que el usuario acepta conscientemente con esta decisión

- Si `agy` falla, se cae, o cambia su formato de salida sin aviso, MILO se queda sin poder razonar hasta que se resuelva — no hay segundo camino. Esto es intencional, no un bug a corregir después.
- La latencia de cada respuesta será mayor que con una API directa, porque `agy` tiene overhead de agente de coding (carga de contexto del proyecto), no es un endpoint de chat puro.
- El parsing de la salida de texto de `agy` es el punto más frágil del sistema: cualquier actualización de Antigravity CLI que cambie su formato de salida puede romper `AgyBrain._parse_output`. Fijar la versión de `agy` en producción (`agy --version`) y revisar el changelog antes de actualizar.

---

## 7. Roadmap de esta fase

- [ ] Eliminar cualquier código existente que use API key de Gemini/Anthropic directamente.
- [ ] Implementar `AgyBrain` como único módulo de inferencia.
- [ ] Verificar si `agy` soporta `--output-format json` antes de finalizar el parser.
- [ ] Reconectar el flujo de voz (Whisper/Piper) para que el paso de razonamiento use `AgyBrain` en vez del cliente de API anterior.
- [ ] Reconectar `proactive_engine.py` y el módulo de auto-creación de skills a `AgyBrain`.
- [ ] Implementar el patrón `TOOL_CALL:` para simular function calling sin API nativa.
- [ ] Fijar y documentar la versión de `agy` usada en producción.
- [ ] Probar el flujo completo (texto y voz) confirmando que en ningún punto del código queda una API key activa.
