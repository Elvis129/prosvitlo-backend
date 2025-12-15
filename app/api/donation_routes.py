from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from app.config import settings

router = APIRouter()

class DonationInfo(BaseModel):
    jar_url: Optional[str] = None
    card_number: Optional[str] = None
    description: Optional[str] = None

@router.get("/donation", response_model=DonationInfo)
async def get_donation_info():
    """
    Отримати інформацію про підтримку розробника.
    Дані беруться з .env файлу для легкого оновлення.
    Якщо дані не налаштовані - повертає пусті значення.
    """
    # Перевіряємо чи є хоча б URL банки
    jar_url = getattr(settings, 'DONATION_JAR_URL', None)
    
    # Якщо URL пустий або не налаштований - повертаємо пусті дані
    if not jar_url or jar_url.strip() == '':
        return DonationInfo(
            jar_url=None,
            card_number=None,
            description=None
        )
    
    return DonationInfo(
        jar_url=jar_url,
        card_number=getattr(settings, 'DONATION_CARD_NUMBER', None),
        description=getattr(settings, 'DONATION_DESCRIPTION', None)
    )
