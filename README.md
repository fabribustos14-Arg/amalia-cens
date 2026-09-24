# AmalIA - Asistente Virtual Educativo (CENS N° 3-419)

AmalIA es una asistente virtual basada en Inteligencia Artificial desarrollada con **Streamlit** y la **API de Google Gemini (Gemini 1.5 Flash)**. Está diseñada específicamente para acompañar a los estudiantes jóvenes y adultos del **CENS N° 3-419**, resolviendo consultas académicas basadas exclusivamente en el material oficial y brindando asistencia paso a paso para el uso del aula virtual (Moodle).

---

## 📌 Características Principales

- **Respuestas Académicas Estrictas:** Consulta y analiza en tiempo real los apuntes y textos oficiales cargados en el sistema sin inventar información no presente en los documentos.
- **Soporte Digital y de Plataforma:** Guías claras y paso a paso para convertir archivos a PDF, subir tareas a Moodle, escanear documentos o renombrar entregas.
- **Actualización Dinámica de Material:** Basta con agregar o reemplazar archivos en la carpeta `documentos/` para actualizar la base de conocimiento del asistente.
- **Disponibilidad 24/7 en la Nube:** Desplegada en Streamlit Community Cloud, accesible desde cualquier computadora o celular sin requerir un servidor local activo.

---

## 📁 Estructura del Repositorio

```text
amalia-cens/
│
├── documentos/               # Apuntes, programas y guías en formato PDF o TXT
│   ├── modulo_1.pdf
│   └── guia_alumnos.txt
│
├── .streamlit/
│   └── secrets.toml          # Configuración local de claves (no subir a GitHub)
│
├── app.py                    # Código fuente de la aplicación Streamlit
├── requirements.txt          # Dependencias de Python requeridas
├── logo.png                  # Logotipo oficial de la institución / AmalIA
└── README.md                 # Documentación del proyecto