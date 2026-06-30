# MILO — Asistente Personal Autónomo (MVP de Texto)

Este es el Backend MVP de **MILO**, diseñado para funcionar 24/7 de forma eficiente y económica en servidores de la nube gratuita (ej. Oracle Cloud, Fly.io, etc.), protegiendo el hardware local y minimizando costos al consumir la API de Gemini (Google AI Studio).

---

## 🏗️ Arquitectura y Estructura

El backend está desarrollado con **FastAPI** (Python 3.10+) e integra la API de Gemini (SDK oficial `google-genai`) utilizando **Function Calling (Llamado a funciones)** en un ciclo manual para proveer herramientas del sistema (lectura de archivos, consulta de clima, etc.) al asistente.

```
Milo/
├── src/
│   ├── config.py           # Carga de variables de entorno (.env)
│   ├── main.py             # Servidor FastAPI y endpoints
│   ├── services/
│   │   └── gemini_service.py # Orquestación del LLM y bucle de tools
│   └── tools/              # Registro de herramientas
│       ├── weather.py      # Clima ficticio (Mock tool)
│       ├── file_reader.py  # Lector de archivos del espacio de trabajo
│       └── list_dir.py     # Lista archivos del proyecto recursivamente
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 🚀 Setup & Ejecución Local

### 1. Variables de Entorno
Copia el archivo `.env.example` como `.env` e ingresa tu API Key de Gemini obtenida de [Google AI Studio](https://aistudio.google.com/):

```bash
cp .env.example .env
```

Edita `.env` y rellena:
```env
GEMINI_API_KEY=tu_api_key_aqui
```

### 2. Dependencias y Entorno Virtual
Si ya se crearon las carpetas con Antigravity, puedes inicializar el entorno virtual e instalar las dependencias:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Ejecutar el Servidor FastAPI
Inicia el servidor de desarrollo (con recarga en vivo activa):

```bash
python -m src.main
# O usando uvicorn directamente:
uvicorn src.main:app --reload
```

El servidor estará disponible en [http://localhost:8000](http://localhost:8000).

---

## 📡 Endpoints del API

### 1. Health Check
Verifica que el servicio esté arriba:
*   **Método:** `GET`
*   **Ruta:** `/health`
*   **Respuesta:** `{"status": "ok", "app": "MILO API"}`

### 2. Interacción con MILO (Chat)
Envía un prompt a MILO para que razone y ejecute herramientas:
*   **Método:** `POST`
*   **Ruta:** `/chat`
*   **Cuerpo (JSON):**
    ```json
    {
      "prompt": "Clima en Madrid y lee el archivo MILO_plan.md por favor"
    }
    ```
*   **Respuesta (JSON):**
    ```json
    {
      "response": "El clima actual en Madrid es Partly Cloudy con 19°C... El archivo MILO_plan.md detalla el plan técnico...",
      "execution_log": [
        {
          "tool": "get_current_weather",
          "args": {"location": "Madrid"}
        },
        {
          "tool": "read_local_file",
          "args": {"filename": "MILO_plan.md"}
        }
      ]
    }
    ```

---

## 🛠️ Cómo agregar nuevas herramientas

Para añadir herramientas adicionales a MILO:

1.  Crea un nuevo archivo en `src/tools/` (ej. `src/tools/web_search.py`).
2.  Define una función de Python con **anotaciones de tipo explícitas** (type hints) y un **docstring detallado** (el docstring es el que Gemini utiliza para entender qué hace tu herramienta y qué parámetros necesita).
3.  Regístrala en `src/services/gemini_service.py`:
    *   Impórtala al inicio del archivo.
    *   Agrégala al diccionario `TOOL_REGISTRY`.

*¡Y listo! Gemini la detectará automáticamente en la siguiente llamada.*
# Milo
