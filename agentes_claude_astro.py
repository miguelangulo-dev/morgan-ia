import anthropic
import os
import json
import logging

logger = logging.getLogger(__name__)

CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

class AstroAgent:
    """Agente Claude para lectura astrológica"""
    
    def __init__(self):
        self.client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        self.model = "claude-sonnet-4-20250514"  
    
    # ========================================================================
    # CARTAS NATALES
    # ========================================================================
    
    async def generate_natal_chart_simple(self, birth_date: str) -> dict:
        """
        Genera carta natal simplificada (solo fecha)
        birth_date: "1990-03-15"
        """
        
        prompt = f"""Eres un experto en astrología. Analiza la siguiente fecha de nacimiento y genera una carta natal simplificada.

FECHA DE NACIMIENTO: {birth_date}

Proporciona en formato JSON:
{{
  "zodiac_western": "Signo occidental (ej: Aries)",
  "zodiac_chinese": "Signo chino (ej: Caballo)",
  "zodiac_celtic": "Signo celta (ej: Roble)",
  "zodiac_mayan": "Signo maya",
  "zodiac_egyptian": "Signo egipcio",
  "interpretation": "Párrafo de 3-4 líneas sobre las características principales"
}}

IMPORTANTE: Responde SOLO con el JSON, sin explicaciones adicionales."""
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            result_text = response.content[0].text
            result = json.loads(result_text)
            logger.info(f"✅ Carta natal simple generada para {birth_date}")
            return result
        
        except Exception as e:
            logger.error(f"❌ Error generando carta natal: {str(e)}")
            return None
    
    async def generate_natal_chart_complete(self, birth_date: str, birth_time: str, birth_location: str) -> dict:
        """
        Genera carta natal completa (fecha, hora y lugar)
        birth_date: "1990-03-15"
        birth_time: "14:30:00"
        birth_location: "México, Guanajuato"
        """
        
        prompt = f"""Eres un experto en astrología. Analiza los siguientes datos de nacimiento y genera una carta natal completa.

FECHA DE NACIMIENTO: {birth_date}
HORA DE NACIMIENTO: {birth_time}
LUGAR DE NACIMIENTO: {birth_location}

Considerando la hora y el lugar exacto, calcula los signos ascendentes y datos astrológicos precisos.

Proporciona en formato JSON:
{{
  "zodiac_western": "Signo occidental (ej: Aries)",
  "zodiac_chinese": "Signo chino (ej: Caballo)",
  "zodiac_celtic": "Signo celta (ej: Roble)",
  "zodiac_mayan": "Signo maya",
  "zodiac_egyptian": "Signo egipcio",
  "ascending_sign": "Signo ascendente (ej: Leo)",
  "moon_sign": "Signo lunar",
  "detailed_interpretation": "Párrafo de 40-45 líneas con análisis detallado incluyendo casas astrológicas"
}}

IMPORTANTE: Responde SOLO con el JSON, sin explicaciones adicionales."""
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1200,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            result_text = response.content[0].text
            result = json.loads(result_text)
            logger.info(f"✅ Carta natal completa generada para {birth_date}")
            return result
        
        except Exception as e:
            logger.error(f"❌ Error generando carta natal completa: {str(e)}")
            return None
    
    # ========================================================================
    # TIRADAS DE TAROT EGIPCIO
    # ========================================================================
    
    async def generate_tarot_reading(self, questions: list, tarot_pdf_context: str = "") -> dict:
        """
        Genera tirada de tarot egipcio con respuestas sí/no
        questions: ["¿Será un buen año?", "¿Encontraré amor?", ...]
        tarot_pdf_context: Contenido de los PDFs de tarot egipcio (opcional)
        """
        
        questions_str = "\n".join([f"{i+1}. {q}" for i, q in enumerate(questions)])
        
        prompt = f"""Eres un experto en tarot egipcio. Te proporcionaré {len(questions)} preguntas que requieren respuestas de sí o no.

PREGUNTAS:
{questions_str}

{"CONTEXTO DE INTERPRETACIÓN (Libro de Tarot Egipcio):" + tarot_pdf_context if tarot_pdf_context else ""}

Para cada pregunta:
1. Elige una carta egipcia apropiada
2. Da una respuesta clara (Sí / No)
3. Da el significado de la carta elegida y su simbología. Ej: Te ha salido Osiris, dios del inframundo, la respuesta es un NO, ya que esta carta representa el fin de los ciclos y el cierre de etapas...
4. Proporciona una interpretación basada en la carta

Responde en formato JSON:
{{
  "readings": [
    {{
      "question": "¿Será un buen año?",
      "card": "El Loto (carta XVIII)",
      "answer": "Sí",
      "interpretation": "La carta del Loto indica renovación y crecimiento. Este año traerá oportunidades de transformación personal..."
    }},
    ...
  ],
  "overall_message": "Mensaje general sobre todas las lecturas (2-3 líneas)"
}}

IMPORTANTE: 
- Responde SOLO con el JSON
- Las respuestas deben ser claras (Sí/No)
- Las interpretaciones deben basarse en simbolismo egipcio
- No añadas explicaciones fuera del JSON"""
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            result_text = response.content[0].text
            result = json.loads(result_text)
            logger.info(f"✅ Tirada de tarot generada para {len(questions)} preguntas")
            return result
        
        except Exception as e:
            logger.error(f"❌ Error generando tirada de tarot: {str(e)}")
            return None
    
    # ========================================================================
    # AFINIDAD ZODIACAL
    # ========================================================================
    
    async def generate_zodiac_affinity(self, user_zodiac: str, target_zodiac: str) -> dict:
        """
        Calcula afinidad entre dos signos zodiacales
        user_zodiac: "Aries"
        target_zodiac: "Leo"
        """
        
        prompt = f"""Eres un experto en astrología y compatibilidad zodiacal.

Analiza la afinidad entre estos dos signos:

SIGNO DEL USUARIO: {user_zodiac}
SIGNO OBJETIVO: {target_zodiac}

Considera: elementos astrológicos, polaridad, compatibilidad emocional, intelectual y sexual.

Responde en formato JSON:
{{
  "user_zodiac": "Aries",
  "target_zodiac": "Leo",
  "affinity_percentage": 85,
  "affinity_level": "Muy Alta",
  "compatibility": {{
    "emotional": 8,
    "intellectual": 8,
    "sexual": 9,
    "friendship": 9
  }},
  "interpretation": "Párrafo de 4-5 líneas explicando por qué estos signos tienen buena compatibilidad",
  "advice": "Consejo específico para esta pareja astrológica"
}}

IMPORTANTE: 
- Responde SOLO con el JSON
- affinity_percentage: 0-100
- Los valores de compatibility: 0-10"""
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1500,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            result_text = response.content[0].text
            result = json.loads(result_text)
            logger.info(f"✅ Afinidad zodiacal calculada: {user_zodiac} + {target_zodiac}")
            return result
        
        except Exception as e:
            logger.error(f"❌ Error calculando afinidad: {str(e)}")
            return None
