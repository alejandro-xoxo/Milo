# Ajuste de instalación desde cero

- **Qué**: Ajusté la configuración de `pytest` para que la instalación limpia no intente recolectar scripts manuales bajo `scratch/`.
- **Por qué**: `scratch/test_audio_processing.py` depende de red externa (`gtts` contra Google) y rompe la validación básica en un entorno recién instalado.
- **Cómo**: Añadí `pytest.ini` con `norecursedirs = scratch .venv .git .mypy_cache .pytest_cache`.
- **Para qué**: Separar pruebas automatizadas de experimentos manuales y permitir que `pytest` funcione correctamente en una instalación desde cero.
