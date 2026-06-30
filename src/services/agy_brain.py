import subprocess
import logging
import os
import requests
from src.services.db_service import record_tool_failure, reset_tool_failures, log_incident
from src.services.circuit_breaker import check_circuit_breaker, ToolDisabledException

logger = logging.getLogger(__name__)

class AgyBrain:
    """
    Único cerebro de MILO. No usa ninguna API key directamente.
    Toda inferencia pasa por OpenClaw local gateway como motor primario,
    con fallback automático a Antigravity CLI (agy / Vulcan).
    """

    def __init__(self, project_path: str):
        self.project_path = project_path

    def ask(self, prompt: str, mode: str = "chat", status_callback=None) -> str:
        """
        Envía un prompt a OpenClaw o Vulcan. Implementa triage, optimización
        de tokens mediante recorte de historial, persistencia y resiliencia.
        """
        from src.services.db_service import add_chat_message
        
        # 1. Registrar mensaje del usuario en la base de datos
        add_chat_message("default", "user", prompt)

        # Verificar Circuit Breaker para 'openclaw' al inicio para evitar triage si está deshabilitado
        openclaw_disabled = False
        openclaw_error = ""
        try:
            check_circuit_breaker("openclaw")
        except ToolDisabledException as tde:
            logger.warning(f"AgyBrain: OpenClaw bloqueado por Circuit Breaker: {tde}")
            openclaw_disabled = True
            openclaw_error = str(tde)

        if not openclaw_disabled:
            # 2. Clasificación de Intención (Triage)
            if status_callback:
                status_callback("Analizando intención de la consulta...")
            triage_result = self._run_triage(prompt)
            logger.info(f"Triage clasificado como: {triage_result}")
        else:
            triage_result = "COMPLEX"

        # 3. Obtener contexto optimizado (recortado y resumido)
        # Si la consulta es SIMPLE, usamos menos turnos activos para ahorrar tokens
        max_turns = 4 if triage_result == "SIMPLE" else 6
        messages = self.get_optimized_context("default", max_turns=max_turns)
        
        # Estimar y documentar consumo de tokens (caracteres / 4)
        total_chars = len(str(messages))
        est_tokens = total_chars // 4
        logger.info(f"Consumo de tokens de contexto estimado: ~{est_tokens} tokens ({total_chars} caracteres)")

        # Si el triage determinó que es SIMPLE, inyectamos una instrucción de restricción de herramientas
        # en el system message del contexto para ahorrar tokens de system/tools.
        if triage_result == "SIMPLE" and messages:
            # Encontrar o inyectar mensaje de sistema
            sys_instruct = (
                "Instrucción de optimización de tokens: Esta consulta ha sido clasificada como SIMPLE. "
                "Responde directamente sin invocar herramientas de programación, búsqueda de archivos ni ejecución de comandos."
            )
            if messages[0]["role"] == "system":
                messages[0]["content"] = f"{messages[0]['content']}\n\n{sys_instruct}"
            else:
                messages.insert(0, {"role": "system", "content": sys_instruct})

        use_vulcan = openclaw_disabled
        
        # Reportar estado inicial a la UX
        if status_callback and not use_vulcan:
            status_callback("Invocando OpenClaw (Default)...")

        # Determinar modelo según triage
        model = os.getenv("OPENCLAW_MODEL_SIMPLE", "openclaw/default")
        if triage_result == "COMPLEX":
            model = os.getenv("OPENCLAW_MODEL_COMPLEX", "openclaw/complex")

        # 5. Intentar OpenClaw
        response_text = ""
        if not use_vulcan:
            logger.info(f"Enviando petición a OpenClaw usando modelo: {model}...")
            openclaw_res = self._ask_openclaw(messages, model=model)
            if openclaw_res:
                reset_tool_failures("openclaw")
                self._log_active_engine("openclaw")
                if status_callback:
                    status_callback("Resuelto mediante OpenClaw.")
                response_text = openclaw_res
            else:
                logger.warning("Llamada a OpenClaw fallida, preparando fallback a Vulcan...")
                record_tool_failure("openclaw", threshold=2, cooldown_minutes=3)
                log_incident("openclaw", "Failed to get response from OpenClaw gateway", {"prompt": prompt})
                openclaw_error = "OpenClaw gateway connection failed or returned non-200"
                use_vulcan = True

        # 6. Fallback a agy (Vulcan)
        if use_vulcan:
            if status_callback:
                status_callback("OpenClaw no disponible. Desviando a Vulcan (CLI)...")
            logger.info("Iniciando fallback a Vulcan (agy)...")

            try:
                check_circuit_breaker("vulcan")
            except ToolDisabledException as tde:
                logger.error(f"AgyBrain: Ambos motores fallaron. Vulcan bloqueado por Circuit Breaker: {tde}")
                response_text = f"[MILO] No pude completar la solicitud. OpenClaw falló ({openclaw_error}) y Vulcan está bloqueado por Circuit Breaker."
            else:
                # Formatear el historial completo como un único string para la CLI de agy
                formatted_prompt = ""
                if len(messages) > 1:
                    for msg in messages[:-1]:
                        role_name = "Usuario" if msg["role"] == "user" else "MILO" if msg["role"] == "assistant" else "Sistema"
                        formatted_prompt += f"{role_name}: {msg['content']}\n"
                    formatted_prompt += f"Usuario: {prompt}\n\nResponde considerando el contexto anterior."
                else:
                    formatted_prompt = prompt

                try:
                    result = subprocess.run(
                        ["agy", "--model", "Gemini 3.5 Flash (Medium)", "--dangerously-skip-permissions", "--print", formatted_prompt],
                        capture_output=True, 
                        text=True, 
                        timeout=300,
                        cwd=self.project_path
                    )

                    if result.returncode != 0:
                        logger.error(f"Error en Vulcan (returncode={result.returncode}): {result.stderr}")
                        record_tool_failure("vulcan", threshold=3, cooldown_minutes=30)
                        log_incident("vulcan", result.stderr.strip(), {"prompt": prompt})
                        response_text = f"[MILO] No pude completar la solicitud. OpenClaw falló ({openclaw_error}) y Vulcan falló con error: {result.stderr.strip()}"
                    else:
                        reset_tool_failures("vulcan")
                        self._log_active_engine("vulcan")
                        if status_callback:
                            status_callback("Resuelto mediante Vulcan (CLI).")
                        response_text = self._parse_output(result.stdout)

                except Exception as e:
                    logger.error(f"Excepción en AgyBrain al invocar Vulcan: {e}")
                    record_tool_failure("vulcan", threshold=3, cooldown_minutes=30)
                    log_incident("vulcan", str(e), {"prompt": prompt})
                    response_text = f"[MILO] No pude completar la solicitud. OpenClaw falló ({openclaw_error}) y Vulcan falló con excepción: {e}"

        # 7. Registrar respuesta del asistente en la base de datos
        if response_text:
            add_chat_message("default", "assistant", response_text)

        return response_text

    def get_optimized_context(self, session_id: str = "default", max_turns: int = 6) -> list:
        """
        Retorna el contexto de conversación optimizado: los últimos N turnos activos
        más un resumen comprimido del historial anterior de mensajes.
        """
        from src.services.db_service import get_chat_history, get_last_summary, update_message_summary
        
        # 1. Obtener el historial completo
        history = get_chat_history(session_id, limit=50)
        if not history:
            return []
            
        # 2. Si excede el umbral, resumir los mensajes antiguos y cachear
        if len(history) > max_turns:
            active_messages = history[-max_turns:]
            older_messages = history[:-max_turns]
            
            # Buscar último resumen guardado
            last_sum_data = get_last_summary(session_id)
            last_sum_id = last_sum_data["id"]
            last_sum_text = last_sum_data["summary"]
            
            # Mensajes antiguos no resumidos todavía
            unsummarized_older = [m for m in older_messages if m["id"] > last_sum_id]
            
            if unsummarized_older:
                text_to_sum = ""
                if last_sum_text:
                    text_to_sum += f"Resumen previo de la conversación: {last_sum_text}\n\nNuevos turnos a incorporar:\n"
                for m in unsummarized_older:
                    role_name = "Usuario" if m["role"] == "user" else "MILO"
                    text_to_sum += f"{role_name}: {m['content']}\n"
                
                # Ejecutar llamada sin historial para evitar recursión
                new_summary = self._summarize_text(text_to_sum)
                if new_summary:
                    latest_msg_id = unsummarized_older[-1]["id"]
                    update_message_summary(latest_msg_id, new_summary)
                    last_sum_text = new_summary
            
            # Construir payload de mensajes con el resumen previo
            messages = []
            if last_sum_text:
                messages.append({
                    "role": "system",
                    "content": f"Resumen de la conversación anterior: {last_sum_text}"
                })
            for m in active_messages:
                messages.append({
                    "role": "user" if m["role"] == "user" else "assistant",
                    "content": m["content"]
                })
            return messages
        else:
            messages = []
            for m in history:
                messages.append({
                    "role": "user" if m["role"] == "user" else "assistant",
                    "content": m["content"]
                })
            return messages

    def _summarize_text(self, text: str) -> str:
        """Genera un resumen ultra-conciso del texto sin usar historial."""
        prompt = (
            "Resume los puntos clave de esta conversación de forma "
            "extremadamente concisa (máximo 2 oraciones, un solo párrafo) en español, "
            f"sin saludos ni introducciones:\n\n{text}"
        )
        res = self._ask_openclaw(prompt, model=os.getenv("OPENCLAW_MODEL_SIMPLE", "openclaw/default"))
        if res:
            return res.strip()
            
        # Fallback directo a agy (Vulcan)
        try:
            result = subprocess.run(
                ["agy", "--model", "Gemini 3.5 Flash (Medium)", "--dangerously-skip-permissions", "--print", prompt],
                capture_output=True, 
                text=True, 
                timeout=120,
                cwd=self.project_path
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except:
            pass
        return ""

    def _run_triage(self, prompt: str) -> str:
        """Clasifica la consulta como SIMPLE o COMPLEX usando un prompt rápido."""
        triage_prompt = (
            "Clasifica la intención del usuario en una de estas dos categorías:\n"
            "SIMPLE: Saludos, charla informal, preguntas sencillas de conocimiento general, clima, o consultas que no requieran inspeccionar archivos ni ejecutar comandos.\n"
            "COMPLEX: Tareas de programación, investigación del código, edición o lectura de archivos del espacio de trabajo, o ejecución de comandos bash del sistema.\n\n"
            "Responde estrictamente con una sola palabra en mayúsculas: SIMPLE o COMPLEX.\n\n"
            f"Consulta: \"{prompt}\""
        )
        res = self._ask_openclaw(triage_prompt, model=os.getenv("OPENCLAW_MODEL_SIMPLE", "openclaw/default"))
        if res:
            res_clean = res.strip().upper()
            if "SIMPLE" in res_clean:
                return "SIMPLE"
            if "COMPLEX" in res_clean:
                return "COMPLEX"
                
        try:
            result = subprocess.run(
                ["agy", "--model", "Gemini 3.5 Flash (Medium)", "--dangerously-skip-permissions", "--print", triage_prompt],
                capture_output=True, 
                text=True, 
                timeout=10,
                cwd=self.project_path
            )
            if result.returncode == 0:
                res_clean = result.stdout.strip().upper()
                if "SIMPLE" in res_clean:
                    return "SIMPLE"
        except:
            pass
        return "COMPLEX"

    def _ask_openclaw(self, messages_or_prompt, model: str = None) -> str:
        url = os.getenv("OPENCLAW_URL", "http://127.0.0.1:18789")
        token = os.getenv("OPENCLAW_TOKEN", "")
        
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
            
        if isinstance(messages_or_prompt, str):
            payload_messages = [{"role": "user", "content": messages_or_prompt}]
        else:
            payload_messages = messages_or_prompt
            
        payload = {
            "model": model or os.getenv("OPENCLAW_MODEL", "openclaw/default"),
            "messages": payload_messages
        }
        
        try:
            logger.info(f"Conectando a OpenClaw en {url}/v1/chat/completions...")
            response = requests.post(f"{url}/v1/chat/completions", json=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                logger.info("Respuesta obtenida con éxito desde OpenClaw.")
                return content.strip()
            else:
                logger.error(f"OpenClaw devolvió status {response.status_code}: {response.text}")
                return ""
        except Exception as e:
            logger.error(f"Error de conexión con OpenClaw: {e}")
            return ""

    def _log_active_engine(self, engine_name: str):
        import sqlite3
        from src.services.db_service import get_db_path
        try:
            conn = sqlite3.connect(get_db_path())
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO tool_status (tool_name, failure_count, disabled_until)
            VALUES ('active_engine', 0, ?)
            ON CONFLICT(tool_name) DO UPDATE SET
                disabled_until = excluded.disabled_until
            """, (engine_name,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error logging active engine: {e}")

    def _parse_output(self, raw: str) -> str:
        return raw.strip()

