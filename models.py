from sqlalchemy import Column, String, Integer, Float, DateTime, Text, Boolean, JSON
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import uuid

Base = declarative_base()


class User(Base):
    """Usuarios de Morgan-ia"""
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    phone_number = Column(String(20), unique=True, index=True)
    full_name = Column(String(200), nullable=True)
    gender = Column(String(20), nullable=True)
    age = Column(Integer, nullable=True)
    zodiac_sign = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_interaction = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)


class ConversationState(Base):
    """
    Guarda en que paso de la conversacion va cada usuario.
    """
    __tablename__ = "conversation_states"

    phone_number = Column(String(20), primary_key=True)
    current_step = Column(String(50), default="MENU")
    collected_data = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AuditoriaConsentimiento(Base):
    """
    Auditoria de consentimientos LFPDPPP.
    Registra cada vez que un usuario acepta o rechaza el aviso de privacidad.
    """
    __tablename__ = "auditoria_consentimientos"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    whatsapp_id = Column(String(30), index=True, nullable=False)
    pais_detectado = Column(String(10), nullable=True)   # "MX" o "EXT"
    fecha_hora_utc = Column(DateTime, default=datetime.utcnow, nullable=False)
    ip = Column(String(60), nullable=True)
    version_aviso = Column(String(10), default="v1.3", nullable=False)
    texto_aceptado = Column(Text, nullable=True)         # "Si, acepto" o "No acepto"
    user_agent = Column(String(200), nullable=True)
    rfc_usado = Column(String(20), nullable=True)        # Se llena cuando se genera CFDI
    acepto = Column(Boolean, nullable=False)             # True = acepto, False = rechazo
    created_at = Column(DateTime, default=datetime.utcnow)


class DailySale(Base):
    __tablename__ = "daily_sales"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, index=True)
    sale_date = Column(DateTime, default=datetime.utcnow, index=True)
    service_type = Column(String(50))
    amount_mxn = Column(Float)
    payment_status = Column(String(20), default="pending")
    stripe_session_id = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ZodiacSale(Base):
    __tablename__ = "zodiac_sales"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    zodiac_sign = Column(String(20), unique=True, index=True)
    total_sales = Column(Integer, default=0)
    total_revenue_mxn = Column(Float, default=0.0)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NatalChart(Base):
    """
    Carta natal generada. pdf_ready=True cuando ya se armo el PDF.
    Una vez pagado, delivered=True.
    """
    __tablename__ = "natal_charts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, index=True)
    phone_number = Column(String(20), index=True)
    full_name = Column(String(200))
    birth_date = Column(String)
    birth_time = Column(String, nullable=True)
    birth_place = Column(String(255), nullable=True)
    gender = Column(String(50), nullable=True)
    zodiac_western = Column(String(20))
    zodiac_chinese = Column(String(50))
    zodiac_celtic = Column(String(50))
    zodiac_mayan = Column(String(50))
    zodiac_egyptian = Column(String(50), nullable=True)
    interpretation_json = Column(JSON, nullable=True)
    cover_used = Column(String(200), nullable=True)
    pdf_path = Column(String, nullable=True)
    pdf_ready = Column(Boolean, default=False)
    payment_status = Column(String(20), default="pending")
    delivered = Column(Boolean, default=False)
    # Datos de facturacion
    rfc = Column(String(20), nullable=True)
    razon_social = Column(String(200), nullable=True)
    cfdi_uuid = Column(String(40), nullable=True)
    cfdi_pdf_path = Column(String, nullable=True)
    cfdi_xml_path = Column(String, nullable=True)
    requiere_factura = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class TarotReading(Base):
    __tablename__ = "tarot_readings"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    chart_id = Column(String, index=True)
    phone_number = Column(String(20), index=True)
    questions = Column(JSON)
    readings = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)
