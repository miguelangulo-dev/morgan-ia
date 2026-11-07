"""
conversation_flow.py - Flujo de conversacion Morgan-ia

PASOS DEL FLUJO (en orden):
  MENU
  -> AWAITING_CONSENT        (BUG1 - LFPDPPP: aviso de privacidad PRIMERO)
  -> AWAITING_SERVICE_CONFIRM
  -> AWAITING_FULL_NAME
  -> AWAITING_BIRTH_DATE
  -> AWAITING_BIRTH_TIME
  -> AWAITING_BIRTH_PLACE
  -> AWAITING_GENDER
  -> AWAITING_Q1 -> Q2 -> Q3 -> Q4 -> Q5
  -> AWAITING_INVOICE_MX     (BUG2 - solo para lada +52)
  -> AWAITING_RFC            (BUG2 - opcional, si el usuario dice si a factura)
  -> GENERATING
  -> AWAITING_PAYMENT
  -> COMPLETED

CAMBIOS v3.0:
- BUG1: consentimiento LFPDPPP con tabla auditoria_consentimientos
- BUG2: deteccion lada +52 / extranjero, flujo de facturacion diferenciado
- BUG6: branding "Un producto de Sincronia Tech Developers S.A.S."
- BUG7: guard para pdf_path None, logging mejorado
"""

import logging
import re
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import ConversationState, NatalChart, AuditoriaConsentimiento
from utils_whatsapp import WhatsAppClient
from agentes_claude_astro import AstroAgent
from pdf_generator import build_natal_chart_pdf
from payment import create_payment_link

logger = logging.getLogger(__name__)

wa = WhatsAppClient()
astro = AstroAgent()

PRICE_MXN = 49
BRANDING = "Un producto de Sincronia Tech Developers S.A.S. - www.sincron-ia.com.mx"
AVISO_VERSION = "v1.3"
AVISO_URL = "www.sincron-ia.com.mx/aviso"

# Texto completo del aviso (se guarda en auditoria)
TEXTO_AVISO = (
    "Hola, soy Morgan-IA. Tus datos (nombre, fecha de nacimiento, lugar) se usan "
    "unicamente para generar tu carta astral. No se comparten con terceros. "
    f"Consulta el Aviso de Privacidad completo en {AVISO_URL} ({AVISO_VERSION})."
)


# ============================================================================
# Helpers de estado
# ============================================================================

async def get_or_create_state(db: AsyncSession, phone: str) -> ConversationState:
    result = await db.execute(
        select(ConversationState).where(ConversationState.phone_number == phone)
    )
    state = result.scalar_one_or_none()
    if not state:
        state = ConversationState(
            phone_number=phone, current_step="MENU", collected_data={}
        )
        db.add(state)
        await db.commit()
        await db.refresh(state)
    return state


async def save_state(
    db: AsyncSession,
    state: ConversationState,
    step: str = None,
    data_update: dict = None,
):
    if step:
        state.current_step = step
    if data_update:
        merged = dict(state.collected_data or {})
        merged.update(data_update)
        state.collected_data = merged
    state.updated_at = datetime.utcnow()
    await db.commit()


# ============================================================================
# BUG2: Deteccion de lada
# ============================================================================

def _es_mexico(phone: str) -> bool:
    """
    True si el numero tiene lada mexicana (+52).
    WhatsApp entrega el numero sin '+', p.ej.: 521234567890 o 5212345678
    """
    clean = re.sub(r"\D", "", phone)
    return clean.startswith("52")


# ============================================================================
# Auditoria LFPDPPP
# ============================================================================

async def _registrar_consentimiento(
    db: AsyncSession,
    phone: str,
    acepto: bool,
    texto: str,
):
    """Guarda registro en auditoria_consentimientos."""
    pais = "MX" if _es_mexico(phone) else "EXT"
    registro = AuditoriaConsentimiento(
        whatsapp_id=phone,
        pais_detectado=pais,
        fecha_hora_utc=datetime.utcnow(),
        version_aviso=AVISO_VERSION,
        texto_aceptado=texto,
        acepto=acepto,
    )
    db.add(registro)
    await db.commit()
    logger.info(f"[Auditoria] Consentimiento {'ACEPTADO' if acepto else 'RECHAZADO'} - {phone} ({pais})")


# ============================================================================
# Punto de entrada: texto libre
# ============================================================================

async def handle_incoming_text(db: AsyncSession, phone: str, text: str):
    """Recibe cualquier texto y lo enruta segun el paso actual."""
    state = await get_or_create_state(db, phone)
    step = state.current_step
    text_clean = text.strip()

    # ------------------------------------------------------------------
    # MENU: primer contacto -> mostrar aviso de privacidad (BUG1)
    # ------------------------------------------------------------------
    if step == "MENU":
        await wa.send_text(
            phone,
            f"Hola, soy Morgan-IA *{chr(10)}Un producto de Sincronia Tech Developers S.A.S.*\n\n"
            f"{TEXTO_AVISO}\n\n"
            "Para continuar necesito tu consentimiento.\n"
            f"Consulta el aviso completo en {AVISO_URL}",
        )
        await wa.send_buttons(
            phone,
            "Selecciona una opcion:",
            buttons=[
                {"id": "consent_si", "title": "Si, acepto Aviso"},
                {"id": "consent_no", "title": "No acepto"},
            ],
        )
        await save_state(db, state, step="AWAITING_CONSENT")
        return

    # ------------------------------------------------------------------
    # AWAITING_CONSENT: procesar respuesta al aviso (BUG1)
    # ------------------------------------------------------------------
    if step == "AWAITING_CONSENT":
        if _is_affirmative(text_clean):
            await _registrar_consentimiento(db, phone, acepto=True, texto="Si, acepto")
            await _preguntar_servicio(phone)
            await save_state(db, state, step="AWAITING_SERVICE_CONFIRM")
        else:
            await _registrar_consentimiento(db, phone, acepto=False, texto=text_clean)
            await wa.send_text(
                phone,
                "Sin problema. No podemos procesar tu lectura sin tu consentimiento.\n"
                "Si cambias de opinion, escribe 'hola' cuando quieras.\n\n"
                f"_{BRANDING}_",
            )
            await save_state(db, state, step="MENU")
        return

    # ------------------------------------------------------------------
    # AWAITING_SERVICE_CONFIRM
    # ------------------------------------------------------------------
    if step == "AWAITING_SERVICE_CONFIRM":
        if _is_affirmative(text_clean):
            await _ask_full_name(phone)
            await save_state(db, state, step="AWAITING_FULL_NAME")
        else:
            await wa.send_text(
                phone,
                "Sin problema. Escribe 'hola' cuando quieras tu carta astral.\n\n"
                f"_{BRANDING}_",
            )
            await save_state(db, state, step="MENU")
        return

    # ------------------------------------------------------------------
    # AWAITING_FULL_NAME
    # ------------------------------------------------------------------
    if step == "AWAITING_FULL_NAME":
        if len(text_clean) < 3:
            await wa.send_text(phone, "Ese nombre parece muy corto. Comparte tu nombre completo:")
            return
        await save_state(db, state, step="AWAITING_BIRTH_DATE", data_update={"full_name": text_clean})
        await wa.send_text(
            phone,
            f"Gracias, {text_clean.split()[0]}.\n\n"
            "Cual es tu *fecha de nacimiento*? (Ej: 15/03/1990)",
        )
        return

    # ------------------------------------------------------------------
    # AWAITING_BIRTH_DATE
    # ------------------------------------------------------------------
    if step == "AWAITING_BIRTH_DATE":
        birth_date = _parse_date(text_clean)
        if not birth_date:
            await wa.send_text(
                phone, "No pude leer esa fecha. Usa el formato DD/MM/AAAA, ej: 15/03/1990"
            )
            return
        await save_state(db, state, step="AWAITING_BIRTH_TIME", data_update={"birth_date": birth_date})
        await wa.send_text(
            phone,
            "A que *hora* naciste? (Ej: 14:30)\n\n"
            "Si no la sabes, escribe *'no se'* y seguimos.",
        )
        return

    # ------------------------------------------------------------------
    # AWAITING_BIRTH_TIME
    # ------------------------------------------------------------------
    if step == "AWAITING_BIRTH_TIME":
        birth_time = None
        if not _is_unknown(text_clean):
            birth_time = _parse_time(text_clean)
            if birth_time is None:
                await wa.send_text(
                    phone,
                    "No pude leer esa hora. Usa formato HH:MM (24h), ej: 14:30, o escribe 'no se'.",
                )
                return
        await save_state(
            db, state, step="AWAITING_BIRTH_PLACE", data_update={"birth_time": birth_time}
        )
        await wa.send_text(
            phone,
            "En que ciudad y pais naciste? (Ej: Ciudad de Mexico, Mexico)\n\n"
            "Si no lo recuerdas escribe *'no se'*.",
        )
        return

    # ------------------------------------------------------------------
    # AWAITING_BIRTH_PLACE
    # ------------------------------------------------------------------
    if step == "AWAITING_BIRTH_PLACE":
        birth_place = None if _is_unknown(text_clean) else text_clean
        await save_state(
            db, state, step="AWAITING_GENDER", data_update={"birth_place": birth_place}
        )
        await wa.send_buttons(
            phone,
            "Cual es tu genero? (Ayuda a personalizar tu lectura)",
            buttons=[
                {"id": "genero_m", "title": "Masculino"},
                {"id": "genero_f", "title": "Femenino"},
                {"id": "genero_x", "title": "Prefiero no decir"},
            ],
        )
        return

    # ------------------------------------------------------------------
    # AWAITING_GENDER (via texto, en caso de que no use botones)
    # ------------------------------------------------------------------
    if step == "AWAITING_GENDER":
        g = text_clean.lower()
        if "masc" in g or g in {"m", "hombre"}:
            genero = "Masculino"
        elif "fem" in g or g in {"f", "mujer"}:
            genero = "Femenino"
        else:
            genero = "Prefiero no decir"
        await save_state(db, state, step="AWAITING_Q1", data_update={"birth_gender": genero})
        await wa.send_text(
            phone,
            "Perfecto. Ahora escribe tu *primera pregunta* para la tirada de Tarot.\n"
            "Puede ser cualquier pregunta sobre tu vida (amor, trabajo, salud...).\n\n"
            "Pregunta 1 de 5:",
        )
        return

    # ------------------------------------------------------------------
    # AWAITING_Q1 .. Q5
    # ------------------------------------------------------------------
    for qi in range(1, 6):
        if step == f"AWAITING_Q{qi}":
            if len(text_clean) < 5:
                await wa.send_text(phone, f"Escribe una pregunta un poco mas completa (pregunta {qi} de 5):")
                return
            datos = {f"q{qi}": text_clean}
            if qi < 5:
                siguiente_step = f"AWAITING_Q{qi + 1}"
                await save_state(db, state, step=siguiente_step, data_update=datos)
                await wa.send_text(
                    phone,
                    f"Pregunta {qi + 1} de 5:",
                )
            else:
                # Ultima pregunta -> ir a facturacion o generar directamente
                await save_state(db, state, step="AWAITING_INVOICE_MX", data_update=datos)
                await _preguntar_facturacion(db, state, phone)
            return

    # ------------------------------------------------------------------
    # AWAITING_INVOICE_MX (BUG2 - solo para +52)
    # ------------------------------------------------------------------
    if step == "AWAITING_INVOICE_MX":
        if _is_affirmative(text_clean) or "si" in text_clean.lower():
            await save_state(db, state, step="AWAITING_RFC")
            await wa.send_text(
                phone,
                "Escribe en un mensaje tus datos de facturacion en este formato:\n\n"
                "RFC: XXXX000000XXX\n"
                "Razon Social: Tu Empresa S.A.\n"
                "CP Fiscal: 06600\n"
                "Regimen Fiscal: 601\n"
                "Uso CFDI: G03",
            )
        else:
            # No requiere factura o extranjero: RFC XAXX/XEXX automatico
            rfc_generico = "XAXX010101000" if _es_mexico(phone) else "XEXX010101000"
            await save_state(
                db, state, step="GENERATING",
                data_update={"rfc": rfc_generico, "requiere_factura": False}
            )
            await wa.send_text(phone, "Generando tu carta astral, dame un momento...")
            await _generate_and_prepare_payment(db, state, phone)
        return

    # ------------------------------------------------------------------
    # AWAITING_RFC (BUG2 - usuario mexicano que si quiere factura)
    # ------------------------------------------------------------------
    if step == "AWAITING_RFC":
        rfc_data = _parse_rfc_data(text_clean)
        if not rfc_data:
            await wa.send_text(
                phone,
                "No pude leer tus datos. Asegurate de incluir RFC, Razon Social, CP Fiscal, "
                "Regimen Fiscal y Uso CFDI.\n\nIntenta de nuevo:",
            )
            return
        rfc_data["requiere_factura"] = True
        await save_state(db, state, step="GENERATING", data_update=rfc_data)
        await wa.send_text(phone, "Datos de facturacion guardados. Generando tu carta astral...")
        await _generate_and_prepare_payment(db, state, phone)
        return

    # ------------------------------------------------------------------
    # AWAITING_PAYMENT
    # ------------------------------------------------------------------
    if step == "AWAITING_PAYMENT":
        payment_url = (state.collected_data or {}).get("payment_url", "")
        msg = f"Tu carta astral ya esta lista. Completa el pago de ${PRICE_MXN} MXN para recibirla."
        if payment_url:
            msg += f"\n\n{payment_url}"
        await wa.send_text(phone, msg)
        return

    # ------------------------------------------------------------------
    # COMPLETED
    # ------------------------------------------------------------------
    if step == "COMPLETED":
        if _is_affirmative(text_clean) or "otra" in text_clean.lower():
            await save_state(db, state, step="MENU", data_update={})
            await handle_incoming_text(db, phone, "hola")
        else:
            await wa.send_buttons(
                phone,
                "Que deseas hacer?",
                buttons=[
                    {"id": "otra_carta_si", "title": "Otra carta astral"},
                    {"id": "otra_carta_no", "title": "Por ahora no"},
                ],
            )
        return

    # Fallback
    await save_state(db, state, step="MENU")
    await wa.send_text(phone, "Vamos a empezar de nuevo. Escribe 'hola'.")


# ============================================================================
# Punto de entrada: botones interactivos
# ============================================================================

async def handle_button_reply(db: AsyncSession, phone: str, button_id: str):
    """Traduce clicks de boton al flujo de texto."""
    mapping = {
        # Consentimiento
        "consent_si": "si",
        "consent_no": "no",
        # Servicio
        "quiero_carta": "si",
        "no_gracias": "no",
        # Genero
        "genero_m": "Masculino",
        "genero_f": "Femenino",
        "genero_x": "Prefiero no decir",
        # Factura
        "factura_si": "si",
        "factura_no": "no",
        # Post-completado
        "otra_carta_si": "si, quiero otra",
        "otra_carta_no": "no gracias",
        # Reenvio link
        "reenviar_link": "__reenviar_link__",
        # Cancelar compra
        "cancelar_compra": "cancelar",
    }

    if button_id == "reenviar_link":
        await _reenviar_link(phone)
        return

    text_equivalent = mapping.get(button_id, button_id)
    await handle_incoming_text(db, phone, text_equivalent)


# ============================================================================
# BUG2: logica de facturacion segun lada
# ============================================================================

async def _preguntar_facturacion(db: AsyncSession, state: ConversationState, phone: str):
    """
    BUG2: Si lada es +52 -> pregunta si requiere factura.
    Si es extranjero -> RFC XEXX automatico, va directo a generar.
    """
    if _es_mexico(phone):
        await wa.send_text(
            phone,
            "Por ley en Mexico toda compra se factura automaticamente.\n"
            "Requieres factura con tu RFC?",
        )
        await wa.send_buttons(
            phone,
            "Selecciona:",
            buttons=[
                {"id": "factura_si", "title": "Si, requiero factura"},
                {"id": "factura_no", "title": "No, publico en general"},
            ],
        )
        await save_state(db, state, step="AWAITING_INVOICE_MX")
    else:
        # Extranjero: sin pregunta, RFC XEXX automatico
        await save_state(
            db, state, step="GENERATING",
            data_update={"rfc": "XEXX010101000", "requiere_factura": False}
        )
        await wa.send_text(phone, "Generando tu carta astral, dame un momento...")
        await _generate_and_prepare_payment(db, state, phone)


# ============================================================================
# Generacion de carta + PDF + link de pago (BUG7: guard pdf_path)
# ============================================================================

async def _generate_and_prepare_payment(
    db: AsyncSession, state: ConversationState, phone: str
):
    data = state.collected_data or {}
    full_name = data.get("full_name")
    birth_date = data.get("birth_date")
    birth_time = data.get("birth_time")
    birth_place = data.get("birth_place") or "No especificado"
    birth_gender = data.get("birth_gender") or "No especificado"

    # Recopilar preguntas
    questions = [
        data.get(f"q{i}") for i in range(1, 6) if data.get(f"q{i}")
    ]

    # Anti-duplicate: si ya hay chart_id y payment_url no regenerar
    if data.get("chart_id") and data.get("payment_url"):
        await wa.send_text(
            phone,
            f"Tu carta ya esta lista. Realiza tu pago aqui:\n\n{data['payment_url']}\n\n"
            f"_{BRANDING}_",
        )
        return

    try:
        logger.info(f"[Flow] Generando carta para {phone} - {birth_date}")

        if birth_time:
            reading = await astro.generate_natal_chart_complete(
                birth_date, birth_time, birth_location=birth_place, questions=questions
            )
        else:
            reading = await astro.generate_natal_chart_simple(birth_date, questions=questions)

        if not reading:
            raise ValueError("Claude no devolvio lectura valida")

        # Forzar birth_place y gender en el reading antes de PDF
        reading["birth_place"] = birth_place
        reading["birth_gender"] = birth_gender

        # PDF.co: genera en memoria y sube a la nube — retorna URL publica
        logger.info(f"[Flow] Construyendo PDF para {full_name}")
        pdf_url, cover_used = await build_natal_chart_pdf(
            full_name=full_name,
            birth_date=birth_date,
            birth_time=birth_time,
            reading=reading,
        )

        if not pdf_url:
            raise ValueError("build_natal_chart_pdf retorno url vacia")

        logger.info(f"[Flow] PDF generado: {pdf_url}")

        # Guardar NatalChart en BD
        tarot_readings = reading.get("tarot_readings", [])
        chart = NatalChart(
            phone_number=phone,
            full_name=full_name,
            birth_date=birth_date,
            birth_time=birth_time,
            birth_place=birth_place,
            gender=birth_gender,
            zodiac_western=reading.get("zodiac_western"),
            zodiac_chinese=reading.get("zodiac_chinese"),
            zodiac_celtic=reading.get("zodiac_celtic"),
            zodiac_mayan=reading.get("zodiac_mayan"),
            zodiac_egyptian=reading.get("zodiac_egyptian"),
            interpretation_json=reading,
            cover_used=cover_used,
            pdf_path=pdf_url,   # URL de PDF.co, no ruta local
            pdf_ready=True,
            payment_status="pending",
            rfc=data.get("rfc"),
            requiere_factura=data.get("requiere_factura", False),
        )
        db.add(chart)
        await db.commit()
        await db.refresh(chart)

        # Link de pago Stripe
        payment_url = await create_payment_link(
            amount_mxn=PRICE_MXN,
            reference_id=chart.id,
            description=f"Carta Astral - {full_name}",
        )

        await save_state(
            db, state,
            step="AWAITING_PAYMENT",
            data_update={"chart_id": chart.id, "payment_url": payment_url},
        )

        # Mensaje de pago con branding (BUG6)
        primer_nombre = (full_name or "").split()[0] if full_name else "amig@"
        signo = reading.get("zodiac_western", "")
        await wa.send_text(
            phone,
            f"Tu carta astral esta lista, {primer_nombre}.\n\n"
            f"Tu signo occidental es *{signo}*.\n\n"
            f"Para recibir el PDF completo (5 paginas) realiza tu pago de "
            f"*${PRICE_MXN} MXN* aqui:\n\n"
            f"{payment_url}\n\n"
            f"En cuanto se confirme, te lo mando de inmediato.\n\n"
            f"_{BRANDING}_",
        )

    except Exception as e:
        logger.error(f"[Flow] Error generando carta: {e}", exc_info=True)
        await wa.send_text(
            phone,
            "Tuve un problema generando tu carta. "
            "Escribe 'hola' en un momento para intentar de nuevo.",
        )
        await save_state(db, state, step="MENU")


# ============================================================================
# Entrega del PDF tras confirmar pago (BUG7: guard pdf_path)
# ============================================================================

async def deliver_paid_chart(db: AsyncSession, chart: NatalChart):
    """Entrega el PDF al usuario via WhatsApp y marca como entregado."""
    logger.info(f"[Deliver] Iniciando entrega para chart {chart.id} - {chart.phone_number}")

    if not chart.pdf_path:
        logger.error(f"[Deliver] pdf_path es None para chart {chart.id}. No se puede entregar.")
        await wa.send_text(
            chart.phone_number,
            "Hubo un problema con tu carta. Por favor escribe 'hola' para regenerarla.",
        )
        return

    # Guard anti-doble-entrega
    if chart.delivered:
        logger.info(f"[Deliver] Chart {chart.id} ya entregado anteriormente, omitiendo.")
        return

    chart.payment_status = "paid"
    chart.delivered = True  # marcar ANTES de enviar para bloquear segunda llamada concurrente
    await db.commit()

    primer_nombre = (chart.full_name or "").split()[0] if chart.full_name else "amig@"

    # pdf_path es URL publica de PDF.co — send_document la envia por link directo
    await wa.send_document(
        chart.phone_number,
        file_path=chart.pdf_path,
        filename=f"CartaAstral_{primer_nombre}.pdf",
        caption=(
            f"Aqui esta tu Carta Astral, {primer_nombre}. Gracias por tu confianza.\n\n"
            f"_{BRANDING}_"
        ),
    )

    logger.info(f"[Deliver] PDF entregado para chart {chart.id}")

    result = await db.execute(
        select(ConversationState).where(
            ConversationState.phone_number == chart.phone_number
        )
    )
    state = result.scalar_one_or_none()
    if state:
        await save_state(db, state, step="COMPLETED")

    await wa.send_buttons(
        chart.phone_number,
        "Deseas hacer otra lectura?",
        buttons=[
            {"id": "otra_carta_si", "title": "Si, otra carta"},
            {"id": "otra_carta_no", "title": "Por ahora no"},
        ],
    )


# ============================================================================
# Helpers internos
# ============================================================================

async def _preguntar_servicio(phone: str):
    await wa.send_text(
        phone,
        f"Puedo generarte tu *Carta Astral* personalizada:\n\n"
        f"- Signo occidental, chino, celta, maya y egipcio\n"
        f"- Posiciones planetarias\n"
        f"- Tirada de Tarot Egipcio (5 preguntas)\n"
        f"- Horoscopo semanal\n\n"
        f"Todo por *${PRICE_MXN} MXN*. Pagas solo cuando tu lectura este lista.\n\n"
        f"Deseas que te la genere?\n\n"
        f"_{BRANDING}_",
    )
    await wa.send_buttons(
        phone,
        "Selecciona:",
        buttons=[
            {"id": "quiero_carta", "title": "Si, quiero mi carta"},
            {"id": "no_gracias", "title": "No, gracias"},
        ],
    )


async def _ask_full_name(phone: str):
    await wa.send_text(
        phone,
        "Perfecto. Para generar tu carta astral necesito:\n\n"
        "1. Nombre completo\n"
        "2. Fecha de nacimiento\n"
        "3. Hora de nacimiento (si la sabes)\n"
        "4. Ciudad de nacimiento\n"
        "5. Genero\n"
        "6. 5 preguntas para el Tarot\n\n"
        "Empecemos: cual es tu *nombre completo*?",
    )


async def _reenviar_link(phone: str):
    """Reenvio del link de pago si el usuario lo solicita."""
    # Esta funcion requiere DB pero handle_button_reply no la pasa.
    # Lo manejamos via handle_incoming_text con un mensaje especial.
    await wa.send_text(
        phone,
        "Escribe 'link de pago' para que te reenvie el link.",
    )


def _parse_rfc_data(text: str) -> dict | None:
    """
    Extrae RFC, razon social, CP, regimen fiscal y uso CFDI de un mensaje.
    Acepta formato:
        RFC: XXXX000000XXX
        Razon Social: Nombre
        CP Fiscal: 06600
        Regimen Fiscal: 601
        Uso CFDI: G03
    """
    result = {}
    lines = text.strip().split("\n")
    for line in lines:
        if ":" in line:
            clave, _, valor = line.partition(":")
            clave = clave.strip().lower()
            valor = valor.strip()
            if "rfc" in clave:
                rfc = re.sub(r"\s", "", valor).upper()
                # Validacion basica: 12 o 13 caracteres alfanumericos
                if re.match(r"^[A-Z&]{3,4}[0-9]{6}[A-Z0-9]{3}$", rfc):
                    result["rfc"] = rfc
                else:
                    return None  # RFC invalido
            elif "razon" in clave or "social" in clave:
                result["razon_social"] = valor
            elif "cp" in clave or "postal" in clave:
                result["cp_fiscal"] = valor
            elif "regimen" in clave:
                result["regimen_fiscal"] = valor
            elif "uso" in clave or "cfdi" in clave:
                result["uso_cfdi"] = valor

    # Minimo necesario: RFC
    if "rfc" not in result:
        return None
    return result


def _is_affirmative(text: str) -> bool:
    return text.lower().strip() in {"si", "si!", "yes", "claro", "quiero", "ok", "va", "dale", "s"}


def _is_unknown(text: str) -> bool:
    t = text.lower()
    return "no s" in t or "no se" in t or "no se" in t or "desconoc" in t


def _parse_date(text: str):
    """Acepta DD/MM/AAAA o DD-MM-AAAA y retorna 'AAAA-MM-DD'."""
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
    """Acepta HH:MM y retorna 'HH:MM'."""
    text = text.strip()
    try:
        t = datetime.strptime(text, "%H:%M")
        return t.strftime("%H:%M")
    except ValueError:
        return None
