# aplicacion.py
import streamlit as st
import pandas as pd
import numpy as np
import time
import subprocess
import os
import pickle
from datetime import datetime
from data_provider import EstrategiaAvanzada

# ========== CONFIGURACIÓN ==========
ACTIVOS = [
    "EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "AUDUSD-OTC",
    "EURJPY-OTC", "GBPJPY-OTC", "USDCAD-OTC", "USDCHF-OTC"
]
MAX_MINUTOS_FIJADO = 10
SEGUNDO_EJECUCION = 58
VELAS_HISTORICAS = 50

# Archivos necesarios
CSV_FILE = "iqoption_data_EURUSD_60.csv"
MODELO_FILE = "modelo_xgb.pkl"
SCALER_FILE = "scaler.pkl"

# ========== FUNCIONES AUXILIARES ==========
def ejecutar_script(script_name, mensaje):
    """Ejecuta un script Python y muestra el resultado en Streamlit."""
    with st.spinner(f"{mensaje}..."):
        result = subprocess.run(['python', script_name], capture_output=True, text=True)
        if result.returncode == 0:
            st.success(f"{mensaje} completado.")
            with st.expander(f"Salida de {script_name}"):
                st.text(result.stdout)
            return True
        else:
            st.error(f"Error en {mensaje}: {result.stderr}")
            return False

# ========== VERIFICACIÓN INICIAL ==========
st.set_page_config(layout="wide")
st.title("🤖 Indicador Inteligente IQ Option con IA")

# 1. Verificar y descargar datos si es necesario
if not os.path.exists(CSV_FILE):
    st.info("📥 Archivo de datos no encontrado. Iniciando descarga desde IQ Option...")
    if not ejecutar_script('descargador_iq.py', "Descarga de datos"):
        st.stop()
else:
    st.success("✅ Archivo de datos encontrado.")

# 2. Verificar y entrenar modelo si es necesario
if not (os.path.exists(MODELO_FILE) and os.path.exists(SCALER_FILE)):
    st.info("🧠 Modelo no encontrado. Iniciando entrenamiento de IA...")
    if not ejecutar_script('entrenador_ia.py', "Entrenamiento de IA"):
        st.stop()
else:
    st.success("✅ Modelo y scaler encontrados.")

# 3. Cargar modelo y scaler en session_state (opcional, pero útil)
try:
    with open(MODELO_FILE, 'rb') as f:
        st.session_state['modelo'] = pickle.load(f)
    with open(SCALER_FILE, 'rb') as f:
        st.session_state['scaler'] = pickle.load(f)
    st.success("✅ Modelo cargado correctamente en la sesión.")
except Exception as e:
    st.error(f"❌ Error al cargar modelo: {e}")
    st.stop()

# ========== CLASES DEL BOT (tomadas de tu app.py original, adaptadas) ==========

class DataManager:
    """Gestor de datos en tiempo real (simulado o real)"""
    def __init__(self):
        self.historial = {activo: [] for activo in ACTIVOS}

    def obtener_velas(self, activo, count=VELAS_HISTORICAS):
        """Simula obtención de velas (reemplazar con API real)"""
        if len(self.historial[activo]) < count:
            # Generar datos iniciales simulados
            precio = np.random.uniform(1.0, 1.2)
            velas = []
            for _ in range(count):
                open_p = precio
                close_p = open_p + np.random.normal(0, 0.001)
                high_p = max(open_p, close_p) + np.random.uniform(0, 0.0005)
                low_p = min(open_p, close_p) - np.random.uniform(0, 0.0005)
                volume = np.random.randint(100, 1000)
                velas.append([open_p, high_p, low_p, close_p, volume])
                precio = close_p
            df = pd.DataFrame(velas, columns=['open','high','low','close','volume'])
            self.historial[activo] = df
        else:
            df = self.historial[activo].tail(count).reset_index(drop=True)
        return df

    def actualizar_vela(self, activo, nueva_vela):
        """Agrega una nueva vela al historial"""
        df_nuevo = pd.DataFrame([nueva_vela])
        self.historial[activo] = pd.concat([self.historial[activo], df_nuevo], ignore_index=True)
        if len(self.historial[activo]) > VELAS_HISTORICAS:
            self.historial[activo] = self.historial[activo].iloc[-VELAS_HISTORICAS:].reset_index(drop=True)

class IQOptionBot:
    """Bot principal que utiliza la IA para generar señales"""
    def __init__(self):
        self.data_manager = DataManager()
        # La estrategia cargará automáticamente los archivos .pkl ya existentes
        self.estrategia = EstrategiaAvanzada(
            modelo_path=MODELO_FILE,
            scaler_path=SCALER_FILE,
            ventana=20
        )
        self.activo_fijado = None
        self.minutos_sin_senal = 0
        self.historial_analisis = []
        self.ultima_senal = None

    def ejecutar_ciclo(self):
        """Ejecuta un ciclo de análisis (llamado cada segundo)"""
        if self.activo_fijado is not None:
            velas_fijado = self.data_manager.obtener_velas(self.activo_fijado)
            liberado = self._liberar_si_corresponde(velas_fijado)
            if liberado:
                activos_a_analizar = ACTIVOS
            else:
                activos_a_analizar = [self.activo_fijado]
        else:
            activos_a_analizar = ACTIVOS

        for activo in activos_a_analizar:
            velas = self.data_manager.obtener_velas(activo)
            analisis = self.estrategia.analizar_activo(velas)
            analisis['activo'] = activo
            analisis['timestamp'] = datetime.now().strftime('%H:%M:%S')

            self.historial_analisis.append(analisis)
            if len(self.historial_analisis) > 20:
                self.historial_analisis.pop(0)

            if analisis['es_bueno']:
                self.ultima_senal = analisis
                if self.activo_fijado is None and analisis['tiene_tendencia']:
                    self.activo_fijado = activo
                    self.minutos_sin_senal = 0
                # Aquí se ejecutaría la orden real
                self._ejecutar_orden(analisis)
            # else: sin acción

    def _liberar_si_corresponde(self, velas):
        if self.activo_fijado is None:
            return False
        analisis = self.estrategia.analizar_activo(velas)
        liberar = False
        if not analisis['tiene_tendencia']:
            liberar = True
        elif analisis['fuerza'] < self.estrategia.umbral_fuerza * 0.7:
            liberar = True
        elif not analisis['es_bueno']:
            self.minutos_sin_senal += 1
            if self.minutos_sin_senal >= MAX_MINUTOS_FIJADO:
                liberar = True
        else:
            self.minutos_sin_senal = 0

        if liberar:
            self.activo_fijado = None
            self.minutos_sin_senal = 0
            return True
        return False

    def _ejecutar_orden(self, analisis):
        """Simula la ejecución de una orden (reemplazar con API real)"""
        # En producción aquí se conectaría a IQ Option para colocar la operación
        pass

# ========== INICIALIZACIÓN DEL BOT EN SESSION STATE ==========
if 'bot' not in st.session_state:
    st.session_state.bot = IQOptionBot()
    st.session_state.ultimo_segundo = -1

bot = st.session_state.bot

# ========== BUCLE PRINCIPAL DE STREAMLIT (se ejecuta en cada refresh) ==========
# Usamos un placeholder para actualizar la UI en tiempo real
placeholder = st.empty()

# Obtener el segundo actual
now = datetime.now()
segundo_actual = now.second

# Ejecutar ciclo solo en el segundo 58 (para evitar sobrecarga)
if segundo_actual == SEGUNDO_EJECUCION and st.session_state.ultimo_segundo != segundo_actual:
    bot.ejecutar_ciclo()
    st.session_state.ultimo_segundo = segundo_actual

# ========== CONSTRUCCIÓN DE LA INTERFAZ ==========
with placeholder.container():
    # Cabecera con estado de fijación
    col1, col2 = st.columns([3, 1])
    with col1:
        if bot.activo_fijado:
            st.markdown(f"## ⚡ **FIJADO EN: {bot.activo_fijado}**")
        else:
            st.markdown("## 🔍 **BUSCANDO ACTIVOS...**")
    with col2:
        st.markdown(f"**{now.strftime('%Y-%m-%d %H:%M:%S')}**")

    # Panel de análisis actual e historial
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("📊 Análisis en curso")
        if bot.historial_analisis:
            ultimo = bot.historial_analisis[-1]
            st.metric("Activo", ultimo['activo'])
            st.metric("Señal", ultimo['sentimiento'])
            st.metric("Fuerza", f"{ultimo['fuerza']:.2%}")
            st.metric("Probabilidad CALL", f"{ultimo['prob_CALL']:.2%}")
            st.metric("Probabilidad PUT", f"{ultimo['prob_PUT']:.2%}")
        else:
            st.info("Esperando datos...")

    with col_right:
        st.subheader("📜 Historial de análisis")
        if bot.historial_analisis:
            df_hist = pd.DataFrame(bot.historial_analisis[-10:])[['timestamp', 'activo', 'sentimiento', 'fuerza']]
            df_hist['fuerza'] = df_hist['fuerza'].apply(lambda x: f"{x:.2%}")
            st.dataframe(df_hist, use_container_width=True)
        else:
            st.info("Sin historial aún.")

    # Pie con última señal detallada
    st.subheader("🔔 Última señal")
    if bot.ultima_senal:
        s = bot.ultima_senal
        st.markdown(f"""
        - **Activo:** {s['activo']} - {s['sentimiento']}
        - **Probabilidad:** CALL {s['prob_CALL']:.2%} / PUT {s['prob_PUT']:.2%}
        - **Fuerza:** {s['fuerza']:.2%} - {s['magnitud_esperada']}
        - **Volumen (presión):** {s['volumen']:.2f}
        - **Tendencia:** {'Sí' if s['tiene_tendencia'] else 'No'}
        """)
    else:
        st.info("Esperando primera señal...")

# Auto-refresh cada segundo para mantener la UI actualizada
st.markdown("""
    <meta http-equiv="refresh" content="1">
""", unsafe_allow_html=True)

# Nota: el meta refresh fuerza la recarga de la página cada segundo,
# lo que permite que el bot verifique el segundo actual y ejecute ciclos.
# Es una solución simple; alternativamente se puede usar st_autorefresh de streamlit-autorefresh.
