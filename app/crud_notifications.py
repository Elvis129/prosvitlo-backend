"""
CRUD операції для роботи з токенами пристроїв, повідомленнями та адресами користувачів
"""

from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone
from typing import List, Optional
import json
import logging

from app.models import DeviceToken, Notification, UserAddress

logger = logging.getLogger(__name__)


# ============= DeviceToken CRUD =============

def create_or_update_device_token(
    db: Session,
    device_id: str,
    fcm_token: str,
    platform: str
) -> DeviceToken:
    """
    Створює новий або оновлює існуючий токен пристрою
    Якщо fcm_token вже існує в іншого пристрою - видаляє старий запис
    """
    # Перевіряємо чи існує токен для цього пристрою
    device_token = db.query(DeviceToken).filter(
        DeviceToken.device_id == device_id
    ).first()
    
    # Перевіряємо чи цей fcm_token не використовується іншим пристроєм
    existing_token_by_fcm = db.query(DeviceToken).filter(
        DeviceToken.fcm_token == fcm_token,
        DeviceToken.device_id != device_id
    ).first()
    
    if existing_token_by_fcm:
        logger.info(f"FCM токен вже використовується пристроєм {existing_token_by_fcm.device_id}, видаляємо старий запис")
        db.delete(existing_token_by_fcm)
        db.commit()
    
    if device_token:
        # Оновлюємо існуючий токен
        device_token.fcm_token = fcm_token
        device_token.platform = platform
        device_token.updated_at = datetime.now(timezone.utc)
        logger.info(f"Updated FCM token for device: {device_id}")
    else:
        # Створюємо новий токен
        device_token = DeviceToken(
            device_id=device_id,
            fcm_token=fcm_token,
            platform=platform,
            notifications_enabled=True
        )
        db.add(device_token)
        logger.info(f"Created new device token: {device_id}")
    
    db.commit()
    db.refresh(device_token)
    return device_token


def get_device_token(db: Session, device_id: str) -> Optional[DeviceToken]:
    """
    Отримує токен пристрою за device_id
    """
    return db.query(DeviceToken).filter(
        DeviceToken.device_id == device_id
    ).first()


def delete_device_token(db: Session, device_id: str) -> bool:
    """
    Видаляє токен пристрою (при видаленні додатку)
    """
    device_token = db.query(DeviceToken).filter(
        DeviceToken.device_id == device_id
    ).first()
    
    if device_token:
        db.delete(device_token)
        db.commit()
        logger.info(f"Deleted device token: {device_id}")
        return True
    
    return False


def toggle_notifications(db: Session, device_id: str, enabled: bool) -> Optional[DeviceToken]:
    """
    Вмикає/вимикає сповіщення для пристрою
    """
    device_token = db.query(DeviceToken).filter(
        DeviceToken.device_id == device_id
    ).first()
    
    if device_token:
        device_token.notifications_enabled = enabled
        device_token.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(device_token)
        logger.info(f"Notifications {'enabled' if enabled else 'disabled'} for device: {device_id}")
        return device_token
    
    return None


# ============= Notification CRUD =============

def create_notification(
    db: Session,
    notification_type: str,
    title: str,
    body: str,
    category: str = 'general',
    data: Optional[dict] = None,
    addresses: Optional[List[dict]] = None,
    device_ids: Optional[List[str]] = None
) -> Notification:
    """
    Створює новe повідомлення в історії
    category: 'general', 'outage', 'restored', 'scheduled', 'emergency'
    device_ids: Список device_id користувачів, яким відправлено повідомлення
    """
    notification = Notification(
        notification_type=notification_type,
        category=category,
        title=title,
        body=body,
        data=json.dumps(data) if data else None,
        addresses=json.dumps(addresses) if addresses else None,
        device_ids=json.dumps(device_ids) if device_ids else None
    )
    
    db.add(notification)
    db.commit()
    db.refresh(notification)
    
    logger.info(f"Created notification: {notification.id} ({notification_type})")
    return notification


def get_recent_notifications(
    db: Session,
    limit: int = 50,
    notification_type: Optional[str] = None
) -> List[Notification]:
    """
    Отримує останні повідомлення
    """
    query = db.query(Notification)
    
    if notification_type:
        query = query.filter(Notification.notification_type == notification_type)
    
    # Фільтруємо тільки за останні 5 днів (UTC)
    five_days_ago = datetime.now(timezone.utc) - timedelta(days=5)
    query = query.filter(Notification.created_at >= five_days_ago)
    
    notifications = query.order_by(
        Notification.created_at.desc()
    ).limit(limit).all()
    
    return notifications


def get_user_notifications(
    db: Session,
    device_id: str,
    limit: int = 50
) -> List[Notification]:
    """
    Отримує історію повідомлень для конкретного користувача
    Включає:
    - Загальні повідомлення (type='all')
    - Персональні повідомлення (де device_id є у списку)
    """
    five_days_ago = datetime.now(timezone.utc) - timedelta(days=5)
    
    # Отримуємо всі повідомлення за останні 5 днів
    all_notifications = db.query(Notification).filter(
        Notification.created_at >= five_days_ago
    ).order_by(
        Notification.created_at.desc()
    ).all()
    
    # Фільтруємо повідомлення для користувача
    user_notifications = []
    for notif in all_notifications:
        # Загальні повідомлення
        if notif.notification_type == 'all':
            user_notifications.append(notif)
        # Персональні повідомлення
        elif notif.device_ids:
            try:
                device_ids = json.loads(notif.device_ids)
                if device_id in device_ids:
                    user_notifications.append(notif)
            except (json.JSONDecodeError, TypeError):
                continue
    
    return user_notifications[:limit]


def cleanup_old_notifications(db: Session) -> int:
    """
    Видаляє повідомлення старіші за 5 днів
    """
    five_days_ago = datetime.now(timezone.utc) - timedelta(days=5)
    
    deleted_count = db.query(Notification).filter(
        Notification.created_at < five_days_ago
    ).delete()
    
    db.commit()
    
    if deleted_count > 0:
        logger.info(f"Deleted {deleted_count} old notifications")
    
    return deleted_count


# ============= UserAddress CRUD =============

def add_user_address(
    db: Session,
    device_id: str,
    city: str,
    street: str,
    house_number: str,
    queue: Optional[str] = None
) -> UserAddress:
    """
    Додає адресу до збережених адрес користувача
    """
    # Перевіряємо чи вже існує така адреса для цього пристрою
    existing = db.query(UserAddress).filter(
        UserAddress.device_id == device_id,
        UserAddress.city == city,
        UserAddress.street == street,
        UserAddress.house_number == house_number
    ).first()
    
    if existing:
        # Оновлюємо чергу якщо змінилася
        if queue and existing.queue != queue:
            existing.queue = queue
            db.commit()
            db.refresh(existing)
            logger.info(f"Updated queue for device {device_id}: {city}, {street}, {house_number} -> {queue}")
        else:
            logger.info(f"Address already exists for device {device_id}: {city}, {street}, {house_number}")
        return existing
    
    # Створюємо нову адресу
    user_address = UserAddress(
        device_id=device_id,
        city=city,
        street=street,
        house_number=house_number,
        queue=queue
    )
    
    db.add(user_address)
    db.commit()
    db.refresh(user_address)
    
    logger.info(f"Added address for device {device_id}: {city}, {street}, {house_number} (queue: {queue})")
    return user_address


def get_user_addresses(db: Session, device_id: str) -> List[UserAddress]:
    """
    Отримує всі збережені адреси користувача
    """
    return db.query(UserAddress).filter(
        UserAddress.device_id == device_id
    ).all()


def delete_user_address(
    db: Session,
    device_id: str,
    city: str,
    street: str,
    house_number: str
) -> bool:
    """
    Видаляє адресу зі збережених адрес користувача
    """
    user_address = db.query(UserAddress).filter(
        UserAddress.device_id == device_id,
        UserAddress.city == city,
        UserAddress.street == street,
        UserAddress.house_number == house_number
    ).first()
    
    if user_address:
        db.delete(user_address)
        db.commit()
        logger.info(f"Deleted address for device {device_id}: {city}, {street}, {house_number}")
        return True
    
    return False


def delete_all_user_addresses(db: Session, device_id: str) -> int:
    """
    Видаляє всі збережені адреси користувача (при видаленні додатку)
    """
    deleted_count = db.query(UserAddress).filter(
        UserAddress.device_id == device_id
    ).delete()
    
    db.commit()
    
    if deleted_count > 0:
        logger.info(f"Deleted {deleted_count} addresses for device: {device_id}")
    
    return deleted_count
