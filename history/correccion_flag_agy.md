# Corrección de Flags e Invocación de Antigravity CLI (agy)

## Qué se quería hacer
Corregir los errores al invocar la CLI de Antigravity (`agy`) desde el backend de MILO, solucionando el error `flags provided but not defined: -permission` y un modelo de inferencia desactualizado.

## Por qué se hizo
El backend de MILO en `src/services/agy_brain.py` estaba intentando llamar a `agy` usando el flag `--permission always-proceed`, el cual no es un flag válido de la CLI. Además, usaba el modelo `"Gemini 3.1 Flash"`, que no estaba disponible en la instalación actual de la CLI.

## Cómo se hizo
1. **Modificación de Flag**: Se reemplazó el flag `--permission always-proceed` por `--dangerously-skip-permissions` en `src/services/agy_brain.py`.
2. **Actualización de Modelo**: Se cambió el modelo `"Gemini 3.1 Flash"` por `"Gemini 3.5 Flash (Medium)"` para asegurar compatibilidad con los modelos disponibles.
3. **Validación**: Se ejecutó la suite completa de pruebas unitarias (`.venv/bin/python -m pytest`) y todas las 52 pruebas pasaron satisfactoriamente.

## Para qué sirve
Permite que MILO delegue e interactúe de forma correcta y fluida con Antigravity CLI sin fallas de parámetros o errores de modelo no encontrado, manteniendo su autonomía y resiliencia operacionales.
