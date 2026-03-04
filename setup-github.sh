#!/bin/bash

echo "🚀 Setup de GitHub y Deploy a Streamlit Cloud"
echo "=============================================="
echo ""

# Pedir usuario de GitHub
read -p "Tu usuario de GitHub: " GITHUB_USER

# Nombre del repo
REPO_NAME="yom-tickets-dashboard"

echo ""
echo "Voy a crear el repositorio: $GITHUB_USER/$REPO_NAME"
echo ""

# Crear repo usando la API de GitHub (requiere token)
echo "Para crear el repo necesito un token de acceso personal."
echo "Puedes crearlo en: https://github.com/settings/tokens/new"
echo "Permisos necesarios: 'repo' (Full control of private repositories)"
echo ""
read -sp "Token de GitHub: " GITHUB_TOKEN
echo ""
echo ""

# Crear repositorio privado
echo "Creando repositorio en GitHub..."
curl -s -X POST -H "Authorization: token $GITHUB_TOKEN" \
  -H "Accept: application/vnd.github.v3+json" \
  https://api.github.com/user/repos \
  -d "{\"name\":\"$REPO_NAME\",\"private\":true,\"description\":\"Dashboard de Tickets - Yom Customer Support\"}" > /tmp/gh-response.json

if grep -q "\"id\"" /tmp/gh-response.json; then
    echo "✅ Repositorio creado exitosamente!"
else
    echo "❌ Error creando repositorio:"
    cat /tmp/gh-response.json | grep "message"
    exit 1
fi

echo ""
echo "Configurando remote..."
git remote add origin "https://$GITHUB_USER:$GITHUB_TOKEN@github.com/$GITHUB_USER/$REPO_NAME.git"
git branch -M main

echo ""
echo "Haciendo push a GitHub..."
git push -u origin main

if [ $? -eq 0 ]; then
    echo ""
    echo "✅ ¡Código subido exitosamente!"
    echo ""
    echo "=============================================="
    echo "Ahora ve a Streamlit Cloud:"
    echo "=============================================="
    echo ""
    echo "1. Abre: https://share.streamlit.io/"
    echo "2. Click 'New app'"
    echo "3. Selecciona:"
    echo "   - Repository: $GITHUB_USER/$REPO_NAME"
    echo "   - Branch: main"
    echo "   - Main file path: app.py"
    echo ""
    echo "4. Click 'Advanced settings'"
    echo "5. En 'Secrets', pega esto:"
    echo ""
    echo "[freshdesk]"
    echo "domain = \"yom1822574979840706786.freshdesk.com\""
    echo "apiKey = \"UTphTYbUmmaaRZN3Xzl\""
    echo ""
    echo "6. Click 'Deploy!'"
    echo ""
    echo "¡Listo! Tu dashboard estará en:"
    echo "https://$REPO_NAME.streamlit.app"
else
    echo "❌ Error haciendo push"
    exit 1
fi
