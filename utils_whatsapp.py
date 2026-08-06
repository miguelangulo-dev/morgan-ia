import httpx
import os
import logging
import json

logger = logging.getLogger(__name__)

WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")

class WhatsAppClient:
    """Cliente para enviar mensajes por WhatsApp"""
    
    def __init__(self):
        self.phone_id = WHATSAPP_PHONE_ID
        self.token = WHATSAPP_TOKEN
        self.api_url = f"https://graph.instagram.com/v18.0/{self.phone_id}/messages"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    async def send_text(self, to_phone: str, text: str, preview_url: bool = False):
        """Envía mensaje de texto simple"""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_phone,
            "type": "text",
            "text": {"preview_url": preview_url, "body": text}
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(self.api_url, json=payload, headers=self.headers)
            
            if response.status_code == 200:
                logger.info(f"✅ Texto enviado a {to_phone}")
                return response.json()
            else:
                logger.error(f"❌ Error enviando texto: {response.text}")
                return None
    
    async def send_buttons(self, to_phone: str, text: str, buttons: list):
        """
        Envía mensaje con botones interactivos
        
        buttons = [
            {"id": "btn1", "title": "Carta Completa"},
            {"id": "btn2", "title": "Carta Simple"}
        ]
        """
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "interactive",
            "interactive": {
                "type": "button",
                "body": {"text": text},
                "action": {
                    "buttons": [
                        {
                            "type": "reply",
                            "reply": {"id": btn["id"], "title": btn["title"]}
                        }
                        for btn in buttons
                    ]
                }
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(self.api_url, json=payload, headers=self.headers)
            
            if response.status_code == 200:
                logger.info(f"✅ Botones enviados a {to_phone}")
                return response.json()
            else:
                logger.error(f"❌ Error enviando botones: {response.text}")
                return None
    
    async def send_list(self, to_phone: str, text: str, button_text: str, sections: list):
        """
        Envía mensaje con menú de lista
        
        sections = [
            {
                "title": "Cartas Natales",
                "rows": [
                    {"id": "carta_completa", "title": "Completa", "description": "Con hora y lugar"},
                    {"id": "carta_simple", "title": "Simple", "description": "Solo fecha"}
                ]
            }
        ]
        """
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "interactive",
            "interactive": {
                "type": "list",
                "body": {"text": text},
                "action": {
                    "button": button_text,
                    "sections": sections
                }
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(self.api_url, json=payload, headers=self.headers)
            
            if response.status_code == 200:
                logger.info(f"✅ Menú de lista enviado a {to_phone}")
                return response.json()
            else:
                logger.error(f"❌ Error enviando lista: {response.text}")
                return None
    
    async def send_document(self, to_phone: str, pdf_url: str, caption: str = ""):
        """Envía documento PDF"""
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "document",
            "document": {
                "link": pdf_url,
                "caption": caption if caption else "Tu lectura de Morgan-ia 🌙"
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(self.api_url, json=payload, headers=self.headers)
            
            if response.status_code == 200:
                logger.info(f"✅ Documento enviado a {to_phone}")
                return response.json()
            else:
                logger.error(f"❌ Error enviando documento: {response.text}")
                return None
    
    async def send_image(self, to_phone: str, image_url: str, caption: str = ""):
        """Envía imagen"""
        payload = {
            "messaging_product": "whatsapp",
            "to": to_phone,
            "type": "image",
            "image": {
                "link": image_url,
                "caption": caption if caption else ""
            }
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(self.api_url, json=payload, headers=self.headers)
            
            if response.status_code == 200:
                logger.info(f"✅ Imagen enviada a {to_phone}")
                return response.json()
            else:
                logger.error(f"❌ Error enviando imagen: {response.text}")
                return None
