# data_provider.py
import time
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

try:
    from iqoptionapi.stable_api import IQ_Option
except ImportError:
    logger.error("No se pudo importar IQ_Option. Instala: pip install iqoptionapi")
    raise

class IQOptionProvider:
    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password
        self.api = IQ_Option(email, password)
        self.conectado = False
        self.needs_2fa = False
        self.conexion_exitosa = False

    def conectar(self) -> Tuple[bool, str]:
        """
        Intenta conectar a IQ Option.
        Returns:
            (success, message) donde message puede ser "2FA" si se requiere código.
        """
        try:
            check, reason = self.api.connect()
            if check:
                self.conectado = True
                self.conexion_exitosa = True
                balance_mode = self.api.get_balance_mode()
                balance = self.api.get_balance()
                return True, f"Conectado - Cuenta: {'REAL' if balance_mode == 'real' else 'PRÁCTICA'} | Balance: {balance}"
            else:
                if reason == "2FA":
                    self.needs_2fa = True
                    return False, "2FA"
                else:
                    return False, f"Error: {reason}"
        except Exception as e:
            return False, f"Excepción: {str(e)}"

    def verificar_2fa(self, codigo: str) -> Tuple[bool, str]:
        """Envía el código 2FA y finaliza la conexión."""
        try:
            check, reason = self.api.connect_2fa(codigo)
            if check:
                self.conectado = True
                self.conexion_exitosa = True
                self.needs_2fa = False
                balance_mode = self.api.get_balance_mode()
                balance = self.api.get_balance()
                return True, f"Conectado - Cuenta: {'REAL' if balance_mode == 'real' else 'PRÁCTICA'} | Balance: {balance}"
            else:
                return False, f"Error 2FA: {reason}"
        except Exception as e:
            return False, f"Excepción: {str(e)}"

    def obtener_activos_otc(self, tipo_activo: str = "digital") -> List[str]:
        if not self.conectado:
            logger.error("No hay conexión activa")
            return []
        try:
            todos = self.api.get_all_open_time()
            if tipo_activo not in todos:
                return []
            return [nombre for nombre, info in todos[tipo_activo].items()
                    if "-OTC" in nombre and info.get("open", False)]
        except Exception as e:
            logger.exception(f"Error obteniendo activos OTC: {e}")
            return []

    def analizar_activo(self, activo: str) -> Optional[Dict[str, Any]]:
        """
        REEMPLAZA ESTE CUERPO CON TU LÓGICA REAL DE ANÁLISIS.
        """
        try:
            velas = self.api.get_candles(activo, 60, 10, time.time())
            if not velas:
                return None
        except Exception as e:
            logger.error(f"Error obteniendo velas de {activo}: {e}")
            return None

        # --- AQUÍ VA TU CÓDIGO DE ANÁLISIS (fuerza, volumen, IA) ---
        import random
        fuerza = random.uniform(0, 100)
        volumen_rel = random.uniform(0.5, 2.5)
        sentimiento = random.choice(["CALL", "PUT", "NEUTRO"])
        es_bueno = fuerza > 70 and volumen_rel > 1.2

        return {
            "activo": activo,
            "fuerza": round(fuerza, 2),
            "volumen": round(volumen_rel, 2),
            "sentimiento": sentimiento,
            "es_bueno": es_bueno,
            "timestamp": datetime.now().isoformat(),
            "velas": velas
        }

    def buscar_mejor_activo(self, tipo_activo: str = "digital", max_intentos: int = None) -> Optional[Dict[str, Any]]:
        if not self.conectado:
            logger.warning("No conectado")
            return None
        activos = self.obtener_activos_otc(tipo_activo)
        if not activos:
            return None
        for i, activo in enumerate(activos):
            if max_intentos and i >= max_intentos:
                break
            resultado = self.analizar_activo(activo)
            if resultado and resultado.get("es_bueno"):
                return resultado
            time.sleep(1)
        return None

# Instancia global (ahora se creará bajo demanda)
_provider_instance = None

def get_provider(email: str, password: str) -> IQOptionProvider:
    global _provider_instance
    if _provider_instance is None or _provider_instance.email != email or _provider_instance.password != password:
        _provider_instance = IQOptionProvider(email, password)
    return _provider_instance
