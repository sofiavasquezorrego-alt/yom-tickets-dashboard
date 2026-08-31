from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pandas as pd


MONTH_NAMES_ES = [
    'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'
]


def month_names_until(today):
    return MONTH_NAMES_ES[:today.month]


def year_start_cutoff(now=None):
    now = now or datetime.now(timezone.utc)
    if isinstance(now, date) and not isinstance(now, datetime):
        year = now.year
    else:
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        year = now.astimezone(timezone.utc).year
    return datetime(year, 1, 1, tzinfo=timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def month_bounds_utc(year, month, local_tz):
    if isinstance(local_tz, str):
        local_tz = ZoneInfo(local_tz)

    start_local = datetime(year, month, 1, tzinfo=local_tz)
    if month == 12:
        end_local = datetime(year + 1, 1, 1, tzinfo=local_tz)
    else:
        end_local = datetime(year, month + 1, 1, tzinfo=local_tz)

    return (
        pd.Timestamp(start_local).tz_convert('UTC'),
        pd.Timestamp(end_local).tz_convert('UTC'),
    )


def _between(series, start, end):
    series = pd.to_datetime(series, errors='coerce', utc=True)
    return series.notna() & (series >= start) & (series < end)


def _resolution_series(df):
    resolved = (
        pd.to_datetime(df['resolved_at'], errors='coerce', utc=True)
        if 'resolved_at' in df.columns
        else pd.Series(pd.NaT, index=df.index, dtype='datetime64[ns, UTC]')
    )
    closed = (
        pd.to_datetime(df['closed_at'], errors='coerce', utc=True)
        if 'closed_at' in df.columns
        else pd.Series(pd.NaT, index=df.index, dtype='datetime64[ns, UTC]')
    )
    return resolved.combine_first(closed)


def build_monthly_comparison(df_all, selected_months, selected_metrics, today, local_tz):
    rows = []
    resolution_at = _resolution_series(df_all)

    for month_name in selected_months:
        month_num = MONTH_NAMES_ES.index(month_name) + 1
        start, end = month_bounds_utc(today.year, month_num, local_tz)

        created_month = df_all[_between(df_all['created_at'], start, end)]
        open_created_month = created_month[~created_month['status'].isin([4, 5])]

        closed_in_month = df_all[
            df_all['status'].isin([4, 5]) & _between(resolution_at, start, end)
        ]
        sla_closed_in_month = closed_in_month[closed_in_month['sla_met'].notna()]

        row = {'Mes': month_name}
        if 'Total' in selected_metrics:
            row['Total'] = len(created_month)
        if 'Abiertos' in selected_metrics:
            row['Abiertos'] = len(open_created_month)
        if 'Cerrados' in selected_metrics:
            row['Cerrados'] = len(closed_in_month)
        if 'SLA Vencido' in selected_metrics:
            row['SLA Vencido'] = int((sla_closed_in_month['sla_met'] == False).sum())
        if 'Por Vencer' in selected_metrics:
            row['Por Vencer'] = len(open_created_month[open_created_month['sla_status'] == 'Por vencer'])
        if 'SLA Compliance %' in selected_metrics:
            if len(sla_closed_in_month) > 0:
                row['SLA Compliance %'] = round(
                    sla_closed_in_month['sla_met'].sum() / len(sla_closed_in_month) * 100, 1
                )
            else:
                row['SLA Compliance %'] = None

        rows.append(row)

    return pd.DataFrame(rows)
