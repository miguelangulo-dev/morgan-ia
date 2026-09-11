"""
payment.py - FINAL REVISADO - Compatible con normativa original + fix Todo listo

Normativa original que se debe conservar:
- STRIPE_API_KEY (o STRIPE_SECRET_KEY)
- STRIPE_WEBHOOK_SECRET
- PUBLIC_DOMAIN / SUCCESS_URL / CANCEL_URL
- handle_stripe_webhook() que lee checkout.session.completed y busca NatalChart por metadata
- metadata key original: natal_chart_id
- Evitar import circular (import diferido de deliver_paid_chart)

Problema original:
- checkout.Session.create sin expires_at -> Stripe expira en 24h -> captura "Todo listo"

Fix aplicado (sin romper lo demas):
- Intenta crear PaymentLink persistente (buy.stripe.com) que NO expira
- Si falla (o no tienes permiso), fallback a Checkout Session con expires_at = 30 dias
- Guarda metadata con AMBAS claves: natal_chart_id (legacy) y chart_id (nuevo) para que webhook viejo y nuevo funcionen
- Lee ambas variables de entorno STRIPE_API_KEY / STRIPE_SECRET_KEY
- Conserva handle_stripe_webhook original
- Agrega regenerador para boton Ya pague / Reenviar
"""

import os
import stripe
import logging
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models import NatalChart

logger = logging.getLogger(__name__)

# Compatibilidad env: Railway tenias STRIPE_API_KEY, el fix nuevo usaba STRIPE_SECRET_KEY
stripe.api_key = os.getenv("STRIPE_API_KEY", "") or os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
# Compatibilidad dominio
DOMAIN = os.getenv("PUBLIC_DOMAIN", "https://morgan-ia-production.up.railway.app")
SUCCESS_URL = os.getenv("SUCCESS_URL", f"{DOMAIN}/pago-exitoso")
CANCEL_URL = os.getenv("CANCEL_URL", f"{DOMAIN}/pago-cancelado")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "")  # opcional

async def create_payment_link(amount_mxn: int, reference_id: str, description: str) -> str:
    """
    Crea link de pago persistente (fix Todo listo) sin romper webhook
    reference_id = NatalChart.id
    """
    # Metadata compatible con webhook viejo y nuevo
    meta = {"natal_chart_id": str(reference_id), "chart_id": str(reference_id)}

    # 1) Intento principal: PaymentLink (no expira) - si tu cuenta Stripe lo permite
    try:
        if STRIPE_PRICE_ID:
            link = stripe.PaymentLink.create(
                line_items=[{"price": STRIPE_PRICE_ID, "quantity": 1}],
                metadata=meta,
                after_completion={"type": "redirect", "redirect": {"url": SUCCESS_URL}},
            )
        else:
            link = stripe.PaymentLink.create(
                line_items=[{
                    "price_data": {
                        "currency": "mxn",
                        "product_data": {"name": description},
                        "unit_amount": amount_mxn * 100,
                    },
                    "quantity": 1,
                }],
                metadata=meta,
                after_completion={"type": "redirect", "redirect": {"url": f"{SUCCESS_URL}?chart_id={reference_id}"}},
            )
        logger.info(f"PaymentLink persistente creado: {link.url} chart {reference_id}")
        return link.url

    except Exception as e:
        logger.warning(f"PaymentLink no disponible ({e}), usando Checkout Session 30d: {str(e)[:200]}")

    # 2) Fallback: Checkout Session con expiracion larga (30 dias) - fix del bug original
    try:
        expires_at = int((datetime.utcnow() + timedelta(days=30)).timestamp())
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "mxn",
                    "product_data": {"name": description},
                    "unit_amount": amount_mxn * 100,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{SUCCESS_URL}?chart_id={reference_id}&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=CANCEL_URL,
            metadata=meta,
            expires_at=expires_at,
        )
        logger.info(f"Checkout Session 30d creada: {session.url} chart {reference_id}")
        return session.url
    except Exception as e2:
        logger.error(f"Error creando session fallback: {e2}")
        raise

async def regenerate_payment_link_for_chart(chart_id: int, full_name: str, amount_mxn: int = 49) -> str:
    """Para boton Ya pague / Reenviar - genera link nuevo que no expira"""
    return await create_payment_link(amount_mxn, str(chart_id), f"Carta Astral Completa - {full_name} - Reenvio")

def is_link_expired_error(msg: str) -> bool:
    kws = ["expired", "Todo listo", "agoto el tiempo", "completaste el pago"]
    return any(k.lower() in msg.lower() for k in kws)

# === WEBHOOK ORIGINAL - SE CONSERVA INTEGRO (solo se hace compatible con ambas metadata keys) ===
async def handle_stripe_webhook(payload: bytes, sig_header: str, db: AsyncSession):
    """
    Se llama desde POST /webhook/stripe en main.py
    Verifica firma y entrega PDF si pago completado
    """
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        logger.error(f"❌ Webhook de Stripe inválido: {str(e)}")
        return {"error": "invalid signature"}, 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        meta = session.get("metadata", {})
        # Compatibilidad: soporta natal_chart_id (viejo) y chart_id (nuevo)
        chart_id = meta.get("natal_chart_id") or meta.get("chart_id")

        if not chart_id:
            logger.warning("⚠️ Webhook sin natal_chart_id ni chart_id en metadata")
            return {"status": "ignored"}, 200

        result = await db.execute(select(NatalChart).where(NatalChart.id == chart_id))
        chart = result.scalar_one_or_none()

        if not chart:
            logger.error(f"❌ No se encontró NatalChart {chart_id}")
            return {"status": "not_found"}, 200

        if chart.payment_status == "paid":
            return {"status": "already_processed"}, 200

        from conversation_flow import deliver_paid_chart
        await deliver_paid_chart(db, chart)
        logger.info(f"✅ Pago confirmado y PDF entregado para chart {chart_id}")

    return {"status": "ok"}, 200
