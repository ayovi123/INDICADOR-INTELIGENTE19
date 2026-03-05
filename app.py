# app.py
import time
import threading
from datetime import datetime
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.table import Table
from rich.text import Text
from rich import box
import pandas as pd
import numpy as np
from data_provider import EstrategiaAvanzada

# ========== CONFIGURACIÓN ==========
ACTIVOS = [
    "EURUSD-OTC", "GBPUSD-OTC", "USDJPY-OTC", "AUDUSD-OTC",
    "EURJPY-OTC", "GBPJPY-OTC", "USDCAD-OTC", "USDCHF-OTC"
]
TIEMPO_ESPERA = 1  # segundos entre ciclos
MAX_MINUTOS_FIJADO = 10  # minutos sin señales para liberar activo
SEGUNDO_EJECUCION = 58  # segundo en el que se ejecuta la orden
VELAS_HISTORICAS = 50  # número de velas a mantener en memoria

# ========== GESTOR DE DATOS SIMULADO (REEMPLAZAR CON API REAL) ==========
class DataManager:
    """
    Clase que simula la obtención de velas históricas de IQ Option.
    En producción, debe conectarse a la API real.
    """
    def __init__(self):
        self.historial = {activo: [] for activo in ACTIVOS}

    def obtener_velas(self, activo, count=VELAS_HISTORICAS):
        """
        Simula la obtención de las últimas 'count' velas de 1 minuto.
        Retorna un DataFrame con columnas: open, high, low, close, volume.
        """
        # Simulación: generar datos aleatorios (en producción obtener de API)
        if len(self.historial[activo]) < count:
            # Generar datos iniciales
            precio = np.random.uniform(1.0, 1.2)  # precio base
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
            # Devolver las últimas 'count' velas
            df = self.historial[activo].tail(count).reset_index(drop=True)
        return df

    def actualizar_vela(self, activo, nueva_vela):
        """
        Agrega una nueva vela al historial y elimina la más antigua.
        nueva_vela: dict con open, high, low, close, volume.
        """
        df_nuevo = pd.DataFrame([nueva_vela])
        self.historial[activo] = pd.concat([self.historial[activo], df_nuevo], ignore_index=True)
        # Mantener solo las últimas VELAS_HISTORICAS
        if len(self.historial[activo]) > VELAS_HISTORICAS:
            self.historial[activo] = self.historial[activo].iloc[-VELAS_HISTORICAS:].reset_index(drop=True)

# ========== CLASE PRINCIPAL DEL BOT ==========
class IQOptionBot:
    def __init__(self):
        self.data_manager = DataManager()
        self.estrategia = EstrategiaAvanzada(
            modelo_path='modelo_xgb.pkl',
            scaler_path='scaler.pkl',
            ventana=20
        )
        self.activo_fijado = None          # Activo actualmente fijado
        self.minutos_sin_senal = 0         # Contador de minutos sin señal buena (cuando está fijado)
        self.historial_analisis = []       # Lista de análisis recientes (para UI)
        self.ultima_senal = None            # Última señal generada (para UI)
        self.console = Console()
        self.running = True

    def verificar_tendencia(self, activo, velas):
        """
        Verifica si el activo tiene tendencia clara según la estrategia.
        """
        analisis = self.estrategia.analizar_activo(velas)
        return analisis['tiene_tendencia']

    def liberar_si_corresponde(self, velas):
        """
        Verifica si se debe liberar el activo fijado.
        Retorna True si se liberó.
        """
        if self.activo_fijado is None:
            return False
        velas_activo = self.data_manager.obtener_velas(self.activo_fijado)
        analisis = self.estrategia.analizar_activo(velas_activo)
        # Condiciones de liberación
        liberar = False
        if not analisis['tiene_tendencia']:
            self.console.log(f"[yellow]Activo {self.activo_fijado} perdió tendencia. Liberando.")
            liberar = True
        elif analisis['fuerza'] < self.estrategia.umbral_fuerza * 0.7:  # fuerza muy baja
            self.console.log(f"[yellow]Activo {self.activo_fijado} perdió fuerza. Liberando.")
            liberar = True
        elif not analisis['es_bueno']:
            self.minutos_sin_senal += 1
            if self.minutos_sin_senal >= MAX_MINUTOS_FIJADO:
                self.console.log(f"[yellow]Activo {self.activo_fijado} sin señales por {MAX_MINUTOS_FIJADO} min. Liberando.")
                liberar = True
        else:
            self.minutos_sin_senal = 0  # reiniciar contador

        if liberar:
            self.activo_fijado = None
            self.minutos_sin_senal = 0
            return True
        return False

    def ejecutar_estrategia(self):
        """
        Bucle principal que corre cada segundo.
        """
        while self.running:
            now = datetime.now()
            segundo = now.second

            # Cada segundo mostramos el estado (actualización rápida de UI)
            self.actualizar_ui()

            # En el segundo 58 ejecutamos el análisis y posible orden
            if segundo == SEGUNDO_EJECUCION:
                self.ejecutar_ciclo()

            time.sleep(TIEMPO_ESPERA)

    def ejecutar_ciclo(self):
        """
        Lógica principal de análisis y decisión.
        """
        # Determinar qué activos analizar
        if self.activo_fijado is not None:
            # Verificar si debemos liberar
            velas_fijado = self.data_manager.obtener_velas(self.activo_fijado)
            liberado = self.liberar_si_corresponde(velas_fijado)
            if liberado:
                # Si se liberó, continuamos con búsqueda general
                activos_a_analizar = ACTIVOS
            else:
                activos_a_analizar = [self.activo_fijado]
        else:
            activos_a_analizar = ACTIVOS

        # Analizar cada activo
        for activo in activos_a_analizar:
            velas = self.data_manager.obtener_velas(activo)
            analisis = self.estrategia.analizar_activo(velas)
            analisis['activo'] = activo
            analisis['timestamp'] = datetime.now().strftime('%H:%M:%S')

            # Agregar al historial de análisis (para UI)
            self.historial_analisis.append(analisis)
            if len(self.historial_analisis) > 20:
                self.historial_analisis.pop(0)

            # Si es buena señal, mostrar y posiblemente fijar activo
            if analisis['es_bueno']:
                self.ultima_senal = analisis
                # Si no hay activo fijado y tiene tendencia, fijarlo
                if self.activo_fijado is None and analisis['tiene_tendencia']:
                    self.activo_fijado = activo
                    self.minutos_sin_senal = 0
                    self.console.log(f"[green]¡Activo {activo} fijado por tendencia y señal buena!")
                # Aquí se ejecutaría la orden real en IQ Option
                self.ejecutar_orden(analisis)
            else:
                # Solo log si estamos depurando
                pass

    def ejecutar_orden(self, analisis):
        """
        Simula la ejecución de una orden CALL/PUT.
        En producción, aquí se conectaría con la API de IQ Option.
        """
        self.console.log(
            f"[bold cyan]SEÑAL: {analisis['activo']} - {analisis['sentimiento']} "
            f"(Prob: CALL {analisis['prob_CALL']:.2%} / PUT {analisis['prob_PUT']:.2%}) "
            f"Fuerza: {analisis['fuerza']:.2%} - {analisis['magnitud_esperada']}"
        )
        # Aquí iría el código real de la orden

    def actualizar_ui(self):
        """
        Construye y muestra la interfaz de usuario en tiempo real usando rich.
        """
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="footer", size=10)
        )
        layout["main"].split_row(
            Layout(name="estado"),
            Layout(name="historial")
        )

        # Header: hora actual y estado de fijación
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if self.activo_fijado:
            header_text = f"[bold green]⚡ BOT ACTIVO - FIJADO EN: {self.activo_fijado} ⚡[/bold green]"
        else:
            header_text = f"[bold yellow]🔍 BOT ACTIVO - BUSCANDO ACTIVOS... 🔍[/bold yellow]"
        layout["header"].update(
            Panel(header_text, subtitle=now, style="bold white on blue", box=box.DOUBLE)
        )

        # Panel de estado actual
        estado_table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
        estado_table.add_column("Activo", style="cyan")
        estado_table.add_column("Análisis actual", style="white")
        # Mostrar el activo que se está analizando ahora (podemos tomar el último del historial)
        if self.historial_analisis:
            ultimo = self.historial_analisis[-1]
            analisis_str = f"{ultimo['sentimiento']} (F:{ultimo['fuerza']:.2%})"
            estado_table.add_row(ultimo['activo'], analisis_str)
        else:
            estado_table.add_row("---", "Esperando datos...")
        layout["estado"].update(Panel(estado_table, title="📊 Análisis en curso", border_style="green"))

        # Panel de historial de análisis
        historial_table = Table(show_header=True, header_style="bold magenta", box=box.SIMPLE)
        historial_table.add_column("Hora", style="dim")
        historial_table.add_column("Activo")
        historial_table.add_column("Señal", justify="center")
        historial_table.add_column("Fuerza", justify="right")
        for analisis in self.historial_analisis[-10:]:  # últimos 10
            color = "green" if analisis['es_bueno'] else "white"
            señal = analisis['sentimiento']
            if analisis['es_bueno']:
                señal = f"[bold {color}]{señal}[/bold {color}]"
            historial_table.add_row(
                analisis['timestamp'],
                analisis['activo'],
                señal,
                f"{analisis['fuerza']:.2%}"
            )
        layout["historial"].update(Panel(historial_table, title="📜 Historial de análisis", border_style="blue"))

        # Footer: última señal detallada
        if self.ultima_senal:
            s = self.ultima_senal
            footer_text = (
                f"[bold]Última señal:[/bold] {s['activo']} - {s['sentimiento']}\n"
                f"Probabilidad: CALL {s['prob_CALL']:.2%} / PUT {s['prob_PUT']:.2%}\n"
                f"Fuerza: {s['fuerza']:.2%} - {s['magnitud_esperada']}\n"
                f"Volumen (presión): {s['volumen']:.2f}\n"
                f"Tendencia: {'Sí' if s['tiene_tendencia'] else 'No'}"
            )
        else:
            footer_text = "Esperando primera señal..."
        layout["footer"].update(Panel(footer_text, title="🔔 Última señal", border_style="red"))

        # Limpiar y mostrar
        self.console.clear()
        self.console.print(layout)

    def detener(self):
        self.running = False

# ========== PUNTO DE ENTRADA ==========
if __name__ == "__main__":
    bot = IQOptionBot()
    try:
        bot.ejecutar_estrategia()
    except KeyboardInterrupt:
        bot.detener()
        console = Console()
        console.print("[red]Bot detenido por el usuario.[/red]")
