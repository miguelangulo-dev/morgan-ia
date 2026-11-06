"""
billing_service.py - Integracion SW Sapien para CFDI v4.0 (Mexico)

BUG 2: Facturacion diferenciada por lada
- +52 (Mexico): pregunta si requiere factura con RFC, Razon Social, CP, Regimen, Uso CFDI
- Extranjero: auto-CFDI con XEXX010101000, sin preguntas
- Sin factura (Mexico): RFC generico XAXX010101000

Endpoint SW Sapien: POST /v4/cfdi
Docs: https://developers.sw.com.mx/knowledge-base/emitir-cfdi-v4/
"""

import httpx
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

SW_TOKEN = os.getenv("SW_SAPIEN_TOKEN", "")
SW_BASE_URL = os.getenv("SW_SAPIEN_URL", "https://services.sw.com.mx")
SW_RFC_EMISOR = os.getenv("SW_RFC_EMISOR", "SINX000101000")  # RFC de Sincronía Tech
SW_NOMBRE_EMISOR = os.getenv("SW_NOMBRE_EMISOR", "Sincronía Tech Developers S.A.S.")
SW_REGIMEN_EMISOR = os.getenv("SW_REGIMEN_EMISOR", "601")  # General de Ley Personas Morales


# ============================================================================
# Funcion principal: emitir CFDI v4
# ============================================================================

async def emitir_cfdi(
    rfc_receptor: str,
    nombre_receptor: str,
    cp_fiscal: str,
    regimen_fiscal: str,
    uso_cfdi: str,
    importe: float,
    descripcion: str,
    chart_id: str,
) -> dict:
    """
    Emite un CFDI v4.0 via SW Sapien.

    Args:
        rfc_receptor:    RFC del receptor (XAXX010101000 o XEXX010101000 para genericos)
        nombre_receptor: Razon social del receptor
        cp_fiscal:       Codigo postal fiscal del receptor
        regimen_fiscal:  Clave de regimen fiscal del receptor (ej: "616" Resico)
        uso_cfdi:        Clave de uso del CFDI (ej: "G03" - Gastos en general)
        importe:         Monto sin IVA (en MXN)
        descripcion:     Descripcion del concepto
        chart_id:        ID de referencia para trazabilidad

    Returns:
        dict: {
            "success": bool,
            "uuid": str,          # UUID del timbre fiscal
            "xml_url": str,       # URL del XML timbrado
            "pdf_url": str,       # URL del PDF del CFDI
            "cadena_original": str,
            "error": str          # solo si success=False
        }
    """
    if not SW_TOKEN:
        logger.warning("[Billing] SW_SAPIEN_TOKEN no configurado. Retornando stub.")
        return _stub_cfdi(chart_id, rfc_receptor)

    fecha_hora = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")

    # Calculo de impuestos (IVA 16%)
    subtotal = round(importe / 1.16, 2)
    iva = round(importe - subtotal, 2)

    payload = {
        "Version": "4.0",
        "Folio": chart_id[:8].upper(),
        "Fecha": fecha_hora,
        "FormaPago": "03",  # Transferencia electronica de fondos
        "NoCertificado": "",  # SW lo llena
        "SubTotal": str(subtotal),
        "Moneda": "MXN",
        "Total": str(round(importe, 2)),
        "TipoDeComprobante": "I",  # Ingreso
        "Exportacion": "01",        # No aplica
        "MetodoPago": "PUE",        # Pago en una sola exhibicion
        "LugarExpedicion": os.getenv("SW_CP_EMISOR", "38000"),  # CP de Celaya, Gto
        "Emisor": {
            "Rfc": SW_RFC_EMISOR,
            "Nombre": SW_NOMBRE_EMISOR,
            "RegimenFiscal": SW_REGIMEN_EMISOR,
        },
        "Receptor": {
            "Rfc": rfc_receptor.upper(),
            "Nombre": nombre_receptor or "PUBLICO EN GENERAL",
            "DomicilioFiscalReceptor": cp_fiscal or "00000",
            "RegimenFiscalReceptor": regimen_fiscal or "616",
            "UsoCFDI": uso_cfdi or "G03",
        },
        "Conceptos": [
            {
                "ClaveProdServ": "84111506",  # Servicios de astrologia
                "Cantidad": "1",
                "ClaveUnidad": "E48",        # Unidad de servicio
                "Descripcion": descripcion,
                "ValorUnitario": str(subtotal),
                "Importe": str(subtotal),
                "ObjetoImp": "02",           # Si objeto de impuesto
                "Impuestos": {
                    "Traslados": [
                        {
                            "Base": str(subtotal),
                            "Impuesto": "002",        # IVA
                            "TipoFactor": "Tasa",
                            "TasaOCuota": "0.160000",
                            "Importe": str(iva),
                        }
                    ]
                },
            }
        ],
        "Impuestos": {
            "TotalImpuestosTrasladados": str(iva),
            "Traslados": [
                {
                    "Base": str(subtotal),
                    "Impuesto": "002",
                    "TipoFactor": "Tasa",
                    "TasaOCuota": "0.160000",
                    "Importe": str(iva),
                }
            ],
        },
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{SW_BASE_URL}/v4/cfdi",
                json=payload,
                headers={
                    "Authorization": f"Bearer {SW_TOKEN}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()

        if data.get("status") == "success":
            cfdi_data = data.get("data", {})
            logger.info(f"[Billing] CFDI emitido para {chart_id}: {cfdi_data.get('uuid')}")
            return {
                "success": True,
                "uuid": cfdi_data.get("uuid"),
                "xml_url": cfdi_data.get("xmlUrl"),
                "pdf_url": cfdi_data.get("pdfUrl"),
                "cadena_original": cfdi_data.get("cadenaOriginalSAT", ""),
                "error": None,
            }
        else:
            msg = data.get("message", "Error desconocido SW Sapien")
            logger.error(f"[Billing] Error SW Sapien: {msg}")
            return {"success": False, "uuid": None, "error": msg}

    except httpx.HTTPStatusError as e:
        logger.error(f"[Billing] HTTP {e.response.status_code} desde SW Sapien: {e}")
        return {"success": False, "uuid": None, "error": f"HTTP {e.response.status_code}"}
    except Exception as e:
        logger.error(f"[Billing] Error inesperado en SW Sapien: {e}", exc_info=True)
        return {"success": False, "uuid": None, "error": str(e)}


# ============================================================================
# Stub para desarrollo/testing (cuando no hay token SW)
# ============================================================================

def _stub_cfdi(chart_id: str, rfc: str) -> dict:
    """Retorna un CFDI falso para desarrollo. No enviar a SAT."""
    import uuid
    fake_uuid = str(uuid.uuid4()).upper()
    logger.info(f"[Billing][STUB] CFDI fake generado para {chart_id} - RFC: {rfc} - UUID: {fake_uuid}")
    return {
        "success": True,
        "uuid": fake_uuid,
        "xml_url": f"https://stub.sincron-ia.com.mx/cfdi/{fake_uuid}.xml",
        "pdf_url": f"https://stub.sincron-ia.com.mx/cfdi/{fake_uuid}.pdf",
        "cadena_original": f"||4.0|{fake_uuid}||",
        "error": None,
        "_stub": True,  # Marcador para detectar que es un stub
    }


# ============================================================================
# Helper: generar RFC generico segun tipo de receptor
# ============================================================================

def rfc_generico_mexico() -> str:
    """RFC para publico en general Mexico."""
    return "XAXX010101000"


def rfc_generico_extranjero() -> str:
    """RFC para operaciones con extranjeros."""
    return "XEXX010101000"
