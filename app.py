# ============================================================
# app.py
# Interfaz Streamlit con:
# - Lista completa de activos OTC
# - Cambio automático de activo si el actual está malo
# - Tabla resumen de todos los activos
# - Señal al segundo 58 con vencimiento
# - Muestra el activo actual y su estado
# ============================================================

import streamlit as st
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
from data_provider import (
    conectar, obtener_velas, obtener_activos_otc,
    generar_senal, filtro_mercado_malo,
    presion_compradora_vendedora, fuerza_real_vela,
    momentum_corto_plazo, detectar_tendencias_y_reversiones,
    detectar_manipulacion_trampas, features_avanzadas
)

# Configuración de la página
st.set_page_config(page_title="IQ Option OTC Analyzer Pro", layout="wide")

# Título principal
st.title("📈 Analizador Profesional de Activos OTC - IQ Option")

# Inicializar session_state
if 'api' not in st.session_state:
    st.session_state.api = None
if 'activos_otc' not in st.session_state:
    st.session_state.activos_otc = []
if 'indice_actual' not in st.session_state:
    st.session_state.indice_actual = 0
if 'ultimo_analisis' not in st.session_state:
    st.session_state.ultimo_analisis = {}
if 'modelos_cargados' not in st.session_state:
    st.session_state.modelos_cargados = False

# Sidebar: credenciales y configuración
with st.sidebar:
    st.header("🔑 Conexión IQ Option")
    email = st.text_input("Email", value="tu_email@ejemplo.com")
    password = st.text_input("Password", type="password", value="")
    twofa = st.text_input("2FA (si aplica)")
    
    if st.button("Conectar"):
        with st.spinner("Conectando..."):
            api = conectar(email, password, twofa if twofa else None)
            if api:
                st.session_state.api = api
                st.success("Conectado")
                # Obtener lista de activos OTC
                with st.spinner("Obteniendo activos OTC..."):
                    st.session_state.activos_otc = obtener_activos_otc(api)
                    st.success(f"Se encontraron {len(st.session_state.activos_otc)} activos OTC")
                    st.session_state.indice_actual = 0
            else:
                st.error("Error de conexión")
    
    st.header("⚙️ Opciones")
    auto_refresh = st.checkbox("Auto-refresh (cada 5s)", value=True)
    segundo_objetivo = st.number_input("Segundo para señal", min_value=0, max_value=59, value=58)
    
    # Mostrar activos disponibles
    if st.session_state.activos_otc:
        st.header("📊 Activos OTC disponibles")
        st.write(f"Total: {len(st.session_state.activos_otc)}")
        # Selector manual para debugging
        idx = st.selectbox("Ir a activo manualmente", 
                           range(len(st.session_state.activos_otc)),
                           format_func=lambda i: st.session_state.activos_otc[i])
        if st.button("Cambiar a este activo"):
            st.session_state.indice_actual = idx
            st.rerun()

# Área principal
if st.session_state.api is None:
    st.info("👈 Conéctate a IQ Option usando el panel izquierdo")
    st.stop()

if not st.session_state.activos_otc:
    st.warning("No se encontraron activos OTC. Verifica la conexión.")
    st.stop()

# Obtener el activo actual basado en el índice
activo_actual = st.session_state.activos_otc[st.session_state.indice_actual]

# Obtener velas del activo actual
with st.spinner(f"Analizando {activo_actual}..."):
    velas = obtener_velas(activo_actual, timeframe=60, cantidad=100)

if velas is None or len(velas) == 0:
    st.error(f"No se pudieron obtener datos para {activo_actual}")
    # Pasar al siguiente activo automáticamente
    st.session_state.indice_actual = (st.session_state.indice_actual + 1) % len(st.session_state.activos_otc)
    st.rerun()

# Verificar si el activo actual está en malas condiciones
if filtro_mercado_malo(velas):
    st.warning(f"⚠️ {activo_actual} está en mercado malo. Cambiando automáticamente...")
    time.sleep(1)
    st.session_state.indice_actual = (st.session_state.indice_actual + 1) % len(st.session_state.activos_otc)
    st.rerun()

# Mostrar hora actual
now = datetime.now()
st.header(f"🔍 Análisis en tiempo real: **{activo_actual}**  (actualización: {now.strftime('%H:%M:%S')})")
st.caption(f"Activo {st.session_state.indice_actual+1} de {len(st.session_state.activos_otc)}")

# Generar señal
segundo_actual = now.second
direccion, score, estado, expiracion, tipo = generar_senal(activo_actual, velas, segundo_actual)

# Mostrar resultado destacado
col1, col2, col3, col4 = st.columns(4)
with col1:
    if direccion == 'CALL':
        st.success(f"🔔 SEÑAL: {direccion}")
    elif direccion == 'PUT':
        st.error(f"🔔 SEÑAL: {direccion}")
    elif direccion == 'NO_OPERAR':
        st.warning(f"⛔ NO OPERAR")
    else:
        st.info(f"⏳ {direccion}")

with col2:
    st.metric("Score / Probabilidad", f"{score:.2%}" if score else "N/A")

with col3:
    st.metric("Estado", estado)

with col4:
    if expiracion:
        st.metric("Vencimiento (próx. vela)", expiracion)

if tipo:
    st.info(f"**Tipo:** {tipo}")

# Métricas adicionales del activo actual
st.subheader("📊 Métricas del activo actual")
col1, col2, col3, col4 = st.columns(4)
compra, venta = presion_compradora_vendedora(velas)
col1.metric("Presión compradora", f"{compra:.2%}")
col2.metric("Presión vendedora", f"{venta:.2%}")
tend = detectar_tendencias_y_reversiones(velas)
col3.metric("Tendencia", tend)
manip = detectar_manipulacion_trampas(velas)
col4.metric("Manipulación", f"{manip:.2%}")

# Tabla resumen de TODOS los activos OTC
st.subheader("📋 Estado de todos los activos OTC")

# Función para analizar rápidamente un activo (solo para la tabla)
def analizar_activo_resumen(activo):
    try:
        v = obtener_velas(activo, timeframe=60, cantidad=50)
        if v is None or len(v) < 20:
            return {'activo': activo, 'estado': 'Error', 'tendencia': 'N/A', 'manip': 'N/A'}
        malo = filtro_mercado_malo(v)
        estado = 'Malo' if malo else 'Bueno'
        tend = detectar_tendencias_y_reversiones(v)
        manip = detectar_manipulacion_trampas(v)
        return {'activo': activo, 'estado': estado, 'tendencia': tend, 'manip': f"{manip:.2%}"}
    except:
        return {'activo': activo, 'estado': 'Error', 'tendencia': 'N/A', 'manip': 'N/A'}

# Mostrar tabla con progreso
if st.button("Actualizar tabla completa"):
    with st.spinner("Analizando todos los activos..."):
        datos_resumen = []
        for i, act in enumerate(st.session_state.activos_otc):
            st.caption(f"Procesando {i+1}/{len(st.session_state.activos_otc)}: {act}")
            datos_resumen.append(analizar_activo_resumen(act))
        df_resumen = pd.DataFrame(datos_resumen)
        st.session_state.ultimo_analisis = df_resumen

if st.session_state.ultimo_analisis:
    st.dataframe(st.session_state.ultimo_analisis, use_container_width=True)

# Últimas velas del activo actual
st.subheader(f"Últimas 10 velas de {activo_actual}")
st.dataframe(velas[['timestamp', 'open', 'high', 'low', 'close', 'volume']].tail(10))

# Auto-refresh
if auto_refresh:
    time.sleep(5)
    st.rerun()
