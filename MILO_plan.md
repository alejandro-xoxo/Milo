# MILO — Plan Técnico de Construcción

## 0. Decisiones clave (según tu contexto real)

- **Tu PC (i5 8va gen, 16GB RAM, se calienta)** NO va a correr el modelo de IA ni el servidor de MILO 24/7. Solo se usa para programar con Antigravity CLI durante el día. El cómputo pesado vive en la nube gratuita.
- **Cerebro de MILO:** Gemini API (gratis vía Google AI Studio), NO modelo local. Tu hardware no soporta LLMs locales decentes sin sobrecalentarse.
- **Loop autónomo:** se divide en dos loops distintos que no deben confundirse:
  1. **Dev Loop (con Antigravity CLI):** mientras duermes, Antigravity sigue programando/depurando MILO en segundo plano, sin pedirte confirmación.
  2. **Self-healing en producción:** una vez MILO esté corriendo como servicio, si una tarea falla, el propio sistema reintenta, diagnostica y corrige sin esperar a que tú apruebes.
- **Manejo de cuota agotada:** el sistema no se detiene, encola la tarea y la reintenta más tarde o rota a otra fuente gratuita disponible.

---

## 1. Arquitectura de despliegue (gratis, sin tu PC encendida)

```
Tu PC (solo developing, de día)
   └── Antigravity CLI → escribe/corrige código → git push
                                    │
                                    ▼
                    Repositorio en GitHub (gratis)
                                    │
                                    ▼
        Servidor gratuito 24/7 (Railway / Render / Fly.io / Oracle Cloud Free Tier)
                                    │
                    MILO corriendo ahí, conectado a:
                                    │
                          Gemini API (gratis, AI Studio)
```

**Por qué así:** tu PC se calienta y no es confiable para un proceso 24/7. Un servicio cloud gratuito (con límites, pero suficientes para uso personal) resuelve la disponibilidad sin gastar dinero ni quemar tu hardware.

### Opciones de hosting gratuito a evaluar (en este orden)
1. **Oracle Cloud Free Tier** — la más generosa, instancia "always free" real, sin caducar. Requiere tarjeta para verificar identidad pero no cobra si te quedas en el tier free.
2. **Fly.io** — capa gratuita pequeña, fácil de desplegar con Docker.
3. **Railway / Render** — capas gratuitas más limitadas (duermen tras inactividad), buenas para empezar a probar antes de migrar a Oracle.

---

## 2. Antigravity CLI como motor de desarrollo nocturno

### Configuración necesaria para que NO pida confirmaciones
- Antigravity CLI tiene un ajuste de **Tool Permission** (vía `/config`):
  - `request-review` (default, pide tu OK) ❌ no sirve para tu caso
  - `proceed-in-sandbox` (actúa libre dentro de un entorno aislado)
  - `always-proceed` ✅ esto es lo que necesitas para que actúe sin pedirte nada mientras duermes
- Configura `always-proceed` SOLO en un entorno/proyecto aislado (sandbox, contenedor o VM), nunca en tu sistema completo, para evitar daños si algo sale mal mientras no estás mirando.

### Cómo estructurar las tareas nocturnas
1. Antes de dormir, defines un archivo `AGENTS.md` en la raíz del repo con instrucciones claras de qué construir/corregir esa noche (ej. "implementa el Tool Orchestrator", "corrige los tests que fallan", "documenta el módulo X").
2. Usas **tareas programadas (scheduled tasks)** de Antigravity 2.0/CLI para que arranque solo a una hora y trabaje en segundo plano.
3. Activas **subagentes dinámicos**: Antigravity puede dividir el trabajo nocturno en varios subagentes en paralelo (uno arregla bugs, otro escribe tests, otro documenta) sin que tengas que orquestarlo a mano.
4. Al despertar: revisas el log de la sesión (`agy inspect` o el resumen exportado) y el diff de los commits antes de aceptar los cambios en tu rama principal. (Recomendado aunque sea autónomo: revisar en frío, no en caliente, no te quita autonomía nocturna).

### Manejo de cuota agotada durante la noche
- Si la cuota gratuita de Gemini se agota a mitad de la noche:
  - Configura el agente para **encolar** las tareas pendientes en un archivo de estado (`tasks_queue.json`) en lugar de fallar.
  - Define un **modelo de respaldo** (fallback) en la config de Antigravity CLI: si Gemini 3.5 Flash no responde por límite de cuota, cae a otro modelo/proveedor gratuito disponible (ej. otra cuenta de AI Studio, o un proveedor gratuito alterno como Groq).
  - Si todos los proveedores están agotados, el agente debe simplemente **dormir y reintentar** en el siguiente ciclo (ej. cada 30-60 min) en lugar de terminar el proceso.

---

## 3. Self-healing de MILO en producción (cuando ya esté corriendo)

Esto es código que tú escribes (con ayuda de Antigravity) dentro de MILO mismo, no algo que Antigravity CLI haga por ti en producción.

### Componentes necesarios
1. **Capa de reintentos (retry layer):** cada llamada a una herramienta o API pasa por un wrapper con reintentos exponenciales (ej. librería `tenacity` en Python) antes de marcar la tarea como fallida.
2. **Diagnóstico automático de errores:** cuando una herramienta falla, el error se envía de vuelta al LLM (Gemini) como contexto, pidiéndole que proponga una corrección (cambiar parámetros, usar otra herramienta, ajustar el plan).
3. **Registro de incidentes (logging):** cada fallo y su resolución se guarda en una base de datos simple (SQLite) para que MILO "aprenda" patrones de fallos recurrentes.
4. **Circuit breaker:** si una herramienta falla repetidamente (ej. 5 veces seguidas), se desactiva temporalmente para no entrar en bucles infinitos costosos de cuota.
5. **Modo degradado:** si Gemini no responde (cuota o caída del servicio), MILO debe poder seguir funcionando en un modo reducido (ej. solo ejecutar tareas ya planificadas, sin generar nuevas, hasta que el servicio vuelva).

---

## 4. Stack tecnológico final

| Componente | Tecnología | Costo |
|---|---|---|
| Desarrollo asistido | Antigravity CLI | Gratis (cuenta Google) |
| Cerebro / razonamiento | Gemini API (AI Studio) | Gratis (con cuota diaria) |
| Backend de MILO | Python + FastAPI | Gratis |
| Tool Orchestrator | Código propio + function calling de Gemini | Gratis |
| Base de datos / memoria | SQLite (o Postgres free tier de Railway/Supabase) | Gratis |
| Hosting 24/7 | Oracle Cloud Free Tier (preferido) o Fly.io | Gratis |
| Control de versiones | GitHub | Gratis |
| Voz (futuro) | Whisper (STT) + Piper/Coqui (TTS), corridos en el servidor cloud, no en tu PC | Gratis |
| Visión (futuro) | Gemini multimodal (ya incluido en la API) | Gratis |

---

## 5. Roadmap por fases

### Fase 0 — Setup (1-2 días)
- [ ] Instalar Antigravity CLI en tu PC.
- [ ] Crear cuenta y API key en Google AI Studio.
- [ ] Crear repo en GitHub para MILO.
- [ ] Crear cuenta en Oracle Cloud Free Tier (o Fly.io como alternativa rápida).

### Fase 1 — MVP de texto (1 semana)
- [ ] Backend FastAPI mínimo que recibe texto y llama a Gemini.
- [ ] 2-3 herramientas reales conectadas (ej. clima, búsqueda web, lectura de archivo).
- [ ] Function calling funcionando end-to-end.
- [ ] Desplegado en el servidor gratuito (no en tu PC).

### Fase 2 — Dev Loop nocturno con Antigravity
- [ ] `AGENTS.md` con instrucciones de qué construir cada noche.
- [ ] Tool Permission en `always-proceed` dentro de sandbox.
- [ ] Tareas programadas nocturnas configuradas.
- [ ] Cola de tareas (`tasks_queue.json`) para sobrevivir a cortes de cuota.
- [ ] Rutina matutina: revisar diffs/commits generados durante la noche.

### Fase 3 — Self-healing en producción
- [ ] Retry layer en todas las llamadas a herramientas.
- [ ] Logging de errores en SQLite.
- [ ] Circuit breaker para herramientas inestables.
- [ ] Modo degradado cuando Gemini no responde.

### Fase 4 — Multimodalidad
- [ ] Integrar voz (Whisper + Piper) en el servidor.
- [ ] Integrar visión vía Gemini multimodal.
- [ ] Interfaz de chat/voz simple (web o app) conectada al backend.

### Fase 5 — Memoria y personalización
- [ ] Memoria persistente (preferencias, historial relevante).
- [ ] Embeddings para búsqueda semántica sobre conversaciones pasadas.

---

## 6. Riesgos a vigilar

- **Cuota gratuita de Gemini:** puede cambiar sus límites sin aviso; diseña el sistema para degradar con gracia, no para depender de que siempre haya cuota disponible.
- **`always-proceed` sin supervisión:** mayor riesgo de que el agente haga cambios no deseados durante la noche. Mitígalo con sandbox/contenedor aislado y revisión matutina de diffs antes de mergear a producción.
- **Servidores gratuitos:** algunos "duermen" tras inactividad (Render/Railway free); si MILO necesita estar siempre despierto, Oracle Free Tier es más confiable a largo plazo.
- **Tu PC:** evita correr cualquier proceso pesado y constante en ella; resérvala solo para la sesión de desarrollo con Antigravity durante el día.
