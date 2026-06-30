# Histórico de Desarrollo: Fases 2 y 3 (Resiliencia y Autonomía)

Este documento detalla las decisiones técnicas tomadas para completar las Fases 2 y 3 del plan de MILO.

---

### 1. ¿Qué queríamos hacer?
*   Establecer una infraestructura que permita a MILO seguir operando de forma autónoma y tolerar fallos cuando no hay supervisión humana.
*   Implementar una cola de tareas en segundo plano para encolar prompts si no hay cuota de API disponible.
*   Crear un cortafuegos de herramientas (Circuit Breaker) para evitar llamadas inútiles a APIs que están caídas o herramientas locales rotas.
*   Configurar un "modo degradado" elegante si tanto Gemini como Claude se quedan sin tokens.

### 2. ¿Por qué lo hicimos?
*   **Tolerancia a fallos:** El sistema no debe crashearse si una API de terceros (Gemini) falla o se agota su límite de uso gratuito diario.
*   **Evitar bucles de error infinitos:** Si una herramienta falla repetidamente, reintentar indefinidamente consume recursos de CPU y tokens de forma inútil. El Circuit Breaker aísla la herramienta dañada por un tiempo.
*   **Asincronía:** Ciertas tareas pesadas de MILO pueden requerir ejecución diferida; una cola de tareas permite procesarlas sin bloquear la respuesta inmediata al usuario.
*   **Robustez de desarrollo nocturno:** Asegurar que si dejamos al agente programando, la infraestructura soporte cortes de API.

### 3. ¿Cómo lo hicimos?
*   **Base de Datos SQLite (`milo.db`):** 
    *   Diseñamos una base de datos ligera para evitar dependencias externas pesadas.
    *   Creamos tablas para:
        *   `task_queue`: Cola de tareas asíncronas con reintentos.
        *   `incidents`: Registro histórico detallado de fallos de herramientas.
        *   `tool_status`: Monitoreo del contador de fallos para Circuit Breaker.
*   **Modo de Fallback a Claude 3.5 Sonnet:**
    *   Si Gemini retorna un error de tipo `429` (Quota Exhausted), el servicio intercepta el error y conmuta al SDK de Anthropic usando la clave de Claude.
*   **Capa de Reintentos Exponenciales y Circuit Breaker (`circuit_breaker.py`):**
    *   Utilizamos la librería `tenacity` para reintentar la llamada a la herramienta 3 veces con una espera exponencial en caso de fallos temporales.
    *   Si los retries fallan, se suma una falla en SQLite. Al alcanzar las 5 fallas consecutivas, la herramienta se deshabilita temporalmente por 15 minutos.
*   **Cola de tareas integrada en FastAPI:**
    *   Creamos un bucle asíncrono (`queue_runner.py`) que corre en segundo plano en FastAPI (usando `lifespan` startup/shutdown hooks).
    *   Creamos endpoints `POST /tasks` y `GET /tasks/{id}` para encolar y consultar.
*   **Modo Degradado en `/chat`:**
    *   Si tanto Gemini como Claude se quedan sin tokens de API, el endpoint `/chat` intercepta el error, crea una tarea con tu prompt en la base de datos de SQLite, y retorna un mensaje en español explicando que tu tarea quedó encolada bajo el ID asignado.

### 4. ¿Para qué sirve?
*   Permite a MILO sobrevivir de forma autónoma en producción sin costos de mantenimiento en hardware o servidores costosos.
*   Da visibilidad completa de los errores que ocurren en segundo plano a través de la tabla de incidentes de SQLite.
*   Protege tus límites de tarifas de APIs externas al manejar inteligentemente los reintentos y la desconexión temporal de servicios inestables.
