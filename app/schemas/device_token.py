from pydantic import BaseModel
from datetime import datetime


class DeviceTokenCreate(BaseModel):
    device_id: str
    fcm_token: str
    platform: str


class DeviceTokenResponse(BaseModel):
    device_id: str
    fcm_token: str
    platform: str
    notifications_enabled: bool
    created_at: datetime
    updated_at: datetime | None

    class Config:
        from_attributes = True
