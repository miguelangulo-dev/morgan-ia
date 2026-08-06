from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse, JSONResponse
import os
import json
import logging
from datetime import datetime
import httpx
import asyncpg
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# Configuración
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")
WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
VERIFY_TOKEN = "morgania2026"
CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
DATABASE_URL = os.getenv("DATABASE_URL", "")

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(title="Morgan-ia")

# Base de datos
if DATABASE_URL:
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
else:
    engine = None
    async_session = None

# ============================================================================
# WEBHOOK VERIFICATION
# ============================================================================

@app.get("/webhook/whatsapp")
async def verify_webhook(request: Request):
    """Verifica el webhook con Meta"""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    
    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("✅ Webhook verificado con Meta")
        return PlainTextResponse(challenge)
    
    logger.warning("❌ Webhook verification fallida")
    return PlainTextResponse("Forbidden", status_code=403)

# ============================================================================
# WEBHOOK MESSAGES
# ============================================================================

@app.post("/webhook/whatsapp")
async def handle_webhook(request: Request):
    """Recibe y procesa mensajes de WhatsApp"""
    data = await request.json()
    
    try:
        # Validar estructura
        if "entry" not in data or not data["entry"]:
            return JSONResponse({"status": "ok"})
        
        changes = data["entry"][0].get("changes", [])
        if not changes:
            return JSONResponse({"status": "ok"})
        
        # Extraer mensaje
        value = changes[0].get("value", {})
        messages = value.get("messages", [])
        
        if not messages:
            # Puede ser notificación de estado (read, delivered)
            return JSONResponse({"status": "ok"})
        
        message = messages[0]
        from_phone = message.get("from")
        message_type = message.get("type")
        timestamp = message.get("timestamp")
        
        logger.info(f"📱 Mensaje recibido: {from_phone} | Tipo: {message_type} | Timestamp: {timestamp}")
        
        # Procesar por tipo de mensaje
        if message_type == "text":
            text_body = message.get("text", {}).get("body", "")
            await process_text_message(from_phone, text_body)
        
        elif message_type == "button":
            # Respuesta de botones
            button_payload = message.get("button", {}).get("payload", "")
            await process_button_message(from_phone, button_payload)
        
        elif message_type == "interactive":
            # Mensajes interactivos (lista, botones con ID)
            interactive = message.get("interactive", {})
            button_reply = interactive.get("button_reply", {})
            list_reply = interactive.get("list_reply", {})
            
            if button_reply:
                await process_button_message(from_phone, button_reply.get("id", ""))
            elif list_reply:
                await process_list_selection(from_phone, list_reply.get("id", ""))
        
        return JSONResponse({"status": "ok"}, status_code=200)
    
    except Exception as e:
        logger.error(f"❌ Error procesando webhook: {str(e)}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

# ============================================================================
# MESSAGE PROCESSING
# ============================================================================

async def process_text_message(from_phone: str, text: str):
    """Procesa mensajes de texto"""
    logger.info(f"📝 Procesando texto: {text}")
    
    # Aquí irá la lógica de Claude y enrutamiento
    # Por ahora, respuesta simple
    
    if "hola" in text.lower() or "hi" in text.lower():
        await send_initial_menu(from_phone)
    else:
        await send_text_message(from_phone, "Escribe 'hola' para comenzar")

async def process_button_message(from_phone: str, payload: str):
    """Procesa respuestas de botones"""
    logger.info(f"🔘 Button payload: {payload}")
    
    # Ejemplos de payloads:
    # "carta_natal_completa", "carta_natal_simple"
    # "tarot", "afinidad_zodiacal"
    
    if payload == "carta_natal_completa":
        await send_text_message(from_phone, "Para una carta natal completa necesito:\n1. Tu fecha de nacimiento\n2. Hora exacta\n3. Lugar de nacimiento\n\n¿Cuál es tu fecha? (Ej: 15/03/1990)")
    
    elif payload == "carta_natal_simple":
        await send_text_message(from_phone, "Necesito tu fecha de nacimiento (Ej: 15/03/1990)")
    
    elif payload == "tarot":
        await send_text_message(from_phone, "Te haré una tirada de tarot con 5 preguntas de sí o no.\n\n¿Cuál es tu primera pregunta?")
    
    elif payload == "afinidad_zodiacal":
        await send_text_message(from_phone, "¿Cuál es tu signo zodiacal?\nEscribe: Aries, Tauro, Géminis, etc.")

async def process_list_selection(from_phone: str, selection_id: str):
    """Procesa selecciones de lista"""
    logger.info(f"📋 List selection: {selection_id}")

async def send_initial_menu(from_phone: str):
    """Envía menú inicial con opciones"""
    text = "🌙 Bienvenido a Morgan-ia 🌙\n\nElige un servicio:"
    
    # Aquí irían botones interactivos
    await send_text_message(from_phone, text)
    await send_text_message(from_phone, "1️⃣ Carta Natal (elige: Completa o Simple)\n2️⃣ Afinidad Zodiacal\n3️⃣ Tirada de Tarot (5 preguntas Sí/No)")

# ============================================================================
# WHATSAPP API CALLS
# ============================================================================

async def send_text_message(to_phone: str, text: str):
    """Envía mensaje de texto por WhatsApp"""
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID:
        logger.error("❌ Credenciales de WhatsApp no configuradas")
        return
    
    url = f"https://graph.instagram.com/v18.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone,
        "type": "text",
        "text": {"preview_url": False, "body": text}
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            logger.info(f"✅ Mensaje enviado a {to_phone}")
        else:
            logger.error(f"❌ Error enviando mensaje: {response.text}")

async def send_media_message(to_phone: str, media_url: str, media_type: str = "document", caption: str = None):
    """Envía documento (PDF) o imagen"""
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_ID:
        logger.error("❌ Credenciales de WhatsApp no configuradas")
        return
    
    url = f"https://graph.instagram.com/v18.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone,
        "type": media_type,
        media_type: {
            "link": media_url
        }
    }
    
    if caption and media_type == "document":
        payload[media_type]["caption"] = caption
    
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            logger.info(f"✅ Media enviado a {to_phone}")
        else:
            logger.error(f"❌ Error enviando media: {response.text}")

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "morgan-ia"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
