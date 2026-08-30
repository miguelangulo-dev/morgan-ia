"""
pdf_generator.py - Overlay de texto sobre plantillas (Pillow)
Coordenadas en proporcion (0-1) faciles de calibrar por plantilla.
"""
import os, logging
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "Contenido")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "generated_pdfs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

CANVAS_W, CANVAS_H = 1240, 1754  # A4 ~150dpi

CONTENT_JPEG_ORDER = [
    "1 Escencia solar.jpeg",
    "2 Afinidades Zodiacales.jpeg",
    "3 Tarot Egipcio.jpeg",
    "4 Posplanetas.jpeg",
]

# ---- CALIBRACION: ajusta estos valores (x,y en proporcion 0-1) ----
# Para calibrar: abre la imagen, mira donde empieza cada campo, divide pixel/ancho.
COORDS = {
    "3 Tarot Egipcio.jpeg": {   # 5 recuadros Pregunta 1..5
        "q1": (0.20, 0.28), "q2": (0.20, 0.42),
        "q3": (0.20, 0.56), "q4": (0.20, 0.70), "q5": (0.20, 0.84),
    },
    "4 Posplanetas.jpeg": {
        "sol": (0.50, 0.40), "luna": (0.62, 0.34), "mercurio": (0.40, 0.44),
        "venus": (0.44, 0.32), "marte": (0.58, 0.47), "jupiter": (0.70, 0.42),
        "saturno": (0.32, 0.37), "urano": (0.55, 0.57), "neptuno": (0.66, 0.62),
        "pluton": (0.36, 0.54), "ascendente": (0.22, 0.52), "medio_cielo": (0.50, 0.24),
    },
}
COLOR_DARK = (35, 25, 10)
COLOR_GOLD = (180, 140, 20)

def _font(size, bold=False):
    for name in (["DejaVuSans-Bold.ttf"] if bold else ["DejaVuSans.ttf"]):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()

def _wrap(draw, text, font, max_w):
    if not text: return []
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=font) <= max_w:
            cur = test
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

def build_natal_chart_pdf(full_name, birth_date, birth_time, reading: dict):
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    safe = "".join(c for c in full_name if c.isalnum() or c == " ").strip().replace(" ", "_")
    pdf_path = os.path.join(OUTPUT_DIR, f"{safe}_{ts}.pdf")

    western  = reading.get("zodiac_western", "");  chinese = reading.get("zodiac_chinese", "")
    celtic   = reading.get("zodiac_celtic", "");   mayan   = reading.get("zodiac_mayan", "")
    egyptian = reading.get("zodiac_egyptian", "")
    asc  = reading.get("ascending_sign", "");      moon = reading.get("moon_sign", "")
    interp = reading.get("detailed_interpretation", reading.get("interpretation", ""))
    tarot  = reading.get("tarot_readings", []);    overall = reading.get("overall_message", "")
    place  = reading.get("birth_place", "No especificado")
    gender = reading.get("birth_gender", "No especificado")
    planets = reading.get("planetary_positions", {})

    pages = []
    for jpeg in CONTENT_JPEG_ORDER:
        path = os.path.join(TEMPLATES_DIR, jpeg)
        if not os.path.exists(path):
            logger.warning(f"Falta fondo: {path}"); continue
        img = Image.open(path).convert("RGB").resize((CANVAS_W, CANVAS_H))
        d = ImageDraw.Draw(img); W, H = img.size
        f_title, f_reg, f_small = _font(34, True), _font(24), _font(20)

        if "1 Escencia" in jpeg:
            d.text((int(W*0.10), int(H*0.10)), f"{full_name}", fill=COLOR_DARK, font=f_title)
            d.text((int(W*0.10), int(H*0.14)), f"{western}  |  {birth_date}  {birth_time or ''}", fill=COLOR_DARK, font=f_reg)
            d.text((int(W*0.10), int(H*0.17)), f"Lugar: {place}   Genero: {gender}", fill=COLOR_DARK, font=f_reg)
            if asc or moon:
                d.text((int(W*0.10), int(H*0.20)), f"Ascendente: {asc}   Luna: {moon}", fill=COLOR_DARK, font=f_reg)
            y = int(H*0.25)
            for line in _wrap(d, interp, f_small, int(W*0.80))[:26]:
                d.text((int(W*0.10), y), line, fill=COLOR_DARK, font=f_small); y += 28

        elif "2 Afinidades" in jpeg:
            rows = [("Occidental", western), ("Chino", chinese), ("Celta", celtic),
                    ("Maya", mayan), ("Egipcio", egyptian)]
            y = int(H*0.22)
            for label, val in rows:
                d.text((int(W*0.12), y), f"{label}: {val}", fill=COLOR_DARK, font=f_reg); y += int(H*0.05)

        elif "3 Tarot" in jpeg:
            c = COORDS["3 Tarot Egipcio.jpeg"]
            for i, t in enumerate(tarot[:5], 1):
                x, yr = c[f"q{i}"]; x = int(W*x); y = int(H*yr)
                cards = t.get("cards", t.get("card", ""))
                d.text((x, y), f"{cards}  ->  {t.get('answer','')}", fill=COLOR_GOLD, font=_font(22, True))
                yy = y + 30
                for line in _wrap(d, t.get("interpretation",""), f_small, int(W*0.72))[:3]:
                    d.text((x, yy), line, fill=COLOR_DARK, font=f_small); yy += 24

        elif "4 Posplanetas" in jpeg:
            for key, (xr, yr) in COORDS["4 Posplanetas.jpeg"].items():
                x, y = int(W*xr), int(H*yr)
                d.text((x-40, y-14), key.upper(), fill=COLOR_GOLD, font=_font(20, True))
                pos = planets.get(key, "")
                if pos: d.text((x-40, y+10), str(pos)[:22], fill=COLOR_DARK, font=f_small)
            if overall:
                yy = int(H*0.88)
                for line in _wrap(d, overall, f_small, int(W*0.82))[:4]:
                    d.text((int(W*0.10), yy), line, fill=COLOR_DARK, font=f_small); yy += 24

        pages.append(img)

    if not pages:
        raise FileNotFoundError("No hay paginas para PDF")
    pages[0].save(pdf_path, "PDF", resolution=150.0, save_all=True, append_images=pages[1:])
    logger.info(f"PDF generado: {pdf_path}")
    return pdf_path, "1 Escencia solar.jpeg"
