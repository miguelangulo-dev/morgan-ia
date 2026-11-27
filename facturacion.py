"""
facturacion.py - CFDI 4.0 para Morgan-IA (PAC: CFDI Express API)

Arma los datos del CFDI, los guarda en la tabla `invoices` y los timbra con
CFDI Express (https://api.cfdi.express). El CSD vive en el panel de CFDI Express;
el emisor se busca por RFC. Si el timbrado falla, la factura queda guardada
con status 'error' o 'pendiente_pac' y no se pierde.

Variables de entorno (Railway):
  CFDI_EXPRESS_KEY          sk_test_... (pruebas) o sk_live_... (produccion)
  EMISOR_RFC                EKU9003173C9 (pruebas) o STD260924HWA (produccion)
  CFDI_EXPRESS_MERCHANT_ID  opcional; si no esta, se busca por EMISOR_RFC
  SAT_CLAVE_PROD=01010101 (temporal), SAT_CLAVE_UNIDAD=E48, IVA_TASA=0.16
  EMISOR_NOMBRE, EMISOR_REGIMEN=601, EMISOR_CP=38028 (respaldo si no se lee del emisor)
"""
import os, re, asyncio, logging
import httpx
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

# ---------- PAC: CFDI Express ----------
API_URL = "https://api.cfdi.express"
_merchant_cache = {}

def _headers(extra=None):
    h = {"Authorization": f"Bearer {os.getenv('CFDI_EXPRESS_KEY', '')}",
         "Content-Type": "application/json"}
    h.update(extra or {})
    return h

async def _merchant(client):
    """Devuelve {'id','zip'} del emisor. Usa CFDI_EXPRESS_MERCHANT_ID o busca por EMISOR_RFC."""
    rfc = os.getenv("EMISOR_RFC", "").upper()
    if rfc in _merchant_cache:
        return _merchant_cache[rfc]
    fixed = os.getenv("CFDI_EXPRESS_MERCHANT_ID")
    if fixed:
        r = await client.get(f"{API_URL}/v1/merchants/{fixed}", headers=_headers())
        m = r.json() if r.status_code == 200 else {"id": fixed}
    else:
        r = await client.get(f"{API_URL}/v1/merchants", headers=_headers())
        r.raise_for_status()
        body = r.json()
        items = body.get("data", body) if isinstance(body, dict) else body
        m = next((x for x in items if str(x.get("rfc", "")).upper() == rfc), None)
        if not m:
            raise ValueError(f"No hay emisor con RFC {rfc} en CFDI Express (revisa modo Test/Live)")
    out = {"id": m.get("id"), "zip": m.get("zip") or LUGAR_EXPEDICION}
    _merchant_cache[rfc] = out
    logger.info(f"Emisor CFDI Express: {out['id']} RFC {rfc}")
    return out

def _request_body(merchant, receptor: dict, total) -> dict:
    """Convierte nuestro receptor al formato de POST /v1/invoices."""
    rec = {"rfc": receptor["Rfc"], "name": receptor["Nombre"],
           "zip": receptor["DomicilioFiscalReceptor"],
           "regimenFiscal": receptor["RegimenFiscalReceptor"]}
    if receptor["Rfc"] == RFC_EXTRANJERO:
        rec["zip"] = merchant["zip"]  # con XEXX va el CP de expedicion del emisor
    if receptor.get("ResidenciaFiscal"):
        rec["residenciaFiscal"] = receptor["ResidenciaFiscal"]
    return {
        "merchantId": merchant["id"],
        "metodoPago": "PUE", "formaPago": "04",   # tarjeta (Stripe), una exhibicion
        "usoCfdi": receptor["UsoCFDI"], "currency": "MXN",
        "receiver": rec,
        "items": [{"productCode": CLAVE_PROD, "unitCode": CLAVE_UNIDAD, "unit": "Servicio",
                   "description": DESCRIPCION, "quantity": 1,
                   "unitPrice": float(_d(total)), "ivaRate": float(IVA_TASA)}],
        "pricesIncludeTax": True,
    }

async def timbrar(receptor: dict, total, idem_key: str):
    """Timbra y regresa {'ok':True,'id','uuid','pdf','xml','body'} o {'ok':False,'error','retry'}.
    idem_key evita timbrar dos veces la misma carta."""
    if not os.getenv("CFDI_EXPRESS_KEY"):
        logger.info("CFDI_EXPRESS_KEY vacia: factura queda pendiente_pac")
        return {"ok": False, "error": "CFDI_EXPRESS_KEY vacia", "retry": True}
    try:
        async with httpx.AsyncClient(timeout=60.0) as c:
            merchant = await _merchant(c)
            body = _request_body(merchant, receptor, total)
            r = await c.post(f"{API_URL}/v1/invoices", json=body,
                             headers=_headers({"Idempotency-Key": idem_key}))
            if r.status_code not in (200, 201, 202):
                err = r.json() if "json" in r.headers.get("content-type", "") else {"detail": r.text}
                code = err.get("code", r.status_code)
                logger.error(f"CFDI Express {r.status_code} {code}: {str(err)[:800]}")
                return {"ok": False, "body": body, "error": f"{code}: {str(err)[:900]}",
                        "retry": r.status_code in (402, 409, 429, 500, 503)}
            inv = r.json()
            # Espera a que esten listos el timbre y los archivos (max ~40 s)
            for _ in range(20):
                if inv.get("status") == "stamped" and (inv.get("files") or {}).get("status") == "ready" \
                        and (inv.get("files") or {}).get("pdfUrl"):
                    break
                if (inv.get("files") or {}).get("status") == "failed":
                    break
                await asyncio.sleep(2)
                g = await c.get(f"{API_URL}/v1/invoices/{inv['id']}", headers=_headers())
                if g.status_code == 200:
                    inv = g.json()
            files = inv.get("files") or {}
            if inv.get("status") != "stamped":
                return {"ok": False, "body": body, "id": inv.get("id"),
                        "error": f"status {inv.get('status')}", "retry": True}
            return {"ok": True, "body": body, "id": inv["id"], "uuid": inv.get("uuid"),
                    "pdf": files.get("pdfUrl"), "xml": files.get("xmlUrl")}
    except Exception as e:
        logger.error(f"Error timbrando: {e}", exc_info=True)
        return {"ok": False, "error": str(e)[:900], "retry": True}

async def descargar(url: str, destino: str):
    """Baja un archivo (las URLs de CFDI Express caducan en 15 min)."""
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as c:
        r = await c.get(url)
        r.raise_for_status()
        with open(destino, "wb") as f:
            f.write(r.content)
    return destino

# ---------- Orquestador ----------
async def facturar(db, chart, tipo: str, receptor: dict = None, total=None):
    """Crea (una sola vez por carta) la factura y trata de timbrarla.
    tipo: 'nacional' | 'extranjero' | 'global'. Nunca lanza error al flujo."""
    try:
        r = await db.execute(select(Invoice).where(Invoice.chart_id == chart.id))
        inv = r.scalar_one_or_none()
        if inv and inv.tipo == "global" and tipo == "nacional":
            await db.delete(inv); await db.commit(); inv = None  # cambio de opinion: si quiere factura
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
            res = await timbrar(receptor, total, idem_key=f"morgan-{inv.id}")
            if res.get("body"):
                inv.cfdi_json = {**cfdi, "_request": res["body"], "_pac_id": res.get("id")}
            if res.get("ok"):
                inv.status, inv.uuid_sat = "timbrada", res.get("uuid")
                inv.stamped_at = datetime.utcnow()
                inv._files = {"pdf": res.get("pdf"), "xml": res.get("xml")}  # caducan en 15 min
            else:
                inv.status = "pendiente_pac" if res.get("retry") else "error"
                inv.error = res.get("error")
            await db.commit()
        return inv
    except Exception as e:
        logger.error(f"Error facturando chart {getattr(chart, 'id', '?')}: {e}", exc_info=True)
        return None
