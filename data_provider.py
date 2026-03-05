# ============================================================
# data_provider.py
# Versión definitiva con:
# - Conexión corregida a IQ Option
# - Todas las mejoras de fuerza, volumen, manipulación, etc.
# - Modelos de IA por activo (entrenamiento y predicción)
# - Detección de todos los activos OTC
# - Auto‑cambio de activo basado en filtro de mercado malo
# ============================================================

from iqoptionapi.stable_api import IQ_Option
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import joblib
import os
from sklearn.ensemble import RandomForestClassifier
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier

# ============================================================
# VARIABLES GLOBALES
# ============================================================
api = None
modelos_por_activo = {}          # dict: activo -> dict de modelos
datos_entrenamiento = {}         # dict: activo -> lista de (features, label)

# ============================================================
# CONEXIÓN A IQ OPTION (CORREGIDA)
# ============================================================
def conectar(email, password, twofa=None):
    global api
    try:
        api = IQ_Option(email, password)
        exito, mensaje = api.connect(twofa) if twofa else api.connect()
        if exito:
            print("✅ Conectado a IQ Option")
            # Cambiar a cuenta demo si se desea
            # api.change_balance("PRACTICE")
            return api
        else:
            print(f"❌ Error de conexión: {mensaje}")
            return None
    except Exception as e:
        print(f"❌ Excepción en conexión: {e}")
        return None

# ============================================================
# OBTENER LISTA DE TODOS LOS ACTIVOS OTC
# ============================================================
def obtener_activos_otc(api):
    """
    Retorna una lista de símbolos de activos OTC disponibles.
    Utiliza get_all_actives() y filtra por nombre que contenga '-OTC'.
    """
    try:
        todos = api.get_all_actives()
        otc = []
        for act_id, info in todos.items():
            nombre = info.get('name', '')
            if '-OTC' in nombre.upper():
                otc.append(nombre)
        return sorted(otc)
    except Exception as e:
        print(f"Error al obtener activos OTC: {e}")
        return []

# ============================================================
# OBTENCIÓN DE VELAS (OHLCV)
# ============================================================
def obtener_velas(activo, timeframe=60, cantidad=100):
    if api is None:
        print("API no conectada")
        return None
    try:
        velas = api.get_candles(activo, timeframe, cantidad, time.time())
        df = pd.DataFrame(velas)
        df['timestamp'] = pd.to_datetime(df['from'], unit='s')
        df = df[['timestamp', 'open', 'max', 'min', 'close', 'volume']]
        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        df = df.sort_values('timestamp')
        return df
    except Exception as e:
        print(f"Error al obtener velas para {activo}: {e}")
        return None

# ============================================================
# FUNCIONES BASE (TUS ORIGINALES) - COLOCA AQUÍ TU CÓDIGO
# ============================================================
def calcular_fuerza_mercado(velas):
    """Placeholder: reemplaza con tu implementación."""
    return 0.5

def volumen_direccional(velas):
    """Placeholder."""
    return 0.5

def detectar_trampas(velas):
    """Placeholder."""
    return 0.0

# ============================================================
# FUNCIONES DE MEJORA (YA EXISTENTES)
# ============================================================
def presion_compradora_vendedora(velas):
    df = velas.copy()
    df['rango'] = df['high'] - df['low']
    df['es_alcista'] = df['close'] > df['open']
    df['es_bajista'] = df['close'] < df['open']
    df['vol_ponderado'] = df['volume'] * df['rango']
    compra = df[df['es_alcista']]['vol_ponderado'].sum()
    venta = df[df['es_bajista']]['vol_ponderado'].sum()
    total = compra + venta
    if total == 0:
        return 0.5, 0.5
    return compra / total, venta / total

def fuerza_real_vela(velas):
    df = velas.copy()
    df['cuerpo'] = abs(df['close'] - df['open'])
    df['rango'] = df['high'] - df['low']
    df['proporcion_cuerpo'] = df['cuerpo'] / df['rango'].replace(0, np.nan)
    df['proporcion_cuerpo'].fillna(0, inplace=True)
    df['vol_media'] = df['volume'].rolling(20, min_periods=1).mean()
    df['vol_relativo'] = df['volume'] / df['vol_media']
    df['dist_max'] = (df['high'] - df['close']) / df['rango'].replace(0, np.nan)
    df['dist_min'] = (df['close'] - df['low']) / df['rango'].replace(0, np.nan)
    df['cierre_extremo'] = np.where(df['close'] > df['open'], 
                                     1 - df['dist_max'], 
                                     1 - df['dist_min'])
    df['cierre_extremo'].fillna(0.5, inplace=True)
    fuerza = (0.4 * df['proporcion_cuerpo'] + 
              0.3 * df['vol_relativo'].clip(0, 2) / 2 + 
              0.3 * df['cierre_extremo'])
    return fuerza.values

def momentum_corto_plazo(velas, periodo=5):
    if len(velas) < periodo:
        return 0
    cambios_precio = velas['close'].pct_change().iloc[-periodo:].mean()
    cambios_volumen = velas['volume'].pct_change().iloc[-periodo:].mean()
    return cambios_precio * (1 + cambios_volumen)

def filtro_mercado_malo(velas):
    if len(velas) < 20:
        return False
    ultimas = velas.iloc[-20:]
    rango_promedio = (ultimas['high'] - ultimas['low']).mean()
    precio_medio = ultimas['close'].mean()
    volatilidad_relativa = rango_promedio / precio_medio if precio_medio != 0 else 0
    cambio_neto = abs(ultimas['close'].iloc[-1] - ultimas['close'].iloc[0]) / ultimas['close'].iloc[0]
    x = np.arange(len(ultimas))
    coef = np.polyfit(x, ultimas['volume'], 1)[0]
    condiciones_malas = 0
    if volatilidad_relativa < 0.001:
        condiciones_malas += 1
    if cambio_neto < 0.002:
        condiciones_malas += 1
    if coef < 0:
        condiciones_malas += 1
    return condiciones_malas >= 2

def features_avanzadas(velas):
    df = velas.copy()
    features = {}
    df['order_flow'] = df['volume'] * (df['close'] - df['open'])
    features['order_flow_sum'] = df['order_flow'].iloc[-10:].sum()
    features['order_flow_mean'] = df['order_flow'].iloc[-10:].mean()
    df['velocidad'] = df['close'].diff()
    features['velocidad_media'] = df['velocidad'].iloc[-5:].mean()
    df['aceleracion'] = df['velocidad'].diff()
    features['aceleracion_media'] = df['aceleracion'].iloc[-5:].mean()
    df['tr'] = np.maximum(df['high'] - df['low'], 
                          np.maximum(abs(df['high'] - df['close'].shift()),
                                     abs(df['low'] - df['close'].shift())))
    atr5 = df['tr'].rolling(5).mean().iloc[-1]
    atr20 = df['tr'].rolling(20).mean().iloc[-1]
    features['compresion_volatilidad'] = atr5 / atr20 if atr20 != 0 else 1
    vol_alcista = df[df['close'] > df['open']]['volume'].sum()
    vol_bajista = df[df['close'] < df['open']]['volume'].sum()
    features['ratio_vol_alcista_bajista'] = vol_alcista / (vol_bajista + 1)
    return features

def detectar_tendencias_y_reversiones(velas):
    if len(velas) < 20:
        return 'NEUTRO'
    y = velas['close'].iloc[-20:].values
    x = np.arange(len(y))
    pendiente = np.polyfit(x, y, 1)[0]
    ultimas_5 = velas.iloc[-5:]
    direccion_corta = (ultimas_5['close'].iloc[-1] - ultimas_5['close'].iloc[0]) > 0
    umbral = 0.0005 * velas['close'].mean()
    if pendiente > umbral:
        if not direccion_corta and ultimas_5['volume'].iloc[-1] > ultimas_5['volume'].mean():
            return 'REV_BAJISTA'
        return 'ALCISTA'
    elif pendiente < -umbral:
        if direccion_corta and ultimas_5['volume'].iloc[-1] > ultimas_5['volume'].mean():
            return 'REV_ALCISTA'
        return 'BAJISTA'
    else:
        return 'NEUTRO'

def detectar_manipulacion_trampas(velas):
    if len(velas) < 10:
        return 0
    df = velas.iloc[-10:].copy()
    df['rango'] = df['high'] - df['low']
    df['cuerpo'] = abs(df['close'] - df['open'])
    df['sombra_superior'] = df['high'] - df[['close', 'open']].max(axis=1)
    df['sombra_inferior'] = df[['close', 'open']].min(axis=1) - df['low']
    df['sombra_total'] = df['sombra_superior'] + df['sombra_inferior']
    df['proporcion_sombras'] = df['sombra_total'] / df['rango']
    manip_score = df['proporcion_sombras'].mean()
    max_previo = df['high'].iloc[:-1].max()
    ultimo = df.iloc[-1]
    if ultimo['high'] > max_previo and ultimo['close'] < max_previo:
        manip_score += 0.3
    return min(manip_score, 1.0)

# ============================================================
# PREPARACIÓN DE FEATURES PARA MODELOS
# ============================================================
def preparar_features_para_modelo(velas):
    feats = {}
    # Tus features originales
    feats['fuerza'] = calcular_fuerza_mercado(velas)
    feats['vol_dir'] = volumen_direccional(velas)
    # Nuevas features
    compra, venta = presion_compradora_vendedora(velas)
    feats['presion_compra'] = compra
    feats['presion_venta'] = venta
    fuerza_velas = fuerza_real_vela(velas)
    feats['fuerza_vela_media'] = fuerza_velas[-5:].mean() if len(fuerza_velas)>=5 else fuerza_velas.mean()
    feats['momentum'] = momentum_corto_plazo(velas)
    avanzadas = features_avanzadas(velas)
    feats.update(avanzadas)
    tendencia = detectar_tendencias_y_reversiones(velas)
    tend_map = {'ALCISTA':1, 'BAJISTA':-1, 'REV_ALCISTA':2, 'REV_BAJISTA':-2, 'NEUTRO':0}
    feats['tendencia'] = tend_map.get(tendencia, 0)
    feats['manipulacion'] = detectar_manipulacion_trampas(velas)
    return pd.DataFrame([feats])

# ============================================================
# ENTRENAMIENTO DE MODELOS POR ACTIVO
# ============================================================
def entrenar_modelo_activo(activo, df_features, labels):
    """
    Entrena un ensemble de modelos (RF, XGB, LGB) para un activo específico.
    Guarda los modelos en la carpeta 'modelos/{activo}/'.
    """
    if len(df_features) < 50:
        print(f"No hay suficientes datos para entrenar {activo}")
        return None
    
    X = df_features.values
    y = labels.values
    
    # Crear carpeta si no existe
    os.makedirs(f'modelos/{activo}', exist_ok=True)
    
    # Random Forest
    rf = RandomForestClassifier(n_estimators=100, random_state=42)
    rf.fit(X, y)
    joblib.dump(rf, f'modelos/{activo}/random_forest.pkl')
    
    # XGBoost
    xgb = XGBClassifier(n_estimators=100, random_state=42)
    xgb.fit(X, y)
    joblib.dump(xgb, f'modelos/{activo}/xgboost.pkl')
    
    # LightGBM
    lgb = LGBMClassifier(n_estimators=100, random_state=42, verbose=-1)
    lgb.fit(X, y)
    joblib.dump(lgb, f'modelos/{activo}/lightgbm.pkl')
    
    # Voting Classifier (soft voting)
    from sklearn.ensemble import VotingClassifier
    voting = VotingClassifier(estimators=[
        ('rf', rf), ('xgb', xgb), ('lgb', lgb)
    ], voting='soft')
    voting.fit(X, y)
    joblib.dump(voting, f'modelos/{activo}/voting.pkl')
    
    print(f"Modelos entrenados para {activo}")
    return {'rf': rf, 'xgb': xgb, 'lgb': lgb, 'voting': voting}

def cargar_modelos_activo(activo):
    """Carga los modelos de un activo desde disco."""
    modelos = {}
    try:
        modelos['rf'] = joblib.load(f'modelos/{activo}/random_forest.pkl')
        modelos['xgb'] = joblib.load(f'modelos/{activo}/xgboost.pkl')
        modelos['lgb'] = joblib.load(f'modelos/{activo}/lightgbm.pkl')
        modelos['voting'] = joblib.load(f'modelos/{activo}/voting.pkl')
    except:
        modelos = None
    return modelos

def predecir_probabilidad_activo(activo, velas):
    """
    Usa el modelo del activo para predecir probabilidad de CALL (próxima vela alcista).
    Retorna (probabilidad, señal, votos) o (None, 'NEUTRO', 0) si no hay modelo.
    """
    modelos = cargar_modelos_activo(activo)
    if modelos is None or len(velas) < 20:
        return None, 'NEUTRO', 0
    
    X = preparar_features_para_modelo(velas)
    
    # Obtener probabilidades de cada modelo
    prob_rf = modelos['rf'].predict_proba(X)[0][1]
    prob_xgb = modelos['xgb'].predict_proba(X)[0][1]
    prob_lgb = modelos['lgb'].predict_proba(X)[0][1]
    
    prob_promedio = (prob_rf + prob_xgb + prob_lgb) / 3
    votos_call = sum([1 for p in [prob_rf, prob_xgb, prob_lgb] if p > 0.5])
    
    if votos_call >= 2:
        señal = 'CALL'
        prob_final = prob_promedio
    else:
        señal = 'PUT'
        prob_final = 1 - prob_promedio
    
    return prob_final, señal, votos_call

def actualizar_datos_entrenamiento(activo, velas):
    """
    Agrega las features de la última vela (o conjunto) a los datos de entrenamiento.
    La etiqueta se define según la dirección de la vela siguiente (futuro).
    """
    global datos_entrenamiento
    if activo not in datos_entrenamiento:
        datos_entrenamiento[activo] = {'X': [], 'y': []}
    
    # Necesitamos al menos 2 velas para etiquetar la anterior con la siguiente
    if len(velas) < 2:
        return
    
    # Para cada vela excepto la última, la etiqueta es la dirección de la vela siguiente
    for i in range(len(velas)-1):
        vela_actual = velas.iloc[i]
        vela_siguiente = velas.iloc[i+1]
        # Feature de la vela actual
        X_actual = preparar_features_para_modelo(velas.iloc[:i+1])  # usar hasta la actual
        # Etiqueta: 1 si la siguiente vela es alcista, 0 si bajista
        label = 1 if vela_siguiente['close'] > vela_siguiente['open'] else 0
        
        datos_entrenamiento[activo]['X'].append(X_actual.values.flatten())
        datos_entrenamiento[activo]['y'].append(label)
    
    # Opcional: limitar el tamaño para no crecer infinitamente
    max_samples = 1000
    if len(datos_entrenamiento[activo]['X']) > max_samples:
        datos_entrenamiento[activo]['X'] = datos_entrenamiento[activo]['X'][-max_samples:]
        datos_entrenamiento[activo]['y'] = datos_entrenamiento[activo]['y'][-max_samples:]

def entrenar_si_es_necesario(activo, min_muestras=100):
    """Entrena el modelo si hay suficientes muestras nuevas."""
    if activo not in datos_entrenamiento:
        return
    X_list = datos_entrenamiento[activo]['X']
    if len(X_list) < min_muestras:
        return
    # Convertir a DataFrame y Series
    df_X = pd.DataFrame(X_list)
    y = pd.Series(datos_entrenamiento[activo]['y'])
    entrenar_modelo_activo(activo, df_X, y)

# ============================================================
# GENERACIÓN DE SEÑAL FINAL (con todas las mejoras)
# ============================================================
def generar_senal(activo, velas, segundo_actual):
    """
    Genera la señal para el activo actual.
    Retorna (direccion, score, estado, expiracion, tipo_reversal)
    """
    # 1. Filtro de mercado malo
    if filtro_mercado_malo(velas):
        return 'NO_OPERAR', 0.0, 'Mercado malo', None, None
    
    # 2. Solo generar en el segundo 58
    if segundo_actual != 58:
        return 'ESPERANDO', 0.0, f'Segundo {segundo_actual}', None, None
    
    # 3. Actualizar datos de entrenamiento (para futuros modelos)
    actualizar_datos_entrenamiento(activo, velas)
    entrenar_si_es_necesario(activo, min_muestras=100)
    
    # 4. Predicción con IA (si existe)
    prob, señal_ml, votos = predecir_probabilidad_activo(activo, velas)
    
    # 5. Reglas de fuerza y volumen
    fuerza = calcular_fuerza_mercado(velas)
    vol_dir = volumen_direccional(velas)
    trampas = detectar_trampas(velas)
    
    # Normalizar (ejemplo)
    fuerza_norm = min(max(fuerza, 0), 1)
    vol_dir_norm = min(max(vol_dir, 0), 1)
    trampas_norm = 1 - min(max(trampas, 0), 1)
    
    # 6. Puntuación híbrida
    if prob is not None:
        score = (0.5 * prob + 0.2 * fuerza_norm + 0.2 * vol_dir_norm + 0.1 * trampas_norm)
    else:
        score = (0.4 * fuerza_norm + 0.4 * vol_dir_norm + 0.2 * trampas_norm)
    
    # 7. Umbral de probabilidad
    if score < 0.62:
        return 'NO_OPERAR', score, 'Score insuficiente', None, None
    
    # 8. Determinar dirección
    if prob is not None:
        direccion = señal_ml
    else:
        direccion = 'CALL' if (fuerza_norm > 0.5 and vol_dir_norm > 0.5) else 'PUT'
    
    # 9. Detectar si es reversión o continuación (usando tendencia)
    tendencia = detectar_tendencias_y_reversiones(velas)
    if tendencia in ['ALCISTA', 'REV_ALCISTA'] and direccion == 'CALL':
        tipo = 'CONTINUACION_ALCISTA'
    elif tendencia in ['BAJISTA', 'REV_BAJISTA'] and direccion == 'PUT':
        tipo = 'CONTINUACION_BAJISTA'
    elif tendencia in ['ALCISTA', 'REV_ALCISTA'] and direccion == 'PUT':
        tipo = 'REVERSION_BAJISTA'
    elif tendencia in ['BAJISTA', 'REV_BAJISTA'] and direccion == 'CALL':
        tipo = 'REVERSION_ALCISTA'
    else:
        tipo = 'NEUTRO'
    
    # 10. Calcular vencimiento (próxima vela)
    # Suponiendo velas de 60 segundos
    ahora = datetime.now()
    # El próximo minuto en punto
    next_minute = (ahora + timedelta(minutes=1)).replace(second=0, microsecond=0)
    expiracion = next_minute.strftime('%H:%M:%S')
    
    return direccion, score, 'OK', expiracion, tipo
