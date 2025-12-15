"""
Pydantic схеми для валідації API запитів та відповідей
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List


# === Схеми для Outages ===

class OutageBase(BaseModel):
    """Базова схема для відключення"""
    city: str = Field(..., description="Місто або село")
    street: str = Field(..., description="Вулиця")
    house_number: str = Field(..., description="Номер будинку")
    queue: Optional[str] = Field(None, description="Черга відключення (1, 2, 3 тощо)")
    zone: Optional[str] = Field(None, description="Зона або група")
    schedule_time: Optional[str] = Field(None, description="Час відключення (наприклад, '08:00 - 12:00')")


class OutageCreate(OutageBase):
    """Схема для створення нового відключення"""
    source_url: Optional[str] = Field(None, description="URL джерела")


class OutageResponse(OutageBase):
    """Схема відповіді з інформацією про відключення"""
    id: int
    updated_at: datetime
    source_url: str
    
    class Config:
        from_attributes = True


class OutageListResponse(BaseModel):
    """Схема відповіді зі списком відключень"""
    total: int = Field(..., description="Загальна кількість записів")
    page: int = Field(..., description="Номер поточної сторінки")
    page_size: int = Field(..., description="Розмір сторінки")
    outages: List[OutageResponse] = Field(..., description="Список відключень")


# === Схеми для Users ===

class UserBase(BaseModel):
    """Базова схема користувача"""
    city: str = Field(..., description="Місто користувача")
    street: str = Field(..., description="Вулиця користувача")
    house_number: str = Field(..., description="Номер будинку")


class UserRegister(UserBase):
    """Схема для реєстрації користувача"""
    firebase_token: str = Field(..., description="Firebase Cloud Messaging токен")


class UserResponse(UserBase):
    """Схема відповіді з інформацією про користувача"""
    id: int
    firebase_token: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


# === Схеми для запитів ===

class OutageQuery(BaseModel):
    """Схема для запиту відключень за адресою"""
    city: str = Field(..., description="Місто")
    street: str = Field(..., description="Вулиця")
    house_number: str = Field(..., description="Номер будинку")


class HistoryQuery(OutageQuery):
    """Схема для запиту історії відключень"""
    limit: Optional[int] = Field(10, description="Кількість записів", ge=1, le=100)


# === Загальні схеми ===

class StatusResponse(BaseModel):
    """Схема для відповіді статусу API"""
    status: str = Field(..., description="Статус API")
    message: Optional[str] = Field(None, description="Додаткове повідомлення")
    timestamp: datetime = Field(default_factory=datetime.now, description="Час відповіді")


class ErrorResponse(BaseModel):
    """Схема для відповідей з помилками"""
    error: str = Field(..., description="Тип помилки")
    message: str = Field(..., description="Опис помилки")
    details: Optional[dict] = Field(None, description="Додаткові деталі")


# === Схеми для аварійних та планових відключень ===

class OutageInfo(BaseModel):
    """Схема інформації про відключення"""
    id: int
    rem_name: str = Field(..., description="Назва РЕМ")
    city: str = Field(..., description="Місто/громада")
    street: str = Field(..., description="Вулиця")
    house_numbers: str = Field(..., description="Номери будинків")
    work_type: str = Field(..., description="Вид робіт")
    created_date: datetime = Field(..., description="Дата створення запису")
    start_time: datetime = Field(..., description="Час початку відключення")
    end_time: datetime = Field(..., description="Час відновлення")
    
    class Config:
        from_attributes = True


class AddressOutagesResponse(BaseModel):
    """Схема відповіді з інформацією про відключення за адресою"""
    city: str = Field(..., description="Місто")
    street: str = Field(..., description="Вулиця")
    house_number: str = Field(..., description="Номер будинку")
    
    # Аварійні відключення
    has_emergency_outage: bool = Field(..., description="Чи є активне аварійне відключення")
    active_emergency: List[OutageInfo] = Field(default=[], description="Активні аварійні відключення")
    upcoming_emergency: List[OutageInfo] = Field(default=[], description="Майбутні аварійні відключення")
    
    # Планові відключення
    has_planned_outage: bool = Field(..., description="Чи є активне планове відключення")
    active_planned: List[OutageInfo] = Field(default=[], description="Активні планові відключення")
    upcoming_planned: List[OutageInfo] = Field(default=[], description="Майбутні планові відключення")


# Device Token Schemas
class DeviceTokenCreate(BaseModel):
    device_id: str
    fcm_token: str
    platform: str


class DeviceTokenResponse(BaseModel):
    device_id: str
    fcm_token: str
    platform: str
    notifications_enabled: bool
    created_at: datetime
    updated_at: datetime | None

    class Config:
        from_attributes = True
