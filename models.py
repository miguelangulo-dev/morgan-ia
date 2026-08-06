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
    gender = Column(String(20), nullable=True)  # "masculino", "femenino", "otro"
    age = Column(Integer, nullable=True)
    zodiac_sign = Column(String(20), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_interaction = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)

class DailySale(Base):
    """Ventas diarias por usuario"""
    __tablename__ = "daily_sales"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, index=True)
    sale_date = Column(DateTime, default=datetime.utcnow, index=True)
    service_type = Column(String(50))  # "carta_natal", "tarot", "afinidad_zodiacal"
    amount_mxn = Column(Float)
    payment_status = Column(String(20), default="pending")  # "pending", "completed", "failed"
    stripe_payment_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class ZodiacSale(Base):
    """Ventas agrupadas por signo zodiacal"""
    __tablename__ = "zodiac_sales"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    zodiac_sign = Column(String(20), unique=True, index=True)
    total_sales = Column(Integer, default=0)
    total_revenue_mxn = Column(Float, default=0.0)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class NatalChart(Base):
    """Cartas natales generadas"""
    __tablename__ = "natal_charts"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, index=True)
    chart_type = Column(String(20))  # "completa" o "simple"
    birth_date = Column(String)  # "1990-03-15"
    birth_time = Column(String, nullable=True)  # "14:30:00" solo si completa
    birth_location = Column(String, nullable=True)
    zodiac_western = Column(String(20))
    zodiac_chinese = Column(String(50))
    zodiac_celtic = Column(String(50))
    zodiac_mayan = Column(String(50))
    zodiac_egyptian = Column(String(50))
    pdf_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class TarotReading(Base):
    """Tiradas de tarot"""
    __tablename__ = "tarot_readings"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, index=True)
    cards = Column(JSON)  # [{"position": 1, "card": "El Mago", "interpretation": "..."}]
    questions = Column(JSON)  # ["¿Será un buen año?", "¿Encontraré amor?", ...]
    answers = Column(JSON)  # [{"question": "...", "answer": "sí/no", "interpretation": "..."}]
    pdf_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class AfffinityReading(Base):
    """Afinidades zodiacales"""
    __tablename__ = "affinity_readings"
    
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, index=True)
    user_zodiac = Column(String(20))
    target_zodiac = Column(String(20))
    affinity_percentage = Column(Integer)
    interpretation = Column(Text)
    pdf_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
