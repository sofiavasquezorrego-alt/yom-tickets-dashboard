#!/usr/bin/env python3
"""
Integración con Google Sheets para leer SLA real
"""

import requests
import pandas as pd
from datetime import datetime
import json
from pathlib import Path

SPREADSHEET_ID = "1HhU0jGyrUE9KNLj3VaZivOeQkwRj_zOQaHMMAWwLMx8"
SLA_SHEET_RANGE = "SLA!A2:D"  # Desde fila 2 hasta el final

def load_tokens():
    """Cargar tokens de Google Sheets"""
    # En Streamlit Cloud, usar secrets
    import streamlit as st
    if hasattr(st, 'secrets') and 'google_sheets' in st.secrets:
        return {
            'access_token': st.secrets['google_sheets']['access_token'],
            'refresh_token': st.secrets['google_sheets']['refresh_token'],
            'client_id': st.secrets['google_sheets']['client_id'],
            'client_secret': st.secrets['google_sheets']['client_secret']
        }
    # En local, usar archivo
    else:
        tokens_path = Path.home() / ".openclaw/credentials/sheets-tokens.json"
        with open(tokens_path) as f:
            tokens = json.load(f)
        
        oauth_path = Path.home() / ".openclaw/credentials/gmail-oauth.json"
        with open(oauth_path) as f:
            oauth = json.load(f)
        
        return {
            'access_token': tokens['access_token'],
            'refresh_token': tokens['refresh_token'],
            'client_id': oauth['installed']['client_id'],
            'client_secret': oauth['installed']['client_secret']
        }

def refresh_access_token(tokens):
    """Refrescar access token si expiró"""
    response = requests.post('https://oauth2.googleapis.com/token', data={
        'client_id': tokens['client_id'],
        'client_secret': tokens['client_secret'],
        'refresh_token': tokens['refresh_token'],
        'grant_type': 'refresh_token'
    })
    
    if response.status_code == 200:
        new_token = response.json()['access_token']
        return new_token
    else:
        raise Exception(f"Error refrescando token: {response.text}")

def read_sla_sheet():
    """
    Leer la planilla de SLA y retornar DataFrame con tiempos reales
    """
    tokens = load_tokens()
    
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{SPREADSHEET_ID}/values/{SLA_SHEET_RANGE}"
    
    headers = {
        'Authorization': f'Bearer {tokens["access_token"]}'
    }
    
    response = requests.get(url, headers=headers)
    
    # Si el token expiró, refrescar
    if response.status_code == 401:
        new_token = refresh_access_token(tokens)
        headers['Authorization'] = f'Bearer {new_token}'
        response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        raise Exception(f"Error leyendo Sheet: {response.status_code} - {response.text}")
    
    data = response.json()
    values = data.get('values', [])
    
    if not values:
        return pd.DataFrame()
    
    # Convertir a DataFrame
    df = pd.DataFrame(values, columns=['ticket_id', 'created_at', 'closed_at', 'resolution_time_str'])
    
    # Convertir tipos
    df['ticket_id'] = pd.to_numeric(df['ticket_id'], errors='coerce')
    df['created_at'] = pd.to_datetime(df['created_at'], format='%d/%m/%Y %H:%M', errors='coerce')
    df['closed_at'] = pd.to_datetime(df['closed_at'], format='%d/%m/%Y %H:%M', errors='coerce')
    
    # Convertir tiempo de resolución (formato "HH:MM:SS") a horas decimales
    def parse_time_to_hours(time_str):
        if pd.isna(time_str) or time_str == '':
            return None
        try:
            parts = time_str.split(':')
            hours = int(parts[0])
            minutes = int(parts[1]) if len(parts) > 1 else 0
            return hours + (minutes / 60.0)
        except:
            return None
    
    df['resolution_hours'] = df['resolution_time_str'].apply(parse_time_to_hours)
    
    # Filtrar filas inválidas
    df = df.dropna(subset=['ticket_id', 'resolution_hours'])
    
    return df[['ticket_id', 'created_at', 'closed_at', 'resolution_hours']]

if __name__ == "__main__":
    # Test
    df = read_sla_sheet()
    print(f"Tickets en planilla: {len(df)}")
    print(df.head(10))
