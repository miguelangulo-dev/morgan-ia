"""
agentes_claude_astro.py - Reescrito
- Campos alineados a las plantillas reales (carta astral, afinidades, tarot, horoscopo)
- Idioma: responde en el MISMO idioma del usuario (Claude nativo)
- Tarot: usa el resumen del libro tarot_egipcio_tirada_decision.md (tirada de decision, 1-4 cartas)
- max_tokens amplio para que el JSON no se trunque; acentos permitidos
"""
import os, json, re, logging
import anthropic

logger = logging.getLogger(__name__)
CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

def _extract_json(raw: str) -> str:
    t = (raw or "").strip()
    if "```" in t:
        m = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", t)
        if m:
            t = m.group(1).strip()
    return t.strip()

TAROT_DIR = os.path.join(os.path.dirname(__file__), "TarotEgipcio")

def _load_book() -> str:
    """Lee COMPLETOS todos los .md/.txt de TarotEgipcio/ (sin recortar)."""
    textos = []
    if os.path.isdir(TAROT_DIR):
        for name in sorted(os.listdir(TAROT_DIR)):
            if name.lower().endswith((".md", ".txt")):
                try:
                    with open(os.path.join(TAROT_DIR, name), encoding="utf-8") as f:
                        textos.append(f"### {name}\n{f.read()}")
                except Exception as e:
                    logger.error(f"No pude leer {name}: {e}")
    if not textos:  # Sin carpeta: usa el .md de la raiz
        raiz = os.path.join(os.path.dirname(__file__), "tarot_egipcio_tirada_decision.md")
        try:
            with open(raiz, encoding="utf-8") as f:
                textos.append(f.read())
        except Exception as e:
            logger.error(f"No pude leer {raiz}: {e}")
    if not textos:
        logger.error("Biblioteca Tarot Egipcio no encontrada (ni carpeta ni raiz)")
        return ""
    logger.info(f"Biblioteca TarotEgipcio cargada: {len(textos)} archivo(s)")
    return "\n\n".join(textos)

def _detect_lang(text: str, default: str = "es") -> str:
    t = f" {re.sub(r'[^a-zA-Záéíóúñü ]', ' ', (text or '').lower())} "
    en = sum(w in t for w in [" the "," will "," should "," my "," is "," am "," are "," do ",
                              " does "," can "," get "," with "," love "," job "," what "," when "])
    es = sum(w in t for w in [" el "," la "," los "," las "," que "," mi "," es "," voy "," debo ",
                              " puedo "," con "," amor "," trabajo "," cuando "," va "," me "])
    if en > es: return "en"
    if es > en: return "es"
    return default

# ---------- Efemerides Suizas (gratis, modo Moshier: sin archivos .se1) ----------
_SIGNOS = {"es": ["Aries","Tauro","Geminis","Cancer","Leo","Virgo","Libra","Escorpio",
                  "Sagitario","Capricornio","Acuario","Piscis"],
           "en": ["Aries","Taurus","Gemini","Cancer","Leo","Virgo","Libra","Scorpio",
                  "Sagittarius","Capricorn","Aquarius","Pisces"]}
_PLANETAS = [("Sol","Sun",0),("Luna","Moon",1),("Mercurio","Mercury",2),("Venus","Venus",3),
             ("Marte","Mars",4),("Jupiter","Jupiter",5),("Saturno","Saturn",6),
             ("Urano","Uranus",7),("Neptuno","Neptune",8),("Pluton","Pluto",9)]

def _geo(place):
    """Ciudad -> (lat, lon, zona horaria). None si no se encuentra."""
    if not place:
        return None
    try:
        from geopy.geocoders import Nominatim
        from tzfpy import get_tz
        loc = Nominatim(user_agent="morgan-ia-bot").geocode(place, timeout=10)
        if loc:
            return loc.latitude, loc.longitude, get_tz(loc.longitude, loc.latitude)
    except Exception as e:
        logger.warning(f"Geocoding fallo para '{place}': {e}")
    return None

def _efemerides(birth_date, birth_time, birth_place, lang="es"):
    """Calcula posiciones reales. birth_date 'DD/MM/AAAA', birth_time 'HH:MM' o None.
    Devuelve dict o None si algo falla (el bot sigue funcionando sin esto)."""
    try:
        import swisseph as swe
        from datetime import datetime
        from zoneinfo import ZoneInfo
        d, m, y = [int(x) for x in birth_date.split("/")]
        h, mi = [int(x) for x in birth_time.split(":")] if birth_time else (12, 0)
        geo = _geo(birth_place)
        tz = (geo[2] if geo and geo[2] else "America/Mexico_City")
        utc = datetime(y, m, d, h, mi, tzinfo=ZoneInfo(tz)).astimezone(ZoneInfo("UTC"))
        jd = swe.julday(utc.year, utc.month, utc.day, utc.hour + utc.minute / 60)
        sg = _SIGNOS.get(lang, _SIGNOS["es"])
        sign = lambda lon: sg[int(lon // 30) % 12]
        casa = "House" if lang == "en" else "Casa"

        cusps = None
        out = {}
        wheel = {"planets": {}, "asc": None, "mc": None, "cusps": None}
        if birth_time and geo:
            cusps, ascmc = swe.houses(jd, geo[0], geo[1], b"P")
            wheel.update(asc=ascmc[0], mc=ascmc[1], cusps=list(cusps))
            out["ascendente"] = sign(ascmc[0])
            out["descendente"] = sign(ascmc[0] + 180)
            out["medio_cielo"] = sign(ascmc[1])
            out["fondo_cielo"] = sign(ascmc[1] + 180)

        def _house(lon):
            for i in range(12):
                a, b = cusps[i], cusps[(i + 1) % 12]
                if (a <= lon < b) if a < b else (lon >= a or lon < b):
                    return i + 1
            return None

        planets = {}
        for es_n, en_n, pid in _PLANETAS:
            lon = swe.calc_ut(jd, pid, swe.FLG_MOSEPH)[0][0]
            wheel["planets"][es_n] = lon
            txt = sign(lon)
            if cusps:
                txt += f" {casa} {_house(lon)}"
            planets[en_n if lang == "en" else es_n] = txt
        out["planetary_positions"] = planets
        out["wheel"] = wheel  # longitudes para dibujar la rueda (no va a Claude)
        logger.info(f"Efemerides OK {birth_date} {birth_time} tz={tz} casas={bool(cusps)}")
        return out
    except Exception as e:
        logger.error(f"Efemerides fallo: {e}", exc_info=True)
        return None

def _lang_instr(lang: str) -> str:
    return ("Responde EXCLUSIVAMENTE en ingles." if lang == "en"
            else "Responde EXCLUSIVAMENTE en espanol.")

class AstroAgent:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        self.model = "claude-sonnet-4-5"
        self.book = _load_book()

    def _chart_prompt(self, birth_date, birth_time, birth_place, gender, lang, eph=None):
        eph_txt = ""
        if eph:
            eph_txt = ("\nPOSICIONES REALES (Efemerides Suizas). Son OBLIGATORIAS: usa EXACTAMENTE "
                       "estos signos; zodiac_western = signo del Sol:\n"
                       + json.dumps({k: v for k, v in eph.items() if k != "wheel"},
                                    ensure_ascii=False) + "\n")
        return f"""Eres Morgania, experta en astrologia ancestral. {_lang_instr(lang)}

DATOS:
Fecha: {birth_date}
Hora: {birth_time or 'Desconocida'}
Lugar: {birth_place or 'No especificado'}
Genero: {gender or 'No especificado'}
{eph_txt}
Devuelve SOLO JSON valido (sin markdown, sin texto extra). Estructura EXACTA:
{{
 "zodiac_western": "Signo occidental (una palabra, ej: Aries) + significado (CAMPO ESTRECHO: max 190 caracteres, cierra con punto)",
  "zodiac_chinese": "Signo chino + significado (CAMPO ESTRECHO: max 190 caracteres, cierra con punto)",
  "zodiac_celtic": "Signo celta + significado (CAMPO ESTRECHO: max 190 caracteres, cierra con punto)",
  "zodiac_mayan": "Signo maya + significado (CAMPO ESTRECHO: max 190 caracteres, cierra con punto)",
  "zodiac_egyptian": "Signo egipcio + significado (CAMPO ESTRECHO: max 190 caracteres, cierra con punto)",
  "ascendente": "Signo + descripcion (CAMPO ESTRECHO: max 190 caracteres, cierra con punto)",
  "descendente": "Signo + descripcion (CAMPO ESTRECHO: max 190 caracteres, cierra con punto)",
  "medio_cielo": "Signo + descripcion (CAMPO ESTRECHO: max 190 caracteres, cierra con punto)",
  "fondo_cielo": "Signo + descripcion (CAMPO ESTRECHO: max 190 caracteres, cierra con punto)",
  "planetary_positions": {{
    "Sol": "Signo Casa", "Luna": "Signo Casa", "Mercurio": "Signo Casa",
    "Venus": "Signo Casa", "Marte": "Signo Casa", "Jupiter": "Signo Casa",
    "Saturno": "Signo Casa", "Urano": "Signo Casa", "Neptuno": "Signo Casa",
    "Pluton": "Signo Casa"
  }},
  "afinidad_polaridad": "5-6 lineas: signos de polaridad afin y opuesta",
  "afinidad_amistad": "5-6 lineas: con que signos hace mejor amistad",
  "afinidad_fisica": "5-6 lineas: afinidad fisica / atraccion",
  "afinidad_intelectual": "5-6 lineas: afinidad intelectual",
  "horoscopo": {{
    "amor": "5-6 lineas de amor y relaciones para esta semana",
    "trabajo": "5-6 lineas de trabajo y carrera",
    "dinero": "5-6 lineas de dinero y finanzas",
    "salud": "5-6 lineas de salud y bienestar",
    "dia_suerte": "un dia de la semana",
    "color_suerte": "un color",
    "numero_suerte": "un numero"
  }}
}}

REGLAS (CRITICO - respeta el limite de caracteres de cada campo):
- CAMPO ESTRECHO (signos zodiac_*, ascendente/descendente/medio_cielo/fondo_cielo
  y todas las afinidades): MAXIMO 190 caracteres reales contando espacios. Es poco
  espacio: escribe 2-3 frases cortas y COMPLETAS. NO lo excedas.
- Los campos de horoscopo (amor/trabajo/dinero/salud): hasta 450 caracteres.
- REGLA DE ORO: cada texto debe CERRAR con punto final y NUNCA quedar a media frase.
  Antes de terminar cuenta los caracteres; si te acercas al limite, cierra la idea ya.
- Si la hora es Desconocida, calcula el ascendente aproximado y acláralo en pocas palabras.
- Solo JSON, sin comentarios."""

    async def _run_chart(self, birth_date, birth_time=None, birth_place=None, gender=None, lang="es"):
        try:
            eph = _efemerides(birth_date, birth_time, birth_place, lang)
            resp = self.client.messages.create(
                model=self.model, max_tokens=8000,
                messages=[{"role": "user", "content":
                           self._chart_prompt(birth_date, birth_time, birth_place, gender, lang, eph)}],
            )
            raw = _extract_json(resp.content[0].text)
            if not raw:
                raise ValueError("Claude devolvio vacio (chart)")
            result = json.loads(raw)
            if eph:  # Planetas: siempre los calculados, no los de Claude
                result["planetary_positions"] = eph["planetary_positions"]
                result["wheel"] = eph["wheel"]
            if birth_place: result["birth_place"] = birth_place
            if gender: result["birth_gender"] = gender
            logger.info(f"OK carta natal {birth_date} lang={lang}")
            return result
        except Exception as e:
            logger.error(f"Error carta natal: {e}", exc_info=True)
            return None

    # Compatibilidad con las firmas que ya usa conversation_flow
    async def generate_natal_chart_simple(self, birth_date, questions=None,
                                          birth_place=None, gender=None, lang="es"):
        return await self._run_chart(birth_date, None, birth_place, gender, lang)

    async def generate_natal_chart_complete(self, birth_date, birth_time,
                                            birth_location=None, questions=None,
                                            gender=None, lang="es"):
        return await self._run_chart(birth_date, birth_time, birth_location, gender, lang)

    async def generate_tarot_reading(self, questions: list, lang: str = "es") -> dict:
        lang = _detect_lang(" ".join(questions), default=lang)
        qs = "\n".join([f"{i+1}. {q}" for i, q in enumerate(questions)])
        book = (f"\n\nBIBLIOTECA TAROT EGIPCIO (UNICA fuente valida; usa SOLO las cartas, "
                f"numeros y significados de esta lista, NO uses Marsella ni Rider-Waite):\n{self.book}\n"
                if self.book else "")
        prompt = f"""Eres Morgania, tarotista experta en TAROT EGIPCIO (78 laminas). {_lang_instr(lang)}
Usa el metodo real de "Tirada de Decision" del Tarot Egipcio.{book}

METODO PARA CADA PREGUNTA DE SI/NO:
- Saca de 1 a 4 cartas del Tarot Egipcio (varia el numero y las cartas segun la pregunta; NO repitas siempre la misma).
- El veredicto Si/No surge de CRUZAR las cartas entre si (no de una carta suelta).
- Considera el contexto (amor, trabajo, salud, dinero) para traducir el simbolo.

PREGUNTAS DEL CONSULTANTE:
{qs}

Devuelve SOLO JSON valido:
{{
  "readings": [
    {{
      "question": "texto exacto de la pregunta",
      "cards": "1 a 4 cartas con su numero, separadas por ' + ' (ej: El Triunfo 7 + La Resurreccion 20)",
      "answer": "Si" o "No",
      "interpretation": "5-6 lineas: que dicen las cartas EN CONJUNTO y por que dan ese Si/No para esta pregunta"
    }}
  ],
  "overall_message": "Cierre mistico de 5-6 lineas que una las respuestas"
}}

REGLAS:
- Exactamente {len(questions)} objetos en "readings", en orden.
- Cada respuesta un Si o No claro; cada tirada con cartas DIFERENTES.
- interpretation y overall_message: MAXIMO 6 lineas cortas, SE CONCRETO y CIERRA la
  ultima frase con punto. Nunca dejes una idea a la mitad ni frases inconclusas.
- Solo JSON."""
        try:
            resp = self.client.messages.create(
                model=self.model, max_tokens=8000,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = _extract_json(resp.content[0].text)
            if not raw:
                raise ValueError("Claude devolvio vacio (tarot)")
            result = json.loads(raw)
            logger.info(f"OK tarot {len(questions)} preguntas lang={lang}")
            return result
        except Exception as e:
            logger.error(f"Error tarot: {e}", exc_info=True)
            return None
