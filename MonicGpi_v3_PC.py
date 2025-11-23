import streamlit as st
import paho.mqtt.client as mqtt
import json
import time
import pandas as pd
import ssl
from datetime import datetime

# ==========================================
# ⚙️ CONFIGURACIÓN
# ==========================================
BROKER = "6071f9f543bb41f297470c8742588c93.s1.eu.hivemq.cloud"
PORT = 8883
USER = "jore746"
PASS = "Wildbl00d$746"
TOPIC = "bosque/sensores"

# ==========================================
# 🧠 LÓGICA
# ==========================================
def analizar_riesgo(temp, gas, hum):
    score = 0
    if temp > 45: score += 50    
    elif temp > 35: score += 20  
    if gas > 300: score += 40    
    if hum < 20: score += 10     
    
    if score >= 60: return "PELIGRO CRÍTICO", "inverse", "🔥 INCENDIO DETECTADO 🔥"
    elif score >= 30: return "ADVERTENCIA", "off", "⚠️ Condiciones Peligrosas"
    else: return "NORMAL", "normal", "✅ Sistema Estable"

# ==========================================
# 🖥️ INTERFAZ GRÁFICA
# ==========================================
st.set_page_config(page_title="Monitor Forestal", page_icon="🌲", layout="wide")

st.title("🌲 Sistema de Detección Temprana de Incendios")
st.markdown("---")

col1, col2, col3 = st.columns(3)
kpi_temp = col1.empty()
kpi_hum = col2.empty()
kpi_gas = col3.empty()

st.markdown("### 📢 Estado del Sistema")
alert_banner = st.empty()
reloj_container = st.empty()
st.markdown("### 📡 Estado de Sensores")
status_container = st.empty()

# ==========================================
# 🔌 CONEXIÓN MQTT (BUZÓN PERSISTENTE)
# ==========================================

@st.cache_resource
def obtener_recursos_mqtt():
    # Creamos un diccionario compartido que SOBREVIVE a los refrescos
    # Este es el "buzón" que no se borrará
    memoria_compartida = {"ultimo_dato": None}

    def on_message(client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode())
            # Guardamos el dato en el buzón compartido
            memoria_compartida["ultimo_dato"] = payload
            # print(f"Recibido: {payload}") # Debug
        except:
            pass

    cliente_id = f"PC_Monitor_{datetime.now().strftime('%S%f')}"
    
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1, cliente_id)
    except:
        client = mqtt.Client(cliente_id)

    client.username_pw_set(USER, PASS)
    client.tls_set(cert_reqs=ssl.CERT_NONE)
    client.on_message = on_message
    
    try:
        client.connect(BROKER, PORT)
        client.subscribe(TOPIC)
        client.loop_start()
        print("✅ Conexión Iniciada.")
    except Exception as e:
        print(f"❌ Error: {e}")

    # Devolvemos tanto el cliente como la memoria para usarla abajo
    return client, memoria_compartida

# Recuperamos la conexión y la memoria desde la caché
_, memoria = obtener_recursos_mqtt()

# ==========================================
# 🔄 BUCLE VISUAL
# ==========================================
while True:
    # Leemos directamente del buzón compartido
    data = memoria["ultimo_dato"]
    hora_actual = datetime.now().strftime("%H:%M:%S")
    
    if data:
        t = data.get('temp', 0)
        h = data.get('hum', 0)
        g = data.get('gas', 0)
        activos = data.get('activos', {})
        
        estado, color_delta, mensaje = analizar_riesgo(t, g, h)
        
        kpi_temp.metric("Temperatura", f"{t} °C", delta_color="inverse")
        kpi_hum.metric("Humedad", f"{h} %")
        kpi_gas.metric("Calidad Aire (CO2)", f"{g} ppm", delta_color=color_delta)
        
        if "PELIGRO" in estado:
            alert_banner.error(f"## {mensaje}")
        elif "ADVERTENCIA" in estado:
            alert_banner.warning(f"## {mensaje}")
        else:
            alert_banner.success(f"## {mensaje}")
            
        reloj_container.success(f"📡 RECIBIENDO DATOS | Último paquete: {hora_actual}")
        
        if activos:
            status_container.table(pd.DataFrame([activos]))
            
    else:
        alert_banner.info("⏳ Esperando primer dato de Raspberry Pi...")
        reloj_container.caption(f"Buscando señal... ({hora_actual})")
    
    time.sleep(1)