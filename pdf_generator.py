"""
Arma el documento final de la carta astral:

1. Elige una portada al azar de /assets/covers/
2. Llena la(s) hoja(s) de contenido con la información generada por Claude,
   colocando nombre/fecha/hora al inicio de cada página como pediste.
3. Convierte todo a un único PDF usando PDF.co
4. Regresa la ruta/URL final y qué portada se usó (para guardarlo en DB)

IMPORTANTE: Sube tus portadas ya diseñadas a /assets/covers/ (formato .docx o .pdf)
y tus machotes de contenido a /assets/templates/ (formato .docx con placeholders
tipo {{nombre}}, {{fecha_nacimiento}}, {{signo_occidental}}, etc.)
"""

import os
import random
import logging
from datetime import datetime
from docx import Document

from pdf_co_integration import merge_docx_to_pdf, docx_to_pdf

logger = logging.getLogger(__name__)

COVERS_DIR = os.path.join(os.path.dirname(__file__), "assets", "covers")
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "assets", "templates")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "generated_pdfs")

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Orden fijo de las secciones de contenido dentro del documento final.
# Cada archivo debe existir en /assets/templates/
CONTENT_TEMPLATE_ORDER = [
    "contenido_signo_occidental.docx",
    "contenido_signo_chino.docx",
    "contenido_signo_celta.docx",
    "contenido_signo_maya.docx",
    "contenido_signo_egipcio.docx",
    "cierre.docx",
]


def _pick_random_cover() -> str:
    """Elige un archivo de portada al azar de la carpeta de portadas."""
    if not os.path.isdir(COVERS_DIR):
        raise FileNotFoundError(f"No existe la carpeta de portadas: {COVERS_DIR}")

    covers = [f for f in os.listdir(COVERS_DIR) if f.lower().endswith((".docx", ".pdf"))]
    if not covers:
        raise FileNotFoundError(f"No hay portadas en {COVERS_DIR}. Sube al menos una.")

    return random.choice(covers)


def _fill_docx_template(template_path: str, output_path: str, context: dict):
    """
    Reemplaza placeholders {{campo}} dentro de un .docx.
    Funciona en párrafos y dentro de tablas.
    """
    doc = Document(template_path)

    def replace_in_paragraph(paragraph):
        for key, value in context.items():
            placeholder = "{{" + key + "}}"
            if placeholder in paragraph.text:
                for run in paragraph.runs:
                    if placeholder in run.text:
                        run.text = run.text.replace(placeholder, str(value))
                # fallback si el placeholder quedó partido entre runs
                full_text = "".join(r.text for r in paragraph.runs)
                if placeholder in full_text:
                    new_text = full_text.replace(placeholder, str(value))
                    for i, run in enumerate(paragraph.runs):
                        run.text = new_text if i == 0 else ""

    for paragraph in doc.paragraphs:
        replace_in_paragraph(paragraph)

    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    replace_in_paragraph(paragraph)

    doc.save(output_path)


def build_natal_chart_pdf(full_name: str, birth_date: str, birth_time: str, reading: dict) -> tuple:
    """
    Devuelve (pdf_path_or_url, cover_filename_used)
    """
    cover_file = _pick_random_cover()
    cover_path = os.path.join(COVERS_DIR, cover_file)

    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    safe_name = "".join(c for c in full_name if c.isalnum() or c == " ").strip().replace(" ", "_")
    work_dir = os.path.join(OUTPUT_DIR, f"{safe_name}_{timestamp}")
    os.makedirs(work_dir, exist_ok=True)

    # Contexto que se inyecta al inicio de cada página, como pediste
    header_context = {
        "nombre": full_name,
        "fecha_nacimiento": birth_date,
        "hora_nacimiento": birth_time if birth_time else "No especificada",
        "signo_occidental": reading.get("zodiac_western", ""),
        "signo_chino": reading.get("zodiac_chinese", ""),
        "signo_celta": reading.get("zodiac_celtic", ""),
        "signo_maya": reading.get("zodiac_mayan", ""),
        "signo_egipcio": reading.get("zodiac_egyptian", ""),
        "interpretacion": reading.get("interpretation", reading.get("detailed_interpretation", "")),
        "fecha_lectura": datetime.utcnow().strftime("%d/%m/%Y"),
    }

    docx_files_in_order = []

    # 1. Portada (si es .docx se rellena igual, por si tiene el nombre impreso)
    if cover_file.lower().endswith(".docx"):
        filled_cover = os.path.join(work_dir, "00_portada.docx")
        _fill_docx_template(cover_path, filled_cover, header_context)
        docx_files_in_order.append(filled_cover)
    else:
        # Si la portada ya es PDF fijo, se concatena directo al final
        docx_files_in_order.append(cover_path)

    # 2. Hojas de contenido, en el orden fijo definido arriba
    for i, template_name in enumerate(CONTENT_TEMPLATE_ORDER, start=1):
        template_path = os.path.join(TEMPLATES_DIR, template_name)
        if not os.path.exists(template_path):
            logger.warning(f"⚠️ Falta el template {template_name}, se omite.")
            continue
        filled_path = os.path.join(work_dir, f"{i:02d}_{template_name}")
        _fill_docx_template(template_path, filled_path, header_context)
        docx_files_in_order.append(filled_path)

    # 3. Convertir todo y fusionar en un único PDF final vía PDF.co.
    # merge_docx_to_pdf regresa la URL pública del PDF final (PDF.co la hostea),
    # que es lo que WhatsApp necesita para poder enviarlo como documento.
    local_backup_path = os.path.join(work_dir, "carta_astral_final.pdf")
    final_pdf_url = merge_docx_to_pdf(docx_files_in_order, local_backup_path)

    return final_pdf_url, cover_file
