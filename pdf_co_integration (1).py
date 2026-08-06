"""
Usa PDF.co para:
1. Convertir cada .docx a PDF
2. Fusionar todos los PDFs en un único documento final
3. Subir el resultado y regresar una URL pública para enviar por WhatsApp

WhatsApp requiere una URL pública (https) para enviar documentos, no un archivo local.
Por eso el resultado final se sube y se regresa el link.
"""

import os
import httpx
import logging

logger = logging.getLogger(__name__)

PDFCO_API_KEY = os.getenv("PDFCO_API_KEY", "")
PDFCO_BASE_URL = "https://api.pdf.co/v1"


def _headers():
    return {"x-api-key": PDFCO_API_KEY}


def docx_to_pdf(docx_path: str) -> str:
    """Sube un .docx y regresa la URL del PDF convertido (hosteado por PDF.co)."""
    with httpx.Client(timeout=60) as client:
        # 1. Sube el archivo a PDF.co
        with open(docx_path, "rb") as f:
            upload_resp = client.post(
                f"{PDFCO_BASE_URL}/file/upload",
                headers=_headers(),
                files={"file": (os.path.basename(docx_path), f)},
            )
        upload_resp.raise_for_status()
        uploaded_url = upload_resp.json()["url"]

        # 2. Convierte a PDF
        convert_resp = client.post(
            f"{PDFCO_BASE_URL}/pdf/convert/from/doc",
            headers=_headers(),
            json={"url": uploaded_url, "inline": False},
        )
        convert_resp.raise_for_status()
        result = convert_resp.json()

        if result.get("error"):
            raise RuntimeError(f"PDF.co error convirtiendo {docx_path}: {result.get('message')}")

        return result["url"]


def merge_docx_to_pdf(docx_or_pdf_paths: list, output_path: str) -> str:
    """
    Convierte cada archivo a PDF (si ya es PDF lo sube tal cual) y los fusiona
    en un único PDF final en el orden dado. Descarga el resultado a output_path.
    """
    pdf_urls = []

    with httpx.Client(timeout=60) as client:
        for path in docx_or_pdf_paths:
            if path.lower().endswith(".pdf"):
                with open(path, "rb") as f:
                    upload_resp = client.post(
                        f"{PDFCO_BASE_URL}/file/upload",
                        headers=_headers(),
                        files={"file": (os.path.basename(path), f)},
                    )
                upload_resp.raise_for_status()
                pdf_urls.append(upload_resp.json()["url"])
            else:
                pdf_urls.append(docx_to_pdf(path))

        # Fusiona todos los PDFs en uno
        merge_resp = client.post(
            f"{PDFCO_BASE_URL}/pdf/merge",
            headers=_headers(),
            json={"url": ",".join(pdf_urls), "inline": False},
        )
        merge_resp.raise_for_status()
        merge_result = merge_resp.json()

        if merge_result.get("error"):
            raise RuntimeError(f"PDF.co error fusionando PDFs: {merge_result.get('message')}")

        final_url = merge_result["url"]

        # Descarga el PDF final localmente (opcional, útil para respaldo)
        pdf_bytes = client.get(final_url).content
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)

        logger.info(f"✅ PDF final armado: {final_url}")
        # Regresamos la URL pública de PDF.co, que es lo que WhatsApp necesita para enviarlo
        return final_url
