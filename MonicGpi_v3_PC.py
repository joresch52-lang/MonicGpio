# -*- coding: utf-8 -*-
"""
🌲 DASHBOARD FORESTAL CON IA
Monitor Central de Incendios con Machine Learning
"""
import streamlit as st
import paho.mqtt.client as mqtt
import json
import time
import pandas as pd
import numpy as np
import ssl
from datetime import datetime
from collections import deque
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings('ignore')

# ==========================================
# ⚙️ CONFIGURACIÓN
# ==========================================


# ==========================================
# 🤖 MODELO DE IA - DETECCIÓN DE ANOMALÍAS
# ==========================================
class DetectorAnomalias:
    """Detector de anomalías usando Isolation Forest"""
    def __init__(self, ventana_entrenamiento=50):
        self.modelo = IsolationForest(
            contamination=0.1,
            random_state=42,
            n_estimators=100
        )
        self.scaler = StandardScaler()
        self.historial = deque(maxlen=ventana_entrenamiento)
        self.entrenado = False
        self.min_muestras = 20
    
    def agregar_muestra(self, temp, hum, gas):
        """Agrega una muestra al historial"""
        self.historial.append([temp, hum, gas])
        
        # Entrenar cuando tengamos suficientes datos
        if len(self.historial) >= self.min_muestras and not self.entrenado:
            self._entrenar()
    
    def _entrenar(self):
        """Entrena el modelo con los datos acumulados"""
        datos = np.array(self.historial)
        datos_escalados = self.scaler.fit_transform(datos)
        self.modelo.fit(datos_escalados)
        self.entrenado = True
    
    def predecir(self, temp, hum, gas):
        """Predice si los datos son anómalos"""
        if not self.entrenado:
            return {
                "es_anomalia": False,
                "confianza": 0,
                "estado": "ENTRENANDO",
                "mensaje": f"Recolectando datos ({len(self.historial)}/{self.min_muestras})"
            }
        
        muestra = np.array([[temp, hum, gas]])
        muestra_escalada = self.scaler.transform(muestra)
        
        prediccion = self.modelo.predict(muestra_escalada)[0]
        score = self.modelo.decision_function(muestra_escalada)[0]
        
        # Convertir score a probabilidad (aproximación)
        confianza = min(100, max(0, int((1 - score) * 50 + 50)))
        
        es_anomalia = prediccion == -1
        
        return {
            "es_anomalia": es_anomalia,
            "confianza": confianza,
            "score": round(score, 3),
            "estado": "ALERTA" if es_anomalia else "NORMAL",
            "mensaje": "⚠️ Patrón inusual detectado" if es_anomalia else "✅ Valores normales"
        }
    
    def get_estadisticas(self):
        """Retorna estadísticas del modelo"""
        if len(self.historial) == 0:
            return None
        datos = np.array(self.historial)
        return {
            "muestras": len(self.historial),
            "temp_media": round(np.mean(datos[:, 0]), 1),
            "temp_std": round(np.std(datos[:, 0]), 2),
            "hum_media": round(np.mean(datos[:, 1]), 1),
            "hum_std": round(np.std(datos[:, 1]), 2),
            "gas_media": round(np.mean(datos[:, 2]), 1),
            "gas_std": round(np.std(datos[:, 2]), 2),
        }

# ==========================================
# 🧠 ANÁLISIS DE RIESGO MEJORADO
# ==========================================
def analizar_riesgo_avanzado(temp, gas, hum, distancia, prediccion_ia):
    """Análisis de riesgo combinando reglas + IA + proximidad"""
    score = 0
    factores = []
    
    # Reglas basadas en umbrales
    if temp > 45:
        score += 40
        factores.append("🔥 Temperatura crítica")
    elif temp > 35:
        score += 20
        factores.append("⚠️ Temperatura elevada")
    
    if gas > 300:
        score += 35
        factores.append("💨 Nivel de gas peligroso")
    elif gas > 150:
        score += 15
        factores.append("💨 Gas elevado")
    
    if hum < 20:
        score += 15
        factores.append("💧 Humedad muy baja")
    elif hum < 35:
        score += 5
        factores.append("💧 Humedad baja")
    
    # Bonus por detección de IA
    if prediccion_ia["es_anomalia"]:
        score += 20
        factores.append("🤖 IA detectó anomalía")
    
    # Detección de proximidad
    mensaje_extra = ""
    if distancia > 0 and distancia < 10:
        factores.append("🚶 Movimiento detectado < 10cm")
        mensaje_extra = " | 🚶 MOVIMIENTO DETECTADO"
    
    # Determinar nivel de alerta
    if score >= 60:
        return {
            "nivel": "CRÍTICO",
            "color": "inverse",
            "icono": "🔥",
            "mensaje": f"¡ALERTA DE INCENDIO!{mensaje_extra}",
            "score": score,
            "factores": factores
        }
    elif score >= 30:
        return {
            "nivel": "ADVERTENCIA",
            "color": "off",
            "icono": "⚠️",
            "mensaje": f"Condiciones Peligrosas{mensaje_extra}",
            "score": score,
            "factores": factores
        }
    else:
        return {
            "nivel": "NORMAL",
            "color": "normal",
            "icono": "✅",
            "mensaje": f"Sistema Estable{mensaje_extra}",
            "score": score,
            "factores": factores
        }

# ==========================================
# 🖥️ CONFIGURACIÓN DE PÁGINA
# ==========================================
st.set_page_config(
    page_title="🌲 Monitor Forestal IA",
    page_icon="🌲",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS Personalizado
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        background: linear-gradient(90deg, #1e5631 0%, #2e7d32 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-align: center;
        padding: 1rem 0;
    }
    .status-card {
        padding: 1rem;
        border-radius: 10px;
        margin: 0.5rem 0;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem;
        border-radius: 15px;
        color: white;
        text-align: center;
    }
    .sensor-online { color: #4caf50; font-weight: bold; }
    .sensor-offline { color: #f44336; font-weight: bold; }
    .ia-badge {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 0.3rem 0.8rem;
        border-radius: 20px;
        font-size: 0.85rem;
    }
    div[data-testid="stMetricValue"] { font-size: 2rem; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# 🎨 INTERFAZ
# ==========================================
st.markdown('<h1 class="main-header">🌲 Monitor Central de Incendios</h1>', unsafe_allow_html=True)
st.markdown('<p style="text-align:center; color:#666;">Sistema de Detección con Inteligencia Artificial</p>', unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("### ⚙️ Configuración")
    st.markdown(f"**Broker:** `{BROKER[:20]}...`")
    st.markdown(f"**Topic:** `{TOPIC}`")
    st.markdown("---")
    st.markdown("### 🤖 Modelo IA")
    st.markdown("**Algoritmo:** Isolation Forest")
    st.markdown("**Propósito:** Detectar patrones anómalos en sensores")
    st.markdown("---")
    st.markdown("### 📊 Pre-procesamiento")
    st.markdown("✓ Promedio móvil (3 muestras)")
    st.markdown("✓ Filtro de ruido")
    st.markdown("✓ Detección de anomalías")
    st.markdown("✓ Detección de proximidad")

st.markdown("---")

# Contenedores principales
col_estado, col_dispositivo = st.columns([1, 2])
estado_rpi = col_estado.empty()
info_dispositivo = col_dispositivo.empty()

st.markdown("---")

# KPIs principales (AHORA SON 5 COLUMNAS)
st.markdown("### 📊 Métricas en Tiempo Real")
col1, col2, col3, col4, col5 = st.columns(5)
kpi_temp = col1.empty()
kpi_hum = col2.empty()
kpi_gas = col3.empty()
kpi_dist = col4.empty()  # Nueva columna para el Ultrasonido
kpi_riesgo = col5.empty()

# Banner de alertas
st.markdown("### 📢 Estado del Sistema")
col_alert, col_ia = st.columns([2, 1])
alert_banner = col_alert.empty()
ia_status = col_ia.empty()

st.markdown("---")

# Sección de Hardware y Sensores
st.markdown("### 🛠️ Hardware y Sensores")
col_hw, col_sens, col_stats = st.columns(3)

info_hardware = col_hw.empty()
tabla_sensores = col_sens.empty()
stats_ia = col_stats.empty()

# Historial de datos
st.markdown("---")
st.markdown("### 📈 Análisis de IA")
col_factores, col_historial = st.columns([1, 2])
factores_riesgo = col_factores.empty()
grafico_historial = col_historial.empty()

# ==========================================
# 🔌 CONEXIÓN MQTT
# ==========================================
@st.cache_resource
def obtener_recursos():
    memoria = {
        "ultimo_dato": None,
        "ultima_recepcion": 0,
        "historial_temp": deque(maxlen=100),
        "historial_hum": deque(maxlen=100),
        "historial_gas": deque(maxlen=100),
        "historial_dist": deque(maxlen=100),
        "timestamps": deque(maxlen=100)
    }
    
    detector_ia = DetectorAnomalias(ventana_entrenamiento=50)

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            memoria["ultimo_dato"] = payload
            memoria["ultima_recepcion"] = time.time()
            
            # Guardar historial
            t = payload.get('temp', 0)
            h = payload.get('hum', 0)
            g = payload.get('gas', 0)
            d = payload.get('distancia', 0)
            
            memoria["historial_temp"].append(t)
            memoria["historial_hum"].append(h)
            memoria["historial_gas"].append(g)
            memoria["historial_dist"].append(d)
            memoria["timestamps"].append(datetime.now())
            
            # Alimentar modelo IA
            detector_ia.agregar_muestra(t, h, g)
        except:
            pass

    client_id = f"Dashboard_{datetime.now().strftime('%S%f')}"
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, client_id)
    except:
        client = mqtt.Client(client_id)

    client.username_pw_set(USER, PASS)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.on_message = on_message

    try:
        client.connect(BROKER, PORT)
        client.subscribe(TOPIC)
        client.loop_start()
    except:
        pass

    return client, memoria, detector_ia

_, memoria, detector_ia = obtener_recursos()

# ==========================================
# 🔄 BUCLE PRINCIPAL
# ==========================================
while True:
    data = memoria["ultimo_dato"]
    ahora = time.time()
    ultima_vez = memoria["ultima_recepcion"]
    segundos_atras = ahora - ultima_vez

    # === ONLINE ===
    if data and segundos_atras < TIEMPO_LIMITE_DESCONEXION:
        t = data.get('temp', 0)
        h = data.get('hum', 0)
        g = data.get('gas', 0)
        d = data.get('distancia', 0)  # Leer distancia del sensor ultrasonido
        hw = data.get('hardware', {})
        sensores = data.get('estado_sensores', {})
        filtro_info = data.get('filtro', {})
        datos_raw = data.get('datos_raw', {})

        # Predicción IA
        prediccion = detector_ia.predecir(t, h, g)
        
        # Análisis de riesgo combinado (incluye distancia)
        riesgo = analizar_riesgo_avanzado(t, g, h, d, prediccion)

        # Estado conexión
        estado_rpi.success(f"🟢 **ONLINE** | Última lectura: hace {int(segundos_atras)}s")
        
        # Info dispositivo
        with info_dispositivo.container():
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"**💻 Dispositivo:** {hw.get('modelo_rpi', 'N/A')}")
            c2.markdown(f"**🌡️ CPU:** {hw.get('cpu_temp', 'N/A')}°C")
            c3.markdown(f"**🐍 Python:** {hw.get('python_version', 'N/A')}")

        # KPIs (5 columnas)
        kpi_temp.metric(
            "🌡️ Temperatura",
            f"{t} °C",
            f"Raw: {datos_raw.get('temp', t)}°C",
            delta_color="inverse" if t > 35 else "normal"
        )
        kpi_hum.metric(
            "💧 Humedad",
            f"{h} %",
            f"Raw: {datos_raw.get('hum', h)}%"
        )
        kpi_gas.metric(
            "💨 Calidad Aire",
            f"{g} ppm",
            f"Raw: {datos_raw.get('gas', g)} ppm",
            delta_color="inverse" if g > 150 else "normal"
        )
        kpi_dist.metric(
            "📏 Proximidad",
            f"{d} cm",
            f"HC-SR04",
            delta_color="inverse" if d > 0 and d < 10 else "normal"
        )
        kpi_riesgo.metric(
            "⚡ Riesgo",
            f"{riesgo['score']}%",
            riesgo['nivel'],
            delta_color=riesgo['color']
        )

        # Alertas
        if riesgo['nivel'] == "CRÍTICO":
            alert_banner.error(f"## {riesgo['icono']} {riesgo['mensaje']}")
        elif riesgo['nivel'] == "ADVERTENCIA":
            alert_banner.warning(f"## {riesgo['icono']} {riesgo['mensaje']}")
        else:
            alert_banner.success(f"## {riesgo['icono']} {riesgo['mensaje']}")

        # Estado IA
        with ia_status.container():
            st.markdown("**🤖 Análisis IA**")
            if prediccion['estado'] == "ENTRENANDO":
                st.info(prediccion['mensaje'])
            elif prediccion['es_anomalia']:
                st.error(f"⚠️ ANOMALÍA (conf: {prediccion['confianza']}%)")
            else:
                st.success(f"✅ Normal (conf: {prediccion['confianza']}%)")

        # Hardware info
        with info_hardware.container():
            st.markdown("**📟 Información del Sistema**")
            st.markdown(f"- **Modelo:** {hw.get('modelo_rpi', 'N/A')}")
            st.markdown(f"- **Host:** {hw.get('hostname', 'N/A')}")
            st.markdown(f"- **Filtro:** Promedio de {filtro_info.get('ventana', 3)} muestras")

        # Tabla de sensores (actualizada para incluir ultrasonido)
        with tabla_sensores.container():
            st.markdown("**📡 Estado de Sensores**")
            df = pd.DataFrame({
                "Sensor": ["DHT11", "HC-SR04", "MQ-135", "LM35"],
                "Tipo": ["Temp/Hum", "Distancia", "Gas", "Temp Precisión"],
                "Modelo": [
                    hw.get('modelo_temp_hum', 'N/A'),
                    hw.get('modelo_distancia', 'N/A'),
                    hw.get('modelo_gas', 'N/A'),
                    hw.get('modelo_temp_precision', 'N/A')
                ],
                "Estado": [
                    sensores.get('dht11', 'N/A'),
                    sensores.get('ultrasonido', 'N/A'),
                    sensores.get('mq135', 'N/A'),
                    sensores.get('lm35', 'N/A')
                ]
            })
            st.dataframe(df, hide_index=True, use_container_width=True)

        # Estadísticas IA
        stats = detector_ia.get_estadisticas()
        with stats_ia.container():
            st.markdown("**📊 Estadísticas del Modelo**")
            if stats:
                st.markdown(f"- **Muestras:** {stats['muestras']}")
                st.markdown(f"- **Temp media:** {stats['temp_media']}°C ±{stats['temp_std']}")
                st.markdown(f"- **Hum media:** {stats['hum_media']}% ±{stats['hum_std']}")
            else:
                st.info("Recolectando datos...")

        # Factores de riesgo
        with factores_riesgo.container():
            st.markdown("**🎯 Factores de Riesgo Detectados**")
            if riesgo['factores']:
                for f in riesgo['factores']:
                    st.markdown(f"- {f}")
            else:
                st.markdown("- Ninguno detectado ✓")

        # Gráfico historial (ahora incluye distancia)
        with grafico_historial.container():
            if len(memoria["historial_temp"]) > 5:
                df_hist = pd.DataFrame({
                    "Temperatura": list(memoria["historial_temp"]),
                    "Humedad": list(memoria["historial_hum"]),
                    "Gas": list(memoria["historial_gas"]),
                    "Distancia": list(memoria["historial_dist"])
                })
                st.line_chart(df_hist, height=200)

    # === OFFLINE ===
    elif data and segundos_atras >= TIEMPO_LIMITE_DESCONEXION:
        estado_rpi.error(f"🔴 **OFFLINE** | Perdido hace {int(segundos_atras)}s")
        info_dispositivo.warning("⚠️ Raspberry Pi no responde")
        
        kpi_temp.metric("🌡️ Temperatura", "--", "Sin señal")
        kpi_hum.metric("💧 Humedad", "--", "Sin señal")
        kpi_gas.metric("💨 Calidad Aire", "--", "Sin señal")
        kpi_dist.metric("📏 Proximidad", "--", "Sin señal")
        kpi_riesgo.metric("⚡ Riesgo", "--", "Sin datos")
        
        alert_banner.error("## 🔌 SISTEMA DESCONECTADO")
        ia_status.warning("IA pausada")
        
        tabla_sensores.empty()
        info_hardware.info("Esperando reconexión...")

    # === ESPERANDO ===
    else:
        estado_rpi.info("⏳ Buscando dispositivo...")
        alert_banner.info("⏳ Esperando primera conexión con Raspberry Pi...")

    time.sleep(1)

