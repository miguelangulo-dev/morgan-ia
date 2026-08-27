"""
conversation_flow v9 - Fix link expirado + regeneracion + diseño limpio
- Si link expiro, genera nuevo PaymentLink automaticamente
- Usa pdf_generator_LIMPIO_v9
- Ya no manda Escribe hola fantasma en GENERATING
"""

import logging
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import ConversationState, NatalChart
from utils_whatsapp import WhatsAppClient
from agentes_claude_astro import AstroAgent
from pdf_generator_LIMPIO_v9 import build_natal_chart_pdf
from payment import create_payment_link, regenerate_payment_link_for_chart

logger = logging.getLogger(__name__)
wa = WhatsAppClient()
astro = AstroAgent()
PRICE_MXN = 49

async def get_or_create_state(db: AsyncSession, phone: str) -> ConversationState:
    result = await db.execute(select(ConversationState).where(ConversationState.phone_number == phone))
    state = result.scalar_one_or_none()
    if not state:
        state = ConversationState(phone_number=phone, current_step="MENU", collected_data={})
        db.add(state); await db.commit(); await db.refresh(state)
    return state

async def save_state(db: AsyncSession, state: ConversationState, step: str = None, data_update: dict = None):
    if step: state.current_step = step
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
    data = state.collected_data or {}

    # FIX GENERATING - no spamear Escribe hola
    if step == "GENERATING":
        if data.get("payment_link"):
            await wa.send_text(phone, f"Tu destino esta sellado, {data.get('full_name','').split()[0]}.\n\nTu link sigue activo (NO expira):\n{data.get('payment_link')}")
            await wa.send_buttons(phone, "Deseas continuar?", buttons=[{"id": "reenviar_link", "title": "Ya pague / Reenviar"}, {"id": "cancelar_compra", "title": "Cancelar"}])
            await save_state(db, state, step="AWAITING_PAYMENT")
            return
        else:
            logger.info(f"Ignorando mensaje en GENERATING para {phone}")
            return

    if step == "AWAITING_PAYMENT":
        if data.get("payment_link"):
            if lower in ["hola","ola","hey","pagar","reenviar","link","ya pague","ya pagué","pago"]:
                # Si el link es de tipo checkout y pudo expirar, regeneramos uno nuevo persistente
                try:
                    # Regenera link persistente siempre al reenviar para evitar Todo listo
                    chart_id = data.get("chart_id")
                    if chart_id:
                        new_link = await regenerate_payment_link_for_chart(chart_id, data.get('full_name',''), PRICE_MXN)
                        await save_state(db, state, data_update={"payment_link": new_link, "payment_url": new_link})
                        await wa.send_text(phone, f"Tu lectura sigue sellada, ${PRICE_MXN} MXN.\n\nTe genere un nuevo link que NO expira:\n{new_link}\n\nEn cuanto pagues te mando el PDF limpio de 6 hojas.")
                    else:
                        await wa.send_text(phone, f"Tu lectura sigue sellada, ${PRICE_MXN} MXN.\nTu link:\n{data.get('payment_link')}")
                    await wa.send_buttons(phone, "Que deseas hacer?", buttons=[{"id": "reenviar_link", "title": "Reenviar link de pago"}, {"id": "cancelar_compra", "title": "Cancelar lectura"}])
                except Exception as e:
                    logger.error(f"Error regenerando link: {e}")
                    await wa.send_text(phone, f"Link anterior: {data.get('payment_link')}")
                return

    if step == "COMPLETED":
        if lower in ["hola","ola","hey","otra","nueva"]:
            await save_state(db, state, step="MENU", data_update={})
            await handle_incoming_text(db, phone, "hola")
            return

    if step == "MENU":
        await wa.send_text(phone, "No es casualidad que llegaras aqui... El poder de las runas celtas nos une esta noche.\nEl destino ya esta escrito en las estrellas, solo hay que leerlo.\n\nSoy Morgania, guardiana de los velos del tiempo y el destino.")
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
        mapping = {"genero_m": "Masculino", "genero_f": "Femenino", "genero_x": "Prefiero no decir"}
        gender = mapping.get(text_clean, text_clean) if text_clean in mapping else text_clean
        await save_state(db, state, step="AWAITING_Q1", data_update={"birth_gender": gender})
        await wa.send_text(phone, "Perfecto. Ahora viene la parte sagrada...\n\nPiensa bien. Puedes hacerme 5 preguntas al destino, y te respondere con un Si/No, revelandote la carta del tarot que salio y su simbologia en relacion a tu pregunta.\n\nPregunta 1 de 5: Cual es tu primera pregunta?")
        return

    if step in ["AWAITING_Q1","AWAITING_Q2","AWAITING_Q3","AWAITING_Q4","AWAITING_Q5"]:
        q_num = int(step[-1])
        if len(text_clean) < 5:
            await wa.send_text(phone, f"Formulala un poco mas completa. Pregunta {q_num}?")
            return
        if q_num < 5:
            await save_state(db, state, step=f"AWAITING_Q{q_num+1}", data_update={f"q{q_num}": text_clean})
            msgs = ["Anotada en las runas...\n\nPregunta 2 de 5:", "Pregunta 3 de 5:", "Pregunta 4 de 5:", "Ultima... Pregunta 5 de 5:"]
            await wa.send_text(phone, msgs[q_num-1])
        else:
            await save_state(db, state, step="GENERATING", data_update={"q5": text_clean})
            await wa.send_text(phone, "Gracias. Sello tus 5 preguntas en el circulo de proteccion.\n\nVoy a generar tu carta astral completa con el nuevo diseño limpio de 6 hojas... dame un momento, esto toma magia.")
            await _generate_and_prepare_payment(db, state, phone)
        return

    await wa.send_text(phone, "Escribe 'hola' para abrir tu destino con Morgania.")
    await save_state(db, state, step="MENU")

async def handle_button_click(db: AsyncSession, phone: str, button_id: str):
    if button_id == "cancelar_compra":
        result = await db.execute(select(ConversationState).where(ConversationState.phone_number == phone))
        state = result.scalar_one_or_none()
        if state:
            await save_state(db, state, step="MENU", data_update={})
        await wa.send_text(phone, "Lectura cancelada sin costo. Escribe 'hola' para volver.")
        return

    if button_id == "reenviar_link":
        result = await db.execute(select(ConversationState).where(ConversationState.phone_number == phone))
        state = result.scalar_one_or_none()
        if state and state.collected_data.get("chart_id"):
            try:
                new_link = await regenerate_payment_link_for_chart(state.collected_data.get("chart_id"), state.collected_data.get("full_name",""), PRICE_MXN)
                await save_state(db, state, data_update={"payment_link": new_link, "payment_url": new_link})
                await wa.send_text(phone, f"Aqui tienes tu nuevo link que NO expira:\n{new_link}\n\nPaga ${PRICE_MXN} MXN y te mando tu PDF limpio de 6 hojas.")
            except Exception as e:
                logger.error(f"Error reenviando: {e}")
                await wa.send_text(phone, f"Tu link anterior: {state.collected_data.get('payment_link')}\nSi dice Todo listo, escribe 'link' para generar uno nuevo que no expira.")
        else:
            await handle_incoming_text(db, phone, "link")
        return

    mapping = {"quiero_carta":"si","no_gracias":"no","genero_m":"Masculino","genero_f":"Femenino","genero_x":"Prefiero no decir"}
    await handle_incoming_text(db, phone, mapping.get(button_id, button_id))

async def handle_button_reply(db: AsyncSession, phone: str, button_id: str):
    return await handle_button_click(db, phone, button_id)

async def _generate_and_prepare_payment(db: AsyncSession, state: ConversationState, phone: str):
    data = state.collected_data or {}
    full_name = data.get("full_name")
    birth_date = data.get("birth_date")
    birth_time = data.get("birth_time")
    birth_place = data.get("birth_place")
    birth_gender = data.get("birth_gender")
    questions = [data.get(f"q{i}") for i in range(1,6) if data.get(f"q{i}")]
    
    try:
        if data.get("chart_id") and data.get("payment_link"):
            logger.info(f"Pago ya generado para {phone}, REGENERANDO link persistente")
            new_link = await regenerate_payment_link_for_chart(data.get("chart_id"), full_name, PRICE_MXN)
            await save_state(db, state, step="AWAITING_PAYMENT", data_update={"payment_link": new_link, "payment_url": new_link})
            await wa.send_text(phone, f"Tu destino ya estaba sellado, {full_name.split()[0] if full_name else ''}.\n\nTu NUEVO link que NO expira:\n{new_link}")
            await wa.send_buttons(phone, "Deseas continuar?", buttons=[{"id": "reenviar_link", "title": "Ya pague / Reenviar"}, {"id": "cancelar_compra", "title": "Cancelar"}])
            return

        reading = await astro.generate_natal_chart_complete(birth_date, birth_time, birth_location=birth_place, questions=questions, gender=birth_gender) if birth_time else await astro.generate_natal_chart_simple(birth_date, questions, birth_place, birth_gender)
        if not reading:
            raise ValueError("Claude vacio")
        reading["birth_place"] = birth_place or "No especificado"
        reading["birth_gender"] = birth_gender or "No especificado"

        pdf_path, cover_used = build_natal_chart_pdf(full_name, birth_date, birth_time, reading)
        
        chart = NatalChart(phone_number=phone, full_name=full_name, birth_date=birth_date, birth_time=birth_time, birth_place=birth_place, gender=birth_gender,
            zodiac_western=reading.get("zodiac_western"), zodiac_chinese=reading.get("zodiac_chinese"), zodiac_celtic=reading.get("zodiac_celtic"),
            zodiac_mayan=reading.get("zodiac_mayan"), zodiac_egyptian=reading.get("zodiac_egyptian"),
            interpretation_json=reading, cover_used=cover_used, pdf_path=pdf_path, pdf_ready=True, payment_status="pending")
        db.add(chart); await db.commit(); await db.refresh(chart)
        
        payment_url = await create_payment_link(amount_mxn=PRICE_MXN, reference_id=chart.id, description=f"Carta Astral 6 Hojas + 5 Tarot - {full_name}")
        await save_state(db, state, step="AWAITING_PAYMENT", data_update={"chart_id": chart.id, "payment_link": payment_url, "payment_url": payment_url, "payment_sent_at": datetime.utcnow().isoformat()})
        
        await wa.send_text(phone, f"Tu destino esta sellado, {full_name.split()[0]}.\n\nEres {reading.get('zodiac_western')} en occidente, y vi tus 5 zodiacos alineados.\n\nTus 5 respuestas del tarot ya estan canalizadas en el PDF LIMPIO de 6 hojas con letra grande legible.\n\nPara romper el sello y recibir tu PDF completo, paga ${PRICE_MXN} MXN aqui (link que NO expira):\n\n{payment_url}\n\nEn cuanto se confirme, te lo mando de inmediato.")
        await wa.send_buttons(phone, "Deseas continuar?", buttons=[{"id": "reenviar_link", "title": "Ya pague / Reenviar"}, {"id": "cancelar_compra", "title": "Cancelar"}])
    except Exception as e:
        logger.error(f"Error generando: {str(e)}", exc_info=True)
        await wa.send_text(phone, "Las runas se nublaron... Intenta de nuevo escribiendo 'hola'.")
        await save_state(db, state, step="MENU")

async def deliver_paid_chart(db: AsyncSession, chart: NatalChart):
    chart.payment_status = "paid"; await db.commit()
    await wa.send_document(chart.phone_number, chart.pdf_path, caption=f"Aqui esta tu destino completo, {chart.full_name.split()[0]}. Nuevo diseño limpio de 6 hojas. Gracias por confiar en Morgania.")
    chart.delivered = True; await db.commit()
    result = await db.execute(select(ConversationState).where(ConversationState.phone_number == chart.phone_number))
    state = result.scalar_one_or_none()
    if state: await save_state(db, state, step="COMPLETED")

async def _ask_full_name(phone: str):
    await wa.send_text(phone, "Perfecto. Para abrir tu destino necesito 3 datos:\n\n1. Nombre completo\n2. Fecha de nacimiento\n3. Hora de nacimiento (si la sabes)\n\nEmpecemos: cual es tu nombre completo?")

def _is_affirmative(text: str) -> bool:
    return text.lower().strip() in {"si","si!","yes","claro","quiero","ok","va","abrir","abrir mi destino"}
def _is_unknown(text: str) -> bool:
    t = text.lower(); return "no s" in t or "no se" in t or "desconoc" in t
def _parse_date(text: str):
    for sep in ["/","-"]:
        parts = text.strip().split(sep)
        if len(parts)==3:
            try:
                day,month,year=parts; from datetime import datetime; d=datetime(int(year),int(month),int(day)); return d.strftime("%Y-%m-%d")
            except: continue
    return None
def _parse_time(text: str):
    text=text.strip()
    try:
        from datetime import datetime; t=datetime.strptime(text,"%H:%M"); return t.strftime("%H:%M")
    except: return None
