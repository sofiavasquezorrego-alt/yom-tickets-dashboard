#!/bin/bash

echo "📊 Iniciando Dashboard de Tickets..."
echo ""

# Verificar si hay un venv
if [ ! -d "venv" ]; then
    echo "Creando entorno virtual..."
    python3 -m venv venv
fi

# Activar venv
source venv/bin/activate

# Instalar dependencias
echo "Instalando dependencias..."
pip install -q -r requirements.txt

# Lanzar Streamlit
echo ""
echo "✅ Abriendo dashboard en el navegador..."
echo "📍 URL: http://localhost:8501"
echo ""
echo "Presiona Ctrl+C para detener el servidor"
echo ""

streamlit run app.py
