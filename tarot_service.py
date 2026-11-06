"""
tarot_service.py - Biblioteca oficial de cartas del Tarot Egipcio.
Lee y parsea tarot_egipcio_tirada_decision.md (raiz del proyecto).
NUNCA inventa cartas fuera de ese archivo.
"""

import os
import re
import logging

logger = logging.getLogger(__name__)

# Ruta al archivo de tarot (raiz del proyecto)
TAROT_MD_PATH = os.path.join(os.path.dirname(__file__), "tarot_egipcio_tirada_decision.md")

# Cache en memoria para no leer el archivo en cada request
_BIBLIOTECA: dict[str, dict] | None = None   # {nombre_normalizado: {numero, nombre, significado}}


def _normalizar(texto: str) -> str:
    """Lowercase sin tildes ni puntuacion extra para comparar nombres."""
    import unicodedata
    s = unicodedata.normalize("NFKD", texto.lower().strip())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9 ]", "", s).strip()
    return s


def _parsear_md(contenido: str) -> dict:
    """
    Extrae las 78 cartas del archivo .md.
    Formato esperado: `NN. **Nombre** - Significado...`
    Retorna: {nombre_normalizado: {numero, nombre, significado}}
    """
    cartas = {}
    # Patron: numero. **Nombre** - significado
    patron = re.compile(r"^\s*(\d+)\.\s+\*\*(.+?)\*\*\s*[-–]\s*(.+)$", re.MULTILINE)
    for m in patron.finditer(contenido):
        numero = int(m.group(1))
        nombre = m.group(2).strip()
        significado = m.group(3).strip()
        clave = _normalizar(nombre)
        cartas[clave] = {
            "numero": numero,
            "nombre": nombre,
            "significado": significado,
        }
    return cartas


def cargar_biblioteca() -> dict:
    """Carga y cachea la biblioteca de cartas desde el archivo .md."""
    global _BIBLIOTECA
    if _BIBLIOTECA is not None:
        return _BIBLIOTECA

    if not os.path.exists(TAROT_MD_PATH):
        raise FileNotFoundError(
            f"Archivo de tarot no encontrado: {TAROT_MD_PATH}\n"
            "Coloca tarot_egipcio_tirada_decision.md en la raiz del proyecto."
        )

    with open(TAROT_MD_PATH, "r", encoding="utf-8") as f:
        contenido = f.read()

    cartas = _parsear_md(contenido)
    if not cartas:
        raise ValueError(
            "No se pudieron parsear cartas de tarot_egipcio_tirada_decision.md. "
            "Verifica el formato del archivo."
        )

    _BIBLIOTECA = cartas
    logger.info(f"[TarotService] Biblioteca cargada: {len(cartas)} cartas")
    return _BIBLIOTECA


def buscar_carta(nombre: str) -> dict | None:
    """
    Busca una carta por nombre (tolerante a tildes y mayusculas).
    Retorna dict con {numero, nombre, significado} o None si no existe.
    """
    biblioteca = cargar_biblioteca()
    clave = _normalizar(nombre)
    return biblioteca.get(clave)


def validar_carta(nombre: str) -> bool:
    """True si la carta existe en el archivo oficial."""
    return buscar_carta(nombre) is not None


def listar_cartas() -> list[dict]:
    """Lista todas las cartas de la biblioteca ordenadas por numero."""
    biblioteca = cargar_biblioteca()
    return sorted(biblioteca.values(), key=lambda c: c["numero"])


def validar_tirada(tirada: list[dict]) -> tuple[bool, list[str]]:
    """
    Valida que todas las cartas de una tirada existan en el archivo oficial.
    Args:
        tirada: lista de dicts con clave 'card' o 'cards'
    Returns:
        (es_valida, lista_de_errores)
    """
    errores = []
    for i, entrada in enumerate(tirada, 1):
        nombre_carta = entrada.get("card") or entrada.get("cards") or ""
        if not nombre_carta:
            errores.append(f"Pregunta {i}: falta nombre de carta")
            continue
        # El nombre puede llegar con numero, ej "El Mago (carta 1)" -- extraemos solo el nombre base
        nombre_limpio = re.sub(r"\s*\(carta\s*\d+\)", "", nombre_carta, flags=re.IGNORECASE).strip()
        nombre_limpio = re.sub(r"\s*#\d+", "", nombre_limpio).strip()
        if not validar_carta(nombre_limpio):
            errores.append(
                f"Pregunta {i}: la carta '{nombre_carta}' NO existe en tarot_egipcio_tirada_decision.md"
            )
    es_valida = len(errores) == 0
    return es_valida, errores


def construir_contexto_prompt() -> str:
    """
    Genera el texto para inyectar en el prompt de Claude con las 78 cartas reales.
    Asi Claude solo puede devolver cartas del archivo oficial.
    """
    biblioteca = cargar_biblioteca()
    cartas_ordenadas = sorted(biblioteca.values(), key=lambda c: c["numero"])

    lineas = ["BIBLIOTECA OFICIAL DE CARTAS (78 cartas del Tarot Egipcio):"]
    lineas.append("Usa EXCLUSIVAMENTE los nombres exactos de esta lista:\n")
    for carta in cartas_ordenadas:
        lineas.append(f"{carta['numero']}. {carta['nombre']}")

    lineas.append(
        "\nIMPORTANTE: Usa SOLO los nombres de la lista anterior. "
        "Cualquier nombre que no aparezca exactamente en esta lista es invalido y NO debe usarse."
    )
    return "\n".join(lineas)
