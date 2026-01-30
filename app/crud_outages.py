"""
CRUD операції для аварійних та планових відключень
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_
from app import models
from typing import List, Optional
from datetime import datetime
import logging
import pytz

import re

# Київська часова зона
KYIV_TZ = pytz.timezone('Europe/Kiev')

def normalize_city_name(city: str) -> str:
    """
    Нормалізує назву міста, видаляючи префікси с., м., смт. тощо
    """
    city = city.strip()
    city = re.sub(r'^(с\.|м\.|смт\.|село |місто )\s*', '', city, flags=re.IGNORECASE)
    return city.strip()

logger = logging.getLogger(__name__)


def create_emergency_outage(
    db: Session,
    rem_id: int,
    rem_name: str,
    city: str,
    street: str,
    house_numbers: str,
    work_type: str,
    created_date: datetime,
    start_time: datetime,
    end_time: datetime
) -> models.EmergencyOutage:
    """
    Створює новий запис аварійного відключення
    """
    outage = models.EmergencyOutage(
        rem_id=rem_id,
        rem_name=rem_name,
        city=city,
        street=street,
        house_numbers=house_numbers,
        work_type=work_type,
        created_date=created_date,
        start_time=start_time,
        end_time=end_time,
        is_active=True
    )
    db.add(outage)
    db.commit()
    db.refresh(outage)
    return outage


def create_planned_outage(
    db: Session,
    rem_id: int,
    rem_name: str,
    city: str,
    street: str,
    house_numbers: str,
    work_type: str,
    created_date: datetime,
    start_time: datetime,
    end_time: datetime
) -> models.PlannedOutage:
    """
    Створює новий запис планового відключення
    """
    outage = models.PlannedOutage(
        rem_id=rem_id,
        rem_name=rem_name,
        city=city,
        street=street,
        house_numbers=house_numbers,
        work_type=work_type,
        created_date=created_date,
        start_time=start_time,
        end_time=end_time,
        is_active=True
    )
    db.add(outage)
    db.commit()
    db.refresh(outage)
    return outage


def get_active_emergency_outages_for_address(
    db: Session,
    city: str,
    street: str,
    house_number: str,
    region: str = None
) -> List[models.EmergencyOutage]:
    """
    Отримує активні аварійні відключення для конкретної адреси
    
    Args:
        region: (опціонально) Фільтр по області (hoe/voe)
    """
    # Нормалізуємо назву міста
    city_normalized = normalize_city_name(city)
    
    # Використовуємо київський час для порівняння
    now = datetime.now(KYIV_TZ).replace(tzinfo=None)
    
    # Знаходимо всі відключення для цього міста та вулиці
    query = db.query(models.EmergencyOutage).filter(
        and_(
            (models.EmergencyOutage.city == city) | (models.EmergencyOutage.city == "с. " + city_normalized) | (models.EmergencyOutage.city == "м. " + city_normalized) | (models.EmergencyOutage.city == city_normalized),
            models.EmergencyOutage.street == street,
            models.EmergencyOutage.is_active == True,
            models.EmergencyOutage.start_time <= now,
            models.EmergencyOutage.end_time >= now
        )
    )
    
    # Фільтруємо по регіону якщо вказано
    if region:
        query = query.filter(models.EmergencyOutage.region == region)
    
    outages = query.all()
    
    # Фільтруємо по номеру будинку
    result = []
    for outage in outages:
        # Перевіряємо чи номер будинку є в списку
        house_numbers_list = [h.strip() for h in outage.house_numbers.split(',')]
        if house_number in house_numbers_list:
            result.append(outage)
    
    return result


def get_active_planned_outages_for_address(
    db: Session,
    city: str,
    street: str,
    house_number: str,
    region: str = None
) -> List[models.PlannedOutage]:
    """
    Отримує активні планові відключення для конкретної адреси
    """
    # Нормалізуємо назву міста
    city_normalized = normalize_city_name(city)
    
    # Використовуємо київський час для порівняння
    now = datetime.now(KYIV_TZ).replace(tzinfo=None)
    
    # Знаходимо всі відключення для цього міста та вулиці
    query = db.query(models.PlannedOutage).filter(
        and_(
            (models.PlannedOutage.city == city) | (models.PlannedOutage.city == "с. " + city_normalized) | (models.PlannedOutage.city == "м. " + city_normalized) | (models.PlannedOutage.city == city_normalized),
            models.PlannedOutage.street == street,
            models.PlannedOutage.is_active == True,
            models.PlannedOutage.start_time <= now,
            models.PlannedOutage.end_time >= now
        )
    )
    
    # Фільтруємо по регіону якщо вказано
    if region:
        query = query.filter(models.PlannedOutage.region == region)
    
    outages = query.all()
    
    # Фільтруємо по номеру будинку
    result = []
    for outage in outages:
        # Перевіряємо чи номер будинку є в списку
        house_numbers_list = [h.strip() for h in outage.house_numbers.split(',')]
        if house_number in house_numbers_list:
            result.append(outage)
    
    return result


def get_upcoming_emergency_outages_for_address(
    db: Session,
    city: str,
    street: str,
    house_number: str,
    region: str = None
) -> List[models.EmergencyOutage]:
    """
    Отримує майбутні аварійні відключення для конкретної адреси
    """
    # Нормалізуємо назву міста
    city_normalized = normalize_city_name(city)
    
    # Використовуємо київський час для порівняння
    now = datetime.now(KYIV_TZ).replace(tzinfo=None)
    
    query = db.query(models.EmergencyOutage).filter(
        and_(
            (models.EmergencyOutage.city == city) | (models.EmergencyOutage.city == "с. " + city_normalized) | (models.EmergencyOutage.city == "м. " + city_normalized) | (models.EmergencyOutage.city == city_normalized),
            models.EmergencyOutage.street == street,
            models.EmergencyOutage.is_active == True,
            models.EmergencyOutage.start_time > now
        )
    )
    
    # Фільтруємо по регіону якщо вказано
    if region:
        query = query.filter(models.EmergencyOutage.region == region)
    
    outages = query.order_by(models.EmergencyOutage.start_time).all()
    
    # Фільтруємо по номеру будинку
    result = []
    for outage in outages:
        house_numbers_list = [h.strip() for h in outage.house_numbers.split(',')]
        if house_number in house_numbers_list:
            result.append(outage)
    
    return result


def get_upcoming_planned_outages_for_address(
    db: Session,
    city: str,
    street: str,
    house_number: str,
    region: str = None
) -> List[models.PlannedOutage]:
    """
    Отримує майбутні планові відключення для конкретної адреси
    """
    # Нормалізуємо назву міста
    city_normalized = normalize_city_name(city)
    
    # Використовуємо київський час для порівняння
    now = datetime.now(KYIV_TZ).replace(tzinfo=None)
    
    query = db.query(models.PlannedOutage).filter(
        and_(
            (models.PlannedOutage.city == city) | (models.PlannedOutage.city == "с. " + city_normalized) | (models.PlannedOutage.city == "м. " + city_normalized) | (models.PlannedOutage.city == city_normalized),
            models.PlannedOutage.street == street,
            models.PlannedOutage.is_active == True,
            models.PlannedOutage.start_time > now
        )
    )
    
    # Фільтруємо по регіону якщо вказано
    if region:
        query = query.filter(models.PlannedOutage.region == region)
    
    outages = query.order_by(models.PlannedOutage.start_time).all()
    
    # Фільтруємо по номеру будинку
    result = []
    for outage in outages:
        house_numbers_list = [h.strip() for h in outage.house_numbers.split(',')]
        if house_number in house_numbers_list:
            result.append(outage)
    
    return result


def deactivate_old_emergency_outages(db: Session) -> int:
    """
    Деактивує аварійні відключення, час яких минув
    """
    # Використовуємо київський час для порівняння
    now = datetime.now(KYIV_TZ).replace(tzinfo=None)
    
    count = db.query(models.EmergencyOutage).filter(
        and_(
            models.EmergencyOutage.is_active == True,
            models.EmergencyOutage.end_time < now
        )
    ).update({"is_active": False})
    
    db.commit()
    logger.info(f"Деактивовано {count} старих аварійних відключень")
    return count


def deactivate_old_planned_outages(db: Session) -> int:
    """
    Деактивує планові відключення, час яких минув
    """
    # Використовуємо київський час для порівняння
    now = datetime.now(KYIV_TZ).replace(tzinfo=None)
    
    count = db.query(models.PlannedOutage).filter(
        and_(
            models.PlannedOutage.is_active == True,
            models.PlannedOutage.end_time < now
        )
    ).update({"is_active": False})
    
    db.commit()
    logger.info(f"Деактивовано {count} старих планових відключень")
    return count


def clear_all_active_emergency_outages(db: Session) -> int:
    """
    Деактивує всі активні аварійні відключення (перед оновленням)
    """
    count = db.query(models.EmergencyOutage).filter(
        models.EmergencyOutage.is_active == True
    ).update({"is_active": False})
    
    db.commit()
    logger.info(f"Деактивовано всі аварійні відключення: {count}")
    return count


def clear_all_active_planned_outages(db: Session) -> int:
    """
    Деактивує всі активні планові відключення (перед оновленням)
    """
    count = db.query(models.PlannedOutage).filter(
        models.PlannedOutage.is_active == True
    ).update({"is_active": False})
    
    db.commit()
    logger.info(f"Деактивовано всі планові відключення: {count}")
    return count
