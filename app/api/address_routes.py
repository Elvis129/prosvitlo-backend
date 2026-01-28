"""
Нові API endpoints для роботи з адресами з GitHub
"""
from fastapi import APIRouter, Query, HTTPException
from typing import List, Optional, Dict

from app.services.address_service import (
    get_cities,
    get_streets,
    get_houses,
    get_address_info,
    search_addresses,
    get_statistics,
    reload_addresses
)

router = APIRouter()


@router.get("/addresses/cities")
async def api_get_cities(
    search: Optional[str] = Query(None, description="Пошуковий запит для фільтрації міст")
):
    """
    Отримати список міст/населених пунктів
    
    Параметри:
    - search: опціональний пошуковий запит (наприклад: "Хмель")
    
    Приклад: /api/v1/addresses/cities?search=Хмель
    """
    try:
        cities = get_cities(search=search)
        return {
            "total": len(cities),
            "cities": cities
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/addresses/streets")
async def api_get_streets(
    city: str = Query(..., description="Назва міста"),
    search: Optional[str] = Query(None, description="Пошуковий запит для фільтрації вулиць")
):
    """
    Отримати список вулиць для міста
    
    Параметри:
    - city: назва міста (обов'язково)
    - search: опціональний пошуковий запит (наприклад: "вул. Героїв")
    
    Приклад: /api/v1/addresses/streets?city=Хмельницький&search=вул
    """
    try:
        streets = get_streets(city=city, search=search)
        
        if not streets:
            raise HTTPException(
                status_code=404,
                detail=f"Вулиці для міста '{city}' не знайдено"
            )
        
        return {
            "city": city,
            "total": len(streets),
            "streets": streets
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/addresses/houses")
async def api_get_houses(
    city: str = Query(..., description="Назва міста"),
    street: str = Query(..., description="Назва вулиці"),
    search: Optional[str] = Query(None, description="Пошуковий запит для фільтрації будинків")
):
    """
    Отримати список будинків для вулиці
    
    Параметри:
    - city: назва міста (обов'язково)
    - street: назва вулиці (обов'язково)
    - search: опціональний пошуковий запит (наприклад: "10")
    
    Приклад: /api/v1/addresses/houses?city=Хмельницький&street=вул. Героїв Майдану
    """
    try:
        houses = get_houses(city=city, street=street, search=search)
        
        if not houses:
            raise HTTPException(
                status_code=404,
                detail=f"Будинки для адреси '{city}, {street}' не знайдено"
            )
        
        return {
            "city": city,
            "street": street,
            "total": len(houses),
            "houses": houses
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/addresses/info")
async def api_get_address_info(
    city: str = Query(..., description="Назва міста"),
    street: str = Query(..., description="Назва вулиці"),
    house: str = Query(..., description="Номер будинку"),
    schedule_date: Optional[str] = Query(None, description="Дата графіка у форматі YYYY-MM-DD (опціонально)")
):
    """
    Отримати повну інформацію про адресу включаючи чергу та статус відключень
    
    Параметри:
    - city: назва міста (обов'язково)
    - street: назва вулиці (обов'язково)
    - house: номер будинку (обов'язково)
    - schedule_date: дата графіка у форматі YYYY-MM-DD (опціонально, за замовчуванням сьогодні)
    
    Приклад: /api/v1/addresses/info?city=Хмельницький&street=вул. Героїв Майдану&house=10&schedule_date=2026-01-26
    """
    from app.database import get_db
    from fastapi import Depends
    from sqlalchemy.orm import Session
    
    # Отримуємо БД
    db_gen = get_db()
    db = next(db_gen)
    
    try:
        info = get_address_info(city=city, street=street, house=house, db=db, schedule_date=schedule_date)
        
        if not info:
            raise HTTPException(
                status_code=404,
                detail=f"Адресу '{city}, {street}, {house}' не знайдено в базі"
            )
        
        return info
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/addresses/search")
async def api_search_addresses(
    query: str = Query(..., min_length=2, description="Пошуковий запит"),
    limit: int = Query(50, ge=1, le=100, description="Максимальна кількість результатів")
):
    """
    Глобальний пошук адрес по базі
    
    Параметри:
    - query: пошуковий запит (мінімум 2 символи)
    - limit: максимальна кількість результатів (за замовчуванням 50, макс 100)
    
    Приклад: /api/v1/addresses/search?query=Хмельницький Героїв
    """
    try:
        results = search_addresses(query=query, limit=limit)
        
        return {
            "query": query,
            "total": len(results),
            "results": results
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/addresses/statistics")
async def api_get_statistics():
    """
    Отримати статистику по базі адрес
    
    Повертає загальну кількість міст, вулиць та будинків
    
    Приклад: /api/v1/addresses/statistics
    """
    try:
        stats = get_statistics()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/addresses/reload")
async def api_reload_addresses():
    """
    Примусово перезавантажити базу адрес з GitHub
    
    Використовується коли база адрес оновлена на GitHub
    """
    try:
        reload_addresses()
        stats = get_statistics()
        
        return {
            "message": "База адрес успішно перезавантажена",
            "statistics": stats
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
