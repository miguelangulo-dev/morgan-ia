"""
Maneja el cobro antes de la entrega del PDF:

1. create_payment_link()  -> se llama al terminar de generar la carta (paso 5)
2. handle_stripe_webhook() -> Stripe nos avisa cuando el pago se completó (paso 6),
   y desde ahí se dispara la entrega del PDF.
"""

import os
import stripe
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import NatalChart

logger = logging.getLogger(__name__)

stripe.api_key = os.getenv("STRIPE_API_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
DOMAIN = os.getenv("PUBLIC_DOMAIN", "https://morgan-ia-production.up.railway.app")


async def create_payment_link(amount_mxn: int, reference_id: str, description: str) -> str:
    """
    Crea una sesión de Stripe Checkout para una carta astral específica.
    reference_id = el id del NatalChart, para poder identificarlo cuando llegue el webhook.
    """
    session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "mxn",
                "product_data": {"name": description},
                "unit_amount": amount_mxn * 100,  # Stripe usa centavos
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url=f"{DOMAIN}/pago-exitoso",
        cancel_url=f"{DOMAIN}/pago-cancelado",
        metadata={"natal_chart_id": reference_id},
    )
    return session.url


async def handle_stripe_webhook(payload: bytes, sig_header: str, db: AsyncSession):
    """
    Se llama desde la ruta POST /webhook/stripe en main.py.
    Verifica la firma, y si el pago se completó, dispara la entrega del PDF.
    """
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        logger.error(f"❌ Webhook de Stripe inválido: {str(e)}")
        return {"error": "invalid signature"}, 400

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        chart_id = session.get("metadata", {}).get("natal_chart_id")

        if not chart_id:
            logger.warning("⚠️ Webhook de Stripe sin natal_chart_id en metadata")
            return {"status": "ignored"}, 200

        result = await db.execute(select(NatalChart).where(NatalChart.id == chart_id))
        chart = result.scalar_one_or_none()

        if not chart:
            logger.error(f"❌ No se encontró NatalChart {chart_id}")
            return {"status": "not_found"}, 200

        if chart.payment_status == "paid":
            # Ya se procesó antes (Stripe puede reenviar el mismo evento)
            return {"status": "already_processed"}, 200

        # Importación diferida para evitar import circular con conversation_flow
        from conversation_flow import deliver_paid_chart
        await deliver_paid_chart(db, chart)
        logger.info(f"✅ Pago confirmado y PDF entregado para chart {chart_id}")

    return {"status": "ok"}, 200
