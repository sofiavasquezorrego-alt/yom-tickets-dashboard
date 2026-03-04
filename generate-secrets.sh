#!/bin/bash
# Generar archivo de secrets para Streamlit Cloud

echo "Generando secrets.toml para Streamlit Cloud..."
echo ""

cat << EOF
# Copiá todo esto en Streamlit Cloud → Settings → Secrets

[freshdesk]
domain = "yom1822574979840706786.freshdesk.com"
apiKey = "UTphTYbUmmaaRZN3Xzl"

[google_sheets]
access_token = "$(cat ~/.openclaw/credentials/sheets-tokens.json | jq -r '.access_token')"
refresh_token = "$(cat ~/.openclaw/credentials/sheets-tokens.json | jq -r '.refresh_token')"
client_id = "$(cat ~/.openclaw/credentials/gmail-oauth.json | jq -r '.installed.client_id')"
client_secret = "$(cat ~/.openclaw/credentials/gmail-oauth.json | jq -r '.installed.client_secret')"
EOF

echo ""
echo ""
echo "✅ Copiá todo el texto de arriba (desde [freshdesk] hasta client_secret)"
echo "   y pegalo en Streamlit Cloud → Settings → Secrets"
