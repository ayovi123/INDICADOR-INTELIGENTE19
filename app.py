# app.py
import streamlit as st
import time
import logging
from data_provider import get_provider

# Configuración de la página
st.set_page_config(page_title="Bot IQ Option - Búsqueda Automática", layout="wide")
st.title("🤖 Bot de Trading IQ Option")
st.markdown("Búsqueda automática de activos OTC con análisis de fuerza y volumen")

# ============================================================
# BARRA LATERAL: CONFIGURACIÓN
# ============================================================
with st.sidebar:
    st.header("⚙️ Configuración")
    email = st.text_input("Email", type="default")
    password = st.text_input("Contraseña", type="password")
    tipo_activo = st.selectbox("Tipo de activo", ["digital", "turbo", "binary"], index=0)
    intervalo_analisis = st.number_input("Intervalo entre búsquedas (segundos)", min_value=5, value=30)
    max_activos_por_busqueda = st.number_input("Máx. activos a analizar por ciclo", min_value=1, value=10, help="Limita la cantidad para no saturar")

    iniciar = st.button("🚀 Iniciar búsqueda automática")
    detener = st.button("⏹️ Detener")

# ============================================================
# ÁREA PRINCIPAL: RESULTADOS
# ============================================================
if "activo_actual" not in st.session_state:
    st.session_state.activo_actual = None
if "ejecutando" not in st.session_state:
    st.session_state.ejecutando = False

# Contenedores para actualizar dinámicamente
placeholder_estado = st.empty()
placeholder_analisis = st.empty()
placeholder_grafico = st.empty()  # Si quieres mostrar velas

if iniciar:
    if not email or not password:
        st.error("Ingresa email y contraseña")
    else:
        st.session_state.ejecutando = True
        # Intentar conectar (el provider se conecta automáticamente al crearse)
        try:
            provider = get_provider(email, password)
            if not provider.conectado:
                st.error("No se pudo conectar a IQ Option. Revisa credenciales.")
                st.session_state.ejecutando = False
        except Exception as e:
            st.error(f"Error de conexión: {e}")
            st.session_state.ejecutando = False

# Bucle principal (se ejecuta mientras el estado sea True)
while st.session_state.ejecutando:
    with placeholder_estado.container():
        st.info(f"🔄 Buscando activos OTC ({tipo_activo})...")
        st.caption(f"Próximo análisis en {intervalo_analisis} segundos")

    # Realizar búsqueda
    provider = get_provider(email, password)
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

            # Aquí podrías mostrar un gráfico con las velas
            # if 'velas' in resultado:
            #     mostrar_grafico(resultado['velas'])

        # Aquí puedes agregar lógica de entrada automática
        # Ejemplo: if resultado['sentimiento'] == "CALL": provider.api.buy(1, resultado['activo'], "call", 1)
    else:
        with placeholder_analisis.container():
            st.warning("😕 No se encontró ningún activo con condiciones favorables en este ciclo")

    # Esperar el intervalo antes de la siguiente búsqueda
    for i in range(intervalo_analisis, 0, -1):
        if not st.session_state.ejecutando:
            break
        placeholder_estado.caption(f"Próximo análisis en {i} segundos...")
        time.sleep(1)

    # Verificar si el usuario detuvo
    if detener:
        st.session_state.ejecutando = False
        break

if not st.session_state.ejecutando and 'provider' in locals():
    st.info("Búsqueda detenida. Presiona 'Iniciar' para reanudar.")
