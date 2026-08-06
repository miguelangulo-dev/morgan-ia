"""
Controla el flujo de conversación paso a paso:

1. Usuario manda mensaje          -> MENU
2. Bot pregunta si quiere servicio -> AWAITING_SERVICE_CONFIRM
3. Usuario responde                -> AWAITING_FULL_NAME
4. Bot pide nombre, fecha, hora    -> AWAITING_FULL_NAME -> AWAITING_BIRTH_DATE -> AWAITING_BIRTH_TIME
5. Bot genera lectura + arma PDF   -> GENERATING -> AWAITING_PAYMENT
6. Pago confirmado                 -> entrega PDF -> COMPLETED
"""

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

PRICE_MXN = 79  # mismo costo para carta completa o simple, según pediste


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
    """Punto de entrada único: recibe cualquier texto y lo enruta según el paso actual."""
    state = await get_or_create_state(db, phone)
    step = state.current_step
    text_clean = text.strip()

    # ------------------------------------------------------------------
    # PASO 1: primer contacto -> presenta el servicio y pregunta si lo quiere
    # ------------------------------------------------------------------
    if step == "MENU":
        await wa.send_text(
            phone,
            "🌙 *Bienvenido a Morgan-ia* 🌙\n\n"
            "Puedo generarte tu *Carta Astral* personalizada, con tu signo occidental, "
            "chino, celta, maya y egipcio.\n\n"
            f"El costo es de ${PRICE_MXN} MXN, pagas solo cuando tu lectura esté lista.\n\n"
            "¿Quieres que te la genere?"
        )
        await wa.send_buttons(
            phone,
            "Selecciona una opción:",
            buttons=[
                {"id": "quiero_carta", "title": "Sí, quiero mi carta"},
                {"id": "no_gracias", "title": "No, gracias"},
            ],
        )
        await save_state(db, state, step="AWAITING_SERVICE_CONFIRM")
        return

    # ------------------------------------------------------------------
    # PASO 3 (si responde con texto en vez de botón, lo tomamos igual)
    # ------------------------------------------------------------------
    if step == "AWAITING_SERVICE_CONFIRM":
        if _is_affirmative(text_clean):
            await _ask_full_name(phone)
            await save_state(db, state, step="AWAITING_FULL_NAME")
        else:
            await wa.send_text(phone, "Sin problema. Escribe 'hola' cuando quieras tu carta astral 🌙")
            await save_state(db, state, step="MENU")
        return

    # ------------------------------------------------------------------
    # PASO 4: nombre completo
    # ------------------------------------------------------------------
    if step == "AWAITING_FULL_NAME":
        if len(text_clean) < 3:
            await wa.send_text(phone, "Ese nombre parece muy corto. ¿Me compartes tu nombre completo?")
            return
        await save_state(db, state, step="AWAITING_BIRTH_DATE", data_update={"full_name": text_clean})
        await wa.send_text(phone, f"Gracias, {text_clean.split()[0]} 🌙\n\n¿Cuál es tu *fecha de nacimiento*? (Ej: 15/03/1990)")
        return

    # ------------------------------------------------------------------
    # PASO 4: fecha de nacimiento
    # ------------------------------------------------------------------
    if step == "AWAITING_BIRTH_DATE":
        birth_date = _parse_date(text_clean)
        if not birth_date:
            await wa.send_text(phone, "No pude leer esa fecha. Usa el formato DD/MM/AAAA, ej: 15/03/1990")
            return
        await save_state(db, state, step="AWAITING_BIRTH_TIME", data_update={"birth_date": birth_date})
        await wa.send_text(
            phone,
            "¿Y a qué *hora* naciste? (Ej: 14:30)\n\n"
            "Si no la sabes, escribe *'no sé'* y seguimos con lo que tenemos."
        )
        return

    # ------------------------------------------------------------------
    # PASO 4: hora de nacimiento (opcional)
    # ------------------------------------------------------------------
    if step == "AWAITING_BIRTH_TIME":
        birth_time = None
        if not _is_unknown(text_clean):
            birth_time = _parse_time(text_clean)
            if birth_time is None:
                await wa.send_text(phone, "No pude leer esa hora. Usa formato HH:MM (24h), ej: 14:30, o escribe 'no sé'.")
                return

        await save_state(db, state, step="GENERATING", data_update={"birth_time": birth_time})
        await wa.send_text(phone, "✨ Generando tu carta astral, dame un momento...")
        await _generate_and_prepare_payment(db, state, phone)
        return

    # ------------------------------------------------------------------
    # PASO 5/6: esperando pago -> cualquier mensaje le recuerda que pague
    # ------------------------------------------------------------------
    if step == "AWAITING_PAYMENT":
        await wa.send_text(
            phone,
            f"Tu carta astral ya está lista ✨. Para recibir el PDF, completa tu pago de ${PRICE_MXN} MXN "
            f"en el link que te envié. En cuanto se confirme, te lo entrego aquí mismo."
        )
        return

    # ------------------------------------------------------------------
    # Ya completado -> reinicia si quiere otra
    # ------------------------------------------------------------------
    if step == "COMPLETED":
        if _is_affirmative(text_clean) or "otra" in text_clean.lower():
            await save_state(db, state, step="MENU", data_update={})
            await handle_incoming_text(db, phone, "hola")
        else:
            await wa.send_text(phone, "🌙 Escribe 'hola' cuando quieras otra lectura.")
        return

    # Fallback
    await save_state(db, state, step="MENU")
    await wa.send_text(phone, "Vamos a empezar de nuevo. Escribe 'hola' 🌙")


async def handle_button_reply(db: AsyncSession, phone: str, button_id: str):
    """Traduce el click del botón a texto equivalente y reusa la misma lógica."""
    mapping = {
        "quiero_carta": "sí",
        "no_gracias": "no",
    }
    text_equivalent = mapping.get(button_id, button_id)
    await handle_incoming_text(db, phone, text_equivalent)


# ============================================================================
# PASO 5: generar lectura + armar PDF (portada aleatoria + contenido) + cobrar
# ============================================================================

async def _generate_and_prepare_payment(db: AsyncSession, state: ConversationState, phone: str):
    data = state.collected_data or {}
    full_name = data.get("full_name")
    birth_date = data.get("birth_date")
    birth_time = data.get("birth_time")

    try:
        if birth_time:
            reading = await astro.generate_natal_chart_complete(birth_date, birth_time, birth_location=None)
        else:
            reading = await astro.generate_natal_chart_simple(birth_date)

        if not reading:
            raise ValueError("Claude no devolvió lectura válida")

        # Arma el PDF: elige portada aleatoria de la carpeta local y llena las hojas de contenido
        # en el orden correcto, con nombre/fecha/hora al inicio de cada página.
        pdf_path, cover_used = build_natal_chart_pdf(
            full_name=full_name,
            birth_date=birth_date,
            birth_time=birth_time,
            reading=reading,
        )

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

        # Genera el link de pago (Stripe) ANTES de entregar el PDF
        payment_url = await create_payment_link(
            amount_mxn=PRICE_MXN,
            reference_id=chart.id,
            description=f"Carta Astral - {full_name}",
        )

        await save_state(db, state, step="AWAITING_PAYMENT", data_update={"chart_id": chart.id})

        await wa.send_text(
            phone,
            f"✨ Tu carta astral está lista, {full_name.split()[0]}.\n\n"
            f"Tu signo occidental es *{reading.get('zodiac_western')}*.\n\n"
            f"Para entregarte el PDF completo con tu portada personalizada y las 5 secciones de tu lectura, "
            f"realiza tu pago de ${PRICE_MXN} MXN aquí:\n\n{payment_url}\n\n"
            f"En cuanto se confirme, te lo mando de inmediato 🌙"
        )

    except Exception as e:
        logger.error(f"❌ Error generando carta astral: {str(e)}", exc_info=True)
        await wa.send_text(phone, "Tuve un problema generando tu carta. Intenta de nuevo en un momento escribiendo 'hola'.")
        await save_state(db, state, step="MENU")


# ============================================================================
# PASO 6: se llama desde el webhook de Stripe cuando el pago se confirma
# ============================================================================

async def deliver_paid_chart(db: AsyncSession, chart: NatalChart):
    chart.payment_status = "paid"
    await db.commit()

    await wa.send_document(
        chart.phone_number,
        chart.pdf_path,
        caption=f"🌙 Aquí está tu Carta Astral, {chart.full_name.split()[0]}. ¡Gracias por tu confianza!",
    )
    chart.delivered = True
    await db.commit()

    result = await db.execute(select(ConversationState).where(ConversationState.phone_number == chart.phone_number))
    state = result.scalar_one_or_none()
    if state:
        await save_state(db, state, step="COMPLETED")


# ============================================================================
# Helpers
# ============================================================================

async def _ask_full_name(phone: str):
    await wa.send_text(
        phone,
        "Perfecto 🌙 Para generar tu carta astral necesito 3 datos:\n\n"
        "1️⃣ Nombre completo\n2️⃣ Fecha de nacimiento\n3️⃣ Hora de nacimiento (si la sabes)\n\n"
        "Empecemos: ¿cuál es tu *nombre completo*?"
    )


def _is_affirmative(text: str) -> bool:
    return text.lower().strip() in {"si", "sí", "sí!", "yes", "claro", "quiero", "ok", "va"}


def _is_unknown(text: str) -> bool:
    t = text.lower()
    return "no s" in t or "no se" in t or "no sé" in t or "desconoc" in t


def _parse_date(text: str):
    """Acepta DD/MM/AAAA o DD-MM-AAAA y devuelve 'AAAA-MM-DD'."""
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
    """Acepta HH:MM y devuelve 'HH:MM'."""
    text = text.strip()
    try:
        t = datetime.strptime(text, "%H:%M")
        return t.strftime("%H:%M")
    except ValueError:
        return None
