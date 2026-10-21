"""WaterWise Backend - Daire Yönetimi ve Listeleme (Apartments Router)."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.schemas import ApartmentListItem
from backend.app.services.consumption_service import get_apartments_list

router = APIRouter(prefix="/apartments", tags=["Daireler"])


@router.get(
    "",
    response_model=List[ApartmentListItem],
    summary="Kayıtlı Daire Listesi",
    description="Sistemdeki 28 dairenin listesini, küme bilgilerini ve normal tüketim aralıklarını döndürür.",
)
def list_apartments(db: Session = Depends(get_db)) -> List[ApartmentListItem]:
    return get_apartments_list(db)


@router.get(
    "/{apartment_id}",
    response_model=ApartmentListItem,
    summary="Tek Daire Bilgisi",
    description="Belirtilen dairenin profilini ve temel bilgilerini getirir.",
)
def get_apartment(
    apartment_id: str = Path(..., description="Daire kimliği (ör. APT_011)"),
    db: Session = Depends(get_db),
) -> ApartmentListItem:
    apts = get_apartments_list(db)
    for apt in apts:
        if apt.id == apartment_id:
            return apt
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"'{apartment_id}' dairesi bulunamadı.",
    )

