# aplicacion.py
import streamlit as st
import pandas as pd
import numpy as np
import time
import subprocess
import os
import pickle
from datetime import datetime
from iqoptionapi.stable_api import IQ_Option
from data_provider import EstrategiaAvanzada

# ========== CONFIGURACIÓN ==========
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

def obtener_activos_otc_desde_api():
    """
    Obtiene dinámicamente la lista de activos OTC disponibles desde IQ Option.
    Usa las credenciales de Secrets (descarga) o las de sesión según contexto.
    """
    try:
        # Para obtener activos, usamos Secrets (es más simple y no requiere sesión activa)
        email = os.environ.get('IQ_EMAIL')
        password = os.environ.get('IQ_PASSWORD')
        
        if not email or not password:
            # Si no hay Secrets, intentamos con las credenciales de sesión (si existen)
            if 'iq_api' in st.session_state:
                api_temp = st.session_state.iq_api
            else:
                st.error("No hay credenciales disponibles para obtener activos")
                return []
        else:
            api_temp = IQ_Option(email, password)
            api_temp.connect()
        
        api_temp.update_ACTIVES_OPCODE()
        activos_dict = api_temp.get_all_ACTIVES_OPCODE()
        
        # Filtrar solo activos OTC
        activos_otc = [nombre for nombre in activos_dict.keys() if "-OTC" in nombre]
        
        # No cerramos sesión si es la misma de st.session_state
        if email and password and 'iq_api' not in st.session_state:
            api_temp.logout()
            
        return activos_otc
    
    except Exception as e:
        st.error(f"Error al obtener activos OTC: {e}")
        return []

# ========== VERIFICACIÓN INICIAL (Descarga y Entrenamiento) ==========
st.set_page_config(layout="wide")
st.title("🤖 Indicador Inteligente IQ Option con IA")

# Verificar Secrets (para descarga de datos)
secrets_ok = False
if 'IQ_EMAIL' in st.secrets and 'IQ_PASSWORD' in st.secrets:
    os.environ['IQ_EMAIL'] = st.secrets['IQ_EMAIL']
    os.environ['IQ_PASSWORD'] = st.secrets['IQ_PASSWORD']
    secrets_ok = True
    st.success("✅ Credenciales de Secrets configuradas correctamente.")
else:
    st.warning("⚠️ Secrets no configurados. La descarga automática de datos no funcionará.")

# 1. Verificar y descargar datos si es necesario (usa Secrets)
if secrets_ok and not os.path.exists(CSV_FILE):
    st.info("📥 Archivo de datos no encontrado. Iniciando descarga desde IQ Option...")
    if not ejecutar_script('descargador_iq.py', "Descarga de datos"):
        st.stop()
elif not os.path.exists(CSV_FILE):
    st.error("❌ No hay archivo de datos y no hay Secrets para descargarlo. Sube manualmente el CSV.")
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

# 3. Cargar modelo y scaler en session_state
try:
    with open(MODELO_FILE, 'rb') as f:
        st.session_state['modelo'] = pickle.load(f)
    with open(SCALER_FILE, 'rb') as f:
        st.session_state['scaler'] = pickle.load(f)
    st.success("✅ Modelo cargado correctamente en la sesión.")
except Exception as e:
    st.error(f"❌ Error al cargar modelo: {e}")
    st.stop()

# ========== INTERFAZ DE LOGIN DEL USUARIO (para operar) ==========
with st.sidebar:
    st.header("🔐 Conexión a IQ Option")
    
    if 'usuario_conectado' not in st.session_state:
        st.session_state.usuario_conectado = False
    
    if not st.session_state.usuario_conectado:
        email_user = st.text_input("Email", key="email_user")
        password_user = st.text_input("Contraseña", type="password", key="password_user")
        tipo_cuenta = st.selectbox("Tipo de cuenta", ["PRACTICE", "REAL"])
        
        if st.button("Conectar"):
            with st.spinner("Conectando..."):
                try:
                    api_user = IQ_Option(email_user, password_user)
                    check, reason = api_user.connect()
                    if check:
                        api_user.change_balance(tipo_cuenta)
                        st.session_state.iq_api = api_user
                        st.session_state.usuario_conectado = True
                        st.session_state.email_user = email_user
                        st.session_state.tipo_cuenta = tipo_cuenta
                        st.success("✅ Conectado correctamente")
                        st.rerun()
                    else:
                        st.error(f"Error: {reason}")
                except Exception as e:
                    st.error(f"Error: {e}")
    else:
        st.success(f"Conectado como: {st.session_state.email_user}")
        st.info(f"Cuenta: {st.session_state.tipo_cuenta}")
        if st.button("Desconectar"):
            if 'iq_api' in st.session_state:
                st.session_state.iq_api.logout()
            st.session_state.usuario_conectado = False
            st.rerun()

# ========== CLASES DEL BOT (adaptadas para usar la sesión del usuario) ==========

class DataManager:
    """Gestor de datos que obtiene activos dinámicamente y velas reales usando la sesión del usuario"""
    
    def __init__(self):
        self.historial = {}
        self.ultima_actualizacion_activos = 0
        self.activos_cache = []
        
    def obtener_activos_disponibles(self):
        """Obtiene activos OTC usando la sesión activa del usuario o Secrets como fallback"""
        ahora = time.time()
        if ahora - self.ultima_actualizacion_activos > 300:  # 5 minutos
            if st.session_state.usuario_conectado and 'iq_api' in st.session_state:
                # Usar sesión del usuario
                api = st.session_state.iq_api
                try:
                    api.update_ACTIVES_OPCODE()
                    activos_dict = api.get_all_ACTIVES_OPCODE()
                    self.activos_cache = [nombre for nombre in activos_dict.keys() if "-OTC" in nombre]
                except:
                    # Fallback a método estático
                    self.activos_cache = obtener_activos_otc_desde_api()
            else:
                # Fallback a Secrets
                self.activos_cache = obtener_activos_otc_desde_api()
            
            self.ultima_actualizacion_activos = ahora
            
            # Inicializar historial para nuevos activos
            for activo in self.activos_cache:
                if activo not in self.historial:
                    self.historial[activo] = []
        
        return self.activos_cache

    def obtener_velas(self, activo, count=VELAS_HISTORICAS):
        """
        Obtiene velas reales de IQ Option usando la sesión del usuario si está conectado.
        Si no, usa simulación (modo offline/demo).
        """
        if st.session_state.usuario_conectado and 'iq_api' in st.session_state:
            # MODO REAL: Obtener velas de la API
            try:
                api = st.session_state.iq_api
                end_from = int(time.time())
                velas = api.get_candles(activo, 60, count, end_from)
                
                if velas:
                    df = pd.DataFrame(velas)
                    df = df[['from', 'open', 'max', 'min', 'close', 'volume']]
                    df.columns = ['from', 'open', 'high', 'low', 'close', 'volume']
                    # Guardar en historial
                    self.historial[activo] = df
                    return df
                else:
                    # Si falla, usar simulación como fallback
                    return self._simular_velas(activo, count)
            except Exception as e:
                st.warning(f"Error obteniendo velas reales de {activo}: {e}. Usando simulación.")
                return self._simular_velas(activo, count)
        else:
            # MODO SIMULACIÓN (para pruebas sin conexión)
            return self._simular_velas(activo, count)
    
    def _simular_velas(self, activo, count):
        """Genera velas simuladas (para desarrollo/pruebas)"""
        if activo not in self.historial or len(self.historial[activo]) < count:
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

class IQOptionBot:
    """Bot principal - ANALIZA TODOS LOS ACTIVOS OTC DISPONIBLES"""
    
    def __init__(self):
        self.data_manager = DataManager()
        self.estrategia = EstrategiaAvanzada(
            modelo_path=MODELO_FILE,
            scaler_path=SCALER_FILE,
            ventana=20
        )
        self.historial_analisis = []
        self.ultima_senal = None
        self.contador_ciclos = 0

    def ejecutar_ciclo(self):
        """Ejecuta un ciclo de análisis sobre TODOS los activos OTC disponibles"""
        
        # Obtener activos disponibles en tiempo real
        activos_a_analizar = self.data_manager.obtener_activos_disponibles()
        
        if not activos_a_analizar:
            return
        
        self.contador_ciclos += 1
        
        # Analizar cada activo disponible
        for activo in activos_a_analizar:
            try:
                velas = self.data_manager.obtener_velas(activo)
                analisis = self.estrategia.analizar_activo(velas)
                analisis['activo'] = activo
                analisis['timestamp'] = datetime.now().strftime('%H:%M:%S')
                analisis['ciclo'] = self.contador_ciclos

                # Agregar al historial
                self.historial_analisis.append(analisis)
                if len(self.historial_analisis) > 50:
                    self.historial_analisis.pop(0)

                # Si es buena señal, guardar como última
                if analisis['es_bueno']:
                    self.ultima_senal = analisis
                    # Aquí iría la ejecución de orden real (si el usuario está conectado)
                    if st.session_state.usuario_conectado:
                        self._ejecutar_orden_real(analisis)
                    
            except Exception as e:
                print(f"Error analizando {activo}: {e}")
                continue

    def _ejecutar_orden_real(self, analisis):
        """Ejecuta una orden real usando la sesión del usuario"""
        try:
            api = st.session_state.iq_api
            direccion = analisis['sentimiento'].lower()
            monto = 1  # Monto fijo por ahora, podrías hacerlo configurable
            
            # Ejemplo para binarias de 1 minuto
            status, order_id = api.buy(monto, analisis['activo'], direccion, 1)
            
            if status:
                st.success(f"✅ Orden ejecutada: {analisis['activo']} {direccion.upper()} - ID: {order_id}")
            else:
                st.error(f"❌ Error ejecutando orden")
        except Exception as e:
            st.error(f"Error en orden: {e}")

# ========== INICIALIZACIÓN DEL BOT ==========
if 'bot' not in st.session_state:
    st.session_state.bot = IQOptionBot()
    st.session_state.ultimo_segundo = -1

bot = st.session_state.bot

# ========== BUCLE PRINCIPAL ==========
placeholder = st.empty()

# Obtener el segundo actual
now = datetime.now()
segundo_actual = now.second

# Ejecutar ciclo solo en el segundo 58 (y solo si el usuario está conectado O si estamos en modo demo)
if segundo_actual == SEGUNDO_EJECUCION and st.session_state.ultimo_segundo != segundo_actual:
    bot.ejecutar_ciclo()
    st.session_state.ultimo_segundo = segundo_actual

# ========== INTERFAZ DE USUARIO ==========
with placeholder.container():
    # Cabecera con información
    col1, col2 = st.columns([3, 1])
    with col1:
        if st.session_state.usuario_conectado:
            st.markdown(f"## ⚡ **BOT ACTIVO - CONECTADO A IQ OPTION**")
        else:
            st.markdown(f"## 🔍 **BOT EN MODO DEMO (sin conexión)**")
    with col2:
        st.markdown(f"**{now.strftime('%Y-%m-%d %H:%M:%S')}**")
        st.markdown(f"**Ciclo #{bot.contador_ciclos}**")

    # Panel principal: dos columnas
    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("📊 Últimos análisis")
        
        # Obtener activos disponibles para mostrar
        activos_disponibles = bot.data_manager.obtener_activos_disponibles()
        st.metric("Activos OTC detectados", len(activos_disponibles))
        
        # Mostrar tabla con últimos 10 análisis
        if bot.historial_analisis:
            df_ultimos = pd.DataFrame(bot.historial_analisis[-10:])
            display_df = df_ultimos[['timestamp', 'activo', 'sentimiento', 'fuerza', 'prob_CALL', 'prob_PUT']].copy()
            display_df['fuerza'] = display_df['fuerza'].apply(lambda x: f"{x:.2%}")
            display_df['prob_CALL'] = display_df['prob_CALL'].apply(lambda x: f"{x:.2%}")
            display_df['prob_PUT'] = display_df['prob_PUT'].apply(lambda x: f"{x:.2%}")
            st.dataframe(display_df, use_container_width=True)
        else:
            st.info("Esperando análisis...")

    with col_right:
        st.subheader("🔔 Última señal")
        if bot.ultima_senal:
            s = bot.ultima_senal
            st.markdown(f"""
            - **Activo:** {s['activo']} - **{s['sentimiento']}**
            - **Probabilidad:** CALL {s['prob_CALL']:.2%} / PUT {s['prob_PUT']:.2%}
            - **Fuerza:** {s['fuerza']:.2%} - {s['magnitud_esperada']}
            - **Volumen (presión):** {s['volumen']:.2f}
            - **Tendencia:** {'Sí' if s['tiene_tendencia'] else 'No'}
            """)
            
            if s['es_bueno']:
                st.success("✅ SEÑAL FAVORABLE DETECTADA")
        else:
            st.info("Esperando primera señal...")

    # Mostrar lista de activos disponibles
    with st.expander("📋 Activos OTC disponibles actualmente"):
        if activos_disponibles:
            st.write(", ".join(activos_disponibles))
        else:
            st.write("No se pudieron obtener activos. Verifica conexión.")

# Auto-refresh cada segundo
st.markdown("""
    <meta http-equiv="refresh" content="1">
""", unsafe_allow_html=True)
