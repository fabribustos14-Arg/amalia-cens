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
    initial_sidebar_state="collapsed"
)

# ---------------------------------------------------------
# 2. GESTIÓN DE CREDENCIALES
# ---------------------------------------------------------
API_KEY = st.secrets.get("GEMINI_API_KEY", "").strip()

if not API_KEY:
    st.error("⚠️ Clave GEMINI_API_KEY no encontrada en los secrets.")
    st.stop()

# ---------------------------------------------------------
# 3. LECTURA LOCAL DE DOCUMENTOS (PDF Y TXT)
# ---------------------------------------------------------
DOCS_DIR = "documentos"

@st.cache_resource(show_spinner="Procesando apuntes del CENS N° 3-419...")
def cargar_textos_documentos():
    textos_acumulados = []
    if not os.path.exists(DOCS_DIR):
        os.makedirs(DOCS_DIR, exist_ok=True)
        return ""

    for ruta in glob.glob(os.path.join(DOCS_DIR, "*.txt")):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                texto = f.read().strip()
                if texto:
                    textos_acumulados.append(f"--- DOCUMENTO: {os.path.basename(ruta)} ---\n{texto}")
        except Exception as e:
            st.warning(f"No se pudo leer '{os.path.basename(ruta)}': {e}")

    for ruta in glob.glob(os.path.join(DOCS_DIR, "*.pdf")):
        try:
            reader = PdfReader(ruta)
            paginas = [p.extract_text() or "" for p in reader.pages]
            texto_pdf = "\n".join(paginas).strip()
            if texto_pdf:
                textos_acumulados.append(f"--- DOCUMENTO PDF: {os.path.basename(ruta)} ---\n{texto_pdf}")
        except Exception as e:
            st.warning(f"No se pudo leer '{os.path.basename(ruta)}': {e}")

    return "\n\n".join(textos_acumulados)

contenido_apuntes = cargar_textos_documentos()

# ---------------------------------------------------------
# 4. INSTRUCCIONES DEL SISTEMA
# ---------------------------------------------------------
PROMPT_FILE = "prompt_sistema.txt"

def construir_prompt_sistema(base_apuntes):
    instrucciones = (
        "Eres AmalIA, la asistente virtual oficial del CENS N° 3-419. "
        "Eres empática, paciente, motivadora y respondes de forma clara a los estudiantes."
    )
    if os.path.exists(PROMPT_FILE):
        try:
            with open(PROMPT_FILE, "r", encoding="utf-8") as f:
                contenido = f.read().strip()
                if contenido:
                    instrucciones = contenido
        except Exception:
            pass

    if base_apuntes:
        return f"{instrucciones}\n\n=== APUNTES Y MATERIAL OFICIAL DE ESTUDIO ===\n{base_apuntes}"
    return instrucciones

SYSTEM_PROMPT = construir_prompt_sistema(contenido_apuntes)

# ---------------------------------------------------------
# 5. LLAMADA NATIVA PARA CLAVES "AQ." (HEADER x-goog-api-key)
# ---------------------------------------------------------
def consultar_gemini(historial_mensajes, prompt_sistema, clave):
    """
    Envía la solicitud REST directa usando x-goog-api-key,
    que es el estándar oficial de Google para las nuevas claves AQ.
    """
    # Nota: Google bloqueó TODA la familia "gemini-2.5-*" para proyectos/cuentas
    # nuevas ("no longer available to new users"), y ya había retirado "gemini-1.5-*".
    # Por eso usamos únicamente la generación vigente (3.x) y sus alias auto-actualizables,
    # que Google recomienda explícitamente en vez de fijar una versión con fecha.
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

    # Cabecera oficial para autenticar con claves AQ.
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
                    # La respuesta llegó vacía (por ejemplo, bloqueada por los filtros
                    # de seguridad). Probamos con el siguiente modelo de la lista.
                    ultimo_error = f"'{modelo}' devolvió una respuesta sin contenido."
                    continue
                partes = candidatos[0].get("content", {}).get("parts", [])
                texto = "".join(p.get("text", "") for p in partes).strip()
                if texto:
                    return texto
                ultimo_error = f"'{modelo}' devolvió una respuesta vacía."
                continue

            # La clave es inválida, fue revocada o no tiene la API habilitada.
            if response.status_code in (401, 403):
                raise Exception(
                    "La clave GEMINI_API_KEY fue rechazada por Google (código "
                    f"{response.status_code}). Verifica que la clave sea válida, que la "
                    "'Generative Language API' esté habilitada en el proyecto, y que la "
                    "clave no haya sido revocada. Detalle: " + response.text
                )

            # Se superó la cuota gratuita o el límite de solicitudes.
            if response.status_code == 429:
                ultimo_error = (
                    "Se alcanzó el límite de solicitudes (cuota) de la API de Gemini. "
                    "Espera unos minutos y volvé a intentar."
                )
                continue

            ultimo_error = f"Código {response.status_code}: {response.text}"
        except requests.exceptions.Timeout:
            ultimo_error = f"'{modelo}' no respondió a tiempo (timeout)."
        except Exception as e:
            ultimo_error = str(e)

    raise Exception(ultimo_error)

# ---------------------------------------------------------
# 6. ENCABEZADO Y PRESENTACIÓN VISUAL
# ---------------------------------------------------------
col1, col2, col3 = st.columns([1, 1.2, 1])
with col2:
    if os.path.exists(LOGO_PATH):
        st.image(LOGO_PATH, width=190)

st.markdown("<h2 style='text-align: center; margin-bottom: 2px;'>AmalIA - CENS N° 3-419</h2>", unsafe_allow_html=True)
st.markdown(
    "<p style='text-align: center; color: #888; font-size: 0.95rem; margin-top: 0px;'>"
    "Espacio de consultas para estudiantes: dudas sobre los apuntes de la materia "
    "y asistencia paso a paso para el uso del Aula Virtual."
    "</p>",
    unsafe_allow_html=True
)
st.divider()

# ---------------------------------------------------------
# 7. HISTORIAL DEL CHAT
# ---------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": "¡Hola! Te doy la bienvenida. Soy **AmalIA**, tu asistente virtual en el **CENS N° 3-419**. ¿En qué puedo orientarte hoy con la materia o con el aula virtual?"
        }
    ]

avatar_asistente = LOGO_PATH if os.path.exists(LOGO_PATH) else "🎓"

for msg in st.session_state.messages:
    avatar = avatar_asistente if msg["role"] == "assistant" else "👤"
    with st.chat_message(msg["role"], avatar=avatar):
        st.markdown(msg["content"])

# ---------------------------------------------------------
# 8. ENTRADA Y RESPUESTAS
# ---------------------------------------------------------
if prompt := st.chat_input("Escribe aquí tu consulta..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar=avatar_asistente):
        with st.spinner("AmalIA está consultando los apuntes..."):
            try:
                # Omitir el saludo inicial (siempre el primer mensaje) al armar
                # el historial para la API, sin depender de comparar textos.
                mensajes_a_enviar = st.session_state.messages[1:]
                if not mensajes_a_enviar:
                    mensajes_a_enviar = [{"role": "user", "content": prompt}]

                texto_respuesta = consultar_gemini(mensajes_a_enviar, SYSTEM_PROMPT, API_KEY)
                st.markdown(texto_respuesta)
                st.session_state.messages.append({"role": "assistant", "content": texto_respuesta})
            except Exception as e:
                st.error("Ocurrió un error al procesar tu mensaje. Vuelve a intentarlo en unos instantes.")
                st.caption(f"Detalle técnico: {e}")
