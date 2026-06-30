# Instrucciones para Agentes de Desarrollo Nocturno (AGENTS.md)

Este archivo define las directrices y normas de desarrollo que **deben seguir de forma obligatoria** todos los agentes autónomos de Antigravity que trabajen en MILO durante los ciclos nocturnos (`/goal` o tareas programadas).

---

## 🚦 Reglas de Desarrollo Críticas

### 1. Control de Ramas y GitFlow
*   **PROHIBIDO** realizar commits directamente sobre la rama `main`.
*   Toda implementación, depuración o refactorización debe realizarse sobre la rama **`develop`**.
*   Si vas a trabajar en una característica grande, crea una rama de característica partiendo de `develop` (ej. `feature/nombre-de-caracteristica`) y haz un *merge* a `develop` al finalizar, verificando que no rompa nada.

### 2. Mensajes de Commit en Español
*   Todos los commits deben redactarse en **español** para facilitar el entendimiento del desarrollador humano.
*   Usa la convención de commits convencionales:
    *   `feat: ...` para nuevas funcionalidades.
    *   `fix: ...` para parches y correcciones de errores.
    *   `test: ...` para pruebas unitarias.
    *   `docs: ...` para documentación.
    *   `chore: ...` para cambios de configuración o mantenimiento.

### 3. Pruebas Unitarias Obligatorias
*   Antes de hacer cualquier commit o dar una tarea por finalizada, **debes ejecutar la suite de pruebas unitarias**:
    ```bash
    .venv/bin/python -m pytest
    ```
*   Si una prueba falla, tu prioridad absoluta es arreglarla antes de proceder con cualquier otra tarea (*Self-healing*).
*   Si agregas una nueva funcionalidad o servicio, **debes escribir su correspondiente test unitario** en la carpeta `tests/`.

### 4. Registro Histórico de Decisiones
*   Al finalizar cada fase o tarea importante, debes crear o actualizar un archivo en la carpeta `history/` (por ejemplo, `history/fase_X.md`).
*   En este archivo debes documentar de forma breve:
    *   **Qué** querías hacer.
    *   **Por qué** lo hiciste.
    *   **Cómo** lo hiciste.
    *   **Para qué** sirve.

### 5. Configuración de Seguridad en el Sandbox
*   Para trabajar de noche sin supervisión humana directa, asegúrate de que el ajuste `toolPermission` en tu entorno esté configurado en `always-proceed` **únicamente dentro de un contenedor o sandbox seguro**, nunca en el sistema operativo nativo del host.
*   En caso de error catastrófico o de datos comprometidos, aborta la ejecución y deja un reporte detallado del incidente en `history/incident_report.md`.
