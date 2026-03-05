# data_provider.py
import streamlit as st
import pandas as pd
import numpy as np
import time
import random
from iqoptionapi.stable_api import IQ_Option

# ------------------------------------------------------------
# CONEXIÓN A IQ OPTION
# ------------------------------------------------------------
def conectar(email, password, twofa=""):
    """
    Conecta a IQ Option y devuelve el objeto API.
    Muestra mensajes de éxito o error.
    """
    api = IQ_Option(email, password)
    try:
        if twofa:
            check, reason = api.connect(verification_code=twofa)
        else:
            check, reason = api.connect()
        
        if check:
            # Cambiar a cuenta demo si se desea (opcional)
            # api.change_balance("PRACTICE")  # "PRACTICE" para demo, "REAL" para real
            st.success("✅ Conexión exitosa a IQ Option")
            return api
        else:
            st.error(f"❌ Error de conexión: {reason}")
            return None
    except Exception as e:
        st.error(f"❌ Excepción: {str(e)}")
        return None

# ------------------------------------------------------------
# OBTENER ACTIVOS OTC
# ------------------------------------------------------------
def obtener_activos_otc(api):
    """
    Retorna una lista de activos OTC disponibles.
    """
    try:
        # Intentar obtener todos los activos (depende de la versión de la API)
        todos = api.get_all_assets()
    except AttributeError:
        todos = api.get_all_actives()  # Método alternativo
    
    otc = []
    for activo in todos:
        nombre = activo.get('name') or activo.get('symbol') or ''
        if 'OTC' in nombre.upper():
            # Obtener precio actual (opcional)
            precio = None
            try:
                precio = api.get_real_time_price(nombre)
            except:
                pass
            otc.append({
                'nombre': nombre,
                'id': activo.get('id'),
                'precio': precio
            })
    return otc

# ------------------------------------------------------------
# ANÁLISIS DE UN ACTIVO (REEMPLAZA CON TU LÓGICA REAL)
# ------------------------------------------------------------
def analizar_activo(api, activo):
    """
    Analiza el activo y devuelve un diccionario con:
    - tipo: 'COMPRA' o 'VENTA'
    - probabilidad: float (0-100)
    - fuerza: float (porcentaje, puede ser >100)
    - trampa: bool
    - motivo_trampa: str
    - motivo: str (explicación general)
    - precaucion: str (mensaje adicional, ej: "vela grande")
    """
    # --- AQUÍ DEBES PONER TU ALGORITMO REAL ---
    # Ejemplo: obtener velas, calcular indicadores, etc.
    # Por ahora, simulamos resultados aleatorios para que puedas probar.
    
    # Simulación (reemplazar con lógica real)
    tipo = random.choice(['COMPRA', 'VENTA'])
    prob = random.uniform(0, 100)
    fuerza = random.uniform(0, 150)
    trampa = random.choice([True, False])
    
    if trampa:
        if tipo == 'COMPRA':
            motivo_trampa = "BAJISTA (falso breakout) → señal de COMPRA"
        else:
            motivo_trampa = "ALCISTA (falso breakout) → señal de VENTA"
    else:
        motivo_trampa = ""
    
    motivo = f"Análisis basado en cruce de medias y RSI. "
    if prob > 70:
        motivo += "Alta probabilidad."
    else:
        motivo += "Probabilidad moderada."
    
    precaucion = ""
    if fuerza > 100:
        precaucion = "¡PRECAUCIÓN: vela siguiente podría ser de gran tamaño (alto potencial de movimiento fuerte)!"
    
    return {
        'tipo': tipo,
        'probabilidad': round(prob, 1),
        'fuerza': round(fuerza, 1),
        'trampa': trampa,
        'motivo_trampa': motivo_trampa,
        'motivo': motivo,
        'precaucion': precaucion
    }

# ------------------------------------------------------------
# FUNCIÓN PARA OBTENER VELAS (OPCIONAL)
# ------------------------------------------------------------
def obtener_velas(api, activo, timeframe=60, count=100):
    """
    Obtiene velas de un activo.
    timeframe en segundos (60 = 1 minuto).
    """
    from time import time
    velas = api.get_candles(activo, timeframe, count, time())
    return pd.DataFrame(velas)
