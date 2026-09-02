"""
conversation_flow.py - Reescrito
- Restaura pregunta de LUGAR de nacimiento y agrega GENERO (para reporte)
- Paso obligatorio de TERMINOS antes del pago
- Idioma ES/EN (textos fijos) + contenido de Claude en idioma del usuario
- Clave maestra de admin -> reporte de ventas por WhatsApp
- Tarot en llamada separada (no trunca el JSON)
"""
import os, re, logging
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models import ConversationState, NatalChart
from utils_whatsapp import WhatsAppClient
from agentes_claude_astro import AstroAgent
from pdf_generator import build_natal_chart_pdf
from payment import create_payment_link

logger = logging.getLogger(__name__)
wa = WhatsAppClient()
astro = AstroAgent()
PRICE_MXN = 49
ADMIN_KEY = os.getenv("MORGAN_ADMIN_KEY", "634r50fw4R!977$5283266")
TERMS_URL = "www.sincron-ia.com.mx"

# ---------- Textos fijos ES/EN ----------
MSG = {
    "es": {
        "intro1": "No es casualidad que llegaras aqui... El destino ya esta escrito en las estrellas.\nSoy Morgania, guardiana de los velos del destino.",
        "offer": ("Tu Lectura Completa por ${p} MXN\n\nTe entrego:\n- Tu Carta Astral completa\n"
                  "- Afinidades zodiacales\n- Tu signo Celta, Maya, Chino y Egipcio\n"
                  "- Posicion de los planetas el dia que naciste\n- Horoscopo semanal\n"
                  "- 5 preguntas al destino con tirada de tarot (Si/No + carta)\n\n"
                  "Pagas ${p} MXN solo cuando todo este listo.\n\nAceptas abrir tu destino?"),
        "b_yes": "Si, abrir mi destino", "b_no": "No por ahora", "choose": "Elige tu camino:",
        "later": "Entiendo... las estrellas esperaran. Escribe 'hola' cuando estes list@.",
        "ask_name": "Para comenzar, dime tu nombre completo.",
        "short_name": "Ese nombre parece muy corto. Me compartes tu nombre completo?",
        "ask_date": "Gracias, {n}\n\nCual es tu fecha de nacimiento? (Ej: 15/03/1990)",
        "bad_date": "No pude leer esa fecha. Usa DD/MM/AAAA, ej: 15/03/1990",
        "ask_time": "Y a que hora naciste? (Ej: 14:30)\nSi no la sabes, escribe 'no se'.",
        "bad_time": "No pude leer esa hora. Usa HH:MM (24h), ej: 14:30, o escribe 'no se'.",
        "ask_place": "En que ciudad naciste? (Ej: Celaya, Mexico)\nSi no lo sabes, escribe 'no se'.",
        "ask_gender": "Como te identificas?",
        "g_m": "Masculino", "g_f": "Femenino", "g_x": "Prefiero no decir",
        "ask_q1": ("Ahora la parte sagrada. Puedes hacerme 5 preguntas al destino; te respondo Si/No "
                   "con la carta que salio y su simbologia.\n\nPregunta 1 de 5:"),
        "next_q": "Anotada.\n\nPregunta {i} de 5:",
        "short_q": "Formulala un poco mas completa. Pregunta {i}?",
        "terms_body": f"He leido y acepto los terminos y condiciones de {TERMS_URL}",
        "b_accept": "He leido y acepto", "b_cancel": "Cancelar",
        "terms_need": "Necesito que aceptes los terminos para continuar. Escribe 'hola' para reiniciar.",
        "generating": ("Gracias. Sello tus 5 preguntas en el circulo de proteccion.\n"
                       "Generando tu lectura completa... dame un momento."),
        "sealed": ("Tu destino esta sellado, {n}.\n\nEres {w} en occidente.\n"
                   "Tus 5 respuestas de tarot ya estan en el PDF.\n\n"
                   "Para recibir tu PDF completo, paga ${p} MXN aqui:\n{u}\n\n"
                   "En cuanto se confirme, te lo envio aqui mismo."),
        "cont": "Deseas continuar?", "b_paid": "Ya pague / Reenviar",
        "err": "Las runas se nublaron un momento... Intenta de nuevo escribiendo 'hola'.",
        "delivered": "Aqui esta tu destino completo, {n}. Gracias por confiar en Morgania.",
        "restart": "Escribe 'hola' para comenzar.",
    },
    "en": {
        "intro1": "It is no coincidence you are here... Your destiny is written in the stars.\nI am Morgania, keeper of the veils.",
        "offer": ("Your Full Reading for ${p} MXN\n\nYou get:\n- Your complete Natal Chart\n"
                  "- Zodiac affinities\n- Your Celtic, Mayan, Chinese and Egyptian sign\n"
                  "- Planetary positions on your birth day\n- Weekly horoscope\n"
                  "- 5 questions to destiny with a tarot spread (Yes/No + card)\n\n"
                  "You pay ${p} MXN only when everything is ready.\n\nDo you accept to open your destiny?"),
        "b_yes": "Yes, open it", "b_no": "Not now", "choose": "Choose your path:",
        "later": "I understand... the stars will wait. Type 'hi' when you are ready.",
        "ask_name": "To begin, tell me your full name.",
        "short_name": "That name seems too short. Can you share your full name?",
        "ask_date": "Thank you, {n}\n\nWhat is your date of birth? (e.g. 15/03/1990)",
        "bad_date": "I couldn't read that date. Use DD/MM/YYYY, e.g. 15/03/1990",
        "ask_time": "And what time were you born? (e.g. 14:30)\nIf you don't know, type 'idk'.",
        "bad_time": "I couldn't read that time. Use HH:MM (24h), e.g. 14:30, or type 'idk'.",
        "ask_place": "In which city were you born? (e.g. Celaya, Mexico)\nIf unknown, type 'idk'.",
        "ask_gender": "How do you identify?",
        "g_m": "Male", "g_f": "Female", "g_x": "Prefer not to say",
        "ask_q1": ("Now the sacred part. You may ask 5 questions to destiny; I answer Yes/No "
                   "with the card drawn and its symbolism.\n\nQuestion 1 of 5:"),
        "next_q": "Noted.\n\nQuestion {i} of 5:",
        "short_q": "Make it a bit more complete. Question {i}?",
        "terms_body": f"I have read and accept the terms and conditions of {TERMS_URL}",
        "b_accept": "I read and accept", "b_cancel": "Cancel",
        "terms_need": "I need you to accept the terms to continue. Type 'hi' to restart.",
        "generating": "Thank you. Sealing your 5 questions.\nGenerating your full reading... one moment.",
        "sealed": ("Your destiny is sealed, {n}.\n\nYou are {w} in the western zodiac.\n"
                   "Your 5 tarot answers are in the PDF.\n\n"
                   "To receive your full PDF, pay ${p} MXN here:\n{u}\n\n"
                   "As soon as it's confirmed, I'll send it right here."),
        "cont": "Continue?", "b_paid": "I paid / Resend",
        "err": "The runes clouded for a moment... Try again by typing 'hi'.",
        "delivered": "Here is your complete destiny, {n}. Thank you for trusting Morgania.",
        "restart": "Type 'hi' to start.",
    },
}

def _detect_lang(text: str) -> str:
    t = f" {(text or '').lower()} "
    en = sum(w in t for w in [" the "," what "," when "," yes "," no "," my "," born ",
                              " love "," will "," should "," hi "," hello "," name "])
    es = sum(w in t for w in [" el "," la "," que "," cuando "," si "," no "," mi "," naci ",
                              " amor "," debo "," hola "," nombre "," soy "])
    return "en" if en > es else "es"

def T(lang, key, **kw):
    s = MSG.get(lang, MSG["es"]).get(key, MSG["es"][key])
    return s.replace("${p}", str(PRICE_MXN)).format(p=PRICE_MXN, **kw) if kw or "{" in s else s

# ---------- Helpers de parseo ----------
def _is_affirmative(t):
    return t.strip().lower() in ["si","sí","s","yes","y","ok","dale","claro","va","quiero","acepto","hi","hola"]

def _is_unknown(t):
    return t.strip().lower() in ["no se","no sé","nose","ns","idk","dont know","don't know","no lo se","-"]

def _parse_date(t):
    m = re.search(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", t)
    if not m: return None
    d, mth, y = m.groups()
    y = ("19"+y if int(y) > 30 else "20"+y) if len(y) == 2 else y
    try:
        datetime(int(y), int(mth), int(d)); return f"{int(d):02d}/{int(mth):02d}/{y}"
    except ValueError:
        return None

def _parse_time(t):
    m = re.search(r"(\d{1,2}):(\d{2})", t)
    if not m: return None
    h, mi = int(m.group(1)), int(m.group(2))
    return f"{h:02d}:{mi:02d}" if 0 <= h < 24 and 0 <= mi < 60 else None

# ---------- State ----------
async def get_or_create_state(db, phone):
    r = await db.execute(select(ConversationState).where(ConversationState.phone_number == phone))
    st = r.scalar_one_or_none()
    if not st:
        st = ConversationState(phone_number=phone, current_step="MENU", collected_data={})
        db.add(st); await db.commit(); await db.refresh(st)
    return st

async def save_state(db, state, step=None, data_update=None):
    if step: state.current_step = step
    if data_update:
        merged = dict(state.collected_data or {}); merged.update(data_update)
        state.collected_data = merged
    state.updated_at = datetime.utcnow()
    await db.commit()

# ---------- Reporte admin ----------
async def _build_admin_report(db) -> str:
    total = (await db.execute(select(func.count()).select_from(NatalChart)
             .where(NatalChart.payment_status == "paid"))).scalar() or 0
    gen = (await db.execute(select(NatalChart.gender, func.count())
           .where(NatalChart.payment_status == "paid").group_by(NatalChart.gender))).all()
    sig = (await db.execute(select(NatalChart.zodiac_western, func.count())
           .where(NatalChart.payment_status == "paid").group_by(NatalChart.zodiac_western))).all()
    today = datetime.utcnow().date()
    hoy = (await db.execute(select(func.count()).select_from(NatalChart)
           .where(NatalChart.payment_status == "paid",
                  NatalChart.created_at >= datetime.combine(today, datetime.min.time())))).scalar() or 0
    pct = lambda n: f"{(n*100//total) if total else 0}%"
    out = [f"REPORTE MORGAN-IA", f"Ventas totales: {total}  (${total*PRICE_MXN} MXN)", f"Ventas hoy: {hoy}", "", "Por genero:"]
    out += [f"  {g or 'N/D'}: {c} ({pct(c)})" for g, c in gen] or ["  (sin datos)"]
    out += ["", "Por signo:"]
    out += [f"  {s or 'N/D'}: {c} ({pct(c)})" for s, c in sorted(sig, key=lambda x: -x[1])] or ["  (sin datos)"]
    return "\n".join(out)

# ---------- Flujo principal ----------
async def handle_incoming_text(db, phone, text):
    text_clean = (text or "").strip()

    # Clave maestra (admin) - antes de todo
    if text_clean == ADMIN_KEY:
        try:
            rep = await _build_admin_report(db)
        except Exception as e:
            logger.error(f"Error reporte admin: {e}", exc_info=True); rep = "No pude generar el reporte."
        await wa.send_text(phone, rep); return

    state = await get_or_create_state(db, phone)
    step = state.current_step
    data = state.collected_data or {}
    lang = data.get("lang", "es")

    if step == "MENU":
        lang = _detect_lang(text_clean)
        await save_state(db, state, data_update={"lang": lang})
        await wa.send_text(phone, T(lang, "intro1"))
        await wa.send_text(phone, T(lang, "offer"))
        await wa.send_buttons(phone, T(lang, "choose"),
            buttons=[{"id":"quiero_carta","title":T(lang,"b_yes")},{"id":"no_gracias","title":T(lang,"b_no")}])
        await save_state(db, state, step="AWAITING_SERVICE_CONFIRM"); return

    if step == "AWAITING_SERVICE_CONFIRM":
        if _is_affirmative(text_clean):
            await wa.send_text(phone, T(lang, "ask_name"))
            await save_state(db, state, step="AWAITING_FULL_NAME")
        else:
            await wa.send_text(phone, T(lang, "later")); await save_state(db, state, step="MENU")
        return

    if step == "AWAITING_FULL_NAME":
        if len(text_clean) < 3:
            await wa.send_text(phone, T(lang, "short_name")); return
        await save_state(db, state, step="AWAITING_BIRTH_DATE", data_update={"full_name": text_clean})
        await wa.send_text(phone, T(lang, "ask_date", n=text_clean.split()[0])); return

    if step == "AWAITING_BIRTH_DATE":
        bd = _parse_date(text_clean)
        if not bd:
            await wa.send_text(phone, T(lang, "bad_date")); return
        await save_state(db, state, step="AWAITING_BIRTH_TIME", data_update={"birth_date": bd})
        await wa.send_text(phone, T(lang, "ask_time")); return

    if step == "AWAITING_BIRTH_TIME":
        bt = None
        if not _is_unknown(text_clean):
            bt = _parse_time(text_clean)
            if bt is None:
                await wa.send_text(phone, T(lang, "bad_time")); return
        await save_state(db, state, step="AWAITING_BIRTH_PLACE", data_update={"birth_time": bt})
        await wa.send_text(phone, T(lang, "ask_place")); return

    if step == "AWAITING_BIRTH_PLACE":
        place = None if _is_unknown(text_clean) else text_clean
        await save_state(db, state, step="AWAITING_GENDER", data_update={"birth_place": place})
        await wa.send_buttons(phone, T(lang, "ask_gender"),
            buttons=[{"id":"genero_m","title":T(lang,"g_m")},
                     {"id":"genero_f","title":T(lang,"g_f")},
                     {"id":"genero_x","title":T(lang,"g_x")}])
        return

    if step == "AWAITING_GENDER":
        gmap = {"genero_m":T(lang,"g_m"),"genero_f":T(lang,"g_f"),"genero_x":T(lang,"g_x")}
        gender = gmap.get(text_clean, text_clean)
        await save_state(db, state, step="AWAITING_Q1", data_update={"birth_gender": gender})
        await wa.send_text(phone, T(lang, "ask_q1")); return

    if step in ["AWAITING_Q1","AWAITING_Q2","AWAITING_Q3","AWAITING_Q4","AWAITING_Q5"]:
        n = int(step[-1])
        if len(text_clean) < 5:
            await wa.send_text(phone, T(lang, "short_q", i=n)); return
        if n < 5:
            await save_state(db, state, step=f"AWAITING_Q{n+1}", data_update={f"q{n}": text_clean})
            await wa.send_text(phone, T(lang, "next_q", i=n+1))
        else:
            await save_state(db, state, step="AWAITING_TERMS", data_update={"q5": text_clean})
            await wa.send_buttons(phone, T(lang, "terms_body"),
                buttons=[{"id":"acepto_terminos","title":T(lang,"b_accept")},
                         {"id":"cancelar_compra","title":T(lang,"b_cancel")}])
        return

    if step == "AWAITING_TERMS":
        if text_clean == "acepto_terminos" or _is_affirmative(text_clean):
            await save_state(db, state, step="GENERATING",
                             data_update={"terms_accepted": True,
                                          "terms_accepted_at": datetime.utcnow().isoformat()})
            await wa.send_text(phone, T(lang, "generating"))
            await _generate_and_prepare_payment(db, state, phone)
        else:
            await wa.send_text(phone, T(lang, "terms_need")); await save_state(db, state, step="MENU")
        return

    if step == "AWAITING_PAYMENT":
        url = data.get("payment_url", "")
        if url:
            await wa.send_text(phone, url)
            await wa.send_buttons(phone, T(lang, "cont"),
                buttons=[{"id":"reenviar_link","title":T(lang,"b_paid")},
                         {"id":"cancelar_compra","title":T(lang,"b_cancel")}])
        else:
            await save_state(db, state, step="MENU"); await wa.send_text(phone, T(lang, "restart"))
        return

    # COMPLETED u otros
    await save_state(db, state, step="MENU"); await wa.send_text(phone, T(lang, "restart"))

async def handle_button_reply(db, phone, button_id):
    if button_id == "cancelar_compra":
        r = await db.execute(select(ConversationState).where(ConversationState.phone_number == phone))
        st = r.scalar_one_or_none()
        lang = (st.collected_data or {}).get("lang","es") if st else "es"
        if st: await save_state(db, st, step="MENU", data_update={})
        await wa.send_text(phone, T(lang, "later")); return
    if button_id == "reenviar_link":
        r = await db.execute(select(ConversationState).where(ConversationState.phone_number == phone))
        st = r.scalar_one_or_none()
        d = (st.collected_data or {}) if st else {}
        lang = d.get("lang", "es")
        # Anti-doble-toque: ignora repeticiones dentro de 15s (evita triple link)
        now = datetime.utcnow()
        last = d.get("last_resend_at")
        if last:
            try:
                if (now - datetime.fromisoformat(last)).total_seconds() < 15:
                    return
            except Exception:
                pass
        # Si el pago ya se confirmo, entrega el PDF en vez de reenviar el link
        chart_id = d.get("chart_id")
        if chart_id:
            cr = await db.execute(select(NatalChart).where(NatalChart.id == chart_id))
            chart = cr.scalar_one_or_none()
            if chart and chart.payment_status == "paid":
                if st: await save_state(db, st, data_update={"last_resend_at": now.isoformat()})
                if not getattr(chart, "delivered", False):
                    await deliver_paid_chart(db, chart)
                return
        # Aun no pagado: reenvia el link UNA sola vez (sin botones, para no duplicar)
        if st: await save_state(db, st, data_update={"last_resend_at": now.isoformat()})
        url = d.get("payment_url", "")
        await wa.send_text(phone, url or T(lang, "restart")); return
        mapping = {"quiero_carta":"si","no_gracias":"no",
               "genero_m":"genero_m","genero_f":"genero_f","genero_x":"genero_x",
               "acepto_terminos":"acepto_terminos"}
    await handle_incoming_text(db, phone, mapping.get(button_id, button_id))

# Compat: main.py llama handle_button_click en algunas versiones
async def handle_button_click(db, phone, button_id):
    return await handle_button_reply(db, phone, button_id)

async def _generate_and_prepare_payment(db, state, phone):
    data = state.collected_data or {}
    lang = data.get("lang","es")
    full_name = data.get("full_name"); birth_date = data.get("birth_date")
    birth_time = data.get("birth_time"); birth_place = data.get("birth_place")
    gender = data.get("birth_gender")
    questions = [data.get(f"q{i}") for i in range(1,6) if data.get(f"q{i}")]
    try:
        if birth_time:
            reading = await astro.generate_natal_chart_complete(
                birth_date, birth_time, birth_location=birth_place, gender=gender, lang=lang)
        else:
            reading = await astro.generate_natal_chart_simple(
                birth_date, birth_place=birth_place, gender=gender, lang=lang)
        if not reading:
            raise ValueError("Claude no devolvio lectura valida")
        reading["birth_place"] = birth_place or "No especificado"
        reading["birth_gender"] = gender or "No especificado"

        if questions:
            tarot = await astro.generate_tarot_reading(questions, lang=lang)
            if tarot and tarot.get("readings"):
                reading["tarot_readings"] = tarot["readings"]
                if tarot.get("overall_message"):
                    reading["overall_message"] = tarot["overall_message"]

        pdf_path, cover_used = build_natal_chart_pdf(full_name, birth_date, birth_time, reading)

        chart = NatalChart(
            phone_number=phone, full_name=full_name, birth_date=birth_date, birth_time=birth_time,
            birth_place=birth_place, gender=gender,
            zodiac_western=reading.get("zodiac_western"), zodiac_chinese=reading.get("zodiac_chinese"),
            zodiac_celtic=reading.get("zodiac_celtic"), zodiac_mayan=reading.get("zodiac_mayan"),
            zodiac_egyptian=reading.get("zodiac_egyptian"),
            interpretation_json=reading, cover_used=cover_used, pdf_path=pdf_path,
            pdf_ready=True, payment_status="pending")
        db.add(chart); await db.commit(); await db.refresh(chart)

        payment_url = await create_payment_link(
            amount_mxn=PRICE_MXN, reference_id=chart.id,
            description=f"Carta Astral + 5 Tarot - {full_name}")
        await save_state(db, state, step="AWAITING_PAYMENT",
                         data_update={"chart_id": chart.id, "payment_url": payment_url})
        await wa.send_text(phone, T(lang, "sealed",
                           n=(full_name or "").split()[0], w=reading.get("zodiac_western",""), u=payment_url))
        await wa.send_buttons(phone, T(lang, "cont"),
            buttons=[{"id":"reenviar_link","title":T(lang,"b_paid")},
                     {"id":"cancelar_compra","title":T(lang,"b_cancel")}])
    except Exception as e:
        logger.error(f"Error generando: {e}", exc_info=True)
        await wa.send_text(phone, T(lang, "err")); await save_state(db, state, step="MENU")

async def deliver_paid_chart(db, chart):
    chart.payment_status = "paid"; await db.commit()
    r = await db.execute(select(ConversationState).where(ConversationState.phone_number == chart.phone_number))
    st = r.scalar_one_or_none()
    lang = (st.collected_data or {}).get("lang","es") if st else "es"
    await wa.send_document(chart.phone_number, chart.pdf_path,
        caption=T(lang, "delivered", n=(chart.full_name or "").split()[0]),
        filename="Morgan-IA.pdf")
    chart.delivered = True; await db.commit()
    if st: await save_state(db, st, step="COMPLETED")
