import os
import glob
import json
import requests
import streamlit as st
from PIL import Image
from pypdf import PdfReader

# ---------------------------------------------------------
# 1. CONFIGURACIÓN DE PÁGINA E IDENTIDAD VISUAL
# ---------------------------------------------------------
LOGO_PATH = "logo.jpg" if os.path.exists("logo.jpg") else "logo.png"

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
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------
# 2. GESTIÓN DE CREDENCIALES
# ---------------------------------------------------------
API_KEY = st.secrets.get("GEMINI_API_KEY", "").strip()

if not API_KEY:
    st.error("⚠️ Clave GEMINI_API_KEY no encontrada en los secrets.")
    st.stop()

# ---------------------------------------------------------
# 3. SELECCIÓN DE ROL Y SUBCARPETAS
# ---------------------------------------------------------
st.sidebar.title("Configuración")
if os.path.exists(LOGO_PATH):
    st.sidebar.image(LOGO_PATH, use_container_width=True)

ROL_OPCIONES = {
    "Estudiante": "estudiantes",
    "Docente": "docentes",
    "Directivo / Administrativo": "directivos"
}

# Inicializar o detectar cambio de rol para reiniciar la conversación
rol_seleccionado = st.sidebar.selectbox(
    "Selecciona tu perfil:",
    list(ROL_OPCIONES.keys()),
    key="rol_actual"
)

subcarpeta_rol = ROL_OPCIONES[rol_seleccionado]

# Si el usuario cambia de rol, reiniciamos el historial de conversación
if "ultimo_rol" not in st.session_state:
    st.session_state.ultimo_rol = rol_seleccionado

if st.session_state.ultimo_rol != rol_seleccionado:
    st.session_state.ultimo_rol = rol_seleccionado
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": f"¡Hola! Has cambiado al perfil **{rol_seleccionado}**. ¿En qué puedo orientarte hoy?"
        }
    ]

# Botón en la barra lateral para forzar la relectura de documentos
if st.sidebar.button("🔄 Recargar Documentos / Borrar Caché", use_container_width=True):
    st.cache_resource.clear()
    st.rerun()

# Botón directo de WhatsApp para inscripciones
st.sidebar.markdown("---")
st.sidebar.link_button(
    "📲 WhatsApp de Inscripciones",
    "https://wa.me/5492634566384?text=Hola%2C%20quisiera%20m%C3%A1s%20informaci%C3%B3n%20sobre%20las%20inscripciones.",
    use_container_width=True
)

# ---------------------------------------------------------
# 4. LECTURA LOCAL DE DOCUMENTOS POR ROL (RECURSIVA)
# ---------------------------------------------------------
BASE_DOCS_DIR = "documentos"

@st.cache_resource(show_spinner="Procesando apuntes del perfil seleccionado...")
def cargar_textos_documentos_por_rol(subcarpeta: str):
    """
    Carga documentos de la subcarpeta del rol específico (ej. documentos/estudiantes/)
    y también de la raíz 'documentos/' si existen archivos comunes a todos.
    Realiza una lectura recursiva para abarcar carpetas internas.
    """
    textos_acumulados = []
    archivos_procesados = []
    
    # Rutas a revisar: la subcarpeta específica del rol y la carpeta raíz general
    carpetas_a_revisar = [os.path.join(BASE_DOCS_DIR, subcarpeta), BASE_DOCS_DIR]

    for carpeta in carpetas_a_revisar:
        if not os.path.exists(carpeta):
            os.makedirs(carpeta, exist_ok=True)
            continue

        # Lectura de TXT recursiva
        for ruta in glob.glob(os.path.join(carpeta, "**", "*.txt"), recursive=True):
            if ruta in archivos_procesados:
                continue
            archivos_procesados.append(ruta)
            try:
                with open(ruta, "r", encoding="utf-8") as f:
                    texto = f.read().strip()
                    if texto:
                        textos_acumulados.append(f"--- DOCUMENTO: {os.path.basename(ruta)} ---\n{texto}")
            except Exception as e:
                st.warning(f"No se pudo leer '{os.path.basename(ruta)}': {e}")

        # Lectura de PDF recursiva
        for ruta in glob.glob(os.path.join(carpeta, "**", "*.pdf"), recursive=True):
            if ruta in archivos_procesados:
                continue
            archivos_procesados.append(ruta)
            try:
                reader = PdfReader(ruta)
                paginas = [p.extract_text() or "" for p in reader.pages]
                texto_pdf = "\n".join(paginas).strip()
                
                if not texto_pdf:
                    st.warning(f"⚠️ El archivo '{os.path.basename(ruta)}' no contiene texto digital legible (puede ser una imagen o escaneo).")
                else:
                    textos_acumulados.append(f"--- DOCUMENTO PDF: {os.path.basename(ruta)} ---\n{texto_pdf}")
            except Exception as e:
                st.warning(f"No se pudo leer '{os.path.basename(ruta)}': {e}")

    return "\n\n".join(textos_acumulados), len(archivos_procesados)

contenido_apuntes, total_archivos = cargar_textos_documentos_por_rol(subcarpeta_rol)

# Información de documentos detectados en la barra lateral
st.sidebar.caption(f"📄 Archivos leídos en este perfil: **{total_archivos}**")

# ---------------------------------------------------------
# 5. INSTRUCCIONES DEL SISTEMA
# ---------------------------------------------------------
PROMPT_FILE = "prompt_sistema.txt"

def construir_prompt_sistema(base_apuntes, rol):
    instrucciones = (
        "Eres AmalIA, la asistente virtual oficial del CENS N° 3-419. "
        "Eres empática, paciente, motivadora y respondes de forma clara a la comunidad educativa."
    )
    if os.path.exists(PROMPT_FILE):
        try:
            with open(PROMPT_FILE, "r", encoding="utf-8") as f:
                contenido = f.read().strip()
                if contenido:
                    instrucciones = contenido
        except Exception:
            pass

    prompt_final = f"{instrucciones}\n\n[CONTEXTO DE ATENCIÓN]: El usuario actual interactúa con el rol de: {rol}."
    if base_apuntes:
        prompt_final += f"\n\n=== APUNTES Y DOCUMENTACIÓN OFICIAL DISPONIBLE ===\n{base_apuntes}"
    return prompt_final

SYSTEM_PROMPT = construir_prompt_sistema(contenido_apuntes, rol_seleccionado)

# ---------------------------------------------------------
# 6. LLAMADA NATIVA PARA CLAVES "AQ." (HEADER x-goog-api-key)
# ---------------------------------------------------------
def consultar_gemini(historial_mensajes, prompt_sistema, clave):
    modelos_a_probar = [
        "gemini-flash-latest",
        "gemini-flash-lite-latest",
        "gemini-3.6-flash",
        "gemini-3.5-flash-lite"
    ]

    contents = []
    for msg in historial_mensajes:
        role = "user" if msg["role"] == "user" else "model"
        contents.append({
            "role": role,
            "parts": [{"text": msg["content"]}]
        })

    payload = {
        "system_instruction": {
            "parts": [{"text": prompt_sistema}]
        },
        "contents": contents,
        "generationConfig": {
            "temperature": 0.2
        }
    }

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": clave
    }

    ultimo_error = None
    for modelo in modelos_a_probar:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)

            if response.status_code == 200:
                data = response.json()
                candidatos = data.get("candidates") or []
                if not candidatos:
                    ultimo_error = f"'{modelo}' devolvió una respuesta sin contenido."
                    continue
                partes = candidatos[0].get("content", {}).get("parts", [])
                texto = "".join(p.get("text", "") for p in partes).strip()
                if texto:
                    return texto
                ultimo_error = f"'{modelo}' devolvió una respuesta vacía."
                continue

            if response.status_code in (401, 403):
                raise Exception(
                    "La clave GEMINI_API_KEY fue rechazada por Google (código "
                    f"{response.status_code}). Verifica que la clave sea válida. "
                    "Detalle: " + response.text
                )

            if response.status_code == 429:
                ultimo_error = "Se alcanzó el límite de solicitudes de la API de Gemini. Aguarda unos minutos."
                continue

            ultimo_error = f"Código {response.status_code}: {response.text}"
        except requests.exceptions.Timeout:
            ultimo_error = f"'{modelo}' no respondió a tiempo (timeout)."
        except Exception as e:
            ultimo_error = str(e)

    raise Exception(ultimo_error)

# ---------------------------------------------------------
# 7. ENCABEZADO Y PRESENTACIÓN VISUAL
# ---------------------------------------------------------
col1, col2, col3 = st.columns([1, 1.2, 1])
with col2:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=190)

st.markdown("<h2 style='text-align: center; margin-bottom: 2px;'>AmalIA - CENS N° 3-419</h2>", unsafe_allow_html=True)
st.markdown(
    f"<p style='text-align: center; color: #666; font-size: 0.95rem; margin-top: 0px;'>"
    f"Canal de asistencia para <b>{rol_seleccionado}</b>. Dudas pedagógicas, apuntes y soporte de Aula Virtual."
    "</p>",
    unsafe_allow_html=True
)
st.divider()

# ---------------------------------------------------------
# 8. HISTORIAL DEL CHAT
# ---------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": f"¡Hola! Te doy la bienvenida. Soy **AmalIA**, asistente virtual del **CENS N° 3-419**. Ingresaste con el perfil de **{rol_seleccionado}**. ¿En qué puedo orientarte hoy?"
        }
    ]

avatar_asistente = LOGO_PATH if os.path.exists(LOGO_PATH) else "🎓"

for msg in st.session_state.messages:
    avatar = avatar_asistente if msg["role"] == "assistant" else "👤"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# ---------------------------------------------------------
# 9. ENTRADA Y CONSULTAS RÁPIDAS
# ---------------------------------------------------------
prompt_sugerido = None

# Botones de consulta rápida según el rol
if rol_seleccionado == "Estudiante":
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("📝 Información sobre inscripciones", use_container_width=True):
            prompt_sugerido = "Hola, quisiera más información sobre las inscripciones."
    with col_btn2:
        if st.button("💻 ¿Cómo subir una tarea a Moodle?", use_container_width=True):
            prompt_sugerido = "¿Cómo hago para adjuntar y subir una tarea al aula virtual Moodle?"

placeholder_input = (
    "Hola, quisiera más información sobre las inscripciones..."
    if rol_seleccionado == "Estudiante"
    else "Escribe aquí tu consulta..."
)

prompt_manual = st.chat_input(placeholder=placeholder_input)
prompt = prompt_sugerido or prompt_manual

if prompt:
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar=avatar_asistente):
        with st.spinner("AmalIA está consultando la documentación..."):
            try:
                mensajes_a_enviar = st.session_state.messages[1:]
                if not mensajes_a_enviar:
                    mensajes_a_enviar = [{"role": "user", "content": prompt}]

                texto_respuesta = consultar_gemini(mensajes_a_enviar, SYSTEM_PROMPT, API_KEY)
                st.markdown(texto_respuesta)
                st.session_state.messages.append({"role": "assistant", "content": texto_respuesta})
            except Exception as e:
                st.error("Ocurrió un error al procesar tu mensaje. Vuelve a intentarlo en unos instantes.")
                st.caption(f"Detalle técnico: {e}")
