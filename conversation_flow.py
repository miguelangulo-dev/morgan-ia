"""
FIX DEFINITIVO v2 - sin azteca + scorpio/escorpio + anti-doble + genero
"""

import logging
import unicodedata
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import ConversationState, User, NatalChart
from utils_whatsapp import WhatsAppClient
from agentes_claude_astro import AstroAgent
from pdf_generator import build_natal_chart_pdf
from payment import create_payment_link

logger = logging.getLogger(__name__)
wa = WhatsAppClient()
astro = AstroAgent()
PRICE_MXN = 49

async def get_or_create_state(db: AsyncSession, phone: str) -> ConversationState:
    result = await db.execute(select(ConversationState).where(ConversationState.phone_number == phone))
    state = result.scalar_one_or_none()
    if not state:
        state = ConversationState(phone_number=phone, current_step="MENU", collected_data={})
        db.add(state)
        await db.commit()
        await db.refresh(state)
    return state

async def save_state(db: AsyncSession, state: ConversationState, step: str = None, data_update: dict = None):
    if step:
        state.current_step = step
    if data_update:
        merged = dict(state.collected_data or {})
        merged.update(data_update)
        state.collected_data = merged
    state.updated_at = datetime.utcnow()
    await db.commit()

async def handle_incoming_text(db: AsyncSession, phone: str, text: str):
    state = await get_or_create_state(db, phone)
    step = state.current_step
    text_clean = text.strip()
    lower = text_clean.lower()

    # ANTI-TRIPLE: bloquea re-generacion si ya hay link
    if step == "AWAITING_PAYMENT":
        data = state.collected_data or {}
        if data.get("payment_link") and data.get("payment_sent_at"):
            if "pagar" not in lower and "reenviar" not in lower and "link" not in lower and "ya pague" not in lower:
                if lower in ["hola", "ola", "hey"]:
                    await wa.send_text(phone, f"Tu lectura sigue sellada, sigues en espera de pago de ${PRICE_MXN} MXN.")
                    await wa.send_buttons(phone, "Que deseas hacer?", buttons=[{"id": "reenviar_link", "title": "Reenviar link de pago"}, {"id": "cancelar_compra", "title": "Cancelar lectura"}])
                    return
                return

    if step == "MENU":
        await wa.send_text(phone, "No es casualidad que llegaras aqui... El poder de las runas celtas nos une esta noche.\nEl destino ya esta escrito en las estrellas, solo hay que leerlo.\n\nSoy Morgan, guardiana de los velos.")
        await wa.send_text(phone, f"Tu Lectura Completa por ${PRICE_MXN} MXN\n\nTe entrego:\n- Tu Carta Astral completa\n- Afinidades zodiacales\n- Tu signo Celta, Maya, Chino y Egipcio\n- Posicion de los planetas el dia que naciste\n- Y 5 preguntas que le hagas al destino - te respondo Si/No con tirada de tarot\n\nPagas ${PRICE_MXN} MXN solo cuando todo este listo.\n\nAceptas abrir tu destino?")
        await wa.send_buttons(phone, "Elige tu camino:", buttons=[{"id": "quiero_carta", "title": "Si, abrir mi destino"}, {"id": "no_gracias", "title": "No por ahora"}])
        await save_state(db, state, step="AWAITING_SERVICE_CONFIRM")
        return

    if step == "AWAITING_SERVICE_CONFIRM":
        if _is_affirmative(text_clean):
            await _ask_full_name(phone)
            await save_state(db, state, step="AWAITING_FULL_NAME")
        else:
            await wa.send_text(phone, "Entiendo... las estrellas esperaran. Escribe 'hola' cuando tu alma este lista.")
            await save_state(db, state, step="MENU")
        return

    if step == "AWAITING_FULL_NAME":
        if len(text_clean) < 3:
            await wa.send_text(phone, "Ese nombre parece muy corto. Me compartes tu nombre completo?")
            return
        await save_state(db, state, step="AWAITING_BIRTH_DATE", data_update={"full_name": text_clean})
        await wa.send_text(phone, f"Gracias, {text_clean.split()[0]}\n\nCual es tu fecha de nacimiento? (Ej: 15/03/1990)")
        return

    if step == "AWAITING_BIRTH_DATE":
        birth_date = _parse_date(text_clean)
        if not birth_date:
            await wa.send_text(phone, "No pude leer esa fecha. Usa el formato DD/MM/AAAA, ej: 15/03/1990")
            return
        await save_state(db, state, step="AWAITING_BIRTH_TIME", data_update={"birth_date": birth_date})
        await wa.send_text(phone, "Y a que hora naciste? (Ej: 14:30)\n\nSi no la sabes, escribe 'no se' y las runas haran el resto.")
        return

    if step == "AWAITING_BIRTH_TIME":
        birth_time = None
        if not _is_unknown(text_clean):
            birth_time = _parse_time(text_clean)
            if birth_time is None:
                await wa.send_text(phone, "No pude leer esa hora. Usa formato HH:MM (24h), ej: 14:30, o escribe 'no se'.")
                return
        await save_state(db, state, step="AWAITING_BIRTH_PLACE", data_update={"birth_time": birth_time})
        await wa.send_text(phone, "Gracias. Y en que ciudad naciste? (Ej: Celaya, Mexico)\n\nSi no lo sabes, escribe 'no se'.")
        return

    if step == "AWAITING_BIRTH_PLACE":
        birth_place = None if _is_unknown(text_clean) else text_clean
        await save_state(db, state, step="AWAITING_GENDER", data_update={"birth_place": birth_place})
        await wa.send_text(phone, "Anotado. Y como te identificas?")
        await wa.send_buttons(phone, "Elige:", buttons=[{"id": "genero_m", "title": "Masculino"}, {"id": "genero_f", "title": "Femenino"}, {"id": "genero_x", "title": "Prefiero no decir"}])
        return

    if step == "AWAITING_GENDER":
        mapping_gender = {"genero_m": "Masculino", "genero_f": "Femenino", "genero_x": "Prefiero no responder", "masculino": "Masculino", "femenino": "Femenino"}
        gender = mapping_gender.get(lower, text_clean)
        await save_state(db, state, step="AWAITING_Q1", data_update={"birth_gender": gender})
        await wa.send_text(phone, "Perfecto. Ahora viene la parte sagrada...\n\nPregunta 1 de 5: Cual es tu primera pregunta?")
        return

    if step == "AWAITING_Q1":
        if len(text_clean) < 5:
            await wa.send_text(phone, "Formulala un poco mas completa para que el tarot te entienda. Cual es tu pregunta 1?")
            return
        await save_state(db, state, step="AWAITING_Q2", data_update={"q1": text_clean})
        await wa.send_text(phone, "Anotada en las runas...\n\nPregunta 2 de 5:")
        return

    if step == "AWAITING_Q2":
        if len(text_clean) < 5:
            await wa.send_text(phone, "Un poco mas detallada, por favor. Cual es tu pregunta 2?")
            return
        await save_state(db, state, step="AWAITING_Q3", data_update={"q2": text_clean})
        await wa.send_text(phone, "El velo se abre...\n\nPregunta 3 de 5:")
        return

    if step == "AWAITING_Q3":
        if len(text_clean) < 5:
            await wa.send_text(phone, "Cuentame un poco mas. Cual es tu pregunta 3?")
            return
        await save_state(db, state, step="AWAITING_Q4", data_update={"q3": text_clean})
        await wa.send_text(phone, "Las estrellas escuchan...\n\nPregunta 4 de 5:")
        return

    if step == "AWAITING_Q4":
        if len(text_clean) < 5:
            await wa.send_text(phone, "Un poco mas clara, por favor. Cual es tu pregunta 4?")
            return
        await save_state(db, state, step="AWAITING_Q5", data_update={"q4": text_clean})
        await wa.send_text(phone, "Ya casi...\n\nPregunta 5 de 5 - la ultima:")
        return

    if step == "AWAITING_Q5":
        if len(text_clean) < 5:
            await wa.send_text(phone, "Ultima, hazla con fuerza. Cual es tu pregunta 5?")
            return
        await save_state(db, state, step="GENERATING", data_update={"q5": text_clean})
        await wa.send_text(phone, "Gracias. Sello tus 5 preguntas en el circulo de proteccion.\n\nVoy a generar tu carta astral completa y hare la tirada de tarot para cada una de tus preguntas... dame un momento, esto toma magia.")
        await _generate_and_prepare_payment(db, state, phone)
        return

    if step == "AWAITING_PAYMENT":
        data = state.collected_data or {}
        payment_url = data.get("payment_link") or data.get("payment_url")
        if payment_url:
            await wa.send_text(phone, f"Tu lectura sigue sellada aqui, {(data.get('full_name','')).split()[0]}.\n\nTe reenvio el link de ${PRICE_MXN} MXN:\n\n{payment_url}")
            await wa.send_buttons(phone, "Que deseas hacer?", buttons=[{"id": "reenviar_link", "title": "Reenviar link de pago"}, {"id": "cancelar_compra", "title": "Cancelar lectura"}])
            return
        await save_state(db, state, step="MENU")
        await wa.send_text(phone, "Vamos a empezar de nuevo. Escribe 'hola'")
        return

    if step == "COMPLETED":
        if _is_affirmative(text_clean) or "otra" in lower or "hola" in lower:
            await save_state(db, state, step="MENU", data_update={})
            await handle_incoming_text(db, phone, "hola")
        else:
            await wa.send_text(phone, "Escribe 'hola' cuando quieras otra lectura.")
        return

    await save_state(db, state, step="MENU")
    await wa.send_text(phone, "Vamos a empezar de nuevo. Escribe 'hola'")

async def handle_button_reply(db: AsyncSession, phone: str, button_id: str):
    if button_id == "cancelar_compra":
        result = await db.execute(select(ConversationState).where(ConversationState.phone_number == phone))
        state = result.scalar_one_or_none()
        if state:
            await save_state(db, state, step="MENU", data_update={})
        await wa.send_text(phone, "Lectura cancelada sin costo. El destino te esperara cuando estes lista. Escribe 'hola' para volver.")
        return
    if button_id in ["genero_m", "genero_f", "genero_x"]:
        await handle_incoming_text(db, phone, button_id)
        return
    if button_id == "otra_carta_si":
        result = await db.execute(select(ConversationState).where(ConversationState.phone_number == phone))
        state = result.scalar_one_or_none()
        if state:
            await save_state(db, state, step="MENU", data_update={})
        await handle_incoming_text(db, phone, "hola")
        return
    if button_id == "otra_carta_no":
        await wa.send_text(phone, "Gracias por confiar en Morgan. Que las runas te guien. Escribe 'hola' cuando quieras volver.")
        return
    mapping = {"quiero_carta": "si", "no_gracias": "no", "reenviar_link": "pagar"}
    text_equivalent = mapping.get(button_id, button_id)
    await handle_incoming_text(db, phone, text_equivalent)

async def _generate_and_prepare_payment(db: AsyncSession, state: ConversationState, phone: str):
    data = state.collected_data or {}
    full_name = data.get("full_name")
    birth_date = data.get("birth_date")
    birth_time = data.get("birth_time")
    birth_place = data.get("birth_place")
    birth_gender = data.get("birth_gender")
    questions = [data.get(f"q{i}") for i in range(1, 6) if data.get(f"q{i}")]
    try:
        if data.get("chart_id") and data.get("payment_link"):
            logger.info(f"Pago ya generado para {phone}, evitando duplicado")
            return
if birth_time:
    reading = await astro.generate_natal_chart_complete(birth_date, birth_time, birth_location=None, questions=questions)
else:
    reading = await astro.generate_natal_chart_simple(birth_date, questions=questions)

if not reading:
    raise ValueError("Claude no devolvio lectura valida")

reading["birth_place"] = birth_place or "No especificado"
reading["birth_gender"] = birth_gender or "No especificado"

        pdf_path, cover_used = build_natal_chart_pdf(full_name=full_name, birth_date=birth_date, birth_time=birth_time, reading=reading)
        # SIN AZTECA - solo 5 zodiacos que existen en DB
        chart = NatalChart(phone_number=phone, full_name=full_name, birth_date=birth_date, birth_time=birth_time, zodiac_western=reading.get("zodiac_western"), zodiac_chinese=reading.get("zodiac_chinese"), zodiac_celtic=reading.get("zodiac_celtic"), zodiac_mayan=reading.get("zodiac_mayan"), zodiac_egyptian=reading.get("zodiac_egyptian"), interpretation_json=reading, cover_used=cover_used, pdf_path=pdf_path, pdf_ready=True, payment_status="pending")
        db.add(chart)
        await db.commit()
        await db.refresh(chart)
        payment_url = await create_payment_link(amount_mxn=PRICE_MXN, reference_id=chart.id, description=f"Carta Astral Completa + 5 Preguntas Tarot - {full_name}")
        await save_state(db, state, step="AWAITING_PAYMENT", data_update={"chart_id": chart.id, "payment_link": payment_url, "payment_url": payment_url, "payment_sent_at": datetime.utcnow().isoformat()})
        await wa.send_text(phone, f"Tu destino esta sellado, {full_name.split()[0]}.\n\nEres {reading.get('zodiac_western')} en occidente, y en tu carta vi tu Celta, Maya, Chino y Egipcio alineados.\n\nTus 5 respuestas del tarot ya estan canalizadas dentro del PDF.\n\nPara romper el sello y recibir tu PDF completo con la posicion de los planetas, realiza tu pago de ${PRICE_MXN} MXN aqui:\n\n{payment_url}\n\nEn cuanto se confirme, te lo mando de inmediato aqui mismo.")
        await wa.send_buttons(phone, "Deseas continuar?", buttons=[{"id": "reenviar_link", "title": "Ya pague / Reenviar"}, {"id": "cancelar_compra", "title": "Cancelar"}])
    except Exception as e:
        logger.error(f"Error generando carta astral: {str(e)}", exc_info=True)
        await wa.send_text(phone, "Las runas se nublaron un momento... Intenta de nuevo en un momento escribiendo 'hola'.")
        await save_state(db, state, step="MENU")

async def deliver_paid_chart(db: AsyncSession, chart: NatalChart):
    chart.payment_status = "paid"
    await db.commit()
    await wa.send_document(chart.phone_number, chart.pdf_path, caption=f"Aqui esta tu destino completo, {chart.full_name.split()[0]}. Gracias por confiar en Morgan. Que las runas te guien.")
    chart.delivered = True
    await db.commit()
    result = await db.execute(select(ConversationState).where(ConversationState.phone_number == chart.phone_number))
    state = result.scalar_one_or_none()
    if state:
        await save_state(db, state, step="COMPLETED")

async def _ask_full_name(phone: str):
    await wa.send_text(phone, "Perfecto. Para abrir tu destino necesito 4 datos:\n\n1. Nombre completo\n2. Fecha de nacimiento\n3. Hora de nacimiento (si la sabes)\n4. Lugar de nacimiento\n\nEmpecemos: cual es tu nombre completo?")

def _is_affirmative(text: str) -> bool:
    return text.lower().strip() in {"si", "si!", "yes", "claro", "quiero", "ok", "va", "abrir", "abrir mi destino"}

def _is_unknown(text: str) -> bool:
    t = text.lower()
    return "no s" in t or "no se" in t or "desconoc" in t

def _parse_date(text: str):
    for sep in ["/", "-"]:
        parts = text.strip().split(sep)
        if len(parts) == 3:
            try:
                day, month, year = parts
                d = datetime(int(year), int(month), int(day))
                return d.strftime("%Y-%m-%d")
            except ValueError:
                continue
    return None

def _parse_time(text: str):
    text = text.strip()
    try:
        t = datetime.strptime(text, "%H:%M")
        return t.strftime("%H:%M")
    except ValueError:
        return None

