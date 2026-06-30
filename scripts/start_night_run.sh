#!/bin/bash
# scripts/start_night_run.sh
# Script para preparar el entorno de desarrollo nocturno y verificar el estado del proyecto.

PROJECT_DIR="/home/alejandro/Proyectos/Milo"
LOG_FILE="$PROJECT_DIR/history/nightly_run.log"

# Crear directorio de logs si no existe
mkdir -p "$PROJECT_DIR/history"

echo "====================================================" >> "$LOG_FILE"
echo "=== INICIANDO EJECUCIÓN NOCTURNA: $(date) ===" >> "$LOG_FILE"
echo "====================================================" >> "$LOG_FILE"

# Ir al directorio del proyecto
cd "$PROJECT_DIR" || exit

# 1. Asegurar rama develop
CURRENT_BRANCH=$(git branch --show-current)
echo "[INFO] Rama actual: $CURRENT_BRANCH" >> "$LOG_FILE"
if [ "$CURRENT_BRANCH" != "develop" ]; then
    echo "[INFO] Cambiando a rama develop..." >> "$LOG_FILE"
    git checkout develop >> "$LOG_FILE" 2>&1
fi

# 2. Descargar últimos cambios de GitHub
echo "[INFO] Descargando últimos cambios de origen..." >> "$LOG_FILE"
git pull origin develop >> "$LOG_FILE" 2>&1

# 3. Validar entorno virtual
if [ ! -d ".venv" ]; then
    echo "[ERROR] El entorno virtual .venv no existe. Abortando." >> "$LOG_FILE"
    exit 1
fi

# 4. Ejecutar suite de pruebas unitarias
echo "[INFO] Ejecutando suite de pruebas pytest..." >> "$LOG_FILE"
.venv/bin/python -m pytest >> "$LOG_FILE" 2>&1

if [ $? -eq 0 ]; then
    echo "[OK] Pruebas pasadas. El entorno está listo y estable para el agente de IA." >> "$LOG_FILE"
else
    echo "[ADVERTENCIA] Algunas pruebas fallaron. Revisar history/nightly_run.log antes de programar." >> "$LOG_FILE"
fi

echo "=== FIN DE PREPARACIÓN NOCTURNA: $(date) ===" >> "$LOG_FILE"
echo "" >> "$LOG_FILE"
