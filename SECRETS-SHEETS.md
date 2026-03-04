# Configurar Google Sheets en Streamlit Cloud

Para que el dashboard pueda leer la planilla de SLA real, necesitás agregar estos secretos en Streamlit Cloud.

## Paso 1: Obtener los valores

Corré este comando en tu terminal:

```bash
cat ~/.openclaw/credentials/sheets-tokens.json
cat ~/.openclaw/credentials/gmail-oauth.json
```

## Paso 2: Agregar en Streamlit Cloud

1. Andá a https://share.streamlit.io/
2. Click en tu app "yom-tickets-dashboard"
3. Click en "⋮" (tres puntos) → "Settings"
4. Click en "Secrets" en el menú izquierdo
5. Pegá este formato (reemplazá los valores con los de arriba):

```toml
[freshdesk]
domain = "yom1822574979840706786.freshdesk.com"
apiKey = "UTphTYbUmmaaRZN3Xzl"

[google_sheets]
access_token = "VALOR_DE_sheets-tokens.json → access_token"
refresh_token = "VALOR_DE_sheets-tokens.json → refresh_token"
client_id = "VALOR_DE_gmail-oauth.json → installed.client_id"
client_secret = "VALOR_DE_gmail-oauth.json → installed.client_secret"
```

## Ejemplo completo:

```toml
[freshdesk]
domain = "yom1822574979840706786.freshdesk.com"
apiKey = "UTphTYbUmmaaRZN3Xzl"

[google_sheets]
access_token = "ya29.a0AY..."
refresh_token = "1//0g..."
client_id = "906879748560-572mqhd5tpjvf4r23vvrb7jsvfs20ctu.apps.googleusercontent.com"
client_secret = "GOCSPX-..."
```

6. Click en "Save"
7. El dashboard se va a redeployar automáticamente

## Verificar que funcione

Después del deploy, deberías ver en el sidebar:
- ✅ SLA real cargado: X tickets

Si ves un error, revisá que los secretos estén bien copiados.
