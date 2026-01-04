from sqlalchemy import Column, String, Boolean, DateTime, UniqueConstraint
from sqlalchemy.sql import func
from app.database import Base


class DeviceToken(Base):
    """Модель для зберігання FCM токенів пристроїв"""
    __tablename__ = "device_tokens"

    device_id = Column(String, primary_key=True, index=True)
    fcm_token = Column(String, nullable=False, unique=True, index=True)  # Унікальний токен
    platform = Column(String, nullable=False)  # 'android' or 'ios'
    notifications_enabled = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
