"""
pdf_generator.py - v4 (rueda zodiacal con Efemerides Suizas)
Canvas 2500x3300. Texto centrado por recuadro (proporciones 0-1).
Orden: 1) Portada 2) Esencia solar (Posicion Planetaria + rueda) 3) Afinidades+Signos
       4) Tarot egipcio (5 respuestas) 5) Horoscopo
"""
import os, glob, math, random, logging, unicodedata
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(__file__)
CONTENT_DIR = os.path.join(BASE_DIR, "Contenido")
COVERS_DIR = os.path.join(BASE_DIR, "Portadas")
FONTS_DIR = os.path.join(BASE_DIR, "fonts")
OUTPUT_DIR = os.path.join(BASE_DIR, "generated_pdfs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

CANVAS_W, CANVAS_H = 2500, 3300
DARK = (35, 25, 10)
GOLD = (150, 110, 15)

TPL_CARTA = "carta_astral.jpeg"
TPL_AFIN = "afinidades.jpeg"
TPL_TAROT = "tarot.jpeg"
TPL_HORO = "horoscopo.jpeg"

SIGN_PREFIX = {
    "aries": "aries", "tauro": "tauro", "geminis": "geminis", "cancer": "cancer",
    "leo": "leo", "virgo": "virgo", "libra": "libra", "escorpio": "scorp",
    "escorpion": "scorp", "scorpio": "scorp", "sagitario": "sagitario",
    "capricornio": "capricornio", "acuario": "acuario", "piscis": "piscis",
}

# CENTRO (x,y) de cada recuadro en proporcion 0-1 + ancho de caja (box). AJUSTA AQUI.
# NOTA: todas las Y se subieron ~1 cm (-0.018) el 2026-09-03, EXCEPTO
# carta_astral -> nombre y datos (hoja 1), que se dejaron igual a peticion del cliente.
COORDS = {
    "carta_astral": {
        "nombre": (0.05, 0.045), "datos": (0.95, 0.045),
        "planetas": (0.50, 0.517), "box_pl": 0.70,
        "ac": (0.31, 0.685), "dc": (0.69, 0.685),
        "mc": (0.31, 0.830), "ic": (0.69, 0.830),
        "box": 0.30,
        # Rueda zodiacal: centro (x,y) y radio (proporcion del ancho). AJUSTA AQUI.
        "rueda": (0.50, 0.290), "r_rueda": 0.20,
    },
    "afinidades": {
        "polaridad": (0.31, 0.207), "amistad": (0.69, 0.207),
        "fisica": (0.31, 0.367),   "intelectual": (0.69, 0.367),
        "chino": (0.31, 0.587),    "celta": (0.69, 0.587),
        "maya": (0.31, 0.740),     "egipcio": (0.69, 0.740),
        "box": 0.30,
    },
    "tarot": {
        "q1": (0.50, 0.175), "q2": (0.50, 0.307), "q3": (0.50, 0.430),
        "q4": (0.50, 0.560), "q5": (0.50, 0.695), "box": 0.72,
    },
    "horoscopo": {
        "amor": (0.50, 0.227), "trabajo": (0.50, 0.392),
        "dinero": (0.50, 0.552), "salud": (0.50, 0.712),
        "dia": (0.40, 0.785), "color": (0.40, 0.810), "numero": (0.40, 0.835),
        "box": 0.68,
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
    # Toma solo la primera palabra del signo, sin puntuacion.
    # (El texto ahora llega como "Escorpio. Intenso..." y antes rompia el match)
    first = ""
    if sign:
        cleaned = _strip(sign)
        cleaned = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in cleaned)
        parts = cleaned.split()
        first = parts[0] if parts else ""
    prefix = SIGN_PREFIX.get(first, None)
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

def _centered(d, text, cx_rel, cy_rel, W, H, font, box_rel, max_lines=6, gap=48, color=DARK):
    all_lines = _wrap(d, text, font, int(W * box_rel))
    if len(all_lines) > max_lines:
        kept = " ".join(all_lines[:max_lines]).rstrip()
        cut = kept.rfind(".")
        kept = kept[:cut + 1] if cut >= 40 else kept.rstrip(" ,;:") + "."
        all_lines = _wrap(d, kept, font, int(W * box_rel))[:max_lines]
    lines = all_lines  
    if not lines:
        return
    cx, cy = int(W * cx_rel), int(H * cy_rel)
    total_h = len(lines) * gap
    y = cy - total_h // 2
    for line in lines:
        d.text((cx, y), line, fill=color, font=font, anchor="ma")
        y += gap

def _open_tpl(name):
    path = os.path.join(CONTENT_DIR, name)
    if not os.path.exists(path):
        logger.warning(f"Falta plantilla: {path}")
        return None
    return Image.open(path).convert("RGB").resize((CANVAS_W, CANVAS_H))

# ---------- Rueda zodiacal ----------
SIGN_GLYPHS = "\u2648\u2649\u264A\u264B\u264C\u264D\u264E\u264F\u2650\u2651\u2652\u2653"
PLANET_GLYPHS = {"Sol": "\u2609", "Luna": "\u263D", "Mercurio": "\u263F", "Venus": "\u2640",
                 "Marte": "\u2642", "Jupiter": "\u2643", "Saturno": "\u2644",
                 "Urano": "\u2645", "Neptuno": "\u2646", "Pluton": "\u2647"}
ASPECTS = [(180, 7, (150, 45, 35)), (90, 6, (150, 45, 35)),   # tensos: rojo
           (120, 6, (40, 90, 140)), (60, 4, (40, 90, 140))]   # armonicos: azul
SS = 2  # supersampling para lineas suaves

def _draw_wheel(img, wheel, cx_rel, cy_rel, r_rel):
    """Dibuja la rueda sobre img (RGB). wheel = {'planets':{nombre:lon}, 'asc', 'mc', 'cusps'}."""
    planets = (wheel or {}).get("planets") or {}
    if not planets:
        return
    W, H = img.size
    R = int(W * r_rel) * SS
    pad = int(R * 0.12)
    size = 2 * (R + pad)
    layer = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    c = size // 2
    asc = wheel.get("asc")
    base = asc if asc is not None else 0.0  # sin hora: Aries a la izquierda

    def pt(lon, r):
        t = math.radians(180 + (lon - base))
        return (c + r * math.cos(t), c - r * math.sin(t))

    def circle(r, w, col):
        d.ellipse((c - r, c - r, c + r, c + r), outline=col, width=w)

    def text_at(txt, lon, r, font, col):
        x, y = pt(lon, r)
        d.text((x, y), txt, fill=col, font=font, anchor="mm")

    r_out, r_zod, r_pl, r_in = R, int(R * 0.84), int(R * 0.70), int(R * 0.56)
    gold, dark = GOLD + (255,), DARK + (255,)

    # Anillos
    circle(r_out, 4 * SS // 2 + 2, gold)
    circle(r_zod, 3, gold)
    circle(r_in, 3, gold)

    # Signos: divisiones, marcas de grados y glifos
    f_sign = _font(int(R * 0.085))
    for i in range(12):
        d.line((pt(i * 30, r_zod), pt(i * 30, r_out)), fill=gold, width=3)
        text_at(SIGN_GLYPHS[i], i * 30 + 15, (r_out + r_zod) / 2, f_sign, dark)
    for deg in range(0, 360, 5):
        if deg % 30:
            ln = R * (0.035 if deg % 10 == 0 else 0.02)
            d.line((pt(deg, r_zod), pt(deg, r_zod + ln)), fill=gold, width=2)

    # Casas (solo con hora y lugar)
    cusps = wheel.get("cusps")
    f_house = _font(int(R * 0.045))
    if cusps and len(cusps) == 12:
        for i, cu in enumerate(cusps):
            angular = i in (0, 3, 6, 9)
            d.line((pt(cu, r_in), pt(cu, r_zod)), fill=dark if angular else gold,
                   width=5 if angular else 2)
            nxt = cusps[(i + 1) % 12]
            mid = cu + ((nxt - cu) % 360) / 2
            text_at(str(i + 1), mid, r_in + R * 0.05, f_house, gold)
        f_ax = _font(int(R * 0.05), True)
        text_at("AC", wheel["asc"], r_out + pad * 0.55, f_ax, dark)
        if wheel.get("mc") is not None:
            text_at("MC", wheel["mc"], r_out + pad * 0.55, f_ax, dark)

    # Aspectos (dentro del circulo interior)
    items = list(planets.items())
    for a in range(len(items)):
        for b in range(a + 1, len(items)):
            diff = abs(items[a][1] - items[b][1]) % 360
            diff = min(diff, 360 - diff)
            for ang, orb, col in ASPECTS:
                if abs(diff - ang) <= orb:
                    d.line((pt(items[a][1], r_in - 4), pt(items[b][1], r_in - 4)),
                           fill=col + (200,), width=3)
                    break

    # Planetas: separa glifos que se enciman (min 8 grados en pantalla)
    order = sorted(items, key=lambda kv: kv[1])
    disp = [lon for _, lon in order]
    for _ in range(30):
        moved = False
        for i in range(len(disp)):
            j = (i + 1) % len(disp)
            gap = (disp[j] - disp[i]) % 360
            if 0 <= gap < 8 and len(disp) > 1:
                push = (8 - gap) / 2
                disp[i] -= push; disp[j] += push; moved = True
        if not moved:
            break
    f_pl = _font(int(R * 0.075))
    for (name, lon), dl in zip(order, disp):
        d.line((pt(lon, r_zod), pt(lon, r_zod - R * 0.04)), fill=dark, width=4)
        d.line((pt(lon, r_in), pt(lon, r_in + R * 0.025)), fill=dark, width=3)
        if abs(((dl - lon + 180) % 360) - 180) > 1:
            d.line((pt(lon, r_zod - R * 0.04), pt(dl, r_pl + R * 0.05)), fill=gold, width=2)
        text_at(PLANET_GLYPHS.get(name, name[:2]), dl, r_pl, f_pl, dark)

    final = size // SS
    layer = layer.resize((final, final), Image.LANCZOS)
    x0 = int(W * cx_rel) - final // 2
    y0 = int(H * cy_rel) - final // 2
    img.paste(layer, (x0, y0), layer)

def build_natal_chart_pdf(full_name, birth_date, birth_time, reading: dict):
    ts = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    safe = "".join(c for c in (full_name or "cliente") if c.isalnum() or c == " ").strip().replace(" ", "_")
    pdf_path = os.path.join(OUTPUT_DIR, f"{safe}_{ts}.pdf")

    western = reading.get("zodiac_western", "")
    place = reading.get("birth_place", "No especificado")
    planets = reading.get("planetary_positions", {}) or {}
    horo = reading.get("horoscopo", {}) or {}
    tarot = reading.get("tarot_readings", []) or []

    f_title = _font(64, True); f_lbl = _font(40, True); f_reg = _font(40); f_small = _font(34)
    GAP_S, GAP_R = 46, 54
    pages = []

    # --- PAGINA 1: PORTADA ---
    cover_path = pick_cover(western)
    cover_used = os.path.basename(cover_path) if cover_path else "sin_portada"
    if cover_path:
        pages.append(Image.open(cover_path).convert("RGB").resize((CANVAS_W, CANVAS_H)))

    # --- PAGINA 2: ESENCIA SOLAR (POSICION PLANETARIA + RUEDA) ---
    img = _open_tpl(TPL_CARTA)
    if img:
        d = ImageDraw.Draw(img); W, H = img.size; c = COORDS["carta_astral"]
        d.text((int(W*c["nombre"][0]), int(H*c["nombre"][1])), full_name or "",
               fill=DARK, font=f_reg, anchor="la")
        d.text((int(W*c["datos"][0]), int(H*c["datos"][1])),
               f"{birth_date}   {birth_time or 'Hora N/D'}   {place}",
               fill=DARK, font=f_small, anchor="ra")
        try:
            _draw_wheel(img, reading.get("wheel"), *c["rueda"], c["r_rueda"])
        except Exception as e:
            logger.error(f"No pude dibujar la rueda: {e}", exc_info=True)
        planets_txt = "   ".join(f"{k}: {v}" for k, v in planets.items())
        _centered(d, planets_txt, *c["planetas"], W, H, f_small, c["box_pl"], 6, GAP_S, GOLD)
        _centered(d, reading.get("ascendente", ""),  *c["ac"], W, H, f_small, c["box"], 6, GAP_S)
        _centered(d, reading.get("descendente", ""), *c["dc"], W, H, f_small, c["box"], 6, GAP_S)
        _centered(d, reading.get("medio_cielo", ""), *c["mc"], W, H, f_small, c["box"], 6, GAP_S)
        _centered(d, reading.get("fondo_cielo", ""),  *c["ic"], W, H, f_small, c["box"], 6, GAP_S)
        pages.append(img)

    # --- PAGINA 3: AFINIDADES + SIGNOS (2 columnas) ---
    img = _open_tpl(TPL_AFIN)
    if img:
        d = ImageDraw.Draw(img); W, H = img.size; c = COORDS["afinidades"]
        _centered(d, reading.get("afinidad_polaridad", ""),   *c["polaridad"],   W, H, f_small, c["box"], 6, GAP_S)
        _centered(d, reading.get("afinidad_amistad", ""),     *c["amistad"],     W, H, f_small, c["box"], 6, GAP_S)
        _centered(d, reading.get("afinidad_fisica", ""),      *c["fisica"],      W, H, f_small, c["box"], 6, GAP_S)
        _centered(d, reading.get("afinidad_intelectual", ""), *c["intelectual"], W, H, f_small, c["box"], 6, GAP_S)
        _centered(d, reading.get("zodiac_chinese", ""),  *c["chino"],   W, H, f_small, c["box"], 6, GAP_S)
        _centered(d, reading.get("zodiac_celtic", ""),   *c["celta"],   W, H, f_small, c["box"], 6, GAP_S)
        _centered(d, reading.get("zodiac_mayan", ""),    *c["maya"],    W, H, f_small, c["box"], 6, GAP_S)
        _centered(d, reading.get("zodiac_egyptian", ""), *c["egipcio"], W, H, f_small, c["box"], 6, GAP_S)
        pages.append(img)

    # --- PAGINA 4: TAROT ---
    img = _open_tpl(TPL_TAROT)
    if img:
        d = ImageDraw.Draw(img); W, H = img.size; c = COORDS["tarot"]
        for i, t in enumerate(tarot[:5], 1):
            cx, cy = c[f"q{i}"]
            cards = t.get("cards", t.get("card", ""))
            head = f"{cards}  ->  {t.get('answer','')}"
            d.text((int(W*cx), int(H*cy)), head, fill=GOLD, font=f_lbl, anchor="ma")
            _centered(d, t.get("interpretation", ""), cx, cy + 0.055, W, H, f_small, c["box"], 6, GAP_S)
        pages.append(img)

    # --- PAGINA 5: HOROSCOPO SEMANAL ---
    img = _open_tpl(TPL_HORO)
    if img:
        d = ImageDraw.Draw(img); W, H = img.size; c = COORDS["horoscopo"]
        _centered(d, horo.get("amor", ""),    *c["amor"],    W, H, f_small, c["box"], 6, GAP_S)
        _centered(d, horo.get("trabajo", ""), *c["trabajo"], W, H, f_small, c["box"], 6, GAP_S)
        _centered(d, horo.get("dinero", ""),  *c["dinero"],  W, H, f_small, c["box"], 6, GAP_S)
        _centered(d, horo.get("salud", ""),   *c["salud"],   W, H, f_small, c["box"], 6, GAP_S)
        d.text((int(W*c["dia"][0]),    int(H*c["dia"][1])),    str(horo.get("dia_suerte", "")),    fill=DARK, font=f_reg, anchor="lm")
        d.text((int(W*c["color"][0]),  int(H*c["color"][1])),  str(horo.get("color_suerte", "")),  fill=DARK, font=f_reg, anchor="lm")
        d.text((int(W*c["numero"][0]), int(H*c["numero"][1])), str(horo.get("numero_suerte", "")), fill=DARK, font=f_reg, anchor="lm")
        pages.append(img)

    if not pages:
        raise FileNotFoundError("No hay paginas para PDF (revisa Contenido/ y Portadas/)")
    pages[0].save(pdf_path, "PDF", resolution=150.0, save_all=True, append_images=pages[1:])
    logger.info(f"PDF generado: {pdf_path} (portada={cover_used})")
    return pdf_path, cover_used
