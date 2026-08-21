import streamlit as st
import pandas as pd
from sqlalchemy import create_engine
import psycopg2
import json
import urllib.parse
from datetime import datetime, timedelta
import plotly.graph_objects as go
import time
import pytz
from zoneinfo import ZoneInfo

# Configuración de página optimizada para móviles
st.set_page_config(
    page_title="Sistema Scada Móvil", 
    page_icon="https://www.miaa.mx/favicon.ico", 
    layout="wide",
    initial_sidebar_state="collapsed"
)

import streamlit.components.v1 as components
components.html(
    """
    <script>
        // Usamos setInterval para asegurar que el script se aplique aunque Streamlit tarde en cargar
        var interval = setInterval(function() {
            var elements = window.parent.document.querySelectorAll('button[data-testid="stExpander"]');
            if (elements.length > 0) {
                elements.forEach(function(el) {
                    el.style.color = "#00d4ff";
                    el.style.fontWeight = "bold";
                });
                clearInterval(interval); // Detener el bucle una vez aplicado
            }
        }, 500);
    </script>
    """,
    height=0
)

# Autorrefresco automático cada 5 minutos (300 segundos)
if 'scada_refresh' not in st.session_state:
    st.session_state.scada_refresh = 0

# 0. SECCION ---------------------------------------- SISTEMA DE AUTENTICACIÓN HUD DEFINITIVO --------------------------------------------------------------------
if 'autenticado' not in st.session_state:
    query_params = st.query_params
    if query_params.get("access") == "granted":
        st.session_state.autenticado = True
        st.session_state.rol = query_params.get("role", "usuario")
    else:
        st.session_state.autenticado = False

if 'fase_carga' not in st.session_state:
    st.session_state.fase_carga = False

@st.cache_resource
def get_mysql_telemetria_engine():
    try:
        c = st.secrets["mysql_telemetria"]
        pwd = urllib.parse.quote_plus(c["password"])
        engine = create_engine(
            f"mysql+mysqlconnector://{c['user']}:{pwd}@{c['host']}/{c['database']}",
            pool_recycle=3600,
            pool_pre_ping=True
        )
        return engine
    except Exception as e:
        st.error(f"⚠️ ERROR CRÍTICO DE CONEXIÓN TELEMETRÍA: {e}")
        return None


from sqlalchemy import create_engine, event
@st.cache_resource
def get_mysql_scada_engine():
    try:
        c = st.secrets["mysql_scada"]
        pwd = urllib.parse.quote_plus(c["password"])
        engine = create_engine(
            f"mysql+mysqlconnector://{c['user']}:{pwd}@{c['host']}/{c['database']}",
            pool_recycle=3600,
            pool_pre_ping=True
        )
        @event.listens_for(engine, "connect")
        def set_big_selects(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("SET SESSION SQL_BIG_SELECTS=1;")
            cursor.close()
        
        with engine.connect() as conn: pass 

        return engine
    except Exception as e:
        st.error(f"⚠️ ERROR CRÍTICO DE CONEXIÓN SCADA: {e}")
        return None

@st.cache_resource
def get_postgres_engine():
    try: 
        conn = psycopg2.connect(**st.secrets["postgres"])
        return conn
    except Exception as e: 
        st.error(f"Error de conexión Postgres: {e}")
        return None

def verificar_credenciales(usuario_input, password_input):
    try:
        engine = get_mysql_telemetria_engine()
        if engine is None: return None
        query = f"SELECT password, tipo_usuario FROM usuarios WHERE usuario = '{usuario_input}'"
        df_user = pd.read_sql(query, engine)
        if not df_user.empty and str(password_input) == str(df_user['password'].iloc[0]):
            return df_user['tipo_usuario'].iloc[0]
        return None
    except Exception as e:
        st.error(f"Error al consultar usuario: {e}")
        return None

#1. SECCION -------------------------------------------------------ESTILO VISUAL HUD AJUSTADO PARA MÓVIL ----------------------------------------------------------------------------------
st.markdown("""
<style>
    /* Configuración base */
    .stApp { background-color: #050a10 !important; }
    .block-container { padding: 10px !important; max-width: 100% !important; }
    header, footer { visibility: hidden !important; }
    
    /* MODIFICACIÓN EXCLUSIVA PARA ELEVAR EL LOGIN */
    .login-container {
        margin-top: -30px !important;
    }
    
    /* EFECTOS Y ANIMACIONES */
    .visual-core { position: relative; width: 280px; height: 280px; margin: auto; }
    .ring { position: absolute; border-radius: 50%; border: 4px solid transparent; animation: spin var(--d) linear infinite; }
    .r1 { width: 100%; height: 100%; border-top: 6px solid #00d4ff; border-bottom: 6px solid #00d4ff; --d: 4s; }
    .r2 { width: 78%; height: 78%; top: 11%; left: 11%; border: 2px dashed #00d4ff; --d: 8s; animation-direction: reverse; }
    .center-logo { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center; }
    .logo-miaa { width: 130px; filter: drop-shadow(0 0 10px #00d4ff); }
    @keyframes spin { 100% { transform: rotate(360deg); } }

    /* ESTILO UNIFICADO DE INPUTS */
    div[data-testid="stTextInputRootElement"] {
        background-color: #0d1b2a !important;
        border: 1px solid #1f4068 !important;
        border-radius: 0px !important;
        box-shadow: none !important;
        height: 40px !important;
    }
    div[data-testid="stTextInputRootElement"] div[data-baseweb="base-input"] {
        background-color: transparent !important;
    }
    .stTextInput input {
        background-color: transparent !important;
        color: #00d4ff !important;
        font-size: 15px !important;
    }
    div[data-testid="stTextInputRootElement"]:focus-within {
        border: 1px solid #00d4ff !important;
    }

    .stButton button { 
        background: #00d4ff !important; color: #050a10 !important; font-weight: bold !important; 
        width: 100%; height: 45px; border: none !important; 
    }
    .login-box { 
        background: rgba(0, 212, 255, 0.05); border-left: 6px solid #00d4ff; 
        padding: 20px; margin-top: 0px; width: 100%; 
    }
    .logo-header {
        width: 130px !important;
        height: auto !important;
        display: block;
        margin: 0 auto 20px auto;
    }
</style>
""", unsafe_allow_html=True)

if not st.session_state.autenticado:
    # Contenedor con clase para aplicar el margen superior negativo exclusivamente al login
    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    col_vis, col_log = st.columns([1, 1])
    with col_vis:
        st.markdown('''
        <div class="visual-core" style="margin-top: 10px;">
            <div class="ring r1"></div><div class="ring r2"></div>
            <div class="center-logo">
                <img src="https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg" class="logo-miaa">
            </div>
        </div>
        ''', unsafe_allow_html=True)

    with col_log:
        if not st.session_state.fase_carga:
            st.markdown('<div class="login-box">', unsafe_allow_html=True)
            st.markdown('<h2 style="color:#00d4ff; font-size:16px; margin-top:0px;">// CREDENCIALES SCADA</h2>', unsafe_allow_html=True)
            with st.form("login_form"):
                u = st.text_input("USUARIO")
                p = st.text_input("PASSWORD", type="password")
                if st.form_submit_button("ACCEDER"):
                    rol = verificar_credenciales(u, p)
                    if rol:
                        st.session_state.temp_rol = rol
                        st.session_state.fase_carga = True
                        st.rerun()
                    else:
                        st.error("❌ ACCESO DENEGADO")
            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="login-box">', unsafe_allow_html=True)
            st.markdown('<h2 style="color:#00d4ff; font-size:16px;">// CONFIGURANDO ENTORNO MÓVIL...</h2>', unsafe_allow_html=True)
            st.session_state.autenticado = True
            st.session_state.rol = st.session_state.temp_rol
            st.session_state.fase_carga = False
            st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# 2. SECCION -----------------------------------------------   FUNCIONES DE EXTRACCIÓN DE DATOS SCADA & POSTGRES -----------------------------------------------------------
def cargar_datos_scada(lista_tags):
    engine = get_mysql_scada_engine()
    if not engine or not lista_tags: return {}
    try:
        tags_str = "', '".join(lista_tags)
        query = f"""
            SELECT r.NAME, h.VALUE, h.FECHA 
            FROM VfiTagNumHistory_Ultimo h 
            JOIN VfiTagRef r ON h.GATEID = r.GATEID 
            WHERE r.NAME IN ('{tags_str}') 
            AND h.FECHA = (SELECT MAX(FECHA) FROM VfiTagNumHistory_Ultimo WHERE GATEID = h.GATEID)
        """
        df = pd.read_sql(query, engine)
        return {row['NAME']: (row['VALUE'], row['FECHA'].strftime('%d/%m/%Y %H:%M') if row['FECHA'] else "N/A") for _, row in df.iterrows()}
    except:
        return {}

def obtener_historia_7_dias(tag_name):
    engine = get_mysql_scada_engine()
    if not engine or not tag_name: return pd.DataFrame()
    try:
        query = f"""
            SELECT h.FECHA, h.VALUE 
            FROM vfitagnumhistory h
            JOIN VfiTagRef r ON h.GATEID = r.GATEID
            WHERE r.NAME = '{tag_name}'
            AND h.FECHA >= DATE_SUB(NOW(), INTERVAL 7 DAY)
            ORDER BY h.FECHA ASC
        """
        df = pd.read_sql(query, engine)
        df['FECHA'] = pd.to_datetime(df['FECHA']) 
        return df
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def cargar_sectores_poligonos():
    conn = psycopg2.connect(**st.secrets["postgres"])
    if not conn: return []
    try:
        query = """
            SELECT sector, "Pozos_Sector", 
                   "Superficie", "Long_Red", "Vol_Prod", "U_Domesticos", 
                   "U_NoDom", "U_Tot", "Poblacion", "Cons_m3", 
                   "Faltas_Agua", "Fugas_Tot", "FTC", "FTA", 
                   "Vol_Medid", "Vol_Fact", "Kwh", "costoKw-hr", 
                   "Recaudacion", "Dotacion", "Balance_Estimado",
                   ST_AsGeoJSON(ST_Transform(geom, 4326)) as geo 
            FROM "Sectorizacion"."Sectores_hidr"
        """
        df = pd.read_sql(query, conn)
        return df.to_dict('records')
    except Exception as e:
        st.error(f"Error al cargar sectores: {e}")
        return []
    finally:
        if conn:
            conn.close()

@st.cache_data(ttl=3600) 
def cargar_mapa_pozos_desde_db():
    engine = get_mysql_telemetria_engine()
    if not engine: return {}
    try:
        df_pozos = pd.read_sql("SELECT * FROM Diccionario_de_pozos", engine)
        nuevo_mapa = {}
        for _, row in df_pozos.iterrows():
            nuevo_mapa[row['Pozos']] = {
                "bomba": row['bomba'], "caudal": row['caudal'], "presion": row['presion'],
                "sumergencia": row['sumergencia'], "nivel_dinamico": row['nivel_dinamico'],
                "nivel_tanque": row['nivel_tanque'], "columna": row['columna'],
                "h_arranque": row['H_arranque'], "h_paro": row['H_paro'],
                "voltajes_l": [row['voltaje_L1'], row['voltaje_L2'], row['voltaje_L3']],
                "amperajes_l": [row['amperaje_L1'], row['amperaje_L2'], row['amperaje_L3']],
                "totalizado": row['totalizado']
            }
        return nuevo_mapa
    except: return {}

@st.cache_data(ttl=3600)
def cargar_tanques_desde_db():
    engine = get_mysql_telemetria_engine()
    if not engine: return {}
    try:
        df_tq = pd.read_sql("SELECT * FROM Diccionario_de_tanques", engine)
        nuevo_mapa_tq = {}
        for _, row in df_tq.iterrows():
            n_max = float(row['Nivel_max']) if row.get('Nivel_max') is not None else 1.0
            if n_max <= 0: n_max = 1.0
            nuevo_mapa_tq[row['Nombre_tq']] = {
                "nombre": row['Nombre_tq'], "tag_nivel": row['nivel_tanque'], "nivel_max": n_max, "sitios": row['Sitios']
            }
        return nuevo_mapa_tq
    except: return {}

@st.cache_data(ttl=3600)
def cargar_rebombeos_desde_db():
    engine = get_mysql_telemetria_engine()
    if not engine: return {}
    try:
        df_rb = pd.read_sql("SELECT * FROM Diccionario_de_rebombeos", engine)
        nuevo_mapa_rb = {}
        df_filtrado = df_rb[df_rb['Telemetria'].str.strip() == "Con telemetria"]
        
        for _, row in df_filtrado.iterrows():
            nuevo_mapa_rb[row['Rebombeo']] = {
                "nombre": row['Nombre_rebombeo'], 
                "telemetria": row['Telemetria'], 
                "presion": row['presion'], 
                "nivel_tanque": row['nivel_tanque'],
                "voltajes_l": [row['voltaje_L1'], row['voltaje_L2'], row['voltaje_L3']],
                "amperajes_l": [row['amperaje_L1'], row['amperaje_L2'], row['amperaje_L3']],
                "setpoint_dia": row['setpoint_dia'],
                "setpoint_noche": row['setpoint_noche']
            }
        return nuevo_mapa_rb
    except Exception as e:
        st.error(f"Error cargando rebombeos: {e}")
        return {}

@st.cache_data(ttl=3600)
def cargar_puntos_de_control_desde_db():
    engine = get_mysql_telemetria_engine()
    if not engine: return {}
    try:
        df = pd.read_sql("SELECT * FROM Diccionario_puntos_de_control", engine)
        d_res = {}
        for _, r in df.iterrows():
            id_reg_val = r.get('Serie', r.get('Registrador', 'ID'))
            d_res[str(id_reg_val)] = {
                "nombre": str(r.get('Domicilio', r.get('Nombre_registrador', 'S/N'))),
                "sector": str(r['Sector']).split('.')[0].strip(),
                "tag_p1": r.get('Presion_1'), "tag_p2": r.get('Presion_2'), "tag_q": r.get('Caudal'),
                "tag_vbat": r.get('bateria'), "tag_idx": r.get('indice'), "Serie": str(id_reg_val)
            }
        return d_res
    except: return {}

@st.cache_data(ttl=3600)
def cargar_puntos_criticos_desde_db():
    engine = get_mysql_telemetria_engine()
    if not engine: return {}
    try:
        df = pd.read_sql("SELECT * FROM Diccionario_puntos_criticos", engine)
        d_res = {}
        for _, r in df.iterrows():
            id_reg = r.get('Serie', r.get('Registrador', 'ID'))
            d_res[str(id_reg)] = {
                "nombre": str(r.get('Colonia', 'S/C')), "Domicilio": str(r.get('Domicilio', 'Sin Domicilio')),
                "sector": str(r['Sector']).split('.')[0].strip(), "tag_p1": r.get('Presion_1'), "tag_q": r.get('Caudal')
            }
        return d_res
    except: return {}

@st.cache_data(ttl=3600)
def cargar_vrp_desde_db():
    engine = get_mysql_telemetria_engine()
    if not engine: return {}
    try:
        df = pd.read_sql("SELECT * FROM Diccionario_vrp", engine)
        d_res = {}
        for _, r in df.iterrows():
            id_val = r.get('Serie', 'ID_VRP')
            d_res[str(id_val)] = {
                "nombre": str(r.get('Domicilio', 'S/N')), "sector": str(r['Sector']).split('.')[0].strip(),
                "tag_p1": r.get('Presion_1'), "tag_p2": r.get('Presion_2'), "tag_q": r.get('Caudal'), "Serie": str(id_val)
            }
        return d_res
    except: return {}

# 3. SECCION ----------------------------------------- PROCESAMIENTO E INTERFAZ DE ACTIVOS -----------------------------------------------------------------------
sectores = cargar_sectores_poligonos()
mapa_pozos_dict = cargar_mapa_pozos_desde_db()
mapa_tanques_dict = cargar_tanques_desde_db()
mapa_rebombeos_dict = cargar_rebombeos_desde_db()

def reset_pozo():
    if st.session_state.opt_pozo != "-- Seleccionar --":
        st.session_state.opt_tanque = "-- Seleccionar --"
        st.session_state.opt_rebombeo = "-- Seleccionar --"
        st.session_state.opt_sector = "-- Seleccionar --"
        st.session_state.activo_tipo = "Pozo"
        st.session_state.activo_id = st.session_state.opt_pozo

def reset_tanque():
    if st.session_state.opt_tanque != "-- Seleccionar --":
        st.session_state.opt_pozo = "-- Seleccionar --"
        st.session_state.opt_rebombeo = "-- Seleccionar --"
        st.session_state.opt_sector = "-- Seleccionar --"
        st.session_state.activo_tipo = "Tanque"
        st.session_state.activo_id = st.session_state.opt_tanque

def reset_rebombeo():
    mapa = cargar_rebombeos_desde_db()
    nombres_a_id = {v['nombre']: k for k, v in mapa.items()}
    seleccion = st.session_state.opt_rebombeo
    
    if seleccion != "-- Seleccionar --":
        st.session_state.opt_pozo = "-- Seleccionar --"
        st.session_state.opt_tanque = "-- Seleccionar --"
        st.session_state.opt_sector = "-- Seleccionar --"
        st.session_state.activo_tipo = "Rebombeo"
        st.session_state.activo_id = nombres_a_id.get(seleccion)
    else:
        st.session_state.activo_id = "-- Seleccionar --"

def reset_sector():
    if st.session_state.opt_sector != "-- Seleccionar --":
        st.session_state.opt_pozo = "-- Seleccionar --"
        st.session_state.opt_tanque = "-- Seleccionar --"
        st.session_state.opt_rebombeo = "-- Seleccionar --"
        st.session_state.activo_tipo = "Sector"
        st.session_state.activo_id = st.session_state.opt_sector

if 'activo_tipo' not in st.session_state:
    st.session_state.activo_tipo = None
    st.session_state.activo_id = None

st.markdown('''
    <img src="https://raw.githubusercontent.com/Miaa-Aguascalientes/Logos/38504978c8f77a4dac38ad476f74dbdee6af2cad/LogoMIAA.svg" 
         class="logo-header">
''', unsafe_allow_html=True)

st.markdown('<h2 style="color:#00d4ff; font-size:18px; margin-bottom:12px;">🖥️ Panel Scada</h2>', unsafe_allow_html=True)

c1, c2 = st.columns(2)
with c1:
    st.selectbox("💧 Pozos", ["-- Seleccionar --"] + sorted(list(mapa_pozos_dict.keys())), key="opt_pozo", on_change=reset_pozo)
    st.selectbox("🛢️  Tanques", ["-- Seleccionar --"] + sorted(list(mapa_tanques_dict.keys())), key="opt_tanque", on_change=reset_tanque)

with c2:
    mapa_rebombeos_dict = cargar_rebombeos_desde_db()
    opciones_nombres = {v['nombre']: k for k, v in mapa_rebombeos_dict.items()}
    st.selectbox(
        "🧊 Rebombeos", 
        ["-- Seleccionar --"] + sorted(list(opciones_nombres.keys())), 
        key="opt_rebombeo", 
        on_change=reset_rebombeo
    )
    st.selectbox("🏘️ Sectores Hidráulicos", ["-- Seleccionar --"] + sorted([s['sector'] for s in sectores if s.get('sector')]), key="opt_sector", on_change=reset_sector)
st.divider()

# 4. SECCION ----------------------------------------- RENDERIZADO DE GRÁFICOS Y MÉTRICAS -------------------------------------------------------------
def renderizar_tarjeta_kpi(col, titulo, valor, unidad, color):
    col.markdown(f'''
        <div style="border: 2px solid {color}; padding: 8px; border-radius: 8px; text-align: center; margin-bottom: 10px; background: rgba(0,0,0,0.2);">
            <p style="color: #ccc; font-size: 9px; margin: 0; text-transform: uppercase; font-weight: bold;">{titulo}</p>
            <p style="color: {color}; font-size: 16px; font-weight: bold; margin: 0;">{valor} <span style="font-size: 10px; color: white;">{unidad}</span></p>
        </div>
    ''', unsafe_allow_html=True)

if st.session_state.activo_tipo == "Pozo" and st.session_state.activo_id != "-- Seleccionar --":
    id_pozo = st.session_state.activo_id
    info_p = mapa_pozos_dict.get(id_pozo)

    mexico_tz = pytz.timezone('America/Mexico_City')
    tags_voltaje = [v for v in info_p.get('voltajes_l', []) if v and v != 'N/A']
    data_voltaje = cargar_datos_scada(tags_voltaje)
    
    fechas_lectura = []
    for tag in tags_voltaje:
        _, fecha_str = data_voltaje.get(tag, (0.0, None))
        if fecha_str and fecha_str != "N/A":
            try:
                dt = datetime.strptime(fecha_str, '%d/%m/%Y %H:%M')
                fechas_lectura.append(dt)
            except:
                continue
    
    if fechas_lectura:
        ultima_fecha_db = max(fechas_lectura)
        ahora = datetime.now(mexico_tz).replace(tzinfo=None)
        es_falla = (ahora - ultima_fecha_db) > timedelta(hours=3)
        fecha_ultima_valida = ultima_fecha_db.strftime('%d/%m/%Y %H:%M')
    else:
        es_falla = True
        fecha_ultima_valida = "Sin datos"

    data_bomba = cargar_datos_scada([info_p['bomba']])
    val_bomba, _ = data_bomba.get(info_p['bomba'], (0.0, "N/A"))

    if es_falla:
        estado_texto = "FALLA DE COMUNICACIÓN"
        color_bomba = "#ffaa00"
        glow_bomba = "0 0 15px #ffaa00"
    else:
        estado_texto = "Bomba Encendida" if float(val_bomba) > 0 else "Bomba Apagada"
        color_bomba = "#00ff00" if float(val_bomba) > 0 else "#ff4b4b"
        glow_bomba = "0 0 15px #00ff00" if float(val_bomba) > 0 else "0 0 15px #ff4b4b"

    st.markdown(f"<h3 style='color:#00d4ff;'>↕️ Detalle de Pozo: {id_pozo}</h3>", unsafe_allow_html=True)
    st.markdown(f'''
        <div style="border: 2px solid {color_bomba}; padding: 8px; border-radius: 8px; text-align: center; margin-bottom: 20px; box-shadow: {glow_bomba};">
            <p style="color: white; font-size: 10px; margin: 0; text-transform: uppercase;">Estado del Pozo</p>
            <p style="color: {color_bomba}; font-size: 20px; font-weight: bold; margin: 0;">{estado_texto}</p>
            <p style="color: white; font-size: 12px; margin-top: 5px;">Última actualización: {fecha_ultima_valida}</p>
        </div>
    ''', unsafe_allow_html=True)

    opciones = ["Hoy", "Ayer", "Últimos 7 días", "Últimos 14 días", "Este Mes", "Último Mes", "Últimos 6 meses", "Personalizado"]
    opcion_fecha = st.selectbox("Rango de tiempo:", opciones, index=2, key="sel_rango_pozo")
    
    hoy_dt = datetime.now()
    if opcion_fecha == "Hoy": f_ini = hoy_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    elif opcion_fecha == "Ayer": f_ini = hoy_dt - timedelta(days=1)
    elif opcion_fecha == "Últimos 7 días": f_ini = hoy_dt - timedelta(days=7)
    elif opcion_fecha == "Últimos 14 días": f_ini = hoy_dt - timedelta(days=14)
    elif opcion_fecha == "Este Mes": f_ini = hoy_dt.replace(day=1)
    elif opcion_fecha == "Último Mes": f_ini = (hoy_dt.replace(day=1) - timedelta(days=1)).replace(day=1)
    elif opcion_fecha == "Últimos 6 meses": f_ini = hoy_dt - timedelta(days=180)
    else: 
        rango = st.date_input("Selecciona rango:", [hoy_dt - timedelta(days=7), hoy_dt], key="date_pozo")
        f_ini = rango[0] if len(rango) == 2 else hoy_dt - timedelta(days=7)

    tags_consulta = [info_p['caudal'], info_p['presion'], info_p['nivel_dinamico'], info_p['sumergencia'], info_p['nivel_tanque']]
    tags_consulta.extend([v for v in info_p['voltajes_l'] if v and v != 'N/A'])
    tags_consulta.extend([a for a in info_p['amperajes_l'] if a and a != 'N/A'])
    
    engine = get_mysql_scada_engine()
    tags_str = "','".join(list(set([t for t in tags_consulta if t])))
    q = f"SELECT r.NAME as TagName, h.VALUE FROM vfitagnumhistory h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags_str}') AND h.FECHA BETWEEN '{f_ini}' AND '{hoy_dt}'"
    df = pd.read_sql(q, engine)
    
    def get_avg(tag, df_loc):
        d = df_loc[df_loc['TagName'] == tag]['VALUE']
        return d.mean() if not d.empty else 0.0

    data_tq = cargar_datos_scada([info_p['nivel_tanque']])
    val_nivel_tq = float(data_tq.get(info_p['nivel_tanque'], (0.0, ""))[0])
    
    if 'mostrar_ind' not in st.session_state:
        st.session_state.mostrar_ind = False
        
    st.session_state.mostrar_ind = st.toggle("Indicadores de Operación", value=st.session_state.mostrar_ind)
    if st.session_state.mostrar_ind:
        f1 = st.columns(3)
        renderizar_tarjeta_kpi(f1[0], "Caudal Prom", f"{get_avg(info_p['caudal'], df):,.2f}", "Lps", "#00d4ff")
        renderizar_tarjeta_kpi(f1[1], "Presión Prom", f"{get_avg(info_p['presion'], df):,.2f}", "Kg/cm²", "#00ff00")
        renderizar_tarjeta_kpi(f1[2], "Nivel de tanque actual", f"{val_nivel_tq:,.2f}", "Mts", "#00ffcc")
        
        f2 = st.columns(2)
        renderizar_tarjeta_kpi(f2[0], "Nivivel Dinamico Prom.", f"{get_avg(info_p['nivel_dinamico'], df):,.2f}", "Mts", "#ff00b4")
        renderizar_tarjeta_kpi(f2[1], "Sumergencia de la bomba Prom.", f"{get_avg(info_p['sumergencia'], df):,.2f}", "Mts", "#a800ff")
        
        f3 = st.columns(2)
        v_tags = [v for v in info_p['voltajes_l'] if v and v != 'N/A']
        v_prom = sum([get_avg(v, df) for v in v_tags]) / len(v_tags) if v_tags else 0
        renderizar_tarjeta_kpi(f3[0], "Voltaje Prom", f"{v_prom:,.1f}", "Volt", "#fffb00")
        
        a_tags = [a for a in info_p['amperajes_l'] if a and a != 'N/A']
        a_prom = sum([get_avg(a, df) for a in a_tags]) / len(a_tags) if a_tags else 0
        renderizar_tarjeta_kpi(f3[1], "Amperaje Prom", f"{a_prom:,.1f}", "Amp", "#ff8000")

    grupos = [
        {"titulo": "Caudal y Presión", "icono": "💧", "tags": [('caudal', "Caudal (Lps)", '#00d4ff'), ('presion', "Presión (Kg/cm²)", '#00ff00')]},
        {"titulo": "Voltaje y Amperaje", "icono": "⚡", "tags": [(t, f"V L{i+1}", '#fffb00') for i, t in enumerate(info_p.get('voltajes_l', [])) if t != 'N/A'] + [(t, f"Amp L{i+1}", '#ff8000') for i, t in enumerate(info_p.get('amperajes_l', [])) if t != 'N/A']},
        {"titulo": "Nivel Tanque", "icono": "🛢️", "tags": [('nivel_tanque', "Tanque (m)", '#00ffcc')]},
        {"titulo": "Niveles de Pozo", "icono": "🌀", "tags": [('nivel_dinamico', "Dinámico (m)", '#ff00b4'), ('sumergencia', "Sumergencia (m)", '#a800ff')]}
    ]

    for grupo in grupos:
        tags_en_grupo = [t for t in grupo['tags'] if info_p.get(t[0], t[0]) in df['TagName'].values]
        if not tags_en_grupo: continue

        st.markdown(f'<h3 style="color: white;">{grupo["icono"]} {grupo["titulo"]}</h3>', unsafe_allow_html=True)
        fig = go.Figure()
        
        for key, label, color in tags_en_grupo:
            tag_name = info_p.get(key, key)
            dft = df[df['TagName'] == tag_name].sort_values('FECHA')
            
            fig.add_trace(go.Scatter(
                x=dft['FECHA'],
                y=dft['VALUE'],
                name=label, 
                mode='lines+markers',
                line=dict(color=color, width=2),
                marker=dict(size=4),
                hovertemplate=f"<span style='color:{color};'>■</span> <b>{label}</b>: %{{y:,.2f}}<extra></extra>"))
        
        fig.update_layout(
            template="plotly_dark", 
            height=300, 
            margin=dict(t=60, b=80, l=10, r=10),
            hovermode="x unified", 
            paper_bgcolor='rgba(0,0,0,0)', 
            plot_bgcolor='rgba(0,0,0,0)',
            showlegend=True,
            xaxis=dict(title_font=dict(color='white'), tickfont=dict(color='white'), linecolor='white', gridcolor='rgba(255,255,255,0.1)'),
            yaxis=dict(title_font=dict(color='white'), tickfont=dict(color='white'), linecolor='white', gridcolor='rgba(255,255,255,0.1)'),
            legend=dict(orientation="h", y=1.2, x=0.5, xanchor="center", yanchor="top", font=dict(size=9, color='white'))
        )
        st.plotly_chart(fig, use_container_width=True)
        st.markdown("<hr style='border: 0.5px solid #00d4ff; margin-top: -30px; margin-bottom: 20px;'>", unsafe_allow_html=True)

elif st.session_state.activo_tipo == "Tanque" and st.session_state.activo_id != "-- Seleccionar --":
    id_tq = st.session_state.activo_id
    info_t = mapa_tanques_dict.get(id_tq)
    
    st.markdown(f"<h3 style='color:#00d4ff;'>🛢️  Análisis de Nivel: {info_t['nombre']}</h3>", unsafe_allow_html=True)

    data_tq = cargar_datos_scada([info_t['tag_nivel']])
    ultimo_nivel, fecha_lectura = data_tq.get(info_t['tag_nivel'], (0.0, "N/A"))
    nivel_max = info_t.get('nivel_max', 0.0)
    
    st.markdown(f'''
        <div style="border: 2px solid #00d4ff; padding: 10px; border-radius: 12px; text-align: center; margin-bottom: 20px; background: rgba(0, 212, 255, 0.05);">
            <p style="color: white; font-size: 12px; margin: 0; line-height: 1; font-weight: bold;">Nivel de tanque actual</p>
            <p style="color: white; font-size: 32px; font-weight: bold; margin: -5px 0 0 0; line-height: 1.2;">
                {float(ultimo_nivel):,.2f} <span style="font-size: 18px; color: #00d4ff;">Mts</span>
            </p>
            <div style="margin-top: 2px;">
                <p style="color: #cccccc; font-size: 12px; margin: 0; line-height: 1.4;">
                    Nivel Máximo: <span style="color: #00d4ff; font-weight: bold;">{float(nivel_max):,.2f} Mts</span>
                </p>
                <p style="color: white; font-size: 12px; margin: 0; line-height: 1;">Última lectura: {fecha_lectura}</p>
            </div>
        </div>
    ''', unsafe_allow_html=True)
    
    opciones = ["Hoy", "Ayer", "Últimos 7 días", "Últimos 14 días", "Este Mes", "Último Mes", "Últimos 6 meses", "Personalizado"]
    opcion_fecha = st.selectbox("Selecciona rango:", opciones, index=2)
    
    hoy_dt = datetime.now()
    f_fin = hoy_dt
    
    if opcion_fecha == "Hoy":
        f_ini = hoy_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    elif opcion_fecha == "Ayer":
        f_ini = hoy_dt - timedelta(days=1)
    elif opcion_fecha == "Últimos 7 días":
        f_ini = hoy_dt - timedelta(days=7)
    elif opcion_fecha == "Últimos 14 días":
        f_ini = hoy_dt - timedelta(days=14)
    elif opcion_fecha == "Este Mes":
        f_ini = hoy_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    elif opcion_fecha == "Último Mes":
        primer_dia_actual = hoy_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        f_ini = (primer_dia_actual - timedelta(days=1)).replace(day=1)
        f_fin = primer_dia_actual - timedelta(seconds=1)
    elif opcion_fecha == "Últimos 6 meses":
        f_ini = hoy_dt - timedelta(days=180)
    elif opcion_fecha == "Personalizado":
        rango = st.date_input("Selecciona rango:", [hoy_dt - timedelta(days=7), hoy_dt])
        if len(rango) == 2:
            f_ini, f_fin = rango[0], rango[1]
        else:
            f_ini = hoy_dt - timedelta(days=7)

    try:
        engine = get_mysql_scada_engine()
        f_ini_str = f_ini.strftime('%Y-%m-%d %H:%M:%S')
        f_fin_str = f_fin.strftime('%Y-%m-%d %H:%M:%S') if isinstance(f_fin, datetime) else f_fin.strftime('%Y-%m-%d %H:%M:%S')
        
        query = f"""
            SELECT h.FECHA, h.VALUE FROM vfitagnumhistory h
            JOIN VfiTagRef r ON h.GATEID = r.GATEID
            WHERE r.NAME = '{info_t['tag_nivel']}' 
            AND h.FECHA BETWEEN '{f_ini_str}' AND '{f_fin_str}'
            ORDER BY h.FECHA ASC
        """
        df_hist = pd.read_sql(query, engine)
        
        if not df_hist.empty:
            df_hist['FECHA'] = pd.to_datetime(df_hist['FECHA'])
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=df_hist['FECHA'],
                y=df_hist['VALUE'],
                name="Nivel Tq",
                mode='lines+markers', 
                line=dict(color='#00ffcc', width=2),
                fill='tozeroy',
                fillcolor='rgba(0, 255, 204, 0.1)',
                hovertemplate="<b>Nivel</b>: %{y:.2f} m<extra></extra>"
            ))
            
            fig.update_layout(
                template="plotly_dark",
                height=300,
                margin=dict(t=60, b=80, l=10, r=10),
                paper_bgcolor='rgba(0,0,0,0)', 
                plot_bgcolor='rgba(0,0,0,0)',
                hovermode="x unified",
                showlegend=True,
                legend=dict(orientation="h", y=1.2, x=0.5, xanchor="center", font=dict(size=10, color='white')),    
                xaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.1)', color='white'),
                yaxis=dict(showgrid=True, gridcolor='rgba(255,255,255,0.1)', color='white')
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.warning("Sin datos para este tanque en el periodo elegido.")
    except Exception as e:
        st.error(f"Error cargando tanque: {e}")

elif st.session_state.activo_tipo == "Rebombeo" and st.session_state.activo_id != "-- Seleccionar --":
    id_rb = st.session_state.activo_id
    info_rb = mapa_rebombeos_dict.get(id_rb)
    
    if info_rb:
        st.markdown(f"<h3 style='color:#00d4ff;'>🧊 Rebombeo: {info_rb['nombre']}</h3>", unsafe_allow_html=True)
        
        opciones = ["Hoy", "Ayer", "Últimos 7 días", "Últimos 14 días", "Este Mes", "Último Mes", "Últimos 6 meses", "Personalizado"]
        opcion_fecha = st.selectbox("Rango de tiempo:", opciones, index=2, key="sel_rango_rb")
        
        hoy_dt = datetime.now()
        f_fin = hoy_dt
        if opcion_fecha == "Hoy": f_ini = hoy_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        elif opcion_fecha == "Ayer": 
            f_ini = (hoy_dt - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            f_fin = hoy_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        elif opcion_fecha == "Últimos 7 días": f_ini = hoy_dt - timedelta(days=7)
        elif opcion_fecha == "Últimos 14 días": f_ini = hoy_dt - timedelta(days=14)
        elif opcion_fecha == "Este Mes": f_ini = hoy_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif opcion_fecha == "Último Mes":
            primer_dia_actual = hoy_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            f_ini = (primer_dia_actual - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            f_fin = primer_dia_actual - timedelta(seconds=1)
        elif opcion_fecha == "Últimos 6 meses": f_ini = hoy_dt - timedelta(days=180)
        else:
            rango = st.date_input("Selecciona rango:", [hoy_dt - timedelta(days=7), hoy_dt], key="date_rb")
            f_ini = pd.to_datetime(rango[0]) if len(rango) == 2 else hoy_dt - timedelta(days=7)
            if len(rango) == 2: f_fin = pd.to_datetime(rango[1]).replace(hour=23, minute=59, second=59)

        engine = get_mysql_scada_engine()
        tag_p, tag_n = info_rb.get('presion'), info_rb.get('nivel_tanque')
        tag_sd, tag_sn = info_rb.get('setpoint_dia'), info_rb.get('setpoint_noche')
        
        tags_todos = [t for t in [tag_p, tag_n, tag_sd, tag_sn] if t]
        tags_str = ",".join([f"'{t}'" for t in tags_todos])
        
        query = f"""
            SELECT h.FECHA, h.VALUE, r.NAME as TAG
            FROM vfitagnumhistory h
            JOIN VfiTagRef r ON h.GATEID = r.GATEID
            WHERE r.NAME IN ({tags_str})
            AND h.FECHA BETWEEN '{f_ini.strftime('%Y-%m-%d %H:%M:%S')}' AND '{f_fin.strftime('%Y-%m-%d %H:%M:%S')}'
            ORDER BY h.FECHA ASC
        """
        df_hist = pd.read_sql(query, engine)
        
        if not df_hist.empty:
            df_hist['FECHA'] = pd.to_datetime(df_hist['FECHA'])
            df_hist = df_hist.sort_values('FECHA')
            ultimos = df_hist.groupby('TAG').last()

            p_val = ultimos.loc[tag_p, 'VALUE'] if tag_p in ultimos.index else 0
            estado_texto = "Sistema Encendido" if float(p_val) >= 0.100 else "Sistema Apagado"
            color_estado = "#00ff00" if float(p_val) >= 0.100 else "#ff4b4b"
            
            st.markdown(f"""
            <div style="border: 2px solid {color_estado}; padding: 10px; border-radius: 10px; text-align: center; margin-bottom: 20px;">
                <p style="margin: 0; font-size: 12px; color: #FFFFFF;">ESTADO DEL SISTEMA</p>
                <h3 style="margin: 0; color: {color_estado};">{estado_texto}</h3>
            </div>
            """, unsafe_allow_html=True)

            def metric_con_icono_al_lado(label, val_tag, icon, unit):
                val = ultimos.loc[val_tag, 'VALUE'] if val_tag in ultimos.index else 0
                fecha_obj = ultimos.loc[val_tag, 'FECHA'] if val_tag in ultimos.index else None
                
                if val_tag in ["RB_099_TRM_SET_POINT_DIA", "RB_099_TRM_SET_POINT_NOCHE"]:
                    val = val / 100.0
                
                if fecha_obj:
                    meses = {
                        1: "Enero", 2: "Febrero", 3: "Marzo", 4: "Abril", 5: "Mayo", 6: "Junio",
                        7: "Julio", 8: "Agosto", 9: "Septiembre", 10: "Octubre", 11: "Noviembre", 12: "Diciembre"
                    }
                    mes_nombre = meses[fecha_obj.month]
                    fecha_str = f"{fecha_obj.day:02d}/{mes_nombre}/{fecha_obj.year} {fecha_obj.strftime('%H:%M')}"
                else:
                    fecha_str = "N/A"
                
                st.markdown("<hr style='border: 0; border-top: 1px solid #FFFFFF; margin: 2px 0 5px 0;'>", unsafe_allow_html=True)
                st.markdown(f"<p style='font-size: 18px; margin-bottom: 2px; color: #FFFFFF; text-align: center;'>{label}</p>", unsafe_allow_html=True)
                
                st.markdown(f"""
                <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 15px;">
                    <h2 style="margin: 0; font-size: 24px;">{icon} {val:.2f} <span style='font-size: 16px;'>{unit}</span></h2>
                    <p style="margin: 0; font-size: 16px; color: #FFFFFF; align-self: flex-end;">{fecha_str}</p>
                </div>
                """, unsafe_allow_html=True)

            metric_con_icono_al_lado("Presión actual del Sistema", tag_p, "🕛", "Kg/cm²")
            metric_con_icono_al_lado("Nivel actual de Tanque", tag_n, "🛢️", "mts")
            metric_con_icono_al_lado("Ajuste Setpoint Día", tag_sd, "☀️", "Kg/cm²")
            metric_con_icono_al_lado("Ajuste Setpoint Noche", tag_sn, "🌙", "Kg/cm²")

            st.markdown("<hr style='border: 0; border-top: 2px solid #00d4ff; margin: 20px 0;'>", unsafe_allow_html=True)
            st.markdown("<h4 style='color:#00d4ff; font-size:14px;'>Histórico: Presión y Nivel de Tanque</h4>", unsafe_allow_html=True)
            
            fig_rb = go.Figure()
            df_n, df_p = df_hist[df_hist['TAG'] == tag_n], df_hist[df_hist['TAG'] == tag_p]
            fig_rb.add_trace(go.Scatter(x=df_n['FECHA'], y=df_n['VALUE'].round(2), name='Nivel (Mts)', mode='lines+markers', line=dict(color='#00d4ff', width=2), marker=dict(size=4)))
            fig_rb.add_trace(go.Scatter(x=df_p['FECHA'], y=df_p['VALUE'].round(2), name='Presión (Kg/cm²)', mode='lines+markers', line=dict(color='#00ff00', width=2), marker=dict(size=4), yaxis="y2"))
            
            fig_rb.update_layout(template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', hovermode="x unified", height=280, margin=dict(t=40, b=40, l=0, r=0), yaxis=dict(title="Nivel (m)"), yaxis2=dict(title="Presión (Kg/cm²)", overlaying="y", side="right"), legend=dict(orientation="h", y=1.2))
            st.plotly_chart(fig_rb, use_container_width=True)
        else:
            st.warning("No hay datos históricos para el rango seleccionado.")

elif st.session_state.activo_tipo == "Sector" and st.session_state.activo_id != "-- Seleccionar --":
    sec_id = st.session_state.activo_id
    datos_s = next((s for s in sectores if s['sector'] == sec_id), None)
    
    if datos_s:
        st.markdown(f"<h3 style='color:#00d4ff;'>🏘️ Sector Hidráulico: {sec_id}</h3>", unsafe_allow_html=True)
        
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            st.markdown(f'<div class="card-indicador"><p class="label-indicador">Superficie</p><p class="value-indicador">{datos_s.get("Superficie",0):,.1f} ha</p></div>', unsafe_allow_html=True)
            st.markdown(f'<div class="card-indicador"><p class="label-indicador">Tomas Totales</p><p class="value-indicador">{datos_s.get("U_Tot",0):,.0f}</p></div>', unsafe_allow_html=True)
        with sc2:
            st.markdown(f'<div class="card-indicador"><p class="label-indicador">Longitud de Red</p><p class="value-indicador">{datos_s.get("Long_Red",0):,.1f} m</p></div>', unsafe_allow_html=True)
            st.markdown(f'<div class="card-indicador"><p class="label-indicador">Población</p><p class="value-indicador">{datos_s.get("Poblacion",0):,.0f} hab</p></div>', unsafe_allow_html=True)
        with sc3:
            st.markdown(f'<div class="card-indicador"><p class="label-indicador">Consumo Mensual</p><p class="value-indicador">{datos_s.get("Cons_m3",0):,.1f} m³</p></div>', unsafe_allow_html=True)
            st.markdown(f'<div class="card-indicador"><p class="label-indicador">Eficiencia / Balance</p><p class="value-indicador">{datos_s.get("Balance_Estimado",0):,.1f}%</p></div>', unsafe_allow_html=True)
            
        st.markdown("<h4 style='color:#00d4ff;'>📈 Histórico de Puntos de Control, Pozos y VRPs</h4>", unsafe_allow_html=True)
        opciones_tiempo = ["Hoy", "Ayer", "Últimos 7 días", "Últimos 14 días", "Este Mes", "Último Mes", "Últimos 6 meses", "Personalizado"]
        rango_seleccionado = st.selectbox("Seleccione el periodo a mostrar", opciones_tiempo, index=2, key="rango_tiempo_sec")
        
        hoy = pd.Timestamp.now().normalize()
        if rango_seleccionado == "Hoy": f_ini_h, f_fin_h = hoy, hoy
        elif rango_seleccionado == "Ayer": f_ini_h, f_fin_h = hoy - pd.Timedelta(days=1), hoy - pd.Timedelta(days=1)
        elif rango_seleccionado == "Últimos 7 días": f_ini_h, f_fin_h = hoy - pd.Timedelta(days=7), hoy
        elif rango_seleccionado == "Últimos 14 días": f_ini_h, f_fin_h = hoy - pd.Timedelta(days=14), hoy
        elif rango_seleccionado == "Este Mes": f_ini_h, f_fin_h = hoy.replace(day=1), hoy
        elif rango_seleccionado == "Último Mes":
            import calendar
            mes_ant = hoy.replace(day=1) - pd.Timedelta(days=1)
            f_ini_h, f_fin_h = mes_ant.replace(day=1), mes_ant.replace(day=calendar.monthrange(mes_ant.year, mes_ant.month)[1])
        elif rango_seleccionado == "Últimos 6 meses": f_ini_h, f_fin_h = hoy - pd.Timedelta(days=180), hoy
        else:
            col_f1, col_f2 = st.columns(2)
            f_ini_h = col_f1.date_input("Fecha Inicio", hoy - pd.Timedelta(days=7))
            f_fin_h = col_f2.date_input("Fecha Fin", hoy)

        str_f_ini = pd.to_datetime(f_ini_h).strftime('%Y-%m-%d 00:00:00')
        str_f_fin = pd.to_datetime(f_fin_h).strftime('%Y-%m-%d 23:59:59')

        dict_reg = {k: v for k, v in cargar_puntos_de_control_desde_db().items() if str(v.get('sector')).strip() == str(sec_id).strip()}
        
        tags_sector = []
        mapeo_config = {}

        for r_id, r_info in dict_reg.items():
            nombre_disp = f"S:{r_id}"
            conf_pc = [
                ('tag_q', f"{nombre_disp} - Q", '#00d4ff', False),
                ('tag_p1', f"{nombre_disp} - P1", '#00ff00', True),
                ('tag_p2', f"{nombre_disp} - P2", '#ffff00', True)
            ]
            for key_t, lb, clr, sec in conf_pc:
                tag_v = r_info.get(key_t)
                if tag_v and str(tag_v).strip().lower() not in ['0', 'none', 'n/a', 'null']:
                    tags_sector.append(tag_v)
                    mapeo_config[tag_v] = {'label': lb, 'color': clr, 'sec': sec}
                    
        if 'mapa_pozos_dict' in globals():
            ids_p_sector = [id_p for id_p, p_info in mapa_pozos_dict.items() if str(p_info.get('sector')).strip() == str(sec_id).strip() or str(sec_id).lower() in str(p_info.get('sector', '')).lower() or str(id_p).strip() == "P156"]
            
            for id_p in ids_p_sector:
                if id_p in mapa_pozos_dict:
                    p_info = mapa_pozos_dict[id_p]
                    conf_pz = [
                        ('caudal', f"Pozo {id_p} - Q", '#00d4ff', False),
                        ('presion', f"Pozo {id_p} - P", '#00ff00', True),
                        ('nivel_tanque', f"Pozo {id_p} - Nivel", '#0000FF', True)
                    ]
                    for key_t, lb, clr, sec in conf_pz:
                        tag_v = p_info.get(key_t)
                        if tag_v and str(tag_v).strip().lower() not in ['0', 'none', 'n/a', 'null']:
                            tags_sector.append(tag_v)
                            mapeo_config[tag_v] = {'label': lb, 'color': clr, 'sec': sec}
                
        if tags_sector:
            try:
                engine_h = get_mysql_scada_engine()
                tags_unicos = "', '".join(list(set(tags_sector)))
                q_sec = f"SELECT h.FECHA, h.VALUE, r.NAME as TAG FROM vfitagnumhistory h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags_unicos}') AND h.FECHA BETWEEN '{str_f_ini}' AND '{str_f_fin}' ORDER BY h.FECHA ASC"
                df_sec = pd.read_sql(q_sec, engine_h)
                
                if not df_sec.empty:
                    df_sec['FECHA'] = pd.to_datetime(df_sec['FECHA'])
                    
                    dias_es = {0: 'Lun', 1: 'Mar', 2: 'Mié', 3: 'Jue', 4: 'Vie', 5: 'Sáb', 6: 'Dom'}
                    meses_es = {1: 'Ene', 2: 'Feb', 3: 'Mar', 4: 'Abr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Ago', 9: 'Sep', 10: 'Oct', 11: 'Nov', 12: 'Dic'}

                    fechas_lineas = pd.date_range(start=df_sec['FECHA'].min().floor('D'), end=df_sec['FECHA'].max().ceil('D'), freq='D')
                    num_dias = len(fechas_lineas)
                    paso = 1 if num_dias <= 15 else (2 if num_dias <= 30 else 5)
                    ticks_filtrados = fechas_lineas[::paso]

                    etiquetas_filtradas = [
                        f"{d.strftime('%H:%M')}<br>{dias_es[d.dayofweek]} {d.day}-{meses_es[d.month]}-{d.year}"
                        for d in ticks_filtrados
                    ]
                
                    fig_sec = go.Figure()
                    idx_q = 0
                    idx_p = 0
                    leyendaitems = []

                    for tag_name in tags_sector:
                        df_tag = df_sec[df_sec['TAG'] == tag_name]
                        if not df_tag.empty:
                            cfg = mapeo_config[tag_name]
                            es_caudal = not cfg['sec']
                            label_u = cfg['label'].upper()

                            unidad_pc = "Lps" if es_caudal else ("Mts" if "NIVEL" in label_u or "TANQUE" in label_u or "MTS" in label_u else "kg/cm²")
                            
                            if es_caudal:
                                brillo = max(75 - (idx_q * 15), 35) 
                                color_base = f"hsl(200, 100%, {brillo}%)" 
                                idx_q += 1
                            else:
                                brillo = max(80 - (idx_p * 20), 0)
                                color_base = f"hsl(145, 100%, {brillo}%)"
                                idx_p += 1

                            fig_sec.add_trace(go.Scatter(
                                x=df_tag['FECHA'], y=df_tag['VALUE'], name=cfg['label'], 
                                yaxis="y2" if cfg['sec'] else "y1", mode='lines+markers',
                                line=dict(width=1.8, color=color_base),
                                marker=dict(size=3, symbol='circle'),
                                fill='tozeroy' if es_caudal else None,
                                fillcolor=color_base.replace("hsl", "hsla").replace(")", ", 0.15)"),
                                hovertemplate='<b>%{fullData.name}</b>: %{y:.2f} ' + unidad_pc + '<extra></extra>'
                            ))
                            leyendaitems.append({"label": cfg['label'], "color": color_base})

                    delta = pd.Timedelta(hours=1)
                    for d in fechas_lineas:
                        es_lunes = (d.dayofweek == 0)
                        fig_sec.add_vrect(x0=d - delta, x1=d + delta, fillcolor="gray", opacity=0.2, layer="below", line_width=0)
                        fig_sec.add_vline(x=d, line_width=1.5, line_dash="dash", line_color="#fffb00" if es_lunes else "white", opacity=0.5, layer="above")
                
                    fig_sec.update_layout(
                        template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
                        hovermode="x unified", height=300, width=1800, autosize=False, margin=dict(t=30, b=30, l=10, r=10), showlegend=False,
                        xaxis=dict(color="white", showgrid=False, tickvals=ticks_filtrados, ticktext=etiquetas_filtradas, tickangle=0, tickformat="%d-%b-%Y %H:%M"),
                        yaxis=dict(title="Caudales (m³/h)", color="#00d4ff", tickformat=".2f"),
                        yaxis2=dict(title="Presiones / Niveles", overlaying="y", side="right", color="#00ff00", showgrid=False, tickformat=".2f")
                    )
                    
                    st.markdown("<p style='color:#00d4ff; font-weight:bold; margin-bottom:5px; font-size:13px;'>Variables en Puntos de Control y Pozos:</p>", unsafe_allow_html=True)
                    items_html = "".join([f'<div style="display:flex; align-items:center; margin-bottom:6px; overflow:hidden;"><span style="height:10px; width:16px; background-color:{item["color"]}; display:inline-block; margin-right:5px; border-radius:2px; flex-shrink:0;"></span><span style="color:white; font-size:10px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{item["label"]}</span></div>' for item in leyendaitems])
                    st.markdown(f'<div style="display:grid; grid-template-columns: repeat(3, 1fr); gap: 6px 10px; width:100%; margin-bottom:10px;">{items_html}</div>', unsafe_allow_html=True)

                    st.markdown("""
                        <style>
                        .scrollable-chart { overflow-x: auto; width: 100%; padding-bottom: 15px; }
                        .scrollable-chart > div { min-width: 1200px; }
                        </style>
                    """, unsafe_allow_html=True)
                    
                    st.markdown('<div class="scrollable-chart">', unsafe_allow_html=True)
                    st.plotly_chart(fig_sec, use_container_width=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                else:
                    st.info("Sin registros telemétricos en el rango de fechas seleccionado para Puntos de Control.")
            except Exception as e:
                st.error(f"Error Scada Puntos de Control: {e}")
        else:
            st.info("No hay puntos de control ni pozos vinculados a este sector.")

        dict_vrp_sec = {k: v for k, v in cargar_vrp_desde_db().items() if str(v.get('sector')).strip() == str(sec_id).strip()}
        tags_vrp_global = []
        mapeo_vrp_global = {}
        
        for v_id, v_info in dict_vrp_sec.items():
            identificador = f"VRP {v_id}" 
            conf_vrp = [
                ('tag_q', f"{identificador} - Q", False),
                ('tag_p1', f"{identificador} - P1", True),
                ('tag_p2', f"{identificador} - P2", True)
            ]
            for key_t, lb, sec in conf_vrp:
                t_val = v_info.get(key_t)
                if t_val and str(t_val).strip().lower() not in ['0', 'none', 'n/a', 'null']:
                    tags_vrp_global.append(t_val)
                    mapeo_vrp_global[t_val] = {'label': lb, 'sec': sec}

        if tags_vrp_global:
            try:
                engine_h = get_mysql_scada_engine()
                tags_in_v = "', '".join(list(set(tags_vrp_global)))
                q_vrp = f"SELECT h.FECHA, h.VALUE, r.NAME as TAG FROM vfitagnumhistory h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags_in_v}') AND h.FECHA BETWEEN '{str_f_ini}' AND '{str_f_fin}' ORDER BY h.FECHA ASC"
                df_v = pd.read_sql(q_vrp, engine_h)
                
                if not df_v.empty:
                    st.markdown(f"<h3 style='color:#00ffcc; font-size:20px; margin-top:25px; margin-bottom:10px;'>🎛️ Análisis Integral de VRPs del Sector</h3>", unsafe_allow_html=True)
                    df_v['FECHA'] = pd.to_datetime(df_v['FECHA'])
                    
                    fig_v = go.Figure()
                    delta = pd.Timedelta(hours=1)
                    for d in fechas_lineas:
                        es_lunes = (d.dayofweek == 0)
                        fig_v.add_vrect(x0=d - delta, x1=d + delta, fillcolor="gray", opacity=0.2, layer="below", line_width=0)
                        fig_v.add_vline(x=d, line_width=1.5, line_dash="dash", line_color="#fffb00" if es_lunes else "white", opacity=0.3, layer="above")
                    
                    idx_vq = 0
                    idx_vp = 0
                    leyenda_vrp_items = []

                    for t_name in tags_vrp_global:
                        df_t = df_v[df_v['TAG'] == t_name]
                        if not df_t.empty:
                            c_vrp = mapeo_vrp_global[t_name]
                            es_caudal_v = not c_vrp['sec']
                            unidad_final = "kg/cm²" if ("P1" in c_vrp['label'] or "P2" in c_vrp['label']) else "Lps"
                            
                            if es_caudal_v:
                                brillo = max(75 - (idx_vq * 15), 35)
                                color_v = f"hsl(200, 100%, {brillo}%)" 
                                idx_vq += 1
                            else:
                                brillo = max(80 - (idx_vp * 15), 30)
                                color_v = f"hsl(150, 100%, {brillo}%)"
                                idx_vp += 1

                            fig_v.add_trace(go.Scatter(
                                x=df_t['FECHA'], y=df_t['VALUE'], name=c_vrp['label'], 
                                yaxis="y2" if c_vrp['sec'] else "y1", mode='lines+markers',
                                line=dict(width=1.8, color=color_v),
                                marker=dict(size=3 if es_caudal_v else 4, symbol='circle'),
                                fill='tozeroy' if es_caudal_v else None,
                                fillcolor=color_v.replace("hsl", "hsla").replace(")", ", 0.12)"),
                                hovertemplate=f'<b>%{{fullData.name}}</b>: %{{y:.2f}} {unidad_final}<extra></extra>'
                            ))
                            leyenda_vrp_items.append({"label": c_vrp['label'], "color": color_v})

                    fig_v.update_layout(
                        template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
                        height=300, width=1800, autosize=False, margin=dict(t=30, b=30, l=10, r=10), hovermode="x unified", showlegend=False,
                        xaxis=dict(color="white", showgrid=False, tickvals=ticks_filtrados, ticktext=etiquetas_filtradas, tickangle=0, tickformat="%d-%b-%Y %H:%M"),
                        yaxis=dict(title="Caudal (Lps)", color="#00d4ff", tickformat=".2f"),
                        yaxis2=dict(title="Presión (kg)", side="right", overlaying="y", color="#00ff00", showgrid=False, tickformat=".2f")
                    )
                    
                    st.markdown("<p style='color:#00ffcc; font-weight:bold; margin-bottom:5px; font-size:13px;'>Variables en este gráfico de VRPs:</p>", unsafe_allow_html=True)
                    items_vrp_html = "".join([f'<div style="display:flex; align-items:center; margin-bottom:6px; overflow:hidden;"><span style="height:10px; width:16px; background-color:{item["color"]}; display:inline-block; margin-right:5px; border-radius:2px; flex-shrink:0;"></span><span style="color:white; font-size:10px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{item["label"]}</span></div>' for item in leyenda_vrp_items])
                    st.markdown(f'<div style="display:grid; grid-template-columns: repeat(3, 1fr); gap: 6px 10px; width:100%; margin-bottom:10px;">{items_vrp_html}</div>', unsafe_allow_html=True)

                    st.markdown('<div class="scrollable-chart">', unsafe_allow_html=True)
                    st.plotly_chart(fig_v, use_container_width=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                else:
                    st.info("No se encontraron registros telemétricos para las VRPs en este sector.")
            except Exception as e:
                st.error(f"Error Scada VRP: {e}")
        else:
            st.info("No hay VRPs configuradas para este sector.")

        dict_pc_sec = {k: v for k, v in cargar_puntos_criticos_desde_db().items() if str(v.get('sector')).strip() == str(sec_id).strip()}
        tags_pc_global = []
        mapeo_pc_global = {}

        for pc_id, pc_info in dict_pc_sec.items():
            domicilio_pc = pc_info.get('Domicilio', 'Sin Domicilio')
            conf_pc_pts = [
                ('tag_q', f"PC {pc_id} ({domicilio_pc}) - Q", False),
                ('tag_p1', f"PC {pc_id} ({domicilio_pc}) - P1", True)
            ]
            for key_t, lb, sec in conf_pc_pts:
                t_val = pc_info.get(key_t)
                if t_val and str(t_val).strip().lower() not in ['0', 'none', 'n/a', 'null']:
                    tags_pc_global.append(t_val)
                    mapeo_pc_global[t_val] = {'label': lb, 'sec': sec}

        if tags_pc_global:
            try:
                engine_h = get_mysql_scada_engine()
                tags_in_pc = "', '".join(list(set(tags_pc_global)))
                q_pc = f"SELECT h.FECHA, h.VALUE, r.NAME as TAG FROM vfitagnumhistory h JOIN VfiTagRef r ON h.GATEID = r.GATEID WHERE r.NAME IN ('{tags_in_pc}') AND h.FECHA BETWEEN '{str_f_ini}' AND '{str_f_fin}' ORDER BY h.FECHA ASC"
                df_pc_h = pd.read_sql(q_pc, engine_h)

                if not df_pc_h.empty:
                    st.markdown(f"<h3 style='color:#ff5555; font-size:20px; margin-top:25px; margin-bottom:10px;'>🚨 Análisis de Puntos Críticos del Sector</h3>", unsafe_allow_html=True)
                    df_pc_h['FECHA'] = pd.to_datetime(df_pc_h['FECHA'])

                    fig_pc = go.Figure()
                    delta = pd.Timedelta(hours=1)
                    for d in fechas_lineas:
                        es_lunes = (d.dayofweek == 0)
                        fig_pc.add_vrect(x0=d - delta, x1=d + delta, fillcolor="gray", opacity=0.2, layer="below", line_width=0)
                        fig_pc.add_vline(x=d, line_width=1.5, line_dash="dash", line_color="#fffb00" if es_lunes else "white", opacity=0.3, layer="above")

                    idx_pcq = 0
                    idx_pcp = 0
                    leyenda_pc_items = []

                    for t_name in tags_pc_global:
                        df_t = df_pc_h[df_pc_h['TAG'] == t_name]
                        if not df_t.empty:
                            c_pc = mapeo_pc_global[t_name]
                            es_caudal_pc = not c_pc['sec']
                            unidad_final_pc = "kg/cm²" if c_pc['sec'] else "Lps"

                            if es_caudal_pc:
                                brillo = max(75 - (idx_pcq * 15), 35)
                                color_pc = f"hsl(200, 100%, {brillo}%)"
                                idx_pcq += 1
                            else:
                                brillo = max(80 - (idx_pcp * 20), 0)
                                color_pc = f"hsl(145, 100%, {brillo}%)"
                                idx_pcp += 1

                            fig_pc.add_trace(go.Scatter(
                                x=df_t['FECHA'], y=df_t['VALUE'], name=c_pc['label'],
                                yaxis="y2" if c_pc['sec'] else "y1", mode='lines+markers',
                                line=dict(width=1.8, color=color_pc),
                                marker=dict(size=3 if es_caudal_pc else 4, symbol='circle'),
                                fill='tozeroy' if es_caudal_pc else None,
                                fillcolor=color_pc.replace("hsl", "hsla").replace(")", ", 0.12)"),
                                hovertemplate=f'<b>%{{fullData.name}}</b>: %{{y:.2f}} {unidad_final_pc}<extra></extra>'
                            ))
                            leyenda_pc_items.append({"label": c_pc['label'], "color": color_pc})

                    fig_pc.update_layout(
                        template="plotly_dark", paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
                        height=300, width=1800, autosize=False, margin=dict(t=30, b=30, l=10, r=10), hovermode="x unified", showlegend=False,
                        xaxis=dict(color="white", showgrid=False, tickvals=ticks_filtrados, ticktext=etiquetas_filtradas, tickangle=0, tickformat="%d-%b-%Y %H:%M"),
                        yaxis=dict(title="Caudal (Lps)", color="#00d4ff", tickformat=".2f"),
                        yaxis2=dict(title="Presión (kg)", side="right", overlaying="y", color="#00ff00", showgrid=False, tickformat=".2f")
                    )

                    st.markdown("<p style='color:#ff5555; font-weight:bold; margin-bottom:5px; font-size:13px;'>Variables en este gráfico de Puntos Críticos:</p>", unsafe_allow_html=True)
                    items_pc_html = "".join([f'<div style="display:flex; align-items:center; margin-bottom:6px; overflow:hidden;"><span style="height:10px; width:16px; background-color:{item["color"]}; display:inline-block; margin-right:5px; border-radius:2px; flex-shrink:0;"></span><span style="color:white; font-size:10px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">{item["label"]}</span></div>' for item in leyenda_pc_items])
                    st.markdown(f'<div style="display:grid; grid-template-columns: repeat(1, 1fr); gap: 6px 10px; width:100%; margin-bottom:10px;">{items_pc_html}</div>', unsafe_allow_html=True)

                    st.markdown('<div class="scrollable-chart">', unsafe_allow_html=True)
                    st.plotly_chart(fig_pc, use_container_width=True)
                    st.markdown('</div>', unsafe_allow_html=True)
                else:
                    st.info("No se encontraron registros telemétricos para los Puntos Críticos en este sector.")
            except Exception as e:
                st.error(f"Error Scada Puntos Críticos: {e}")
        else:
            st.info("No hay Puntos Críticos configurados para este sector.")

    st.markdown("""
    <div style="text-align: center; margin-top: 40px; padding: 20px; background: rgba(0,212,255,0.02); border: 1px dashed #1f4068; border-radius: 10px;">
        <p style="color: #00d4ff; font-family: 'Orbitron', sans-serif; font-size: 14px; margin: 0;">
            Sistema visual Scada. Seleccione una opcion superior para generar el grafico.
        </p>
    </div>
    """, unsafe_allow_html=True)
