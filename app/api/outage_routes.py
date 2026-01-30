"""
API роути для аварійних та планових відключень
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app import crud_outages, schemas
from app.database import get_db
from typing import List
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/address-outages", response_model=schemas.AddressOutagesResponse)
async def get_outages_for_address(
    city: str = Query(..., description="Назва міста"),
    street: str = Query(..., description="Назва вулиці"),
    house: str = Query(..., description="Номер будинку"),
    region: str = Query(None, description="Область (hoe/voe). Якщо не вказано - шукає в усіх"),
    db: Session = Depends(get_db)
):
    """
    Отримує інформацію про аварійні та планові відключення для конкретної адреси
    
    Параметри:
    - city: Назва міста
    - street: Назва вулиці  
    - house: Номер будинку
    - region: (опціонально) hoe/voe - фільтр по області
    
    Повертає:
    - Активні аварійні відключення (зараз)
    - Майбутні аварійні відключення
    - Активні планові відключення (зараз)
    - Майбутні планові відключення
    """
    try:
        logger.info(f"Запит відключень для адреси: {city}, {street}, {house}")
        
        # Нормалізуємо дані
        city = city.strip()
        street = street.strip()
        house_number = house.strip()
        
        # Отримуємо активні аварійні відключення
        active_emergency = crud_outages.get_active_emergency_outages_for_address(
            db=db,
            city=city,
            street=street,
            house_number=house_number,
            region=region
        )
        
        # Отримуємо майбутні аварійні відключення
        upcoming_emergency = crud_outages.get_upcoming_emergency_outages_for_address(
            db=db,
            city=city,
            street=street,
            house_number=house_number,
            region=region
        )
        
        # Отримуємо активні планові відключення
        active_planned = crud_outages.get_active_planned_outages_for_address(
            db=db,
            city=city,
            street=street,
            house_number=house_number,
            region=region
        )
        
        # Отримуємо майбутні планові відключення
        upcoming_planned = crud_outages.get_upcoming_planned_outages_for_address(
            db=db,
            city=city,
            street=street,
            house_number=house_number,
            region=region
        )
        
        # Формуємо відповідь
        response = schemas.AddressOutagesResponse(
            city=city,
            street=street,
            house_number=house_number,
            has_emergency_outage=len(active_emergency) > 0,
            active_emergency=[schemas.OutageInfo.from_orm(o) for o in active_emergency],
            upcoming_emergency=[schemas.OutageInfo.from_orm(o) for o in upcoming_emergency],
            has_planned_outage=len(active_planned) > 0 or len(upcoming_planned) > 0,
            active_planned=[schemas.OutageInfo.from_orm(o) for o in active_planned],
            upcoming_planned=[schemas.OutageInfo.from_orm(o) for o in upcoming_planned]
        )
        
        logger.info(
            f"Знайдено відключень: "
            f"активних аварійних={len(active_emergency)}, "
            f"майбутніх аварійних={len(upcoming_emergency)}, "
            f"активних планових={len(active_planned)}, "
            f"майбутніх планових={len(upcoming_planned)}"
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Помилка при отриманні відключень: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Помилка сервера: {str(e)}"
        )
