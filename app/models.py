"""
SQLAlchemy моделі для бази даних
"""

from sqlalchemy import Column, Integer, String, DateTime, Date, Boolean, Text, Index
from sqlalchemy.sql import func
from app.database import Base


class Outage(Base):
    """
    Модель для зберігання інформації про відключення електроенергії
    """
    __tablename__ = "outages"
    
    id = Column(Integer, primary_key=True, index=True)
    city = Column(String, nullable=False, index=True)
    street = Column(String, nullable=False, index=True)
    house_number = Column(String, nullable=False)
    queue = Column(String, nullable=True)  # Черга відключення (1, 2, 3 тощо)
    zone = Column(String, nullable=True)   # Зона або група
    schedule_time = Column(String, nullable=True)  # Час відключення (наприклад, "08:00 - 12:00")
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    source_url = Column(String, default="https://hoe.com.ua/page/pogodinni-vidkljuchennja")
    
    # Складений індекс для швидкого пошуку за адресою
    __table_args__ = (
        Index('idx_address', 'city', 'street', 'house_number'),
    )
    
    def __repr__(self):
        return f"<Outage(city={self.city}, street={self.street}, house={self.house_number}, queue={self.queue})>"


class AddressQueue(Base):
    """
    Статична таблиця для зберігання відповідності адрес до черг відключення.
    Ця таблиця оновлюється рідко (тільки при зміні на сайті постачальника).
    """
    __tablename__ = "address_queues"
    
    id = Column(Integer, primary_key=True, index=True)
    city = Column(String, nullable=False, index=True)
    street = Column(String, nullable=False, index=True)
    house_number = Column(String, nullable=False)
    queue = Column(String, nullable=False)  # Черга відключення (1, 2, 3 тощо)
    zone = Column(String, nullable=True)    # Додаткова зона/група якщо є
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Унікальний індекс для адрес (одна адреса = одна черга)
    __table_args__ = (
        Index('idx_address_queue_unique', 'city', 'street', 'house_number', unique=True),
    )
    
    def __repr__(self):
        return f"<AddressQueue(city={self.city}, street={self.street}, house={self.house_number}, queue={self.queue})>"


class User(Base):
    """
    Модель для зберігання інформації про користувачів та їх Firebase токени
    """
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    firebase_token = Column(String, unique=True, nullable=False, index=True)
    city = Column(String, nullable=False)
    street = Column(String, nullable=False)
    house_number = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Індекс для пошуку користувачів за адресою
    __table_args__ = (
        Index('idx_user_address', 'city', 'street', 'house_number'),
    )
    
    def __repr__(self):
        return f"<User(id={self.id}, city={self.city}, street={self.street}, house={self.house_number})>"


class Schedule(Base):
    """
    Модель для зберігання графіків відключень
    """
    __tablename__ = "schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)  # Дата графіка
    image_url = Column(String, nullable=False)  # URL зображення графіка
    recognized_text = Column(Text, nullable=True)  # Текстова версія графіка
    parsed_data = Column(Text, nullable=True)  # JSON з розпарсеними даними (черги + інтервали)
    content_hash = Column(String, nullable=True)  # MD5 хеш для перевірки змін
    version = Column(String, default="1.0.0")  # Версія для синхронізації
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    is_active = Column(Boolean, default=True)  # Чи актуальний графік
    
    __table_args__ = (
        Index('idx_schedule_date', 'date'),
    )
    
    def __repr__(self):
        return f"<Schedule(date={self.date}, version={self.version})>"


class EmergencyOutage(Base):
    """
    Модель для зберігання аварійних відключень
    """
    __tablename__ = "emergency_outages"
    
    id = Column(Integer, primary_key=True, index=True)
    rem_id = Column(Integer, nullable=False, index=True)  # ID району електромереж
    rem_name = Column(String, nullable=False)  # Назва РЕМ
    city = Column(String, nullable=False, index=True)  # Місто/громада
    street = Column(String, nullable=False, index=True)  # Вулиця
    house_numbers = Column(Text, nullable=False)  # Список номерів будинків (через кому)
    work_type = Column(String, nullable=False)  # Вид робіт
    created_date = Column(DateTime(timezone=True), nullable=False)  # Дата створення запису
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)  # Час початку
    end_time = Column(DateTime(timezone=True), nullable=False, index=True)  # Час відновлення
    is_active = Column(Boolean, default=True, index=True)  # Чи активне відключення
    notification_sent_at = Column(DateTime(timezone=True), nullable=True, index=True)  # Коли відправлено пуш
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index('idx_emergency_active', 'is_active', 'start_time', 'end_time'),
        Index('idx_emergency_location', 'city', 'street'),
    )
    
    def __repr__(self):
        return f"<EmergencyOutage(city={self.city}, street={self.street}, start={self.start_time})>"


class PlannedOutage(Base):
    """
    Модель для зберігання планових відключень
    """
    __tablename__ = "planned_outages"
    
    id = Column(Integer, primary_key=True, index=True)
    rem_id = Column(Integer, nullable=False, index=True)  # ID району електромереж
    rem_name = Column(String, nullable=False)  # Назва РЕМ
    city = Column(String, nullable=False, index=True)  # Місто/громада
    street = Column(String, nullable=False, index=True)  # Вулиця
    house_numbers = Column(Text, nullable=False)  # Список номерів будинків (через кому)
    work_type = Column(String, nullable=False)  # Вид робіт
    created_date = Column(DateTime(timezone=True), nullable=False)  # Дата створення запису
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)  # Час початку
    end_time = Column(DateTime(timezone=True), nullable=False, index=True)  # Час відновлення
    is_active = Column(Boolean, default=True, index=True)  # Чи активне відключення
    notification_sent_at = Column(DateTime(timezone=True), nullable=True, index=True)  # Коли відправлено пуш
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    __table_args__ = (
        Index('idx_planned_active', 'is_active', 'start_time', 'end_time'),
        Index('idx_planned_location', 'city', 'street'),
    )
    
    def __repr__(self):
        return f"<PlannedOutage(city={self.city}, street={self.street}, start={self.start_time})>"


class DeviceToken(Base):
    """
    Модель для зберігання FCM токенів пристроїв
    Кожен пристрій може мати лише один активний токен
    """
    __tablename__ = "device_tokens"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, unique=True, nullable=False, index=True)  # Унікальний ID пристрою
    fcm_token = Column(String, nullable=False, index=True)  # Firebase Cloud Messaging токен
    notifications_enabled = Column(Boolean, default=True, nullable=False)  # Чи увімкнені пуші
    platform = Column(String, nullable=False)  # android або ios
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<DeviceToken(device_id={self.device_id}, enabled={self.notifications_enabled})>"


class Notification(Base):
    """
    Модель для зберігання історії повідомлень
    Повідомлення зберігаються 5 днів
    """
    __tablename__ = "notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    notification_type = Column(String, nullable=False, index=True)  # 'all' або 'address'
    category = Column(String, nullable=False, default='general', index=True)  # 'general', 'outage', 'restored', 'scheduled', 'emergency'
    title = Column(String, nullable=False)
    body = Column(Text, nullable=False)
    data = Column(Text, nullable=True)  # JSON з додатковими даними
    addresses = Column(Text, nullable=True)  # JSON масив адрес для type='address'
    device_ids = Column(Text, nullable=True)  # JSON масив device_id користувачів, яким відправлено
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    __table_args__ = (
        Index('idx_notification_created', 'created_at'),
        Index('idx_notification_type', 'notification_type', 'created_at'),
    )
    
    def __repr__(self):
        return f"<Notification(type={self.notification_type}, title={self.title})>"


class UserAddress(Base):
    """
    Модель для зберігання збережених адрес користувачів
    Один пристрій може мати кілька збережених адрес
    """
    __tablename__ = "user_addresses"
    
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, nullable=False, index=True)  # Зв'язок з DeviceToken
    city = Column(String, nullable=False)
    street = Column(String, nullable=False)
    house_number = Column(String, nullable=False)
    queue = Column(String, nullable=True, index=True)  # Черга відключення (1.1, 2.1, тощо)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index('idx_user_address_device', 'device_id'),
        Index('idx_user_address_location', 'city', 'street', 'house_number'),
    )
    
    def __repr__(self):
        return f"<UserAddress(device={self.device_id}, city={self.city}, street={self.street}, house={self.house_number})>"


class QueueNotification(Base):
    """
    Модель для відстеження відправлених push-повідомлень по чергах
    Гарантує що кожна черга отримає повідомлення лише один раз в годину
    """
    __tablename__ = "queue_notifications"
    
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)  # Дата графіка
    hour = Column(Integer, nullable=False, index=True)  # Година відключення (0-23)
    queue = Column(String, nullable=False, index=True)  # Черга (наприклад "1.1", "2.2")
    notification_sent_at = Column(DateTime(timezone=True), server_default=func.now())  # Коли відправлено
    
    __table_args__ = (
        Index('idx_queue_notification_unique', 'date', 'hour', 'queue', unique=True),
    )
    
    def __repr__(self):
        return f"<QueueNotification(date={self.date}, hour={self.hour}, queue={self.queue})>"


class AnnouncementOutage(Base):
    """
    Модель для зберігання додаткових проміжків відключення з оголошень
    Використовується коли в оголошеннях вказано "підчергу X.Y з HH:MM до HH:MM"
    """
    __tablename__ = "announcement_outages"
    
    id = Column(Integer, primary_key=True, index=True)
    date = Column(Date, nullable=False, index=True)  # Дата відключення
    queue = Column(String, nullable=False, index=True)  # Черга (наприклад "6.2")
    start_hour = Column(Integer, nullable=False)  # Година початку (0-23)
    end_hour = Column(Integer, nullable=False)  # Година завершення (0-23)
    announcement_text = Column(Text, nullable=True)  # Текст оголошення (для контексту)
    is_active = Column(Boolean, default=True, index=True)  # Чи актуальне відключення
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    notification_sent_at = Column(DateTime(timezone=True), nullable=True)  # Коли відправлено пуш
    
    __table_args__ = (
        Index('idx_announcement_outage_date_queue', 'date', 'queue', 'start_hour'),
        Index('idx_announcement_outage_active', 'is_active', 'date'),
    )
    
    def __repr__(self):
        return f"<AnnouncementOutage(date={self.date}, queue={self.queue}, {self.start_hour}:00-{self.end_hour}:00)>"

    
    def __repr__(self):
        return f"<QueueNotification(date={self.date}, hour={self.hour}, queue={self.queue})>"


class NoScheduleNotificationState(Base):
    """
    Модель для відстеження стану повідомлень про відсутність графіка
    Тримає один запис з налаштуваннями
    """
    __tablename__ = "no_schedule_notification_state"
    
    id = Column(Integer, primary_key=True, index=True)
    enabled = Column(Boolean, default=True, nullable=False)  # Чи увімкнені повідомлення
    consecutive_days_without_schedule = Column(Integer, default=0, nullable=False)  # Лічильник днів без графіка
    last_check_date = Column(Date, nullable=True)  # Остання дата перевірки
    last_notification_date = Column(Date, nullable=True)  # Коли останній раз відправляли повідомлення
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<NoScheduleNotificationState(enabled={self.enabled}, days_without={self.consecutive_days_without_schedule})>"


class SentAnnouncementHash(Base):
    """
    Модель для зберігання хешів відправлених оголошень
    Запобігає дублюванню повідомлень після перезавантаження сервера
    """
    __tablename__ = "sent_announcement_hashes"
    
    id = Column(Integer, primary_key=True, index=True)
    content_hash = Column(String, unique=True, nullable=False, index=True)  # MD5 хеш контенту оголошення
    announcement_type = Column(String, nullable=False, default='general')  # 'general', 'schedule', 'paragraph'
    title = Column(String, nullable=True)  # Заголовок для довідки
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    __table_args__ = (
        Index('idx_sent_hash_created', 'created_at'),
    )
    
    def __repr__(self):
        return f"<SentAnnouncementHash(hash={self.content_hash[:8]}..., type={self.announcement_type})>"


