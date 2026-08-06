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
    Guarda en qué paso de la conversación va cada usuario.
    Esto es lo que permite que el bot 'recuerde' qué preguntó y qué falta.
    """
    __tablename__ = "conversation_states"

    phone_number = Column(String(20), primary_key=True)
    current_step = Column(String(50), default="MENU")
    # Aquí se van acumulando los datos que el usuario da mientras avanza
    # ej: {"full_name": "Juan Perez", "birth_date": "1990-03-15", "birth_time": "14:30", "service": "carta_natal"}
    collected_data = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DailySale(Base):
    __tablename__ = "daily_sales"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, index=True)
    sale_date = Column(DateTime, default=datetime.utcnow, index=True)
    service_type = Column(String(50))
    amount_mxn = Column(Float)
    payment_status = Column(String(20), default="pending")  # pending, paid, failed
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
    Carta natal generada. pdf_ready=True cuando ya se armó el PDF (portada+contenido)
    y está esperando el pago. Una vez pagado, delivered=True.
    """
    __tablename__ = "natal_charts"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, index=True)
    phone_number = Column(String(20), index=True)
    full_name = Column(String(200))
    birth_date = Column(String)          # "1990-03-15"
    birth_time = Column(String, nullable=True)  # "14:30" o None si no la sabe
    zodiac_western = Column(String(20))
    zodiac_chinese = Column(String(50))
    zodiac_celtic = Column(String(50))
    zodiac_mayan = Column(String(50))
    zodiac_egyptian = Column(String(50))
    interpretation_json = Column(JSON)   # todo el contenido generado por Claude, por sección
    cover_used = Column(String(200), nullable=True)  # nombre del archivo de portada elegido
    pdf_path = Column(String, nullable=True)   # ruta/URL del PDF ya armado
    pdf_ready = Column(Boolean, default=False)
    payment_status = Column(String(20), default="pending")  # pending, paid
    delivered = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
