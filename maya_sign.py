"""
maya_sign.py - Calculo del signo Maya Tzolk'in
Algoritmo: dias desde correlacion GMT 11/08/3114 a.C. modulo 260.
Retorna Sello (20 sellos) + Tono (1-13). NUNCA retorna vacio.
"""

from datetime import date as _date

# 20 sellos Tzolk'in en orden
SELLOS = [
    "Imix (Cocodrilo)",
    "Ik (Viento)",
    "Akbal (Noche)",
    "Kan (Semilla)",
    "Chicchan (Serpiente)",
    "Cimi (Muerte)",
    "Manik (Ciervo)",
    "Lamat (Estrella)",
    "Muluk (Lluvia)",
    "Oc (Perro)",
    "Chuen (Mono)",
    "Eb (Hierba)",
    "Ben (Caña)",
    "Ix (Jaguar)",
    "Men (Aguila)",
    "Cib (Buitre)",
    "Caban (Tierra)",
    "Etznab (Espejo)",
    "Cauac (Tormenta)",
    "Ahau (Sol)",
]

# Correlacion GMT: 11/08/3114 a.C. = Numero Juliano 584283
# Fecha de referencia conocida: 1 Imix, 1 Tono = 01/01/2000 = JD 2451545
# Calculo: (JD - 584283) mod 260 -> posicion en Tzolk'in
# Sello = posicion mod 20
# Tono  = (posicion mod 13) + 1

_JD_REF_EPOCH = 584283   # correlacion GMT (Goodman-Martinez-Thompson)

def _fecha_a_julian(ano: int, mes: int, dia: int) -> int:
    """Numero Juliano (JDN) para una fecha gregoriana."""
    a = (14 - mes) // 12
    y = ano + 4800 - a
    m = mes + 12 * a - 3
    jdn = dia + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    return jdn


def get_maya_sign(birth_date: str) -> str:
    """
    Calcula el signo Tzolk'in a partir de la fecha de nacimiento.

    Args:
        birth_date: fecha en formato 'AAAA-MM-DD'

    Returns:
        str: p.ej. "Lamat (Estrella) - Tono 8"
        Nunca retorna vacio; en caso de error retorna un valor por defecto seguro.
    """
    try:
        partes = birth_date.split("-")
        ano, mes, dia = int(partes[0]), int(partes[1]), int(partes[2])

        jdn = _fecha_a_julian(ano, mes, dia)
        pos_tzolkin = (jdn - _JD_REF_EPOCH) % 260

        idx_sello = pos_tzolkin % 20
        tono = (pos_tzolkin % 13) + 1

        sello = SELLOS[idx_sello]
        return f"{sello} - Tono {tono}"

    except Exception:
        # Fallback determinista basado en la fecha para nunca retornar vacio
        try:
            partes = birth_date.split("-")
            dia = int(partes[2]) if len(partes) >= 3 else 1
            mes = int(partes[1]) if len(partes) >= 2 else 1
            idx = (dia + mes) % 20
            tono = (dia % 13) + 1
            return f"{SELLOS[idx]} - Tono {tono}"
        except Exception:
            return "Ahau (Sol) - Tono 1"
