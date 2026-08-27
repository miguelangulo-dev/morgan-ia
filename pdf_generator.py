"""
pdf_generator.py - VERSION SIN reportlab - Solo Pillow (para fix crash Railway)
Escribe nombre del planeta en ubicacion aproximada SOLO en pagina 4 Posplanetas
"""

import os
import logging
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "Contenido")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "generated_pdfs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

CONTENT_JPEG_ORDER = [
    "1 Escencia solar.jpeg",
    "2 Afinidades Zodiacales.jpeg",
    "3 Tarot Egipcio.jpeg",
    "4 Posplanetas.jpeg",
]

PLANET_COORDS_ESTIMADAS = {
    "sol": (0.50, 0.38),
    "luna": (0.65, 0.32),
    "mercurio": (0.38, 0.42),
    "venus": (0.42, 0.30),
    "marte": (0.60, 0.45),
    "jupiter": (0.72, 0.40),
    "saturno": (0.30, 0.35),
    "urano": (0.55, 0.55),
    "neptuno": (0.68, 0.60),
    "pluton": (0.35, 0.52),
    "ascendente": (0.20, 0.50),
    "medio_cielo": (0.50, 0.22),
}

def _wrap(text, max_chars=85):
    if not text: return []
    words = text.split()
    lines, cur = [], ""
    for w in words:
        if len(cur + " " + w) <= max_chars:
            cur = (cur + " " + w).strip()
        else:
            lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines

def build_natal_chart_pdf(full_name: str, birth_date: str, birth_time: str, reading: dict) -> tuple:
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    safe_name = "".join(c for c in full_name if c.isalnum() or c == " ").strip().replace(" ", "_")
    pdf_path = os.path.join(OUTPUT_DIR, f"{safe_name}_{timestamp}.pdf")

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
    planets = reading.get("planetary_positions", {})

    annotated_pages = []

    for jpeg_name in CONTENT_JPEG_ORDER:
        jpeg_path = os.path.join(TEMPLATES_DIR, jpeg_name)
        if not os.path.exists(jpeg_path):
            logger.warning(f"Falta fondo: {jpeg_path}")
            continue
        
        img = Image.open(jpeg_path).convert("RGB")
        # Redimensionar a A4 aprox para calidad
        img = img.resize((1240, 1754))  # A4 300dpi aprox
        draw = ImageDraw.Draw(img)
        
        try:
            # Intenta fuente bold, si no existe usa default
            font_bold = ImageFont.truetype("DejaVuSans-Bold.ttf", 32)
            font_reg = ImageFont.truetype("DejaVuSans.ttf", 22)
            font_small = ImageFont.truetype("DejaVuSans.ttf", 18)
        except:
            font_bold = ImageFont.load_default()
            font_reg = ImageFont.load_default()
            font_small = ImageFont.load_default()

        W, H = img.size

        if "1 Escencia" in jpeg_name:
            draw.text((60, 140), f"{full_name} - {western}", fill=(20,20,20), font=font_bold)
            draw.text((60, 190), f"Fecha: {birth_date}  Hora: {birth_time}", fill=(20,20,20), font=font_reg)
            draw.text((60, 220), f"Lugar: {birth_place}  Genero: {gender}", fill=(20,20,20), font=font_reg)
            draw.text((60, 250), f"Asc: {asc}  Luna: {moon}", fill=(20,20,20), font=font_reg)
            y = 300
            for line in _wrap(interp, 75)[:18]:
                draw.text((60, y), line, fill=(20,20,20), font=font_small)
                y += 26

        elif "2 Afinidades" in jpeg_name:
            y = 200
            draw.text((60, y), "Afinidades Zodiacales", fill=(20,20,20), font=font_bold); y+=50
            for label, val in [("Occidental", western), ("Chino", chinese), ("Celta", celtic), ("Maya", mayan), ("Egipcio", egyptian)]:
                draw.text((60, y), f"{label}: {val}", fill=(20,20,20), font=font_reg); y+=35

        elif "3 Tarot" in jpeg_name:
            y = 150
            draw.text((60, y), "Tarot Egipcio", fill=(20,20,20), font=font_bold); y+=50
            for i, t in enumerate(tarot_list[:5], 1):
                draw.text((60, y), f"{i}. {t.get('question','')[:70]}", fill=(20,20,20), font=font_small); y+=25
                draw.text((70, y), f"{t.get('card','')} - {t.get('answer','')}", fill=(80,80,80), font=font_small); y+=25
                for line in _wrap(t.get('interpretation',''), 70)[:2]:
                    draw.text((70, y), line, fill=(30,30,30), font=font_small); y+=22
                y+=10
                if y > H-100: break

        elif "4 Posplanetas" in jpeg_name:
            # SOLO AQUI: nombre del planeta en ubicacion aproximada
            for planet_key, (x_rel, y_rel) in PLANET_COORDS_ESTIMADAS.items():
                pos_text = planets.get(planet_key, "")
                x = int(W * x_rel)
                y = int(H * (1 - y_rel))  # PIL y=0 arriba, por eso invertimos
                # Dibujar etiqueta dorada con fondo semitransparente
                label = planet_key.upper()
                # fondo
                draw.rectangle([x-50, y-15, x+50, y+10], fill=(0,0,0,120))
                draw.text((x-40, y-12), label, fill=(255,215,0), font=font_bold)
                if pos_text:
                    draw.text((x-45, y+12), pos_text[:20], fill=(255,255,255), font=font_small)
            
            # Mensaje final abajo
            draw.text((60, H-200), f"Mensaje Final: {overall[:120]}...", fill=(255,255,255), font=font_reg)

        annotated_pages.append(img)

    if not annotated_pages:
        raise FileNotFoundError("No hay paginas para PDF")

    # Guardar como PDF multipagina con Pillow (no necesita reportlab)
    annotated_pages[0].save(pdf_path, "PDF", resolution=100.0, save_all=True, append_images=annotated_pages[1:])
    
    logger.info(f"PDF Pillow con posplanetas generado: {pdf_path}")
    return pdf_path, "4 Posplanetas.jpeg"

        cover_file = _pick_random_cover(western)
    except:
        pass

    return pdf_path, cover_file
