from datetime import date
from zoneinfo import ZoneInfo

import pandas as pd

from monthly_metrics import build_monthly_comparison, month_names_until, year_start_cutoff


CHILE_TZ = ZoneInfo("America/Santiago")


def test_sla_compliance_uses_resolution_month():
    df = pd.DataFrame([
        {
            'id': 1,
            'status': 5,
            'created_at': pd.Timestamp('2026-01-10T12:00:00Z'),
            'resolved_at': pd.Timestamp('2026-08-02T12:00:00Z'),
            'closed_at': pd.NaT,
            'sla_met': True,
            'sla_status': 'Resuelto a tiempo',
        },
        {
            'id': 2,
            'status': 5,
            'created_at': pd.Timestamp('2026-01-11T12:00:00Z'),
            'resolved_at': pd.Timestamp('2026-01-12T12:00:00Z'),
            'closed_at': pd.NaT,
            'sla_met': False,
            'sla_status': 'Resuelto tarde',
        },
    ])

    table = build_monthly_comparison(
        df,
        ['Enero', 'Agosto'],
        ['Total', 'Cerrados', 'SLA Vencido', 'SLA Compliance %'],
        date(2026, 8, 31),
        CHILE_TZ,
    )

    jan = table[table['Mes'] == 'Enero'].iloc[0]
    aug = table[table['Mes'] == 'Agosto'].iloc[0]

    assert jan['Total'] == 2
    assert jan['Cerrados'] == 1
    assert jan['SLA Vencido'] == 1
    assert jan['SLA Compliance %'] == 0
    assert aug['Total'] == 0
    assert aug['Cerrados'] == 1
    assert aug['SLA Vencido'] == 0
    assert aug['SLA Compliance %'] == 100


def test_month_boundaries_use_chile_timezone():
    df = pd.DataFrame([
        {
            'id': 1,
            'status': 2,
            'created_at': pd.Timestamp('2026-02-01T02:30:00Z'),
            'resolved_at': pd.NaT,
            'closed_at': pd.NaT,
            'sla_met': None,
            'sla_status': 'OK',
        },
    ])

    table = build_monthly_comparison(
        df,
        ['Enero', 'Febrero'],
        ['Total'],
        date(2026, 8, 31),
        CHILE_TZ,
    )

    assert table.loc[table['Mes'] == 'Enero', 'Total'].iloc[0] == 1
    assert table.loc[table['Mes'] == 'Febrero', 'Total'].iloc[0] == 0


def test_year_to_date_defaults():
    assert month_names_until(date(2026, 8, 31)) == [
        'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto'
    ]
    assert year_start_cutoff(date(2026, 8, 31)) == '2026-01-01T00:00:00Z'


if __name__ == "__main__":
    test_sla_compliance_uses_resolution_month()
    test_month_boundaries_use_chile_timezone()
    test_year_to_date_defaults()
