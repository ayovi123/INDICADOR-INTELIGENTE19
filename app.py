# app.py
import streamlit as st
import time
from data_provider import get_provider

st.set_page_config(page_title="Bot IQ Option - Búsqueda Automática", layout="wide")
st.title("🤖 Bot de Trading IQ Option")
st.markdown("Búsqueda automática de activos OTC con análisis de fuerza y volumen")

# ============================================================
# BARRA LATERAL: CONFIGURACIÓN Y CONEXIÓN
# ============================================================
with st.sidebar:
    st.header("⚙️ Configuración")
    email = st.text_input("Email", value=st.session_state.get("email", ""), key="email_input")
    password = st.text_input("Contraseña", type="password", value=st.session_state.get("password", ""), key="password_input")
    
    # Botón de conexión
    if st.button("🔌 Conectar a IQ Option"):
        if not email or not password:
            st.error("Ingresa email y contraseña")
        else:
            with st.spinner("Conectando..."):
                provider = get_provider(email, password)
                success, message = provider.conectar()
                if success:
                    st.session_state.conectado = True
                    st.session_state.provider = provider
                    st.session_state.mensaje_conexion = message
                    st.session_state.needs_2fa = False
                    st.rerun()
                elif message == "2FA":
                    st.session_state.needs_2fa = True
                    st.session_state.provider = provider
                    st.session_state.mensaje_conexion = "Se requiere código 2FA"
                    st.rerun()
                else:
                    st.error(message)
    
    # Si requiere 2FA, mostrar campo y botón de verificación
    if st.session_state.get("needs_2fa", False):
        codigo_2fa = st.text_input("Código 2FA", key="codigo_2fa")
        if st.button("Verificar 2FA"):
            if not codigo_2fa:
                st.error("Ingresa el código")
            else:
                provider = st.session_state.provider
                success, message = provider.verificar_2fa(codigo_2fa)
                if success:
                    st.session_state.conectado = True
                    st.session_state.needs_2fa = False
                    st.session_state.mensaje_conexion = message
                    st.rerun()
                else:
                    st.error(message)
    
    # Mostrar estado de conexión
    if st.session_state.get("conectado", False):
        st.success(st.session_state.get("mensaje_conexion", "Conectado"))
        st.caption(f"Email: {email}")
    else:
        st.info("No conectado")
    
    st.divider()
    
    # Opciones de búsqueda (solo habilitadas si está conectado)
    tipo_activo = st.selectbox("Tipo de activo", ["digital", "turbo", "binary"], index=0, disabled=not st.session_state.get("conectado", False))
    intervalo_analisis = st.number_input("Intervalo entre búsquedas (segundos)", min_value=5, value=30, disabled=not st.session_state.get("conectado", False))
    max_activos_por_busqueda = st.number_input("Máx. activos a analizar por ciclo", min_value=1, value=10, disabled=not st.session_state.get("conectado", False))
    
    col1, col2 = st.columns(2)
    with col1:
        iniciar = st.button("🚀 Iniciar búsqueda", disabled=not st.session_state.get("conectado", False) or st.session_state.get("ejecutando", False))
    with col2:
        detener = st.button("⏹️ Detener", disabled=not st.session_state.get("ejecutando", False))

# ============================================================
# ÁREA PRINCIPAL: RESULTADOS DE BÚSQUEDA
# ============================================================
if "ejecutando" not in st.session_state:
    st.session_state.ejecutando = False
if "activo_actual" not in st.session_state:
    st.session_state.activo_actual = None

# Manejar inicio
if iniciar:
    st.session_state.ejecutando = True
    st.rerun()

# Manejar detención
if detener:
    st.session_state.ejecutando = False
    st.rerun()

# Bucle de búsqueda (se ejecuta mientras ejecutando = True)
if st.session_state.get("ejecutando", False) and st.session_state.get("conectado", False):
    provider = st.session_state.provider
    placeholder_estado = st.empty()
    placeholder_analisis = st.empty()
    
    # Un ciclo de búsqueda (luego se rerunea para actualizar la interfaz)
    with placeholder_estado.container():
        st.info(f"🔄 Buscando activos OTC ({tipo_activo})...")
    
    resultado = provider.buscar_mejor_activo(
        tipo_activo=tipo_activo,
        max_intentos=max_activos_por_busqueda
    )
    
    if resultado:
        st.session_state.activo_actual = resultado
        with placeholder_analisis.container():
            st.success(f"🎯 Activo seleccionado: **{resultado['activo']}**")
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Fuerza", f"{resultado['fuerza']}%")
            with col2:
                st.metric("Volumen rel.", f"{resultado['volumen']}x")
            with col3:
                st.metric("Señal IA", resultado['sentimiento'])
    else:
        with placeholder_analisis.container():
            st.warning("😕 No se encontró ningún activo con condiciones favorables en este ciclo")
    
    # Esperar el intervalo antes de rerun
    time.sleep(intervalo_analisis)
    st.rerun()
else:
    if st.session_state.get("conectado", False):
        if st.session_state.get("activo_actual"):
            st.info("Último activo encontrado. Presiona 'Iniciar búsqueda' para reanudar.")
            # Mostrar el último resultado
            ultimo = st.session_state.activo_actual
            st.success(f"**{ultimo['activo']}** - Fuerza: {ultimo['fuerza']}% | Vol: {ultimo['volumen']}x | IA: {ultimo['sentimiento']}")
        else:
            st.info("Conectado. Presiona 'Iniciar búsqueda' para comenzar.")
    else:
        st.info("Ingresa tus credenciales y presiona 'Conectar'.")
