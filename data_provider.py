# ============================================================
# data_provider.py
# Versión mejorada con todos los puntos solicitados:
# - Conexión corregida a IQ Option
# - Presión compradora/vendedora, fuerza real de vela, momentum
# - Filtros de mercado malo (rango pequeño, lateral, volumen decreciente)
# - Features avanzadas: order flow aproximado, velocidad/aceleración,
#   compresión de volatilidad
# - Detección de tendencias y reversiones
# - Detección de manipulación y trampas de liquidez
# - Predicción probabilística con modelos IA (híbrido)
# - Señal confirmada al segundo 58
# - Sistema de puntuación híbrido
#
# IMPORTANTE: Se mantiene la base de fuerza de mercado,
# volumen direccional y detección de trampas original.
# ============================================================

from iqoptionapi.stable_api import IQ_Option
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
from sklearn.ensemble import RandomForestClassifier, VotingClassifier
from xgboost import XGBClassifier
from lightgbm import LGBMClassifier
import joblib
import os

# ============================================================
# CONEXIÓN A IQ OPTION (CORREGIDA)
# ============================================================
api = None  # variable global para la API

def conectar(email, password, twofa=None):
    """
    Conecta a IQ Option y retorna el objeto api.
    """
    global api
    try:
        api = IQ_Option(email, password)
        exito, mensaje = api.connect(twofa) if twofa else api.connect()
        if exito:
            print("✅ Conectado a IQ Option")
            # Cambiar a cuenta demo si se desea (opcional)
            # api.change_balance("PRACTICE")
            return api
        else:
            print(f"❌ Error de conexión: {mensaje}")
            return None
    except Exception as e:
        print(f"❌ Excepción en conexión: {e}")
        return None

# ============================================================
# OBTENCIÓN DE VELAS (OHLCV)
# ============================================================
def obtener_velas(activo, timeframe=60, cantidad=100):
    """
    Obtiene velas históricas de IQ Option.
    timeframe en segundos (60, 300, 900, etc.)
    Retorna DataFrame con columnas: timestamp, open, high, low, close, volume
    """
    if api is None:
        print("API no conectada")
        return None
    try:
        # IQ Option devuelve velas en orden descendente (la más reciente primero)
        velas = api.get_candles(activo, timeframe, cantidad, time.time())
        df = pd.DataFrame(velas)
        df['timestamp'] = pd.to_datetime(df['from'], unit='s')
        df = df[['timestamp', 'open', 'max', 'min', 'close', 'volume']]
        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        df = df.sort_values('timestamp')  # orden ascendente
        return df
    except Exception as e:
        print(f"Error al obtener velas: {e}")
        return None

# ============================================================
# FUNCIONES BASE (LAS QUE YA TIENES – NO MODIFICAR)
# ============================================================
# (Aquí debes insertar tus funciones originales de:
#  - calcular_fuerza_mercado
#  - volumen_direccional
#  - detectar_trampas
#  - etc.
#  Las dejamos como placeholders; tú las reemplazas con tu código real)
# ============================================================

def calcular_fuerza_mercado(velas):
    """
    Placeholder: tu implementación original.
    """
    # return algun_valor
    pass

def volumen_direccional(velas):
    """
    Placeholder: tu implementación original.
    """
    pass

def detectar_trampas(velas):
    """
    Placeholder: tu implementación original.
    """
    pass

# ============================================================
# NUEVAS FUNCIONES (MEJORAS CHATGPT)
# ============================================================

def presion_compradora_vendedora(velas):
    """
    Calcula presión compradora (close > open) y vendedora (close < open)
    basada en volumen y rango de la vela.
    Retorna (presion_compradora, presion_vendedora) como porcentajes.
    """
    df = velas.copy()
    df['rango'] = df['high'] - df['low']
    df['es_alcista'] = df['close'] > df['open']
    df['es_bajista'] = df['close'] < df['open']
    
    # Volumen ponderado por el rango de la vela (las velas grandes con volumen importan más)
    df['vol_ponderado'] = df['volume'] * df['rango']
    
    compra = df[df['es_alcista']]['vol_ponderado'].sum()
    venta = df[df['es_bajista']]['vol_ponderado'].sum()
    total = compra + venta
    if total == 0:
        return 0.5, 0.5
    return compra / total, venta / total

def fuerza_real_vela(velas):
    """
    Calcula la fuerza real de cada vela combinando:
    - Tamaño del cuerpo en proporción al rango total
    - Volumen relativo (comparado con la media)
    - Cierre en los extremos (sombras pequeñas)
    Retorna un array de fuerzas (0 a 1) para cada vela.
    """
    df = velas.copy()
    df['cuerpo'] = abs(df['close'] - df['open'])
    df['rango'] = df['high'] - df['low']
    df['proporcion_cuerpo'] = df['cuerpo'] / df['rango'].replace(0, np.nan)
    df['proporcion_cuerpo'].fillna(0, inplace=True)
    
    # Volumen relativo (últimas 20 velas)
    df['vol_media'] = df['volume'].rolling(20, min_periods=1).mean()
    df['vol_relativo'] = df['volume'] / df['vol_media']
    
    # Cierre en extremos: qué tan cerca está el cierre del máximo o mínimo
    df['dist_max'] = (df['high'] - df['close']) / df['rango'].replace(0, np.nan)
    df['dist_min'] = (df['close'] - df['low']) / df['rango'].replace(0, np.nan)
    # Si es alcista, interesa que cierre cerca del max; si bajista, cerca del min
    df['cierre_extremo'] = np.where(df['close'] > df['open'], 
                                     1 - df['dist_max'],  # alcista: 1 = pegado al max
                                     1 - df['dist_min'])  # bajista: 1 = pegado al min
    df['cierre_extremo'].fillna(0.5, inplace=True)
    
    # Fuerza = combinación lineal
    fuerza = (0.4 * df['proporcion_cuerpo'] + 
              0.3 * df['vol_relativo'].clip(0, 2) / 2 + 
              0.3 * df['cierre_extremo'])
    return fuerza.values

def momentum_corto_plazo(velas, periodo=5):
    """
    Calcula momentum basado en el cambio de precio y volumen.
    Retorna un valor positivo (alcista) o negativo (bajista).
    """
    if len(velas) < periodo:
        return 0
    cambios_precio = velas['close'].pct_change().iloc[-periodo:].mean()
    cambios_volumen = velas['volume'].pct_change().iloc[-periodo:].mean()
    # Momentum combina precio y volumen
    momentum = cambios_precio * (1 + cambios_volumen)
    return momentum

def filtro_mercado_malo(velas):
    """
    Detecta si el mercado actual es "malo" para operar:
    - Rango pequeño (baja volatilidad)
    - Lateral (precio no se mueve)
    - Volumen decreciente
    Retorna True si es malo, False si es operable.
    """
    if len(velas) < 20:
        return False  # no hay suficientes datos
    
    ultimas = velas.iloc[-20:]
    
    # Rango promedio (ATR simplificado)
    rango_promedio = (ultimas['high'] - ultimas['low']).mean()
    precio_medio = ultimas['close'].mean()
    volatilidad_relativa = rango_promedio / precio_medio if precio_medio != 0 else 0
    
    # Lateral: el precio no se mueve significativamente
    cambio_neto = abs(ultimas['close'].iloc[-1] - ultimas['close'].iloc[0]) / ultimas['close'].iloc[0]
    
    # Volumen decreciente: pendiente negativa en los últimos periodos
    x = np.arange(len(ultimas))
    coef = np.polyfit(x, ultimas['volume'], 1)[0]  # pendiente
    
    condiciones_malas = 0
    if volatilidad_relativa < 0.001:  # umbral ajustable
        condiciones_malas += 1
    if cambio_neto < 0.002:
        condiciones_malas += 1
    if coef < 0:  # volumen decreciente
        condiciones_malas += 1
    
    return condiciones_malas >= 2  # si al menos 2 condiciones se cumplen, mercado malo

def features_avanzadas(velas):
    """
    Genera features avanzadas para los modelos de IA:
    - Order flow aproximado (volumen * dirección)
    - Velocidad del precio (derivada)
    - Aceleración (segunda derivada)
    - Compresión de volatilidad (comparación ATR corto vs largo)
    - etc.
    Retorna un diccionario con las features.
    """
    df = velas.copy()
    features = {}
    
    # Order flow aproximado: volumen * (close - open)
    df['order_flow'] = df['volume'] * (df['close'] - df['open'])
    features['order_flow_sum'] = df['order_flow'].iloc[-10:].sum()
    features['order_flow_mean'] = df['order_flow'].iloc[-10:].mean()
    
    # Velocidad (derivada del precio)
    df['velocidad'] = df['close'].diff()
    features['velocidad_media'] = df['velocidad'].iloc[-5:].mean()
    
    # Aceleración (segunda derivada)
    df['aceleracion'] = df['velocidad'].diff()
    features['aceleracion_media'] = df['aceleracion'].iloc[-5:].mean()
    
    # Compresión de volatilidad: ATR(5) / ATR(20)
    df['tr'] = np.maximum(df['high'] - df['low'], 
                          np.maximum(abs(df['high'] - df['close'].shift()),
                                     abs(df['low'] - df['close'].shift())))
    atr5 = df['tr'].rolling(5).mean().iloc[-1]
    atr20 = df['tr'].rolling(20).mean().iloc[-1]
    features['compresion_volatilidad'] = atr5 / atr20 if atr20 != 0 else 1
    
    # Relación de volumen alcista/bajista
    vol_alcista = df[df['close'] > df['open']]['volume'].sum()
    vol_bajista = df[df['close'] < df['open']]['volume'].sum()
    features['ratio_vol_alcista_bajista'] = vol_alcista / (vol_bajista + 1)
    
    return features

def detectar_tendencias_y_reversiones(velas):
    """
    Detecta tendencia alcista, bajista o posible reversión.
    Retorna: 'ALCISTA', 'BAJISTA', 'REV_ALCISTA', 'REV_BAJISTA' o 'NEUTRO'.
    """
    if len(velas) < 20:
        return 'NEUTRO'
    
    # Pendiente de regresión lineal en los últimos 20 periodos
    y = velas['close'].iloc[-20:].values
    x = np.arange(len(y))
    pendiente = np.polyfit(x, y, 1)[0]
    
    # Detectar posible reversión: cambio de dirección con volumen
    ultimas_5 = velas.iloc[-5:]
    direccion_corta = (ultimas_5['close'].iloc[-1] - ultimas_5['close'].iloc[0]) > 0
    
    # Si pendiente > umbral, tendencia alcista; si < -umbral, bajista
    umbral = 0.0005 * velas['close'].mean()  # ajustable
    if pendiente > umbral:
        # Ver si hay señal de reversión a bajista en los últimos candles
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
    """
    Detecta patrones de manipulación (wick largos, velas de alta volatilidad con poco volumen,
    falsos rompimientos). Retorna un score de 0 a 1 (1 = alta probabilidad de manipulación).
    """
    if len(velas) < 10:
        return 0
    
    df = velas.iloc[-10:].copy()
    df['rango'] = df['high'] - df['low']
    df['cuerpo'] = abs(df['close'] - df['open'])
    df['sombra_superior'] = df['high'] - df[['close', 'open']].max(axis=1)
    df['sombra_inferior'] = df[['close', 'open']].min(axis=1) - df['low']
    df['sombra_total'] = df['sombra_superior'] + df['sombra_inferior']
    
    # Wick largos en proporción al rango
    df['proporcion_sombras'] = df['sombra_total'] / df['rango']
    # Velas con cuerpo pequeño pero sombras grandes = posible manipulación
    manip_score = df['proporcion_sombras'].mean()
    
    # Falso rompimiento: precio supera máximo reciente pero cierra dentro
    max_previo = df['high'].iloc[:-1].max()
    ultimo = df.iloc[-1]
    if ultimo['high'] > max_previo and ultimo['close'] < max_previo:
        manip_score += 0.3
    
    return min(manip_score, 1.0)

# ============================================================
# MODELOS DE IA Y PREDICCIÓN PROBABILÍSTICA
# ============================================================
# Se usarán modelos entrenados previamente (RandomForest, XGBoost, LightGBM)
# y un voting classifier para obtener probabilidades híbridas.
# ============================================================

def cargar_modelos():
    """
    Carga los modelos guardados (deben existir en la carpeta 'modelos/').
    Si no existen, se pueden entrenar en caliente (opción no implementada aquí).
    """
    modelos = {}
    try:
        modelos['rf'] = joblib.load('modelos/random_forest.pkl')
        modelos['xgb'] = joblib.load('modelos/xgboost.pkl')
        modelos['lgb'] = joblib.load('modelos/lightgbm.pkl')
        # Voting classifier híbrido (soft voting)
        modelos['voting'] = joblib.load('modelos/voting_clf.pkl')
    except:
        print("No se encontraron modelos entrenados. Se usará lógica basada en reglas.")
        modelos = None
    return modelos

def preparar_features_para_modelo(velas):
    """
    Reúne todas las features (tus originales + las nuevas) en un vector.
    """
    feats = {}
    
    # Features originales (si las tienes definidas)
    # feats['fuerza'] = calcular_fuerza_mercado(velas)
    # feats['vol_dir'] = volumen_direccional(velas)
    
    # Nuevas features
    compra, venta = presion_compradora_vendedora(velas)
    feats['presion_compra'] = compra
    feats['presion_venta'] = venta
    
    fuerza_velas = fuerza_real_vela(velas)
    feats['fuerza_vela_media'] = fuerza_velas[-5:].mean() if len(fuerza_velas)>=5 else fuerza_velas.mean()
    
    feats['momentum'] = momentum_corto_plazo(velas)
    
    # features avanzadas
    avanzadas = features_avanzadas(velas)
    feats.update(avanzadas)
    
    # Detección de tendencia codificada
    tendencia = detectar_tendencias_y_reversiones(velas)
    tend_map = {'ALCISTA':1, 'BAJISTA':-1, 'REV_ALCISTA':2, 'REV_BAJISTA':-2, 'NEUTRO':0}
    feats['tendencia'] = tend_map.get(tendencia, 0)
    
    feats['manipulacion'] = detectar_manipulacion_trampas(velas)
    
    # Convertir a DataFrame de una fila
    df_feats = pd.DataFrame([feats])
    return df_feats

def predecir_probabilidad(velas, modelos):
    """
    Usa los modelos para predecir probabilidad de CALL (alcista) o PUT (bajista).
    Retorna (probabilidad, señal_consenso, votos)
    """
    if modelos is None or len(velas) < 20:
        # Si no hay modelos, usar lógica basada en fuerza y volumen
        return None, 'NEUTRO', 0
    
    X = preparar_features_para_modelo(velas)
    
    # Obtener probabilidades de cada modelo
    prob_rf = modelos['rf'].predict_proba(X)[0][1] if 'rf' in modelos else 0.5
    prob_xgb = modelos['xgb'].predict_proba(X)[0][1] if 'xgb' in modelos else 0.5
    prob_lgb = modelos['lgb'].predict_proba(X)[0][1] if 'lgb' in modelos else 0.5
    
    # Votación híbrida: promedio de probabilidades
    prob_promedio = (prob_rf + prob_xgb + prob_lgb) / 3
    
    # Votación discreta (cada modelo vota CALL si prob > 0.5)
    votos_call = sum([1 for p in [prob_rf, prob_xgb, prob_lgb] if p > 0.5])
    
    # Señal de consenso: si al menos 2 modelos coinciden
    if votos_call >= 2:
        señal_consenso = 'CALL'
        prob_final = prob_promedio
    else:
        señal_consenso = 'PUT'
        prob_final = 1 - prob_promedio  # probabilidad de PUT
    
    return prob_final, señal_consenso, votos_call

# ============================================================
# GENERACIÓN DE SEÑAL FINAL (con todas las mejoras)
# ============================================================
def generar_senal(activo, velas, modelos, segundo_actual):
    """
    Genera la señal final integrando:
    - Filtro de mercado malo
    - Predicción probabilística
    - Confirmación al segundo 58
    - Sistema de puntuación híbrido (mezcla de reglas + ML)
    """
    # 1. Filtro de mercado malo
    if filtro_mercado_malo(velas):
        return 'NO_OPERAR', 0.0, 'Mercado malo'
    
    # 2. Si no es el segundo 58, no generar señal (solo se confirma en ese instante)
    if segundo_actual != 58:   # asumiendo que tenemos el segundo actual
        return 'ESPERANDO', 0.0, f'Segundo {segundo_actual}'
    
    # 3. Obtener features y predicción ML
    prob, señal_ml, votos = predecir_probabilidad(velas, modelos)
    
    # 4. Calcular score híbrido combinando ML con reglas (fuerza, volumen, trampas)
    fuerza = calcular_fuerza_mercado(velas)   # tu función original
    vol_dir = volumen_direccional(velas)       # tu función original
    trampas = detectar_trampas(velas)          # tu función original
    
    # Normalizar (ejemplo)
    fuerza_norm = min(max(fuerza, 0), 1)
    vol_dir_norm = min(max(vol_dir, 0), 1)
    trampas_norm = 1 - min(max(trampas, 0), 1)  # a mayor trampa, menor confianza
    
    # Puntuación híbrida (pesos ajustables)
    if prob is not None:
        # Si hay ML, combinar
        score = (0.5 * prob + 0.2 * fuerza_norm + 0.2 * vol_dir_norm + 0.1 * trampas_norm)
    else:
        # Solo reglas
        score = (0.4 * fuerza_norm + 0.4 * vol_dir_norm + 0.2 * trampas_norm)
    
    # 5. Aplicar umbral de probabilidad (solo operar si score > 0.62)
    if score < 0.62:
        return 'NO_OPERAR', score, 'Score insuficiente'
    
    # 6. Determinar dirección (usar señal_ml si existe, sino usar dirección de fuerza/volumen)
    if prob is not None:
        direccion = señal_ml
    else:
        # Regla simple: si fuerza y volumen direccional apuntan en mismo sentido
        if fuerza_norm > 0.5 and vol_dir_norm > 0.5:
            direccion = 'CALL'
        else:
            direccion = 'PUT'
    
    return direccion, score, 'OK'
