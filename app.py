import os
import glob
import streamlit as st
import google.generativeai as genai
from PIL import Image

# ---------------------------------------------------------
# 1. CONFIGURACIÓN DE PÁGINA E IDENTIDAD VISUAL
# ---------------------------------------------------------
LOGO_PATH = "logo.png"

# Icono de pestaña (usa el logo si existe, o el icono de graduación por defecto)
page_icon = "🎓"
if os.path.exists(LOGO_PATH):
    try:
        page_icon = Image.open(LOGO_PATH)
    except Exception:
        page_icon = "🎓"

st.set_page_config(
    page_title="AmalIA - CENS N° 3-419",
    page_icon=page_icon,
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ---------------------------------------------------------
# 2. GESTIÓN SEGURA DE LA API KEY (STREAMLIT SECRETS)
# ---------------------------------------------------------
API_KEY = st.secrets.get("GEMINI_API_KEY", None)

if not API_KEY:
    st.error(
        "⚠️ **Clave de API no configurada.** "
        "Recuerda agregar `GEMINI_API_KEY` en los Secrets de Streamlit Community Cloud."
    )
    st.stop()

genai.configure(api_key=API_KEY)

# ---------------------------------------------------------
# 3. CARGA DINÁMICA DE LA PERSONALIDAD (PROMPT DEL SISTEMA)
# ---------------------------------------------------------
PROMPT_FILE = "prompt_sistema.txt"

def cargar_instrucciones_sistema(ruta=PROMPT_FILE):
    """
    Lee las directivas de tono, empatía y reglas desde un archivo TXT externo.
    Si el archivo no existe, usa una instrucción básica de respaldo.
    """
    if os.path.exists(ruta):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                contenido = f.read().strip()
                if contenido:
                    return contenido
        except Exception as e:
            st.warning(f"Aviso: No se pudo leer '{ruta}'. Usando configuración base. Detalle: {e}")

    # Instrucción de respaldo si el archivo no está presente
    return (
        "Eres AmalIA, la asistente virtual oficial del CENS N° 3-419. "
        "Eres empática, paciente, motivadora y respondes de forma clara y accesible a los estudiantes."
    )

# ---------------------------------------------------------
# 4. CARGA DE BASE DE CONOCIMIENTO (DOCUMENTOS CON CACHÉ)
# ---------------------------------------------------------
DOCS_DIR = "documentos"

@st.cache_resource(show_spinner="Sincronizando apuntes y base de conocimiento...")
def inicializar_conocimiento():
    """
    Lee todos los archivos PDF y TXT dentro de 'documentos/' y los sube
    a la Files API de Google. Se almacena en caché para optimizar tiempos y cuota.
    """
    uploaded_files = []
    
    if not os.path.exists(DOCS_DIR):
        os.makedirs(DOCS_DIR, exist_ok=True)
        return uploaded_files

    rutas = glob.glob(os.path.join(DOCS_DIR, "*.pdf")) + glob.glob(os.path.join(DOCS_DIR, "*.txt"))
    
    for ruta in rutas:
        try:
            mime_type = "application/pdf" if ruta.lower().endswith(".pdf") else "text/plain"
            archivo_gemini = genai.upload_file(path=ruta, mime_type=mime_type)
            uploaded_files.append(archivo_gemini)
        except Exception as e:
            st.warning(f"No se pudo cargar '{os.path.basename(ruta)}': {e}")
            
    return uploaded_files

archivos_conocimiento = inicializar_conocimiento()

# ---------------------------------------------------------
# 5. INICIALIZACIÓN DEL CHAT CON GEMINI 1.5 FLASH
# ---------------------------------------------------------
@st.cache_resource
def obtener_chat_session(_archivos, prompt_sistema):
    """
    Crea una sesión de chat persistente con Gemini 1.5 Flash inyectando
    el prompt del sistema y los archivos adjuntos.
    """
    model = genai.GenerativeModel(
        model_name="gemini-1.5-flash",
        system_instruction=prompt_sistema,
        generation_config={
            "temperature": 0.2,  # Evita alucinaciones
            "top_p": 0.95,
        }
    )
    
    # Preparar contexto inicial con los apuntes subidos
    contexto_inicial = []
    if _archivos:
        contexto_inicial.extend(_archivos)
        contexto_inicial.append(
            "Utiliza los documentos adjuntos arriba como tu única base oficial para resolver consultas académicas."
        )
    
    chat = model.start_chat(history=[
        {"role": "user", "parts": contexto_inicial},
        {"role": "model", "parts": ["Comprendido. Soy AmalIA del CENS N° 3-419. Estoy lista para acompañar y resolver dudas sobre los apuntes y la plataforma virtual."]}
    ] if contexto_inicial else [])
    
    return chat

# Cargamos el prompt del TXT y creamos la sesión
instrucciones_actuales = cargar_instrucciones_sistema()
chat_session = obtener_chat_session(archivos_conocimiento, instrucciones_actuales)

# ---------------------------------------------------------
# 6. ENCABEZADO Y PRESENTACIÓN VISUAL
# ---------------------------------------------------------
# Centrado de logotipo
col1, col2, col3 = st.columns([1, 1.2, 1])
with col2:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=190)

st.markdown("<h2 style='text-align: center; margin-bottom: 2px;'>AmalIA - CENS N° 3-419</h2>", unsafe_allow_html=True)
st.markdown(
    "<p style='text-align: center; color: #555; font-size: 0.95rem; margin-top: 0px;'>"
    "Espacio de consultas para estudiantes: dudas sobre los apuntes de la materia "
    "y asistencia paso a paso para el uso del Aula Virtual."
    "</p>",
    unsafe_allow_html=True
)
st.divider()

# ---------------------------------------------------------
# 7. HISTORIAL DEL CHAT (SESSION STATE)
# ---------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "¡Hola! Te doy la bienvenida. Soy **AmalIA**, tu asistente virtual en el **CENS N° 3-419**. ¿En qué puedo orientarte hoy con la materia o con el aula virtual?"
        }
    ]

# Avatar para el asistente (usa logo.png si está disponible)
avatar_asistente = LOGO_PATH if os.path.exists(LOGO_PATH) else "🎓"

# Renderizar mensajes previos
for msg in st.session_state.messages:
    avatar = avatar_asistente if msg["role"] == "assistant" else "👤"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# ---------------------------------------------------------
# 8. ENTRADA DE CONSULTA Y RESPUESTA DEL ASISTENTE
# ---------------------------------------------------------
if prompt := st.chat_input("Escribe aquí tu consulta..."):
    # Guardar y mostrar mensaje del estudiante
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    # Generar respuesta de AmalIA
    with st.chat_message("assistant", avatar=avatar_asistente):
        with st.spinner("AmalIA está consultando los apuntes..."):
            try:
                response = chat_session.send_message(prompt)
                texto_respuesta = response.text
                st.markdown(texto_respuesta)
                
                # Almacenar respuesta en el historial de sesión
                st.session_state.messages.append({"role": "assistant", "content": texto_respuesta})
            except Exception as e:
                msg_error = "Disculpa, ocurrió un inconveniente temporal al procesar tu respuesta. Por favor, vuelve a intentar en unos momentos."
                st.error(msg_error)
