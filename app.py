#!/usr/bin/env python3
"""
Dashboard de Tickets — Yom Customer Support
v2.0 — Rewritten from scratch for data accuracy
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone, date
import requests
import json
import concurrent.futures
from pathlib import Path
from zoneinfo import ZoneInfo
import streamlit.components.v1 as components

WAITING_CUSTOMER_STATUS = 6

CHILE_TZ = ZoneInfo("America/Santiago")

SLA_COMPLIANCE_HELP = (
    "**SLA Compliance — rangos de referencia:**\n\n"
    "🔴 Bajo — menos de 80%\n\n"
    "🟡 Medio — entre 80% y 94%\n\n"
    "🟢 Alto — 95% o más"
)

st.set_page_config(
    page_title="Dashboard de Tickets - Yom",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

components.html(
    "<script>setTimeout(function(){window.parent.location.reload();}, 300000);</script>",
    height=0,
)

# ── Credentials ──────────────────────────────────────────────
@st.cache_resource
def load_credentials():
    if hasattr(st, 'secrets') and 'freshdesk' in st.secrets:
        return {
            'domain': st.secrets['freshdesk']['domain'],
            'api_key': st.secrets['freshdesk']['apiKey']
        }
    creds_path = Path.home() / ".openclaw/credentials/freshdesk.json"
    with open(creds_path) as f:
        data = json.load(f)
        return {'domain': data['domain'], 'api_key': data['apiKey']}


creds = load_credentials()
BASE_URL = f"https://{creds['domain']}/api/v2"
AUTH = (creds['api_key'], 'X')


def api_get(endpoint, params=None):
    r = requests.get(f"{BASE_URL}{endpoint}", auth=AUTH, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


# ── Data fetching ────────────────────────────────────────────
@st.cache_data(ttl=300)
def fetch_companies():
    """Return {company_id: company_name} dict."""
    companies = {}
    page = 1
    while page <= 10:
        try:
            batch = api_get('/companies', {'per_page': 100, 'page': page})
            if not batch:
                break
            for c in batch:
                companies[c['id']] = c['name']
            if len(batch) < 100:
                break
            page += 1
        except Exception:
            break
    return companies


@st.cache_data(ttl=300)
def fetch_all_tickets():
    """
    Fetch tickets updated in the last 180 days (with stats).
    We filter by created_at client-side for accuracy.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(days=180)).strftime('%Y-%m-%dT%H:%M:%SZ')
    all_tickets = []
    page = 1
    while page <= 30:
        try:
            batch = api_get('/tickets', {
                'updated_since': cutoff,
                'per_page': 100,
                'page': page,
                'include': 'stats',
                'order_by': 'created_at',
                'order_type': 'desc'
            })
            if not batch:
                break
            all_tickets.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        except Exception as e:
            st.warning(f"Error en página {page}: {e}")
            break
    return all_tickets


@st.cache_data(ttl=600, show_spinner=False)
def fetch_ticket_activities(ticket_id):
    activities = []
    page = 1
    while page <= 30:
        try:
            resp = api_get(f'/tickets/{ticket_id}/activities',
                           {'per_page': 30, 'page': page})
        except Exception:
            return None
        if isinstance(resp, dict) and 'activities' in resp:
            batch = resp['activities']
        elif isinstance(resp, list):
            batch = resp
        else:
            break
        if not batch:
            break
        activities.extend(batch)
        if len(batch) < 30:
            break
        page += 1
    return activities


def _extract_status_change(activity):
    content = activity.get('content')
    if not isinstance(content, dict):
        return None
    last = content.get('last_updated_data')
    if not isinstance(last, dict):
        return None
    status = last.get('status')
    if status is None:
        return None
    if isinstance(status, dict):
        return status.get('to')
    if isinstance(status, list) and len(status) >= 2:
        return status[1]
    if isinstance(status, (int, float)):
        return int(status)
    return None


def compute_waiting_customer_total(activities, current_status, fallback_since, now):
    """
    Sum durations across all segments where status was WAITING_CUSTOMER_STATUS.
    Returns pd.Timedelta or pd.NaT.
    """
    if activities is None:
        if current_status == WAITING_CUSTOMER_STATUS and pd.notna(fallback_since):
            return now - fallback_since
        return pd.NaT

    transitions = []
    for a in activities:
        ts_raw = a.get('performed_at') or a.get('created_at')
        if not ts_raw:
            continue
        new_status = _extract_status_change(a)
        if new_status is None:
            continue
        ts = pd.to_datetime(ts_raw, utc=True, errors='coerce')
        if pd.isna(ts):
            continue
        transitions.append((ts, int(new_status)))

    transitions.sort()

    total = pd.Timedelta(0)
    enter_ts = None
    for ts, status in transitions:
        if status == WAITING_CUSTOMER_STATUS:
            if enter_ts is None:
                enter_ts = ts
        else:
            if enter_ts is not None:
                total += ts - enter_ts
                enter_ts = None

    if current_status == WAITING_CUSTOMER_STATUS:
        if enter_ts is not None:
            total += now - enter_ts
        elif not transitions and pd.notna(fallback_since):
            total += now - fallback_since

    if total == pd.Timedelta(0) and not any(
        s == WAITING_CUSTOMER_STATUS for _, s in transitions
    ) and current_status != WAITING_CUSTOMER_STATUS:
        return pd.NaT

    return total


# ── DataFrame builder ────────────────────────────────────────
def build_dataframe(tickets, companies):
    if not tickets:
        return pd.DataFrame()

    df = pd.DataFrame(tickets)

    # Dates — force UTC
    df['created_at'] = pd.to_datetime(df['created_at'], utc=True)
    df['updated_at'] = pd.to_datetime(df['updated_at'], utc=True)
    df['due_by'] = pd.to_datetime(df.get('due_by'), errors='coerce', utc=True)

    # resolved_at from stats
    df['resolved_at'] = df['stats'].apply(
        lambda s: s.get('resolved_at') if isinstance(s, dict) else None
    )
    df['resolved_at'] = pd.to_datetime(df['resolved_at'], errors='coerce', utc=True)

    # first_responded_at from stats
    df['first_responded_at'] = df['stats'].apply(
        lambda s: s.get('first_responded_at') if isinstance(s, dict) else None
    )
    df['first_responded_at'] = pd.to_datetime(df['first_responded_at'], errors='coerce', utc=True)

    # pending_since / status_updated_at from stats (for customer-pending-time calc)
    df['pending_since'] = df['stats'].apply(
        lambda s: s.get('pending_since') if isinstance(s, dict) else None
    )
    df['pending_since'] = pd.to_datetime(df['pending_since'], errors='coerce', utc=True)

    df['status_updated_at'] = df['stats'].apply(
        lambda s: s.get('status_updated_at') if isinstance(s, dict) else None
    )
    df['status_updated_at'] = pd.to_datetime(df['status_updated_at'], errors='coerce', utc=True)

    # Priority & Status maps
    prio_map = {1: 'Baja', 2: 'Media', 3: 'Alta', 4: 'Urgente'}
    status_map = {2: 'Abierto', 3: 'Pendiente', 4: 'Resuelto', 5: 'Cerrado',
                  6: 'Esperando al cliente'}
    df['priority_name'] = df['priority'].map(prio_map).fillna('Desconocida')
    df['status_name'] = df['status'].map(status_map).fillna('Desconocido')

    # ── Client name ──
    # Primary: company_id → company name
    df['client_name'] = df['company_id'].map(companies) if 'company_id' in df.columns else pd.Series('', index=df.index)
    df['client_name'] = df['client_name'].fillna('')

    # Fallback: first tag
    if 'tags' in df.columns:
        tag_name = df['tags'].apply(
            lambda t: t[0] if isinstance(t, list) and len(t) > 0 else ''
        )
        mask = df['client_name'] == ''
        df.loc[mask, 'client_name'] = tag_name[mask]

    df['client_name'] = df['client_name'].replace('', 'Sin cliente')

    # ── SLA status ──
    now = pd.Timestamp.now(tz='UTC')

    def calc_sla(row):
        is_open = row['status'] not in [4, 5]
        is_closed = row['status'] in [4, 5]
        due = row['due_by']
        resolved = row['resolved_at']

        if pd.isna(due):
            return 'Sin SLA'

        if is_open:
            if now > due:
                return 'Vencido'
            hours_left = (due - now).total_seconds() / 3600
            if hours_left < 4:
                return 'Por vencer'
            return 'OK'

        if is_closed:
            if pd.notna(resolved) and resolved > due:
                return 'Resuelto tarde'
            if pd.notna(resolved):
                return 'Resuelto a tiempo'
            return 'Sin datos'

        return 'N/A'

    df['sla_status'] = df.apply(calc_sla, axis=1)

    # Boolean for compliance calcs
    df['sla_met'] = df['sla_status'].map({
        'Resuelto a tiempo': True,
        'Resuelto tarde': False
    })

    # Subject (clean)
    if 'subject' in df.columns:
        df['subject'] = df['subject'].fillna('(sin asunto)')

    return df


# ── Sidebar: filters ─────────────────────────────────────────
st.sidebar.header("Filtros")

MONTH_NAMES_ES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
                  'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
_today = date.today()
_month_options = MONTH_NAMES_ES[:_today.month]

date_option = st.sidebar.selectbox(
    "Período",
    ["Este mes"] + _month_options + ["Personalizado"]
)

if date_option == "Personalizado":
    c1, c2 = st.sidebar.columns(2)
    with c1:
        start_date = st.date_input("Desde", date.today() - timedelta(days=30))
    with c2:
        end_date = st.date_input("Hasta", date.today())
elif date_option == "Este mes":
    start_date = date(_today.year, _today.month, 1)
    end_date = _today
else:
    _month_num = MONTH_NAMES_ES.index(date_option) + 1
    start_date = date(_today.year, _month_num, 1)
    if _month_num == _today.month:
        end_date = _today
    elif _month_num == 12:
        end_date = date(_today.year, 12, 31)
    else:
        end_date = date(_today.year, _month_num + 1, 1) - timedelta(days=1)

start_dt = pd.Timestamp(start_date, tz='UTC')
end_dt = pd.Timestamp(end_date, tz='UTC') + pd.Timedelta(days=1)


# ── Load data ─────────────────────────────────────────────────
try:
    companies = fetch_companies()
    raw = fetch_all_tickets()
    df_all = build_dataframe(raw, companies)
except Exception as e:
    st.error(f"Error conectando con Freshdesk: {e}")
    st.info("Verifica los Secrets en Settings → Secrets de Streamlit Cloud.")
    st.stop()

if df_all.empty:
    st.warning("No se encontraron tickets.")
    st.stop()

# Filter by created_at
df = df_all[(df_all['created_at'] >= start_dt) & (df_all['created_at'] < end_dt)].copy()

if df.empty:
    st.warning("No hay tickets creados en el período seleccionado.")
    st.stop()

# Sidebar filters
clients = sorted(df['client_name'].unique().tolist())
selected_client = st.sidebar.selectbox("Cliente", ["Todos"] + clients)

priorities = sorted(df['priority_name'].unique().tolist())
selected_priority = st.sidebar.selectbox("Prioridad", ["Todas"] + priorities)

statuses = sorted(df['status_name'].unique().tolist())
selected_status = st.sidebar.selectbox("Estado", ["Todos"] + statuses)

if selected_client != "Todos":
    df = df[df['client_name'] == selected_client]
if selected_priority != "Todas":
    df = df[df['priority_name'] == selected_priority]
if selected_status != "Todos":
    df = df[df['status_name'] == selected_status]

now_chile = datetime.now(CHILE_TZ)
st.sidebar.markdown("---")
st.sidebar.caption(f"{now_chile.strftime('%d/%m/%Y %H:%M')} Chile")
st.sidebar.caption(f"{len(df)} tickets en período")


# ── Header ────────────────────────────────────────────────────
st.title("Dashboard de Tickets — Yom")
st.caption(f"{start_date.strftime('%d/%m/%Y')} – {end_date.strftime('%d/%m/%Y')}")

# ── Top metrics ─────────────────────────────────────────────────
open_df = df[~df['status'].isin([4, 5])]
closed_df = df[df['status'].isin([4, 5])]

c1, c2, c3, c4, c5 = st.columns(5)

with c1:
    st.metric("Total", len(df))
with c2:
    st.metric("Abiertos", len(open_df))
with c3:
    vencidos = len(open_df[open_df['sla_status'] == 'Vencido'])
    st.metric("SLA Vencido", vencidos)
with c4:
    por_vencer = len(open_df[open_df['sla_status'] == 'Por vencer'])
    st.metric("Por Vencer", por_vencer)
with c5:
    sla_data = closed_df[closed_df['sla_met'].notna()]
    if len(sla_data) > 0:
        pct = sla_data['sla_met'].sum() / len(sla_data) * 100
        st.metric("SLA Compliance", f"{pct:.0f}%", help=SLA_COMPLIANCE_HELP)
    else:
        st.metric("SLA Compliance", "—", help=SLA_COMPLIANCE_HELP)

st.markdown("---")


# ── Tabs ──────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["Overview", "SLA", "Clientes", "Detalle", "Comparación por mes"]
)

# ── TAB 1: Overview ──────────────────────────────────────────
with tab1:
    col_l, col_r = st.columns(2)

    with col_l:
        type_series = df['type'] if 'type' in df.columns else pd.Series('Sin tipo', index=df.index)
        counts = type_series.fillna('Sin tipo').replace('', 'Sin tipo').value_counts()
        fig = px.pie(
            values=counts.values, names=counts.index,
            title="Por Type", hole=0.4,
            color_discrete_sequence=px.colors.qualitative.Set2
        )
        fig.update_layout(margin=dict(t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)

    with col_r:
        counts = df['priority_name'].value_counts()
        fig = px.pie(
            values=counts.values, names=counts.index,
            title="Por Prioridad", hole=0.4,
            color_discrete_sequence=px.colors.qualitative.Pastel
        )
        fig.update_layout(margin=dict(t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)

    # Daily trend
    daily = df.groupby(df['created_at'].dt.date).size().reset_index()
    daily.columns = ['Fecha', 'Tickets']
    fig = px.bar(daily, x='Fecha', y='Tickets', title="Tickets creados por día")
    fig.update_layout(margin=dict(t=40, b=20))
    st.plotly_chart(fig, use_container_width=True)


# ── TAB 2: SLA ───────────────────────────────────────────────
with tab2:
    st.subheader("SLA Compliance — Tickets Cerrados")

    sla_closed = closed_df[closed_df['sla_met'].notna()]

    if len(sla_closed) > 0:
        met = int(sla_closed['sla_met'].sum())
        not_met = len(sla_closed) - met

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("A tiempo", met)
        with c2:
            st.metric("Tarde", not_met)
        with c3:
            st.metric("Compliance", f"{met / len(sla_closed) * 100:.1f}%", help=SLA_COMPLIANCE_HELP)

        # By priority
        by_prio = sla_closed.groupby('priority_name').agg(
            total=('sla_met', 'count'),
            a_tiempo=('sla_met', 'sum')
        ).reset_index()
        by_prio['a_tiempo'] = by_prio['a_tiempo'].astype(int)
        by_prio['tarde'] = by_prio['total'] - by_prio['a_tiempo']
        by_prio['compliance'] = (by_prio['a_tiempo'] / by_prio['total'] * 100).round(1)
        by_prio.columns = ['Prioridad', 'Total', 'A tiempo', 'Tarde', '% Compliance']

        st.dataframe(
            by_prio, use_container_width=True, hide_index=True,
            column_config={
                '% Compliance': st.column_config.Column('% Compliance', help=SLA_COMPLIANCE_HELP)
            }
        )

        fig = px.bar(
            by_prio, x='Prioridad', y='% Compliance',
            title="Compliance por Prioridad",
            color='% Compliance',
            color_continuous_scale='RdYlGn',
            range_color=[0, 100],
            text='% Compliance'
        )
        fig.add_hline(y=80, line_dash="dash", line_color="red",
                      annotation_text="Meta 80%")
        fig.update_layout(margin=dict(t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)

        # Detail: which tickets were late?
        late_tickets = sla_closed[sla_closed['sla_status'] == 'Resuelto tarde'][
            ['id', 'subject', 'priority_name', 'client_name', 'created_at', 'resolved_at', 'due_by']
        ].copy()
        if not late_tickets.empty:
            st.subheader("Tickets resueltos fuera de SLA")
            late_tickets['created_at'] = late_tickets['created_at'].dt.tz_convert(CHILE_TZ).dt.strftime('%d/%m %H:%M')
            late_tickets['resolved_at'] = late_tickets['resolved_at'].dt.tz_convert(CHILE_TZ).dt.strftime('%d/%m %H:%M')
            late_tickets['due_by'] = late_tickets['due_by'].dt.tz_convert(CHILE_TZ).dt.strftime('%d/%m %H:%M')
            late_tickets.columns = ['#', 'Asunto', 'Prioridad', 'Cliente', 'Creado', 'Resuelto', 'Vencía']
            st.dataframe(late_tickets, use_container_width=True, hide_index=True)
    else:
        st.info("No hay tickets cerrados con datos de SLA en este período.")

    # Open tickets SLA
    st.markdown("---")
    st.subheader("Tickets Abiertos — Estado SLA")

    if len(open_df) > 0:
        for status_val in ['Vencido', 'Por vencer', 'OK', 'Sin SLA']:
            count = len(open_df[open_df['sla_status'] == status_val])
            if count == 0:
                continue
            if status_val == 'Vencido':
                st.error(f"🚨 {count} ticket(s) con SLA VENCIDO")
            elif status_val == 'Por vencer':
                st.warning(f"⚠️ {count} ticket(s) por vencer (<4h)")
            elif status_val == 'OK':
                st.success(f"✅ {count} ticket(s) dentro de SLA")
            else:
                st.info(f"ℹ️ {count} ticket(s) sin SLA asignado")

        # Table of overdue open tickets
        overdue = open_df[open_df['sla_status'].isin(['Vencido', 'Por vencer'])][
            ['id', 'subject', 'priority_name', 'client_name', 'status_name', 'due_by', 'created_at']
        ].copy()
        if not overdue.empty:
            overdue['due_by'] = overdue['due_by'].dt.tz_convert(CHILE_TZ).dt.strftime('%d/%m %H:%M')
            overdue['created_at'] = overdue['created_at'].dt.tz_convert(CHILE_TZ).dt.strftime('%d/%m %H:%M')
            overdue.columns = ['#', 'Asunto', 'Prioridad', 'Cliente', 'Estado', 'Vencía', 'Creado']
            st.dataframe(overdue, use_container_width=True, hide_index=True)
    else:
        st.success("No hay tickets abiertos en este período.")

    # Customer waiting time per ticket (status 6 — Esperando al cliente)
    st.markdown("---")
    st.subheader("Tiempo Esperando al Cliente")
    st.caption(
        "Suma de **todos los períodos** en estado *Esperando al cliente* "
        "(reconstruido desde el activity log de cada ticket)."
    )

    now_ts = pd.Timestamp.now(tz='UTC')
    ticket_ids = df['id'].tolist()

    with st.spinner(f"Calculando tiempos para {len(ticket_ids)} ticket(s)…"):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            activities_by_id = dict(zip(
                ticket_ids,
                ex.map(fetch_ticket_activities, ticket_ids)
            ))

    api_failed = sum(1 for v in activities_by_id.values() if v is None)
    if api_failed and api_failed == len(ticket_ids):
        st.warning(
            "El endpoint de activities de Freshdesk no respondió para ningún "
            "ticket. Mostrando solo el último período como aproximación."
        )
        with st.expander("Detalle del error (debug)"):
            try:
                probe = requests.get(
                    f"{BASE_URL}/tickets/{ticket_ids[0]}/activities",
                    auth=AUTH, timeout=15
                )
                st.code(
                    f"GET /tickets/{ticket_ids[0]}/activities\n"
                    f"status: {probe.status_code}\n"
                    f"body: {probe.text[:500]}"
                )
            except Exception as e:
                st.code(f"Exception: {e}")
    elif api_failed:
        st.info(f"{api_failed} ticket(s) sin activities — usando aproximación para esos.")

    waiting_totals = df.apply(
        lambda r: compute_waiting_customer_total(
            activities_by_id.get(r['id']), r['status'], r['pending_since'], now_ts
        ),
        axis=1
    )
    df_w = df.assign(waiting_time=waiting_totals)
    df_w['_waiting_seconds'] = df_w['waiting_time'].apply(
        lambda t: t.total_seconds() if isinstance(t, pd.Timedelta) else None
    )
    df_w = df_w[df_w['_waiting_seconds'].notna() & (df_w['_waiting_seconds'] > 0)].copy()

    if df_w.empty:
        st.info("Ningún ticket del período registró tiempo en 'Esperando al cliente'.")
    else:
        clients = sorted(df_w['client_name'].unique().tolist())
        client_filter = st.selectbox(
            "Filtrar por cliente", ["Todos"] + clients, key="waiting_client_filter"
        )
        view = df_w if client_filter == "Todos" else df_w[df_w['client_name'] == client_filter]

        if view.empty:
            st.info("No hay tickets del cliente seleccionado con tiempo de espera.")
        else:
            avg = view['waiting_time'].mean()

            def fmt_duration(td):
                if pd.isna(td):
                    return "—"
                s = int(td.total_seconds())
                d, rem = divmod(s, 86400)
                h, rem = divmod(rem, 3600)
                m = rem // 60
                if d:
                    return f"{d}d {h}h {m}m"
                return f"{h}h {m}m"

            c1, c2 = st.columns(2)
            with c1:
                st.metric("Tickets", len(view))
            with c2:
                st.metric("Promedio espera cliente", fmt_duration(avg))

            view = view.sort_values('waiting_time', ascending=False)
            display = pd.DataFrame({
                '#': view['id'],
                'Asunto': view['subject'],
                'Cliente': view['client_name'],
                'Estado': view['status_name'],
                'Tiempo Esperando Cliente': view['waiting_time'].apply(fmt_duration),
            })
            st.dataframe(display, use_container_width=True, hide_index=True)


# ── TAB 3: Clientes ──────────────────────────────────────────
with tab3:
    st.subheader("Resumen por Cliente")

    client_agg = df.groupby('client_name').agg(
        total=('id', 'count'),
        abiertos=('status', lambda x: (~x.isin([4, 5])).sum()),
        cerrados=('status', lambda x: (x.isin([4, 5])).sum()),
    ).reset_index()

    # Add SLA compliance per client
    client_sla = closed_df[closed_df['sla_met'].notna()].groupby('client_name').agg(
        sla_total=('sla_met', 'count'),
        sla_met=('sla_met', 'sum')
    ).reset_index()
    client_sla['sla_met'] = client_sla['sla_met'].astype(int)
    client_sla['sla_compliance'] = (client_sla['sla_met'] / client_sla['sla_total'] * 100).round(0)

    client_agg = client_agg.merge(client_sla[['client_name', 'sla_compliance']], on='client_name', how='left')
    client_agg = client_agg.sort_values('total', ascending=False)
    client_agg.columns = ['Cliente', 'Total', 'Abiertos', 'Cerrados', 'SLA %']
    client_agg['SLA %'] = client_agg['SLA %'].apply(lambda x: f"{x:.0f}%" if pd.notna(x) else "—")

    st.dataframe(
        client_agg, use_container_width=True, hide_index=True,
        column_config={
            'SLA %': st.column_config.Column('SLA %', help=SLA_COMPLIANCE_HELP)
        }
    )

    # Chart
    chart_data = client_agg.head(10).copy()
    fig = px.bar(
        chart_data, x='Cliente', y='Total',
        title="Top Clientes por Volumen",
        color='Abiertos',
        color_continuous_scale='OrRd'
    )
    fig.update_layout(margin=dict(t=40, b=20))
    st.plotly_chart(fig, use_container_width=True)


# ── TAB 4: Detalle ───────────────────────────────────────────
with tab4:
    st.subheader("Lista de Tickets")

    cols = ['id', 'subject', 'priority_name', 'status_name',
            'client_name', 'sla_status', 'created_at', 'updated_at']
    cols = [c for c in cols if c in df.columns]

    detail = df[cols].copy()
    detail['created_at'] = detail['created_at'].dt.tz_convert(CHILE_TZ).dt.strftime('%d/%m/%Y %H:%M')
    detail['updated_at'] = detail['updated_at'].dt.tz_convert(CHILE_TZ).dt.strftime('%d/%m/%Y %H:%M')

    col_rename = {
        'id': '#', 'subject': 'Asunto', 'priority_name': 'Prioridad',
        'status_name': 'Estado', 'client_name': 'Cliente',
        'sla_status': 'SLA', 'created_at': 'Creado', 'updated_at': 'Actualizado'
    }
    detail = detail.rename(columns={k: v for k, v in col_rename.items() if k in detail.columns})

    st.dataframe(
        detail.sort_values('Creado', ascending=False),
        use_container_width=True,
        height=600
    )

    csv = detail.to_csv(index=False).encode('utf-8')
    st.download_button(
        "Descargar CSV", csv,
        f"tickets_yom_{date.today().isoformat()}.csv",
        "text/csv"
    )


# ── TAB 5: Comparación por mes ───────────────────────────────
with tab5:
    st.subheader("Comparación por mes")
    st.caption("Independiente del filtro de período y filtros del sidebar.")

    mc_today = date.today()
    mc_month_options = MONTH_NAMES_ES[:mc_today.month]

    mc_col_l, mc_col_r = st.columns(2)
    with mc_col_l:
        mc_default_months = mc_month_options[-3:] if len(mc_month_options) >= 3 else mc_month_options
        mc_selected_months = st.multiselect(
            "Meses a comparar",
            mc_month_options,
            default=mc_default_months,
            key="mc_months"
        )
    with mc_col_r:
        mc_all_metrics = ['Total', 'Abiertos', 'Cerrados',
                          'SLA Vencido', 'Por Vencer', 'SLA Compliance %']
        mc_selected_metrics = st.multiselect(
            "Métricas",
            mc_all_metrics,
            default=mc_all_metrics,
            key="mc_metrics"
        )

    if not mc_selected_months:
        st.info("Selecciona al menos un mes para comparar.")
    elif not mc_selected_metrics:
        st.info("Selecciona al menos una métrica.")
    else:
        mc_rows = []
        for mc_month in mc_selected_months:
            mc_month_num = MONTH_NAMES_ES.index(mc_month) + 1
            mc_start = pd.Timestamp(date(mc_today.year, mc_month_num, 1), tz='UTC')
            if mc_month_num == 12:
                mc_end = pd.Timestamp(date(mc_today.year + 1, 1, 1), tz='UTC')
            else:
                mc_end = pd.Timestamp(date(mc_today.year, mc_month_num + 1, 1), tz='UTC')

            mc_month_df = df_all[(df_all['created_at'] >= mc_start) &
                                 (df_all['created_at'] < mc_end)]
            mc_open = mc_month_df[~mc_month_df['status'].isin([4, 5])]
            mc_closed = mc_month_df[mc_month_df['status'].isin([4, 5])]
            mc_sla_data = mc_closed[mc_closed['sla_met'].notna()]

            mc_row = {'Mes': mc_month}
            if 'Total' in mc_selected_metrics:
                mc_row['Total'] = len(mc_month_df)
            if 'Abiertos' in mc_selected_metrics:
                mc_row['Abiertos'] = len(mc_open)
            if 'Cerrados' in mc_selected_metrics:
                mc_row['Cerrados'] = len(mc_closed)
            if 'SLA Vencido' in mc_selected_metrics:
                mc_row['SLA Vencido'] = len(mc_open[mc_open['sla_status'] == 'Vencido'])
            if 'Por Vencer' in mc_selected_metrics:
                mc_row['Por Vencer'] = len(mc_open[mc_open['sla_status'] == 'Por vencer'])
            if 'SLA Compliance %' in mc_selected_metrics:
                if len(mc_sla_data) > 0:
                    mc_row['SLA Compliance %'] = round(
                        mc_sla_data['sla_met'].sum() / len(mc_sla_data) * 100, 1
                    )
                else:
                    mc_row['SLA Compliance %'] = None
            mc_rows.append(mc_row)

        mc_table = pd.DataFrame(mc_rows)
        st.dataframe(
            mc_table, use_container_width=True, hide_index=True,
            column_config={
                'SLA Compliance %': st.column_config.Column(
                    'SLA Compliance %', help=SLA_COMPLIANCE_HELP
                )
            }
        )

        mc_value_cols = [c for c in mc_table.columns if c != 'Mes']
        if mc_value_cols:
            mc_melted = mc_table.melt(
                id_vars=['Mes'], value_vars=mc_value_cols,
                var_name='Métrica', value_name='Valor'
            )
            mc_fig = px.bar(
                mc_melted, x='Mes', y='Valor',
                color='Métrica', barmode='group',
                title="Comparación mensual"
            )
            mc_fig.update_layout(margin=dict(t=40, b=20))
            st.plotly_chart(mc_fig, use_container_width=True)


# ── Footer ────────────────────────────────────────────────────
st.markdown("---")
st.caption(f"Dashboard Yom v2.0 — Datos de Freshdesk · Cache 5 min · {now_chile.strftime('%d/%m/%Y %H:%M')} Chile")
