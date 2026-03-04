# 📊 Dashboard de Tickets - Yom Customer Support

Dashboard interactivo en tiempo real para monitorear tickets de Freshdesk.

## 🚀 Instalación Local

```bash
# Instalar dependencias
pip install -r requirements.txt

# Ejecutar
streamlit run app.py
```

El dashboard se abrirá en `http://localhost:8501`

## ☁️ Deploy en Streamlit Cloud (Gratis)

1. Crear cuenta en https://streamlit.io/cloud
2. Conectar tu repositorio GitHub
3. Seleccionar `dashboard-streamlit/app.py`
4. Configurar secrets:
   - Ir a Settings → Secrets
   - Agregar:
     ```toml
     [freshdesk]
     domain = "yom1822574979840706786.freshdesk.com"
     apiKey = "UTphTYbUmmaaRZN3Xzl"
     ```
5. Deploy automático

**Nota:** En Streamlit Cloud, modificar `app.py` línea 21 para leer secrets:

```python
# Reemplazar load_credentials() con:
creds = {
    'domain': st.secrets['freshdesk']['domain'],
    'apiKey': st.secrets['freshdesk']['apiKey']
}
```

## 📈 KPIs Incluidos

### 🔴 Críticos
- **SLA Compliance Rate** - % tickets dentro del SLA
- **Tickets con SLA Vencido** - Número total
- **Tickets Abiertos** - Por prioridad
- **Clientes Afectados** - Clientes con tickets abiertos

### 📊 Análisis
- Distribución por prioridad
- Distribución por estado
- Tendencia temporal (tickets/día)
- Tiempo promedio de resolución
- Top 10 clientes con más tickets

### 🔍 Filtros Disponibles
- Período (7/30/90 días o personalizado)
- Prioridad
- Estado
- Cliente

## 🎨 Características

- ✅ Actualización automática cada 5 minutos
- ✅ Filtros interactivos
- ✅ Gráficos dinámicos (Plotly)
- ✅ Exportar datos a CSV
- ✅ Responsive (funciona en móvil)
- ✅ Conectado directo a Freshdesk API

## 🔧 Personalización

Para agregar más KPIs, editar `app.py` y agregar tabs o métricas adicionales.

## 📝 Notas

- Cache de datos: 5 minutos (línea 36)
- Límite de carga: últimos 90 días por defecto
- Horario hábil: Simplificado, calcular con `calculate_working_hours()` si se necesita precisión
