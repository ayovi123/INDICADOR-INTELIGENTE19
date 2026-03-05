import streamlit as st
from datetime import datetime
from data_provider import (
    get_current_vela,
    get_historical_velas,
    detectar_trampa,
    calcular_probabilidad_y_fuerza
)
from streamlit_autorefresh import st_autorefresh

# Configuración de la página
st.set_page_config(page_title="Señales 1 minuto OTC", layout="centered")
st.title("📈 Señal para vela de 1 minuto (OTC)")
st.markdown("Esperando la próxima señal...")

# Auto‑refresh cada 60 segundos (para actualizar en el segundo 58)
st_autorefresh(interval=60 * 1000, key="autorefresh")

# Inicializar variables de estado
if 'historico' not in st.session_state:
    st.session_state.historico = get_historical_velas(minutes=20)
    st.session_state.ultima_senal = ""
    st.session_state.minuto_generado = -1

# Obtener hora actual
now = datetime.now()
segundo = now.second
minuto = now.minute

# Mostrar hora en la barra lateral
st.sidebar.write(f"🕒 Hora actual: {now.strftime('%H:%M:%S')}")

# Generar nueva señal solo si estamos cerca del segundo 58 y no se generó ya en este minuto
if (58 <= segundo <= 59 or segundo == 0) and st.session_state.minuto_generado != minuto:
    # Obtener la última vela (la que acaba de cerrar)
    vela_actual = get_current_vela()

    # Actualizar histórico
    st.session_state.historico.append(vela_actual)
    if len(st.session_state.historico) > 20:
        st.session_state.historico.pop(0)

    # Detectar trampas
    trampa = detectar_trampa(vela_actual, st.session_state.historico[:-1])

    # Calcular probabilidades y fuerza
    prob_compra, prob_venta, fuerza = calcular_probabilidad_y_fuerza(vela_actual, st.session_state.historico[:-1])

    # Decidir dirección
    direccion = None
    probabilidad = 0
    umbral = 62

    if trampa:
        if "VENTA" in trampa:
            direccion = "VENTA"
            probabilidad = prob_venta
        elif "COMPRA" in trampa:
            direccion = "COMPRA"
            probabilidad = prob_compra
    else:
        if prob_compra > umbral and prob_compra > prob_venta:
            direccion = "COMPRA"
            probabilidad = prob_compra
        elif prob_venta > umbral and prob_venta > prob_compra:
            direccion = "VENTA"
            probabilidad = prob_venta

    # Si ninguna supera el umbral, elegir la mayor
    if direccion is None:
        if prob_compra > prob_venta:
            direccion = "COMPRA"
            probabilidad = prob_compra
        else:
            direccion = "VENTA"
            probabilidad = prob_venta

    # Formatear mensaje
    arriba_abajo = "MÁS ARRIBA" if direccion == "COMPRA" else "MÁS ABAJO"
    senal = f"{direccion} → Probabilidad {probabilidad:.0f}% / 100. Fuerza detectada: {fuerza:.2f}. Pronóstico: vela siguiente terminará {arriba_abajo}."
    if probabilidad > 75:
        senal += " ¡PRECAUCIÓN: vela siguiente podría ser de gran tamaño (alto potencial de movimiento fuerte)!"
    if trampa:
        senal += f"\n\n⚠️ **Trampa detectada:** {trampa}"

    # Guardar en sesión
    st.session_state.ultima_senal = senal
    st.session_state.minuto_generado = minuto

# Mostrar la última señal generada
if st.session_state.ultima_senal:
    st.markdown("## 🔔 Última señal")
    st.success(st.session_state.ultima_senal)
else:
    st.info("Aún no hay señales. Espera al segundo 58 del minuto actual.")

# Opcional: mostrar histórico de velas
with st.expander("📊 Ver últimas velas (histórico)"):
    st.write(st.session_state.historico)
