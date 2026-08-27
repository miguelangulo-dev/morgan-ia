"""
utils_whatsapp.py - FIX v2 - corrige BASE_URL vacio + Unsupported post request
El error "Object with ID 'messages' does not exist" es porque PHONE_NUMBER_ID estaba vacio al importar.
Ahora lee env dentro de __init__ y valida.
"""

import os
import logging
import httpx
import mimetypes

logger = logging.getLogger(__name__)

def _get_env(name_list, default=""):
    for n in name_list:
        v = os.getenv(n)
        if v:
            return v
    return default

class WhatsAppClient:
    def __init__(self):
        # Lee token de varias posibles variables (por si en Railway lo nombraste diferente)
        self.token = _get_env([
            "WHATSAPP_TOKEN",
            "WHATSAPP_ACCESS_TOKEN",
            "META_WHATSAPP_TOKEN",
            "WHATSAPP_API_TOKEN",
            "GRAPH_API_TOKEN"
        ])
        self.phone_id = _get_env([
            "WHATSAPP_PHONE_NUMBER_ID",
            "PHONE_NUMBER_ID",
            "WHATSAPP_PHONE_ID",
            "META_PHONE_NUMBER_ID",
            "WA_PHONE_NUMBER_ID"
        ])
        self.api_version = _get_env(["WHATSAPP_API_VERSION", "GRAPH_API_VERSION"], "v18.0")
        
        if not self.token:
            logger.error("❌ WHATSAPP_TOKEN vacio - revisa Railway Variables")
        if not self.phone_id:
            logger.error("❌ WHATSAPP_PHONE_NUMBER_ID vacio - revisa Railway Variables")
        else:
            logger.info(f"WhatsApp Client init phone_id={self.phone_id[:6]}... version={self.api_version}")

        self.base_url = f"https://graph.facebook.com/{self.api_version}/{self.phone_id}"
        self.headers = {"Authorization": f"Bearer {self.token}"}

    def _check_config(self):
        if not self.phone_id or not self.token:
            logger.error(f"Config WhatsApp incompleta phone_id={bool(self.phone_id)} token={bool(self.token)}")
            return False
        # Evita que base_url termine en //messages
        if "//" in self.base_url.replace("https://", ""):
            logger.error(f"BASE_URL mal formada: {self.base_url}")
            return False
        return True

    async def send_text(self, phone: str, text: str):
        if not self._check_config():
            return None
        url = f"{self.base_url}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "text",
            "text": {"body": text}
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, headers={**self.headers, "Content-Type": "application/json"}, json=payload)
            if r.status_code != 200:
                logger.error(f"Error enviando texto: {r.status_code} {r.text} | url={url}")
            return r

    async def send_buttons(self, phone: str, body_text: str, buttons: list):
        if not self._check_config():
            return None
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
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, headers={**self.headers, "Content-Type": "application/json"}, json=payload)
            if r.status_code != 200:
                logger.error(f"Error enviando botones: {r.status_code} {r.text} | url={url}")
            return r

    async def send_document(self, phone: str, file_path: str, caption: str = "", filename: str = "Carta_Astral_Morgan.pdf"):
        if not self._check_config():
            return None
        # URL publica
        if file_path.startswith("http://") or file_path.startswith("https://"):
            return await self._send_document_by_link(phone, file_path, caption, filename)
        if not os.path.exists(file_path):
            logger.error(f"PDF no existe: {file_path}")
            return None
        media_id = await self._upload_media(file_path)
        if not media_id:
            return None
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
                        media_id = r.json().get("id")
                        logger.info(f"Media subido OK: {media_id}")
                        return media_id
                    else:
                        logger.error(f"Error subiendo media: {r.status_code} {r.text} | url={url}")
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
            "document": {"id": media_id, "caption": caption, "filename": filename}
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, headers={**self.headers, "Content-Type": "application/json"}, json=payload)
            if r.status_code != 200:
                logger.error(f"Error enviando doc por id: {r.status_code} {r.text}")
            else:
                logger.info(f"Documento enviado por id {media_id} a {phone}")
            return r

    async def _send_document_by_link(self, phone: str, link: str, caption: str, filename: str):
        url = f"{self.base_url}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "document",
            "document": {"link": link, "caption": caption, "filename": filename}
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(url, headers={**self.headers, "Content-Type": "application/json"}, json=payload)
            if r.status_code != 200:
                logger.error(f"Error enviando doc por link: {r.status_code} {r.text}")
            return r
