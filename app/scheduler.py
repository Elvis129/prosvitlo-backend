from apscheduler.schedulers.background import BackgroundScheduler
from app.scraper.schedule_parser import fetch_schedule_images, parse_queue_schedule
from app.scraper.announcements_parser import fetch_announcements, check_schedule_availability
from app.utils.image_downloader_sync import download_schedule_image_sync
from app.scraper.outage_parser import fetch_all_emergency_outages, fetch_all_planned_outages
from app import crud_schedules, crud_outages
from sqlalchemy.orm import Session
from app.models import EmergencyOutage, PlannedOutage
from app.database import SessionLocal
import logging
from datetime import date, datetime, timedelta
import hashlib
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler()

# Зберігаємо хеші останніх оголошень щоб не спамити
last_announcement_hashes = set()


def generate_outage_hash(outage):
    """Генерує хеш для відключення на основі ключових полів"""
    key_data = {
        'rem_id': outage['rem_id'],
        'city': outage['city'],
        'street': outage['street'],
        'house_numbers': outage['house_numbers'],
        'start_time': str(outage['start_time']),
        'end_time': str(outage['end_time']),
        'work_type': outage['work_type']
    }
    data_str = json.dumps(key_data, sort_keys=True)
    return hashlib.md5(data_str.encode()).hexdigest()


def cleanup_old_schedules():
    """Видаляє старі графіки, залишаючи тільки вчора, сьогодні, завтра"""
    db: Session = SessionLocal()
    try:
        today = date.today()
        yesterday = today - timedelta(days=1)
        
        from app.models import Schedule
        old_schedules = db.query(Schedule).filter(
            Schedule.date < yesterday
        ).all()
        
        if old_schedules:
            logger.info(f"Видаляємо {len(old_schedules)} старих графіків")
            for schedule in old_schedules:
                db.delete(schedule)
            db.commit()
            
    except Exception as e:
        logger.error(f"Помилка при очищенні старих графіків: {e}")
        db.rollback()
    finally:
        db.close()


def check_and_notify_announcements():
    """
    Перевіряє загальні оголошення з сайту кожні 5 хвилин
    Відправляє push ТІЛЬКИ якщо є НОВІ оголошення
    """
    global last_announcement_hashes
    from app.services import firebase_service
    from app.services.telegram_service import get_telegram_service
    from app import crud_notifications
    
    db: Session = SessionLocal()
    try:
        logger.info("🔍 Перевіряємо оголошення...")
        announcements = fetch_announcements()
        
        if not announcements:
            logger.info("ℹ️ Нових оголошень не знайдено")
        else:
            logger.info(f"📢 Знайдено {len(announcements)} оголошень для перевірки")
        
        for announcement in announcements:
            content_hash = announcement['content_hash']
            
            # Якщо цей хеш вже бачили - пропускаємо
            if content_hash in last_announcement_hashes:
                continue
            
            # Нове оголошення - відправляємо push ВСІМ
            title = announcement['title']
            full_body = announcement.get('full_body', announcement['body'])
            
            # Для push обмежуємо текст (250 символів)
            push_body = full_body[:250] + '...' if len(full_body) > 250 else full_body
            
            result = firebase_service.send_to_all_users(
                db=db,
                title=title,
                body=push_body,
                data={
                    "type": "announcement",
                    "source": announcement['source']
                }
            )
            
            if result['success'] > 0:
                # Зберігаємо ПОВНИЙ текст в історію
                crud_notifications.create_notification(
                    db=db,
                    notification_type="all",
                    category="general",
                    title=title,
                    body=full_body
                )
                
                # Запам'ятовуємо що відправили
                last_announcement_hashes.add(content_hash)
                
                # Відправляємо ПОВНИЙ текст в Telegram канал
                telegram = get_telegram_service()
                if telegram:
                    telegram_success = telegram.send_announcement(
                        title=title,
                        body=full_body,
                        source=announcement['source']
                    )
                    if telegram_success:
                        logger.info(f"✅ Telegram: повідомлення відправлено в канал")
                    else:
                        logger.error(f"❌ Telegram: помилка відправки")
                else:
                    logger.warning(f"⚠️ Telegram сервіс не ініціалізований")
                logger.info(f"✅ Відправлено оголошення ВСІМ: {title}")
        
        # Очищаємо старі хеші (залишаємо останні 100)
        if len(last_announcement_hashes) > 100:
            last_announcement_hashes.clear()
            
    except Exception as e:
        logger.error(f"Помилка при перевірці оголошень: {e}")
    finally:
        db.close()


def update_schedules():
    """
    Оновлює графіки кожні 5 хвилин
    Перезаписує ТІЛЬКИ якщо дані змінилися (перевірка по хешу)
    Відправляє повідомлення про НОВІ графіки (нові дати)
    """
    db: Session = SessionLocal()
    schedule_changed = False
    new_dates_added = []  # Відстежуємо нові дати
    
    try:
        logger.info("Початок оновлення графіків...")
        
        # Перевіряємо доступність графіків
        availability = check_schedule_availability()
        if availability and not availability['available']:
            logger.info(f"⚠️ {availability['message']}")
        
        schedules = fetch_schedule_images()

        # ⭐ ВАЖЛИВО: Очищаємо старі графіки ЗАВЖДИ, незалежно від наявності нових
        cleanup_old_schedules()

        if not schedules:
            logger.warning("Не вдалося отримати графіки")
            return  # Вийти після cleanup
        
        today = date.today()
        
        for schedule_info in schedules:
            schedule_date = schedule_info.get('date')
            image_url = schedule_info.get('image_url')
            recognized_text = schedule_info.get('recognized_text')
            content_hash = schedule_info.get('content_hash')

            if not schedule_date or not recognized_text:
                continue
            
            local_image_path = download_schedule_image_sync(image_url)
            if local_image_path and local_image_path != image_url:
                if local_image_path.startswith('/static/'):
                    image_url = f"http://10.0.2.2:8000{local_image_path}"
                else:
                    image_url = local_image_path
            
            existing = crud_schedules.get_schedule_by_date(db=db, date_val=schedule_date)
            
            # ⭐ НОВА ЛОГІКА: відстежуємо нові дати
            if existing:
                # Графік вже є в БД - перевіряємо чи змінився
                if existing.content_hash == content_hash:
                    logger.info(f"Графік для {schedule_date} не змінився - пропускаємо")
                    continue
                else:
                    schedule_changed = True
                    logger.info(f"Графік для {schedule_date} ЗМІНИВСЯ - оновлюємо")
            else:
                # Нового графіка немає в БД
                schedule_changed = True
                # Якщо це майбутня дата (завтра або пізніше) - відправимо повідомлення
                if schedule_date >= today:
                    new_dates_added.append(schedule_date)
                    logger.info(f"📅 НОВИЙ графік на {schedule_date} буде додано")
            
            parsed_schedule = parse_queue_schedule(recognized_text)
            if not parsed_schedule:
                continue
            
            if existing:
                crud_schedules.update_schedule(
                    db=db,
                    schedule_id=existing.id,
                    image_url=image_url,
                    recognized_text=recognized_text,
                    parsed_data=parsed_schedule,
                    content_hash=content_hash
                )
            else:
                crud_schedules.create_schedule(
                    db=db,
                    date=schedule_date,
                    image_url=image_url,
                    recognized_text=recognized_text,
                    parsed_data=parsed_schedule,
                    content_hash=content_hash
                )
        
        # Відправляємо сповіщення якщо є НОВІ дати (завтра, післязавтра)
        if new_dates_added:
            # Сортуємо дати і беремо найближчу
            new_dates_added.sort()
            nearest_date = new_dates_added[0]
            logger.info(f"🔔 Відправка повідомлення про новий графік на {nearest_date}")
            notify_schedule_update(nearest_date)
        
        logger.info("Оновлення графіків завершено")
        
    except Exception as e:
        logger.error(f"Помилка при оновленні графіків: {e}")
    finally:
        db.close()


def update_emergency_outages():
    """
    Оновлює аварійні відключення кожну годину
    Додає/видаляє ТІЛЬКИ ті що змінилися (перевірка по хешу)
    Якщо сторінки не змінилися - взагалі не парсить
    """
    db: Session = SessionLocal()
    try:
        logger.info("Початок оновлення аварійних відключень...")
        
        outages = fetch_all_emergency_outages()
        
        # ⚡ ОПТИМІЗАЦІЯ: Якщо None - сторінки не змінилися, нічого не робимо
        if outages is None:
            logger.info("✓ Аварійні відключення: сторінки без змін")
            return
        
        if not outages:
            crud_outages.clear_all_active_emergency_outages(db)
            return
        
        new_hashes = set()
        outages_by_hash = {}
        for outage in outages:
            outage_hash = generate_outage_hash(outage)
            new_hashes.add(outage_hash)
            outages_by_hash[outage_hash] = outage
        
        existing_outages = db.query(EmergencyOutage).filter(
            EmergencyOutage.is_active == True
        ).all()
        
        existing_hashes = set()
        existing_by_hash = {}
        for existing in existing_outages:
            existing_dict = {
                'rem_id': existing.rem_id,
                'city': existing.city,
                'street': existing.street,
                'house_numbers': existing.house_numbers,
                'start_time': str(existing.start_time),
                'end_time': str(existing.end_time),
                'work_type': existing.work_type
            }
            existing_hash = generate_outage_hash(existing_dict)
            existing_hashes.add(existing_hash)
            existing_by_hash[existing_hash] = existing
        
        to_add = new_hashes - existing_hashes
        to_remove = existing_hashes - new_hashes
        
        # ⭐ ЛОГІКА: якщо нічого не змінилось - нічого не робимо
        if not to_add and not to_remove:
            logger.info("Аварійні відключення не змінились")
            return
        
        logger.info(f"Аварійні: +{len(to_add)}, -{len(to_remove)}")
        
        for outage_hash in to_remove:
            existing_by_hash[outage_hash].is_active = False
        
        for outage_hash in to_add:
            outage = outages_by_hash[outage_hash]
            crud_outages.create_emergency_outage(
                db=db,
                rem_id=outage['rem_id'],
                rem_name=outage['rem_name'],
                city=outage['city'],
                street=outage['street'],
                house_numbers=outage['house_numbers'],
                work_type=outage['work_type'],
                created_date=outage['created_date'],
                start_time=outage['start_time'],
                end_time=outage['end_time']
            )
        
        db.commit()
        
    except Exception as e:
        logger.error(f"Помилка при оновленні аварійних: {e}")
        db.rollback()
    finally:
        db.close()


def update_planned_outages():
    """
    Оновлює планові відключення ТІЛЬКИ 1 раз на день о 9:00
    Додає/видаляє ТІЛЬКИ ті що змінилися (перевірка по хешу)
    Якщо сторінки не змінилися - взагалі не парсить
    """
    db: Session = SessionLocal()
    try:
        logger.info("Початок оновлення планових відключень...")
        
        outages = fetch_all_planned_outages()
        
        # ⚡ ОПТИМІЗАЦІЯ: Якщо None - сторінки не змінилися, нічого не робимо
        if outages is None:
            logger.info("✓ Планові відключення: сторінки без змін")
            return
        
        if not outages:
            crud_outages.clear_all_active_planned_outages(db)
            return
        
        new_hashes = set()
        outages_by_hash = {}
        for outage in outages:
            outage_hash = generate_outage_hash(outage)
            new_hashes.add(outage_hash)
            outages_by_hash[outage_hash] = outage
        
        existing_outages = db.query(PlannedOutage).filter(
            PlannedOutage.is_active == True
        ).all()
        
        existing_hashes = set()
        existing_by_hash = {}
        for existing in existing_outages:
            existing_dict = {
                'rem_id': existing.rem_id,
                'city': existing.city,
                'street': existing.street,
                'house_numbers': existing.house_numbers,
                'start_time': str(existing.start_time),
                'end_time': str(existing.end_time),
                'work_type': existing.work_type
            }
            existing_hash = generate_outage_hash(existing_dict)
            existing_hashes.add(existing_hash)
            existing_by_hash[existing_hash] = existing
        
        to_add = new_hashes - existing_hashes
        to_remove = existing_hashes - new_hashes
        
        # ⭐ ЛОГІКА: якщо нічого не змінилось - нічого не робимо
        if not to_add and not to_remove:
            logger.info("Планові відключення не змінились")
            return
        
        logger.info(f"Планові: +{len(to_add)}, -{len(to_remove)}")
        
        for outage_hash in to_remove:
            existing_by_hash[outage_hash].is_active = False
        
        for outage_hash in to_add:
            outage = outages_by_hash[outage_hash]
            crud_outages.create_planned_outage(
                db=db,
                rem_id=outage['rem_id'],
                rem_name=outage['rem_name'],
                city=outage['city'],
                street=outage['street'],
                house_numbers=outage['house_numbers'],
                work_type=outage['work_type'],
                created_date=outage['created_date'],
                start_time=outage['start_time'],
                end_time=outage['end_time']
            )
        
        db.commit()
        
    except Exception as e:
        logger.error(f"Помилка при оновленні планових: {e}")
        db.rollback()
    finally:
        db.close()


def cleanup_old_outages():
    """Видаляє старі відключення"""
    db: Session = SessionLocal()
    try:
        current_time = datetime.now()
        cutoff_time = current_time - timedelta(days=7)
        
        old_emergency = db.query(EmergencyOutage).filter(
            EmergencyOutage.end_time < cutoff_time
        ).all()
        
        old_planned = db.query(PlannedOutage).filter(
            PlannedOutage.end_time < cutoff_time
        ).all()
        
        for outage in old_emergency:
            db.delete(outage)
        
        for outage in old_planned:
            db.delete(outage)
        
        db.commit()
        
        if old_emergency or old_planned:
            logger.info(f"Видалено старих відключень: {len(old_emergency)} аварійних, {len(old_planned)} планових")
            
    except Exception as e:
        logger.error(f"Помилка при очищенні: {e}")
        db.rollback()
    finally:
        db.close()


def check_upcoming_outages_and_notify():
    """
    Перевіряє відключення (аварійні/планові/по чергах) які почнуться за 5 хвилин
    Викликається кожні 5 хвилин
    """
    from app.services import firebase_service
    from app.services.telegram_service import get_telegram_service
    from app import crud_notifications
    from app.models import UserAddress, DeviceToken
    
    db: Session = SessionLocal()
    try:
        current_time = datetime.now()
        target_time = current_time + timedelta(minutes=5)
        
        logger.info(f"🔔 Перевірка відключень на {target_time.strftime('%H:%M')}...")
        
        # ========== 1. АВАРІЙНІ ВІДКЛЮЧЕННЯ ==========
        emergency_outages = db.query(EmergencyOutage).filter(
            EmergencyOutage.is_active == True,
            EmergencyOutage.start_time >= current_time,
            EmergencyOutage.start_time <= target_time
        ).all()
        
        if emergency_outages:
            logger.info(f"⚠️ Знайдено {len(emergency_outages)} аварійних відключень")
        
        for outage in emergency_outages:
            start_time_str = outage.start_time.strftime("%H:%M")
            end_time_str = outage.end_time.strftime("%H:%M")
            
            title = "⚠️ Аварійне відключення за 5 хвилин"
            body = f"{outage.city}, {outage.street}, {outage.house_numbers}\n{start_time_str} - {end_time_str}"
            
            logger.info(f"📤 Відправка аварійного пушу: {outage.city}, {outage.street}")
            
            for house in outage.house_numbers.split(','):
                house = house.strip()
                result = firebase_service.send_to_address_users(
                    db=db,
                    city=outage.city,
                    street=outage.street,
                    house_number=house,
                    title=title,
                    body=body,
                    data={
                        "type": "emergency",
                        "city": outage.city,
                        "street": outage.street,
                        "house_number": house,
                        "start_time": outage.start_time.isoformat(),
                        "end_time": outage.end_time.isoformat()
                    }
                )
                
                if result['success'] > 0:
                    crud_notifications.create_notification(
                        db=db,
                        notification_type="address",
                        category="emergency",
                        title=title,
                        body=body,
                        addresses=[{
                            "city": outage.city,
                            "street": outage.street,
                            "house_number": house
                        }]
                    )
                    logger.info(f"✅ Аварійний push: {result['success']} пристроїв для {outage.city}, {outage.street}, {house}")
                else:
                    logger.info(f"ℹ️ Немає користувачів для {outage.city}, {outage.street}, {house}")
        
        # ========== 2. ПЛАНОВІ ВІДКЛЮЧЕННЯ ==========
        planned_outages = db.query(PlannedOutage).filter(
            PlannedOutage.is_active == True,
            PlannedOutage.start_time >= current_time,
            PlannedOutage.start_time <= target_time
        ).all()
        
        if planned_outages:
            logger.info(f"📋 Знайдено {len(planned_outages)} планових відключень")
        
        for outage in planned_outages:
            start_time_str = outage.start_time.strftime("%H:%M")
            end_time_str = outage.end_time.strftime("%H:%M")
            
            title = "📋 Планове відключення за 5 хвилин"
            body = f"{outage.city}, {outage.street}, {outage.house_numbers}\n{start_time_str} - {end_time_str}"
            
            logger.info(f"📤 Відправка планового пушу: {outage.city}, {outage.street}")
            
            for house in outage.house_numbers.split(','):
                house = house.strip()
                result = firebase_service.send_to_address_users(
                    db=db,
                    city=outage.city,
                    street=outage.street,
                    house_number=house,
                    title=title,
                    body=body,
                    data={
                        "type": "planned",
                        "city": outage.city,
                        "street": outage.street,
                        "house_number": house,
                        "start_time": outage.start_time.isoformat(),
                        "end_time": outage.end_time.isoformat()
                    }
                )
                
                if result['success'] > 0:
                    crud_notifications.create_notification(
                        db=db,
                        notification_type="address",
                        category="scheduled",
                        title=title,
                        body=body,
                        addresses=[{
                            "city": outage.city,
                            "street": outage.street,
                            "house_number": house
                        }]
                    )
                    logger.info(f"✅ Плановий push: {result['success']} пристроїв для {outage.city}, {outage.street}, {house}")
                else:
                    logger.info(f"ℹ️ Немає користувачів для {outage.city}, {outage.street}, {house}")
        
        # ========== 3. ВІДКЛЮЧЕННЯ ПО ЧЕРГАХ (1.1, 1.2, etc) ==========
        today = current_time.date()
        schedule = crud_schedules.get_schedule_by_date(db=db, date_val=today)
        
        if schedule and schedule.parsed_data:
            parsed_data = schedule.parsed_data
            target_hour = target_time.hour
            hour_key = f"{target_hour:02d}:00"
            
            # Якщо через 5 хв почнеться нова година з відключеннями
            if hour_key in parsed_data:
                queues_to_notify = parsed_data[hour_key]
                logger.info(f"⚡ Знайдено черги для відключення о {hour_key}: {queues_to_notify}")
                
                for queue in queues_to_notify:
                    # Знаходимо користувачів з цією чергою
                    user_addresses = db.query(UserAddress).filter(
                        UserAddress.queue == queue
                    ).all()
                    
                    if not user_addresses:
                        logger.info(f"ℹ️ Немає користувачів для черги {queue}")
                        continue
                    
                    logger.info(f"📤 Відправка push для черги {queue} ({len(user_addresses)} користувачів)")
                    
                    device_ids = [ua.device_id for ua in user_addresses]
                    
                    tokens = db.query(DeviceToken).filter(
                        DeviceToken.device_id.in_(device_ids),
                        DeviceToken.notifications_enabled == True
                    ).all()
                    
                    if not tokens:
                        logger.info(f"ℹ️ Немає активних пристроїв для черги {queue}")
                        continue
                    
                    fcm_tokens = [token.fcm_token for token in tokens]
                    
                    title = f"⚡ Відключення черги {queue} за 5 хвилин"
                    body = f"Згідно графіку, о {target_hour:02d}:00 буде відключено чергу {queue}"
                    
                    result = firebase_service.send_push_to_multiple(
                        fcm_tokens=fcm_tokens,
                        title=title,
                        body=body,
                        data={
                            "type": "queue_outage",
                            "queue": queue,
                            "hour": str(target_hour)
                        }
                    )
                    
                    if result['success'] > 0:
                        crud_notifications.create_notification(
                            db=db,
                            notification_type="queue",
                            category="scheduled",
                            title=title,
                            body=body
                        )
                        logger.info(f"✅ Черга {queue}: {result['success']} push відправлено")
                    else:
                        logger.info(f"⚠️ Черга {queue}: {result['failed']} помилок")
            else:
                logger.debug(f"ℹ️ Немає відключень о {hour_key}")
        else:
            logger.debug("ℹ️ Немає графіка на сьогодні")
        
    except Exception as e:
        logger.error(f"Помилка при перевірці відключень: {e}")
    finally:
        db.close()


def notify_schedule_update(schedule_date=None):
    """Відправляє push про оновлення графіків
    
    Args:
        schedule_date: Дата нового графіка (якщо є)
    """
    from app.services import firebase_service
    from app.services.telegram_service import get_telegram_service
    from app import crud_notifications
    
    db: Session = SessionLocal()
    try:
        logger.info("📅 Відправка сповіщення про оновлення графіків...")
        
        # Формуємо повідомлення залежно від дати
        if schedule_date:
            from datetime import date as dt_date
            today = dt_date.today()
            
            if schedule_date == today:
                date_text = "на сьогодні"
            elif schedule_date == today + timedelta(days=1):
                date_text = "на завтра"
            elif schedule_date == today + timedelta(days=2):
                date_text = "на післязавтра"
            else:
                date_text = f"на {schedule_date.strftime('%d.%m')}"
            
            title = "📅 Новий графік відключень"
            body = f"З'явився графік {date_text}"
        else:
            title = "📅 Оновлення графіків"
            body = "З'явився новий графік відключень"
        
        result = firebase_service.send_to_all_users(
            db=db,
            title=title,
            body=body,
            data={"type": "schedule_update"}
        )
        
        if result['success'] > 0:
            crud_notifications.create_notification(
                db=db,
                notification_type="all",
                category="general",
                title=title,
                body=body
            )
            logger.info(f"✅ Push про графіки відправлено: {result}")
            
            # Відправляємо в Telegram
            telegram = get_telegram_service()
            if telegram:
                telegram_success = telegram.send_message(
                    message=f"<b>{title}</b>\n\n{body}",
                    parse_mode="HTML"
                )
                if telegram_success:
                    logger.info("✅ Telegram: повідомлення про графіки відправлено")
                else:
                    logger.error("❌ Telegram: помилка відправки повідомлення про графіки")
            else:
                logger.warning("⚠️ Telegram не ініціалізований для відправки про графіки")
        else:
            logger.warning(f"⚠️ Жоден push не відправлено (немає активних пристроїв)")
        
    except Exception as e:
        logger.error(f"Помилка при відправці сповіщення: {e}")
    finally:
        db.close()


def cleanup_old_notifications_job():
    """Видаляє повідомлення старіші за 5 днів (щодня о 3:00)"""
    from app import crud_notifications
    
    db: Session = SessionLocal()
    try:
        deleted_count = crud_notifications.cleanup_old_notifications(db)
        if deleted_count > 0:
            logger.info(f"Видалено {deleted_count} старих повідомлень")
    except Exception as e:
        logger.error(f"Помилка при очищенні: {e}")
    finally:
        db.close()


def start_scheduler():
    """
    Запускає планувальник з КОНФІГУРОВАНИМИ налаштуваннями:
    - Сайт парситься з інтервалом CHECK_INTERVAL_MINUTES (5 хв або 60 хв)
    - Планові відключення парсяться 1 раз на день о 9:00
    - Сповіщення за 5 хв перевіряються з тим самим інтервалом
    - Дані перезаписуються ТІЛЬКИ якщо змінились (хеш-перевірка)
    """
    from app.config import settings
    
    # Не виконуємо одразу при старті - дозволяємо uvicorn швидко стартувати
    # Перше оновлення відбудеться через 10 секунд після запуску
    from datetime import datetime, timedelta
    start_time = datetime.now() + timedelta(seconds=10)
    
    check_interval = settings.CHECK_INTERVAL_MINUTES
    
    # ⭐ Графіки - перший запуск через 10с, потім з заданим інтервалом
    scheduler.add_job(update_schedules, 'interval', minutes=check_interval, id='schedules', next_run_time=start_time)
    
    # ⭐ Аварійні - перший запуск через 15с, потім з заданим інтервалом
    scheduler.add_job(update_emergency_outages, 'interval', minutes=check_interval, id='emergency', 
                     next_run_time=start_time + timedelta(seconds=5))
    
    # ⭐ Оголошення з сайту - перший запуск через 20с, потім з заданим інтервалом
    scheduler.add_job(check_and_notify_announcements, 'interval', minutes=check_interval, id='announcements',
                     next_run_time=start_time + timedelta(seconds=10))
    
    # ⭐ Планові - перший запуск через 25с, потім ТІЛЬКИ 1 раз на день о 9:00
    scheduler.add_job(update_planned_outages, 'cron', hour=9, minute=0, id='planned')
    scheduler.add_job(update_planned_outages, 'date', run_date=start_time + timedelta(seconds=15), id='planned_initial')
    
    # ⭐ Сповіщення за 5 хв (аварійні/планові/черги) - з заданим інтервалом
    scheduler.add_job(check_upcoming_outages_and_notify, 'interval', minutes=check_interval, id='notifications')
    
    # Очищення старих відключень - раз на добу о 2:00
    scheduler.add_job(cleanup_old_outages, 'cron', hour=2, minute=0, id='cleanup_outages')
    
    # Очищення старих повідомлень - щодня о 3:00
    scheduler.add_job(cleanup_old_notifications_job, 'cron', hour=3, minute=0, id='cleanup_notifications')
    
    scheduler.start()
    logger.info("=" * 60)
    logger.info("✅ Планувальник запущено:")
    logger.info(f"  📅 Графіки: кожні {check_interval} хвилин")
    logger.info(f"  ⚠️ Аварійні відключення: кожні {check_interval} хвилин")
    logger.info(f"  📢 Оголошення з сайту: кожні {check_interval} хвилин")
    logger.info("  📋 Планові відключення: щодня о 9:00")
    logger.info(f"  🔔 Сповіщення за 5 хв: кожні {check_interval} хвилин")
    logger.info("  🧹 Очищення відключень: щодня о 2:00")
    logger.info("  🧹 Очищення повідомлень: щодня о 3:00")
    logger.info("=" * 60)


def stop_scheduler():
    """Зупиняє планувальник"""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Планувальник зупинено")


def get_scheduler_status():
    """Повертає статус планувальника"""
    jobs_info = []
    if scheduler.running:
        for job in scheduler.get_jobs():
            jobs_info.append({
                "id": job.id,
                "next_run": str(job.next_run_time) if job.next_run_time else None
            })
    
    return {
        "running": scheduler.running,
        "jobs": jobs_info
    }
