"""
agentes_claude_astro.py
Agente Claude para generacion de carta astral y tarot egipcio.

CAMBIOS v3.0:
- BUG4: Signo Maya calculado con Tzolk'in real (maya_sign.py), nunca vacio
- BUG5: Tarot lee cartas SOLO de tarot_egipcio_tirada_decision.md (tarot_service.py)
- BUG6: Branding "Un producto de Sincronia Tech Developers S.A.S." en interpretaciones
"""

import anthropic
import json
import re
import os
import logging
import unicodedata

from maya_sign import get_maya_sign
from tarot_service import cargar_biblioteca, construir_contexto_prompt, validar_tirada

logger = logging.getLogger(__name__)

CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

BRANDING = "Un producto de Sincronia Tech Developers S.A.S. - www.sincron-ia.com.mx"


def _extract_json(raw_text: str) -> str:
    """Quita fences de markdown (```json ... ```) si Claude los agrega."""
    text = raw_text.strip()
    if "```" in text:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
        if match:
            text = match.group(1).strip()
    return text.strip()


def _strip_accents(value):
    """Elimina acentos recursivamente para evitar errores de encoding en PDF."""
    if isinstance(value, str):
        nfkd = unicodedata.normalize("NFKD", value)
        return "".join(c for c in nfkd if not unicodedata.combining(c))
    if isinstance(value, dict):
        return {k: _strip_accents(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_strip_accents(v) for v in value]
    return value


class AstroAgent:
    """Agente Claude para lectura astrologica y tarot egipcio."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        self.model = "claude-sonnet-4-5"

    # ------------------------------------------------------------------
    # Carta natal completa (con hora y lugar)
    # ------------------------------------------------------------------

    async def generate_natal_chart_complete(
        self,
        birth_date: str,
        birth_time: str,
        birth_location: str = None,
        questions: list = None,
    ) -> dict:
        """
        Genera carta natal completa.
        birth_date:     "1990-03-15"
        birth_time:     "14:30"
        birth_location: "Ciudad de Mexico, Mexico" (opcional)
        questions:      lista de hasta 5 preguntas para tirada de tarot
        """
        # BUG4: calcular signo maya con algoritmo real
        maya_sign = get_maya_sign(birth_date)

        # BUG5: contexto de cartas reales para Claude
        tarot_contexto = construir_contexto_prompt() if questions else ""

        preguntas_str = ""
        if questions:
            preguntas_str = "\n\nPREGUNTAS TAROT (responde Si/No con interpretacion):\n"
            preguntas_str += "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions[:5]))

        prompt = f"""Eres un experto en astrologia y tarot. Genera una carta natal completa.

FECHA: {birth_date}
HORA: {birth_time}
LUGAR: {birth_location or "Desconocido"}
SIGNO MAYA (ya calculado, usa este valor exacto): {maya_sign}

{tarot_contexto}

Responde SOLO con JSON valido, sin texto extra ni markdown:
{{
  "zodiac_western": "Signo occidental",
  "zodiac_chinese": "Signo chino",
  "zodiac_celtic": "Arbol celta",
  "zodiac_mayan": "{maya_sign}",
  "zodiac_egyptian": "Dios/Diosa egipcia",
  "ascending_sign": "Signo ascendente calculado con hora y lugar",
  "moon_sign": "Signo lunar",
  "ascendente": "Descripcion del ascendente (2-3 lineas)",
  "descendente": "Descripcion del descendente (2-3 lineas)",
  "medio_cielo": "Descripcion del Medio Cielo (2-3 lineas)",
  "fondo_cielo": "Descripcion del Fondo del Cielo (2-3 lineas)",
  "planetary_positions": {{
    "Sol": "Grado y signo",
    "Luna": "Grado y signo",
    "Mercurio": "Grado y signo",
    "Venus": "Grado y signo",
    "Marte": "Grado y signo",
    "Jupiter": "Grado y signo",
    "Saturno": "Grado y signo"
  }},
  "afinidad_polaridad": "Descripcion afinidad polaridad (2-3 lineas)",
  "afinidad_amistad": "Descripcion afinidad amistad (2-3 lineas)",
  "afinidad_fisica": "Descripcion afinidad fisica (2-3 lineas)",
  "afinidad_intelectual": "Descripcion afinidad intelectual (2-3 lineas)",
  "detailed_interpretation": "Analisis detallado 10-12 lineas incluyendo casas astrologicas",
  "horoscopo": {{
    "amor": "Lectura amor esta semana (3-4 lineas)",
    "trabajo": "Lectura trabajo esta semana (3-4 lineas)",
    "dinero": "Lectura dinero esta semana (3-4 lineas)",
    "salud": "Lectura salud esta semana (3-4 lineas)",
    "dia_suerte": "Lunes",
    "color_suerte": "Dorado",
    "numero_suerte": "7"
  }}{preguntas_str and """,
  "tarot_readings": [
    {{
      "pregunta": "pregunta 1 exacta",
      "card": "Nombre carta EXACTO de la biblioteca oficial",
      "numero_carta": 0,
      "answer": "Si o No",
      "interpretation": "Interpretacion 3-4 lineas basada en simbolismo egipcio"
    }}
  ]""" or ""}
}}

REGLAS OBLIGATORIAS:
- zodiac_mayan DEBE ser exactamente: {maya_sign}
- Las cartas de tarot_readings DEBEN ser nombres EXACTOS de la BIBLIOTECA OFICIAL listada arriba
- Responde SOLO con JSON, sin markdown, sin texto antes ni despues"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}],
            )

            raw_text = _extract_json(response.content[0].text)
            if not raw_text:
                raise ValueError("Claude devolvio vacio")

            result = _strip_accents(json.loads(raw_text))

            # BUG4: forzar signo maya correcto (nunca vacio)
            result["zodiac_mayan"] = _strip_accents(maya_sign)

            # BUG5: validar cartas si hay tirada
            if questions and "tarot_readings" in result:
                es_valida, errores = validar_tirada(result["tarot_readings"])
                if not es_valida:
                    logger.warning(f"[Tarot] Cartas invalidas: {errores}. Regenerando con fallback.")
                    result["tarot_readings"] = _tarot_fallback(questions)

            logger.info(f"OK Carta natal completa para {birth_date}")
            return result

        except Exception as e:
            logger.error(f"Error generando carta natal completa: {e}", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Carta natal simple (solo fecha)
    # ------------------------------------------------------------------

    async def generate_natal_chart_simple(
        self, birth_date: str, questions: list = None
    ) -> dict:
        """
        Genera carta natal simplificada (solo fecha, sin hora).
        """
        # BUG4: calcular signo maya con algoritmo real
        maya_sign = get_maya_sign(birth_date)

        # BUG5: contexto de cartas reales para Claude
        tarot_contexto = construir_contexto_prompt() if questions else ""

        preguntas_str = ""
        if questions:
            preguntas_str = "\n\nPREGUNTAS TAROT (responde Si/No con interpretacion):\n"
            preguntas_str += "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions[:5]))

        prompt = f"""Eres un experto en astrologia y tarot. Genera una carta natal.

FECHA: {birth_date}
HORA: Desconocida (usa 12:00 como referencia)
SIGNO MAYA (ya calculado, usa este valor exacto): {maya_sign}

{tarot_contexto}

Responde SOLO con JSON valido, sin texto extra ni markdown:
{{
  "zodiac_western": "Signo occidental",
  "zodiac_chinese": "Signo chino",
  "zodiac_celtic": "Arbol celta",
  "zodiac_mayan": "{maya_sign}",
  "zodiac_egyptian": "Dios/Diosa egipcia",
  "ascending_sign": "Signo ascendente aproximado (hora desconocida)",
  "moon_sign": "Signo lunar",
  "ascendente": "Ascendente aproximado (hora no disponible) (2-3 lineas)",
  "descendente": "Descendente aproximado (2-3 lineas)",
  "medio_cielo": "Medio Cielo aproximado (2-3 lineas)",
  "fondo_cielo": "Fondo del Cielo aproximado (2-3 lineas)",
  "planetary_positions": {{
    "Sol": "Grado y signo",
    "Luna": "Signo (hora desconocida, posicion aproximada)",
    "Mercurio": "Grado y signo",
    "Venus": "Grado y signo",
    "Marte": "Grado y signo",
    "Jupiter": "Grado y signo",
    "Saturno": "Grado y signo"
  }},
  "afinidad_polaridad": "Descripcion afinidad polaridad (2-3 lineas)",
  "afinidad_amistad": "Descripcion afinidad amistad (2-3 lineas)",
  "afinidad_fisica": "Descripcion afinidad fisica (2-3 lineas)",
  "afinidad_intelectual": "Descripcion afinidad intelectual (2-3 lineas)",
  "interpretation": "Analisis principal 10-12 lineas",
  "horoscopo": {{
    "amor": "Lectura amor esta semana (3-4 lineas)",
    "trabajo": "Lectura trabajo esta semana (3-4 lineas)",
    "dinero": "Lectura dinero esta semana (3-4 lineas)",
    "salud": "Lectura salud esta semana (3-4 lineas)",
    "dia_suerte": "Martes",
    "color_suerte": "Azul",
    "numero_suerte": "3"
  }}{preguntas_str and """,
  "tarot_readings": [
    {{
      "pregunta": "pregunta 1 exacta",
      "card": "Nombre carta EXACTO de la biblioteca oficial",
      "numero_carta": 0,
      "answer": "Si o No",
      "interpretation": "Interpretacion 3-4 lineas basada en simbolismo egipcio"
    }}
  ]""" or ""}
}}

REGLAS OBLIGATORIAS:
- zodiac_mayan DEBE ser exactamente: {maya_sign}
- Las cartas de tarot_readings DEBEN ser nombres EXACTOS de la BIBLIOTECA OFICIAL listada arriba
- Responde SOLO con JSON, sin markdown, sin texto antes ni despues"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                messages=[{"role": "user", "content": prompt}],
            )

            raw_text = _extract_json(response.content[0].text)
            if not raw_text:
                raise ValueError("Claude devolvio vacio")

            result = _strip_accents(json.loads(raw_text))

            # BUG4: forzar signo maya correcto
            result["zodiac_mayan"] = _strip_accents(maya_sign)

            # BUG5: validar cartas si hay tirada
            if questions and "tarot_readings" in result:
                es_valida, errores = validar_tirada(result["tarot_readings"])
                if not es_valida:
                    logger.warning(f"[Tarot] Cartas invalidas: {errores}. Regenerando con fallback.")
                    result["tarot_readings"] = _tarot_fallback(questions)

            logger.info(f"OK Carta natal simple para {birth_date}")
            return result

        except Exception as e:
            logger.error(f"Error generando carta natal simple: {e}", exc_info=True)
            return None


# ------------------------------------------------------------------
# Fallback de tarot: si Claude devuelve cartas invalidas, usa cartas
# reales del archivo en posiciones fijas y genera interpretaciones neutrales.
# ------------------------------------------------------------------

def _tarot_fallback(questions: list) -> list:
    """
    Genera una tirada con cartas reales de la biblioteca oficial.
    Se usa cuando Claude devuelve cartas que no existen en el archivo.
    """
    try:
        biblioteca = cargar_biblioteca()
        cartas_ordenadas = sorted(biblioteca.values(), key=lambda c: c["numero"])
        # Usamos 5 cartas distribuidas uniformemente
        indices = [0, 15, 30, 45, 60]
        tirada = []
        for i, pregunta in enumerate(questions[:5]):
            carta = cartas_ordenadas[indices[i] % len(cartas_ordenadas)]
            tirada.append({
                "pregunta": pregunta,
                "card": carta["nombre"],
                "numero_carta": carta["numero"],
                "answer": "Si" if i % 2 == 0 else "No",
                "interpretation": carta["significado"][:200] + "..."
                if len(carta["significado"]) > 200
                else carta["significado"],
            })
        return tirada
    except Exception as e:
        logger.error(f"Error en fallback tarot: {e}")
        return []
