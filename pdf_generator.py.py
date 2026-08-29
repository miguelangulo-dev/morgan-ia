"""
pdf_generator.py - VERSION NUEVA
Plantillas: JPEG por pagina, texto dibujado con Pillow
Paginas en orden:
  1. Portada (segun signo occidental, carpeta Portadas/)
  2. Carta Astral (CartaAstral.jpeg)
  3. Afinidades Zodiacales (AfinidadesyZodiacos.jpeg)
  4. Tarot Egipcio (LecturaTarot.jpeg)
  5. Horoscopo Semanal (Horoscoposemanal.jpg)
"""

import os
import logging
import random
import unicodedata
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
PORTADAS_DIR = os.path.join(BASE_DIR, "Portadas")
CONTENIDO_DIR= os.path.join(BASE_DIR, "Contenido")
OUTPUT_DIR   = os.path.join(BASE_DIR, "generated_pdfs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Nombres exactos de las plantillas en /Contenido
T_CARTA     = "CartaAstral.jpeg"
T_AFINIDADES= "AfinidadesyZodiacos.jpeg"
T_TAROT     = "LecturaTarot.jpeg"
T_HOROSCOPO = "Horoscoposemanal.jpg"

# Mapa de signo -> variantes para buscar en nombres de archivo de portada
SIGNOS_MAP = {
    "aries":       ["aries"],
    "tauro":       ["tauro","taurus"],
    "taurus":      ["tauro","taurus"],
    "geminis":     ["geminis","gemini"],
    "gemini":      ["geminis","gemini"],
    "cancer":      ["cancer"],
    "leo":         ["leo"],
    "virgo":       ["virgo"],
    "libra":       ["libra"],
    "escorpio":    ["escorpio","scorpio","scorpion"],
    "scorpio":     ["escorpio","scorpio","scorpion"],
    "sagitario":   ["sagitario","sagittarius"],
    "sagittarius": ["sagitario","sagittarius"],
    "capricornio": ["capricornio","capricorn"],
    "capricorn":   ["capricornio","capricorn"],
    "acuario":     ["acuario","aquarius"],
    "aquarius":    ["acuario","aquarius"],
    "piscis":      ["piscis","pisces"],
    "pisces":      ["piscis","pisces"],
}

def _norm(s):
    """quita acentos y pone en minusculas para comparar"""
    n = unicodedata.normalize("NFKD", s.lower())
    return "".join(c for c in n if not unicodedata.combining(c))

def _pick_portada(signo: str) -> str:
    if not os.path.isdir(PORTADAS_DIR):
        raise FileNotFoundError(f"No existe carpeta Portadas/: {PORTADAS_DIR}")
    # Solo extensiones que Pillow puede abrir directamente (excluye .pdf)
    exts = (".jpeg", ".jpg", ".png")
    all_files = [f for f in os.listdir(PORTADAS_DIR) if f.lower().endswith(exts)]
    if not all_files:
        raise FileNotFoundError(f"No hay portadas en {PORTADAS_DIR}")
    signo_norm = _norm(signo)
    variantes  = SIGNOS_MAP.get(signo_norm, [signo_norm])
    matching   = [f for f in all_files if any(v in _norm(f) for v in variantes)]
    pool = matching if matching else all_files
    chosen = random.choice(pool[:3] if len(pool) >= 3 else pool)
    logger.info(f"Portada elegida: {chosen} para signo {signo}")
    return chosen

def _load_font(size: int, bold: bool = False):
    paths_bold = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "DejaVuSans-Bold.ttf",
    ]
    paths_reg = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "DejaVuSans.ttf",
    ]
    paths = paths_bold if bold else paths_reg
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except:
            continue
    return ImageFont.load_default()

def _wrap(text: str, max_chars: int = 70):
    """Parte texto largo en lineas de max_chars"""
    if not text:
        return []
    words = str(text).split()
    lines, cur = [], ""
    for w in words:
        if len(cur + " " + w) <= max_chars:
            cur = (cur + " " + w).strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


# ===========================================================================
# PAGINA 1: PORTADA (solo imagen, sin texto encima - el signo ya esta impreso)
# ===========================================================================
def _page_portada(signo: str) -> Image.Image:
    fname = _pick_portada(signo)
    path  = os.path.join(PORTADAS_DIR, fname)
    raw = Image.open(path)
    # Si tiene canal alpha (PNG RGBA/P), componer sobre fondo blanco para evitar fondo negro
    if raw.mode in ("RGBA", "P", "LA"):
        bg  = Image.new("RGB", raw.size, (255, 255, 255))
        src = raw.convert("RGBA")
        bg.paste(src, mask=src.split()[3])
        img = bg
    else:
        img = raw.convert("RGB")
    img = img.resize((900, 1600), Image.LANCZOS)
    return img


# ===========================================================================
# PAGINA 2: CARTA ASTRAL
# Campos: NOMBRE, Fecha, Hora, Lugar, Ascendente, Descendente, MC, IC
# ===========================================================================
def _page_carta_astral(reading: dict, full_name: str, birth_date: str, birth_time: str) -> Image.Image:
    path = os.path.join(CONTENIDO_DIR, T_CARTA)
    img  = Image.open(path).convert("RGB").resize((900, 1600), Image.LANCZOS)
    draw = ImageDraw.Draw(img)

    f_big  = _load_font(28, bold=True)
    f_med  = _load_font(22)
    f_sm   = _load_font(18)
    COLOR  = (60, 30, 10)     # marron oscuro, legible sobre pergamino

    # --- NOMBRE (debajo del scroll, y≈390) ---
    draw.text((130, 385), full_name[:50], fill=COLOR, font=f_big)

    # --- Fecha / Hora / Lugar (y≈460) ---
    hora_str  = birth_time or "No especificada"
    lugar_str = str(reading.get("birth_place", ""))[:25] or "No especificado"
    draw.text((105, 458), birth_date,  fill=COLOR, font=f_med)
    draw.text((330, 458), hora_str,    fill=COLOR, font=f_med)
    draw.text((525, 458), lugar_str,   fill=COLOR, font=f_med)

    planets = reading.get("planetary_positions", {})

    # --- Ascendente AC (caja izq, y≈1350) ---
    ac = str(planets.get("ascendente", reading.get("ascending_sign", "")))
    draw.text((90, 1355), ac[:35], fill=COLOR, font=f_sm)

    # --- Descendente DC (caja der, y≈1355) ---
    dc = str(planets.get("descendente", ""))
    draw.text((490, 1355), dc[:35], fill=COLOR, font=f_sm)

    # --- Medio Cielo MC (caja izq, y≈1510) ---
    mc = str(planets.get("medio_cielo", ""))
    draw.text((90, 1510), mc[:35], fill=COLOR, font=f_sm)

    # --- Fondo del Cielo IC (caja der, y≈1510) ---
    ic = str(planets.get("fondo_cielo", ""))
    draw.text((490, 1510), ic[:35], fill=COLOR, font=f_sm)

    return img


# ===========================================================================
# PAGINA 3: AFINIDADES ZODIACALES
# Campos: Polaridad, Amistad, Fisica, Intelectual, 4 zodiacos
# ===========================================================================
def _page_afinidades(reading: dict) -> Image.Image:
    path = os.path.join(CONTENIDO_DIR, T_AFINIDADES)
    img  = Image.open(path).convert("RGB").resize((900, 1600), Image.LANCZOS)
    draw = ImageDraw.Draw(img)

    f_med = _load_font(20)
    f_sm  = _load_font(17)

    interp = reading.get("detailed_interpretation", reading.get("interpretation", ""))

    # Polaridad (rojo)
    lines = _wrap(interp, 60)
    draw.text((110, 335), lines[0] if lines else "", fill=(160, 30, 30), font=f_med)
    if len(lines) > 1:
        draw.text((110, 360), lines[1], fill=(160, 30, 30), font=f_sm)

    # Amistad (azul) — siguiente bloque del texto
    draw.text((110, 490), lines[2] if len(lines) > 2 else "", fill=(30, 60, 160), font=f_med)
    draw.text((110, 515), lines[3] if len(lines) > 3 else "", fill=(30, 60, 160), font=f_sm)

    # Fisica (verde)
    draw.text((110, 645), lines[4] if len(lines) > 4 else "", fill=(30, 130, 60), font=f_med)
    draw.text((110, 670), lines[5] if len(lines) > 5 else "", fill=(30, 130, 60), font=f_sm)

    # Intelectual (dorado)
    draw.text((110, 795), lines[6] if len(lines) > 6 else "", fill=(160, 120, 10), font=f_med)
    draw.text((110, 820), lines[7] if len(lines) > 7 else "", fill=(160, 120, 10), font=f_sm)

    COLOR = (60, 30, 10)

    # Zodiaco Chino (caja izq)
    chino = str(reading.get("zodiac_chinese", ""))
    for i, l in enumerate(_wrap(chino, 28)[:3]):
        draw.text((70, 1080 + i*22), l, fill=COLOR, font=f_sm)

    # Zodiaco Celta (caja der)
    celta = str(reading.get("zodiac_celtic", ""))
    for i, l in enumerate(_wrap(celta, 28)[:3]):
        draw.text((470, 1080 + i*22), l, fill=COLOR, font=f_sm)

    # Zodiaco Maya (caja izq)
    maya = str(reading.get("zodiac_mayan", ""))
    for i, l in enumerate(_wrap(maya, 28)[:3]):
        draw.text((70, 1310 + i*22), l, fill=COLOR, font=f_sm)

    # Zodiaco Egipcio (caja der)
    egipcio = str(reading.get("zodiac_egyptian", ""))
    for i, l in enumerate(_wrap(egipcio, 28)[:3]):
        draw.text((470, 1310 + i*22), l, fill=COLOR, font=f_sm)

    return img


# ===========================================================================
# PAGINA 4: TAROT EGIPCIO
# Pregunta + Carta + Respuesta Si/No + Interpretacion
# 5 secciones de colores: rojo, azul, amarillo, verde, morado
# ===========================================================================
def _page_tarot(reading: dict) -> Image.Image:
    path = os.path.join(CONTENIDO_DIR, T_TAROT)
    img  = Image.open(path).convert("RGB").resize((900, 1600), Image.LANCZOS)
    draw = ImageDraw.Draw(img)

    f_sm  = _load_font(16)
    f_med = _load_font(18)

    tarot_list = reading.get("tarot_readings", [])

    # Y base de cada seccion (cabecera de color)
    SECCIONES = [
        (430,  (200, 255, 255, 255)),   # roja  -> texto oscuro
        (640,  (200, 255, 255, 255)),   # azul
        (850,  (200, 255, 255, 255)),   # amarilla
        (1060, (200, 255, 255, 255)),   # verde
        (1270, (200, 255, 255, 255)),   # morada
    ]
    TEXT_COLOR = (30, 15, 5)

    for idx, (y_base, _) in enumerate(SECCIONES):
        if idx >= len(tarot_list):
            break
        t = tarot_list[idx]
        q    = str(t.get("question", ""))[:70]
        card = str(t.get("card", ""))[:50]
        ans  = str(t.get("answer", ""))
        interp = str(t.get("interpretation", ""))

        # Pregunta (encima de la caja de color)
        draw.text((90, y_base - 20), f"P{idx+1}: {q}", fill=TEXT_COLOR, font=f_sm)
        # Carta y respuesta
        draw.text((90, y_base + 10), f"{card} — {ans}", fill=TEXT_COLOR, font=f_med)
        # Interpretacion (2 lineas)
        for i, l in enumerate(_wrap(interp, 75)[:2]):
            draw.text((90, y_base + 38 + i*20), l, fill=TEXT_COLOR, font=f_sm)

    return img


# ===========================================================================
# PAGINA 5: HOROSCOPO SEMANAL
# Secciones: Amor, Dinero, Salud, Trabajo, Consejo
# ===========================================================================
def _page_horoscopo(reading: dict) -> Image.Image:
    path = os.path.join(CONTENIDO_DIR, T_HOROSCOPO)
    img  = Image.open(path).convert("RGB").resize((900, 1600), Image.LANCZOS)
    draw = ImageDraw.Draw(img)

    f_sm  = _load_font(16)
    COLOR = (60, 30, 10)

    overall = str(reading.get("overall_message", ""))
    interp  = reading.get("detailed_interpretation", reading.get("interpretation", ""))
    lines_interp = _wrap(str(interp), 65)

    # Usamos partes del overall_message y la interpretacion para llenar las 5 secciones
    overall_lines = _wrap(overall, 65)

    SECCIONES_Y = [330, 570, 810, 1050, 1290]
    TEXTOS = [
        overall_lines[0:2],    # Amor
        overall_lines[2:4] if len(overall_lines) > 2 else lines_interp[0:2],
        overall_lines[4:6] if len(overall_lines) > 4 else lines_interp[2:4],
        lines_interp[4:6] if len(lines_interp) > 4 else lines_interp[0:2],
        lines_interp[6:8] if len(lines_interp) > 6 else lines_interp[0:2],
    ]

    for y, text_lines in zip(SECCIONES_Y, TEXTOS):
        for i, l in enumerate(text_lines[:2]):
            draw.text((110, y + i*24), l, fill=COLOR, font=f_sm)

    return img


# ===========================================================================
# FUNCION PRINCIPAL
# ===========================================================================
def build_natal_chart_pdf(full_name: str, birth_date: str, birth_time: str, reading: dict) -> tuple:
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    safe_name = "".join(c for c in full_name if c.isalnum() or c == " ").strip().replace(" ", "_")
    pdf_path  = os.path.join(OUTPUT_DIR, f"{safe_name}_{timestamp}.pdf")

    signo = reading.get("zodiac_western", "aries")

    pages = [
        _page_portada(signo),
        _page_carta_astral(reading, full_name, birth_date, birth_time),
        _page_afinidades(reading),
        _page_tarot(reading),
        _page_horoscopo(reading),
    ]

    # Guardar como PDF multipagina con Pillow
    pages[0].save(
        pdf_path,
        "PDF",
        resolution=150.0,
        save_all=True,
        append_images=pages[1:]
    )

    cover_used = _pick_portada.__name__   # solo para logging
    logger.info(f"PDF generado: {pdf_path} ({len(pages)} paginas)")
    return pdf_path, signo
