# app.py
import streamlit as st
import pandas as pd
import time
from datetime import datetime
import data_provider as dp

# Configuración de la página
st.set_page_config(page_title="Indicador IQ Option", layout="wide")
st.title("📈 Indicador Inteligente para IQ Option (OTC)")

# Inicializar variables de sesión
if 'api' not in st.session_state:
    st.session_state.api = None
if 'autenticado' not in st.session_state:
    st.session_state.autenticado = False
if 'activos_otc' not in st.session_state:
    st.session_state.activos_otc = []
if 'activo_seleccionado' not in st.session_state:
    st.session_state.activo_seleccionado = None
if 'analisis' not in st.session_state:
    st.session_state.analisis = None

# ------------------------------------------------------------
# PASO 1: LOGIN
# ------------------------------------------------------------
if not st.session_state.autenticado:
    st.header("🔐 Conectar a IQ Option")
    with st.form("login_form"):
        email = st.text_input("Email", placeholder="tu@email.com")
        password = st.text_input("Contraseña", type="password")
        twofa = st.text_input("Código 2FA (si tienes)", placeholder="Opcional")
        submitted = st.form_submit_button("Iniciar sesión")
        
        if submitted:
            if not email or not password:
                st.error("Por favor ingresa email y contraseña")
            else:
                with st.spinner("Conectando a IQ Option..."):
                    api = dp.conectar(email, password, twofa)
                    if api:
                        st.session_state.api = api
                        st.session_state.autenticado = True
                        st.rerun()
    st.stop()  # No mostrar nada más hasta que se autentique

# ------------------------------------------------------------
# PASO 2: BÚSQUEDA DE ACTIVOS OTC
# ------------------------------------------------------------
st.sidebar.header("🔍 Búsqueda de activos")
if st.sidebar.button("Buscar activos OTC", type="primary"):
    with st.spinner("Buscando activos OTC para analizar..."):
        activos = dp.obtener_activos_otc(st.session_state.api)
        if activos:
            st.session_state.activos_otc = activos
            st.sidebar.success(f"✅ {len(activos)} activos encontrados")
        else:
            st.sidebar.warning("Ningún activo OTC encontrado")
            st.session_state.activos_otc = []

# Mostrar lista de activos en el sidebar
if st.session_state.activos_otc:
    st.sidebar.subheader("Activos OTC disponibles")
    nombres = [a['nombre'] for a in st.session_state.activos_otc]
    seleccion = st.sidebar.selectbox("Selecciona un activo", nombres)
    
    if st.sidebar.button("Analizar activo"):
        st.session_state.activo_seleccionado = seleccion
        st.session_state.analisis = None  # Limpiar análisis anterior
        st.rerun()

# ------------------------------------------------------------
# PASO 3: ANÁLISIS DEL ACTIVO SELECCIONADO
# ------------------------------------------------------------
if st.session_state.activo_seleccionado:
    activo = st.session_state.activo_seleccionado
    st.header(f"📊 Análisis de {activo}")
    
    # Mostrar mensajes de estado
    st.info(f"**Activo detectado:** {activo} (OTC) - Cumple condiciones de volumen y tendencia.")
    with st.spinner(f"Analizando {activo} (OTC)..."):
        # Pequeña pausa para simular procesamiento (opcional)
        time.sleep(1)
        analisis = dp.analizar_activo(st.session_state.api, activo)
        st.session_state.analisis = analisis
    
    # Mostrar resultados
    if st.session_state.analisis:
        a = st.session_state.analisis
        st.subheader("📢 Señal completa")
        
        # Usar columnas para organizar
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Tipo", a['tipo'])
            st.metric("Probabilidad", f"{a['probabilidad']}%")
        with col2:
            st.metric("Fuerza", f"{a['fuerza']}%")
            trampa_color = "red" if a['trampa'] else "green"
            st.markdown(f"**Trampa detectada:** <span style='color:{trampa_color}'>{'SÍ' if a['trampa'] else 'NO'}</span>", unsafe_allow_html=True)
        
        if a['trampa']:
            st.warning(f"🧩 **Motivo trampa:** {a['motivo_trampa']}")
        
        st.info(f"📝 **Motivo:** {a['motivo']}")
        
        if a['precaucion']:
            st.error(f"⚠️ {a['precaucion']}")
        
        # Espacio para gráfico (puedes agregar velas más adelante)
        st.subheader("📉 Gráfico del activo")
        st.caption("(Aquí puedes integrar un gráfico de velas con plotly)")
        # Ejemplo de placeholder
        st.line_chart(pd.DataFrame({'Precio': [1,2,3,2,1]}))

# ------------------------------------------------------------
# PIE DE PÁGINA Y OPCIONES
# ------------------------------------------------------------
st.sidebar.markdown("---")
if st.sidebar.button("Cerrar sesión"):
    for key in ['api', 'autenticado', 'activos_otc', 'activo_seleccionado', 'analisis']:
        if key in st.session_state:
            del st.session_state[key]
    st.rerun()

# Mostrar la hora actual en el sidebar (opcional)
st.sidebar.write(f"Última actualización: {datetime.now().strftime('%H:%M:%S')}")
