"""
API endpoints для графіків відключень
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, date, timedelta
from pydantic import BaseModel
import json
import pytz

from app.database import get_db
from app.scraper.schedule_parser import fetch_schedule_images, parse_queue_schedule
from app import crud_schedules

# Київський часовий пояс
KYIV_TZ = pytz.timezone('Europe/Kiev')

router = APIRouter()


class ScheduleResponse(BaseModel):
    """Модель відповіді з графіком"""
    id: int
    date: date
    image_url: str
    version: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class OutageInterval(BaseModel):
    """Інтервал відключення"""
    start_hour: float  # Може бути 17.5 для 17:30
    end_hour: float
    label: str  # Наприклад "08:00 - 12:00"


class OutageStatusResponse(BaseModel):
    """Статус відключення"""
    has_power: bool
    queue: str
    message: str
    schedule_date: date | None = None
    schedule_image_url: str | None = None
    upcoming_outages: List[OutageInterval] = []


@router.get("/schedules/current", response_model=List[ScheduleResponse])
async def get_current_schedules(
    limit: int = 7,
    db: Session = Depends(get_db)
):
    """
    Отримати поточні графіки відключень (останні N днів)
    """
    schedules = crud_schedules.get_active_schedules(db, limit=limit)
    return schedules


@router.get("/schedules/latest", response_model=ScheduleResponse)
async def get_latest_schedule(db: Session = Depends(get_db)):
    """
    Отримати найновіший графік
    """
    schedule = crud_schedules.get_latest_schedule(db)
    if not schedule:
        raise HTTPException(status_code=404, detail="Графіки не знайдено")
    return schedule


@router.get("/schedules/status", response_model=OutageStatusResponse)
async def get_outage_status(
    city: str,
    street: str,
    house: str,
    schedule_date: Optional[str] = Query(None, description="Дата графіка в форматі YYYY-MM-DD. Якщо не вказано - використовується сьогодні."),
    db: Session = Depends(get_db)
):
    """
    Перевірити статус відключення для адреси
    
    Використовує збережені розпарсені дані графіків для визначення поточного статусу.
    Можна вказати дату для отримання графіка на конкретний день.
    """
    from app.services.address_service import get_address_info
    import logging
    
    logger = logging.getLogger(__name__)
    
    # Отримуємо чергу для адреси
    address_info = get_address_info(city, street, house)
    if not address_info:
        raise HTTPException(status_code=404, detail="Адресу не знайдено")
    
    queue = address_info.get("queue", "Невідомо")
    
    # Визначаємо дату для пошуку графіка
    if schedule_date:
        try:
            target_date = datetime.strptime(schedule_date, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="Невірний формат дати. Використовуйте YYYY-MM-DD")
    else:
        target_date = date.today()
    
    # Отримуємо графік для вказаної дати
    schedule = crud_schedules.get_schedule_by_date(db, target_date)
    
    if not schedule:
        return OutageStatusResponse(
            has_power=True,
            queue=queue,
            message=f"Графік на {target_date.strftime('%d.%m.%Y')} відсутній",
            schedule_date=target_date,
            schedule_image_url=None,
            upcoming_outages=[]
        )
    
    # Використовуємо parsed_data з БД замість парсингу на льоту
    try:
        if schedule.parsed_data:
            # Використовуємо вже розпарсені дані
            queue_schedules = json.loads(schedule.parsed_data) if isinstance(schedule.parsed_data, str) else schedule.parsed_data
            logger.info(f"Використання parsed_data з БД для {target_date}: {list(queue_schedules.keys())}")
        elif schedule.recognized_text:
            # Fallback: парсимо текст якщо parsed_data немає
            queue_schedules = parse_queue_schedule(schedule.recognized_text)
            logger.info(f"Парсинг recognized_text для {target_date}: {list(queue_schedules.keys())}")
        else:
            return OutageStatusResponse(
                has_power=True,
                queue=queue,
                message=f"Ваша черга: {queue}. Графік на {target_date.strftime('%d.%m.%Y')} ще не розпізнано.",
                schedule_date=schedule.date,
                schedule_image_url=schedule.image_url,
                upcoming_outages=[]
            )
        
        # Конвертуємо списки в кортежі для сумісності
        queue_schedules_tuples = {}
        for q, intervals in queue_schedules.items():
            queue_schedules_tuples[q] = [tuple(i) if isinstance(i, list) else i for i in intervals]
        
        # Отримуємо інтервали для черги користувача
        queue_clean = queue.replace(". підчерга", "").replace(" підчерга", "").strip()
        user_intervals = queue_schedules_tuples.get(queue_clean, []) or queue_schedules_tuples.get(queue, [])
        
        if not user_intervals:
            logger.warning(f"Не знайдено інтервалів для черги {queue} (очищено: {queue_clean})")
            return OutageStatusResponse(
                has_power=True,
                queue=queue,
                message=f"Ваша черга: {queue}. Інформація про відключення для цієї черги не знайдена в графіку на {target_date.strftime('%d.%m.%Y')}.",
                schedule_date=schedule.date,
                schedule_image_url=schedule.image_url,
                upcoming_outages=[]
            )
        
        # Формуємо ВСІ відключення за день
        all_outages = []
        current_interval = None
        next_outage = None
        
        # Поточна година (тільки для сьогодні)
        is_today = target_date == date.today()
        if is_today:
            # Використовуємо київський час
            now = datetime.now(KYIV_TZ)
            current_hour = now.hour + now.minute / 60.0
            logger.info(f"Поточний київський час: {now.strftime('%H:%M')}, час в годинах: {current_hour:.2f}, інтервали черги {queue}: {user_intervals}")
        else:
            current_hour = -1  # Для майбутніх днів завжди "не зараз"
        
        # Перевіряємо чи зараз відключення (тільки для сьогодні)
        is_outage_now = False
        if is_today:
            is_outage_now = any(start <= current_hour < end for start, end in user_intervals)
        
        has_power = not is_outage_now
        
        for start, end in user_intervals:
            # Перевіряємо чи це поточне відключення
            if is_today and start <= current_hour < end:
                current_interval = (start, end)
            
            # Перше майбутнє відключення
            if is_today and next_outage is None and start > current_hour:
                next_outage = (start, end)
            
            # Форматуємо час з урахуванням хвилин
            start_h = int(start)
            start_m = int((start - start_h) * 60)
            end_h = int(end)
            end_m = int((end - end_h) * 60)
            
            label = f"{start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d}"
            
            all_outages.append(OutageInterval(
                start_hour=start,
                end_hour=end,
                label=label
            ))
        
        # Сортуємо за часом початку
        all_outages.sort(key=lambda x: x.start_hour)
        
        # Формуємо повідомлення
        if is_today:
            if is_outage_now:
                if current_interval:
                    end_h = int(current_interval[1])
                    end_m = int((current_interval[1] - end_h) * 60)
                    message = f"⚠️ Відключення! Очікується до {end_h:02d}:{end_m:02d}"
                else:
                    message = "⚠️ Зараз відключення електроенергії"
            else:
                if next_outage:
                    start_h = int(next_outage[0])
                    start_m = int((next_outage[0] - start_h) * 60)
                    end_h = int(next_outage[1])
                    end_m = int((next_outage[1] - end_h) * 60)
                    message = f"✅ Електроенергія є. Наступне відключення: {start_h:02d}:{start_m:02d} - {end_h:02d}:{end_m:02d}"
                else:
                    message = "✅ Електроенергія є. Сьогодні більше відключень немає"
        else:
            # Для майбутніх днів
            if all_outages:
                message = f"Графік на {target_date.strftime('%d.%m.%Y')}: {len(all_outages)} відключень"
            else:
                message = f"На {target_date.strftime('%d.%m.%Y')} відключень не заплановано"
        
        logger.info(f"Статус для черги {queue} на {target_date}: has_power={has_power}, message={message}, all_outages={len(all_outages)}")
        
        return OutageStatusResponse(
            has_power=has_power,
            queue=queue,
            message=message,
            schedule_date=schedule.date,
            schedule_image_url=schedule.image_url,
            upcoming_outages=all_outages
        )
        
    except Exception as e:
        logger.error(f"Помилка парсингу графіка: {e}", exc_info=True)
        return OutageStatusResponse(
            has_power=True,
            queue=queue,
            message=f"Ваша черга: {queue}. Помилка обробки графіка.",
            schedule_date=schedule.date,
            schedule_image_url=schedule.image_url,
            upcoming_outages=[]
        )
