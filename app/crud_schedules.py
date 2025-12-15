"""
CRUD операції для графіків відключень
"""
from sqlalchemy.orm import Session
from sqlalchemy import desc
from datetime import date, datetime
from typing import List, Optional, Dict
from app.models import Schedule
import json


def create_schedule(
    db: Session,
    date: date,
    image_url: str,
    recognized_text: str = None,
    parsed_data: Dict = None,
    content_hash: str = None,
    version: str = "1.0.0"
) -> Schedule:
    """Створення нового графіка"""
    db_schedule = Schedule(
        date=date,
        image_url=image_url,
        recognized_text=recognized_text,
        parsed_data=json.dumps(parsed_data) if parsed_data else None,
        content_hash=content_hash,
        version=version,
        is_active=True
    )
    db.add(db_schedule)
    db.commit()
    db.refresh(db_schedule)
    return db_schedule


def get_schedule_by_date(db: Session, date_val: date) -> Optional[Schedule]:
    """Отримання графіка за датою"""
    return db.query(Schedule).filter(
        Schedule.date == date_val,
        Schedule.is_active == True
    ).first()


def get_active_schedules(db: Session, limit: int = 7) -> List[Schedule]:
    """Отримання активних графіків (останні N днів)"""
    return db.query(Schedule).filter(
        Schedule.is_active == True
    ).order_by(desc(Schedule.date)).limit(limit).all()


def get_latest_schedule(db: Session) -> Optional[Schedule]:
    """Отримання найновішого графіка"""
    return db.query(Schedule).filter(
        Schedule.is_active == True
    ).order_by(desc(Schedule.date)).first()


def update_schedule(
    db: Session,
    schedule_id: int,
    image_url: str = None,
    recognized_text: str = None,
    parsed_data: Dict = None,
    content_hash: str = None,
    **kwargs
) -> Optional[Schedule]:
    """Оновлення графіка"""
    schedule = db.query(Schedule).filter(Schedule.id == schedule_id).first()
    if schedule:
        if image_url is not None:
            schedule.image_url = image_url
        if recognized_text is not None:
            schedule.recognized_text = recognized_text
        if parsed_data is not None:
            schedule.parsed_data = json.dumps(parsed_data)
        if content_hash is not None:
            schedule.content_hash = content_hash
        
        # Оновлюємо час змін
        schedule.updated_at = datetime.utcnow()
        
        # Інші параметри
        for key, value in kwargs.items():
            if hasattr(schedule, key):
                setattr(schedule, key, value)
        
        db.commit()
        db.refresh(schedule)
    return schedule


def deactivate_old_schedules(db: Session, days_old: int = 7):
    """Деактивація старих графіків"""
    from datetime import timedelta
    cutoff_date = date.today() - timedelta(days=days_old)
    db.query(Schedule).filter(
        Schedule.date < cutoff_date
    ).update({"is_active": False})
    db.commit()
