"""
pdf_generator.py - VERSIÓN JPEG - Usa tus 4 fondos de Contenido/
1 Escencia solar.jpeg -> Carta Astral
2 Afinidades Zodiacales.jpeg -> Afinidades
3 Tarot Egipcio.jpeg -> Tarot
4 Posplanetas.jpeg -> Cierre / Planetas + Mensaje final

Usa ReportLab para escribir encima del JPEG
"""

import os
import logging
from datetime import datetime
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader

logger = logging.getLogger(__name__)

COVERS_DIR = os.path.join(os.path.dirname(__file__), "Portadas")
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "Contenido")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "generated_pdfs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Tu orden nuevo - exactamente tus 4 archivos
CONTENT_JPEG_ORDER = [
    "1 Escencia solar.jpeg",
    "2 Afinidades Zodiacales.jpeg",
    "3 Tarot Egipcio.jpeg",
    "4 Posplanetas.jpeg",
]

def _wrap_text(text, max_chars=90):
    """Corta texto largo en lineas de max_chars sin cortar palabras"""
    if not text:
        return []
    words = text.split()
    lines = []
    current = ""
    for w in words:
        if len(current + " " + w) <= max_chars:
            current = (current + " " + w).strip()
        else:
            lines.append(current)
            current = w
    if current:
        lines.append(current)
    return lines

def build_natal_chart_pdf(full_name: str, birth_date: str, birth_time: str, reading: dict) -> tuple:
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    safe_name = "".join(c for c in full_name if c.isalnum() or c == " ").strip().replace(" ", "_")
    pdf_path = os.path.join(OUTPUT_DIR, f"{safe_name}_{timestamp}.pdf")

    # Datos de Claude
    western = reading.get("zodiac_western", "")
    chinese = reading.get("zodiac_chinese", "")
    celtic = reading.get("zodiac_celtic", "")
    mayan = reading.get("zodiac_mayan", "")
    egyptian = reading.get("zodiac_egyptian", "")
    asc = reading.get("ascending_sign", "")
    moon = reading.get("moon_sign", "")
    interp = reading.get("detailed_interpretation", reading.get("interpretation", ""))
    tarot_list = reading.get("tarot_readings", [])
    overall = reading.get("overall_message", "")
    birth_place = reading.get("birth_place", "No especificado")
    gender = reading.get("birth_gender", "No especificado")

    c = canvas.Canvas(pdf_path, pagesize=A4)
    width, height = A4

    for jpeg_name in CONTENT_JPEG_ORDER:
        jpeg_path = os.path.join(TEMPLATES_DIR, jpeg_name)
        if not os.path.exists(jpeg_path):
            logger.warning(f"Falta fondo: {jpeg_path}")
            continue

        # Fondo JPEG pantalla completa
        c.drawImage(ImageReader(jpeg_path), 0, 0, width=width, height=height, preserveAspectRatio=True, anchor='c')

        # --- MAPEO DE CONTENIDO POR PAGINA ---
        c.setFillColorRGB(0.1, 0.1, 0.1)  # texto casi negro, cambia a blanco si tu jpeg es oscuro: 1,1,1
        c.setFont("Helvetica", 10)

        if "1 Escencia" in jpeg_name:
            # PAGINA 1 - ESENCIA SOLAR = carta astral principal
            y = height - 120
            c.setFont("Helvetica-Bold", 16)
            c.drawString(50, y, f"{full_name} - {western}")
            y -= 20
            c.setFont("Helvetica", 10)
            c.drawString(50, y, f"Fecha: {birth_date}  Hora: {birth_time}  Lugar: {birth_place}  Genero: {gender}")
            y -= 15
            c.drawString(50, y, f"Ascendente: {asc}  Luna: {moon}")
            y -= 25
            c.setFont("Helvetica-Bold", 12)
            c.drawString(50, y, "Interpretacion:")
            y -= 15
            c.setFont("Helvetica", 9)
            for line in _wrap_text(interp, 95)[:25]:  # 12-15 lineas de Claude, mostramos max 25 lineas fisicas
                c.drawString(50, y, line)
                y -= 12
                if y < 60:
                    break

        elif "2 Afinidades" in jpeg_name:
            # PAGINA 2 - AFINIDADES ZODIACALES
            y = height - 150
            c.setFont("Helvetica-Bold", 14)
            c.drawString(50, y, "Afinidades Zodiacales")
            y -= 25
            c.setFont("Helvetica", 11)
            c.drawString(50, y, f"Occidental: {western}")
            y -= 18
            c.drawString(50, y, f"Chino: {chinese}")
            y -= 18
            c.drawString(50, y, f"Celta: {celtic}")
            y -= 18
            c.drawString(50, y, f"Maya: {mayan}")
            y -= 18
            c.drawString(50, y, f"Egipcio: {egyptian}")
            y -= 30
            # aqui puedes agregar compatibilidad si tienes
            c.setFont("Helvetica", 9)
            c.drawString(50, y, "Cada signo aporta una energia ancestral que potencia tu destino.")

        elif "3 Tarot" in jpeg_name:
            # PAGINA 3 - TAROT EGIPCIO - 5 preguntas
            y = height - 120
            c.setFont("Helvetica-Bold", 14)
            c.drawString(50, y, "Tarot Egipcio - 5 Respuestas del Destino")
            y -= 20
            for i, t in enumerate(tarot_list[:5], 1):
                if y < 80:
                    break
                c.setFont("Helvetica-Bold", 10)
                q = t.get('question','')[:90]
                c.drawString(50, y, f"{i}. {q}")
                y -= 12
                c.setFont("Helvetica", 9)
                c.drawString(60, y, f"Carta: {t.get('card','')} | Respuesta: {t.get('answer','')}")
                y -= 12
                for line in _wrap_text(t.get('interpretation',''), 90)[:5]:
                    c.drawString(60, y, line)
                    y -= 11
                y -= 10

        elif "4 Posplanetas" in jpeg_name or "Posplanet" in jpeg_name:
            # PAGINA 4 - POSICION PLANETAS + CIERRE
            y = height - 130
            c.setFont("Helvetica-Bold", 14)
            c.drawString(50, y, "Posicion Planetaria y Mensaje Final")
            y -= 25
            c.setFont("Helvetica", 10)
            c.drawString(50, y, f"Nombre: {full_name}")
            y -= 15
            c.drawString(50, y, f"Signo: {western} | Asc: {asc} | Luna: {moon}")
            y -= 25
            c.setFont("Helvetica-Bold", 11)
            c.drawString(50, y, "Mensaje del Universo:")
            y -= 15
            c.setFont("Helvetica", 10)
            for line in _wrap_text(overall, 90)[:12]:
                c.drawString(50, y, line)
                y -= 13

        c.showPage()

    c.save()
    logger.info(f"PDF JPEG generado: {pdf_path}")

    # Portada random como antes
    cover_file = "default_cover.jpg"
    try:
        from final_pdf_generator_v2 import _pick_random_cover
        cover_file = _pick_random_cover(western)
    except:
        pass

    return pdf_path, cover_file
