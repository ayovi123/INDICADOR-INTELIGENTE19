# data_provider.py
import time
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

# Configurar logging (puedes ajustar el nivel)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================
# CONEXIÓN A IQ OPTION (Funciona con librería original y fork)
# ============================================================
try:
    from iqoptionapi.stable_api import IQ_Option
except ImportError:
    logger.error("No se pudo importar IQ_Option. Instala la librería: pip install iqoptionapi")
    raise

class IQOptionProvider:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.api = None
        self.conectado = False

    def conectar(self):
        """Establece conexión con IQ Option (maneja 2FA si es necesario)."""
        self.api = IQ_Option(self.email, self.password)
        check, reason = self.api.connect()
        if check:
            self.conectado = True
            logger.info("Conexión exitosa a IQ Option")
            # Obtener tipo de cuenta
            balance_mode = self.api.get_balance_mode()
            logger.info(f"Cuenta: {'REAL' if balance_mode == 'real' else 'PRÁCTICA'}")
            logger.info(f"Balance: {self.api.get_balance()}")
            return True
        else:
            logger.error(f"Error de conexión: {reason}")
            if reason == "2FA":
                codigo = input("Ingresa el código de verificación 2FA: ")
                check, reason = self.api.connect_2fa(codigo)
                if check:
                    self.conectado = True
                    logger.info("Conexión exitosa con 2FA")
                    return True
                else:
                    logger.error(f"Error en 2FA: {reason}")
                    return False
            return False

    def obtener_activos_otc(self, tipo_activo: str = "digital") -> List[str]:
        """
        Obtiene lista de activos OTC abiertos para el tipo especificado.
        Args:
            tipo_activo: "digital", "turbo", "binary", etc.
        Returns:
            Lista de nombres de activos (ej. ['EURUSD-OTC', 'AUDCAD-OTC'])
        """
        if not self.conectado:
            logger.error("No hay conexión activa")
            return []
        try:
            todos = self.api.get_all_open_time()
            if tipo_activo not in todos:
                logger.error(f"Tipo de activo '{tipo_activo}' no encontrado")
                return []
            activos = []
            for nombre, info in todos[tipo_activo].items():
                if "-OTC" in nombre and info.get("open", False):
                    activos.append(nombre)
            logger.info(f"Activos OTC encontrados ({tipo_activo}): {len(activos)}")
            return activos
        except Exception as e:
            logger.exception(f"Error obteniendo activos OTC: {e}")
            return []

    def analizar_activo(self, activo: str) -> Optional[Dict[str, Any]]:
        """
        Ejecuta el análisis completo de un activo (fuerza, volumen, IA).
        REEMPLAZA ESTA FUNCIÓN CON TU LÓGICA REAL.
        Actualmente es un placeholder que simula resultados.
        """
        # --- AQUÍ DEBES PONER TU CÓDIGO DE ANÁLISIS REAL ---
        # Ejemplo de uso de tu lógica existente:
        try:
            # Obtener velas (por ejemplo, 10 velas de 1 minuto)
            velas = self.api.get_candles(activo, 60, 10, time.time())
            if not velas:
                logger.warning(f"Sin datos de velas para {activo}")
                return None
        except Exception as e:
            logger.error(f"Error obteniendo velas de {activo}: {e}")
            return None

        # Aquí llamarías a tus funciones de fuerza, volumen, etc.
        # Por ahora, simulamos resultados
        import random
        fuerza = random.uniform(0, 100)
        volumen_rel = random.uniform(0.5, 2.5)
        sentimiento = random.choice(["CALL", "PUT", "NEUTRO"])
        es_bueno = fuerza > 70 and volumen_rel > 1.2

        resultado = {
            "activo": activo,
            "fuerza": round(fuerza, 2),
            "volumen": round(volumen_rel, 2),
            "sentimiento": sentimiento,
            "es_bueno": es_bueno,
            "timestamp": datetime.now().isoformat(),
            "velas": velas  # opcional
        }
        return resultado

    def buscar_mejor_activo(self, tipo_activo: str = "digital", max_intentos: int = None) -> Optional[Dict[str, Any]]:
        """
        Itera sobre activos OTC hasta encontrar uno que cumpla condiciones.
        Args:
            tipo_activo: "digital", "turbo", "binary"
            max_intentos: máximo de activos a analizar (None = todos)
        Returns:
            Diccionario con el análisis del primer activo que cumple, o None si no encuentra.
        """
        activos = self.obtener_activos_otc(tipo_activo)
        if not activos:
            logger.warning("No hay activos OTC disponibles")
            return None

        logger.info(f"Iniciando búsqueda del mejor activo entre {len(activos)} OTCs")
        for i, activo in enumerate(activos):
            if max_intentos and i >= max_intentos:
                break
            logger.info(f"Analizando {i+1}/{len(activos)}: {activo}")
            resultado = self.analizar_activo(activo)
            if resultado and resultado.get("es_bueno"):
                logger.info(f"✅ Activo seleccionado: {activo} (fuerza={resultado['fuerza']}, volumen={resultado['volumen']})")
                return resultado
            # Pequeña pausa entre análisis para no saturar
            time.sleep(1)
        logger.warning("No se encontró ningún activo que cumpla condiciones")
        return None

# Instancia global (opcional, para mantener una sola conexión)
_provider_instance = None

def get_provider(email: str, password: str) -> IQOptionProvider:
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = IQOptionProvider(email, password)
        _provider_instance.conectar()
    return _provider_instance
