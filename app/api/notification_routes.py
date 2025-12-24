"""
API endpoints для управління push-повідомленнями
"""
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, field_serializer
import json

from app.database import get_db
from app import crud_notifications
from app.services import firebase_service

router = APIRouter()


# ============= Request/Response Models =============

class DeviceTokenRequest(BaseModel):
    """Модель для реєстрації FCM токену"""
    device_id: str
    fcm_token: str
    platform: str  # "android" або "ios"


class DeviceTokenResponse(BaseModel):
    """Модель відповіді з інформацією про токен"""
    id: int
    device_id: str
    notifications_enabled: bool
    platform: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class NotificationToggleRequest(BaseModel):
    """Модель для вмикання/вимикання сповіщень"""
    device_id: str
    enabled: bool


class UserAddressRequest(BaseModel):
    """Модель для додавання адреси користувача"""
    device_id: str
    city: str
    street: str
    house_number: str


class UserAddressResponse(BaseModel):
    """Модель відповіді з адресою користувача"""
    id: int
    device_id: str
    city: str
    street: str
    house_number: str
    created_at: datetime
    
    class Config:
        from_attributes = True


class NotificationResponse(BaseModel):
    """Модель відповіді з повідомленням"""
    id: int
    notification_type: str
    category: str
    title: str
    body: str
    data: Optional[str] = None
    addresses: Optional[str] = None
    created_at: datetime
    
    @field_serializer('created_at')
    def serialize_datetime(self, dt: datetime, _info):
        """Серіалізуємо datetime з UTC маркером"""
        if dt.tzinfo is None:
            # Якщо без timezone - додаємо UTC
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    
    class Config:
        from_attributes = True


class SendNotificationRequest(BaseModel):
    """Модель для ручної відправки повідомлення"""
    title: str
    body: str
    notification_type: str  # "all" або "address"
    category: str = 'general'  # 'general', 'outage', 'restored', 'scheduled', 'emergency'
    addresses: Optional[List[dict]] = None  # Для type="address"
    data: Optional[dict] = None


# ============= Device Token Endpoints =============

@router.post("/tokens/register", response_model=DeviceTokenResponse, tags=["Notifications"])
async def register_device_token(
    request: DeviceTokenRequest,
    db: Session = Depends(get_db)
):
    """
    Реєстрація або оновлення FCM токену пристрою
    """
    try:
        device_token = crud_notifications.create_or_update_device_token(
            db=db,
            device_id=request.device_id,
            fcm_token=request.fcm_token,
            platform=request.platform
        )
        return device_token
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to register token: {str(e)}")


@router.delete("/tokens/unregister/{device_id}", tags=["Notifications"])
async def unregister_device_token(
    device_id: str,
    db: Session = Depends(get_db)
):
    """
    Видалення FCM токену пристрою (при видаленні додатку)
    """
    try:
        # Видаляємо токен
        deleted = crud_notifications.delete_device_token(db, device_id)
        
        # Видаляємо всі збережені адреси користувача
        crud_notifications.delete_all_user_addresses(db, device_id)
        
        if deleted:
            return {"message": "Device token and addresses deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Device token not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to unregister token: {str(e)}")


@router.get("/tokens/{device_id}", response_model=DeviceTokenResponse, tags=["Notifications"])
async def get_device_token_info(
    device_id: str,
    db: Session = Depends(get_db)
):
    """
    Отримання інформації про токен пристрою
    """
    device_token = crud_notifications.get_device_token(db, device_id)
    
    if not device_token:
        raise HTTPException(status_code=404, detail="Device token not found")
    
    return device_token


@router.patch("/tokens/toggle", response_model=DeviceTokenResponse, tags=["Notifications"])
async def toggle_device_notifications(
    request: NotificationToggleRequest,
    db: Session = Depends(get_db)
):
    """
    Вмикання/вимикання сповіщень для пристрою
    """
    device_token = crud_notifications.toggle_notifications(
        db=db,
        device_id=request.device_id,
        enabled=request.enabled
    )
    
    if not device_token:
        raise HTTPException(status_code=404, detail="Device token not found")
    
    return device_token


# ============= User Address Endpoints =============

@router.post("/addresses/add", response_model=UserAddressResponse, tags=["Notifications"])
async def add_saved_address(
    request: UserAddressRequest,
    db: Session = Depends(get_db)
):
    """
    Додавання адреси до збережених адрес користувача
    """
    try:
        user_address = crud_notifications.add_user_address(
            db=db,
            device_id=request.device_id,
            city=request.city,
            street=request.street,
            house_number=request.house_number
        )
        return user_address
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add address: {str(e)}")


@router.get("/addresses/{device_id}", response_model=List[UserAddressResponse], tags=["Notifications"])
async def get_saved_addresses(
    device_id: str,
    db: Session = Depends(get_db)
):
    """
    Отримання всіх збережених адрес користувача
    """
    addresses = crud_notifications.get_user_addresses(db, device_id)
    return addresses


@router.delete("/addresses/remove", tags=["Notifications"])
async def remove_saved_address(
    request: UserAddressRequest,
    db: Session = Depends(get_db)
):
    """
    Видалення адреси зі збережених адрес користувача
    """
    deleted = crud_notifications.delete_user_address(
        db=db,
        device_id=request.device_id,
        city=request.city,
        street=request.street,
        house_number=request.house_number
    )
    
    if deleted:
        return {"message": "Address removed successfully"}
    else:
        raise HTTPException(status_code=404, detail="Address not found")


# ============= Notification History Endpoints =============

@router.get("/notifications", response_model=List[NotificationResponse], tags=["Notifications"])
async def get_notifications(
    limit: int = 50,
    notification_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Отримання історії повідомлень (останні 5 днів)
    """
    notifications = crud_notifications.get_recent_notifications(
        db=db,
        limit=limit,
        notification_type=notification_type
    )
    return notifications


@router.post("/notifications/send", tags=["Notifications"])
async def send_notification(
    request: SendNotificationRequest,
    db: Session = Depends(get_db)
):
    """
    Ручна відправка push-повідомлення (для тестування або адмін-панелі)
    """
    try:
        # Ініціалізуємо Firebase якщо потрібно
        
        # Зберігаємо повідомлення в історію
        notification = crud_notifications.create_notification(
            db=db,
            notification_type=request.notification_type,
            category=request.category,
            title=request.title,
            body=request.body,
            data=request.data,
            addresses=request.addresses
        )
        
        # Відправляємо push
        if request.notification_type == "all":
            result = firebase_service.send_to_all_users(
                db=db,
                title=request.title,
                body=request.body,
                data=request.data
            )
        elif request.notification_type == "address" and request.addresses:
            # Відправляємо для кожної адреси окремо
            total_success = 0
            total_failed = 0
            
            for address in request.addresses:
                result = firebase_service.send_to_address_users(
                    db=db,
                    city=address.get("city"),
                    street=address.get("street"),
                    house_number=address.get("house_number"),
                    title=request.title,
                    body=request.body,
                    data=request.data
                )
                total_success += result['success']
                total_failed += result['failed']
            
            result = {'success': total_success, 'failed': total_failed}
        else:
            raise HTTPException(
                status_code=400,
                detail="For type='address', addresses list is required"
            )
        
        return {
            "message": "Notification sent",
            "notification_id": notification.id,
            "result": result
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send notification: {str(e)}")


@router.post("/notifications/cleanup", tags=["Notifications"])
async def cleanup_notifications(
    db: Session = Depends(get_db)
):
    """
    Видалення повідомлень старіших за 5 днів
    """
    try:
        deleted_count = crud_notifications.cleanup_old_notifications(db)
        return {
            "message": f"Deleted {deleted_count} old notifications"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to cleanup notifications: {str(e)}")


@router.delete("/notifications/clear-all", tags=["Notifications"])
async def clear_all_notifications(
    db: Session = Depends(get_db)
):
    """
    Видалення ВСІХ повідомлень з бази даних (для адміністрування)
    Використовується для очищення тестових повідомлень
    """
    try:
        from app.models import Notification
        deleted_count = db.query(Notification).delete()
        db.commit()
        return {
            "message": f"All notifications cleared. Deleted {deleted_count} notifications"
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to clear notifications: {str(e)}")
