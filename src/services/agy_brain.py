import subprocess
import logging

logger = logging.getLogger(__name__)

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
        Envía un prompt a agy.
        """
        # Según las instrucciones: subprocess.run(["agy", "--print", prompt], capture_output=True, text=True)
        try:
            result = subprocess.run(
                ["agy", "--model", "Gemini 3.1 Pro (Low)", "--print", prompt],
                capture_output=True, 
                text=True, 
                timeout=300,
                cwd=self.project_path
            )

            if result.returncode != 0:
                logger.error(f"Error en AgyBrain: {result.stderr}")
                return f"[MILO] No pude completar esto con Antigravity CLI: {result.stderr.strip()}"

            return self._parse_output(result.stdout)
        except Exception as e:
            logger.error(f"Excepción en AgyBrain: {e}")
            return f"[MILO] Error interno invocando Antigravity: {e}"

    def _parse_output(self, raw: str) -> str:
        # --print ya debería imprimir directamente el resultado
        return raw.strip()
