#!/usr/bin/env python3
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
import requests
import json
import os
from pathlib import Path

# Configuración de página
st.set_page_config(
    page_title="Dashboard de Tickets - Yom",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Cargar credenciales de Freshdesk
@st.cache_resource
def load_credentials():
    # Si está en Streamlit Cloud, usar secrets
    if hasattr(st, 'secrets') and 'freshdesk' in st.secrets:
        return {
            'domain': st.secrets['freshdesk']['domain'],
            'apiKey': st.secrets['freshdesk']['apiKey']
        }
    # Si es local, usar archivo
    else:
        creds_path = Path.home() / ".openclaw/credentials/freshdesk.json"
        with open(creds_path) as f:
            return json.load(f)

creds = load_credentials()
FRESHDESK_DOMAIN = creds['domain']
FRESHDESK_API_KEY = creds['apiKey']

# Función para hacer requests a Freshdesk
def freshdesk_request(endpoint, params=None):
    url = f"https://{FRESHDESK_DOMAIN}/api/v2{endpoint}"
    auth = (FRESHDESK_API_KEY, 'X')
    response = requests.get(url, auth=auth, params=params)
    response.raise_for_status()
    return response.json()

# Cache de datos (5 minutos)
@st.cache_data(ttl=300)
def fetch_tickets(days_back=90):
    """Obtener todos los tickets de los últimos N días"""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    cutoff_str = cutoff.strftime('%Y-%m-%dT%H:%M:%SZ')
    
    all_tickets = []
    page = 1
    
    with st.spinner(f'Cargando tickets de los últimos {days_back} días...'):
        while True:
            try:
                tickets = freshdesk_request(
                    '/tickets',
                    params={
                        'updated_since': cutoff_str,
                        'per_page': 100,
                        'page': page
                    }
                )
                
                if not tickets:
                    break
                    
                all_tickets.extend(tickets)
                page += 1
                
                # Límite de seguridad
                if page > 50:
                    break
                    
            except Exception as e:
                st.error(f"Error en página {page}: {str(e)}")
                break
    
    return all_tickets

# Calcular horas hábiles
def calculate_working_hours(start_date, end_date):
    """Calcular horas hábiles entre dos fechas"""
    hours = 0
    current = start_date
    
    while current < end_date:
        if current.weekday() < 5 and 8 <= current.hour < 19:
            hours += 1
        current += timedelta(hours=1)
    
    return hours

# Procesar datos
def process_tickets(tickets):
    """Convertir tickets a DataFrame con métricas calculadas"""
    df = pd.DataFrame(tickets)
    
    if df.empty:
        return df
    
    # Convertir fechas
    df['created_at'] = pd.to_datetime(df['created_at'])
    df['updated_at'] = pd.to_datetime(df['updated_at'])
    
    # Mapear prioridad y estado
    priority_map = {1: 'Baja', 2: 'Media', 3: 'Alta', 4: 'Urgente'}
    status_map = {2: 'Abierto', 3: 'Pendiente', 4: 'Resuelto', 5: 'Cerrado'}
    
    df['priority_name'] = df['priority'].map(priority_map)
    df['status_name'] = df['status'].map(status_map)
    
    # SLA por prioridad
    sla_map = {'Baja': 40, 'Media': 18, 'Alta': 9, 'Urgente': 9}
    df['sla_hours'] = df['priority_name'].map(sla_map)
    
    # Calcular tiempo transcurrido (simplificado - asume 24/7 por ahora)
    # Convertir 'now' a timezone-aware para evitar errores
    now = datetime.now(timezone.utc)
    
    # Asegurar que created_at sea timezone-aware
    if df['created_at'].dt.tz is None:
        df['created_at'] = df['created_at'].dt.tz_localize('UTC')
    
    df['elapsed_hours'] = (now - df['created_at']).dt.total_seconds() / 3600
    
    # SLA restante
    df['sla_remaining'] = df['sla_hours'] - df['elapsed_hours']
    df['sla_status'] = df['sla_remaining'].apply(
        lambda x: 'Vencido' if x < 0 else ('Por vencer' if x < 3 else 'OK')
    )
    
    # Tiempo de resolución (para tickets cerrados/resueltos)
    df['resolution_time'] = (df['updated_at'] - df['created_at']).dt.total_seconds() / 3600
    
    return df

# --- INICIO DE LA APP ---

st.title("📊 Dashboard de Tickets - Customer Support")
st.markdown("---")

# Sidebar - Filtros
st.sidebar.header("Filtros")

# Selector de rango de fechas
date_range = st.sidebar.selectbox(
    "Período",
    ["Últimos 7 días", "Últimos 30 días", "Últimos 90 días", "Personalizado"]
)

if date_range == "Últimos 7 días":
    days_back = 7
elif date_range == "Últimos 30 días":
    days_back = 30
elif date_range == "Últimos 90 días":
    days_back = 90
else:
    start_date = st.sidebar.date_input("Fecha inicio", datetime.now() - timedelta(days=30))
    end_date = st.sidebar.date_input("Fecha fin", datetime.now())
    days_back = (datetime.now() - datetime.combine(start_date, datetime.min.time())).days

# Cargar datos
try:
    tickets_raw = fetch_tickets(days_back)
    df = process_tickets(tickets_raw)
except Exception as e:
    st.error(f"Error cargando tickets: {str(e)}")
    st.info("Verifica que los Secrets estén configurados correctamente en Settings → Secrets")
    st.stop()

if df.empty:
    st.warning("No hay tickets en el período seleccionado.")
    st.stop()

# Filtro de fecha personalizado
if date_range == "Personalizado":
    df = df[
        (df['created_at'].dt.date >= start_date) &
        (df['created_at'].dt.date <= end_date)
    ]

# Filtros adicionales
priorities = ['Todas'] + sorted(df['priority_name'].dropna().unique().tolist())
selected_priority = st.sidebar.selectbox("Prioridad", priorities)

statuses = ['Todos'] + sorted(df['status_name'].dropna().unique().tolist())
selected_status = st.sidebar.selectbox("Estado", statuses)

# Aplicar filtros
filtered_df = df.copy()

if selected_priority != 'Todas':
    filtered_df = filtered_df[filtered_df['priority_name'] == selected_priority]

if selected_status != 'Todos':
    filtered_df = filtered_df[filtered_df['status_name'] == selected_status]

# Cliente (top 20)
if 'requester_id' in filtered_df.columns:
    top_clients = filtered_df['requester_id'].value_counts().head(20).index.tolist()
    client_options = ['Todos'] + [f"Cliente {c}" for c in top_clients]
    selected_client = st.sidebar.selectbox("Cliente", client_options)
    
    if selected_client != 'Todos':
        client_id = int(selected_client.split()[1])
        filtered_df = filtered_df[filtered_df['requester_id'] == client_id]

# Información de última actualización
st.sidebar.markdown("---")
st.sidebar.caption(f"Última actualización: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
st.sidebar.caption(f"Total tickets cargados: {len(df)}")

# --- MÉTRICAS PRINCIPALES ---

col1, col2, col3, col4 = st.columns(4)

with col1:
    open_tickets = len(filtered_df[filtered_df['status'].isin([2, 3])])
    st.metric("🎫 Tickets Abiertos", open_tickets)

with col2:
    sla_vencido = len(filtered_df[
        (filtered_df['sla_status'] == 'Vencido') & 
        (filtered_df['status'].isin([2, 3]))
    ])
    st.metric("🚨 SLA Vencido", sla_vencido, delta=None, delta_color="inverse")

with col3:
    sla_por_vencer = len(filtered_df[
        (filtered_df['sla_status'] == 'Por vencer') & 
        (filtered_df['status'].isin([2, 3]))
    ])
    st.metric("⚠️ SLA Por Vencer", sla_por_vencer)

with col4:
    if 'requester_id' in filtered_df.columns:
        clientes_unicos = filtered_df[filtered_df['status'].isin([2, 3])]['requester_id'].nunique()
        st.metric("👥 Clientes Afectados", clientes_unicos)

st.markdown("---")

# --- TABS ---

tab1, tab2, tab3, tab4 = st.tabs(["📈 Overview", "⏱️ SLA", "📋 Categorías", "🔍 Detalles"])

with tab1:
    st.subheader("Vista General")
    
    col1, col2 = st.columns(2)
    
    with col1:
        # Distribución por prioridad
        priority_counts = filtered_df['priority_name'].value_counts()
        fig_priority = px.pie(
            values=priority_counts.values,
            names=priority_counts.index,
            title="Distribución por Prioridad",
            color_discrete_sequence=px.colors.qualitative.Set2
        )
        st.plotly_chart(fig_priority, use_container_width=True)
    
    with col2:
        # Distribución por estado
        status_counts = filtered_df['status_name'].value_counts()
        fig_status = px.bar(
            x=status_counts.index,
            y=status_counts.values,
            title="Distribución por Estado",
            labels={'x': 'Estado', 'y': 'Cantidad'},
            color=status_counts.index,
            color_discrete_sequence=px.colors.qualitative.Pastel
        )
        st.plotly_chart(fig_status, use_container_width=True)
    
    # Tendencia temporal
    st.subheader("📅 Tendencia de Tickets")
    
    daily_tickets = filtered_df.groupby(filtered_df['created_at'].dt.date).size().reset_index()
    daily_tickets.columns = ['Fecha', 'Cantidad']
    
    fig_trend = px.line(
        daily_tickets,
        x='Fecha',
        y='Cantidad',
        title="Tickets Creados por Día",
        markers=True
    )
    st.plotly_chart(fig_trend, use_container_width=True)

with tab2:
    st.subheader("⏱️ Análisis de SLA")
    
    # SLA Compliance
    open_tickets_df = filtered_df[filtered_df['status'].isin([2, 3])]
    
    if not open_tickets_df.empty:
        sla_ok = len(open_tickets_df[open_tickets_df['sla_status'] == 'OK'])
        sla_total = len(open_tickets_df)
        sla_compliance = (sla_ok / sla_total * 100) if sla_total > 0 else 0
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("✅ SLA Compliance Rate", f"{sla_compliance:.1f}%")
        
        with col2:
            avg_remaining = open_tickets_df['sla_remaining'].mean()
            st.metric("⏰ SLA Promedio Restante", f"{avg_remaining:.1f}h")
        
        with col3:
            critical = len(open_tickets_df[
                (open_tickets_df['priority_name'] == 'Alta') & 
                (open_tickets_df['sla_status'] != 'OK')
            ])
            st.metric("🔴 Tickets Alta en Riesgo", critical)
        
        # Tabla de tickets con SLA vencido
        st.subheader("🚨 Tickets con SLA Vencido")
        
        vencidos = open_tickets_df[open_tickets_df['sla_status'] == 'Vencido'][
            ['id', 'subject', 'priority_name', 'sla_remaining', 'created_at']
        ].sort_values('sla_remaining')
        
        if not vencidos.empty:
            vencidos['sla_remaining'] = vencidos['sla_remaining'].apply(lambda x: f"{abs(x):.1f}h vencido")
            vencidos['created_at'] = vencidos['created_at'].dt.strftime('%Y-%m-%d %H:%M')
            st.dataframe(vencidos, use_container_width=True)
        else:
            st.success("✅ No hay tickets con SLA vencido")
    else:
        st.info("No hay tickets abiertos en el período seleccionado")

with tab3:
    st.subheader("📋 Análisis por Categorías")
    
    # Top 10 clientes
    if 'requester_id' in filtered_df.columns:
        st.subheader("👥 Top 10 Clientes con Más Tickets")
        
        top_clients = filtered_df['requester_id'].value_counts().head(10)
        fig_clients = px.bar(
            x=[f"Cliente {c}" for c in top_clients.index],
            y=top_clients.values,
            title="Tickets por Cliente",
            labels={'x': 'Cliente', 'y': 'Cantidad de Tickets'},
            color=top_clients.values,
            color_continuous_scale='Reds'
        )
        st.plotly_chart(fig_clients, use_container_width=True)
    
    # Tiempo promedio de resolución por prioridad
    st.subheader("⏱️ Tiempo Promedio de Resolución")
    
    resolved = filtered_df[filtered_df['status'].isin([4, 5])]
    
    if not resolved.empty:
        avg_resolution = resolved.groupby('priority_name')['resolution_time'].mean().sort_values()
        
        fig_resolution = px.bar(
            x=avg_resolution.index,
            y=avg_resolution.values,
            title="Tiempo Promedio de Resolución por Prioridad (horas)",
            labels={'x': 'Prioridad', 'y': 'Horas'},
            color=avg_resolution.values,
            color_continuous_scale='Viridis'
        )
        st.plotly_chart(fig_resolution, use_container_width=True)
    else:
        st.info("No hay tickets resueltos en el período seleccionado")

with tab4:
    st.subheader("🔍 Lista Detallada de Tickets")
    
    # Tabla completa con filtros
    display_columns = ['id', 'subject', 'priority_name', 'status_name', 'sla_status', 'created_at', 'updated_at']
    available_columns = [col for col in display_columns if col in filtered_df.columns]
    
    detail_df = filtered_df[available_columns].copy()
    detail_df['created_at'] = detail_df['created_at'].dt.strftime('%Y-%m-%d %H:%M')
    detail_df['updated_at'] = detail_df['updated_at'].dt.strftime('%Y-%m-%d %H:%M')
    
    # Renombrar columnas para mejor visualización
    detail_df.columns = ['ID', 'Asunto', 'Prioridad', 'Estado', 'SLA', 'Creado', 'Actualizado']
    
    st.dataframe(
        detail_df.sort_values('Creado', ascending=False),
        use_container_width=True,
        height=600
    )
    
    # Botón de descarga
    csv = detail_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Descargar CSV",
        data=csv,
        file_name=f"tickets_{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv",
        mime="text/csv"
    )

# Footer
st.markdown("---")
st.caption("Dashboard de Tickets - Yom Customer Support | Actualización automática cada 5 minutos")
