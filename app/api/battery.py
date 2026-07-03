from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.grid_metric import GridMetric
from app.services.battery_dispatch import battery_system
from app.schemas.telemetry import BatteryStatusResponse, BatteryControlRequest

router = APIRouter(prefix="/api/battery", tags=["Battery Storage (BESS)"])

@router.get("/status", response_model=BatteryStatusResponse)
def get_battery_status(db: Session = Depends(get_db)):
    """Fetch current state of charge and optimization stats of BESS."""
    # Retrieve latest demand/solar to supply context metrics
    latest_metric = db.query(GridMetric).order_by(GridMetric.timestamp.desc()).first()
    
    demand = 0.0
    solar = 0.0
    if latest_metric:
        demand = latest_metric.total_demand_kw
        solar = latest_metric.total_generation_kw
        
    status = battery_system.get_status(demand, solar)
    return status

@router.post("/control", response_model=BatteryStatusResponse)
def control_battery(control: BatteryControlRequest, db: Session = Depends(get_db)):
    """Override the battery operating mode (auto, charge, discharge, idle)."""
    mode = control.mode.lower()
    if mode not in ["auto", "charge", "discharge", "idle"]:
        raise HTTPException(status_code=400, detail="Invalid operating mode. Choose: auto, charge, discharge, or idle")
        
    battery_system.mode = mode
    if control.target_power_kw is not None:
        # Cap manual override power at maximum system capacity
        battery_system.target_power_kw = min(control.target_power_kw, battery_system.max_power_kw)
    else:
        battery_system.target_power_kw = None
        
    # Get latest demand/solar
    latest_metric = db.query(GridMetric).order_by(GridMetric.timestamp.desc()).first()
    demand = 0.0
    solar = 0.0
    if latest_metric:
        demand = latest_metric.total_demand_kw
        solar = latest_metric.total_generation_kw
        
    return battery_system.get_status(demand, solar)
