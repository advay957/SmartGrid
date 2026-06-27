from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.meter import Meter
from app.models.grid_metric import Telemetry
from app.schemas.telemetry import MeterCreate, MeterResponse, TelemetryCreate, TelemetryResponse

router = APIRouter(prefix="/api/telemetry", tags=["Telemetry & Meters"])

@router.post("/meters", response_model=MeterResponse, status_code=status.HTTP_201_CREATED)
def create_meter(meter_in: MeterCreate, db: Session = Depends(get_db)):
    """Create a new smart meter in the grid."""
    db_meter = Meter(
        name=meter_in.name,
        type=meter_in.type,
        max_capacity_kw=meter_in.max_capacity_kw,
        status=meter_in.status,
        location=meter_in.location
    )
    db.add(db_meter)
    db.commit()
    db.refresh(db_meter)
    return db_meter

@router.get("/meters", response_model=List[MeterResponse])
def read_meters(db: Session = Depends(get_db)):
    """Retrieve all smart meters in the grid."""
    return db.query(Meter).all()

@router.get("/meters/{meter_id}/history", response_model=List[TelemetryResponse])
def get_meter_history(meter_id: int, limit: int = 100, db: Session = Depends(get_db)):
    """Fetch the historical telemetry records for a specific meter."""
    meter = db.query(Meter).filter(Meter.id == meter_id).first()
    if not meter:
        raise HTTPException(status_code=404, detail="Meter not found")
        
    return (
        db.query(Telemetry)
        .filter(Telemetry.meter_id == meter_id)
        .order_by(Telemetry.timestamp.desc())
        .limit(limit)
        .all()
    )

@router.post("/record", response_model=TelemetryResponse, status_code=status.HTTP_201_CREATED)
def record_telemetry(telemetry_in: TelemetryCreate, db: Session = Depends(get_db)):
    """Post a manual telemetry reading for a smart meter."""
    meter = db.query(Meter).filter(Meter.id == telemetry_in.meter_id).first()
    if not meter:
        raise HTTPException(status_code=404, detail="Meter not found")
        
    db_telemetry = Telemetry(
        meter_id=telemetry_in.meter_id,
        active_power_kw=telemetry_in.active_power_kw,
        reactive_power_kvar=telemetry_in.reactive_power_kvar,
        voltage_v=telemetry_in.voltage_v,
        frequency_hz=telemetry_in.frequency_hz
    )
    db.add(db_telemetry)
    db.commit()
    db.refresh(db_telemetry)
    return db_telemetry
