"""
REST API endpoints для ProСвітло backend (production-ready)
Видалено дубльовані та адмін-функції
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime

from app.database import get_db
from app import crud, schemas
from app.scheduler import get_scheduler_status

router = APIRouter()


@router.get("/status", response_model=schemas.StatusResponse)
async def api_status():
    """
    Перевірка статусу API
    """
    scheduler_status = get_scheduler_status()
    
    return schemas.StatusResponse(
        status="healthy",
        message=f"API працює. Scheduler: {'running' if scheduler_status['running'] else 'stopped'}",
        timestamp=datetime.now()
    )


@router.get("/scheduler/jobs")
async def get_scheduler_jobs():
    """
    Детальна інформація про scheduler jobs
    """
    scheduler_status = get_scheduler_status()
    return scheduler_status


# ===== ЗАЛИШЕНО ТІЛЬКИ ДЛЯ СУМІСНОСТІ З СТАРОЮ ВЕРСІЄЮ (deprecated) =====
# Ці endpoints будуть видалені в наступній версії


@router.get("/outages", deprecated=True)
async def get_all_outages_deprecated():
    """
    ⚠️ ЗАСТАРІЛИЙ: Використовуйте /api/v1/address-outages замість цього
    """
    raise HTTPException(
        status_code=410,
        detail="Цей endpoint застарілий. Використовуйте /api/v1/address-outages"
    )


@router.get("/outage", deprecated=True)
async def get_outage_by_address_deprecated():
    """
    ⚠️ ЗАСТАРІЛИЙ: Використовуйте /api/v1/address-outages замість цього
    """
    raise HTTPException(
        status_code=410,
        detail="Цей endpoint застарілий. Використовуйте /api/v1/address-outages"
    )


@router.get("/history", deprecated=True)
async def get_outage_history_deprecated():
    """
    ⚠️ ЗАСТАРІЛИЙ: Використовуйте /api/v1/address-outages замість цього
    """
    raise HTTPException(
        status_code=410,
        detail="Цей endpoint застарілий. Використовуйте /api/v1/address-outages"
    )


@router.get("/cities", deprecated=True)
async def get_cities_deprecated():
    """
    ⚠️ ЗАСТАРІЛИЙ: Використовуйте /api/v1/addresses/cities замість цього
    """
    raise HTTPException(
        status_code=410,
        detail="Цей endpoint застарілий. Використовуйте /api/v1/addresses/cities"
    )


@router.post("/register", deprecated=True)
async def register_user_deprecated():
    """
    ⚠️ ЗАСТАРІЛИЙ: Використовуйте /api/v1/tokens/register замість цього
    """
    raise HTTPException(
        status_code=410,
        detail="Цей endpoint застарілий. Використовуйте /api/v1/tokens/register"
    )
