"""
utils_whatsapp.py - FIX document.link is not a valid URL
Ahora sube el PDF local a WhatsApp y envia con media_id, no con link
"""

import os
import logging
import httpx
import mimetypes

logger = logging.getLogger(__name__)

WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", os.getenv("WHATSAPP_ACCESS_TOKEN", ""))
PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", os.getenv("PHONE_NUMBER_ID", ""))
WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v18.0")

BASE_URL = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{PHONE_NUMBER_ID}"

class WhatsAppClient:
    def __init__(self):
        self.token = WHATSAPP_TOKEN
        self.phone_id = PHONE_NUMBER_ID
        self.base_url = BASE_URL
        self.headers = {"Authorization": f"Bearer {self.token}"}

    async def send_text(self, phone: str, text: str):
        url = f"{self.base_url}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "text",
            "text": {"body": text}
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(url, headers={**self.headers, "Content-Type": "application/json"}, json=payload)
            if r.status_code != 200:
                logger.error(f"Error enviando texto: {r.text}")
            return r

    async def send_buttons(self, phone: str, body_text: str, buttons: list):
        # buttons = [{"id": "...", "title": "..."}]
        url = f"{self.base_url}/messages"
        btns = []
        for b in buttons[:3]:
            btns.append({
                "type": "reply",
                "reply": {"id": b["id"], "title": b["title"][:20]}
            })
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": body_text},
                "action": {"buttons": btns}
            }
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(url, headers={**self.headers, "Content-Type": "application/json"}, json=payload)
            if r.status_code != 200:
                logger.error(f"Error enviando botones: {r.text}")
            return r

    async def send_document(self, phone: str, file_path: str, caption: str = "", filename: str = "Carta_Astral_Morgan.pdf"):
        """
        FIX: Si file_path es local (/app/generated_pdfs/...), lo sube primero a WhatsApp
        para obtener media_id y luego envia el documento con id, no con link.
        Si es URL http, lo envia como link.
        """
        # Si es URL publica, enviar directo con link
        if file_path.startswith("http://") or file_path.startswith("https://"):
            return await self._send_document_by_link(phone, file_path, caption, filename)

        # Si es archivo local, subirlo
        if not os.path.exists(file_path):
            logger.error(f"PDF no existe: {file_path}")
            return None

        # 1. Subir archivo a WhatsApp para obtener media_id
        media_id = await self._upload_media(file_path)
        if not media_id:
            logger.error(f"No se pudo subir media: {file_path}")
            return None

        # 2. Enviar documento con media_id
        return await self._send_document_by_id(phone, media_id, caption, filename)

    async def _upload_media(self, file_path: str) -> str:
        url = f"{self.base_url}/media"
        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = "application/pdf"

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                with open(file_path, "rb") as f:
                    files = {"file": (os.path.basename(file_path), f, mime_type)}
                    data = {"messaging_product": "whatsapp", "type": "document"}
                    r = await client.post(url, headers=self.headers, data=data, files=files)
                    if r.status_code == 200:
                        j = r.json()
                        media_id = j.get("id")
                        logger.info(f"Media subido OK: {media_id} para {file_path}")
                        return media_id
                    else:
                        logger.error(f"Error subiendo media: {r.status_code} {r.text}")
                        return None
        except Exception as e:
            logger.error(f"Excepcion subiendo media: {e}", exc_info=True)
            return None

    async def _send_document_by_id(self, phone: str, media_id: str, caption: str, filename: str):
        url = f"{self.base_url}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "document",
            "document": {
                "id": media_id,
                "caption": caption,
                "filename": filename
            }
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(url, headers={**self.headers, "Content-Type": "application/json"}, json=payload)
            if r.status_code != 200:
                logger.error(f"Error enviando documento por id: {r.text}")
            else:
                logger.info(f"Documento enviado por id {media_id} a {phone}")
            return r

    async def _send_document_by_link(self, phone: str, link: str, caption: str, filename: str):
        url = f"{self.base_url}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "document",
            "document": {
                "link": link,
                "caption": caption,
                "filename": filename
            }
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(url, headers={**self.headers, "Content-Type": "application/json"}, json=payload)
            if r.status_code != 200:
                logger.error(f"Error enviando documento por link: {r.text}")
            return r
