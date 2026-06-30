#> Este documento extiende `MILO_plan.md`. Asume que el MVP de texto + Tool Orchestrator + hosting gratuito ya está funcionando.

---

## 0. Resumen de lo que se añade

| Capacidad nueva | Qué significa en la práctica |
|---|---|
| **Proactividad** | MILO detecta situaciones y actúa/avisa sin que se le pida, dentro de los límites que tú definas |
| **Voz → Antigravity CLI** | Le hablas a MILO y él traduce eso en comandos que ejecuta `agy` (Antigravity CLI) para programar/corregir cosas |
| **Auto-creación de Skills** | MILO puede generar sus propios archivos `SKILL.md` cuando detecta que necesita un conocimiento/flujo que no tiene |
| **Navegación e investigación** | MILO puede salir a internet, leer páginas, comparar fuentes y traerte resultados sintetizados |

---

## 1. Proactividad

Jarvis nunca espera pasivamente; detecta contexto y actúa. Para lograr esto sin que MILO esté "siempre escuchando" (ya que lo activas manualmente), la proactividad ocurre **dentro de una sesión activa**, no en segundo plano 24/7.

### Mecanismo: Observador + Disparadores (triggers)
1. **Capa de observación de contexto:** cuando activas MILO, este lee señales disponibles al inicio de la sesión: archivos modificados recientemente, errores en logs de Antigravity de la noche, eventos de calendario del día (si conectas esa API), correos no leídos relevantes.
2. **Motor de reglas + LLM:** en lugar de que el LLM decida todo desde cero cada vez, define un set de "disparadores" simples (ej. `si hay > 3 errores en el log nocturno → avisar y proponer fix`, `si hay una tarea pendiente vencida → recordarla primero`). El LLM se usa para decidir *cómo* comunicarlo y *qué acción* proponer, no para detectar el patrón (eso es más barato y confiable con reglas).
3. **Apertura proactiva de sesión:** en vez de que MILO solo responda cuando le hablas, el primer mensaje de cada sesión lo genera él mismo: un resumen tipo "Mientras dormías pasó X, te recomiendo Y" — esto es lo que más se siente "Jarvis".

### Implementación técnica
- Un módulo `proactive_engine.py` que corre **al iniciar sesión** (no en background 24/7), recopila señales de las fuentes conectadas, y genera el primer mensaje antes de que tú escribas nada.
- Las "señales" se guardan en la misma base SQLite que ya usas para logging de errores (Fase 3 del plan anterior) — así reutilizas infraestructura existente.

---

## 2. Conectar voz con Antigravity CLI (programar hablando)

Esto separa dos roles claramente:
- **MILO** = el asistente conversacional con el que hablas.
- **Antigravity CLI (`agy`)** = el motor que de verdad escribe/corrige código.

MILO actúa como **intermediario por voz** que traduce tu intención hablada en comandos hacia `agy`.

### Flujo completo
```
Tu voz
   │
Speech-to-Text (Whisper, local o en el servidor)
   │
MILO (Gemini) interpreta la intención
   │
MILO arma el prompt/comando para Antigravity CLI
   │
Ejecuta vía subprocess: agy run "<instrucción>" --model gemini-3.5-flash
   │
Antigravity CLI programa/corrige en el repo
   │
MILO lee el resultado (logs/diff) y te responde por voz (TTS)
```

### Piezas técnicas
1. **STT (voz → texto):** Whisper corriendo en tu servidor (no en tu PC, para no calentarla). Si la latencia es un problema, puedes usar el modelo `whisper-small` para velocidad.
2. **Puente MILO ↔ agy:** una herramienta nueva en tu Tool Orchestrator, por ejemplo `run_antigravity_task(instruction: str, project_path: str)`, que internamente hace:
   ```python
   subprocess.run(["agy", "run", instruction, "--cwd", project_path, "--permission", "always-proceed"])
   ```
3. **Traducción de intención:** el LLM de MILO no manda tu frase tal cual a `agy`; primero la reformula en una instrucción técnica clara (igual que harías tú escribiendo un buen prompt), porque "oye arregla eso de ayer" no es un buen comando para Antigravity. MILO debe tener contexto de "qué se hizo ayer" (de los logs) para poder traducir bien.
4. **TTS (texto → voz):** Piper o Coqui TTS para que MILO te responda en voz cuando termine la tarea ("Listo, ya corregí los tests que fallaban anoche").
5. **Permisos:** como ya decidiste que NO quieres confirmaciones constantes, esta herramienta corre con `always-proceed`, pero — igual que con control de dispositivos — define una lista blanca de qué tipo de tareas puede lanzar por voz sin pausa (refactors, fixes, docs) vs. cuáles sí deben pedir confirmación verbal (borrar código, hacer deploy a producción, cambiar credenciales).

---

## 3. Auto-creación de Skills

Antigravity CLI ya soporta Agent Skills (`SKILL.md` en `.agents/skills/`). La idea aquí es que **MILO mismo identifique cuándo necesita una skill nueva y la genere**, en vez de que tú tengas que escribirla a mano cada vez.

### Cuándo se dispara la creación de una skill
- MILO detecta que repitió un mismo tipo de tarea (ej. "investigar precios de X", "generar reporte de Y") más de N veces sin tener un flujo guardado para ello.
- MILO falla repetidamente en un tipo de tarea y, tras resolverla con ayuda tuya o de Antigravity, guarda el procedimiento que funcionó como skill para no volver a fallar igual.

### Flujo técnico
1. MILO detecta el patrón → genera un borrador de `SKILL.md` (nombre, descripción, pasos, ejemplos) usando el propio LLM.
2. Lo guarda en `.agents/skills/<nombre>/SKILL.md` dentro del repo.
3. Hace commit de la skill nueva (vía `agy` o git directo) para que quede disponible tanto para Antigravity CLI como para el propio Tool Orchestrator de MILO.
4. En la siguiente sesión, MILO ya puede invocar esa skill como conocimiento reutilizable en vez de razonar desde cero.

### Nota de control
Dado que esto modifica el comportamiento futuro del propio sistema, conviene loguear cada skill auto-creada en un changelog simple (`skills_changelog.md`) para que puedas revisar qué "hábitos" está adquiriendo MILO, aunque no tengas que aprobarlos uno por uno en el momento.

---

## 4. Navegación e investigación web

MILO necesita poder salir a buscar información real, no solo responder con lo que el LLM ya sabe.

### Opciones (de más simple a más potente)
1. **Búsqueda + lectura de páginas (lo mínimo viable):**
   - Herramienta `web_search(query)` usando alguna API de búsqueda gratuita (ej. la API gratuita de Brave Search, o scraping ligero con `requests` + `BeautifulSoup` si quieres evitar dependencias de pago).
   - Herramienta `fetch_page(url)` que descarga y limpia el HTML a texto plano para que el LLM lo lea.
2. **Navegación interactiva real (más "Jarvis"):**
   - Usar **Playwright** (gratis, open-source) para controlar un navegador real: hacer clic, llenar formularios, navegar entre páginas — útil si necesitas que MILO interactúe con sitios que no son simples de leer con scraping.
   - Esto es más pesado en recursos; corre en el servidor cloud, no en tu PC.
3. **Síntesis de investigación:**
   - Cuando la tarea es "investiga X", MILO no debe devolver un solo resultado: arma un mini-pipeline donde busca 3-5 fuentes, las lee, y el LLM sintetiza una respuesta comparando lo encontrado — similar a un "modo research" simple, hecho con tus propias herramientas en vez de depender de un servicio externo de pago.

### Dónde corre esto
Todo el navegador/scraper corre en tu servidor cloud (Oracle/Fly.io), igual que el resto de MILO — tu PC nunca ejecuta esto.

---

## 5. Roadmap de esta fase

### Sub-fase A — Proactividad básica
- [ ] `proactive_engine.py`: recopila señales al iniciar sesión.
- [ ] Mensaje de apertura autogenerado en cada sesión.
- [ ] Reglas simples de disparo (errores nocturnos, tareas vencidas).

### Sub-fase B — Voz → Antigravity CLI
- [ ] STT con Whisper en el servidor.
- [ ] Herramienta `run_antigravity_task` en el Tool Orchestrator.
- [ ] Lista blanca de instrucciones permitidas sin confirmación verbal.
- [ ] TTS de respuesta con Piper/Coqui.

### Sub-fase C — Auto-creación de skills
- [ ] Detección de patrones repetidos (contador simple en SQLite).
- [ ] Generador de `SKILL.md` con el LLM.
- [ ] Commit automático de skills nuevas.
- [ ] `skills_changelog.md` para auditoría pasiva.

### Sub-fase D — Navegación e investigación
- [ ] `web_search` + `fetch_page` como herramientas básicas.
- [ ] Playwright para navegación interactiva (si se necesita).
- [ ] Pipeline de síntesis multi-fuente para tareas tipo "investiga X".

---

## 6. Riesgos específicos de esta fase

- **Voz sin confirmación ejecutando código:** un mal entendido de STT podría traducirse en una instrucción destructiva para Antigravity. La lista blanca de la Sub-fase B no es opcional, es la salvaguarda mínima.
- **Skills auto-creadas de mala calidad:** si MILO genera skills basadas en patrones mal detectados, puede "aprender" malos hábitos. El changelog te permite limpiar/borrar skills problemáticas periódicamente sin tener que aprobar cada una en tiempo real.
- **Costo de cómputo en el servidor gratuito:** Whisper + Playwright + LLM corriendo juntos pueden exceder los límites de un tier gratuito pequeño (Render/Railway). Si notas lentitud o caídas, es momento de migrar definitivamente a Oracle Free Tier (más recursos sostenidos sin dormir el servicio).

---

# PARTE II — Interfaz Gráfica y Voz en Tiempo Real (100% Gratis)

> Extiende `MILO_plan.md` y `MILO_plan_fase_avanzada.md`. Aquí se define cómo MILO deja de ser "solo backend" y se convierte en algo con pantalla y voz en vivo, tipo Jarvis, sin pagar nada.

---

## 0. Qué significa "tiempo real" aquí (importante ser realista)

"Hablar en tiempo real" como Jarvis tiene dos niveles, y con stack 100% gratuito conviene apuntar al nivel 1 primero:

1. **Nivel 1 — Conversación por turnos con baja latencia:** hablas, MILO procesa, responde en voz, casi sin notar espera (1-3 segundos). **Esto es 100% alcanzable gratis.**
2. **Nivel 2 — Streaming continuo bidireccional** (interrumpirlo a media frase, como el modo de voz nativo de apps comerciales): técnicamente posible con herramientas open-source, pero mucho más pesado de mantener gratis en un servidor de tier libre. Lo dejamos como mejora futura, no como meta inicial.

Vamos con Nivel 1: se siente natural y conversacional, sin que necesites infraestructura cara.

---

## 1. Arquitectura de la interfaz

```
┌─────────────────────────────────────────┐
│     INTERFAZ GRÁFICA (Frontend web)      │
│   Texto + botón de micrófono + avatar/   │
│   indicador visual de "escuchando/        │
│   pensando/hablando"                      │
└───────────────┬───────────────────────────┘
                │ WebSocket (conexión persistente, gratis)
                ▼
┌─────────────────────────────────────────┐
│   Backend MILO (FastAPI) — en tu server  │
│   gratuito (Oracle/Fly.io)               │
│   - Recibe audio → STT (Whisper)         │
│   - Llama a Gemini (texto)               │
│   - Genera respuesta → TTS (Piper)       │
│   - Envía audio + texto de vuelta        │
└─────────────────────────────────────────┘
```

**Por qué WebSocket y no peticiones normales:** una conexión persistente permite que la interfaz muestre estados en vivo ("escuchando", "pensando", "hablando") sin recargar nada, que es justo lo que da la sensación de "tiempo real" tipo Jarvis. Es gratis y nativo en FastAPI (no necesitas un servicio de terceros).

---

## 2. Stack de interfaz gráfica (gratis)

| Componente | Tecnología | Por qué |
|---|---|---|
| Frontend | HTML + CSS + JS plano, o React si ya te sientes cómodo | No necesitas nada de pago; se sirve como archivos estáticos desde el mismo backend o gratis en GitHub Pages / Vercel free tier |
| Comunicación en vivo | WebSocket nativo (`fastapi.WebSocket`) | Incluido en FastAPI, sin costo, sin servicio externo |
| Captura de voz en el navegador | Web Audio API / `MediaRecorder` (nativo del navegador) | No requiere librería de pago; todos los navegadores modernos lo soportan |
| Indicador visual | Una animación CSS simple (círculo pulsante tipo "Jarvis arc reactor") | Puro frontend, cero costo, mucho efecto |
| Reproducción de voz | `<audio>` HTML reproduciendo el archivo TTS que devuelve el backend | Nativo del navegador |

**Nota sobre "avatar":** si quieres algo visual más vistoso (un círculo animado tipo Jarvis/HAL, ondas de audio reaccionando a la voz), se puede hacer con un Canvas/SVG animado en CSS/JS — no necesitas modelos 3D ni nada pago, una animación bien hecha en 2D ya transmite la sensación.

---

## 3. Flujo de conversación de voz en tiempo real (Nivel 1)

1. **Click en micrófono** (o un futuro hotword "Oye MILO" — ver sección 5) → el navegador empieza a grabar con `MediaRecorder`.
2. El audio se envía por WebSocket al backend en cuanto detecta silencio (Voice Activity Detection simple, gratis con la librería `webrtcvad` en Python).
3. Backend: Whisper transcribe → Gemini procesa con function calling (puede llamar herramientas del Tool Orchestrator) → genera respuesta en texto.
4. Backend convierte la respuesta a voz con Piper (rápido y ligero, ideal para baja latencia en CPU sin GPU).
5. El audio de respuesta se envía de vuelta por el mismo WebSocket y se reproduce automáticamente en la interfaz.
6. La interfaz muestra el texto de la respuesta simultáneamente (subtítulos), útil si estás en un lugar donde no puedes/quieres tener audio.

### Por qué Piper y no otra opción de TTS
Piper está diseñado para correr rápido en CPU (no necesita GPU), lo cual es clave porque tu servidor gratuito probablemente no tendrá GPU. Genera voces bastante naturales para ser gratis y local, y soporta español.

---

## 4. Mantenerlo gratis: puntos críticos a vigilar

- **Whisper y Piper corren en tu servidor cloud gratuito, NO en tu PC** (consistente con el resto del plan). Pero ambos consumen CPU; en un tier muy pequeño (Render free) la latencia puede sentirse lenta. Si pasa esto, es la señal definitiva de migrar a Oracle Free Tier, que da más CPU sostenida sin costo.
- **No uses APIs de voz de pago** (ej. ElevenLabs, Google TTS de pago) — Piper/Coqui cubren la necesidad sin gastar nada, aunque la calidad de voz sea un escalón debajo de las opciones comerciales.
- **WebSocket persistente cuidando recursos:** cierra la conexión cuando no estás usando MILO activamente (no la dejes abierta indefinidamente), para no consumir innecesariamente los recursos limitados del tier gratuito.

---

## 5. Mejoras futuras (no para el MVP de esta fase)

- **Hotword ("Oye MILO")** para activar por voz sin tocar el mouse: se puede hacer gratis con `openWakeWord` u otra librería de wake-word open-source corriendo en el navegador o en un cliente ligero.
- **Streaming real (Nivel 2):** Gemini Live API tiene un modo de streaming de voz, pero revisar si su tier gratuito lo cubre antes de depender de él; si no, se puede aproximar con chunks de audio más pequeños y respuestas parciales, aunque es más complejo de mantener estable gratis.
- **Avatar más elaborado:** animaciones reactivas a la amplitud del audio (ondas que se mueven con tu voz) — efecto visual fuerte, sigue siendo gratis con JS/Canvas.

---

## 6. Roadmap de esta fase

- [ ] Página HTML simple con botón de micrófono + indicador de estado.
- [ ] Endpoint WebSocket en FastAPI (`/ws/voice`).
- [ ] Integrar Whisper para STT en el backend.
- [ ] Integrar Piper para TTS en el backend.
- [ ] Conectar el flujo completo: voz → texto → Gemini → texto → voz → reproducción.
- [ ] Animación visual de estado (escuchando/pensando/hablando).
- [ ] Subtítulos en pantalla sincronizados con el audio de respuesta.
- [ ] Pruebas de latencia en el servidor gratuito elegido; migrar de tier si es necesario.

---

# PARTE III — Integración con Antigravity CLI como Herramienta de Razonamiento

> Extiende los documentos anteriores. Aquí se define cómo Antigravity CLI deja de ser "algo que se usa por voz aparte" y se convierte en **una herramienta más dentro del Tool Orchestrator de MILO**, que MILO puede invocar por sí mismo cuando razona que la tarea lo requiere — ya sea para investigar algo o para programar algo.

---

## 0. Idea central

Hasta ahora, Antigravity CLI (`agy`) se usaba solo cuando tú hablabas y pedías programar algo. Ahora lo que quieres es que **MILO decida solo, como parte de su razonamiento normal**, cuándo conviene delegarle una tarea a `agy` — igual que decide cuándo usar la herramienta de clima o la de búsqueda web. `agy` se convierte en un "subagente experto" al que MILO recurre.

```
Tú: "Milo, necesito saber cómo está el repo y arreglar el bug de ayer"
        │
MILO (Gemini) razona: "esto requiere examinar código y corregirlo,
                        no lo puedo hacer yo solo con texto, delego a agy"
        │
MILO llama a la herramienta: run_antigravity(task, mode)
        │
Antigravity CLI ejecuta la tarea real sobre el repo
        │
MILO recibe el resultado/log → lo interpreta → te responde en lenguaje natural
```

MILO actúa como el "cerebro conversacional" y Antigravity CLI como las "manos técnicas profundas" cuando la tarea excede lo que el propio Tool Orchestrator simple puede hacer.

---

## 1. Dos modos de uso de la herramienta `agy`

Defines la herramienta con un parámetro `mode` para que MILO sepa cuál pedir según la tarea:

### Modo `research` (investigación/información)
- Para cuando necesitas que se investigue algo dentro del propio proyecto/código: "¿qué hace este módulo?", "¿por qué falla este test?", "resume el estado del repo".
- Antigravity CLI tiene contexto profundo del código (a diferencia de MILO, que solo ve lo que tú le cuentas), así que es mejor delegarle preguntas sobre el propio proyecto en vez de que MILO improvise sin ver el código real.
- Se ejecuta en modo de solo lectura/análisis, sin tocar archivos.

### Modo `code` (programar/corregir)
- Para cuando la tarea implica modificar archivos reales: arreglar bugs, implementar features, refactorizar.
- Se ejecuta con permisos de escritura (`always-proceed`, como ya definiste).

```python
def run_antigravity(task: str, mode: Literal["research", "code"], project_path: str) -> str:
    permission = "proceed-in-sandbox" if mode == "research" else "always-proceed"
    result = subprocess.run(
        ["agy", "run", task, "--cwd", project_path, "--permission", permission],
        capture_output=True, text=True, timeout=600
    )
    return result.stdout
```

Esta función se registra como **una tool más** en el esquema de function calling que ya tienes definido para Gemini — MILO la ve igual que ve `web_search` o `get_weather`, y decide cuándo usarla según el esquema/descripción que le das (el `description` del tool es lo que más influye en que MILO la elija bien).

---

## 2. Cómo hacer que MILO "razone" cuándo usarla (no solo ejecute por palabra clave)

La clave no es que detectes la palabra "programar" en tu frase y dispares `agy` por reglas fijas — eso sería frágil. Es que **el LLM decida**, igual que decide cualquier otra tool call, basándose en:

1. **Una descripción de herramienta bien escrita**, por ejemplo:
   > "Usa esta herramienta cuando la tarea requiera examinar, escribir o corregir código real dentro del repositorio del proyecto, algo que no puedes hacer solo con razonamiento de texto. No la uses para preguntas generales que no involucren el código del proyecto."
2. **Contexto del proyecto disponible para MILO**: si MILO no sabe que existe un repo, nunca va a pensar en usar `agy`. Dale en el system prompt una referencia clara: "Tienes acceso a un proyecto de código en `project_path`, y puedes delegar tareas técnicas profundas a Antigravity CLI."
3. **Resultado de la tool alimentando el siguiente razonamiento**: cuando `agy` responde, ese texto vuelve a Gemini como resultado de la tool call, y MILO sigue razonando sobre eso (por ejemplo, decidir si necesita pedirle a `agy` un segundo paso, o si ya puede responderte directamente).

Esto es exactamente el patrón estándar de **tool use en cadena**: MILO no "sabe programar", sabe **cuándo pedirle a quien programa que lo haga**, y luego interpreta el resultado para ti. Es el mismo principio de "Reasoning & Planning + Tool Orchestrator" que ya tenías en la arquitectura original de MILO, solo que ahora una de las tools es en sí misma un agente completo (Antigravity CLI) en lugar de una función simple.

---

## 3. Manejo de tareas largas (Antigravity puede tardar)

A diferencia de tus otras tools (clima, búsqueda), una tarea de programación real puede tardar minutos. Esto afecta tu arquitectura:

- **No bloquear la conversación:** lanza `agy` como tarea asíncrona en background (ya tienes el patrón de "tareas async" mencionado en el plan de hosting). MILO le dice al usuario "Voy a investigar/corregir esto, te aviso cuando termine" en vez de quedarse "congelado" esperando.
- **Notificación al terminar:** cuando `agy` termina, el resultado se guarda (en la misma cola/estado que ya usas para la cuota agotada) y, en tu próxima interacción con MILO (o por la apertura proactiva de sesión que ya planeaste), te informa el resultado.
- **Reusa la cola de tareas (`tasks_queue.json`) que ya definiste** en el plan original para cuota agotada — aquí sirve también para tareas en progreso de Antigravity, no solo para reintentos por límite de API.

---

## 4. Resultado: MILO como "director" y Antigravity como "ejecutor técnico"

Con esto, la división de trabajo queda clara y consistente con todo lo que ya construiste:

| | MILO (Gemini + Tool Orchestrator) | Antigravity CLI |
|---|---|---|
| Rol | Conversación, razonamiento, decidir qué hacer | Ejecutar tareas técnicas profundas sobre código real |
| Cuándo actúa | Siempre que lo activas | Solo cuando MILO decide delegarle algo |
| Ve el código | No directamente | Sí, contexto completo del repo |
| Responde a ti | Sí, en lenguaje natural/voz | No directamente — su salida pasa por MILO primero |

Esto es justo el patrón "Jarvis": tú le hablas a una sola entidad (MILO), y por debajo MILO orquesta herramientas y agentes especializados sin que tú tengas que saber que existen — la inteligencia percibida viene de la orquestación, no de que un solo modelo lo sepa todo.

---

## 5. Roadmap de esta integración

- [ ] Definir la tool `run_antigravity` con sus dos modos (`research`, `code`) en el esquema de function calling de Gemini.
- [ ] Escribir la descripción de la tool con cuidado (es lo que más determina si MILO la usa bien o no).
- [ ] Implementar ejecución asíncrona (no bloqueante) de `agy` desde el backend.
- [ ] Reusar `tasks_queue.json` para tareas largas de Antigravity en progreso.
- [ ] Probar con tareas reales: una de `research` ("¿qué hace el módulo X?") y una de `code` ("arregla el bug Y") para validar que MILO elige el modo correcto sin que se lo indiques explícitamente.
- [ ] Ajustar el system prompt de MILO para que sepa que el proyecto/repo existe y puede delegarle tareas a Antigravity.
