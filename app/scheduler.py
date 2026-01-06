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
import pytz

# Київська часова зона
KYIV_TZ = pytz.timezone('Europe/Kiev')

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
                    from app.config import settings
                    image_url = f"{settings.BASE_URL}{local_image_path}"
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
            
            # ⭐ СКИДАЄМО СТАН "немає графіка" коли додається новий графік
            reset_no_schedule_state(db)
        
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
        
        new_outages_list = []
        for outage_hash in to_add:
            outage = outages_by_hash[outage_hash]
            new_outage = crud_outages.create_emergency_outage(
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
            new_outages_list.append(new_outage)
        
        db.commit()
        
        # 🔔 НЕГАЙНА ВІДПРАВКА ПУШІВ для нових відключень
        if new_outages_list:
            logger.info(f"🔔 Відправка негайних пушів для {len(new_outages_list)} нових аварійних відключень")
            notify_new_outages_immediately(db, new_outages_list, "emergency")
        
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
        
        new_outages_list = []
        for outage_hash in to_add:
            outage = outages_by_hash[outage_hash]
            new_outage = crud_outages.create_planned_outage(
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
            new_outages_list.append(new_outage)
        
        db.commit()
        
        # 🔔 НЕГАЙНА ВІДПРАВКА ПУШІВ для нових відключень
        if new_outages_list:
            logger.info(f"🔔 Відправка негайних пушів для {len(new_outages_list)} нових планових відключень")
            notify_new_outages_immediately(db, new_outages_list, "planned")
        
    except Exception as e:
        logger.error(f"Помилка при оновленні планових: {e}")
        db.rollback()
    finally:
        db.close()


def cleanup_old_outages():
    """Видаляє старі відключення"""
    db: Session = SessionLocal()
    try:
        current_time = datetime.now(KYIV_TZ).replace(tzinfo=None)
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


def notify_new_outages_immediately(db: Session, outages_list, outage_type: str):
    """
    Негайно відправляє пуші для нових відключень що щойно з'явились
    
    Args:
        db: Database session
        outages_list: Список нових відключень (EmergencyOutage або PlannedOutage)
        outage_type: "emergency" або "planned"
    """
    from app.services import firebase_service
    from app import crud_notifications
    
    # Використовуємо naive datetime для порівняння з naive datetime в БД
    current_time = datetime.now(KYIV_TZ).replace(tzinfo=None)
    
    for outage in outages_list:
        # Відправляємо ТІЛЬКИ якщо відключення ще не закінчилося
        if outage.end_time <= current_time:
            logger.info(f"⏭️ Пропуск - відключення вже закінчилося: {outage.city}, {outage.street}")
            continue
        
        start_time_str = outage.start_time.strftime("%H:%M")
        end_time_str = outage.end_time.strftime("%H:%M")
        
        # Визначаємо тип повідомлення
        if outage.start_time <= current_time:
            # Відключення вже почалося
            if outage_type == "emergency":
                title = "⚠️ Аварійне відключення ЗАРАЗ"
            else:
                title = "📋 Планове відключення ЗАРАЗ"
            time_info = f"Почалося о {start_time_str}, триватиме до {end_time_str}"
        else:
            # Відключення ще не почалося
            minutes_until = int((outage.start_time - current_time).total_seconds() / 60)
            if outage_type == "emergency":
                title = f"⚠️ Аварійне відключення через {minutes_until} хв"
            else:
                title = f"📋 Планове відключення через {minutes_until} хв"
            time_info = f"{start_time_str} - {end_time_str}"
        
        body = f"{outage.city}, {outage.street}, {outage.house_numbers}\n{time_info}"
        
        logger.info(f"📤 Негайний пуш: {outage.city}, {outage.street}")
        
        sent_successfully = False
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
                    "type": outage_type,
                    "city": outage.city,
                    "street": outage.street,
                    "house_number": house,
                    "start_time": outage.start_time.isoformat(),
                    "end_time": outage.end_time.isoformat()
                }
            )
            
            if result['success'] > 0:
                sent_successfully = True
                crud_notifications.create_notification(
                    db=db,
                    notification_type="address",
                    category=outage_type,
                    title=title,
                    body=body,
                    addresses=[{
                        "city": outage.city,
                        "street": outage.street,
                        "house_number": house
                    }],
                    device_ids=result.get('device_ids', [])
                )
                logger.info(f"✅ Негайний push: {result['success']} пристроїв для {house}")
            else:
                logger.info(f"ℹ️ Немає користувачів для {house}")
        
        # ФІКСУЄМО ЩО PUSH ВІДПРАВЛЕНО
        if sent_successfully:
            outage.notification_sent_at = current_time
            db.commit()
            logger.info(f"✅ Позначено відключення як оповіщене: {outage.id}")


def check_upcoming_outages_and_notify():
    """
    Перевіряє відключення (аварійні/планові/по чергах) які почнуться за 10 хвилин
    АБО вже почалися але ще не отримали сповіщення
    Викликається кожні 5 хвилин
    """
    from app.services import firebase_service
    from app.services.telegram_service import get_telegram_service
    from app import crud_notifications
    from app.models import UserAddress, DeviceToken
    
    db: Session = SessionLocal()
    try:
        # Використовуємо київський час (naive для порівняння з БД)
        current_time = datetime.now(KYIV_TZ).replace(tzinfo=None)
        target_time = current_time + timedelta(minutes=10)
        
        logger.info(f"🔔 Перевірка відключень на {target_time.strftime('%H:%M')}...")
        
        # ========== 1. АВАРІЙНІ ВІДКЛЮЧЕННЯ ==========
        # Відправляємо пуші для:
        # 1) Відключень що почнуться за 10 хвилин
        # 2) Відключень що вже почалися (start_time < current_time) але ще не закінчилися
        emergency_outages = db.query(EmergencyOutage).filter(
            EmergencyOutage.is_active == True,
            EmergencyOutage.notification_sent_at == None,  # ЩЕ НЕ ВІДПРАВЛЕНО
            EmergencyOutage.end_time > current_time,  # Ще не закінчилося
            # АБО почнеться за 10 хвилин АБО вже почалося
        ).all()
        
        if emergency_outages:
            logger.info(f"⚠️ Знайдено {len(emergency_outages)} аварійних відключень для перевірки")
        
        for outage in emergency_outages:
            # Перевіряємо чи це відключення в межах 10 хвилин АБО вже почалося
            if not (outage.start_time <= target_time or outage.start_time < current_time):
                continue
                
            start_time_str = outage.start_time.strftime("%H:%M")
            end_time_str = outage.end_time.strftime("%H:%M")
            
            # Визначаємо тип повідомлення
            if outage.start_time < current_time:
                title = "⚠️ Аварійне відключення ЗАРАЗ"
                time_info = f"Почалося о {start_time_str}, триватиме до {end_time_str}"
            else:
                minutes_until = int((outage.start_time - current_time).total_seconds() / 60)
                title = f"⚠️ Аварійне відключення за {minutes_until} хв"
                time_info = f"{start_time_str} - {end_time_str}"
            
            body = f"{outage.city}, {outage.street}, {outage.house_numbers}\n{time_info}"
            
            logger.info(f"📤 Відправка аварійного пушу: {outage.city}, {outage.street}")
            
            sent_successfully = False
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
                    sent_successfully = True
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
                        }],
                        device_ids=result.get('device_ids', [])
                    )
                    logger.info(f"✅ Аварійний push: {result['success']} пристроїв для {outage.city}, {outage.street}, {house}")
                else:
                    logger.info(f"ℹ️ Немає користувачів для {outage.city}, {outage.street}, {house}")
            
            # ФІКСУЄМО ЩО PUSH ВІДПРАВЛЕНО
            if sent_successfully:
                outage.notification_sent_at = current_time
                db.commit()
                logger.info(f"✅ Позначено аварійне відключення як оповіщене: {outage.id}")
        
        # ========== 2. ПЛАНОВІ ВІДКЛЮЧЕННЯ ==========
        planned_outages = db.query(PlannedOutage).filter(
            PlannedOutage.is_active == True,
            PlannedOutage.notification_sent_at == None,  # ЩЕ НЕ ВІДПРАВЛЕНО
            PlannedOutage.end_time > current_time,  # Ще не закінчилося
        ).all()
        
        if planned_outages:
            logger.info(f"📋 Знайдено {len(planned_outages)} планових відключень для перевірки")
        
        for outage in planned_outages:
            # Перевіряємо чи це відключення в межах 10 хвилин АБО вже почалося
            if not (outage.start_time <= target_time or outage.start_time < current_time):
                continue
                
            start_time_str = outage.start_time.strftime("%H:%M")
            end_time_str = outage.end_time.strftime("%H:%M")
            
            # Визначаємо тип повідомлення
            if outage.start_time < current_time:
                title = "📋 Планове відключення ЗАРАЗ"
                time_info = f"Почалося о {start_time_str}, триватиме до {end_time_str}"
            else:
                minutes_until = int((outage.start_time - current_time).total_seconds() / 60)
                title = f"📋 Планове відключення за {minutes_until} хв"
                time_info = f"{start_time_str} - {end_time_str}"
            
            body = f"{outage.city}, {outage.street}, {outage.house_numbers}\n{time_info}"
            
            logger.info(f"📤 Відправка планового пушу: {outage.city}, {outage.street}")
            
            sent_successfully = False
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
                    sent_successfully = True
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
                        }],
                        device_ids=result.get('device_ids', [])
                    )
                    logger.info(f"✅ Плановий push: {result['success']} пристроїв для {outage.city}, {outage.street}, {house}")
                else:
                    logger.info(f"ℹ️ Немає користувачів для {outage.city}, {outage.street}, {house}")
            
            # ФІКСУЄМО ЩО PUSH ВІДПРАВЛЕНО
            if sent_successfully:
                outage.notification_sent_at = current_time
                db.commit()
                logger.info(f"✅ Позначено планове відключення як оповіщене: {outage.id}")
        
        # ========== 3. ВІДКЛЮЧЕННЯ ПО ЧЕРГАХ (1.1, 1.2, etc) ==========
        from app.models import QueueNotification
        
        today = current_time.date()
        schedule = crud_schedules.get_schedule_by_date(db=db, date_val=today)
        
        if schedule and schedule.parsed_data:
            parsed_data = schedule.parsed_data
            
            # Перевіряємо відключення за 10 хвилин АБО ті що вже почалися
            for hour_str, queues in parsed_data.items():
                hour = int(hour_str.split(':')[0])
                
                # Створюємо datetime для цієї години (в київському часі)
                outage_time = current_time.replace(hour=hour, minute=0, second=0, microsecond=0)
                
                # Якщо ця година в межах 10 хвилин АБО вже почалася (але не більше години тому)
                time_diff = (current_time - outage_time).total_seconds() / 60  # різниця в хвилинах
                should_notify = (current_time < outage_time <= target_time) or (0 <= time_diff <= 60)
                
                if should_notify:
                    logger.info(f"⚡ Перевірка черг для відключення о {hour:02d}:00: {queues}")
                    
                    for queue in queues:
                        # ПЕРЕВІРКА: чи вже відправляли для цієї дати/години/черги
                        already_sent = db.query(QueueNotification).filter(
                            QueueNotification.date == today,
                            QueueNotification.hour == hour,
                            QueueNotification.queue == queue
                        ).first()
                        
                        if already_sent:
                            logger.debug(f"ℹ️ Push для черги {queue} о {hour:02d}:00 вже відправлено раніше")
                            continue
                        
                        # Знаходимо користувачів з цією чергою
                        user_addresses = db.query(UserAddress).filter(
                            UserAddress.queue == queue
                        ).all()
                        
                        if not user_addresses:
                            logger.info(f"ℹ️ Немає користувачів для черги {queue}")
                            continue
                        
                        logger.info(f"📤 Відправка push для черги {queue} ({len(user_addresses)} адрес)")
                        
                        # Дедуплікація: один користувач може мати кілька адрес
                        device_ids = list(set([ua.device_id for ua in user_addresses]))
                        
                        tokens = db.query(DeviceToken).filter(
                            DeviceToken.device_id.in_(device_ids),
                            DeviceToken.notifications_enabled == True
                        ).all()
                        
                        if not tokens:
                            logger.info(f"ℹ️ Немає активних пристроїв для черги {queue}")
                            continue
                        
                        fcm_tokens = [token.fcm_token for token in tokens]
                        active_device_ids = [token.device_id for token in tokens]
                        
                        # Визначаємо текст повідомлення
                        if time_diff > 0:
                            title = f"⚡ Відключення черги {queue} ЗАРАЗ"
                            body = f"Почалося о {hour:02d}:00 згідно графіку"
                        else:
                            minutes_until = int((outage_time - current_time).total_seconds() / 60)
                            title = f"⚡ Відключення черги {queue} за {minutes_until} хв"
                            body = f"Згідно графіку, о {hour:02d}:00 буде відключено чергу {queue}"
                        
                        result = firebase_service.send_push_to_multiple(
                            fcm_tokens=fcm_tokens,
                            title=title,
                            body=body,
                            data={
                                "type": "queue_outage",
                                "queue": queue,
                                "hour": str(hour)
                            }
                        )
                        
                        if result['success'] > 0:
                            # ФІКСУЄМО ЩО PUSH ВІДПРАВЛЕНО
                            queue_notif = QueueNotification(
                                date=today,
                                hour=hour,
                                queue=queue
                            )
                            db.add(queue_notif)
                            db.commit()
                            
                            crud_notifications.create_notification(
                                db=db,
                                notification_type="queue",
                                category="scheduled",
                                title=title,
                                body=body,
                                device_ids=active_device_ids
                            )
                            logger.info(f"✅ Черга {queue}: {result['success']} push відправлено, зафіксовано в БД")
                        else:
                            logger.info(f"⚠️ Черга {queue}: {result['failed']} помилок")
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


def reset_no_schedule_state(db: Session):
    """
    Скидає стан повідомлень "немає графіка" коли додається новий графік
    """
    from app.models import NoScheduleNotificationState
    
    try:
        state = db.query(NoScheduleNotificationState).first()
        
        if not state:
            # Створюємо початковий стан
            state = NoScheduleNotificationState(
                enabled=True,
                consecutive_days_without_schedule=0
            )
            db.add(state)
        else:
            # Скидаємо лічильник і вмикаємо повідомлення
            state.enabled = True
            state.consecutive_days_without_schedule = 0
        
        db.commit()
        logger.info("✅ Скинуто стан повідомлень 'немає графіка' (додано новий графік)")
    
    except Exception as e:
        logger.error(f"❌ Помилка при скиданні стану: {e}")
        db.rollback()


def check_tomorrow_schedule_and_notify():
    """
    Перевіряє чи є графік на завтра (викликається о 23:00)
    Якщо немає - відправляє повідомлення користувачам та в Telegram
    
    Логіка:
    1. Перевіряємо чи є графік на завтра
    2. Якщо немає і enabled=True → відправляємо push
    3. Збільшуємо лічильник consecutive_days_without_schedule
    4. Якщо лічильник досяг 5 → вимикаємо повідомлення (enabled=False)
    5. Якщо є графік → пропускаємо (стан скинеться автоматично при додаванні графіка)
    """
    from app.models import NoScheduleNotificationState
    from datetime import date, timedelta
    from app import crud_schedules
    from app.services import firebase_service, telegram_service
    
    db: Session = SessionLocal()
    
    try:
        tomorrow = date.today() + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%d.%m.%Y")
        
        logger.info(f"🌙 Перевірка графіка на завтра ({tomorrow_str}) о 23:00")
        
        # Отримуємо або створюємо стан
        state = db.query(NoScheduleNotificationState).first()
        if not state:
            state = NoScheduleNotificationState(
                enabled=True,
                consecutive_days_without_schedule=0
            )
            db.add(state)
            db.commit()
        
        # Перевіряємо чи є графік на завтра
        schedule = crud_schedules.get_schedule_by_date(db=db, date_val=tomorrow)
        
        if schedule:
            logger.info(f"✅ Графік на завтра ({tomorrow_str}) є в базі - повідомлення не потрібне")
            state.last_check_date = date.today()
            db.commit()
            return
        
        # Графіка немає
        logger.info(f"📭 Графіка на завтра ({tomorrow_str}) немає")
        
        # Перевіряємо чи увімкнені повідомлення
        if not state.enabled:
            logger.info(f"🔕 Повідомлення вимкнені (було {state.consecutive_days_without_schedule} днів без графіків)")
            state.last_check_date = date.today()
            db.commit()
            return
        
        # Відправляємо повідомлення
        title = "📭 Немає графіка на завтра"
        body = f"Графік погодинних відключень на {tomorrow_str} ще не опубліковано"
        
        logger.info(f"📤 Відправка push всім користувачам: {title}")
        
        # Push всім користувачам
        result = firebase_service.send_to_all_users(
            db=db,
            title=title,
            body=body,
            data={
                "type": "no_schedule",
                "date": tomorrow.isoformat()
            }
        )
        
        logger.info(f"✅ Push відправлено: {result['success']} успішно, {result['failed']} невдало")
        
        # Telegram повідомлення
        telegram_message = f"📭 *Немає графіка на завтра*\n\nГрафік погодинних відключень на {tomorrow_str} ще не опубліковано"
        telegram_service.send_telegram_notification(telegram_message)
        logger.info("📨 Повідомлення відправлено в Telegram")
        
        # Зберігаємо в історію
        crud_notifications.create_notification(
            db=db,
            notification_type="all",
            category="no_schedule",
            title=title,
            body=body
        )
        
        # Оновлюємо стан
        state.consecutive_days_without_schedule += 1
        state.last_check_date = date.today()
        state.last_notification_date = date.today()
        
        logger.info(f"📊 Лічильник днів без графіка: {state.consecutive_days_without_schedule}")
        
        # Якщо 5 днів підряд - вимикаємо повідомлення
        if state.consecutive_days_without_schedule >= 5:
            state.enabled = False
            logger.warning(f"🔕 ВИМКНЕНО повідомлення 'немає графіка' (5 днів поспіль)")
            
            # Відправляємо службове повідомлення в Telegram
            admin_message = "⚠️ *Автоматичне вимкнення*\n\nПовідомлення 'немає графіка' вимкнено після 5 днів без графіків.\nВони автоматично увімкнуться коли з'явиться новий графік."
            telegram_service.send_telegram_notification(admin_message)
        
        db.commit()
        logger.info("✅ Перевірку графіка на завтра завершено")
    
    except Exception as e:
        logger.error(f"❌ Помилка при перевірці графіка на завтра: {e}")
        logger.exception("Детальна інформація:")
        db.rollback()
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
    
    # ⭐ Перевірка та перезавантаження відсутніх зображень - при старті та щодня о 4:00
    from app.utils.image_downloader_sync import check_and_redownload_missing_images
    scheduler.add_job(lambda: check_and_redownload_missing_images(SessionLocal()), 'cron', hour=4, minute=0, id='check_images')
    scheduler.add_job(lambda: check_and_redownload_missing_images(SessionLocal()), 'date', run_date=start_time + timedelta(seconds=30), id='check_images_initial')
    
    # ⭐ Аварійні - перший запуск через 15с, потім з заданим інтервалом
    scheduler.add_job(update_emergency_outages, 'interval', minutes=check_interval, id='emergency', 
                     next_run_time=start_time + timedelta(seconds=5))
    
    # ⭐ Оголошення з сайту - перший запуск через 20с, потім з заданим інтервалом
    scheduler.add_job(check_and_notify_announcements, 'interval', minutes=check_interval, id='announcements',
                     next_run_time=start_time + timedelta(seconds=10))
    
    # ⭐ Планові - перший запуск через 25с, потім ТІЛЬКИ 1 раз на день о 9:00
    scheduler.add_job(update_planned_outages, 'cron', hour=9, minute=0, id='planned')
    scheduler.add_job(update_planned_outages, 'date', run_date=start_time + timedelta(seconds=15), id='planned_initial')
    
    # ⭐ Сповіщення за 10 хв (аварійні/планові/черги) - з заданим інтервалом
    scheduler.add_job(check_upcoming_outages_and_notify, 'interval', minutes=check_interval, id='notifications')
    
    # ⭐ Перевірка чи є графік на завтра - щодня о 23:00
    scheduler.add_job(check_tomorrow_schedule_and_notify, 'cron', hour=23, minute=0, id='check_tomorrow')
    
    # Очищення старих відключень - раз на добу о 2:00
    scheduler.add_job(cleanup_old_outages, 'cron', hour=2, minute=0, id='cleanup_outages')
    
    # Очищення старих повідомлень - щодня о 3:00
    scheduler.add_job(cleanup_old_notifications_job, 'cron', hour=3, minute=0, id='cleanup_notifications')
    
    scheduler.start()
    logger.info("=" * 60)
    logger.info("✅ Планувальник запущено:")
    logger.info(f"  📅 Графіки: кожні {check_interval} хвилин")
    logger.info("  🖼️ Перевірка зображень: при старті та щодня о 4:00")
    logger.info(f"  ⚠️ Аварійні відключення: кожні {check_interval} хвилин")
    logger.info(f"  📢 Оголошення з сайту: кожні {check_interval} хвилин")
    logger.info("  📋 Планові відключення: щодня о 9:00")
    logger.info(f"  🔔 Сповіщення за 10 хв: кожні {check_interval} хвилин")
    logger.info("  🌙 Перевірка графіка на завтра: щодня о 23:00")
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
