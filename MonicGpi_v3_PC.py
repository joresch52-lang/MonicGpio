# -*- coding: utf-8 -*-
"""
🌲 MONITOR FORESTAL - RASPBERRY PI 3
Sistema de detección temprana de incendios con sensor ultrasónico
"""
import paho.mqtt.client as mqtt
import adafruit_dht
import board
import json
import time
import ssl
import random
import platform
import os
import RPi.GPIO as GPIO
from collections import deque
from datetime import datetime

# ==========================================
# ⚙️ CONFIGURACIÓN MQTT
# ==========================================
BROKER = "6071f9f543bb41f297470c8742588c93.s1.eu.hivemq.cloud"
PORT = 8883
USER = "jore746"
PASS = "Wildbl00d$746"
TOPIC = "bosque/sensores"

# ==========================================
# 🔧 CONFIGURACIÓN DE SENSORES
# ==========================================
PIN_DHT11 = board.D27
TRIG = 14               # Ultrasonido (Disparo) - Pin Físico 8
ECHO = 15               # Ultrasonido (Escucha) - Pin Físico 10

USAR_DHT11 = True
USAR_ULTRASONIDO = True
USAR_MQ135 = False      # Cambiar a True cuando conectes
USAR_LM35 = False       # Cambiar a True cuando conectes

# ==========================================
# 📊 CLASE DE PRE-PROCESAMIENTO
# ==========================================
class FiltroDatos:
    """
    Filtro Híbrido Inteligente:
    - Temperatura/Humedad/Gas: Promedio móvil (3 muestras) para estabilidad
    - Distancia: Pasa DIRECTO (Raw) para detección instantánea de movimiento
    """
    def __init__(self):
        # Sensores lentos: Ventana de 3 para filtrar ruido
        self.historial_temp = deque(maxlen=3)
        self.historial_hum = deque(maxlen=3)
        self.historial_gas = deque(maxlen=3)
        # Ultrasonido: Sin historial, pasa directo

        # 2. Variable para Ultrasonido (Anti-Rebote)
        self.ultima_distancia_valida = 0
        self.MAX_RANGO_REAL = 400 # Límite físico del sensor (4 metros)
    
    def procesar(self, temp, hum, gas, distancia_raw):
        """
        Procesa los datos aplicando filtrado selectivo
        Returns: dict con valores procesados
        """
        resultado = {"temp": None, "hum": None, "gas": None, "distancia": None}
        
        # --- FILTRADO CON PROMEDIO (Señales lentas) ---
        if temp is not None:
            self.historial_temp.append(temp)
            resultado["temp"] = round(sum(self.historial_temp) / len(self.historial_temp), 1)
        
        if hum is not None:
            self.historial_hum.append(hum)
            resultado["hum"] = round(sum(self.historial_hum) / len(self.historial_hum), 1)
        
        if gas is not None:
            self.historial_gas.append(gas)
            resultado["gas"] = round(sum(self.historial_gas) / len(self.historial_gas), 1)
        
        if distancia_raw is not None:
            if distancia_raw > self.MAX_RANGO_REAL:
                # ¡CASO ERROR 840cm! -> Ignoramos y mantenemos el anterior
                resultado["distancia"] = self.ultima_distancia_valida
            else:
                # CASO REAL -> Actualizamos memoria y enviamos
                self.ultima_distancia_valida = distancia_raw
                resultado["distancia"] = distancia_raw
        else:
            # Si el sensor no leyó nada, mantenemos el último conocido
            resultado["distancia"] = self.ultima_distancia_valida
        
        return resultado
    
    def get_estado(self):
        """Retorna configuración actual del filtro"""
        return {
            "muestras_temp": len(self.historial_temp),
            "muestras_hum": len(self.historial_hum),
            "muestras_gas": len(self.historial_gas),
            "ventana_promedio": 3,
            "modo_distancia": f"Anti-Pico > {self.MAX_RANGO_REAL}cm"
        }

# ==========================================
# 🖥️ DETECCIÓN DE HARDWARE
# ==========================================
def obtener_info_raspberry():
    """Detecta automáticamente el modelo de Raspberry Pi y obtiene info del sistema"""
    modelo = "Raspberry Pi (Desconocido)"
    try:
        with open('/proc/device-tree/model', 'r') as f:
            modelo = f.read().strip('\x00').strip()
    except:
        modelo = platform.machine() + " - " + platform.system()
    
    # Temperatura del CPU
    cpu_temp = None
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            cpu_temp = round(int(f.read()) / 1000, 1)
    except:
        pass
    
    return {
        "modelo_rpi": modelo,
        "cpu_temp": cpu_temp,
        "python_version": platform.python_version(),
        "hostname": platform.node()
    }

# ==========================================
# 📡 CLASE DE GESTIÓN DE SENSORES
# ==========================================
class GestorSensores:
    """Gestiona la inicialización y lectura de todos los sensores"""
    
    def __init__(self):
        self.dht_sensor = None
        self.estado = {
            "dht11": {"conectado": False, "modelo": "DHT11 Digital", "ultimo_error": None},
            "ultrasonido": {"conectado": False, "modelo": "HC-SR04", "ultimo_error": None},
            "mq135": {"conectado": False, "modelo": "MQ-135 (Gas/Humo)", "ultimo_error": None},
            "lm35": {"conectado": False, "modelo": "LM35 Analógico", "ultimo_error": None}
        }
        self._inicializar_sensores()
    
    def _inicializar_sensores(self):
        """Inicializa todos los sensores habilitados"""
        
        # DHT11 - Temperatura y Humedad
        if USAR_DHT11:
            try:
                self.dht_sensor = adafruit_dht.DHT11(PIN_DHT11)
                self.estado["dht11"]["conectado"] = True
                print("✅ DHT11: Inicializado correctamente")
            except Exception as e:
                self.estado["dht11"]["ultimo_error"] = str(e)
                print(f"❌ DHT11: Error - {e}")
        
        # HC-SR04 - Sensor Ultrasónico
        if USAR_ULTRASONIDO:
            try:
                GPIO.setwarnings(False)
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(TRIG, GPIO.OUT)
                GPIO.setup(ECHO, GPIO.IN)
                self.estado["ultrasonido"]["conectado"] = True
                print("✅ Ultrasonido HC-SR04: Inicializado correctamente")
            except Exception as e:
                self.estado["ultrasonido"]["ultimo_error"] = str(e)
                print(f"❌ Ultrasonido: Error - {e}")
        
        # MQ135 - Sensor de Gas (preparado para conexión futura)
        if USAR_MQ135:
            self.estado["mq135"]["conectado"] = True
            print("✅ MQ135: Listo (simulado)")
        
        # LM35 - Temperatura de Precisión (preparado para conexión futura)
        if USAR_LM35:
            self.estado["lm35"]["conectado"] = True
            print("✅ LM35: Listo (simulado)")
    
    def leer_dht11(self):
        """Lee temperatura y humedad del DHT11"""
        if not USAR_DHT11 or self.dht_sensor is None:
            return None, None
        try:
            temp = self.dht_sensor.temperature
            hum = self.dht_sensor.humidity
            self.estado["dht11"]["conectado"] = True
            self.estado["dht11"]["ultimo_error"] = None
            return temp, hum
        except RuntimeError as e:
            self.estado["dht11"]["ultimo_error"] = str(e)
            return None, None
    
    def leer_ultrasonido(self):
        """
        Lee distancia del sensor HC-SR04
        Retorna: distancia en cm (0 si hay error)
        """
        if not USAR_ULTRASONIDO:
            return 0
        try:
            # Enviar pulso de disparo
            GPIO.output(TRIG, False)
            time.sleep(0.05)  # Pausa para estabilizar
            GPIO.output(TRIG, True)
            time.sleep(0.00001)  # Pulso de 10 microsegundos
            GPIO.output(TRIG, False)

            timeout = time.time()
            inicio = time.time()
            fin = time.time()

            # Esperar inicio de señal de retorno (Echo sube a HIGH)
            while GPIO.input(ECHO) == 0:
                inicio = time.time()
                if inicio - timeout > 0.1:  # Timeout de 100ms
                    return 0

            # Esperar fin de señal de retorno (Echo baja a LOW)
            while GPIO.input(ECHO) == 1:
                fin = time.time()
                if fin - inicio > 0.1:  # Timeout de 100ms
                    return 0

            # Calcular distancia: Tiempo * Velocidad del sonido / 2
            # Velocidad del sonido = 343 m/s = 34300 cm/s
            # Factor: 34300 / 2 = 17150 cm/s
            distancia = (fin - inicio) * 17150
            self.estado["ultrasonido"]["conectado"] = True
            self.estado["ultrasonido"]["ultimo_error"] = None
            return round(distancia, 2)
        except Exception as e:
            self.estado["ultrasonido"]["ultimo_error"] = str(e)
            return 0
    
    def leer_mq135(self):
        """Lee nivel de gas del MQ135 (simulado por ahora)"""
        if not USAR_MQ135:
            return 0
        # TODO: Implementar lectura real con ADC (MCP3008)
        return random.randint(10, 50)
    
    def leer_lm35(self):
        """Lee temperatura de precisión del LM35 (simulado por ahora)"""
        if not USAR_LM35:
            return None
        # TODO: Implementar lectura real con ADC (MCP3008)
        return round(random.uniform(20.0, 25.0), 1)
    
    def obtener_estado_sensores(self):
        """Retorna el estado ONLINE/OFFLINE de todos los sensores"""
        return {
            "dht11": "ONLINE" if self.estado["dht11"]["conectado"] else "OFFLINE",
            "ultrasonido": "ONLINE" if self.estado["ultrasonido"]["conectado"] else "OFFLINE",
            "mq135": "ONLINE" if self.estado["mq135"]["conectado"] else "OFFLINE",
            "lm35": "ONLINE" if self.estado["lm35"]["conectado"] else "OFFLINE"
        }
    
    def obtener_modelos(self):
        """Retorna los modelos de sensores configurados"""
        return {
            "modelo_temp_hum": self.estado["dht11"]["modelo"],
            "modelo_distancia": self.estado["ultrasonido"]["modelo"],
            "modelo_gas": self.estado["mq135"]["modelo"],
            "modelo_temp_precision": self.estado["lm35"]["modelo"]
        }
    
    def cleanup(self):
        """Libera recursos de los sensores"""
        if self.dht_sensor:
            try:
                self.dht_sensor.exit()
            except:
                pass
        if USAR_ULTRASONIDO:
            try:
                GPIO.cleanup()
            except:
                pass

# ==========================================
# 🖨️ FUNCIONES DE CONSOLA
# ==========================================
def imprimir_banner():
    """Muestra banner inicial del sistema"""
    print("\n" + "="*60)
    print("🌲 MONITOR FORESTAL - RASPBERRY PI 3")
    print("   Sistema de Detección de Incendios con Ultrasonido")
    print("="*60)

def imprimir_datos(datos_raw, datos_filtrados, info_rpi):
    """Imprime los datos en consola de forma organizada"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    
    print(f"\n┌──────────────────────────────────────────────────────────")
    print(f"│ 📡 LECTURA: {timestamp}")
    print(f"├──────────────────────────────────────────────────────────")
    print(f"│ 🖥️  Dispositivo: {info_rpi['modelo_rpi']}")
    if info_rpi.get('cpu_temp'):
        print(f"│ 🌡️  CPU Temp: {info_rpi['cpu_temp']}°C")
    print(f"├──────────────────────────────────────────────────────────")
    print(f"│ 📊 DATOS CRUDOS (Lectura Directa del Sensor)")
    print(f"│    🌡️  Temperatura: {datos_raw['temp']}°C")
    print(f"│    💧 Humedad: {datos_raw['hum']}%")
    print(f"│    💨 Gas: {datos_raw['gas']} ppm")
    print(f"│    📏 Distancia: {datos_raw['distancia']} cm")
    print(f"├──────────────────────────────────────────────────────────")
    print(f"│ 🔄 DATOS PROCESADOS")
    print(f"│    🌡️  Temperatura: {datos_filtrados['temp']}°C (Promedio 3)")
    print(f"│    💧 Humedad: {datos_filtrados['hum']}% (Promedio 3)")
    print(f"│    💨 Gas: {datos_filtrados['gas']} ppm (Promedio 3)")
    print(f"│    📏 Distancia: {datos_filtrados['distancia']} cm (DIRECTO)")
    print(f"└──────────────────────────────────────────────────────────")

# ==========================================
# 🚀 PROGRAMA PRINCIPAL
# ==========================================
def main():
    imprimir_banner()
    
    # Inicializar componentes del sistema
    info_rpi = obtener_info_raspberry()
    print(f"\n📱 Dispositivo: {info_rpi['modelo_rpi']}")
    print(f"🏠 Hostname: {info_rpi['hostname']}")
    print(f"🐍 Python: {info_rpi['python_version']}")
    
    sensores = GestorSensores()
    filtro = FiltroDatos()
    
    # Configurar cliente MQTT
    print(f"\n🌐 Conectando a MQTT Broker...")
    print(f"   Servidor: {BROKER}")
    print(f"   Puerto: {PORT}")
    print(f"   Topic: {TOPIC}")
    
    client_id = f"RaspberryPi_{info_rpi['hostname']}_{random.randint(1000,9999)}"
    
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id)
    except:
        client = mqtt.Client(client_id)
    
    client.username_pw_set(USER, PASS)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    
    def on_connect(client, userdata, flags, rc):
        if rc == 0:
            print("✅ Conectado exitosamente a HiveMQ Cloud")
        else:
            print(f"❌ Error de conexión. Código: {rc}")
    
    def on_disconnect(client, userdata, rc):
        print("⚠️ Desconectado del broker MQTT")
    
    client.on_connect = on_connect
    client.on_disconnect = on_disconnect
    
    try:
        client.connect(BROKER, PORT)
        client.loop_start()
    except Exception as e:
        print(f"❌ Error de red: {e}")
        return
    
    print("\n" + "="*60)
    print("🔄 INICIANDO MONITOREO CONTINUO")
    print("   Presiona Ctrl+C para detener el sistema")
    print("="*60)
    
    # Bucle principal de monitoreo
    try:
        while True:
            # === 1. LECTURA DE SENSORES ===
            temp_dht, hum_dht = sensores.leer_dht11()
            gas_mq = sensores.leer_mq135()
            temp_lm = sensores.leer_lm35()
            distancia = sensores.leer_ultrasonido()  # Lectura directa sin filtro
            
            # Seleccionar fuente de temperatura (priorizar LM35 si está disponible)
            temp_principal = temp_lm if USAR_LM35 and temp_lm else temp_dht
            
            # Validar datos nulos
            if temp_principal is None:
                temp_principal = 0
            if hum_dht is None:
                hum_dht = 0
            
            # === 2. PREPARAR DATOS CRUDOS ===
            datos_raw = {
                "temp": temp_principal,
                "hum": hum_dht,
                "gas": gas_mq,
                "distancia": distancia
            }
            
            # === 3. PRE-PROCESAMIENTO ===
            # Aplica filtrado selectivo:
            # - Temp/Hum/Gas: Promedio móvil (suavizado)
            # - Distancia: Pasa directo (velocidad)
            datos_filtrados = filtro.procesar(
                temp_principal, hum_dht, gas_mq, distancia
            )
            
            # === 4. ENVÍO DE DATOS ===
            if datos_filtrados["temp"] is not None:
                # Construir payload JSON completo
                payload = {
                    "sensor_id": "Pi_Bosque_01",
                    
                    # Datos procesados (valores estables + distancia instantánea)
                    "temp": datos_filtrados["temp"],
                    "hum": datos_filtrados["hum"] if datos_filtrados["hum"] else 0,
                    "gas": datos_filtrados["gas"] if datos_filtrados["gas"] else 0,
                    "distancia": datos_filtrados["distancia"] if datos_filtrados["distancia"] else 0,
                    
                    # Datos crudos para comparación y depuración
                    "datos_raw": datos_raw,
                    
                    # Estado de conexión de sensores
                    "estado_sensores": sensores.obtener_estado_sensores(),
                    
                    # Información del hardware
                    "hardware": {
                        **obtener_info_raspberry(),
                        **sensores.obtener_modelos()
                    },
                    
                    # Configuración del filtro
                    "filtro": filtro.get_estado(),
                    
                    # Timestamp UNIX
                    "timestamp": time.time()
                }
                
                # Publicar en MQTT
                client.publish(TOPIC, json.dumps(payload))
                
                # Mostrar en consola
                imprimir_datos(datos_raw, datos_filtrados, info_rpi)
            else:
                print(f"⏳ [{datetime.now().strftime('%H:%M:%S')}] Esperando datos válidos del DHT11...")
            
            # Pausa entre lecturas (1.5 segundos para aprovechar respuesta rápida del ultrasonido)
            time.sleep(1.5)
            
    except KeyboardInterrupt:
        print("\n\n🛑 Señal de interrupción recibida. Deteniendo sistema...")
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
    finally:
        print("\n🧹 Limpiando recursos...")
        sensores.cleanup()
        client.loop_stop()
        client.disconnect()
        print("👋 Sistema cerrado correctamente. ¡Hasta pronto!")

if __name__ == "__main__":
    main()
