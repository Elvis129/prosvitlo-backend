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
        logger.info(f"📤 Відправка одиночного пушу на токен {fcm_token[:20]}...")
        logger.info(f"📝 Title: {title}")
        logger.info(f"📝 Body: {body[:100]}..." if len(body) > 100 else f"📝 Body: {body}")
        
        # Переконуємося що Firebase ініціалізовано
        if _firebase_app is None:
            logger.info("🔧 Ініціалізація Firebase...")
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
                    ),
                ),
            ),
        )
        
        # Відправляємо
        response = messaging.send(message)
        logger.info(f"✅ Успішно відправлено повідомлення: {response}")
        return True
    
    except Exception as e:
        logger.error(f"❌ Помилка відправки push-повідомлення: {e}")
        logger.exception("Детальна інформація про помилку:")
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
        logger.warning("⚠️ send_push_to_multiple: Немає токенів для відправки")
        return {'success': 0, 'failed': 0}
    
    try:
        logger.info(f"🚀 Початок відправки на {len(fcm_tokens)} токенів...")
        logger.info(f"📝 Title: {title}")
        logger.info(f"📝 Body: {body[:100]}..." if len(body) > 100 else f"📝 Body: {body}")
        
        # Переконуємося що Firebase ініціалізовано
        if _firebase_app is None:
            logger.info("🔧 Ініціалізація Firebase...")
            initialize_firebase()
        
        success_count = 0
        failed_count = 0
        invalid_tokens = []  # Збираємо невалідні токени
        
        # Відправляємо по одному токену
        for idx, token in enumerate(fcm_tokens, 1):
            logger.info(f"📤 Відправка {idx}/{len(fcm_tokens)} на токен {token[:20]}...")
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
                        ),
                    ),
                ),
            )
            
            try:
                response = messaging.send(message)
                success_count += 1
                logger.info(f"✅ Успішно відправлено на токен {token[:20]}...: {response}")
            except messaging.UnregisteredError:
                logger.error(f"❌ Токен {token[:20]}... не зареєстрований (пристрій видалив додаток)")
                invalid_tokens.append(token)
                failed_count += 1
            except messaging.SenderIdMismatchError:
                logger.error(f"❌ Токен {token[:20]}... належить іншому проєкту")
                invalid_tokens.append(token)
                failed_count += 1
            except Exception as e:
                error_str = str(e)
                logger.error(f"❌ Помилка відправки на токен {token[:20]}...: {e}")
                # Перевіряємо чи це помилка невалідного токену
                if 'registration-token-not-registered' in error_str or 'invalid-registration-token' in error_str:
                    logger.warning(f"⚠️ Токен {token[:20]}... невалідний, додаємо до списку видалення")
                    invalid_tokens.append(token)
                failed_count += 1
        
        logger.info(f"✅ Завершено відправку: успішно={success_count}, невдало={failed_count}")
        
        # Повертаємо результат з невалідними токенами
        result = {
            'success': success_count,
            'failed': failed_count
        }
        if invalid_tokens:
            result['invalid_tokens'] = invalid_tokens
            logger.warning(f"⚠️ Виявлено {len(invalid_tokens)} невалідних токенів")
        
        return result
    
    except Exception as e:
        logger.error(f"❌ КРИТИЧНА помилка при відправці multicast push: {e}")
        logger.exception("Детальна інформація про помилку:")
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
        
        logger.info(f"🔍 Пошук користувачів для адреси: {city}, {street}, {house_number}")
        logger.info(f"📊 Знайдено адрес: {len(user_addresses)}")
        
        if not user_addresses:
            logger.info(f"❌ Не знайдено користувачів для адреси: {city}, {street}, {house_number}")
            return {'success': 0, 'failed': 0}
        
        # Дедуплікація: один користувач може мати кілька адрес
        device_ids = list(set([ua.device_id for ua in user_addresses]))
        logger.info(f"📱 Device IDs (унікальних): {device_ids[:5]}..." if len(device_ids) > 5 else f"📱 Device IDs: {device_ids}")
        
        # Отримуємо токени для цих пристроїв (тільки з увімкненими сповіщеннями)
        tokens = db.query(DeviceToken).filter(
            DeviceToken.device_id.in_(device_ids),
            DeviceToken.notifications_enabled == True
        ).all()
        
        logger.info(f"🔔 Знайдено токенів з увімкненими сповіщеннями: {len(tokens)}")
        
        if not tokens:
            logger.info(f"❌ Немає пристроїв з увімкненими сповіщеннями для адреси: {city}, {street}, {house_number}")
            return {'success': 0, 'failed': 0}
        
        # Дедуплікація токенів (на випадок дублікатів)
        fcm_tokens = list(set([token.fcm_token for token in tokens]))
        active_device_ids = list(set([token.device_id for token in tokens]))
        
        logger.info(f"📊 Унікальних токенів після дедуплікації: {len(fcm_tokens)}")
        
        # Відправляємо мультикаст повідомлення
        logger.info(f"📤 Відправка пушу на {len(fcm_tokens)} пристроїв для адреси {city}, {street}, {house_number}")
        result = send_push_to_multiple(fcm_tokens, title, body, data)
        
        # Видаляємо невалідні токени з бази
        if 'invalid_tokens' in result and result['invalid_tokens']:
            logger.info(f"🗑️ Видалення {len(result['invalid_tokens'])} невалідних токенів з бази...")
            for invalid_token in result['invalid_tokens']:
                token_to_delete = db.query(DeviceToken).filter(
                    DeviceToken.fcm_token == invalid_token
                ).first()
                if token_to_delete:
                    logger.info(f"🗑️ Видаляємо токен {token_to_delete.device_id} (невалідний)")
                    db.delete(token_to_delete)
            db.commit()
        
        # Додаємо device_ids для збереження в історію
        result['device_ids'] = active_device_ids
        
        logger.info(f"✅ Завершено відправку для адреси {city}, {street}, {house_number}: {result}")
        return result
    
    except Exception as e:
        logger.error(f"❌ Помилка відправки targeted notification для {city}, {street}, {house_number}: {e}")
        logger.exception("Детальна інформація про помилку:")
        return {'success': 0, 'failed': 0}


def send_to_queue_users(
    db,
    queue: str,
    title: str,
    body: str,
    data: Optional[Dict[str, str]] = None
) -> Dict[str, int]:
    """
    Відправка повідомлення користувачам за чергою
    
    Args:
        db: Database session
        queue: Номер черги (наприклад "6.1")
        title: Заголовок повідомлення
        body: Текст повідомлення
        data: Додаткові дані (опціонально)
    
    Returns:
        dict: {'success': кількість успішних, 'failed': кількість невдалих, 'device_ids': список пристроїв}
    """
    from app.models import DeviceToken, UserAddress
    
    try:
        # Отримуємо device_id для цієї черги
        user_addresses = db.query(UserAddress).filter(
            UserAddress.queue == queue
        ).all()
        
        logger.info(f"🔍 Пошук користувачів для черги: {queue}")
        logger.info(f"📊 Знайдено адрес: {len(user_addresses)}")
        
        if not user_addresses:
            logger.info(f"❌ Не знайдено користувачів для черги: {queue}")
            return {'success': 0, 'failed': 0, 'device_ids': []}
        
        # Дедуплікація: один користувач може мати кілька адрес
        device_ids = list(set([ua.device_id for ua in user_addresses]))
        logger.info(f"📱 Device IDs (унікальних): {len(device_ids)}")
        
        # Отримуємо токени для цих пристроїв (тільки з увімкненими сповіщеннями)
        tokens = db.query(DeviceToken).filter(
            DeviceToken.device_id.in_(device_ids),
            DeviceToken.notifications_enabled == True
        ).all()
        
        logger.info(f"🔔 Знайдено токенів з увімкненими сповіщеннями: {len(tokens)}")
        
        if not tokens:
            logger.info(f"❌ Немає пристроїв з увімкненими сповіщеннями для черги: {queue}")
            # Але зберігаємо device_ids для історії
            return {'success': 0, 'failed': 0, 'device_ids': device_ids}
        
        # Дедуплікація токенів
        fcm_tokens = list(set([token.fcm_token for token in tokens]))
        active_device_ids = list(set([token.device_id for token in tokens]))
        
        logger.info(f"📊 Унікальних токенів після дедуплікації: {len(fcm_tokens)}")
        
        # Відправляємо мультикаст повідомлення
        logger.info(f"📤 Відправка пушу на {len(fcm_tokens)} пристроїв для черги {queue}")
        result = send_push_to_multiple(fcm_tokens, title, body, data)
        
        # Видаляємо невалідні токени з бази
        if 'invalid_tokens' in result and result['invalid_tokens']:
            logger.info(f"🗑️ Видалення {len(result['invalid_tokens'])} невалідних токенів з бази...")
            for invalid_token in result['invalid_tokens']:
                token_to_delete = db.query(DeviceToken).filter(
                    DeviceToken.fcm_token == invalid_token
                ).first()
                if token_to_delete:
                    logger.info(f"🗑️ Видаляємо токен {token_to_delete.device_id} (невалідний)")
                    db.delete(token_to_delete)
            db.commit()
        
        # Додаємо device_ids для збереження в історію (ВСІ пристрої, навіть якщо notifications_enabled=0)
        result['device_ids'] = device_ids
        
        logger.info(f"✅ Завершено відправку для черги {queue}: {result}")
        return result
    
    except Exception as e:
        logger.error(f"❌ Помилка відправки notification для черги {queue}: {e}")
        logger.exception("Детальна інформація про помилку:")
        return {'success': 0, 'failed': 0, 'device_ids': []}


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
        logger.info(f"🔍 Пошук всіх пристроїв з увімкненими сповіщеннями...")
        tokens = db.query(DeviceToken).filter(
            DeviceToken.notifications_enabled == True
        ).all()
        
        logger.info(f"📊 Знайдено токенів з увімкненими сповіщеннями: {len(tokens)}")
        
        if not tokens:
            logger.warning("⚠️ Немає пристроїв з увімкненими сповіщеннями")
            return {'success': 0, 'failed': 0}
        
        # Дедуплікація токенів (на випадок дублікатів в базі)
        fcm_tokens = list(set([token.fcm_token for token in tokens]))
        logger.info(f"📊 Унікальних токенів після дедуплікації: {len(fcm_tokens)}")
        
        # Відправляємо мультикаст повідомлення
        logger.info(f"📤 Відправка broadcast пушу на {len(fcm_tokens)} пристроїв...")
        logger.info(f"📝 Заголовок: {title}")
        logger.info(f"📝 Текст: {body[:100]}..." if len(body) > 100 else f"📝 Текст: {body}")
        result = send_push_to_multiple(fcm_tokens, title, body, data)
        
        # Видаляємо невалідні токени з бази
        if 'invalid_tokens' in result and result['invalid_tokens']:
            logger.info(f"🗑️ Видалення {len(result['invalid_tokens'])} невалідних токенів з бази...")
            for invalid_token in result['invalid_tokens']:
                token_to_delete = db.query(DeviceToken).filter(
                    DeviceToken.fcm_token == invalid_token
                ).first()
                if token_to_delete:
                    logger.info(f"🗑️ Видаляємо токен {token_to_delete.device_id} (невалідний)")
                    db.delete(token_to_delete)
            db.commit()
        
        logger.info(f"✅ Broadcast завершено: успішно={result['success']}, невдало={result['failed']}")
        return result
    
    except Exception as e:
        logger.error(f"❌ Помилка відправки broadcast notification: {e}")
        logger.exception("Детальна інформація про помилку:")
        return {'success': 0, 'failed': 0}
