# 🚀 Instrucciones de Deploy - Dashboard de Tickets

## ✅ Lo que ya está listo

- ✅ Código preparado
- ✅ Git inicializado
- ✅ Commit hecho
- ✅ Script de deploy automático

## 🔑 Paso 1: Crear Token de GitHub (30 segundos)

1. Ve a https://github.com/settings/tokens/new
2. Dale un nombre: "Streamlit Deploy"
3. En permisos, marca solo: **`repo`** (Full control of private repositories)
4. Click "Generate token"
5. **Copia el token** (solo lo verás una vez)

## 🚀 Paso 2: Ejecutar Script de Deploy

```bash
cd /Users/svo/.openclaw/workspace/dashboard-streamlit
./setup-github.sh
```

Te pedirá:
- Tu usuario de GitHub
- El token que acabas de crear

¡Y listo! El script hace todo automáticamente:
- Crea el repositorio privado
- Sube el código
- Te da las instrucciones finales

## ☁️ Paso 3: Deploy en Streamlit Cloud (2 minutos)

1. Ve a https://share.streamlit.io/
2. Click "New app"
3. Selecciona:
   - **Repository:** `tu-usuario/yom-tickets-dashboard`
   - **Branch:** `main`
   - **Main file path:** `app.py`

4. Click "Advanced settings"
5. En **Secrets**, pega:

```toml
[freshdesk]
domain = "yom1822574979840706786.freshdesk.com"
apiKey = "UTphTYbUmmaaRZN3Xzl"
```

6. Click "Deploy!"

## 🎉 ¡Listo!

Tu dashboard estará disponible en:
`https://yom-tickets-dashboard.streamlit.app`

(O el nombre de repo que hayas elegido)

---

**Tiempo total:** ~5 minutos
**Costo:** $0 (Streamlit Cloud es gratis para repos privados)
