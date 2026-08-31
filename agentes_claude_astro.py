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

def _load_book() -> str:
    try:
        p = os.path.join(os.path.dirname(__file__), "tarot_egipcio_tirada_decision.md")
        with open(p, encoding="utf-8") as f:
            return f.read()[:6500]
    except Exception:
        return ""

def _lang_instr(lang: str) -> str:
    return ("Responde EXCLUSIVAMENTE en ingles." if lang == "en"
            else "Responde EXCLUSIVAMENTE en espanol.")

class AstroAgent:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        self.model = "claude-sonnet-4-5"
        self.book = _load_book()

    def _chart_prompt(self, birth_date, birth_time, birth_place, gender, lang):
        return f"""Eres Morgania, experta en astrologia ancestral. {_lang_instr(lang)}

DATOS:
Fecha: {birth_date}
Hora: {birth_time or 'Desconocida'}
Lugar: {birth_place or 'No especificado'}
Genero: {gender or 'No especificado'}

Devuelve SOLO JSON valido (sin markdown, sin texto extra). Estructura EXACTA:
{{
  "zodiac_western": "Signo occidental (una palabra, ej: Aries)",
  "zodiac_chinese": "Signo chino",
  "zodiac_celtic": "Signo celta",
  "zodiac_mayan": "Signo maya",
  "zodiac_egyptian": "Signo egipcio",
  "ascendente": "Signo + 1 linea breve",
  "descendente": "Signo + 1 linea breve",
  "medio_cielo": "Signo + 1 linea breve",
  "fondo_cielo": "Signo + 1 linea breve",
  "planetary_positions": {{
    "Sol": "Signo Casa", "Luna": "Signo Casa", "Mercurio": "Signo Casa",
    "Venus": "Signo Casa", "Marte": "Signo Casa", "Jupiter": "Signo Casa",
    "Saturno": "Signo Casa", "Urano": "Signo Casa", "Neptuno": "Signo Casa",
    "Pluton": "Signo Casa"
  }},
  "afinidad_polaridad": "2 lineas: signos de polaridad afin y opuesta",
  "afinidad_amistad": "2 lineas: con que signos hace mejor amistad",
  "afinidad_fisica": "2 lineas: afinidad fisica / atraccion",
  "afinidad_intelectual": "2 lineas: afinidad intelectual",
  "horoscopo": {{
    "amor": "2-3 lineas de amor y relaciones para esta semana",
    "trabajo": "2-3 lineas de trabajo y carrera",
    "dinero": "2-3 lineas de dinero y finanzas",
    "salud": "2-3 lineas de salud y bienestar",
    "dia_suerte": "un dia de la semana",
    "color_suerte": "un color",
    "numero_suerte": "un numero"
  }}
}}

REGLAS:
- ascendente/descendente/medio_cielo/fondo_cielo: BREVES (1 linea c/u) para que quepan.
- afinidades y horoscopo: 2-3 lineas maximo por campo.
- Si la hora es Desconocida, calcula el ascendente de forma aproximada y acláralo brevemente.
- Solo JSON, sin comentarios."""

    async def _run_chart(self, birth_date, birth_time=None, birth_place=None, gender=None, lang="es"):
        try:
            resp = self.client.messages.create(
                model=self.model, max_tokens=8000,
                messages=[{"role": "user", "content":
                           self._chart_prompt(birth_date, birth_time, birth_place, gender, lang)}],
            )
            raw = _extract_json(resp.content[0].text)
            if not raw:
                raise ValueError("Claude devolvio vacio (chart)")
            result = json.loads(raw)
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
        qs = "\n".join([f"{i+1}. {q}" for i, q in enumerate(questions)])
        book = f"\n\nRESUMEN DEL METODO (usalo como referencia real):\n{self.book}\n" if self.book else ""
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
      "cards": "1 a 4 cartas con su numero, separadas por ' + ' (ej: La Carroza VII + El Loco 0)",
      "answer": "Si" o "No",
      "interpretation": "3-4 lineas: que dicen las cartas EN CONJUNTO y por que dan ese Si/No para esta pregunta"
    }}
  ],
  "overall_message": "Cierre mistico de 4-5 lineas que una las respuestas"
}}

REGLAS:
- Exactamente {len(questions)} objetos en "readings", en orden.
- Cada respuesta un Si o No claro; cada tirada con cartas DIFERENTES.
- Solo JSON."""
        try:
            resp = self.client.messages.create(
                model=self.model, max_tokens=4000,
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
