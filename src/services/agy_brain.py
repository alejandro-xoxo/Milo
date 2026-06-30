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
    Toda inferencia pasa por Antigravity CLI (agy) por defecto.
    Si agy falla o está inactivo por cuotas (429), hace failover automático
    a OpenClaw local gateway.
    """

    def __init__(self, project_path: str):
        self.project_path = project_path

    def ask(self, prompt: str, mode: str = "chat", status_callback=None) -> str:
        """
        Envía un prompt a agy (Vulcan). Si falla por cuotas o circuit breaker,
        hace fallback a OpenClaw.
        """
        use_openclaw = False
        agy_error = ""

        # Reportar estado inicial a la UX
        if status_callback:
            status_callback("Invocando Vulcan (CLI)...")

        # 1. Verificar Circuit Breaker para 'vulcan' (reemplaza 'agy')
        try:
            check_circuit_breaker("vulcan")
        except ToolDisabledException as tde:
            logger.warning(f"AgyBrain: Vulcan bloqueado por Circuit Breaker: {tde}")
            use_openclaw = True
            agy_error = str(tde)

        # 2. Intentar agy directo si no está bloqueado
        if not use_openclaw:
            try:
                result = subprocess.run(
                    ["agy", "--model", "Gemini 3.5 Flash (Medium)", "--dangerously-skip-permissions", "--print", prompt],
                    capture_output=True, 
                    text=True, 
                    timeout=300,
                    cwd=self.project_path
                )

                if result.returncode != 0:
                    stderr_lower = result.stderr.lower()
                    is_quota = any(kw in stderr_lower for kw in ["quota", "limit", "429", "exhausted", "resource_exhausted"])
                    logger.error(f"Error en AgyBrain (returncode={result.returncode}): {result.stderr}")
                    
                    # Registrar fallo en el circuit breaker bajo el nombre 'vulcan'
                    record_tool_failure("vulcan")
                    log_incident("vulcan", result.stderr.strip(), {"prompt": prompt, "is_quota": is_quota})
                    
                    agy_error = result.stderr.strip()
                    use_openclaw = True
                else:
                    # Éxito: resetear fallos del circuit breaker
                    reset_tool_failures("vulcan")
                    self._log_active_engine("vulcan")
                    if status_callback:
                        status_callback("Resuelto mediante Vulcan (CLI).")
                    return self._parse_output(result.stdout)

            except Exception as e:
                logger.error(f"Excepción en AgyBrain al invocar agy (Vulcan): {e}")
                record_tool_failure("vulcan")
                log_incident("vulcan", str(e), {"prompt": prompt})
                agy_error = str(e)
                use_openclaw = True

        # 3. Fallback a OpenClaw
        if use_openclaw:
            if status_callback:
                status_callback("Vulcan sin cuota. Desviando a OpenClaw...")
            logger.info("Iniciando fallback a OpenClaw...")
            openclaw_res = self._ask_openclaw(prompt)
            if openclaw_res:
                self._log_active_engine("openclaw")
                if status_callback:
                    status_callback("Resuelto mediante OpenClaw.")
                return openclaw_res
            else:
                # Si OpenClaw también falló, devolver el error original de agy
                return f"[MILO] No pude completar la solicitud. Vulcan falló ({agy_error}) y OpenClaw no está disponible."

    def _ask_openclaw(self, prompt: str) -> str:
        url = os.getenv("OPENCLAW_URL", "http://127.0.0.1:18789")
        token = os.getenv("OPENCLAW_TOKEN", "")
        
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
            
        payload = {
            "model": os.getenv("OPENCLAW_MODEL", "openclaw/default"),
            "messages": [
                {"role": "user", "content": prompt}
            ]
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

