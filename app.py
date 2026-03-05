# ============================================================
# app.py
# Interfaz Streamlit para el analizador IQ Option OTC
# Se muestra el nombre del activo y los resultados de la señal.
# ============================================================

import streamlit as st
import pandas as pd
import numpy as np
import time
from datetime import datetime
from data_provider import (
    conectar, obtener_velas, generar_senal,
    cargar_modelos, filtro_mercado_malo,
    presion_compradora_vendedora, fuerza_real_vela,
    momentum_corto_plazo, detectar_tendencias_y_reversiones,
    detectar_manipulacion_trampas
)

# Configuración de la página
st.set_page_config(page_title="IQ Option OTC Analyzer", layout="wide")

# Título principal
st.title("📈 Analizador de Activos OTC - IQ Option (Mejorado)")

# Inicializar session_state
if 'api' not in st.session_state:
    st.session_state.api = None
if 'activo' not in st.session_state:
    st.session_state.activo = "EURUSD-OTC"
if 'modelos' not in st.session_state:
    with st.spinner("Cargando modelos de IA..."):
        st.session_state.modelos = cargar_modelos()
        if st.session_state.modelos:
            st.sidebar.success("Modelos cargados")
        else:
            st.sidebar.warning("Modelos no encontrados, usando solo reglas")

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
            else:
                st.error("Error de conexión")
    
    st.header("📊 Activo a analizar")
    activo_input = st.text_input("Símbolo OTC", value=st.session_state.activo)
    if activo_input != st.session_state.activo:
        st.session_state.activo = activo_input
    
    st.header("⚙️ Opciones")
    auto_refresh = st.checkbox("Auto-refresh (cada 5s)", value=True)
    segundo_objetivo = st.number_input("Segundo para señal", min_value=0, max_value=59, value=58)

# Área principal
if st.session_state.api is None:
    st.info("👈 Conéctate a IQ Option usando el panel izquierdo")
    st.stop()

# Obtener datos actuales
with st.spinner("Obteniendo velas..."):
    velas = obtener_velas(st.session_state.activo, timeframe=60, cantidad=100)

if velas is None or len(velas) == 0:
    st.error("No se pudieron obtener datos para el activo")
    st.stop()

# Mostrar información del activo y hora
now = datetime.now()
st.header(f"🔍 Análisis en tiempo real: {st.session_state.activo}  (última actualización: {now.strftime('%H:%M:%S')})")

# Crear pestañas
tab1, tab2, tab3 = st.tabs(["📈 Señal", "📊 Métricas", "🤖 Modelos"])

with tab1:
    # Obtener segundo actual
    segundo_actual = now.second
    
    # Generar señal
    direccion, score, estado = generar_senal(
        st.session_state.activo, 
        velas, 
        st.session_state.modelos,
        segundo_actual
    )
    
    # Mostrar resultado destacado
    col1, col2, col3 = st.columns(3)
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
    
    # Información adicional
    st.write(f"**Segundo actual:** {segundo_actual} (objetivo: {segundo_objetivo})")
    
    # Mostrar última vela
    st.subheader("Última vela")
    ultima = velas.iloc[-1]
    st.write(f"Time: {ultima['timestamp']} | O: {ultima['open']:.5f} | H: {ultima['high']:.5f} | L: {ultima['low']:.5f} | C: {ultima['close']:.5f} | V: {ultima['volume']:.0f}")
    
    # Tabla de las últimas 10 velas
    st.subheader("Últimas 10 velas")
    st.dataframe(velas[['timestamp', 'open', 'high', 'low', 'close', 'volume']].tail(10))

with tab2:
    st.subheader("Métricas de mercado")
    
    # Filtro mercado malo
    malo = filtro_mercado_malo(velas)
    st.metric("Mercado malo", "SÍ" if malo else "NO")
    
    # Presión compradora/vendedora
    compra, venta = presion_compradora_vendedora(velas)
    col1, col2 = st.columns(2)
    col1.metric("Presión compradora", f"{compra:.2%}")
    col2.metric("Presión vendedora", f"{venta:.2%}")
    
    # Fuerza real de velas
    fuerza_velas = fuerza_real_vela(velas)
    st.metric("Fuerza media últimas 5 velas", f"{fuerza_velas[-5:].mean():.2%}" if len(fuerza_velas)>=5 else "N/A")
    
    # Momentum
    mom = momentum_corto_plazo(velas)
    st.metric("Momentum corto plazo", f"{mom:.5f}")
    
    # Tendencia
    tend = detectar_tendencias_y_reversiones(velas)
    st.metric("Tendencia", tend)
    
    # Manipulación
    manip = detectar_manipulacion_trampas(velas)
    st.metric("Score manipulación", f"{manip:.2%}")

with tab3:
    st.subheader("Modelos de IA")
    if st.session_state.modelos:
        st.write("Modelos cargados:")
        for nombre in st.session_state.modelos.keys():
            st.write(f"- {nombre}")
        
        # Mostrar predicción actual si es posible
        from data_provider import preparar_features_para_modelo, predecir_probabilidad
        prob, senal_ml, votos = predecir_probabilidad(velas, st.session_state.modelos)
        if prob:
            st.metric("Probabilidad CALL (ML)", f"{prob:.2%}")
            st.metric("Votos modelos", f"{votos}/3")
            st.metric("Señal ML", senal_ml)
    else:
        st.warning("No hay modelos cargados. Las señales se basan solo en reglas.")

# Auto-refresh
if auto_refresh:
    time.sleep(5)
    st.rerun()
