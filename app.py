# aplicacion.py
import streamlit as st
import pandas as pd
import numpy as np
import time
import pickle
import os
from datetime import datetime
from iqoptionapi.stable_api import IQ_Option
from data_provider import EstrategiaAvanzada

# ========== CONFIGURACIÓN ==========
SEGUNDO_EJECUCION = 58
VELAS_HISTORICAS = 50
ACTIVO_DESCARGAR = "EURUSD"
TIMEFRAME = 60  # 1 minuto
VELAS_POR_REQUEST = 1000
NUM_REQUESTS = 500  # Ajustable (500 = 500k velas)

# Archivos necesarios
MODELO_FILE = "modelo_xgb.pkl"
SCALER_FILE = "scaler.pkl"
CSV_FILE = "iqoption_data_EURUSD_60.csv"

# ========== FUNCIONES DE DESCARGA Y ENTRENAMIENTO ==========

def descargar_datos(api, activo, total_requests):
    """
    Descarga velas históricas usando la API ya conectada.
    Muestra progreso en Streamlit.
    Retorna el DataFrame con las velas.
    """
    todas_las_velas = []
    end_from = int(time.time())
    
    progreso = st.progress(0, text="Iniciando descarga...")
    
    for i in range(total_requests):
        to_time = end_from - i * VELAS_POR_REQUEST * TIMEFRAME
        try:
            velas = api.get_candles(activo, TIMEFRAME, VELAS_POR_REQUEST, to_time)
            if velas:
                df_batch = pd.DataFrame(velas)
                df_batch = df_batch[['from', 'open', 'max', 'min', 'close', 'volume']]
                df_batch.columns = ['from', 'open', 'high', 'low', 'close', 'volume']
                todas_las_velas.append(df_batch)
            
            # Actualizar progreso
            progreso.progress((i + 1) / total_requests, text=f"Descargando lote {i+1}/{total_requests}")
            time.sleep(0.3)
        except Exception as e:
            st.warning(f"Error en lote {i+1}: {e}")
            time.sleep(1)
    
    progreso.empty()
    
    if not todas_las_velas:
        return None
    
    df_final = pd.concat(todas_las_velas, ignore_index=True)
    df_final = df_final.drop_duplicates(subset=['from'])
    df_final = df_final.sort_values('from').reset_index(drop=True)
    return df_final

def entrenar_modelo_con_datos(df):
    """Entrena XGBoost y guarda modelo.pkl y scaler.pkl."""
    from sklearn.preprocessing import StandardScaler
    import xgboost as xgb
    from sklearn.metrics import accuracy_score
    
    # Crear target
    df['target'] = (df['close'].shift(-1) > df['close']).astype(int)
    df = df.dropna(subset=['target']).reset_index(drop=True)
    
    estrategia = EstrategiaAvanzada(modelo_path=None, scaler_path=None, ventana=20)
    
    features_list = []
    targets_list = []
    
    for i in range(20, len(df)):
        ventana_df = df.iloc[i-20:i][['open','high','low','close','volume']]
        feat = estrategia.calcular_features(ventana_df)
        if feat is not None:
            features_list.append(feat)
            targets_list.append(df.iloc[i]['target'])
    
    if len(features_list) < 100:
        raise ValueError("No hay suficientes muestras para entrenar.")
    
    X = pd.DataFrame(features_list)
    y = pd.Series(targets_list)
    
    split = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split], X.iloc[split:]
    y_train, y_test = y.iloc[:split], y.iloc[split:]
    
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    
    modelo = xgb.XGBClassifier(
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        random_state=42,
        n_jobs=-1,
        eval_metric='logloss',
        use_label_encoder=False
    )
    modelo.fit(X_train_scaled, y_train, eval_set=[(X_test_scaled, y_test)], verbose=False)
    
    y_pred = modelo.predict(X_test_scaled)
    acc = accuracy_score(y_test, y_pred)
    st.info(f"Precisión en validación: {acc:.4f}")
    
    with open(MODELO_FILE, 'wb') as f:
        pickle.dump(modelo, f)
    with open(SCALER_FILE, 'wb') as f:
        pickle.dump(scaler, f)
    
    return modelo, scaler

# ========== INTERFAZ DE LOGIN ==========
st.set_page_config(layout="wide")
st.title("🤖 Indicador Inteligente IQ Option con IA")

with st.sidebar:
    st.header("🔐 Conexión a IQ Option")
    
    if 'iq_api' not in st.session_state:
        st.session_state.iq_api = None
        st.session_state.usuario_conectado = False
    
    if not st.session_state.usuario_conectado:
        email_user = st.text_input("Email", key="email_login")
        password_user = st.text_input("Contraseña", type="password", key="password_login")
        tipo_cuenta = st.selectbox("Tipo de cuenta", ["PRACTICE", "REAL"])
        
        if st.button("Conectar"):
            with st.spinner("Conectando..."):
                api = IQ_Option(email_user, password_user)
                check, reason = api.connect()
                if check:
                    # Verificación adicional: intentar obtener balance
                    try:
                        api.change_balance(tipo_cuenta)
                        balance = api.get_balance()
                        st.session_state.iq_api = api
                        st.session_state.usuario_conectado = True
                        st.session_state.email_user = email_user
                        st.success(f"✅ Conectado. Balance: {balance}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al obtener balance: {e}")
                else:
                    st.error(f"Error de conexión: {reason}")
                    st.info("Verifica que tus credenciales sean correctas y que la cuenta sea válida.")
    else:
        st.success(f"Conectado como: {st.session_state.email_user}")
        if st.button("Desconectar"):
            if st.session_state.iq_api:
                st.session_state.iq_api.logout()
            st.session_state.iq_api = None
            st.session_state.usuario_conectado = False
            st.rerun()

# ========== VERIFICACIÓN DE MODELOS Y BOTÓN DE ENTRENAMIENTO ==========

modelos_existen = os.path.exists(MODELO_FILE) and os.path.exists(SCALER_FILE)

if not modelos_existen:
    if st.session_state.usuario_conectado:
        st.warning("⚠️ Los archivos del modelo de IA no existen. Debes descargar datos históricos y entrenar el modelo.")
        if st.button("📥 Descargar datos históricos y entrenar IA", type="primary"):
            with st.status("Iniciando proceso...", expanded=True) as status:
                status.update(label="Descargando datos...")
                df_descargado = descargar_datos(
                    st.session_state.iq_api,
                    ACTIVO_DESCARGAR,
                    NUM_REQUESTS
                )
                
                if df_descargado is None:
                    status.update(label="Error en la descarga", state="error")
                    st.stop()
                
                # Guardar CSV
                df_descargado.to_csv(CSV_FILE, index=False)
                status.update(label="Descarga completada. Entrenando modelo...")
                
                try:
                    modelo, scaler = entrenar_modelo_con_datos(df_descargado)
                    status.update(label="✅ Entrenamiento completado con éxito", state="complete")
                    st.success("Modelo guardado. La aplicación se recargará para usarlo.")
                    time.sleep(2)
                    st.rerun()
                except Exception as e:
                    status.update(label=f"Error en entrenamiento: {e}", state="error")
                    st.stop()
    else:
        st.info("🔌 Conéctate a IQ Option para poder descargar datos y entrenar el modelo.")
        st.stop()
else:
    st.success("✅ Modelo de IA cargado y listo para operar.")

# ========== CLASES DEL BOT ==========

class DataManager:
    def __init__(self):
        self.historial = {}
        self.ultima_actualizacion_activos = 0
        self.activos_cache = []
    
    def obtener_activos_disponibles(self):
        ahora = time.time()
        if ahora - self.ultima_actualizacion_activos > 300:
            if st.session_state.usuario_conectado and st.session_state.iq_api:
                api = st.session_state.iq_api
                try:
                    api.update_ACTIVES_OPCODE()
                    activos_dict = api.get_all_ACTIVES_OPCODE()
                    self.activos_cache = [nombre for nombre in activos_dict.keys() if "-OTC" in nombre]
                except Exception as e:
                    st.warning(f"Error actualizando activos: {e}")
                    self.activos_cache = []
            else:
                self.activos_cache = []
            self.ultima_actualizacion_activos = ahora
        return self.activos_cache
    
    def obtener_velas(self, activo, count=VELAS_HISTORICAS):
        if st.session_state.usuario_conectado and st.session_state.iq_api:
            try:
                api = st.session_state.iq_api
                end_from = int(time.time())
                velas = api.get_candles(activo, 60, count, end_from)
                if velas:
                    df = pd.DataFrame(velas)
                    df = df[['from', 'open', 'max', 'min', 'close', 'volume']]
                    df.columns = ['from', 'open', 'high', 'low', 'close', 'volume']
                    self.historial[activo] = df
                    return df
            except Exception as e:
                st.warning(f"Error obteniendo velas de {activo}, usando simulación: {e}")
        # Fallback a simulación
        return self._simular_velas(activo, count)
    
    def _simular_velas(self, activo, count):
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
    def __init__(self):
        self.data_manager = DataManager()
        self.estrategia = EstrategiaAvanzada(MODELO_FILE, SCALER_FILE, ventana=20)
        self.historial_analisis = []
        self.ultima_senal = None
        self.contador_ciclos = 0
    
    def ejecutar_ciclo(self):
        activos = self.data_manager.obtener_activos_disponibles()
        if not activos:
            return
        self.contador_ciclos += 1
        for activo in activos:
            try:
                velas = self.data_manager.obtener_velas(activo)
                analisis = self.estrategia.analizar_activo(velas)
                analisis['activo'] = activo
                analisis['timestamp'] = datetime.now().strftime('%H:%M:%S')
                self.historial_analisis.append(analisis)
                if len(self.historial_analisis) > 50:
                    self.historial_analisis.pop(0)
                if analisis['es_bueno']:
                    self.ultima_senal = analisis
                    # Aquí podrías ejecutar la orden real
                    # self._ejecutar_orden(analisis)
            except Exception as e:
                print(f"Error en {activo}: {e}")
    
    # def _ejecutar_orden(self, analisis):
    #     pass

# ========== INICIALIZAR BOT ==========
if 'bot' not in st.session_state:
    st.session_state.bot = IQOptionBot()
    st.session_state.ultimo_segundo = -1

bot = st.session_state.bot

# ========== BUCLE PRINCIPAL (se ejecuta en cada refresh) ==========
now = datetime.now()
segundo_actual = now.second

if segundo_actual == SEGUNDO_EJECUCION and st.session_state.ultimo_segundo != segundo_actual:
    bot.ejecutar_ciclo()
    st.session_state.ultimo_segundo = segundo_actual

# ========== INTERFAZ DE USUARIO ==========
col1, col2 = st.columns([3,1])
with col1:
    if st.session_state.usuario_conectado:
        st.markdown(f"## ⚡ **BOT ACTIVO - CONECTADO**")
    else:
        st.markdown(f"## 🔍 **BOT EN MODO DEMO (sin conexión)**")
with col2:
    st.markdown(f"**{now.strftime('%Y-%m-%d %H:%M:%S')}**")
    st.markdown(f"**Ciclo #{bot.contador_ciclos}**")

col_left, col_right = st.columns(2)

with col_left:
    st.subheader("📊 Últimos análisis")
    activos = bot.data_manager.obtener_activos_disponibles()
    st.metric("Activos OTC", len(activos))
    if bot.historial_analisis:
        df_hist = pd.DataFrame(bot.historial_analisis[-10:])
        df_display = df_hist[['timestamp','activo','sentimiento','fuerza','prob_CALL','prob_PUT']].copy()
        df_display['fuerza'] = df_display['fuerza'].apply(lambda x: f"{x:.2%}")
        df_display['prob_CALL'] = df_display['prob_CALL'].apply(lambda x: f"{x:.2%}")
        df_display['prob_PUT'] = df_display['prob_PUT'].apply(lambda x: f"{x:.2%}")
        st.dataframe(df_display, use_container_width=True)
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
        - **Volumen:** {s['volumen']:.2f}
        - **Tendencia:** {'Sí' if s['tiene_tendencia'] else 'No'}
        """)
        if s['es_bueno']:
            st.success("✅ SEÑAL FAVORABLE")
    else:
        st.info("Esperando señal...")

with st.expander("📋 Activos OTC detectados"):
    if activos:
        st.write(", ".join(activos))
    else:
        st.write("No hay activos disponibles.")

# Auto-refresh cada segundo
st.markdown("""
    <meta http-equiv="refresh" content="1">
""", unsafe_allow_html=True)
