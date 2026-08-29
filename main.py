from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, JSONResponse, HTMLResponse
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
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

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
                logger.info(f"ℹ️ Tipo de mensaje no manejado todavía: {message_type}")
        
        return JSONResponse({"status": "ok"})
    
    except Exception as e:
        logger.error(f"❌ Error webhook: {str(e)}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

# ============================================================================
# WEBHOOK STRIPE - Confirmación de pago
# ============================================================================

@app.post("/webhook/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    async with get_session() as db:
        result, status_code = await handle_stripe_webhook(payload, sig_header, db)
    return JSONResponse(result, status_code=status_code)

# ============================================================================
# PÁGINAS DE PAGO (Stripe redirects)
# ============================================================================

@app.get("/pago-exitoso")
async def pago_exitoso(request: Request):
    from sqlalchemy import select
    from models import NatalChart
    
    chart_id = request.query_params.get("chart_id")
    session_id = request.query_params.get("session_id")
    logger.info(f"Usuario regreso de Stripe - chart_id={chart_id} session_id={session_id}")
    
    if not chart_id:
        return HTMLResponse("""
        <html><body style="background:#0a0a0a;color:#FFD700;text-align:center;padding:50px;font-family:sans-serif">
        <h1>Pago Confirmado</h1>
        <p>Tu destino esta sellado. Regresa a WhatsApp, tu PDF ya se esta entregando.</p>
        </body></html>
        """)
    
    async with get_session() as db:
        result = await db.execute(select(NatalChart).where(NatalChart.id == chart_id))
        chart = result.scalar_one_or_none()
        
        if not chart:
            logger.error(f"Chart {chart_id} no encontrado en pago-exitoso")
            return HTMLResponse("<h1>Pago recibido, pero no encontre tu carta. Escribe hola en WhatsApp</h1>")
        
        if chart.payment_status != "paid":
            chart.payment_status = "paid"
            await db.commit()
            try:
                await flow.deliver_paid_chart(db, chart)
                logger.info(f"✅ PDF entregado desde /pago-exitoso para chart {chart_id}")
            except Exception as e:
                logger.error(f"❌ Error entregando PDF desde pago-exitoso: {e}", exc_info=True)
    
    return HTMLResponse(f"""
    <html>
    <head><meta name="viewport" content="width=device-width, initial-scale=1"></head>
    <body style="background:#0a0a0a;color:#fff;text-align:center;padding:40px;font-family:sans-serif">
        <div style="border:1px solid #FFD700;border-radius:16px;padding:30px;max-width:500px;margin:auto">
            <h1 style="color:#FFD700">✨ Pago Confirmado ✨</h1>
            <p style="font-size:18px">Tu destino esta sellado.</p>
            <p>Regresa a WhatsApp, tu PDF ya se esta entregando.</p>
            <p style="margin-top:20px;color:#888;font-size:12px">Chart: {chart_id}</p>
        </div>
    </body>
    </html>
    """)

@app.get("/pago-cancelado")
async def pago_cancelado(request: Request):
    return HTMLResponse("""
    <html><body style="background:#0a0a0a;color:#fff;text-align:center;padding:50px;font-family:sans-serif">
    <h1 style="color:#FFD700">Pago Cancelado</h1>
    <p>Escribe 'hola' en WhatsApp para generar un nuevo link que no expira.</p>
    </body></html>
    """)

# ============================================================================
# Cleanup automático de inactivos
# ============================================================================

from datetime import datetime, timedelta
from sqlalchemy import select, delete
from apscheduler.schedulers.asyncio import AsyncIOScheduler

async def cleanup_inactive():
    async with get_session() as db:
        now = datetime.utcnow()
        limit_24h = now - timedelta(hours=24)
        limit_48h = now - timedelta(hours=48)
        limit_7d = now - timedelta(days=7)
        
        await db.execute(delete(ConversationState).where(
            ConversationState.updated_at < limit_24h,
            ConversationState.current_step.notin_(["AWAITING_PAYMENT", "COMPLETED"])
        ))
        
        result = await db.execute(select(NatalChart).where(
            NatalChart.created_at < limit_48h,
            NatalChart.payment_status == "pending"
        ))
        for chart in result.scalars().all():
            try:
                if chart.pdf_path and os.path.exists(chart.pdf_path):
                    os.remove(chart.pdf_path)
            except:
                pass
        
        await db.execute(delete(NatalChart).where(
            NatalChart.created_at < limit_48h,
            NatalChart.payment_status == "pending"
        ))
        
        await db.execute(delete(ConversationState).where(
            ConversationState.updated_at < limit_48h,
            ConversationState.current_step == "AWAITING_PAYMENT"
        ))
        
        await db.execute(delete(ConversationState).where(
            ConversationState.updated_at < limit_7d,
            ConversationState.current_step == "COMPLETED"
        ))
        
        await db.commit()
        logger.info(f"🧹 Cleanup ejecutado: {now}")

scheduler = AsyncIOScheduler()
scheduler.add_job(cleanup_inactive, 'interval', hours=1)
scheduler.start()

# ============================================================================
# Health check
# ============================================================================

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "morgan-ia"}

@app.get("/")
async def root():
    return {"status": "ok", "service": "morgan-ia", "version": "fix-pago-exitoso-final"}
    
