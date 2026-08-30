
"""
Agente Claude FINAL - Con FIX n8n aplicado
- max_tokens 4000 -> 8000 en carta simple y completa
- tarot separado del calculo de carta (sin questions_text y sin tarot_readings)
- generate_tarot_reading con metodo Tirada de Decision 1-4 cartas (cards)
"""

import anthropic
import json
import re
import os
import logging

logger = logging.getLogger(__name__)

CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

def _extract_json(raw_text: str) -> str:
    """Quita fences de markdown (```json ... ```) si Claude los agrega."""
    text = raw_text.strip()
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            text = match.group(1).strip()
    return text.strip()

def _strip_accents(value):
    import unicodedata
    def clean(s):
        nfkd = unicodedata.normalize('NFKD', s)
        ascii_only = "".join([c for c in nfkd if not unicodedata.combining(c)])
        return ascii_only.replace("¿","").replace("¡","").replace("?","").replace("!","").replace("á","a").replace("é","e").replace("í","i").replace("ó","o").replace("ú","u")
    if isinstance(value, str):
        return clean(value)
    if isinstance(value, dict):
        return {k: _strip_accents(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_strip_accents(v) for v in value]
    return value


class AstroAgent:
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        self.model = "claude-sonnet-4-5"
    
    async def generate_natal_chart_simple(self, birth_date: str, questions: list = None, lang: str = "es") -> dict:
        idioma = "inglés" if lang == "en" else "español"
        prompt = f"""Responde en {idioma}.
Eres Morgan, experta en astrología ancestral. Analiza esta fecha y genera carta natal COMPLETA SOLO de zodiacos y personalidad.

FECHA DE NACIMIENTO: {birth_date}

Proporciona SOLO JSON válido (con acentos permitidos):

{{
  "zodiac_western": "Signo occidental ej: Aries",
  "zodiac_chinese": "Signo chino ej: Caballo",
  "zodiac_celtic": "Signo celta ej: Roble",
  "zodiac_mayan": "Signo maya",
  "zodiac_egyptian": "Signo egipcio",
  "ascending_sign": "Ascendente ej: Leo",
  "moon_sign": "Signo lunar ej: Tauro",
  "interpretation": "Párrafo de 12 a 15 líneas detalladas sobre personalidad, destino, energía, propósito de vida, retos y dones. Debe ser profundo y extenso.",
  "overall_message": "Mensaje final de 5 a 6 líneas, místico, cierre poderoso"
}}

REGLAS:
- Responde SOLO con JSON en {idioma}
- No incluyas tarot_readings aquí
- Interpretation debe ser LARGA 12-15 líneas mínimo
"""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8000,
                messages=[{"role": "user", "content": prompt}]
            )
            raw_text = _extract_json(response.content[0].text)
            if not raw_text:
                raise ValueError("Claude devolvio vacio")
            result = json.loads(raw_text)
            if questions:
                result["user_questions"] = questions
            logger.info(f"OK Carta natal simple para {birth_date} lang={lang}")
            return result
        except Exception as e:
            logger.error(f"Error generando carta natal simple: {str(e)}")
            return None
    
    async def generate_natal_chart_complete(self, birth_date: str, birth_time: str, birth_location: str = None, questions: list = None, lang: str = "es") -> dict:
        idioma = "inglés" if lang == "en" else "español"
        prompt = f"""Responde en {idioma}.
Eres Morgan, guardiana de los velos, experta en astrología, tarot egipcio y zodiacos ancestrales.

DATOS:
FECHA: {birth_date}
HORA: {birth_time}
LUGAR: {birth_location or "Desconocido"}

Calcula con hora exacta: ascendente, signo lunar, casas astrológicas, posición planetaria.

Proporciona SOLO JSON válido (con acentos permitidos):

{{
  "zodiac_western": "Signo occidental",
  "zodiac_chinese": "Signo chino",
  "zodiac_celtic": "Signo celta",
  "zodiac_mayan": "Signo maya",
  "zodiac_egyptian": "Signo egipcio",
  "ascending_sign": "Ascendente",
  "moon_sign": "Signo lunar",
  "detailed_interpretation": "Análisis DETALLADO de 12 a 15 líneas mínimo. Incluye: casas astrológicas, posición de planetas al nacer, energía predominante, propósitos de vida, karma, dones ocultos, retos. Debe ser extenso, místico y profundo.",
  "planetary_positions": {{
    "sol": "Aries Casa 1",
    "luna": "Tauro Casa 2",
    "ascendente": "Aries",
    "medio_cielo": "Capricornio"
  }},
  "overall_message": "Mensaje final místico de 5 a 6 líneas que cierre"
}}

REGLAS CRÍTICAS:
- Responde SOLO JSON válido en {idioma}
- detailed_interpretation LARGA 12-15 líneas, no 5-6
- No incluyas tarot_readings aquí, el tarot lo hace otra función
- overall_message 5-6 líneas, no 2-3
"""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8000,
                messages=[{"role": "user", "content": prompt}]
            )
            raw_text = _extract_json(response.content[0].text)
            if not raw_text:
                raise ValueError("Claude devolvio vacio")
            result = json.loads(raw_text)
            if questions:
                result["user_questions"] = questions
            logger.info(f"OK Carta natal completa para {birth_date} lang={lang}")
            return result
        except Exception as e:
            logger.error(f"Error generando carta natal completa: {str(e)}")
            return None
    
    async def generate_tarot_reading(self, questions: list, lang: str = "es") -> dict:
        questions_str = "\n".join([f"{i+1}. {q}" for i, q in enumerate(questions)])
        idioma = "espanol" if lang == "es" else "ingles"
        prompt = f"""Eres Morgania, tarotista experta en TAROT EGIPCIO (78 laminas).
Responde en {idioma}. Usa el metodo real de "Tirada de Decision" del Tarot Egipcio.

METODO PARA CADA PREGUNTA DE SI/NO:
- Saca de 1 a 4 cartas del Tarot Egipcio (varia el numero y las cartas segun la energia de la pregunta; NO repitas siempre la misma).
- El veredicto Si/No surge de CRUZAR las cartas entre si (no de una carta suelta): cartas luminosas/de accion (El Mago, El Triunfo, La Inspiracion, El Argonauta, La Resurreccion, La Transmutacion, El Regreso, El Prodigio, La Conjetura, La Consumacion) empujan hacia SI; cartas de bloqueo/densas (La Pasion, La Fragilidad, La Esperanza invertida, El Desasosiego, Impedimentos, La Desorientacion, El Resentimiento, La Incertidumbre) empujan hacia NO. La combinacion define la respuesta.
- Considera el CONTEXTO de la pregunta (amor, trabajo, salud, dinero) para traducir el simbolo.

PREGUNTAS DEL CONSULTANTE:
{questions_str}

Devuelve SOLO JSON valido (sin markdown). Formato:
{{
  "readings": [
    {{
      "question": "texto exacto de la pregunta",
      "cards": "1 a 4 cartas separadas por ' + ' con su numero, ej: La Carroza VII + El Loco 0",
      "answer": "Si" o "No",
      "interpretation": "3 a 4 lineas: que dicen las cartas EN CONJUNTO y por que dan ese Si/No para esta pregunta concreta"
    }}
  ],
  "overall_message": "Cierre mistico de 4 a 5 lineas que una las 5 respuestas"
}}

REGLAS:
- Exactamente {len(questions)} objetos en "readings", uno por pregunta y en orden.
- Cada respuesta debe ser un Si o No claro.
- Cada tirada usa cartas DIFERENTES.
- Solo JSON."""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=3500,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = _extract_json(response.content[0].text)
            if not raw_text:
                raise ValueError("Claude devolvio vacio")
            result = json.loads(raw_text)
            logger.info(f"OK Tirada tarot para {len(questions)} preguntas")
            return result
        except Exception as e:
            logger.error(f"Error generando tirada tarot: {str(e)}")
            return None
    
    async def generate_zodiac_affinity(self, user_zodiac: str, target_zodiac: str, lang: str = "es") -> dict:
        idioma = "inglés" if lang == "en" else "español"
        prompt = f"""Responde en {idioma}.
Eres experto en compatibilidad zodiacal.

SIGNO USUARIO: {user_zodiac}
SIGNO OBJETIVO: {target_zodiac}

Considera elementos, polaridad, emocional, intelectual, física y química.

JSON válido con acentos permitidos:

{{
  "user_zodiac": "{user_zodiac}",
  "target_zodiac": "{target_zodiac}",
  "affinity_percentage": 85,
  "affinity_level": "Muy Alta",
  "compatibility": {{
    "emotional": 8,
    "intellectual": 8,
    "physical": 9,
    "friendship": 9
  }},
  "interpretation": "Párrafo de 8 a 10 líneas explicando compatibilidad entre signos, dinámica, retos y fortalezas",
  "advice": "Consejo específico de 5 a 6 líneas para esta pareja"
}}

Solo JSON en {idioma}.
"""
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}]
            )
            raw_text = _extract_json(response.content[0].text)
            if not raw_text:
                raise ValueError("Claude devolvio vacio")
            result = json.loads(raw_text)
            logger.info(f"OK Afinidad: {user_zodiac} + {target_zodiac} lang={lang}")
            return result
        except Exception as e:
            logger.error(f"Error calculando afinidad: {str(e)}")
            return None
