"""
facturacion.py - CFDI 4.0 para Morgan-IA (PAC: EdifactMx)

PARTE A (lista): arma los datos del CFDI y los guarda en la tabla `invoices`.
PARTE B (pendiente): timbrar() se conecta cuando Edifact entregue su
documentacion de API y las credenciales del sandbox. Mientras, las facturas
quedan con status 'pendiente_pac' y no se pierde ninguna.

Variables de entorno (Railway):
  EMISOR_RFC, EMISOR_NOMBRE (razon social SIN "S.A.S."), EMISOR_REGIMEN=601, EMISOR_CP=38028
  SAT_CLAVE_PROD=01010101 (temporal), SAT_CLAVE_UNIDAD=E48, IVA_TASA=0.16
  EDIFACT_URL, EDIFACT_USER, EDIFACT_PASSWORD           (parte B)
  CSD_CER_B64, CSD_KEY_B64, CSD_PASSWORD (solo si Edifact pide que sellemos nosotros)
"""
import os, re, logging
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import select

from models import Invoice

logger = logging.getLogger(__name__)

EMISOR = {
    "Rfc": os.getenv("EMISOR_RFC", ""),
    "Nombre": os.getenv("EMISOR_NOMBRE", "SINCRONIA TECH DEVELOPERS"),
    "RegimenFiscal": os.getenv("EMISOR_REGIMEN", "601"),
}
LUGAR_EXPEDICION = os.getenv("EMISOR_CP", "38028")
CLAVE_PROD = os.getenv("SAT_CLAVE_PROD", "01010101")
CLAVE_UNIDAD = os.getenv("SAT_CLAVE_UNIDAD", "E48")
IVA_TASA = Decimal(os.getenv("IVA_TASA", "0.16"))
DESCRIPCION = "Lectura de Carta Astral y Tarot (PDF digital)"

RFC_EXTRANJERO = "XEXX010101000"

# Regimenes que mas usan personas y empresas (el usuario escribe el numero)
REGIMENES = {
    "601": "General de Ley Personas Morales",
    "603": "Personas Morales con Fines no Lucrativos",
    "605": "Sueldos y Salarios",
    "606": "Arrendamiento",
    "612": "Actividades Empresariales y Profesionales",
    "616": "Sin obligaciones fiscales",
    "621": "Incorporacion Fiscal",
    "625": "Plataformas Tecnologicas",
    "626": "Regimen Simplificado de Confianza (RESICO)",
}
# Estos regimenes no aceptan G03 (Gastos en general); el SAT solo deja S01
_SOLO_S01 = {"605", "611", "614", "615", "616"}

# Lada -> pais (catalogo c_Pais del SAT). Se busca el prefijo mas largo.
PAIS_POR_LADA = {
    "1": "USA", "7": "RUS", "20": "EGY", "27": "ZAF", "30": "GRC", "31": "NLD", "32": "BEL",
    "33": "FRA", "34": "ESP", "36": "HUN", "39": "ITA", "40": "ROU", "41": "CHE", "43": "AUT",
    "44": "GBR", "45": "DNK", "46": "SWE", "47": "NOR", "48": "POL", "49": "DEU", "51": "PER",
    "53": "CUB", "54": "ARG", "55": "BRA", "56": "CHL", "57": "COL", "58": "VEN", "60": "MYS",
    "61": "AUS", "62": "IDN", "63": "PHL", "64": "NZL", "65": "SGP", "66": "THA", "81": "JPN",
    "82": "KOR", "84": "VNM", "86": "CHN", "90": "TUR", "91": "IND", "351": "PRT", "353": "IRL",
    "358": "FIN", "420": "CZE", "502": "GTM", "503": "SLV", "504": "HND", "505": "NIC",
    "506": "CRI", "507": "PAN", "509": "HTI", "591": "BOL", "593": "ECU", "595": "PRY",
    "598": "URY", "972": "ISR", "971": "ARE", "966": "SAU",
    "1787": "PRI", "1809": "DOM", "1829": "DOM", "1849": "DOM",
}

# ---------- Validaciones ----------
_RFC_RE = re.compile(r"^[A-ZÑ&]{3,4}\d{6}[A-Z\d]{3}$")

def es_mexico(phone: str) -> bool:
    return re.sub(r"\D", "", phone or "").startswith("52")

def pais_por_telefono(phone: str):
    d = re.sub(r"\D", "", phone or "")
    for n in (4, 3, 2, 1):
        if d[:n] in PAIS_POR_LADA:
            return PAIS_POR_LADA[d[:n]]
    return None

def validar_rfc(texto: str):
    rfc = re.sub(r"[\s\-]", "", (texto or "").upper())
    if rfc in ("XAXX010101000", RFC_EXTRANJERO):
        return None  # los genericos no se capturan aqui
    return rfc if _RFC_RE.match(rfc) else None

def validar_cp(texto: str):
    m = re.fullmatch(r"\s*(\d{5})\s*", texto or "")
    return m.group(1) if m else None

def validar_regimen(texto: str):
    m = re.search(r"\d{3}", texto or "")
    return m.group(0) if m and m.group(0) in REGIMENES else None

def uso_cfdi_para(regimen: str) -> str:
    return "S01" if regimen in _SOLO_S01 else "G03"

def lista_regimenes() -> str:
    return "\n".join(f"{k} - {v}" for k, v in REGIMENES.items())

# ---------- Armado del CFDI ----------
def _d(x) -> Decimal:
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def desglose(total_con_iva):
    """Precio con IVA incluido -> (subtotal, iva, total)."""
    total = _d(total_con_iva)
    sub = _d(total / (1 + IVA_TASA))
    return sub, total - sub, total

def armar_cfdi(receptor: dict, total_con_iva) -> dict:
    sub, iva, total = desglose(total_con_iva)
    tasa = f"{IVA_TASA:.6f}"
    traslado = {"Base": str(sub), "Impuesto": "002", "TipoFactor": "Tasa",
                "TasaOCuota": tasa, "Importe": str(iva)}
    return {
        "Version": "4.0", "Serie": "MORG",
        "FormaPago": "04", "MetodoPago": "PUE",   # 04 tarjeta (Stripe), pago en una exhibicion
        "Moneda": "MXN", "TipoDeComprobante": "I", "Exportacion": "01",
        "LugarExpedicion": LUGAR_EXPEDICION,
        "SubTotal": str(sub), "Total": str(total),
        "Emisor": EMISOR,
        "Receptor": receptor,
        "Conceptos": [{
            "ClaveProdServ": CLAVE_PROD, "Cantidad": "1", "ClaveUnidad": CLAVE_UNIDAD,
            "Unidad": "Servicio", "Descripcion": DESCRIPCION,
            "ValorUnitario": str(sub), "Importe": str(sub), "ObjetoImp": "02",
            "Impuestos": {"Traslados": [traslado]},
        }],
        "Impuestos": {"TotalImpuestosTrasladados": str(iva), "Traslados": [traslado]},
    }

def receptor_nacional(rfc, nombre, cp, regimen) -> dict:
    return {"Rfc": rfc, "Nombre": nombre.upper().strip(), "DomicilioFiscalReceptor": cp,
            "RegimenFiscalReceptor": regimen, "UsoCFDI": uso_cfdi_para(regimen)}

def receptor_extranjero(nombre, phone) -> dict:
    r = {"Rfc": RFC_EXTRANJERO, "Nombre": (nombre or "CLIENTE EXTRANJERO").upper().strip(),
         "DomicilioFiscalReceptor": LUGAR_EXPEDICION,  # con RFC generico va el CP del emisor
         "RegimenFiscalReceptor": "616", "UsoCFDI": "S01"}
    pais = pais_por_telefono(phone)
    if pais:
        r["ResidenciaFiscal"] = pais
    return r

# ---------- PAC (PARTE B) ----------
async def timbrar(cfdi: dict):
    """PARTE B: enviar a Edifact y regresar {'uuid','xml','pdf'}.
    No se programa hasta tener la documentacion oficial (no se inventan endpoints)."""
    if not os.getenv("EDIFACT_USER"):
        logger.info("Edifact sin configurar: factura queda pendiente_pac")
    return None

# ---------- Orquestador ----------
async def facturar(db, chart, tipo: str, receptor: dict = None, total=None):
    """Crea (una sola vez por carta) la factura y trata de timbrarla.
    tipo: 'nacional' | 'extranjero' | 'global'. Nunca lanza error al flujo."""
    try:
        r = await db.execute(select(Invoice).where(Invoice.chart_id == chart.id))
        inv = r.scalar_one_or_none()
        if inv:
            return inv
        if tipo == "extranjero":
            receptor = receptor_extranjero(chart.full_name, chart.phone_number)
        if tipo == "global":
            receptor = {"Rfc": "XAXX010101000", "Nombre": "PUBLICO EN GENERAL"}
        cfdi = armar_cfdi(receptor, total) if tipo != "global" else None
        inv = Invoice(
            chart_id=chart.id, phone_number=chart.phone_number, tipo=tipo,
            rfc=receptor.get("Rfc"), nombre=receptor.get("Nombre"),
            cp=receptor.get("DomicilioFiscalReceptor"), regimen=receptor.get("RegimenFiscalReceptor"),
            uso_cfdi=receptor.get("UsoCFDI"), residencia_fiscal=receptor.get("ResidenciaFiscal"),
            total=float(_d(total)), cfdi_json=cfdi,
            status="global" if tipo == "global" else "pendiente_pac")
        db.add(inv); await db.commit(); await db.refresh(inv)
        logger.info(f"Factura {tipo} registrada chart={chart.id} status={inv.status}")

        if cfdi:
            res = await timbrar(cfdi)
            if res:
                inv.status, inv.uuid_sat = "timbrada", res.get("uuid")
                inv.xml_path, inv.pdf_path = res.get("xml"), res.get("pdf")
                inv.stamped_at = datetime.utcnow()
                await db.commit()
        return inv
    except Exception as e:
        logger.error(f"Error facturando chart {getattr(chart, 'id', '?')}: {e}", exc_info=True)
        return None
