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

# Google Sheets - leer CSV público directo (no requiere API)
SPREADSHEET_ID = "1HhU0jGyrUE9KNLj3VaZivOeQkwRj_zOQaHMMAWwLMx8"
SLA_GID = "1232697974"

@st.cache_data(ttl=300)
def load_sla_from_sheet():
    """Cargar SLA desde la planilla pública (CSV)"""
    try:
        url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv&gid={SLA_GID}"
        df = pd.read_csv(url, skiprows=1, names=['ticket_id', 'created_at', 'closed_at', 'resolution_time_str'])
        
        # Convertir tiempo "HH:MM:SS" a horas decimales
        def parse_time(time_str):
            try:
                parts = str(time_str).split(':')
                return int(parts[0]) + (int(parts[1]) / 60.0)
            except:
                return None
        
        df['resolution_hours'] = df['resolution_time_str'].apply(parse_time)
        df = df.dropna(subset=['ticket_id', 'resolution_hours'])
        df['ticket_id'] = df['ticket_id'].astype(int)
        
        return df[['ticket_id', 'resolution_hours']]
    except Exception as e:
        st.sidebar.error(f"❌ Error leyendo planilla: {str(e)}")
        return pd.DataFrame()

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
    """
    Obtener todos los tickets con stats.
    Nota: Freshdesk API no permite filtrar por created_at directamente,
    así que traemos con updated_since y filtramos después por created_at.
    """
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
                        'page': page,
                        'include': 'stats'
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
    """
    Calcular horas hábiles entre dos fechas (L-V, 8 AM - 7 PM Chile)
    """
    if pd.isna(start_date) or pd.isna(end_date):
        return 0
    
    if start_date >= end_date:
        return 0
    
    # Asegurar que sean timezone-aware
    if start_date.tzinfo is None:
        start_date = start_date.replace(tzinfo=timezone.utc)
    if end_date.tzinfo is None:
        end_date = end_date.replace(tzinfo=timezone.utc)
    
    hours = 0
    current = start_date
    
    # Iterar hora por hora
    while current < end_date:
        # Lunes a Viernes (0-4) y entre 8 AM y 7 PM
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
    
    # Obtener nombre de empresa desde tags (primer tag es el cliente)
    if 'tags' in df.columns:
        df['client_name'] = df['tags'].apply(
            lambda x: x[0] if isinstance(x, list) and len(x) > 0 else 'Sin cliente'
        )
    else:
        df['client_name'] = 'Sin cliente'
    
    # SLA por prioridad
    sla_map = {'Baja': 40, 'Media': 18, 'Alta': 9, 'Urgente': 9}
    df['sla_hours'] = df['priority_name'].map(sla_map)
    
    # Calcular tiempo transcurrido (simplificado - asume 24/7 por ahora)
    # Convertir 'now' a timezone-aware para evitar errores
    now = datetime.now(timezone.utc)
    
    # Asegurar que created_at sea timezone-aware
    if df['created_at'].dt.tz is None:
        df['created_at'] = df['created_at'].dt.tz_localize('UTC')
    
    # Calcular horas transcurridas en horas hábiles
    df['elapsed_hours'] = df['created_at'].apply(
        lambda x: calculate_working_hours(x, now)
    )
    
    # SLA restante (solo para tickets abiertos)
    df['sla_remaining'] = df['sla_hours'] - df['elapsed_hours']
    df['sla_status'] = df.apply(
        lambda row: 'Vencido' if row['sla_remaining'] < 0 and row['status'] in [2, 3] 
                    else ('Por vencer' if row['sla_remaining'] < 3 and row['status'] in [2, 3] else 'OK'),
        axis=1
    )
    
    # Extraer stats.resolved_at si existe
    if 'stats' in df.columns:
        df['resolved_at'] = df['stats'].apply(
            lambda x: x.get('resolved_at') if isinstance(x, dict) else None
        )
        df['resolved_at'] = pd.to_datetime(df['resolved_at'], errors='coerce')
        
        # Asegurar timezone-aware
        if df['resolved_at'].dt.tz is None:
            df['resolved_at'] = df['resolved_at'].dt.tz_localize('UTC', nonexistent='shift_forward', ambiguous='NaT')
    else:
        df['resolved_at'] = None
    
    # Tiempo de resolución en horas hábiles (solo para tickets con resolved_at)
    df['resolution_time'] = df.apply(
        lambda row: calculate_working_hours(row['created_at'], row['resolved_at'])
                    if row['status'] in [4, 5] and pd.notna(row.get('resolved_at')) 
                    else None,
        axis=1
    )
    
    # Calcular SLA compliance histórico (solo si tenemos resolution_time)
    df['sla_met'] = df.apply(
        lambda row: (row['resolution_time'] <= row['sla_hours']) 
                    if pd.notna(row.get('resolution_time'))
                    else None,
        axis=1
    )
    
    # Tipo de problema (cliente vs Yom)
    if 'type' in df.columns:
        df['problem_origin'] = df['type'].apply(
            lambda x: 'Cliente' if x and ('no es problema' in str(x).lower() or 'cliente' in str(x).lower())
                     else 'Yom' if x else 'Sin clasificar'
        )
    else:
        df['problem_origin'] = 'Sin clasificar'
    
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
    
    # Cargar SLA real desde planilla (SOLO para tiempos de resolución)
    sla_df = load_sla_from_sheet()
    
    if not sla_df.empty:
        # Merge con la planilla (SOLO resolution_hours)
        df = df.merge(
            sla_df,
            left_on='id',
            right_on='ticket_id',
            how='left',
            suffixes=('_freshdesk', '_planilla')
        )
        
        # Usar resolution_hours de la planilla si existe
        df['resolution_time'] = df['resolution_hours'].where(pd.notna(df['resolution_hours']), None)
        
        # Recalcular sla_met
        df['sla_met'] = df.apply(
            lambda row: (row['resolution_time'] <= row['sla_hours']) 
                        if pd.notna(row.get('resolution_time'))
                        else None,
            axis=1
        )
        
        tickets_with_sla = len(df[df['resolution_time'].notna()])
        st.sidebar.success(f"✅ SLA de planilla: {tickets_with_sla} tickets")
        
        tickets_closed_no_sla = len(df[(df['status'].isin([4, 5])) & (df['resolution_time'].isna())])
        if tickets_closed_no_sla > 0:
            st.sidebar.warning(f"⚠️ {tickets_closed_no_sla} tickets cerrados sin SLA")
    else:
        st.sidebar.warning("⚠️ No se pudo cargar planilla de SLA")
    
except Exception as e:
    st.error(f"Error cargando tickets: {str(e)}")
    st.info("Verifica que los Secrets estén configurados correctamente en Settings → Secrets")
    st.stop()

if df.empty:
    st.warning("No hay tickets en el período seleccionado.")
    st.stop()

# Filtro por fecha de creación según el período seleccionado
if date_range == "Personalizado":
    df = df[
        (df['created_at'].dt.date >= start_date) &
        (df['created_at'].dt.date <= end_date)
    ]
else:
    # Para períodos predefinidos, filtrar por created_at
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=days_back)
    df = df[df['created_at'] >= cutoff_date]

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
if 'client_name' in filtered_df.columns:
    top_clients = filtered_df['client_name'].value_counts().head(20).index.tolist()
    client_options = ['Todos'] + top_clients
    selected_client = st.sidebar.selectbox("Cliente", client_options)
    
    if selected_client != 'Todos':
        filtered_df = filtered_df[filtered_df['client_name'] == selected_client]

# Información de última actualización
st.sidebar.markdown("---")
st.sidebar.caption(f"Última actualización: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
st.sidebar.caption(f"Tickets creados en el período: {len(df)}")

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
    if 'client_name' in filtered_df.columns:
        clientes_unicos = filtered_df[filtered_df['status'].isin([2, 3])]['client_name'].nunique()
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
        # Origen del problema (Cliente vs Yom)
        if 'problem_origin' in filtered_df.columns:
            origin_counts = filtered_df['problem_origin'].value_counts()
            fig_origin = px.pie(
                values=origin_counts.values,
                names=origin_counts.index,
                title="Origen del Problema",
                color_discrete_map={
                    'Cliente': '#90EE90',
                    'Yom': '#FFB6C1',
                    'Sin clasificar': '#D3D3D3'
                }
            )
            st.plotly_chart(fig_origin, use_container_width=True)
        else:
            st.info("Campo 'type' no disponible para análisis de origen")
    
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
    
    # Información del período
    st.info(f"📅 Analizando tickets CREADOS en el período seleccionado ({date_range}). Total: {len(filtered_df)} tickets.")
    
    # SLA Compliance histórico (todos los tickets cerrados/resueltos en el período)
    closed_tickets = filtered_df[filtered_df['status'].isin([4, 5])]
    
    if not closed_tickets.empty and 'sla_met' in closed_tickets.columns:
        sla_met_count = closed_tickets['sla_met'].sum()
        sla_total_closed = len(closed_tickets[closed_tickets['sla_met'].notna()])
        sla_compliance_historical = (sla_met_count / sla_total_closed * 100) if sla_total_closed > 0 else 0
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric(
                "✅ SLA Compliance General", 
                f"{sla_compliance_historical:.1f}%",
                help=f"Basado en {sla_total_closed} tickets cerrados/resueltos que fueron CREADOS en el período seleccionado"
            )
        
        with col2:
            # Tickets abiertos en riesgo
            open_tickets_df = filtered_df[filtered_df['status'].isin([2, 3])]
            in_risk = len(open_tickets_df[open_tickets_df['sla_status'] != 'OK'])
            st.metric("⚠️ Tickets Abiertos en Riesgo", in_risk)
        
        # SLA Compliance por prioridad (desglosado)
        st.subheader("📊 SLA Compliance por Prioridad")
        
        sla_by_priority = closed_tickets.groupby('priority_name').agg({
            'sla_met': ['sum', 'count']
        })
        sla_by_priority.columns = ['Cumplidos', 'Total']
        sla_by_priority['% Cumplimiento'] = (sla_by_priority['Cumplidos'] / sla_by_priority['Total'] * 100).round(1)
        sla_by_priority = sla_by_priority.sort_values('% Cumplimiento', ascending=False)
        
        # Mostrar en columnas
        priority_cols = st.columns(len(sla_by_priority))
        for idx, (priority, row) in enumerate(sla_by_priority.iterrows()):
            with priority_cols[idx]:
                st.metric(
                    f"{priority}", 
                    f"{row['% Cumplimiento']:.1f}%",
                    help=f"{int(row['Cumplidos'])} de {int(row['Total'])} tickets"
                )
        
        # Gráfico de SLA por prioridad
        st.subheader("📊 Gráfico de Cumplimiento por Prioridad")
        
        if not sla_by_priority.empty:
            fig_sla_priority = px.bar(
                x=sla_by_priority.index,
                y=sla_by_priority['% Cumplimiento'],
                title="% de Cumplimiento de SLA por Prioridad",
                labels={'x': 'Prioridad', 'y': '% Cumplimiento'},
                color=sla_by_priority['% Cumplimiento'],
                color_continuous_scale='RdYlGn',
                range_color=[0, 100]
            )
            fig_sla_priority.add_hline(y=80, line_dash="dash", line_color="red", 
                                       annotation_text="Meta: 80%")
            st.plotly_chart(fig_sla_priority, use_container_width=True)
    else:
        st.info("No hay tickets cerrados en el período seleccionado para calcular SLA histórico")
    
    # SLA de tickets actuales abiertos
    st.subheader("🎫 Estado Actual de Tickets Abiertos")
    
    open_tickets_df = filtered_df[filtered_df['status'].isin([2, 3])]
    
    if not open_tickets_df.empty:
        sla_ok = len(open_tickets_df[open_tickets_df['sla_status'] == 'OK'])
        sla_total = len(open_tickets_df)
        sla_compliance_current = (sla_ok / sla_total * 100) if sla_total > 0 else 0
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.metric("✅ Tickets en Tiempo", sla_ok)
        
        with col2:
            avg_remaining = open_tickets_df['sla_remaining'].mean()
            st.metric("⏰ SLA Promedio Restante", f"{avg_remaining:.1f}h")
        
        # Tabla de tickets con SLA vencido
        st.subheader("🚨 Tickets con SLA Vencido")
        
        vencidos = open_tickets_df[open_tickets_df['sla_status'] == 'Vencido'][
            ['id', 'subject', 'priority_name', 'client_name', 'sla_remaining', 'created_at']
        ].sort_values('sla_remaining')
        
        if not vencidos.empty:
            vencidos['sla_remaining'] = vencidos['sla_remaining'].apply(lambda x: f"{abs(x):.1f}h vencido")
            vencidos['created_at'] = vencidos['created_at'].dt.strftime('%Y-%m-%d %H:%M')
            vencidos.columns = ['ID', 'Asunto', 'Prioridad', 'Cliente', 'SLA Vencido', 'Creado']
            st.dataframe(vencidos, use_container_width=True)
        else:
            st.success("✅ No hay tickets con SLA vencido")
    else:
        st.info("No hay tickets abiertos en el período seleccionado")

with tab3:
    st.subheader("📋 Análisis por Categorías")
    
    # Ranking de clientes (sin gráfico)
    if 'client_name' in filtered_df.columns:
        st.subheader("👥 Ranking de Clientes con Más Tickets")
        
        top_clients = filtered_df['client_name'].value_counts().head(10).reset_index()
        top_clients.columns = ['Cliente', 'Cantidad de Tickets']
        top_clients['Ranking'] = range(1, len(top_clients) + 1)
        top_clients = top_clients[['Ranking', 'Cliente', 'Cantidad de Tickets']]
        
        st.dataframe(top_clients, use_container_width=True, hide_index=True)
    
    # Tiempo promedio de resolución por prioridad (corregido)
    st.subheader("⏱️ Tiempo Promedio de Resolución por Prioridad")
    
    resolved = filtered_df[
        (filtered_df['status'].isin([4, 5])) & 
        (filtered_df['resolution_time'].notna())
    ]
    
    if not resolved.empty:
        avg_resolution = resolved.groupby('priority_name')['resolution_time'].mean().sort_values()
        
        # Mostrar tabla en vez de gráfico para ver números exactos
        resolution_df = pd.DataFrame({
            'Prioridad': avg_resolution.index,
            'Tiempo Promedio (horas)': avg_resolution.values.round(1),
            'Tickets Resueltos': resolved.groupby('priority_name').size().values
        })
        
        st.dataframe(resolution_df, use_container_width=True, hide_index=True)
        
        # Gráfico
        fig_resolution = px.bar(
            x=avg_resolution.index,
            y=avg_resolution.values,
            title="Tiempo Promedio de Resolución (horas)",
            labels={'x': 'Prioridad', 'y': 'Horas'},
            color=avg_resolution.values,
            color_continuous_scale='Viridis'
        )
        st.plotly_chart(fig_resolution, use_container_width=True)
    else:
        st.info("No hay tickets resueltos en el período seleccionado")
    
    # Análisis de origen del problema
    if 'problem_origin' in filtered_df.columns:
        st.subheader("🔍 Análisis de Origen del Problema")
        
        origin_stats = filtered_df['problem_origin'].value_counts().reset_index()
        origin_stats.columns = ['Origen', 'Cantidad']
        origin_stats['Porcentaje'] = (origin_stats['Cantidad'] / origin_stats['Cantidad'].sum() * 100).round(1)
        
        st.dataframe(origin_stats, use_container_width=True, hide_index=True)

with tab4:
    st.subheader("🔍 Lista Detallada de Tickets")
    
    # Tabla completa con filtros
    display_columns = ['id', 'subject', 'priority_name', 'status_name', 'client_name', 
                      'problem_origin', 'sla_status', 'created_at', 'updated_at']
    available_columns = [col for col in display_columns if col in filtered_df.columns]
    
    detail_df = filtered_df[available_columns].copy()
    detail_df['created_at'] = detail_df['created_at'].dt.strftime('%Y-%m-%d %H:%M')
    detail_df['updated_at'] = detail_df['updated_at'].dt.strftime('%Y-%m-%d %H:%M')
    
    # Renombrar columnas para mejor visualización
    column_names = {
        'id': 'ID',
        'subject': 'Asunto',
        'priority_name': 'Prioridad',
        'status_name': 'Estado',
        'client_name': 'Cliente',
        'problem_origin': 'Origen',
        'sla_status': 'SLA',
        'created_at': 'Creado',
        'updated_at': 'Actualizado'
    }
    detail_df = detail_df.rename(columns={k: v for k, v in column_names.items() if k in detail_df.columns})
    
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
