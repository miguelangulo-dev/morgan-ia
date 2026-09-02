"""
pdf_generator.py - Reescrito (Pillow, sin coordenadas al pixel: texto CENTRADO por recuadro)
Orden: 1) Portada por signo (aleatoria)  2) Carta Astral  3) Afinidades  4) Tarot  5) Horoscopo
Coordenadas = CENTRO de cada recuadro en proporcion 0-1 (faciles de ajustar).
"""
import os, glob, random, logging, unicodedata
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(__file__)
CONTENT_DIR = os.path.join(BASE_DIR, "Contenido")
COVERS_DIR = os.path.join(BASE_DIR, "Portadas")
FONTS_DIR = os.path.join(BASE_DIR, "fonts")
OUTPUT_DIR = os.path.join(BASE_DIR, "generated_pdfs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

CANVAS_W, CANVAS_H = 1240, 1754
DARK = (35, 25, 10)
GOLD = (150, 110, 15)

# Plantillas de contenido (paginas 2..5)
TPL_CARTA = "carta_astral.jpeg"
TPL_AFIN = "afinidades.jpeg"
TPL_TAROT = "tarot.jpeg"
TPL_HORO = "horoscopo.jpeg"

# Escorpio -> Scorpio/Scorpion (typo en repo). Se resuelve por prefijo.
SIGN_PREFIX = {
    "aries": "aries", "tauro": "tauro", "geminis": "geminis", "cancer": "cancer",
    "leo": "leo", "virgo": "virgo", "libra": "libra", "escorpio": "scorp",
    "escorpion": "scorp", "scorpio": "scorp", "sagitario": "sagitario",
    "capricornio": "capricornio", "acuario": "acuario", "piscis": "piscis",
}

# CENTRO (x,y) de cada recuadro en proporcion 0-1 + ancho de caja. AJUSTA AQUI.
COORDS = {
    "carta_astral": {
        "nombre": (0.27, 0.061), "datos": (0.73, 0.061),
        "ac": (0.27, 0.643), "dc": (0.73, 0.643),
        "mc": (0.27, 0.723), "ic": (0.73, 0.723),
        "planetas": (0.50, 0.514), "box": 0.29,
    },
    "afinidades": {
        "polaridad": (0.27, 0.212), "amistad": (0.73, 0.212),
        "fisica": (0.27, 0.423), "intelectual": (0.73, 0.423),
        "chino": (0.27, 0.548), "celta": (0.73, 0.548),
        "maya": (0.27, 0.645), "egipcio": (0.73, 0.645), "box": 0.29,
    },
    "tarot": {
        "q1": (0.50, 0.214), "q2": (0.50, 0.380), "q3": (0.50, 0.512),
        "q4": (0.50, 0.644), "q5": (0.50, 0.771), "box": 0.80,
    },
    "horoscopo": {
        "amor": (0.50, 0.255), "trabajo": (0.50, 0.444),
        "dinero": (0.50, 0.548), "salud": (0.50, 0.683),
        "suerte": (0.50, 0.818), "box": 0.80,
    },
}

def _font(size, bold=False):
    fname = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for path in (os.path.join(FONTS_DIR, fname), fname):
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()

def _strip(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s or "")
                   if not unicodedata.combining(c)).lower().strip()

def pick_cover(sign: str):
    prefix = SIGN_PREFIX.get(_strip(sign).split()[0] if sign else "", None)
    if prefix and os.path.isdir(COVERS_DIR):
        matches = [f for f in os.listdir(COVERS_DIR)
                   if _strip(f).startswith(prefix) and f.lower().endswith((".jpeg", ".jpg", ".png"))]
        if matches:
            return os.path.join(COVERS_DIR, random.choice(matches))
    logger.warning(f"Sin portada para signo '{sign}' (prefix={prefix})")
    return None

def _wrap(d, text, font, max_w):
    if not text:
        return []
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if d.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines

def _centered(d, text, cx_rel, cy_rel, W, H, font, box_rel, max_lines=3, gap=30, color=DARK):
    """Dibuja texto centrado (horizontal) alrededor del centro vertical del recuadro."""
    lines = _wrap(d, text, font, int(W * box_rel))[:max_lines]
    if not lines:
        return
    cx, cy = int(W * cx_rel), int(H * cy_rel)
    total_h = len(lines) * gap
    y = cy - total_h // 2
    for line in lines:
        d.text((cx, y), line, fill=color, font=font, anchor="ma")  # 'ma' = centrado horiz, top
        y += gap

def _open_tpl(name):
    path = os.path.join(CONTENT_DIR, name)
    if not os.path.exists(path):
        logger.warning(f"Falta plantilla: {path}")
        return None
    return Image.open(path).convert("RGB").resize((CANVAS_W, CANVAS_H))

def build_natal_chart_pdf(full_name, birth_date, birth_time, reading: dict):
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    safe = "".join(c for c in (full_name or "cliente") if c.isalnum() or c == " ").strip().replace(" ", "_")
    pdf_path = os.path.join(OUTPUT_DIR, f"{safe}_{ts}.pdf")

    western = reading.get("zodiac_western", "")
    place = reading.get("birth_place", "No especificado")
    planets = reading.get("planetary_positions", {}) or {}
    horo = reading.get("horoscopo", {}) or {}
    tarot = reading.get("tarot_readings", []) or []

    f_title = _font(30, True); f_lbl = _font(22, True); f_reg = _font(22); f_small = _font(20)
    pages = []

    # --- PAGINA 1: PORTADA (sin texto) ---
    cover_path = pick_cover(western)
    cover_used = os.path.basename(cover_path) if cover_path else "sin_portada"
    if cover_path:
        pages.append(Image.open(cover_path).convert("RGB").resize((CANVAS_W, CANVAS_H)))

    # --- PAGINA 2: CARTA ASTRAL + PLANETAS ---
    img = _open_tpl(TPL_CARTA)
    if img:
        d = ImageDraw.Draw(img); W, H = img.size; c = COORDS["carta_astral"]
        d.text((int(W*c["nombre"][0]), int(H*c["nombre"][1])), full_name or "", fill=DARK, font=f_title, anchor="ma")
        d.text((int(W*c["datos"][0]), int(H*c["datos"][1])),
               f"{birth_date}   {birth_time or 'Hora N/D'}   {place}", fill=DARK, font=f_small, anchor="ma")
        _centered(d, reading.get("ascendente",""),  *c["ac"], W, H, f_small, c["box"], 3, 26)
        _centered(d, reading.get("descendente",""), *c["dc"], W, H, f_small, c["box"], 3, 26)
        _centered(d, reading.get("medio_cielo",""), *c["mc"], W, H, f_small, c["box"], 3, 26)
        _centered(d, reading.get("fondo_cielo",""),  *c["ic"], W, H, f_small, c["box"], 3, 26)
        planets_txt = "   ".join(f"{k}: {v}" for k, v in planets.items())
        _centered(d, planets_txt, *c["planetas"], W, H, f_small, 0.90, 4, 24, GOLD)
        pages.append(img)

    # --- PAGINA 3: AFINIDADES ---
    img = _open_tpl(TPL_AFIN)
    if img:
        d = ImageDraw.Draw(img); W, H = img.size; c = COORDS["afinidades"]
        _centered(d, reading.get("afinidad_polaridad",""),   *c["polaridad"],   W, H, f_small, c["box"], 2, 26)
        _centered(d, reading.get("afinidad_amistad",""),     *c["amistad"],     W, H, f_small, c["box"], 2, 26)
        _centered(d, reading.get("afinidad_fisica",""),      *c["fisica"],      W, H, f_small, c["box"], 2, 26)
        _centered(d, reading.get("afinidad_intelectual",""), *c["intelectual"], W, H, f_small, c["box"], 2, 26)
        _centered(d, reading.get("zodiac_chinese",""),  *c["chino"],   W, H, f_reg, c["box"], 2, 26)
        _centered(d, reading.get("zodiac_celtic",""),   *c["celta"],   W, H, f_reg, c["box"], 2, 26)
        _centered(d, reading.get("zodiac_mayan",""),    *c["maya"],    W, H, f_reg, c["box"], 2, 26)
        _centered(d, reading.get("zodiac_egyptian",""), *c["egipcio"], W, H, f_reg, c["box"], 2, 26)
        pages.append(img)

    # --- PAGINA 4: TAROT ---
    img = _open_tpl(TPL_TAROT)
    if img:
        d = ImageDraw.Draw(img); W, H = img.size; c = COORDS["tarot"]
        for i, t in enumerate(tarot[:5], 1):
            cx, cy = c[f"q{i}"]
            cards = t.get("cards", t.get("card", ""))
            head = f"{cards}  ->  {t.get('answer','')}"
            d.text((int(W*cx), int(H*cy)-24), head, fill=GOLD, font=f_lbl, anchor="ma")
            _centered(d, t.get("interpretation",""), cx, cy+0.02, W, H, f_small, c["box"], 2, 24)
        pages.append(img)

    # --- PAGINA 5: HOROSCOPO SEMANAL ---
    img = _open_tpl(TPL_HORO)
    if img:
        d = ImageDraw.Draw(img); W, H = img.size; c = COORDS["horoscopo"]
        _centered(d, horo.get("amor",""),    *c["amor"],    W, H, f_small, c["box"], 3, 26)
        _centered(d, horo.get("trabajo",""), *c["trabajo"], W, H, f_small, c["box"], 3, 26)
        _centered(d, horo.get("dinero",""),  *c["dinero"],  W, H, f_small, c["box"], 3, 26)
        _centered(d, horo.get("salud",""),   *c["salud"],   W, H, f_small, c["box"], 3, 26)
        suerte = f"Dia: {horo.get('dia_suerte','')}   Color: {horo.get('color_suerte','')}   Numero: {horo.get('numero_suerte','')}"
        _centered(d, suerte, *c["suerte"], W, H, f_reg, 0.90, 2, 28, GOLD)
        pages.append(img)

    if not pages:
        raise FileNotFoundError("No hay paginas para PDF (revisa Contenido/ y Portadas/)")
    pages[0].save(pdf_path, "PDF", resolution=150.0, save_all=True, append_images=pages[1:])
    logger.info(f"PDF generado: {pdf_path} (portada={cover_used})")
    return pdf_path, cover_used
