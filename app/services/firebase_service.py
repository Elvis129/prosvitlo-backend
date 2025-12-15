import os
import logging
from typing import List, Dict, Optional
from firebase_admin import credentials, messaging, initialize_app
import firebase_admin

logger = logging.getLogger(__name__)

# Глобальна змінна для Firebase app
_firebase_app = None


def initialize_firebase():
    """
    Ініціалізація Firebase Admin SDK
    """
    global _firebase_app
    
    try:
        # Перевіряємо чи вже ініціалізовано
        _firebase_app = firebase_admin.get_app()
        logger.info("Firebase app already initialized")
        return _firebase_app
    except ValueError:
        # App не існує, ініціалізуємо
        pass
    
    try:
        # Шлях до service account key
        service_account_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
            'serviceAccountKey.json'
        )
        
        if not os.path.exists(service_account_path):
            logger.error(f"Service account key not found at {service_account_path}")
            raise FileNotFoundError(f"Service account key not found at {service_account_path}")
        
        cred = credentials.Certificate(service_account_path)
        _firebase_app = initialize_app(cred)
        
        logger.info("Firebase Admin SDK initialized successfully")
        return _firebase_app
    
    except Exception as e:
        logger.error(f"Error initializing Firebase: {e}")
        raise


def send_push_notification(
    fcm_token: str,
    title: str,
    body: str,
    data: Optional[Dict[str, str]] = None
) -> bool:
    """
    Відправка push-повідомлення на один пристрій
    
    Args:
        fcm_token: Firebase Cloud Messaging токен пристрою
        title: Заголовок повідомлення
        body: Текст повідомлення
        data: Додаткові дані (опціонально)
    
    Returns:
        bool: True якщо відправлено успішно, False інакше
    """
    try:
        # Переконуємося що Firebase ініціалізовано
        if _firebase_app is None:
            initialize_firebase()
        
        # Створюємо повідомлення
        message = messaging.Message(
            notification=messaging.Notification(
                title=title,
                body=body,
            ),
            data=data or {},
            token=fcm_token,
            android=messaging.AndroidConfig(
                priority='high',
                notification=messaging.AndroidNotification(
                    icon='ic_stat_notification',
                    sound='default',
                ),
            ),
            apns=messaging.APNSConfig(
                payload=messaging.APNSPayload(
                    aps=messaging.Aps(
                        sound='default',
                        badge=1,
                    ),
                ),
            ),
        )
        
        # Відправляємо
        response = messaging.send(message)
        logger.info(f"Successfully sent message: {response}")
        return True
    
    except Exception as e:
        logger.error(f"Error sending push notification: {e}")
        return False


def send_push_to_multiple(
    fcm_tokens: List[str],
    title: str,
    body: str,
    data: Optional[Dict[str, str]] = None
) -> Dict[str, int]:
    """
    Відправка push-повідомлення на кілька пристроїв
    """
    if not fcm_tokens:
        return {'success': 0, 'failed': 0}
    
    try:
        # Переконуємося що Firebase ініціалізовано
        if _firebase_app is None:
            initialize_firebase()
        
        success_count = 0
        failed_count = 0
        
        # Відправляємо по одному токену
        for token in fcm_tokens:
            message = messaging.Message(
                notification=messaging.Notification(
                    title=title,
                    body=body,
                ),
                data=data or {},
                token=token,
                android=messaging.AndroidConfig(
                    priority='high',
                    notification=messaging.AndroidNotification(
                        icon='ic_stat_notification',
                        color='#F6D66E',
                        sound='default',
                    ),
                ),
                apns=messaging.APNSConfig(
                    payload=messaging.APNSPayload(
                        aps=messaging.Aps(
                            sound='default',
                            badge=1,
                        ),
                    ),
                ),
            )
            
            try:
                messaging.send(message)
                success_count += 1
            except Exception as e:
                logger.error(f"Failed to send to token {token[:20]}...: {e}")
                failed_count += 1
        
        logger.info(f"Sent broadcast notification: success={success_count}, failed={failed_count}")
        return {'success': success_count, 'failed': failed_count}
    
    except Exception as e:
        logger.error(f"Error sending multicast push notification: {e}")
        return {'success': 0, 'failed': len(fcm_tokens)}


def send_to_address_users(
    db,
    city: str,
    street: str,
    house_number: str,
    title: str,
    body: str,
    data: Optional[Dict[str, str]] = None
) -> Dict[str, int]:
    """
    Відправка повідомлення користувачам за адресою
    
    Args:
        db: Database session
        city: Місто
        street: Вулиця
        house_number: Номер будинку
        title: Заголовок повідомлення
        body: Текст повідомлення
        data: Додаткові дані (опціонально)
    
    Returns:
        dict: {'success': кількість успішних, 'failed': кількість невдалих}
    """
    from app.models import DeviceToken, UserAddress
    
    try:
        # Отримуємо device_id для цієї адреси
        user_addresses = db.query(UserAddress).filter(
            UserAddress.city == city,
            UserAddress.street == street,
            UserAddress.house_number == house_number
        ).all()
        
        if not user_addresses:
            logger.info(f"No users found for address: {city}, {street}, {house_number}")
            return {'success': 0, 'failed': 0}
        
        device_ids = [ua.device_id for ua in user_addresses]
        
        # Отримуємо токени для цих пристроїв (тільки з увімкненими сповіщеннями)
        tokens = db.query(DeviceToken).filter(
            DeviceToken.device_id.in_(device_ids),
            DeviceToken.notifications_enabled == True
        ).all()
        
        if not tokens:
            logger.info(f"No devices with enabled notifications for address: {city}, {street}, {house_number}")
            return {'success': 0, 'failed': 0}
        
        fcm_tokens = [token.fcm_token for token in tokens]
        
        # Відправляємо мультикаст повідомлення
        result = send_push_to_multiple(fcm_tokens, title, body, data)
        
        logger.info(f"Sent targeted notification to {len(fcm_tokens)} devices for address {city}, {street}, {house_number}: {result}")
        return result
    
    except Exception as e:
        logger.error(f"Error sending targeted notification: {e}")
        return {'success': 0, 'failed': 0}


def send_to_all_users(
    db,
    title: str,
    body: str,
    data: Optional[Dict[str, str]] = None
) -> Dict[str, int]:
    """
    Відправка повідомлення всім користувачам з увімкненими сповіщеннями
    
    Args:
        db: Database session
        title: Заголовок повідомлення
        body: Текст повідомлення
        data: Додаткові дані (опціонально)
    
    Returns:
        dict: {'success': кількість успішних, 'failed': кількість невдалих}
    """
    from app.models import DeviceToken
    
    try:
        # Отримуємо всі токени з увімкненими сповіщеннями
        tokens = db.query(DeviceToken).filter(
            DeviceToken.notifications_enabled == True
        ).all()
        
        if not tokens:
            logger.info("No devices with enabled notifications")
            return {'success': 0, 'failed': 0}
        
        fcm_tokens = [token.fcm_token for token in tokens]
        
        # Відправляємо мультикаст повідомлення
        result = send_push_to_multiple(fcm_tokens, title, body, data)
        
        logger.info(f"Sent broadcast notification to {len(fcm_tokens)} devices: {result}")
        return result
    
    except Exception as e:
        logger.error(f"Error sending broadcast notification: {e}")
        return {'success': 0, 'failed': 0}
