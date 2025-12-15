"""
CRUD операції для роботи з базою даних
"""

from sqlalchemy.orm import Session
from sqlalchemy import and_, desc
from typing import List, Optional
from app.models import Outage, User
from app.schemas import OutageCreate, UserRegister


# === CRUD операції для Outages ===

def create_outage(db: Session, outage: OutageCreate) -> Outage:
    """Створення нового запису про відключення"""
    db_outage = Outage(**outage.model_dump())
    db.add(db_outage)
    db.commit()
    db.refresh(db_outage)
    return db_outage


def get_outage_by_id(db: Session, outage_id: int) -> Optional[Outage]:
    """Отримання відключення за ID"""
    return db.query(Outage).filter(Outage.id == outage_id).first()


def get_outage_by_address(
    db: Session, 
    city: str, 
    street: str, 
    house_number: str
) -> Optional[Outage]:
    """Отримання відключення за адресою"""
    return db.query(Outage).filter(
        and_(
            Outage.city == city,
            Outage.street == street,
            Outage.house_number == house_number
        )
    ).first()


def get_all_outages(db: Session, skip: int = 0, limit: int = 100) -> List[Outage]:
    """Отримання всіх відключень з пагінацією"""
    return db.query(Outage).order_by(desc(Outage.updated_at)).offset(skip).limit(limit).all()


def get_outages_by_city(db: Session, city: str, skip: int = 0, limit: int = 100) -> List[Outage]:
    """Отримання всіх відключень для конкретного міста"""
    return db.query(Outage).filter(Outage.city == city).order_by(desc(Outage.updated_at)).offset(skip).limit(limit).all()


def get_outages_history(
    db: Session, 
    city: str, 
    street: str, 
    house_number: str,
    limit: int = 10
) -> List[Outage]:
    """Отримання історії відключень для конкретної адреси"""
    return db.query(Outage).filter(
        and_(
            Outage.city == city,
            Outage.street == street,
            Outage.house_number == house_number
        )
    ).order_by(desc(Outage.updated_at)).limit(limit).all()


def count_outages(db: Session) -> int:
    """Підрахунок загальної кількості відключень"""
    return db.query(Outage).count()


def update_outage(db: Session, outage_id: int, outage_data: OutageCreate) -> Optional[Outage]:
    """Оновлення інформації про відключення"""
    db_outage = get_outage_by_id(db, outage_id)
    if db_outage:
        for key, value in outage_data.model_dump().items():
            setattr(db_outage, key, value)
        db.commit()
        db.refresh(db_outage)
    return db_outage


def delete_outage(db: Session, outage_id: int) -> bool:
    """Видалення відключення"""
    db_outage = get_outage_by_id(db, outage_id)
    if db_outage:
        db.delete(db_outage)
        db.commit()
        return True
    return False


def upsert_outage(db: Session, outage_data: OutageCreate) -> Outage:
    """
    Створення нового відключення або оновлення існуючого
    Використовується при парсингу для уникнення дублікатів
    """
    existing = get_outage_by_address(
        db, 
        outage_data.city, 
        outage_data.street, 
        outage_data.house_number
    )
    
    if existing:
        # Оновлюємо існуючий запис
        for key, value in outage_data.model_dump().items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing
    else:
        # Створюємо новий запис
        return create_outage(db, outage_data)


# === CRUD операції для Users ===

def create_user(db: Session, user: UserRegister) -> User:
    """Створення нового користувача"""
    db_user = User(**user.model_dump())
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """Отримання користувача за ID"""
    return db.query(User).filter(User.id == user_id).first()


def get_user_by_token(db: Session, firebase_token: str) -> Optional[User]:
    """Отримання користувача за Firebase токеном"""
    return db.query(User).filter(User.firebase_token == firebase_token).first()


def get_users_by_address(
    db: Session, 
    city: str, 
    street: str, 
    house_number: str
) -> List[User]:
    """Отримання всіх користувачів за адресою (для відправки сповіщень)"""
    return db.query(User).filter(
        and_(
            User.city == city,
            User.street == street,
            User.house_number == house_number
        )
    ).all()


def get_all_users(db: Session, skip: int = 0, limit: int = 100) -> List[User]:
    """Отримання всіх користувачів"""
    return db.query(User).offset(skip).limit(limit).all()


def update_user_token(db: Session, user_id: int, new_token: str) -> Optional[User]:
    """Оновлення Firebase токену користувача"""
    db_user = get_user_by_id(db, user_id)
    if db_user:
        db_user.firebase_token = new_token
        db.commit()
        db.refresh(db_user)
    return db_user


def delete_user(db: Session, user_id: int) -> bool:
    """Видалення користувача"""
    db_user = get_user_by_id(db, user_id)
    if db_user:
        db.delete(db_user)
        db.commit()
        return True
    return False


def upsert_user(db: Session, user_data: UserRegister) -> User:
    """
    Створення нового користувача або оновлення існуючого
    Якщо токен вже існує, оновлюємо адресу
    """
    existing = get_user_by_token(db, user_data.firebase_token)
    
    if existing:
        # Оновлюємо адресу користувача
        existing.city = user_data.city
        existing.street = user_data.street
        existing.house_number = user_data.house_number
        db.commit()
        db.refresh(existing)
        return existing
    else:
        # Створюємо нового користувача
        return create_user(db, user_data)
