from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.core.database import get_db
from app.models.grid_metric import GridMetric
from app.services.grid_metrics import get_recent_metrics
from app.schemas.telemetry import GridMetricResponse
from app.workers.tasks import simulation_controls

router = APIRouter(prefix="/api/grid", tags=["Grid Management"])

@router.get("/status", response_model=GridMetricResponse)
def get_grid_status(db: Session = Depends(get_db)):
    """Fetch the latest status and stability metrics of the grid."""
    latest = db.query(GridMetric).order_by(GridMetric.timestamp.desc()).first()
    if not latest:
        raise HTTPException(status_code=404, detail="No grid metrics recorded yet")
    return latest

@router.get("/history", response_model=List[GridMetricResponse])
def get_grid_history(limit: int = 50, db: Session = Depends(get_db)):
    """Fetch recent historical grid metrics for charting."""
    return get_recent_metrics(db, limit)

@router.post("/control")
def update_simulation_control(control_data: dict):
    """
    Control simulation parameters:
    - load_multiplier: float (e.g. 1.5 for load spike)
    - solar_multiplier: float (e.g. 0.2 for overcast)
    - grid_fault_active: bool (triggers frequency/voltage drop)
    """
    global simulation_controls
    
    if "load_multiplier" in control_data:
        val = float(control_data["load_multiplier"])
        if 0.0 <= val <= 5.0:
            simulation_controls["load_multiplier"] = val
            
    if "solar_multiplier" in control_data:
        val = float(control_data["solar_multiplier"])
        if 0.0 <= val <= 2.0:
            simulation_controls["solar_multiplier"] = val
            
    if "grid_fault_active" in control_data:
        simulation_controls["grid_fault_active"] = bool(control_data["grid_fault_active"])
        
    return {
        "status": "success",
        "controls": simulation_controls
    }

@router.get("/control")
def get_simulation_control():
    """Retrieve current simulation control values."""
    return simulation_controls
