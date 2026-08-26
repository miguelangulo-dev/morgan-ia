"""
Agente Claude FINAL - Sin acentos, prompts largos, tarot integrado
Corregido: 5-6 lineas -> 12-15, sin ¿ ¡ tildes, overall_message ampliado
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
    """
    Quita acentos/tildes/¿¡ de cualquier string dentro del dict, recursivamente.
    Usa unicodedata para garantizar texto limpio sin depender de que Claude obedezca.
    """
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
    
    async def generate_natal_chart_simple(self, birth_date: str, questions: list = None) -> dict:
        questions_text = ""
        if questions:
            q_str = "\n".join([f"{i+1}. {q}" for i, q in enumerate(questions)])
            questions_text = f"""
PREGUNTAS AL TAROT (5 preguntas del usuario):
{q_str}

Para cada pregunta, incluye en el JSON final un objeto tarot con:
- question, card, answer (Si/No), interpretation de 4-5 lineas explicando carta y simbologia
"""

        prompt = f"""Eres Morgan, experta en astrologia ancestral. Analiza esta fecha y genera carta natal COMPLETA.

FECHA DE NACIMIENTO: {birth_date}
{questions_text}

Proporciona SOLO JSON valido, sin acentos, sin caracteres especiales como ¿ ¡, sin tildes, todo en ASCII simple para evitar errores de encoding:

{{
  "zodiac_western": "Signo occidental ej: Aries",
  "zodiac_chinese": "Signo chino ej: Caballo",
  "zodiac_celtic": "Signo celta ej: Roble",
  "zodiac_mayan": "Signo maya",
  "zodiac_egyptian": "Signo egipcio",
  "interpretation": "Parrafo de 12 a 15 lineas detalladas sobre personalidad, destino, energia, proposito de vida, retos y dones. Debe ser profundo y extenso.",
  "tarot_readings": [
    {{
      "question": "texto pregunta 1",
      "card": "Nombre de carta egipcia con numero romano ej: El Loto XVIII",
      "answer": "Si o No",
      "interpretation": "Parrafo de 5 a 6 lineas explicando que significa la carta, su simbologia egipcia y como responde a la pregunta especifica del usuario"
    }}
  ],
  "overall_message": "Mensaje final de 5 a 6 lineas, mistico, cierre poderoso que una todas las respuestas"
}}

REGLAS:
- Responde SOLO con JSON
- No uses acentos ni tildes
- No uses simbolos ¿ ¡ 
- Si hay preguntas, genera tarot_readings con las 5
- Interpretation debe ser LARGA 12-15 lineas minimo
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
            result = _strip_accents(json.loads(raw_text))
            if questions:
                result["user_questions"] = questions
            logger.info(f"OK Carta natal simple para {birth_date}")
            return result
        except Exception as e:
            logger.error(f"Error generando carta natal simple: {str(e)}")
            return None
    
    async def generate_natal_chart_complete(self, birth_date: str, birth_time: str, birth_location: str = None, questions: list = None) -> dict:
        questions_text = ""
        if questions:
            q_str = "\n".join([f"{i+1}. {q}" for i, q in enumerate(questions)])
            questions_text = f"""
PREGUNTAS AL TAROT - EL USUARIO HIZO 5 PREGUNTAS AL DESTINO:
{q_str}

IMPORTANTE: Para CADA una de esas 5 preguntas debes hacer tirada tarot egipcio:
- Elige carta adecuada (no siempre la misma, varia segun pregunta)
- Responde Si/No claro
- Explica carta y simbologia en 5-6 lineas
- Relaciona con su pregunta especifica
"""

        prompt = f"""Eres Morgan, guardiana de los velos, experta en astrologia, tarot egipcio y zodiacos ancestrales.

DATOS:
FECHA: {birth_date}
HORA: {birth_time}
LUGAR: {birth_location or "Desconocido"}
{questions_text}

Calcula con hora exacta: ascendente, signo lunar, casas astrologicas, posicion planetaria.

Proporciona SOLO JSON valido, sin acentos, sin tildes, sin ¿ ¡, ASCII simple:

{{
  "zodiac_western": "Signo occidental",
  "zodiac_chinese": "Signo chino",
  "zodiac_celtic": "Signo celta",
  "zodiac_mayan": "Signo maya",
  "zodiac_egyptian": "Signo egipcio",
  "ascending_sign": "Ascendente",
  "moon_sign": "Signo lunar",
  "detailed_interpretation": "Analisis DETALLADO de 12 a 15 lineas minimo. Incluye: casas astrologicas, posicion de planetas al nacer, energia predominante, propositos de vida, karma, dones ocultos, retos. Debe ser extenso, mistico y profundo.",
  "tarot_readings": [
    {{
      "question": "pregunta del usuario",
      "card": "Nombre carta egipcia con numero romano - EJEMPLO generico, tu eliges la correcta segun pregunta",
      "answer": "Si o No",
      "interpretation": "5 a 6 lineas explicando simbologia de la carta egipcia y que significa para esta pregunta especifica"
    }}
  ],
  "overall_message": "Mensaje final mistico de 5 a 6 lineas que cierre y una todas las lecturas, dando consejo general"
}}

REGLAS CRITICAS:
- Responde SOLO JSON valido
- NO uses acentos, tildes, ni simbolos raros ¿ ¡
- detailed_interpretation LARGA 12-15 lineas, no 5-6
- Si hay 5 preguntas, tarot_readings debe tener 5 objetos, cada uno con carta DIFERENTE segun corresponda
- card es ejemplo, tu eliges carta real segun energia de pregunta
- overall_message 5-6 lineas, no 2-3
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
            result = _strip_accents(json.loads(raw_text))
            if questions:
                result["user_questions"] = questions
            logger.info(f"OK Carta natal completa para {birth_date}")
            return result
        except Exception as e:
            logger.error(f"Error generando carta natal completa: {str(e)}")
            return None
    
    async def generate_tarot_reading(self, questions: list, tarot_pdf_context: str = "") -> dict:
        questions_str = "\n".join([f"{i+1}. {q}" for i, q in enumerate(questions)])
        
        prompt = f"""Eres experto en tarot egipcio. Responde 5 preguntas con Si/No y carta.

PREGUNTAS:
{questions_str}

Para cada pregunta:
1. Elige carta egipcia DIFERENTE segun energia (no repitas siempre El Loto, varia)
2. Responde Si o No claro
3. Interpreta carta en 5-6 lineas

JSON solo, sin acentos, sin ¿ ¡, ASCII:

{{
  "readings": [
    {{
      "question": "texto pregunta",
      "card": "Nombre carta egipcia con numero romano - ejemplo generico, tu eliges la adecuada",
      "answer": "Si",
      "interpretation": "5 a 6 lineas de interpretacion con simbologia egipcia explicada y relacionada a la pregunta"
    }}
  ],
  "overall_message": "Mensaje general de 5 a 6 lineas mistico que una todo"
}}

REGLAS:
- Solo JSON
- Sin acentos
- Carta del ejemplo es solo ejemplo, tu eliges carta real
- overall_message largo 5-6 lineas
- Cada interpretation 5-6 lineas
"""
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            raw_text = _extract_json(response.content[0].text)
            if not raw_text:
                raise ValueError("Claude devolvio vacio")
            result = _strip_accents(json.loads(raw_text))
            logger.info(f"OK Tirada tarot para {len(questions)} preguntas")
            return result
        except Exception as e:
            logger.error(f"Error generando tirada tarot: {str(e)}")
            return None
    
    async def generate_zodiac_affinity(self, user_zodiac: str, target_zodiac: str) -> dict:
        prompt = f"""Eres experto en compatibilidad zodiacal.

SIGNO USUARIO: {user_zodiac}
SIGNO OBJETIVO: {target_zodiac}

Considera elementos, polaridad, emocional, intelectual, sexual.

JSON solo, sin acentos:

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
  "interpretation": "Parrafo de 8 a 10 lineas explicando compatibilidad entre signos, dinamica, retos y fortalezas",
  "advice": "Consejo especifico de 5 a 6 lineas para esta pareja"
}}

Solo JSON, sin acentos ni simbolos raros.
"""
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            raw_text = _extract_json(response.content[0].text)
            if not raw_text:
                raise ValueError("Claude devolvio vacio")
            result = _strip_accents(json.loads(raw_text))
            logger.info(f"OK Afinidad: {user_zodiac} + {target_zodiac}")
            return result
        except Exception as e:
            logger.error(f"Error calculando afinidad: {str(e)}")
            return None
 
