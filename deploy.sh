#!/bin/bash

echo "🚀 Preparando deploy a Streamlit Cloud..."
echo ""

# Verificar si git está inicializado
if [ ! -d ".git" ]; then
    echo "Inicializando repositorio Git..."
    git init
    git add .
    git commit -m "Initial commit: Dashboard de Tickets"
    echo ""
    echo "✅ Repositorio Git creado"
    echo ""
    echo "Ahora necesitas:"
    echo "1. Crear un repositorio en GitHub (https://github.com/new)"
    echo "2. Ejecutar estos comandos:"
    echo ""
    echo "   git remote add origin https://github.com/TU_USUARIO/TU_REPO.git"
    echo "   git branch -M main"
    echo "   git push -u origin main"
    echo ""
else
    echo "✅ Repositorio Git ya existe"
    echo ""
    echo "Asegúrate de hacer push a GitHub:"
    echo "   git add ."
    echo "   git commit -m 'Update dashboard'"
    echo "   git push"
fi

echo ""
echo "Después ve a: https://share.streamlit.io/"
echo "Y conecta tu repositorio de GitHub"
