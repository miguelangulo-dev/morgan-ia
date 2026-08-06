# 🌙 Morgan-ia - Chatbot de Astrología & Tarot en WhatsApp

Chatbot IA que genera cartas natales, tiradas de tarot egipcio y calcula afinidades zodiacales en WhatsApp.

## 📋 Stack Confirmado

- **Frontend**: WhatsApp Cloud API (Meta)
- **Backend**: FastAPI + Uvicorn
- **IA**: Claude API (Anthropic)
- **Base de datos**: PostgreSQL (Railway)
- **Pagos**: Stripe
- **PDF**: PDF.co
- **Hosting**: Railway

---

## 🚀 Estructura del Proyecto

```
morgan-ia/
├── main.py                      # FastAPI webhook y rutas
├── models.py                    # SQLAlchemy models
├── utils_whatsapp.py           # Cliente WhatsApp (text, buttons, lists, media)
├── agentes_claude_astro.py     # Agente Claude para IA
├── requirements.txt             # Dependencias Python
├── .env.example                # Variables de entorno
├── assets/
│   ├── pdfs/                   # PDFs de tarot egipcio (subir aquí)
│   │   ├── tarot_egiptio.pdf
│   │   └── interpretaciones.pdf
│   └── templates/              # Machotes de documentos
│       ├── portada.docx
│       ├── contenido.docx
│       └── cierre.docx
└── README.md
```

---

## 🔧 Setup en Railway

### 1. **Crear servicio PostgreSQL**
```
Railway Dashboard → New → Database → PostgreSQL
```

### 2. **Crear servicio Web (Morgan-ia)**
```
Railway Dashboard → New → GitHub Repo (morgan-ia)
```

### 3. **Conectar PostgreSQL a Morgan-ia**
```
PostgreSQL service → Connect → Select morgan-ia service
```

Esto automáticamente agrega `DATABASE_URL` a las variables de entorno.

### 4. **Variables de Entorno en Railway**

En el servicio `morgan-ia`, ve a **Variables** y configura:

```env
WHATSAPP_PHONE_ID=1197127820156021
WHATSAPP_BUSINESS_ACCOUNT_ID=1510278050496302
WHATSAPP_TOKEN=tu_token_aqui
VERIFY_TOKEN=morgania2026
ANTHROPIC_API_KEY=sk-ant-...
STRIPE_API_KEY=sk_live_...
PDFCO_API_KEY=tu_key_aqui
ENVIRONMENT=production
```

El `DATABASE_URL` se genera automáticamente al conectar PostgreSQL.

### 5. **Build Command**
```
pip install -r requirements.txt
```

### 6. **Start Command**
```
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## 🔗 Configurar Webhook en Meta Developers

### URL de Webhook
```
https://morgan-ia-production.up.railway.app/webhook/whatsapp
```

### Pasos en Meta App Dashboard:
1. Ir a tu app → **WhatsApp** → **Configuration**
2. **Webhook URL**: `https://morgan-ia-production.up.railway.app/webhook/whatsapp`
3. **Verify Token**: `morgania2026`
4. **Subscribe** a estos webhooks:
   - ✅ messages
   - ✅ message_status
   - ✅ message_template_status_update

---

## 📚 Próximos Pasos (TO-DO)

### 1️⃣ **Integración de PDFs de Tarot Egipcio**
- Sube los PDFs a `/assets/pdfs/`
- En `agentes_claude_astro.py`, modifica `generate_tarot_reading()`:
```python
# Leer PDFs y pasar contexto a Claude
tarot_pdf_context = read_tarot_pdfs()
result = await agent.generate_tarot_reading(questions, tarot_pdf_context)
```

### 2️⃣ **Machotes de Documentos (DOCX)**
- Sube los machotes a `/assets/templates/`
- Usa `docxtemplater` para rellenar campos:
```python
{{fecha_lectura}}
{{signo_zodiacal}}
{{interpretacion}}
```

### 3️⃣ **Generación de PDFs con PDF.co**
- Crear `utils/pdf_co_integration.py`
- Convertir DOCX → PDF y subirlo a storage (Railway Volume o S3)

### 4️⃣ **Integración de Stripe**
- Crear rutas para crear payment intents
- Guardar transacciones en `DailySale` y `ZodiacSale`

### 5️⃣ **Menú Interactivo Completo**
- Botones para elegir: "Carta Completa" vs "Carta Simple"
- Recopilar datos del usuario (género, edad, fecha nacimiento)
- Guardar en tabla `User`

### 6️⃣ **Lógica de Conversación (State Management)**
- Sistema para recordar el estado de la conversación
- Ej: "esperando_fecha_nacimiento", "esperando_respuesta_tarot", etc.

---

## 🔑 Credenciales Necesarias

### WhatsApp
- `WHATSAPP_PHONE_ID`: 1197127820156021
- `WHATSAPP_BUSINESS_ACCOUNT_ID`: 1510278050496302
- `WHATSAPP_TOKEN`: Obtener de Meta App Dashboard

### Claude API
- `ANTHROPIC_API_KEY`: Obtener de https://console.anthropic.com/

### Stripe
- `STRIPE_API_KEY`: Obtener de https://dashboard.stripe.com/

### PDF.co
- `PDFCO_API_KEY`: Obtener de https://pdf.co/

---

## 📊 Base de Datos - Tablas

### `users`
```sql
id | phone_number | gender | age | zodiac_sign | created_at | last_interaction | is_active
```

### `daily_sales`
```sql
id | user_id | sale_date | service_type | amount_mxn | payment_status | stripe_payment_id | created_at
```

### `zodiac_sales`
```sql
id | zodiac_sign | total_sales | total_revenue_mxn | last_updated
```

### `natal_charts`
```sql
id | user_id | chart_type | birth_date | birth_time | birth_location | zodiac_western/chinese/celtic/mayan/egyptian | pdf_url | created_at
```

### `tarot_readings`
```sql
id | user_id | cards | questions | answers | pdf_url | created_at
```

### `affinity_readings`
```sql
id | user_id | user_zodiac | target_zodiac | affinity_percentage | interpretation | pdf_url | created_at
```

---

## 🧪 Test Local

```bash
# 1. Instalar dependencias
pip install -r requirements.txt

# 2. Crear archivo .env
cp .env.example .env
# Editar .env con tus credenciales

# 3. Iniciar servidor
uvicorn main:app --reload

# 4. Test webhook verification
curl "http://localhost:8000/webhook/whatsapp?hub.mode=subscribe&hub.verify_token=morgania2026&hub.challenge=test"

# 5. Test health
curl http://localhost:8000/health
```

---

## 📱 Flujo de Conversación Esperado

```
Usuario: "Hola"
Morgan-ia: "🌙 Bienvenido a Morgan-ia 🌙\n\nElige un servicio:"
[Botones: Carta Natal | Afinidad Zodiacal | Tarot]

Usuario: [Elige "Carta Natal"]
Morgan-ia: "¿Deseas una carta completa o simple?"
[Botones: Completa (con hora) | Simple (solo fecha)]

Usuario: [Elige "Simple"]
Morgan-ia: "¿Cuál es tu fecha de nacimiento? (Ej: 15/03/1990)"

Usuario: "15/03/1990"
Morgan-ia: [Claude genera carta] "Tu signo zodiacal es Aries. Aries está representado por..."
[Envía PDF con carta completa]

Usuario: "¿Cuánto cuesta?"
Morgan-ia: "Una lectura completa cuesta $79 MXN. ¿Deseas pagar?"
[Botón: Pagar con Stripe]
```

---

## 🆘 Troubleshooting

### ❌ "Webhook verification fallida"
- Verifica que `VERIFY_TOKEN` en .env sea exactamente `morgania2026`
- Recarga la página en Meta Developers

### ❌ "Database connection error"
- Verifica que `DATABASE_URL` esté correctamente configurada
- Ejecuta migrations si aplica

### ❌ "Claude API error"
- Verifica que `ANTHROPIC_API_KEY` sea válido
- Revisa límites de cuota en console.anthropic.com

---

## 📞 Soporte

Para preguntas sobre stack o integración:
- Claude API: https://docs.anthropic.com/
- WhatsApp Cloud API: https://developers.facebook.com/docs/whatsapp/cloud-api
- Railway: https://docs.railway.app/
- Stripe: https://stripe.com/docs/

---

**Morgan-ia v1.0** - Creado con ❤️ por Miguel
