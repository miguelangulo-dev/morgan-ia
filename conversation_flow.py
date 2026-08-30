
"""
Flujo FINAL COMPLETO - REVISION 3, 4, 5
- REVISION 3: Multiidioma ES/EN (_detect_lang, MSG, lang en astro)
- REVISION 4: Botón términos antes del pago (AWAITING_TERMS)
- REVISION 5: Clave maestra + reporte ventas WhatsApp
"""

import os
import logging
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

ADMIN_KEY = os.getenv("MORGAN_ADMIN_KEY", "634r50fw4R!977$5283266")

def _detect_lang(text: str) -> str:
    t = f" {text.lower()} "
    en = sum(w in t for w in [" the "," what "," when "," yes "," no "," my "," born "," love "," will "," should "])
    es = sum(w in t for w in [" el "," la "," que "," cuando "," si "," no "," mi "," naci "," amor "," debo "])
    return "en" if en > es else "es"

MSG = {
    "es": {
        "menu_intro1": "No es casualidad que llegaras aquí... El poder de las runas celtas nos une esta noche.\nEl destino ya está escrito en las estrellas, solo hay que leerlo.\n\nSoy Morgan, guardiana de los velos.",
        "menu_intro2": f"Tu Lectura Completa por ${PRICE_MXN} MXN\n\nTe entrego:\n- Tu Carta Astral completa\n- Afinidades zodiacales\n- Tu signo Celta, Maya, Chino y Egipcio\n- Posición de los planetas el día que naciste\n- Y 5 preguntas que le hagas al destino - te respondo Sí/No con tirada de tarot\n\nPagas ${PRICE_MXN} MXN solo cuando todo esté listo.\n\n¿Aceptas abrir tu destino?",
        "choose_path": "Elige tu camino:",
        "btn_yes": "Sí, abrir mi destino",
        "btn_no": "No por ahora",
        "service_no": "Entiendo... las estrellas esperarán. Escribe 'hola' cuando tu alma esté lista.",
        "ask_name_intro": "Perfecto. Para abrir tu destino necesito 3 datos:\n\n1. Nombre completo\n2. Fecha de nacimiento\n3. Hora de nacimiento (si la sabes)\n\nEmpecemos: ¿cuál es tu nombre completo?",
        "name_short": "Ese nombre parece muy corto. ¿Me compartes tu nombre completo?",
        "thanks_name": "Gracias, {name}\n\n¿Cuál es tu fecha de nacimiento? (Ej: 15/03/1990)",
        "date_invalid": "No pude leer esa fecha. Usa el formato DD/MM/AAAA, ej: 15/03/1990",
        "ask_time": "¿Y a qué hora naciste? (Ej: 14:30)\n\nSi no la sabes, escribe 'no sé' y las runas harán el resto.",
        "time_invalid": "No pude leer esa hora. Usa formato HH:MM (24h), ej: 14:30, o escribe 'no sé'.",
        "q_intro": "Perfecto. Ahora viene la parte sagrada...\n\nPiensa bien. Puedes hacerme 5 preguntas al destino, y te responderé con un Sí/No, revelándote la carta del tarot que salió y su simbología.\n\nPregunta 1 de 5: ¿Cuál es tu primera pregunta?",
        "q1_short": "Formúlala un poco más completa. ¿Cuál es tu pregunta 1?",
        "q2": "Anotada en las runas...\n\nPregunta 2 de 5:",
        "q2_short": "Un poco más detallada. ¿Cuál es tu pregunta 2?",
        "q3": "El velo se abre...\n\nPregunta 3 de 5:",
        "q3_short": "Cuéntame un poco más. ¿Cuál es tu pregunta 3?",
        "q4": "Las estrellas escuchan...\n\nPregunta 4 de 5:",
        "q4_short": "Un poco más clara. ¿Cuál es tu pregunta 4?",
        "q5": "Último sello...\n\nPregunta 5 de 5:",
        "q5_short": "Un poco más clara. ¿Cuál es tu pregunta 5?",
        "terms_intro": "Antes de sellar tu destino necesito tu confirmación.",
        "terms_btn_text": "He leído y acepto los términos y condiciones de www.sincron-ia.com.mx",
        "terms_btn_yes": "He leído y acepto",
        "terms_thanks": "Gracias. Sello tus 5 preguntas en el círculo de protección. Generando tu lectura...",
        "terms_needed": "Necesito que aceptes los términos para continuar. Escribe 'hola' para reiniciar.",
        "generating": "Las runas están trabajando... sellando tu destino...",
        "sealed": "Tu destino está sellado, {name}.\n\nEres {zodiac} en occidente.\n\nTus 5 respuestas del tarot ya están canalizadas en el PDF.\n\nPara recibir tu PDF completo, paga ${price} MXN aquí (link que NO expira):\n\n{payment_url}",
        "continue": "¿Deseas continuar?",
        "btn_paid": "Ya pagué / Reenviar",
        "btn_cancel": "Cancelar",
        "error": "Las runas se nublaron un momento... Intenta de nuevo escribiendo 'hola'.",
    },
    "en": {
        "menu_intro1": "It's no coincidence you arrived here... The power of the Celtic runes unites us tonight.\nDestiny is already written in the stars.\n\nI'm Morgan, guardian of the veils.",
        "menu_intro2": f"Your Complete Reading for ${PRICE_MXN} MXN\n\nI give you:\n- Your complete Natal Chart\n- Zodiac affinities\n- Your Celtic, Mayan, Chinese and Egyptian signs\n- Position of the planets on the day you were born\n- And 5 questions you ask destiny - I answer Yes/No with tarot\n\nYou pay ${PRICE_MXN} MXN only when everything is ready.\n\nDo you accept to open your destiny?",
        "choose_path": "Choose your path:",
        "btn_yes": "Yes, open my destiny",
        "btn_no": "Not now",
        "service_no": "I understand... the stars will wait. Type 'hello' when your soul is ready.",
        "ask_name_intro": "Perfect. To open your destiny I need 3 data:\n\n1. Full name\n2. Birth date\n3. Birth time (if you know it)\n\nLet's start: what is your full name?",
        "name_short": "That name seems too short. Can you share your full name?",
        "thanks_name": "Thank you, {name}\n\nWhat is your birth date? (Ex: 03/15/1990)",
        "date_invalid": "I couldn't read that date. Use DD/MM/YYYY, ex: 15/03/1990",
        "ask_time": "And at what time were you born? (Ex: 14:30)\n\nIf you don't know, type 'don't know'.",
        "time_invalid": "I couldn't read that time. Use HH:MM (24h), ex: 14:30, or type 'don't know'.",
        "q_intro": "Perfect. Now comes the sacred part...\n\nThink well. You can ask me 5 questions to destiny, and I will answer Yes/No, revealing the tarot card and its symbolism.\n\nQuestion 1 of 5: What is your first question?",
        "q1_short": "Make it a bit more complete. What is your question 1?",
        "q2": "Noted in the runes...\n\nQuestion 2 of 5:",
        "q2_short": "A bit more detailed. What is your question 2?",
        "q3": "The veil opens...\n\nQuestion 3 of 5:",
        "q3_short": "Tell me a bit more. What is your question 3?",
        "q4": "The stars are listening...\n\nQuestion 4 of 5:",
        "q4_short": "A bit clearer. What is your question 4?",
        "q5": "Last seal...\n\nQuestion 5 of 5:",
        "q5_short": "A bit clearer. What is your question 5?",
        "terms_intro": "Before sealing your destiny I need your confirmation.",
        "terms_btn_text": "I have read and accept the terms and conditions of www.sincron-ia.com.mx",
        "terms_btn_yes": "I have read and accept",
        "terms_thanks": "Thank you. I seal your 5 questions in the protection circle. Generating your reading...",
        "terms_needed": "I need you to accept the terms to continue. Type 'hello' to restart.",
        "generating": "The runes are working... sealing your destiny...",
        "sealed": "Your destiny is sealed, {name}.\n\nYou are {zodiac} in the west.\n\nYour 5 tarot answers are already channeled inside the PDF.\n\nTo receive your complete PDF, pay ${price} MXN here (link never expires):\n\n{payment_url}",
        "continue": "Do you want to continue?",
        "btn_paid": "I paid / Resend",
        "btn_cancel": "Cancel",
        "error": "The runes clouded for a moment... Try again by typing 'hello'.",
    }
}

async def _build_admin_report(db: AsyncSession) -> str:
    from sqlalchemy import func
    from datetime import timedelta
    hoy = datetime.utcnow().date()
    total = (await db.execute(select(func.count()).select_from(NatalChart).where(NatalChart.payment_status == "paid"))).scalar() or 0
    gen = (await db.execute(select(NatalChart.gender, func.count()).where(NatalChart.payment_status == "paid").group_by(NatalChart.gender))).all()
    sig = (await db.execute(select(NatalChart.zodiac_western, func.count()).where(NatalChart.payment_status == "paid").group_by(NatalChart.zodiac_western))).all()
    hoy_n = (await db.execute(select(func.count()).select_from(NatalChart).where(NatalChart.payment_status == "paid", NatalChart.created_at >= datetime.combine(hoy, datetime.min.time())))).scalar() or 0
    def pct(n): return f"{(n*100//total) if total else 0}%"
    lines = [f"REPORTE MORGAN-IA", f"Ventas totales: {total}  (${total*49} MXN)", f"Ventas hoy: {hoy_n}", "", "Por genero:"]
    lines += [f"  {g or 'N/D'}: {c} ({pct(c)})" for g, c in gen]
    lines += ["", "Por signo:"]
    lines += [f"  {s or 'N/D'}: {c} ({pct(c)})" for s, c in sorted(sig, key=lambda x: -x[1])]
    return "\n".join(lines)

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
    data = state.collected_data or {}

    # FIX 5 - Clave maestra + reporte
    if text_clean == ADMIN_KEY:
        try:
            reporte = await _build_admin_report(db)
        except Exception as e:
            logger.error(f"Error reporte admin: {e}")
            reporte = "No pude generar el reporte."
        await wa.send_text(phone, reporte)
        return

    lang = data.get("lang") or _detect_lang(text_clean)
    if not data.get("lang"):
        await save_state(db, state, data_update={"lang": lang})
        data["lang"] = lang
    t = MSG[lang]

    if step == "MENU":
        await wa.send_text(phone, t["menu_intro1"])
        await wa.send_text(phone, t["menu_intro2"])
        await wa.send_buttons(phone, t["choose_path"], buttons=[{"id": "quiero_carta", "title": t["btn_yes"]}, {"id": "no_gracias", "title": t["btn_no"]}])
        await save_state(db, state, step="AWAITING_SERVICE_CONFIRM")
        return

    if step == "AWAITING_SERVICE_CONFIRM":
        if _is_affirmative(text_clean):
            await wa.send_text(phone, t["ask_name_intro"])
            await save_state(db, state, step="AWAITING_FULL_NAME")
        else:
            await wa.send_text(phone, t["service_no"])
            await save_state(db, state, step="MENU")
        return

    if step == "AWAITING_FULL_NAME":
        if len(text_clean) < 3:
            await wa.send_text(phone, t["name_short"])
            return
        await save_state(db, state, step="AWAITING_BIRTH_DATE", data_update={"full_name": text_clean})
        await wa.send_text(phone, t["thanks_name"].format(name=text_clean.split()[0]))
        return

    if step == "AWAITING_BIRTH_DATE":
        birth_date = _parse_date(text_clean)
        if not birth_date:
            await wa.send_text(phone, t["date_invalid"])
            return
        await save_state(db, state, step="AWAITING_BIRTH_TIME", data_update={"birth_date": birth_date})
        await wa.send_text(phone, t["ask_time"])
        return

    if step == "AWAITING_BIRTH_TIME":
        birth_time = None
        if not _is_unknown(text_clean):
            birth_time = _parse_time(text_clean)
            if birth_time is None:
                await wa.send_text(phone, t["time_invalid"])
                return
        await save_state(db, state, step="AWAITING_Q1", data_update={"birth_time": birth_time})
        await wa.send_text(phone, t["q_intro"])
        return

    if step == "AWAITING_Q1":
        if len(text_clean) < 5:
            await wa.send_text(phone, t["q1_short"])
            return
        await save_state(db, state, step="AWAITING_Q2", data_update={"q1": text_clean})
        await wa.send_text(phone, t["q2"])
        return

    if step == "AWAITING_Q2":
        if len(text_clean) < 5:
            await wa.send_text(phone, t["q2_short"])
            return
        await save_state(db, state, step="AWAITING_Q3", data_update={"q2": text_clean})
        await wa.send_text(phone, t["q3"])
        return

    if step == "AWAITING_Q3":
        if len(text_clean) < 5:
            await wa.send_text(phone, t["q3_short"])
            return
        await save_state(db, state, step="AWAITING_Q4", data_update={"q3": text_clean})
        await wa.send_text(phone, t["q4"])
        return

    if step == "AWAITING_Q4":
        if len(text_clean) < 5:
            await wa.send_text(phone, t["q4_short"])
            return
        await save_state(db, state, step="AWAITING_Q5", data_update={"q4": text_clean})
        await wa.send_text(phone, t["q5"])
        return

    if step == "AWAITING_Q5":
        if len(text_clean) < 5:
            await wa.send_text(phone, t["q5_short"])
            return
        # FIX 4 - Paso de términos antes del pago
        await save_state(db, state, step="AWAITING_TERMS", data_update={"q5": text_clean})
        await wa.send_text(phone, t["terms_intro"])
        await wa.send_buttons(
            phone,
            t["terms_btn_text"],
            buttons=[{"id": "acepto_terminos", "title": t["terms_btn_yes"]},
                     {"id": "cancelar_compra", "title": t["btn_cancel"}],
        )
        return

    if step == "AWAITING_TERMS":
        if _is_affirmative(text_clean) or text_clean == "acepto_terminos":
            await save_state(db, state, step="GENERATING",
                             data_update={"terms_accepted": True,
                                          "terms_accepted_at": datetime.utcnow().isoformat()})
            await wa.send_text(phone, t["terms_thanks"])
            await _generate_and_prepare_payment(db, state, phone)
        else:
            await wa.send_text(phone, t["terms_needed"])
        return

    if step == "GENERATING":
        # Evitar spam si ya está generando
        return

async def handle_button_click(db: AsyncSession, phone: str, button_id: str):
    result = await db.execute(select(ConversationState).where(ConversationState.phone_number == phone))
    state = result.scalar_one_or_none()
    data = state.collected_data if state else {}
    lang = data.get("lang", "es")
    t = MSG[lang]

    if button_id == "cancelar_compra":
        if state:
            await save_state(db, state, step="MENU", data_update={})
        await wa.send_text(phone, "Lectura cancelada sin costo. Escribe 'hola' para volver." if lang=="es" else "Reading canceled at no cost. Type 'hello' to return.")
        return

    if button_id == "acepto_terminos":
        await handle_incoming_text(db, phone, "acepto_terminos")
        return

    if button_id == "otra_carta_si":
        if state:
            await save_state(db, state, step="MENU", data_update={"lang": lang})
        await handle_incoming_text(db, phone, "hola" if lang=="es" else "hello")
        return

    if button_id == "otra_carta_no":
        await wa.send_text(phone, "Gracias por confiar en Morgan. Que las runas te guien." if lang=="es" else "Thank you for trusting Morgan. May the runes guide you.")
        return

    mapping = {
        "quiero_carta": "si",
        "no_gracias": "no",
        "reenviar_link": "pagar",
    }
    text_equivalent = mapping.get(button_id, button_id)
    await handle_incoming_text(db, phone, text_equivalent)

async def handle_button_reply(db: AsyncSession, phone: str, button_id: str):
    return await handle_button_click(db, phone, button_id)

async def _generate_and_prepare_payment(db: AsyncSession, state: ConversationState, phone: str):
    data = state.collected_data or {}
    full_name = data.get("full_name")
    birth_date = data.get("birth_date")
    birth_time = data.get("birth_time")
    questions = [data.get(f"q{i}") for i in range(1, 6) if data.get(f"q{i}")]
    lang = data.get("lang", "es")
    t = MSG[lang]
    
    try:
        if birth_time:
            reading = await astro.generate_natal_chart_complete(birth_date, birth_time, birth_location=None, lang=lang)
        else:
            reading = await astro.generate_natal_chart_simple(birth_date, lang=lang)
        
        if not reading:
            raise ValueError("Claude no devolvio lectura valida")

        # Tarot en llamada separada (evita truncado del JSON)
        if questions:
            tarot = await astro.generate_tarot_reading(questions, lang=lang)
            if tarot and tarot.get("readings"):
                reading["tarot_readings"] = tarot["readings"]
                if tarot.get("overall_message"):
                    reading["overall_message"] = tarot["overall_message"]
        
        pdf_path, cover_used = build_natal_chart_pdf(full_name=full_name, birth_date=birth_date, birth_time=birth_time, reading=reading)
        
        chart = NatalChart(
            phone_number=phone,
            full_name=full_name,
            birth_date=birth_date,
            birth_time=birth_time,
            zodiac_western=reading.get("zodiac_western"),
            zodiac_chinese=reading.get("zodiac_chinese"),
            zodiac_celtic=reading.get("zodiac_celtic"),
            zodiac_mayan=reading.get("zodiac_mayan"),
            zodiac_egyptian=reading.get("zodiac_egyptian"),
            interpretation_json=reading,
            cover_used=cover_used,
            pdf_path=pdf_path,
            pdf_ready=True,
            payment_status="pending",
        )
        db.add(chart)
        await db.commit()
        await db.refresh(chart)
        
        payment_url = await create_payment_link(amount_mxn=PRICE_MXN, reference_id=chart.id, description=f"Carta Astral Completa + 5 Preguntas Tarot - {full_name}")
        
        await save_state(db, state, step="AWAITING_PAYMENT", data_update={"chart_id": chart.id, "payment_url": payment_url})
        
        await wa.send_text(phone, t["sealed"].format(name=full_name.split()[0], zodiac=reading.get('zodiac_western',''), price=PRICE_MXN, payment_url=payment_url))
        await wa.send_buttons(phone, t["continue"], buttons=[{"id": "reenviar_link", "title": t["btn_paid"]}, {"id": "cancelar_compra", "title": t["btn_cancel"}])
    except Exception as e:
        logger.error(f"Error generando carta astral: {str(e)}", exc_info=True)
        await wa.send_text(phone, t["error"])
        await save_state(db, state, step="MENU")

async def deliver_paid_chart(db: AsyncSession, chart: NatalChart):
    chart.payment_status = "paid"
    await db.commit()
    await wa.send_document(chart.phone_number, chart.pdf_path, caption=f"Aquí está tu destino completo, {chart.full_name.split()[0]}. Gracias por confiar en Morgan." if chart.interpretation_json.get("lang","es")!="en" else f"Here is your complete destiny, {chart.full_name.split()[0]}. Thank you for trusting Morgan.")
    chart.delivered = True
    await db.commit()
    result = await db.execute(select(ConversationState).where(ConversationState.phone_number == chart.phone_number))
    state = result.scalar_one_or_none()
    if state:
        await save_state(db, state, step="COMPLETED")

def _is_affirmative(text: str) -> bool:
    return text.lower().strip() in {"si", "sí", "si!", "yes", "claro", "quiero", "ok", "va", "abrir", "abrir mi destino", "open", "open my destiny", "acepto_terminos", "acepto", "he leido y acepto"}

def _is_unknown(text: str) -> bool:
    t = text.lower()
    return "no s" in t or "no se" in t or "desconoc" in t or "don't know" in t or "dont know" in t

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
