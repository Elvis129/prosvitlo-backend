from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta
from typing import List, Dict, Any
import logging
import hashlib
import json
import pytz

from app.scraper.schedule_parser import fetch_schedule_images, parse_queue_schedule
from app.scraper.announcements_parser import fetch_announcements, check_schedule_availability
from app.utils.image_downloader_sync import download_schedule_image_sync
from app.scraper.outage_parser import fetch_all_emergency_outages, fetch_all_planned_outages
from app import crud_schedules, crud_outages
from app.models import EmergencyOutage, PlannedOutage
from app.database import SessionLocal

# Київська часова зона
KYIV_TZ = pytz.timezone('Europe/Kiev')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ВАЖЛИВО: Scheduler працює в київській часовій зоні
scheduler = BackgroundScheduler(timezone='Europe/Kiev')

# ЗМІНА: Замість in-memory sets, використовуємо БД для зберігання хешів
# Це запобігає дублюванню повідомлень після перезавантаження сервера
# Хеші завантажуються з БД при старті та оновлюються при відправці
last_announcement_hashes = set()  # Буде завантажено з БД при старті
last_sent_paragraphs = set()  # Буде завантажено з БД при старті


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


def load_sent_hashes_from_db():
    """
    Завантажує хеші відправлених оголошень з БД при старті сервера
    Це запобігає повторній відправці після перезавантаження
    """
    global last_announcement_hashes, last_sent_paragraphs
    
    db: Session = SessionLocal()
    try:
        from app.models import SentAnnouncementHash
        from datetime import datetime, timedelta
        
        # Завантажуємо хеші за останні 7 днів (старіші можна ігнорувати)
        cutoff_date = datetime.now(KYIV_TZ) - timedelta(days=7)
        
        recent_hashes = db.query(SentAnnouncementHash).filter(
            SentAnnouncementHash.created_at >= cutoff_date
        ).all()
        
        for hash_record in recent_hashes:
            if hash_record.announcement_type == 'paragraph':
                last_sent_paragraphs.add(hash_record.content_hash)
            else:
                last_announcement_hashes.add(hash_record.content_hash)
        
        logger.info(f"📥 Завантажено з БД: {len(last_announcement_hashes)} хешів оголошень, "
                   f"{len(last_sent_paragraphs)} хешів параграфів")
        
    except Exception as e:
        logger.error(f"❌ Помилка завантаження хешів з БД: {e}")
    finally:
        db.close()


def save_sent_hash_to_db(content_hash: str, announcement_type: str = 'general', title: str = None):
    """
    Зберігає хеш відправленого оголошення в БД
    
    Args:
        content_hash: MD5 хеш контенту
        announcement_type: 'general', 'schedule', або 'paragraph'
        title: Заголовок для довідки (опціонально)
    """
    db: Session = SessionLocal()
    try:
        from app.models import SentAnnouncementHash
        
        # Перевіряємо чи вже існує
        existing = db.query(SentAnnouncementHash).filter(
            SentAnnouncementHash.content_hash == content_hash
        ).first()
        
        if not existing:
            new_hash = SentAnnouncementHash(
                content_hash=content_hash,
                announcement_type=announcement_type,
                title=title[:100] if title else None  # Обмежуємо довжину
            )
            db.add(new_hash)
            db.commit()
            logger.debug(f"💾 Збережено хеш в БД: {content_hash[:8]}... (type: {announcement_type})")
        
    except Exception as e:
        logger.error(f"❌ Помилка збереження хешу в БД: {e}")
        db.rollback()
    finally:
        db.close()


def cleanup_old_sent_hashes():
    """Видаляє старі хеші (старіші 30 днів)"""
    db: Session = SessionLocal()
    try:
        from app.models import SentAnnouncementHash
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.now(KYIV_TZ) - timedelta(days=30)
        
        deleted = db.query(SentAnnouncementHash).filter(
            SentAnnouncementHash.created_at < cutoff_date
        ).delete()
        
        db.commit()
        
        if deleted > 0:
            logger.info(f"🧹 Видалено {deleted} старих хешів оголошень")
        
    except Exception as e:
        logger.error(f"❌ Помилка очищення старих хешів: {e}")
        db.rollback()
    finally:
        db.close()


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


def send_queue_notification(schedule_date: str, queue: str, start_hour: int, end_hour: int, is_possible: bool = False):
    """
    Відправляє push для конкретної черги
    Викликається автоматично за 10 хвилин до відключення
    
    Args:
        schedule_date: Дата відключення (YYYY-MM-DD)
        queue: Номер черги (наприклад "6.1")
        start_hour: Година початку відключення
        end_hour: Година закінчення відключення
        is_possible: True якщо це можливе відключення (сіра клітинка)
    """
    # КРИТИЧНО: Виводимо в stdout для перевірки чи функція взагалі викликається
    notif_type = "МОЖЛИВЕ" if is_possible else "ТОЧНЕ"
    print(f"🔴 send_queue_notification ВИКЛИКАНО: date={schedule_date}, queue={queue}, start={start_hour}, end={end_hour}, type={notif_type}", flush=True)
    
    from app.services import firebase_service
    from app import crud_notifications
    from app.models import QueueNotification
    
    db: Session = SessionLocal()
    try:
        print(f"🔴 send_queue_notification: db створено, починаємо перевірку дедуплікації", flush=True)
        # Перевірка дедуплікації - чи не був вже відправлений пуш
        from datetime import datetime
        date_obj = datetime.strptime(schedule_date, "%Y-%m-%d").date()
        existing = db.query(QueueNotification).filter(
            QueueNotification.date == date_obj,
            QueueNotification.queue == queue,
            QueueNotification.hour == start_hour
        ).first()
        
        if existing:
            print(f"🔴 send_queue_notification: знайдено existing дедуплікації", flush=True)
            logger.info(f"⏭️ Пуш для черги {queue} на {schedule_date} о {start_hour}:00 вже відправлено")
            
            # Перевіряємо чи є запис в історії (може бути відсутній якщо старий пуш був до фіксу)
            from app.models import UserAddress, Notification
            existing_history = db.query(Notification).filter(
                Notification.notification_type == 'queue'
            ).filter(Notification.title.like(f'%{queue}%')).first()
            
            if not existing_history:
                # Історії немає - створюємо для користувачів цієї черги
                print(f"🔴 send_queue_notification: existing але немає в історії, додаємо", flush=True)
                user_addresses = db.query(UserAddress).filter(UserAddress.queue == queue).all()
                device_ids = list(set([ua.device_id for ua in user_addresses]))
                
                if device_ids:
                    title = f"⚡ Відключення черги {queue}"
                    body = f"Сьогодні о {start_hour:02d}:00 - {end_hour:02d}:00"
                    crud_notifications.create_notification(
                        db=db,
                        notification_type="queue",
                        category="schedule",
                        title=title,
                        body=body,
                        device_ids=device_ids
                    )
                    logger.info(f"💾 Додано в історію для {len(device_ids)} пристроїв (пост-фікс)")
            
            db.close()
            return
        
        print(f"🔴 send_queue_notification: починаємо відправку пушу", flush=True)
        
        # КРИТИЧНО: Позначаємо що пуш відправлено ОДРАЗУ (дедуплікація)
        # Це запобігає дублюванню якщо функція викликається повторно
        from datetime import datetime
        date_obj = datetime.strptime(schedule_date, "%Y-%m-%d").date()
        queue_notif = QueueNotification(
            date=date_obj,
            queue=queue,
            hour=start_hour
        )
        db.add(queue_notif)
        db.commit()
        print(f"🔴 send_queue_notification: створено QueueNotification для дедуплікації", flush=True)
        
        # Відправка пушу
        if is_possible:
            title = f"⚠️ Можливе відключення черги {queue}"
            body = f"Сьогодні о {start_hour:02d}:00 - {end_hour:02d}:00 можливе відключення"
        else:
            title = f"⚡ Відключення черги {queue}"
            body = f"Сьогодні о {start_hour:02d}:00 - {end_hour:02d}:00"
        
        logger.info(f"📤 Відправка пушу для черги {queue} о {start_hour}:00-{end_hour}:00")
        print(f"🔴 send_queue_notification: викликаємо firebase_service.send_to_queue_users", flush=True)
        
        result = firebase_service.send_to_queue_users(
            db=db,
            queue=queue,
            title=title,
            body=body,
            data={
                "type": "queue_possible" if is_possible else "queue",
                "category": "scheduled",
                "queue": queue,
                "date": schedule_date,
                "start_hour": str(start_hour),
                "end_hour": str(end_hour),
                "is_possible": str(is_possible)
            }
        )
        
        # Зберігаємо в історію ЗАВЖДИ якщо є пристрої (навіть якщо notifications_enabled=False)
        device_ids = result.get('device_ids', [])
        if device_ids:
            crud_notifications.create_notification(
                db=db,
                notification_type="queue",
                category="schedule",
                title=title,
                body=body,
                device_ids=device_ids
            )
            logger.info(f"💾 Збережено в історію для {len(device_ids)} пристроїв")
            
            if result['success'] > 0:
                print(f"🔴 send_queue_notification: SUCCESS! Відправлено {result['success']} пристроїв", flush=True)
                logger.info(f"✅ Відправлено пуш для черги {queue}: {result['success']} пристроїв")
            else:
                print(f"🔴 send_queue_notification: є пристрої але notifications_enabled=False", flush=True)
                logger.info(f"ℹ️ Є пристрої для черги {queue} але всі мають вимкнені сповіщення")
        else:
            print(f"🔴 send_queue_notification: немає користувачів для черги {queue}", flush=True)
            logger.info(f"ℹ️ Немає користувачів для черги {queue}")
            
    except Exception as e:
        print(f"🔴 send_queue_notification: EXCEPTION! {e}", flush=True)
        logger.error(f"Помилка при відправці пушу для черги {queue}: {e}")
        import traceback
        traceback.print_exc()
        db.rollback()
    finally:
        print(f"🔴 send_queue_notification: ЗАВЕРШЕНО (finally block)", flush=True)
        db.close()


def _create_notification_job(schedule_date: str, schedule_date_obj, current_time, queue: str, interval: tuple, is_possible: bool) -> int:
    """
    Допоміжна функція для створення notification job
    
    Returns:
        1 якщо job створено, 0 якщо пропущено
    """
    start_hour, end_hour = interval
    
    # ⚠️ ВАЖЛИВО: start_hour/end_hour - це КИЇВСЬКИЙ час!
    # Створюємо datetime в київській зоні, потім конвертуємо в naive для БД
    outage_time_kyiv = KYIV_TZ.localize(
        datetime.combine(schedule_date_obj, datetime.min.time()).replace(hour=int(start_hour), minute=0)
    )
    outage_time = outage_time_kyiv.replace(tzinfo=None)  # Naive для БД
    
    # Час відправки пушу (за 10 хвилин) - також в київському часі
    notification_time_kyiv = outage_time_kyiv - timedelta(minutes=10)
    notification_time = notification_time_kyiv.replace(tzinfo=None)  # Naive для порівняння з current_time
    
    # Відправляємо ТІЛЬКИ якщо час ще не минув
    if notification_time <= current_time:
        # Якщо вже пізно - перевіряємо чи відключення ще не закінчилось
        # end_hour може бути 24 (опівніч) - обробляємо як наступний день 00:00
        if end_hour == 24:
            outage_end_time_kyiv = KYIV_TZ.localize(
                datetime.combine(schedule_date_obj + timedelta(days=1), datetime.min.time())
            )
        else:
            outage_end_time_kyiv = KYIV_TZ.localize(
                datetime.combine(schedule_date_obj, datetime.min.time()).replace(hour=int(end_hour), minute=0)
            )
        outage_end_time = outage_end_time_kyiv.replace(tzinfo=None)
        
        if outage_end_time > current_time:
            # Відключення ще триває - відправляємо ОДРАЗУ
            notif_type = "можливе" if is_possible else "точне"
            logger.info(f"⚡ Негайна відправка для черги {queue} ({notif_type}, вже о {start_hour}:00)")
            send_queue_notification(schedule_date, queue, start_hour, end_hour, is_possible)
        else:
            logger.info(f"⏭️ Пропуск черги {queue} о {start_hour}:00 (вже минуло)")
        return 0
    
    # Створюємо динамічний job
    job_type = "possible" if is_possible else "outage"
    job_id = f"queue_{schedule_date}_{queue}_{start_hour}_{job_type}"
    
    try:
        # ⚠️ ВАЖЛИВО: Scheduler працює в київській зоні, передаємо naive datetime
        scheduler.add_job(
            send_queue_notification,
            'date',
            run_date=notification_time,  # Naive київський datetime
            args=[schedule_date, queue, start_hour, end_hour, is_possible],
            id=job_id,
            replace_existing=True
        )
        notif_type = "можливе" if is_possible else "точне"
        logger.info(f"✅ Заплановано пуш ({notif_type}) для черги {queue} на {notification_time.strftime('%d.%m %H:%M')} (Київ)")
        return 1
    except Exception as e:
        logger.error(f"❌ Помилка при плануванні job для черги {queue}: {e}")
        return 0


def schedule_queue_notifications(schedule_date: str, parsed_data: dict):
    """
    Створює динамічні jobs для кожної черги в графіку
    Кожен job спрацює за 10 хвилин до відключення
    
    Args:
        schedule_date: Дата графіка (YYYY-MM-DD)
        parsed_data: Розпарсений графік 
            Старий формат: {"6.1": [[12, 16]], ...}
            Новий формат: {"6.1": {"outages": [(12, 16)], "possible": [(8, 10)]}, ...}
    """
    try:
        logger.info(f"🔹 ПОЧАТОК schedule_queue_notifications для {schedule_date}")
        logger.info(f"🔹 parsed_data type: {type(parsed_data)}, content: {parsed_data}")
        
        current_time = datetime.now(KYIV_TZ).replace(tzinfo=None)
        schedule_date_obj = datetime.strptime(schedule_date, "%Y-%m-%d").date()
        
        # Видаляємо старі jobs для цієї дати (якщо графік оновився)
        job_prefix = f"queue_{schedule_date}_"
        removed_count = 0
        for job in scheduler.get_jobs():
            if job.id.startswith(job_prefix):
                job.remove()
                removed_count += 1
        if removed_count > 0:
            logger.info(f"🗑️ Видалено {removed_count} старих jobs")
        
        logger.info(f"📅 Планування пушів для графіка {schedule_date}")
        
        # Перевірка чи parsed_data це string (JSON)
        if isinstance(parsed_data, str):
            logger.info(f"⚠️ parsed_data - це string, парсимо JSON")
            import json
            parsed_data = json.loads(parsed_data)
        
        jobs_created = 0
        for queue, queue_data in parsed_data.items():
            logger.info(f"🔹 Обробка черги {queue}, дані: {queue_data}")
            
            # Підтримка нового формату з окремими outages/possible
            if isinstance(queue_data, dict) and 'outages' in queue_data:
                # Новий формат: {"outages": [...], "possible": [...]}
                outages_intervals = queue_data.get('outages', [])
                possible_intervals = queue_data.get('possible', [])
                logger.info(f"  📘 Новий формат: відключення {outages_intervals}, можливі {possible_intervals}")
                
                # Обробляємо точні відключення
                for interval in outages_intervals:
                    jobs_created += _create_notification_job(
                        schedule_date, schedule_date_obj, current_time, queue, interval, is_possible=False
                    )
                
                # Обробляємо можливі відключення
                for interval in possible_intervals:
                    jobs_created += _create_notification_job(
                        schedule_date, schedule_date_obj, current_time, queue, interval, is_possible=True
                    )
            else:
                # Старий формат: просто список інтервалів
                intervals = queue_data
                logger.info(f"  📗 Старий формат: {intervals}")
                
                for interval in intervals:
                    jobs_created += _create_notification_job(
                        schedule_date, schedule_date_obj, current_time, queue, interval, is_possible=False
                    )
        
        logger.info(f"🔹 ЗАВЕРШЕНО schedule_queue_notifications: створено {jobs_created} jobs")
    except Exception as e:
        logger.error(f"❌ КРИТИЧНА ПОМИЛКА в schedule_queue_notifications: {e}")
        logger.exception("Детальна інформація:")


def parse_queue_times_from_announcement(text: str) -> List[Dict[str, Any]]:
    """
    Витягує з тексту оголошення інформацію про черги та часові проміжки відключень
    
    Приклади:
    - "підчергу 6.2 з 10:00 до 14:00"
    - "споживачів підчерги 3.1 з 09:00 до 12:00"
    - "черга 4.2 буде відключена з 15:00 до 19:00"
    
    Returns:
        List[Dict] з полями: queue, start_hour, end_hour, is_power_on (True якщо "заживлення")
    """
    import re
    from datetime import datetime
    
    results = []
    
    # Паттерн для пошуку черг та часових проміжків
    # Шукаємо: "підчерг[уи]?" + "X.Y" + "з" + "HH:MM" + "до" + "HH:MM"
    pattern = r'підчерг[уиі]?\s+(\d+\.\d+)\s+з\s+(\d{1,2}):(\d{2})\s+до\s+(\d{1,2}):(\d{2})'
    
    matches = re.finditer(pattern, text, re.IGNORECASE)
    
    for match in matches:
        queue = match.group(1)  # Наприклад "6.2"
        start_hour = int(match.group(2))
        start_min = int(match.group(3))
        end_hour = int(match.group(4))
        end_min = int(match.group(5))
        
        # Визначаємо чи це увімкнення світла (заживлення) чи відключення
        # Шукаємо ключові слова перед згадкою черги
        context_before = text[:match.start()].lower()
        is_power_on = 'заживлення' in context_before or 'повернення' in context_before or 'відновлення' in context_before
        is_power_off = 'знеструмлен' in context_before or 'відключен' in context_before or 'вимкнен' in context_before
        
        # Якщо не знайшли контекст, шукаємо після
        if not is_power_on and not is_power_off:
            context_after = text[match.end():match.end()+50].lower()
            is_power_on = 'заживлення' in context_after or 'повернення' in context_after
            is_power_off = 'знеструмлен' in context_after or 'відключен' in context_after
        
        # Якщо хвилини не 00, округлюємо до годин (для сумісності з поточною системою)
        if start_min != 0:
            logger.warning(f"⚠️ Оголошення містить хвилини ({start_hour}:{start_min}), округляємо до {start_hour}:00")
        if end_min != 0:
            logger.warning(f"⚠️ Оголошення містить хвилини ({end_hour}:{end_min}), округляємо до {end_hour}:00")
        
        results.append({
            'queue': queue,
            'start_hour': start_hour,
            'end_hour': end_hour,
            'is_power_on': is_power_on,
            'is_power_off': is_power_off,
            'matched_text': match.group(0)
        })
        
        logger.info(f"📋 Витягнуто з оголошення: черга {queue}, {start_hour}:00-{end_hour}:00, "
                   f"{'✅ заживлення' if is_power_on else '⚡ відключення' if is_power_off else '❓ невизначено'}")
    
    return results


def check_and_notify_announcements():
    """
    Перевіряє загальні оголошення з сайту кожні 5 хвилин
    Відправляє push ТІЛЬКИ якщо є НОВІ оголошення
    + Витягує часові проміжки для черг та створює додаткові пуші
    + Фільтрує вже відправлені параграфи для запобігання дублювання
    + Зберігає хеші в БД для запобігання дублюванню після перезавантаження
    """
    global last_announcement_hashes, last_sent_paragraphs
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
            
            # ⭐ НОВА ЛОГІКА: Фільтруємо вже відправлені параграфи з повідомлення
            full_body = announcement.get('full_body', announcement['body'])
            paragraphs = full_body.split('\n\n')
            
            # Знаходимо нові параграфи (які ще не відправляли)
            new_paragraphs = []
            for para in paragraphs:
                para_stripped = para.strip()
                if not para_stripped or len(para_stripped) < 10:
                    continue
                
                # Генеруємо хеш параграфа
                para_hash = hashlib.md5(para_stripped.encode()).hexdigest()
                
                # Якщо параграф новий - додаємо
                if para_hash not in last_sent_paragraphs:
                    new_paragraphs.append(para_stripped)
                    last_sent_paragraphs.add(para_hash)
                    # ⭐ Зберігаємо хеш параграфа в БД
                    save_sent_hash_to_db(para_hash, announcement_type='paragraph')
                else:
                    logger.info(f"⏭️ Пропущено вже відправлений параграф: {para_stripped[:50]}...")
            
            # Якщо всі параграфи вже були відправлені - пропускаємо оголошення
            if not new_paragraphs:
                logger.info(f"ℹ️ Всі параграфи в оголошенні '{announcement['title']}' вже були відправлені")
                last_announcement_hashes.add(content_hash)
                # ⭐ Зберігаємо хеш оголошення в БД
                save_sent_hash_to_db(content_hash, announcement_type='general', title=announcement['title'])
                continue
            
            # Формуємо текст тільки з НОВИХ параграфів
            filtered_body = '\n\n'.join(new_paragraphs)
            
            # Нове оголошення - відправляємо push ВСІМ
            title = announcement['title']
            
            # Для push обмежуємо текст (500 символів для повноти інформації)
            push_body = filtered_body[:500] + '...' if len(filtered_body) > 500 else filtered_body
            
            result = firebase_service.send_to_all_users(
                db=db,
                title=title,
                body=push_body,
                data={
                    "type": "announcement",
                    "category": "general",
                    "source": announcement['source']
                }
            )
            
            if result['success'] > 0:
                # Зберігаємо ВІДФІЛЬТРОВАНИЙ текст в історію
                crud_notifications.create_notification(
                    db=db,
                    notification_type="all",
                    category="general",
                    title=title,
                    body=filtered_body
                )
                
                # Запам'ятовуємо що відправили
                last_announcement_hashes.add(content_hash)
                # ⭐ Зберігаємо хеш оголошення в БД
                save_sent_hash_to_db(content_hash, announcement_type='general', title=title)
                
                # Відправляємо ВІДФІЛЬТРОВАНИЙ текст в Telegram канал
                telegram = get_telegram_service()
                if telegram:
                    telegram_success = telegram.send_announcement(
                        title=title,
                        body=filtered_body,
                        source=announcement['source']
                    )
                    if telegram_success:
                        logger.info(f"✅ Telegram: повідомлення відправлено в канал")
                    else:
                        logger.error(f"❌ Telegram: помилка відправки")
                else:
                    logger.warning(f"⚠️ Telegram сервіс не ініціалізований")
                logger.info(f"✅ Відправлено оголошення ВСІМ: {title}")
                
                # ⭐ ФУНКЦІОНАЛ: Парсимо часові проміжки для черг
                queue_times = parse_queue_times_from_announcement(filtered_body)
                if queue_times:
                    logger.info(f"🕐 Знайдено {len(queue_times)} часових проміжків для черг в оголошенні")
                    
                    # Отримуємо поточну дату для створення jobs
                    now = datetime.now(KYIV_TZ)
                    today_str = now.strftime('%Y-%m-%d')
                    today_date = now.date()
                    
                    from app.models import AnnouncementOutage
                    
                    for qt in queue_times:
                        # Створюємо пуш тільки для ВІДКЛЮЧЕНЬ (is_power_off=True)
                        # Заживлення (is_power_on) - це повернення світла, не потребує окремого пушу
                        if qt['is_power_off']:
                            queue = qt['queue']
                            start_hour = qt['start_hour']
                            end_hour = qt['end_hour']
                            
                            logger.info(f"📅 Обробка додаткового відключення черги {queue}: {start_hour}:00-{end_hour}:00")
                            
                            # ⭐ Зберігаємо в БД
                            try:
                                # Перевіряємо чи вже є такий запис
                                existing = db.query(AnnouncementOutage).filter(
                                    AnnouncementOutage.date == today_date,
                                    AnnouncementOutage.queue == queue,
                                    AnnouncementOutage.start_hour == start_hour,
                                    AnnouncementOutage.end_hour == end_hour
                                ).first()
                                
                                if existing:
                                    logger.info(f"ℹ️ Запис про відключення черги {queue} вже існує в БД")
                                else:
                                    # Створюємо новий запис
                                    announcement_outage = AnnouncementOutage(
                                        date=today_date,
                                        queue=queue,
                                        start_hour=start_hour,
                                        end_hour=end_hour,
                                        announcement_text=filtered_body[:500],  # Зберігаємо перші 500 символів
                                        is_active=True
                                    )
                                    db.add(announcement_outage)
                                    db.commit()
                                    logger.info(f"💾 Збережено в БД: черга {queue}, {start_hour}:00-{end_hour}:00")
                                
                            except Exception as db_error:
                                logger.error(f"❌ Помилка збереження в БД: {db_error}")
                                db.rollback()
                            
                            # Створюємо job за 10 хвилин до відключення (як для звичайних графіків)
                            notification_time = now.replace(hour=start_hour, minute=0, second=0, microsecond=0)
                            notification_time = notification_time - timedelta(minutes=10)
                            
                            # Якщо час вже минув сьогодні, не створюємо job
                            if notification_time < now:
                                logger.warning(f"⚠️ Час нотифікації {notification_time.strftime('%H:%M')} вже минув, пропускаємо")
                                continue
                            
                            job_id = f"queue_announcement_{queue}_{start_hour}_{now.strftime('%Y%m%d%H%M%S')}"
                            
                            try:
                                scheduler.add_job(
                                    send_queue_notification,
                                    trigger='date',
                                    run_date=notification_time,
                                    args=[today_str, queue, start_hour, end_hour],
                                    id=job_id,
                                    replace_existing=True,
                                    misfire_grace_time=300
                                )
                                logger.info(f"✅ Заплановано пуш для черги {queue} (з оголошення) на {notification_time.strftime('%H:%M')}")
                            except Exception as job_error:
                                logger.error(f"❌ Помилка створення job для черги {queue}: {job_error}")
                        elif qt['is_power_on']:
                            logger.info(f"ℹ️ Пропускаємо заживлення черги {qt['queue']} (не потребує окремого пушу)")
                        else:
                            logger.warning(f"⚠️ Не вдалося визначити тип події для черги {qt['queue']}, пропускаємо")
        
        # Очищаємо старі хеші (залишаємо останні 100)
        if len(last_announcement_hashes) > 100:
            last_announcement_hashes.clear()
        
        # Очищаємо старі параграфи (залишаємо останні 200)
        if len(last_sent_paragraphs) > 200:
            # Видаляємо половину найстаріших
            to_keep = list(last_sent_paragraphs)[-100:]
            last_sent_paragraphs.clear()
            last_sent_paragraphs.update(to_keep)
            logger.info(f"🧹 Очищено кеш параграфів, залишено {len(last_sent_paragraphs)}")
            
    except Exception as e:
        logger.error(f"Помилка при перевірці оголошень: {e}")
    finally:
        db.close()


def update_schedules():
    """
    Оновлює графіки кожні 5 хвилин
    Використовує color-based parser для аналізу зображень графіків
    Перезаписує ТІЛЬКИ якщо дані змінилися (перевірка по хешу)
    Відправляє повідомлення про НОВІ графіки (нові дати)
    """
    db: Session = SessionLocal()
    schedule_changed = False
    new_dates_added = []  # Відстежуємо нові дати
    
    try:
        logger.info("🔄 [v4-COLOR-PARSER] Початок оновлення графіків з підтримкою парсингу кольорів...")
        
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
            content_hash = schedule_info.get('content_hash')

            if not schedule_date:
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
            parsed_schedule = None
            schedule_needs_update = False
            
            if existing:
                # Графік вже є в БД - перевіряємо чи змінився
                if existing.content_hash == content_hash:
                    logger.info(f"Графік для {schedule_date} не змінився - використовуємо з БД")
                    # Витягуємо parsed_data з БД
                    import json
                    try:
                        parsed_schedule = json.loads(existing.parsed_data) if isinstance(existing.parsed_data, str) else existing.parsed_data
                        
                        # ⭐ ВАЖЛИВО: якщо в БД немає parsed_data - парсимо заново
                        if not parsed_schedule:
                            logger.warning(f"⚠️ Графік для {schedule_date} в БД але без parsed_data - перепарсуємо")
                            schedule_needs_update = True
                            try:
                                from app.scraper.schedule_color_parser import parse_schedule_from_image
                                parsed_schedule = parse_schedule_from_image(image_url)
                                logger.info(f"✅ [v4] Color парсер знайшов {len(parsed_schedule)} підчерг (fallback)")
                            except Exception as e:
                                logger.error(f"❌ [v4] Color parser помилка (fallback): {e}")
                                parsed_schedule = {}
                        
                    except Exception as e:
                        logger.error(f"Помилка парсингу даних з БД: {e}")
                        # Якщо не вдалось витягти з БД - парсимо заново COLOR-BASED методом
                        schedule_needs_update = True
                        logger.info(f"🎨 [v4] Використовую color-based парсер (БД fallback)")
                        try:
                            from app.scraper.schedule_color_parser import parse_schedule_from_image
                            parsed_schedule = parse_schedule_from_image(image_url)
                        except Exception as parse_err:
                            logger.error(f"❌ [v4] Color parser помилка: {parse_err}")
                            parsed_schedule = {}
                else:
                    schedule_changed = True
                    schedule_needs_update = True
                    logger.info(f"Графік для {schedule_date} ЗМІНИВСЯ - парсимо заново")
                    # Одразу використовуємо color-based парсер
                    logger.info(f"🎨 [v4] Використовую color-based парсер (зміна графіка)")
                    try:
                        from app.scraper.schedule_color_parser import parse_schedule_from_image
                        parsed_schedule = parse_schedule_from_image(image_url)
                        logger.info(f"✅ [v4] Color парсер знайшов {len(parsed_schedule)} підчерг")
                    except Exception as e:
                        logger.error(f"❌ [v4] Color parser помилка: {e}")
                        parsed_schedule = {}
            else:
                # Нового графіка немає в БД - парсимо color-based методом
                schedule_changed = True
                schedule_needs_update = True
                logger.info(f"🎨 [v4] Новий графік {schedule_date}, використовую color-based парсер")
                try:
                    from app.scraper.schedule_color_parser import parse_schedule_from_image
                    parsed_schedule = parse_schedule_from_image(image_url)
                    logger.info(f"✅ [v4] Color парсер знайшов {len(parsed_schedule)} підчерг для {schedule_date}")
                except Exception as e:
                    logger.error(f"❌ [v4] Color parser помилка: {e}")
                    parsed_schedule = {}
                
                logger.info(f"🔍 [v4] parsed_schedule: {len(parsed_schedule) if parsed_schedule else 0} підчерг")
                # Якщо це майбутня дата (завтра або пізніше) - відправимо повідомлення
                if schedule_date >= today:
                    new_dates_added.append(schedule_date)
                    logger.info(f"📅 НОВИЙ графік на {schedule_date} буде додано")
            
            # Оновлюємо БД тільки якщо графік змінився
            if schedule_needs_update:
                local_image_path = download_schedule_image_sync(image_url)
                if local_image_path and local_image_path != image_url:
                    if local_image_path.startswith('/static/'):
                        from app.config import settings
                        image_url = f"{settings.BASE_URL}{local_image_path}"
                    else:
                        image_url = local_image_path
                
                if existing:
                    crud_schedules.update_schedule(
                        db=db,
                        schedule_id=existing.id,
                        image_url=image_url,
                        recognized_text="",
                        parsed_data=parsed_schedule,
                        content_hash=content_hash
                    )
                else:
                    crud_schedules.create_schedule(
                        db=db,
                        date=schedule_date,
                        image_url=image_url,
                        recognized_text="",
                        parsed_data=parsed_schedule,
                        content_hash=content_hash
                    )
            
            # ⭐ ЗАВЖДИ створюємо динамічні jobs для черг (навіть якщо графік не змінився)
            # Це потрібно щоб відновити jobs після рестарту сервера
            # ВАЖЛИВО: Якщо parsed_schedule порожній {} - jobs не створюються
            if parsed_schedule:  # Тільки якщо є дані
                try:
                    logger.info(f"📅 Викликаємо schedule_queue_notifications для {schedule_date}")
                    schedule_queue_notifications(str(schedule_date), parsed_schedule)
                    logger.info(f"✅ schedule_queue_notifications завершено для {schedule_date}")
                except Exception as e:
                    logger.error(f"❌ Помилка в schedule_queue_notifications для {schedule_date}: {e}")
                    logger.exception("Детальна інформація про помилку:")
            else:
                logger.info(f"⏭️ Пропускаємо створення jobs для {schedule_date} - немає текстової версії")
        
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
        
        # 🔔 СТВОРЮЄМО JOBS для нових відключень
        if new_outages_list:
            logger.info(f"🔔 Планування пушів для {len(new_outages_list)} нових аварійних відключень")
            for new_outage in new_outages_list:
                notify_new_outages_immediately(db, [new_outage], "emergency")
        
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
        
        # 🔔 СТВОРЮЄМО JOBS для нових відключень
        if new_outages_list:
            logger.info(f"🔔 Планування пушів для {len(new_outages_list)} нових планових відключень")
            for new_outage in new_outages_list:
                notify_new_outages_immediately(db, [new_outage], "planned")
        
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
        # Пропускаємо якщо відключення вже закінчилося
        if outage.end_time <= current_time:
            logger.info(f"⏭️ Пропуск - відключення вже закінчилося: {outage.city}, {outage.street}")
            continue
        
        # Перевіряємо чи вже був відправлений пуш
        if outage.notification_sent_at is not None:
            logger.info(f"⏭️ Пропуск - пуш вже відправлено: {outage.city}, {outage.street}")
            continue
        
        # Визначаємо коли відправити пуш
        minutes_until = int((outage.start_time - current_time).total_seconds() / 60)
        
        if minutes_until > 10:
            # Якщо більше 10 хвилин - створюємо job
            schedule_outage_notification(outage, outage_type)
        else:
            # Якщо менше 10 хвилин АБО вже почалось - відправляємо ОДРАЗУ
            send_outage_notification(outage.id, outage_type)


def send_outage_notification(outage_id: int, outage_type: str):
    """
    Відправляє push для конкретного відключення (аварійного чи планового)
    
    Args:
        outage_id: ID відключення в БД
        outage_type: "emergency" або "planned"
    """
    from app.services import firebase_service
    from app import crud_notifications
    
    db: Session = SessionLocal()
    try:
        # Отримуємо відключення з БД
        if outage_type == "emergency":
            outage = db.query(EmergencyOutage).filter(EmergencyOutage.id == outage_id).first()
        else:
            outage = db.query(PlannedOutage).filter(PlannedOutage.id == outage_id).first()
        
        if not outage:
            logger.error(f"❌ Відключення {outage_type} з ID {outage_id} не знайдено")
            db.close()
            return
        
        # Перевірка дедуплікації
        if outage.notification_sent_at is not None:
            logger.info(f"⏭️ Пуш для {outage_type} {outage_id} вже відправлено")
            db.close()
            return
        
        current_time = datetime.now(KYIV_TZ).replace(tzinfo=None)
        
        # Перевіряємо чи відключення ще актуальне
        if outage.end_time <= current_time:
            logger.info(f"⏭️ Відключення {outage_type} {outage_id} вже закінчилось")
            db.close()
            return
        
        # Формуємо повідомлення
        start_time_str = outage.start_time.strftime("%H:%M")
        end_time_str = outage.end_time.strftime("%H:%M")
        
        if outage.start_time <= current_time:
            # Вже почалося
            if outage_type == "emergency":
                title = "⚠️ Аварійне відключення ЗАРАЗ"
            else:
                title = "📋 Планове відключення ЗАРАЗ"
            time_info = f"Почалося о {start_time_str}, триватиме до {end_time_str}"
        else:
            # Ще не почалося
            if outage_type == "emergency":
                title = f"⚠️ Аварійне відключення о {start_time_str}"
            else:
                title = f"📋 Планове відключення о {start_time_str}"
            time_info = f"{start_time_str} - {end_time_str}"
        
        logger.info(f"📤 Відправка пушу для {outage_type}: {outage.city}, {outage.street}")
        
        # ⚡ ОПТИМІЗАЦІЯ: Спочатку отримуємо ВСІ адреси користувачів для цього міста/вулиці
        from app.models import UserAddress, DeviceToken
        houses_list = [h.strip() for h in outage.house_numbers.split(',')]
        
        user_addresses = db.query(UserAddress).filter(
            UserAddress.city == outage.city,
            UserAddress.street == outage.street,
            UserAddress.house_number.in_(houses_list)
        ).all()
        
        logger.info(f"📊 Знайдено {len(user_addresses)} користувачів на {outage.street} в будинках: {houses_list}")
        
        if not user_addresses:
            logger.info(f"ℹ️ Немає зареєстрованих користувачів для {outage.city}, {outage.street}")
            return
        
        # Групуємо адреси по будинках
        addresses_by_house = {}
        for ua in user_addresses:
            if ua.house_number not in addresses_by_house:
                addresses_by_house[ua.house_number] = []
            addresses_by_house[ua.house_number].append(ua)
        
        # Відправляємо для кожного будинку окремо
        sent_to_any = False
        all_device_ids = []
        
        for house in houses_list:
            if house not in addresses_by_house:
                logger.info(f"ℹ️ Немає користувачів для будинку {house}")
                continue
            
            house_addresses = addresses_by_house[house]
            device_ids = list(set([ua.device_id for ua in house_addresses]))
            
            # Отримуємо токени для цих пристроїв
            tokens = db.query(DeviceToken).filter(
                DeviceToken.device_id.in_(device_ids),
                DeviceToken.notifications_enabled == True
            ).all()
            
            if not tokens:
                logger.info(f"ℹ️ Немає активних пристроїв для будинку {house}")
                continue
            
            fcm_tokens = list(set([token.fcm_token for token in tokens]))
            active_device_ids = list(set([token.device_id for token in tokens]))
            
            # ⭐ ВАЖЛИВО: body має містити ТІЛЬКИ конкретний будинок
            body = f"{outage.city}, {outage.street}, {house}\n{time_info}"
            
            # Відправляємо push
            result = firebase_service.send_push_to_multiple(
                tokens=fcm_tokens,
                title=title,
                body=body,
                data={
                    "type": outage_type,
                    "category": outage_type,
                    "city": outage.city,
                    "street": outage.street,
                    "house_number": house,
                    "start_time": outage.start_time.isoformat(),
                    "end_time": outage.end_time.isoformat()
                }
            )
            
            # Видаляємо невалідні токени
            if 'invalid_tokens' in result and result['invalid_tokens']:
                for invalid_token in result['invalid_tokens']:
                    token_to_delete = db.query(DeviceToken).filter(
                        DeviceToken.fcm_token == invalid_token
                    ).first()
                    if token_to_delete:
                        db.delete(token_to_delete)
                db.commit()
            
            # Зберігаємо в історію для КОЖНОГО будинку окремо
            if result['success'] > 0 or len(active_device_ids) > 0:
                sent_to_any = True
                all_device_ids.extend(active_device_ids)
                
                # ⭐ ЗБЕРІГАЄМО В ІСТОРІЮ для цього будинку
                crud_notifications.create_notification(
                    db=db,
                    notification_type="address",
                    category=outage_type,
                    title=title,
                    body=body,  # body вже містить правильний будинок
                    addresses=[{
                        "city": outage.city,
                        "street": outage.street,
                        "house_number": house
                    }],
                    device_ids=active_device_ids
                )
                logger.info(f"✅ Push відправлено: {result['success']} пристроїв для будинку {house}")
            else:
                logger.info(f"ℹ️ Немає користувачів для будинку {house}")
        
        # ФІКСУЄМО ЩО PUSH ВІДПРАВЛЕНО (дедуплікація)
        if sent_to_any:
            outage.notification_sent_at = current_time
            db.commit()
            logger.info(f"✅ Позначено {outage_type} {outage_id} як оповіщене")
        
    except Exception as e:
        logger.error(f"Помилка при відправці пушу для {outage_type} {outage_id}: {e}")
        db.rollback()
    finally:
        db.close()


def schedule_outage_notification(outage, outage_type: str):
    """
    Створює динамічний job для відправки пушу за 10 хвилин до відключення
    
    Args:
        outage: EmergencyOutage або PlannedOutage object
        outage_type: "emergency" або "planned"
    """
    current_time = datetime.now(KYIV_TZ).replace(tzinfo=None)
    notification_time = outage.start_time - timedelta(minutes=10)
    
    # Відправляємо ТІЛЬКИ якщо час ще не минув
    if notification_time <= current_time:
        logger.info(f"⚡ Час вже минув - відправка ОДРАЗУ для {outage_type} {outage.id}")
        send_outage_notification(outage.id, outage_type)
        return
    
    job_id = f"{outage_type}_{outage.id}"
    
    try:
        scheduler.add_job(
            send_outage_notification,
            'date',
            run_date=notification_time,
            args=[outage.id, outage_type],
            id=job_id,
            replace_existing=True
        )
        logger.info(f"✅ Заплановано пуш для {outage_type} {outage.id} на {notification_time.strftime('%d.%m %H:%M')}")
    except Exception as e:
        logger.error(f"Помилка при плануванні job для {outage_type} {outage.id}: {e}")


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
            
            logger.info(f"📤 Відправка аварійного пушу: {outage.city}, {outage.street}")
            
            # ОПТИМІЗОВАНО: один запит для всіх будинків
            houses_list = [h.strip() for h in outage.house_numbers.split(',')]
            user_addresses = db.query(UserAddress).filter(
                UserAddress.city == outage.city,
                UserAddress.street == outage.street,
                UserAddress.house_number.in_(houses_list)
            ).all()
            
            # Групуємо адреси по будинкам
            houses_to_addresses = {}
            for addr in user_addresses:
                if addr.house_number not in houses_to_addresses:
                    houses_to_addresses[addr.house_number] = []
                houses_to_addresses[addr.house_number].append(addr)
            
            sent_successfully = False
            for house in houses_list:
                addresses = houses_to_addresses.get(house, [])
                if not addresses:
                    logger.info(f"ℹ️ Немає користувачів для {outage.city}, {outage.street}, {house}")
                    continue
                
                # Збираємо токени
                fcm_tokens = []
                active_device_ids = []
                for addr in addresses:
                    device_tokens = db.query(DeviceToken).filter(DeviceToken.user_address_id == addr.id).all()
                    for dt in device_tokens:
                        if dt.fcm_token not in fcm_tokens:
                            fcm_tokens.append(dt.fcm_token)
                            active_device_ids.append(dt.device_id)
                
                if not fcm_tokens:
                    logger.info(f"ℹ️ Немає токенів для {outage.city}, {outage.street}, {house}")
                    continue
                
                # Формуємо body для конкретного будинку
                body = f"{outage.city}, {outage.street}, {house}\n{time_info}"
                
                result = firebase_service.send_multicast_notification(
                    fcm_tokens=fcm_tokens,
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
                
                # Видаляємо невалідні токени
                if 'invalid_tokens' in result and result['invalid_tokens']:
                    for invalid_token in result['invalid_tokens']:
                        token_to_delete = db.query(DeviceToken).filter(
                            DeviceToken.fcm_token == invalid_token
                        ).first()
                        if token_to_delete:
                            db.delete(token_to_delete)
                    db.commit()
                
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
                        device_ids=active_device_ids
                    )
                    logger.info(f"✅ Аварійний push: {result['success']} пристроїв для {outage.city}, {outage.street}, {house}")
            
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
            
            logger.info(f"📤 Відправка планового пушу: {outage.city}, {outage.street}")
            
            # ОПТИМІЗОВАНО: один запит для всіх будинків
            houses_list = [h.strip() for h in outage.house_numbers.split(',')]
            user_addresses = db.query(UserAddress).filter(
                UserAddress.city == outage.city,
                UserAddress.street == outage.street,
                UserAddress.house_number.in_(houses_list)
            ).all()
            
            # Групуємо адреси по будинкам
            houses_to_addresses = {}
            for addr in user_addresses:
                if addr.house_number not in houses_to_addresses:
                    houses_to_addresses[addr.house_number] = []
                houses_to_addresses[addr.house_number].append(addr)
            
            sent_successfully = False
            for house in houses_list:
                addresses = houses_to_addresses.get(house, [])
                if not addresses:
                    logger.info(f"ℹ️ Немає користувачів для {outage.city}, {outage.street}, {house}")
                    continue
                
                # Збираємо токени
                fcm_tokens = []
                active_device_ids = []
                for addr in addresses:
                    device_tokens = db.query(DeviceToken).filter(DeviceToken.user_address_id == addr.id).all()
                    for dt in device_tokens:
                        if dt.fcm_token not in fcm_tokens:
                            fcm_tokens.append(dt.fcm_token)
                            active_device_ids.append(dt.device_id)
                
                if not fcm_tokens:
                    logger.info(f"ℹ️ Немає токенів для {outage.city}, {outage.street}, {house}")
                    continue
                
                # Формуємо body для конкретного будинку
                body = f"{outage.city}, {outage.street}, {house}\n{time_info}"
                
                result = firebase_service.send_multicast_notification(
                    fcm_tokens=fcm_tokens,
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
                
                # Видаляємо невалідні токени
                if 'invalid_tokens' in result and result['invalid_tokens']:
                    for invalid_token in result['invalid_tokens']:
                        token_to_delete = db.query(DeviceToken).filter(
                            DeviceToken.fcm_token == invalid_token
                        ).first()
                        if token_to_delete:
                            db.delete(token_to_delete)
                    db.commit()
                
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
                        device_ids=active_device_ids
                    )
                    logger.info(f"✅ Плановий push: {result['success']} пристроїв для {outage.city}, {outage.street}, {house}")
            
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
            # Парсимо JSON якщо це string
            parsed_data = json.loads(schedule.parsed_data) if isinstance(schedule.parsed_data, str) else schedule.parsed_data
            
            # parsed_data має структуру: {"6.1": [[12, 16]], "6.2": [[12, 16]], ...}
            # Перебираємо всі черги і їхні інтервали
            for queue, intervals in parsed_data.items():
                if not intervals:
                    continue
                
                # Для кожного інтервалу перевіряємо чи потрібно відправити сповіщення
                for interval in intervals:
                    if len(interval) != 2:
                        continue
                    
                    start_hour, end_hour = interval
                    
                    # Створюємо datetime для початку відключення (в київському часі)
                    outage_time = current_time.replace(hour=start_hour, minute=0, second=0, microsecond=0)
                    
                    # Якщо цей час в межах 10 хвилин АБО відключення вже почалося (але не більше години тому)
                    time_diff = (current_time - outage_time).total_seconds() / 60  # різниця в хвилинах
                    should_notify = (current_time < outage_time <= target_time) or (0 <= time_diff <= 60)
                    
                    if should_notify:
                        logger.info(f"⚡ Перевірка черги {queue} для відключення {start_hour:02d}:00-{end_hour:02d}:00")
                        
                        # ПЕРЕВІРКА: чи вже відправляли для цієї дати/години/черги
                        already_sent = db.query(QueueNotification).filter(
                            QueueNotification.date == today,
                            QueueNotification.hour == start_hour,
                            QueueNotification.queue == queue
                        ).first()
                        
                        if already_sent:
                            logger.debug(f"ℹ️ Push для черги {queue} о {start_hour:02d}:00 вже відправлено раніше")
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
                            body = f"Почалося о {start_hour:02d}:00 згідно графіку"
                        else:
                            minutes_until = int((outage_time - current_time).total_seconds() / 60)
                            title = f"⚡ Відключення черги {queue} за {minutes_until} хв"
                            body = f"Згідно графіку, о {start_hour:02d}:00 буде відключено чергу {queue}"
                        
                        result = firebase_service.send_push_to_multiple(
                            fcm_tokens=fcm_tokens,
                            title=title,
                            body=body,
                            data={
                                "type": "queue_outage",
                                "category": "scheduled",
                                "queue": queue,
                                "hour": str(start_hour)
                            }
                        )
                        
                        if result['success'] > 0:
                            # ФІКСУЄМО ЩО PUSH ВІДПРАВЛЕНО
                            queue_notif = QueueNotification(
                                date=today,
                                hour=start_hour,
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
            data={
                "type": "schedule_update",
                "category": "general"
            }
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


def cleanup_inactive_devices():
    """
    Видаляє неактивні токени та адреси (щодня о 4:30)
    
    Логіка:
    1. Видаляє device_tokens які не оновлювались більше 90 днів
    2. Видаляє user_addresses для device_id які не мають активного токену
    """
    from app.models import DeviceToken, UserAddress
    from datetime import datetime, timedelta
    
    db: Session = SessionLocal()
    try:
        # Поріг неактивності - 90 днів
        inactive_threshold = datetime.now() - timedelta(days=90)
        
        logger.info("🧹 Початок очищення неактивних пристроїв...")
        
        # 1. Знаходимо і видаляємо старі токени (не оновлювались 90+ днів)
        old_tokens = db.query(DeviceToken).filter(
            DeviceToken.updated_at < inactive_threshold
        ).all()
        
        old_token_device_ids = [token.device_id for token in old_tokens]
        
        if old_tokens:
            logger.info(f"📱 Знайдено {len(old_tokens)} неактивних токенів (не оновлювались >90 днів)")
            for token in old_tokens:
                logger.info(f"  🗑️ Видаляємо токен: {token.device_id} (платформа: {token.platform}, останнє оновлення: {token.updated_at})")
                db.delete(token)
        
        # 2. Знаходимо device_id в user_addresses які не мають токену
        orphaned_addresses = db.query(UserAddress).outerjoin(
            DeviceToken, UserAddress.device_id == DeviceToken.device_id
        ).filter(
            DeviceToken.device_id == None  # Немає відповідного токену
        ).all()
        
        if orphaned_addresses:
            # Групуємо по device_id для статистики
            orphaned_device_ids = list(set([addr.device_id for addr in orphaned_addresses]))
            logger.info(f"🏠 Знайдено {len(orphaned_addresses)} адрес без активного токену ({len(orphaned_device_ids)} пристроїв)")
            
            for addr in orphaned_addresses:
                logger.info(f"  🗑️ Видаляємо адресу: {addr.city}, {addr.street}, {addr.house_number} (device: {addr.device_id})")
                db.delete(addr)
        
        # Виконуємо commit один раз для всіх змін
        db.commit()
        
        total_deleted_tokens = len(old_tokens)
        total_deleted_addresses = len(orphaned_addresses)
        
        if total_deleted_tokens > 0 or total_deleted_addresses > 0:
            logger.info(f"✅ Очищення завершено: видалено {total_deleted_tokens} токенів та {total_deleted_addresses} адрес")
        else:
            logger.info("✅ Очищення завершено: неактивних пристроїв не знайдено")
        
    except Exception as e:
        logger.error(f"❌ Помилка при очищенні неактивних пристроїв: {e}")
        logger.exception("Детальна інформація про помилку:")
        db.rollback()
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
    from app import crud_schedules, crud_notifications
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
    
    print(f"🔵 [SCHEDULER] start_scheduler ВИКЛИКАНО", flush=True)
    logger.info("🔵 [SCHEDULER] start_scheduler ВИКЛИКАНО")
    
    # ⭐ ЗАВАНТАЖУЄМО ХЕШІ З БД при старті
    logger.info("📥 Завантаження хешів відправлених оголошень з БД...")
    load_sent_hashes_from_db()
    
    # Не виконуємо одразу при старті - дозволяємо uvicorn швидко стартувати
    # Перше оновлення відбудеться через 10 секунд після запуску
    from datetime import datetime, timedelta
    start_time = datetime.now() + timedelta(seconds=10)
    
    check_interval = settings.CHECK_INTERVAL_MINUTES
    
    print(f"🚀 [SCHEDULER] Запуск scheduler з інтервалом {check_interval} хвилин", flush=True)
    logger.info(f"🚀 Запуск scheduler з інтервалом {check_interval} хвилин")
    
    # ⭐ Графіки - перший запуск через 10с, потім з заданим інтервалом
    try:
        print(f"🔵 [SCHEDULER] Додаємо job 'schedules' з інтервалом {check_interval} хв, перший запуск: {start_time}", flush=True)
        scheduler.add_job(update_schedules, 'interval', minutes=check_interval, id='schedules', next_run_time=start_time)
        print(f"✅ [SCHEDULER] Job 'schedules' успішно створено", flush=True)
        logger.info(f"✅ Job 'schedules' створено (інтервал: {check_interval} хв)")
    except Exception as e:
        print(f"❌ [SCHEDULER] Помилка створення job 'schedules': {e}", flush=True)
        logger.error(f"❌ Помилка створення job 'schedules': {e}")
        logger.exception("Детальна інформація:")
    
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
    
    # ⭐ ДИНАМІЧНІ JOBS створюються автоматично:
    #    - При парсингу графіків (schedule_queue_notifications)
    #    - При додаванні аварійних відключень (schedule_outage_notification)
    #    - При додаванні планових відключень (schedule_outage_notification)
    
    # ⭐ Перевірка чи є графік на завтра - щодня о 23:00
    scheduler.add_job(check_tomorrow_schedule_and_notify, 'cron', hour=23, minute=0, id='check_tomorrow')
    
    # Очищення старих відключень - раз на добу о 2:00
    scheduler.add_job(cleanup_old_outages, 'cron', hour=2, minute=0, id='cleanup_outages')
    
    # Очищення старих повідомлень - щодня о 3:00
    scheduler.add_job(cleanup_old_notifications_job, 'cron', hour=3, minute=0, id='cleanup_notifications')
    
    # Очищення неактивних пристроїв та адрес - щодня о 4:30
    scheduler.add_job(cleanup_inactive_devices, 'cron', hour=4, minute=30, id='cleanup_devices')
    
    # ⭐ Очищення старих хешів оголошень - щодня о 5:00
    scheduler.add_job(cleanup_old_sent_hashes, 'cron', hour=5, minute=0, id='cleanup_hashes')
    
    print(f"🔵 [SCHEDULER] Викликаємо scheduler.start()", flush=True)
    scheduler.start()
    print(f"✅ [SCHEDULER] scheduler.start() завершено успішно", flush=True)
    
    # Виводимо список всіх jobs
    jobs = scheduler.get_jobs()
    print(f"📋 [SCHEDULER] Всього jobs: {len(jobs)}", flush=True)
    for job in jobs:
        print(f"  - {job.id}: {job.next_run_time}", flush=True)
    
    logger.info("=" * 60)
    logger.info("✅ Планувальник запущено:")
    logger.info(f"  📅 Графіки: кожні {check_interval} хвилин (+ динамічні jobs для черг)")
    logger.info("  🖼️ Перевірка зображень: при старті та щодня о 4:00")
    logger.info(f"  ⚠️ Аварійні відключення: кожні {check_interval} хвилин (+ динамічні jobs)")
    logger.info(f"  📢 Оголошення з сайту: кожні {check_interval} хвилин")
    logger.info("  📋 Планові відключення: щодня о 9:00 (+ динамічні jobs)")
    logger.info("  🔔 Сповіщення: ДИНАМІЧНІ за 10 хв до кожного відключення")
    logger.info("  🌙 Перевірка графіка на завтра: щодня о 23:00")
    logger.info("  🧹 Очищення відключень: щодня о 2:00")
    logger.info("  🧹 Очищення повідомлень: щодня о 3:00")
    logger.info("  🧹 Очищення неактивних пристроїв: щодня о 4:30")
    logger.info("  🧹 Очищення хешів оголошень: щодня о 5:00")
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
# Build version: 1769416182
# Mon Jan 26 10:35:56 EET 2026
