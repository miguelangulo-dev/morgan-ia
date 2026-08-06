from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, JSONResponse
import os
import logging

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from models import Base
import conversation_flow as flow
from payment import handle_stripe_webhook

# ============================================================================
# Configuración
# ============================================================================

VERIFY_TOKEN = "morgania2026"
DATABASE_URL = os.getenv("DATABASE_URL", "")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Morgan-ia")

engine = create_async_engine(DATABASE_URL, echo=False) if DATABASE_URL else None
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False) if engine else None


@app.on_event("startup")
async def on_startup():
    if engine:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("✅ Tablas verificadas/creadas")
    else:
        logger.warning("⚠️ DATABASE_URL no configurada")


def get_session() -> AsyncSession:
    return async_session()


# ============================================================================
# WEBHOOK WHATSAPP - Verificación (Meta)
# ============================================================================

@app.get("/webhook/whatsapp")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("✅ Webhook verificado con Meta")
        return PlainTextResponse(challenge)

    logger.warning("❌ Webhook verification fallida")
    return PlainTextResponse("Forbidden", status_code=403)


# ============================================================================
# WEBHOOK WHATSAPP - Mensajes entrantes
# ============================================================================

@app.post("/webhook/whatsapp")
async def handle_webhook(request: Request):
    data = await request.json()

    try:
        entry = data.get("entry", [])
        if not entry:
            return JSONResponse({"status": "ok"})

        changes = entry[0].get("changes", [])
        if not changes:
            return JSONResponse({"status": "ok"})

        value = changes[0].get("value", {})
        messages = value.get("messages", [])

        if not messages:
            # notificación de estado (read/delivered), no un mensaje nuevo
            return JSONResponse({"status": "ok"})

        message = messages[0]
        from_phone = message.get("from")
        message_type = message.get("type")

        logger.info(f"📱 Mensaje de {from_phone} | tipo: {message_type}")

        async with get_session() as db:
            if message_type == "text":
                text_body = message.get("text", {}).get("body", "")
                await flow.handle_incoming_text(db, from_phone, text_body)

            elif message_type == "interactive":
                interactive = message.get("interactive", {})
                button_reply = interactive.get("button_reply", {})
                if button_reply:
                    await flow.handle_button_reply(db, from_phone, button_reply.get("id", ""))

            elif message_type == "button":
                payload = message.get("button", {}).get("payload", "")
                await flow.handle_button_reply(db, from_phone, payload)

            else:
                # audio, imagen, etc. -> aún no soportado en este flujo
                logger.info(f"ℹ️ Tipo de mensaje no manejado todavía: {message_type}")

        return JSONResponse({"status": "ok"})

    except Exception as e:
        logger.error(f"❌ Error procesando webhook: {str(e)}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)


# ============================================================================
# WEBHOOK STRIPE - Confirmación de pago (dispara entrega del PDF)
# ============================================================================

@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    async with get_session() as db:
        result, status_code = await handle_stripe_webhook(payload, sig_header, db)

    return JSONResponse(result, status_code=status_code)


# ============================================================================
# Health check
# ============================================================================

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "morgan-ia"}
