# Historial de Cambios: Integración de Codex CLI y Vulcan Explícito (Fase 5)

Este documento registra las decisiones de diseño y cambios técnicos realizados para establecer a Codex CLI como motor principal y a Vulcan como invocación explícita.

## 1. Qué se quería hacer
* Configurar Codex CLI como el motor conversacional principal por defecto (punto de entrada único para preguntas/charlas generales).
* Convertir a Vulcan/agy en una herramienta de ejecución e investigación que solo se invoca bajo demanda explícita (triggers).
* Desacoplar por completo a OpenClaw del camino crítico de conversación directa para evitar interferencias.

## 2. Por qué se hizo
* Para optimizar la resiliencia conversacional: el flujo no debe realizar cascadas automáticas ocultas (silent fallbacks). Si Codex falla, se encola en SQLite y se reporta.
* Para ahorrar consumo de tokens en turnos interactivos estándar y reservar la potencia de codificación/ejecución para peticiones concretas.

## 3. Cómo se hizo
* **Enrutador (`ask` en `agy_brain.py`):** Se reescribió el punto de entrada para comprobar primero la presencia de triggers explícitos de Vulcan (evitando falsos negativos).
* **Extracción de Tareas (`strip_trigger_phrase`):** Limpia las llamadas explícitas para pasar solo la tarea limpia a Vulcan.
* **Integración de `run_codex`:** Ejecuta `/home/alejandro/.local/bin/codex exec` con control de parámetros (`gpt-5.4-mini` + reasoning effort `low` por defecto; escala a `gpt-5.4` en tareas complejas) usando `-o` para capturar la respuesta limpia.
* **Circuit Breakers Actualizados:** Se reconfiguraron los breakers de `codex` y `vulcan` por separado.
* **Pruebas de Aislamiento:** Se reescribió `tests/test_agy_brain.py` y se actualizó `tests/test_proactive.py` para compartir de forma segura `test_milo.db` limpiándolo en cada fixture.

## 4. Para qué sirve
* Permite chatear de forma fluida y rápida con Codex local (modelo OpenAI).
* Permite programar y realizar modificaciones al código llamando explícitamente a Vulcan (ej: *"vulcan, crea una prueba unitaria para el router"*).
* Asegura estabilidad a largo plazo e independencia de caídas de tokens de proveedores únicos.
