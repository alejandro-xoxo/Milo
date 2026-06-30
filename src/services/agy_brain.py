import subprocess
import logging
import os
import requests
from src.services.db_service import record_tool_failure, reset_tool_failures, log_incident
from src.services.circuit_breaker import check_circuit_breaker, ToolDisabledException

logger = logging.getLogger(__name__)

class AgyBrain:
    """
    Cerebro de MILO V3 (Codex CLI + Vulcan Explícito).
    Codex es el motor principal y Vulcan es invocado de forma explícita.
    """

    def __init__(self, project_path: str):
        self.project_path = project_path

    def ask(self, prompt: str, mode: str = "chat", status_callback=None) -> str:
        """
        Punto de entrada de cada mensaje. Enruta a OpenClaw, Codex o Vulcan.
        """
        from src.services.db_service import add_chat_message, enqueue_task
        
        # 1. Registrar mensaje del usuario en la base de datos
        add_chat_message("default", "user", prompt)

        # 2. Enrutamiento (Router de Mensajes)
        if self.detect_vulcan_trigger(prompt):
            if status_callback:
                status_callback("Ejecutando herramienta Vulcan (Invocación Explícita)...")
            
            # Verificar Circuit Breaker para Vulcan
            try:
                check_circuit_breaker("vulcan")
            except ToolDisabledException as tde:
                err_msg = f"[MILO] Vulcan está deshabilitado temporalmente por fallos consecutivos: {tde}"
                if status_callback:
                    status_callback(err_msg)
                return err_msg
                
            trigger_phrase = self.get_trigger_phrase(prompt)
            tarea = self.strip_trigger_phrase(prompt)
            logger.info(f"Trigger detectado: '{trigger_phrase}'. Tarea extraída: '{tarea}'")
            
            # Ejecutar Vulcan explícito
            vulcan_res = self.run_antigravity(tarea, mode="proceed-in-sandbox")
            
            # Verificar si hubo error en run_antigravity
            if "Error al ejecutar la tarea en Vulcan" in vulcan_res or "Excepción en Vulcan" in vulcan_res:
                record_tool_failure("vulcan", threshold=3, cooldown_minutes=15)
                log_incident("vulcan", vulcan_res, {"prompt": prompt, "task": tarea})
                if status_callback:
                    status_callback(f"Proceso finalizado con error: {vulcan_res}")
                return vulcan_res
            else:
                reset_tool_failures("vulcan")
                # Inyectar el resultado de vuelta al contexto de Codex en SQLite
                add_chat_message("default", "assistant", f"[Resultado de Vulcan para la tarea]: {vulcan_res}")
                if status_callback:
                    status_callback("Proceso finalizado. Tarea completada con éxito.")
                return f"Completé la tarea mediante Vulcan: {vulcan_res}"
        
        # Camino Principal: Intentar OpenClaw
        openclaw_disabled = False
        openclaw_error = ""
        try:
            check_circuit_breaker("openclaw")
        except ToolDisabledException as tde:
            logger.warning(f"AgyBrain: OpenClaw bloqueado por Circuit Breaker: {tde}")
            openclaw_disabled = True
            openclaw_error = str(tde)

        triage_result = None
        if not openclaw_disabled:
            if status_callback:
                status_callback("Invocando OpenClaw...")

            # Clasificación de Intención (Triage)
            triage_result = self._run_triage(prompt)
            logger.info(f"Triage clasificado como: {triage_result}")

            # Determinar modelo según triage
            model = os.getenv("OPENCLAW_MODEL_SIMPLE", "openclaw")
            if triage_result == "COMPLEX":
                model = os.getenv("OPENCLAW_MODEL_COMPLEX", "openclaw")

            # Obtener contexto optimizado
            max_turns = 4 if triage_result == "SIMPLE" else 6
            messages = self.get_optimized_context("default", max_turns=max_turns)

            # Inyectar instrucción simple si aplica
            if triage_result == "SIMPLE" and messages:
                sys_instruct = (
                    "Instrucción de optimización de tokens: Esta consulta ha sido clasificada como SIMPLE. "
                    "Responde directamente sin invocar herramientas de programación, búsqueda de archivos ni ejecución de comandos."
                )
                if messages[0]["role"] == "system":
                    messages[0]["content"] = f"{messages[0]['content']}\n\n{sys_instruct}"
                else:
                    messages.insert(0, {"role": "system", "content": sys_instruct})

            # Llamar a OpenClaw API
            openclaw_res = self._ask_openclaw(messages, model=model)
            if openclaw_res:
                reset_tool_failures("openclaw")
                self._log_active_engine("OpenClaw")
                if status_callback:
                    status_callback("Resuelto mediante OpenClaw.")
                add_chat_message("default", "assistant", openclaw_res)
                return openclaw_res
            else:
                logger.warning("Llamada a OpenClaw fallida, preparando fallback a Codex...")
                record_tool_failure("openclaw", threshold=2, cooldown_minutes=3)
                log_incident("openclaw", "Failed to get response from OpenClaw gateway", {"prompt": prompt})
                openclaw_error = "OpenClaw gateway connection failed or returned non-200"

        # Fallback a Codex CLI (si OpenClaw falla o está deshabilitado)
        if status_callback:
            status_callback("OpenClaw no disponible. Desviando a Codex...")
            
        try:
            check_circuit_breaker("codex")
        except ToolDisabledException as tde:
            logger.warning(f"AgyBrain: Codex bloqueado por Circuit Breaker: {tde}")
            enqueue_task("codex_chat_fallback", {"prompt": prompt})
            err_msg = f"[MILO] Ambos motores fallaron. OpenClaw falló ({openclaw_error}) y Codex está bloqueado por Circuit Breaker: {tde}"
            if status_callback:
                status_callback(err_msg)
            return err_msg

        if triage_result is None:
            triage_result = self._run_triage(prompt)
        response_text = self.run_codex(prompt, triage_result=triage_result)
        
        if response_text:
            reset_tool_failures("codex")
            self._log_active_engine("Codex")
            if status_callback:
                status_callback("Resuelto mediante Codex.")
            add_chat_message("default", "assistant", response_text)
            return response_text
        else:
            record_tool_failure("codex", threshold=3, cooldown_minutes=5)
            log_incident("codex", "Codex CLI failed to respond or returned empty", {"prompt": prompt})
            enqueue_task("codex_chat_fallback", {"prompt": prompt})
            err_msg = "[MILO] El motor conversacional principal (OpenClaw) y el de respaldo (Codex) no están disponibles. La tarea ha sido encolada para su procesamiento posterior."
            if status_callback:
                status_callback(err_msg)
            return err_msg

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
            "model": model or os.getenv("OPENCLAW_MODEL", "openclaw"),
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

    def detect_vulcan_trigger(self, prompt: str) -> bool:
        """
        Detecta triggers explícitos de Vulcan en el prompt, evitando falsos positivos.
        """
        prompt_lower = prompt.lower()
        if "vulcan" not in prompt_lower:
            return False
        
        # Negaciones comunes complejas
        negations = [
            "no uses vulcan", "no uses a vulcan",
            "no usar vulcan", "no usar a vulcan",
            "sin vulcan", "sin a vulcan",
            "no quiero usar vulcan", "no quiero usar a vulcan",
            "no quiero vulcan", "no quiero a vulcan",
            "evita vulcan", "evita a vulcan",
            "no activa vulcan", "no activa a vulcan",
            "no activar vulcan", "no activar a vulcan",
            "no llames a vulcan", "no llama a vulcan",
            "no llames vulcan", "no llama vulcan",
            "no uses el vulcan", "no usar el vulcan"
        ]
        for neg in negations:
            if neg in prompt_lower:
                return False
        return True


    def get_trigger_phrase(self, prompt: str) -> str:
        """Retorna la frase de trigger detectada en el prompt."""
        prompt_lower = prompt.lower()
        triggers = ["llama a vulcan", "activa vulcan", "usa vulcan", "vulcan"]
        for trigger in triggers:
            if trigger in prompt_lower:
                return trigger
        return "vulcan"

    def strip_trigger_phrase(self, prompt: str) -> str:
        """
        Remueve la frase de trigger de activación del prompt crudo.
        """
        prompt_lower = prompt.lower()
        triggers = ["llama a vulcan", "activa vulcan", "usa vulcan", "vulcan"]
        cleaned = prompt
        for trigger in triggers:
            idx = cleaned.lower().find(trigger)
            if idx != -1:
                cleaned = cleaned[:idx] + cleaned[idx + len(trigger):]
        # Limpiar puntuaciones comunes del prompt restante
        cleaned = cleaned.strip(" :,.!?\n\t")
        return cleaned

    def run_codex(self, prompt: str, triage_result: str = "SIMPLE", include_context: bool = True) -> str:
        """
        Ejecuta Codex CLI en modo no interactivo.
        """
        # Determinar modelo según triage
        model = "gpt-5.4-mini"
        args = ["/home/alejandro/.local/bin/codex", "exec", "--dangerously-bypass-approvals-and-sandbox", "--ephemeral"]
        
        if triage_result == "SIMPLE":
            args.extend(["--model", "gpt-5.4-mini", "-c", "model_reasoning_effort=\"low\""])
        else:
            args.extend(["--model", "gpt-5.4-mini"])

        # Obtener contexto optimizado (recortado y resumido)
        if include_context:
            max_turns = 4 if triage_result == "SIMPLE" else 6
            messages = self.get_optimized_context("default", max_turns=max_turns)
            
            # Formatear el contexto para Codex
            formatted_prompt = ""
            if len(messages) > 1:
                for msg in messages[:-1]:
                    role_name = "Usuario" if msg["role"] == "user" else "MILO" if msg["role"] == "assistant" else "Sistema"
                    formatted_prompt += f"{role_name}: {msg['content']}\n"
                formatted_prompt += f"Usuario: {prompt}"
            else:
                formatted_prompt = prompt
        else:
            formatted_prompt = prompt
            
        # Usar un archivo de salida temporal para capturar la respuesta limpia
        import tempfile
        out_file = tempfile.mktemp(suffix=".txt")
        args.extend(["-o", out_file, formatted_prompt])
        
        try:
            logger.info(f"Ejecutando Codex: {args}")
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=self.project_path
            )
            if result.returncode != 0:
                logger.error(f"Error en Codex CLI (returncode={result.returncode}): {result.stderr}")
                return ""
            
            # Leer el archivo de salida
            if os.path.exists(out_file):
                with open(out_file, "r") as f:
                    response_text = f.read().strip()
                try:
                    os.remove(out_file)
                except:
                    pass
                return response_text
            else:
                logger.error("El archivo de salida de Codex no se creó.")
                return ""
        except Exception as e:
            logger.error(f"Excepción al ejecutar Codex CLI: {e}")
            return ""

    def run_antigravity(self, task: str, mode: str = "proceed-in-sandbox") -> str:
        """
        Ejecuta una tarea de forma autónoma usando Vulcan (agy).
        """
        cmd = ["agy", "--model", "Gemini 3.5 Flash (Medium)", "--dangerously-skip-permissions"]
        if "sandbox" in mode:
            cmd.append("--sandbox")
        cmd.extend(["--print", task])
        
        try:
            logger.info(f"Ejecutando run_antigravity: {cmd}")
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300,
                cwd=self.project_path
            )
            if result.returncode != 0:
                logger.error(f"Error en run_antigravity: {result.stderr}")
                return f"Error al ejecutar la tarea en Vulcan: {result.stderr.strip()}"
            return result.stdout.strip()
        except Exception as e:
            logger.error(f"Excepción en run_antigravity: {e}")
            return f"Excepción en Vulcan: {str(e)}"

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
        try:
            check_circuit_breaker("openclaw")
            res = self._ask_openclaw(prompt, model="openclaw")
            if res:
                return res.strip()
        except Exception as e:
            logger.warning(f"Error al resumir con OpenClaw: {e}")
            
        res = self.run_codex(prompt, triage_result="SIMPLE", include_context=False)
        if res:
            return res.strip()
        return ""

    def _run_triage(self, prompt: str) -> str:
        """Clasifica la intención en SIMPLE o COMPLEX."""
        triage_prompt = (
            "Clasifica la intención del usuario en una de estas dos categorías:\n"
            "SIMPLE: Saludos, charla informal, preguntas sencillas de conocimiento general, clima, o consultas que no requieran inspeccionar archivos ni ejecutar comandos.\n"
            "COMPLEX: Tareas de programación, investigación del código, edición o lectura de archivos del espacio de trabajo, o ejecución de comandos bash del sistema.\n\n"
            "Responde estrictamente con una sola palabra en mayúsculas: SIMPLE o COMPLEX.\n\n"
            f"Consulta: \"{prompt}\""
        )
        try:
            check_circuit_breaker("openclaw")
            res = self._ask_openclaw(triage_prompt, model="openclaw")
            if res:
                res_clean = res.strip().upper()
                if "SIMPLE" in res_clean:
                    return "SIMPLE"
                if "COMPLEX" in res_clean:
                    return "COMPLEX"
        except Exception as e:
            logger.warning(f"Error en triage con OpenClaw: {e}")
            
        res = self.run_codex(triage_prompt, triage_result="SIMPLE", include_context=False)
        if res:
            res_clean = res.strip().upper()
            if "SIMPLE" in res_clean:
                return "SIMPLE"
            if "COMPLEX" in res_clean:
                return "COMPLEX"
        return "COMPLEX"

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
