from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import datetime
from app.core.database import get_db
from app.services.forecasting import get_grid_forecast
from app.schemas.telemetry import ForecastResponse

router = APIRouter(prefix="/api/forecast", tags=["Machine Learning Forecasts"])

@router.get("", response_model=ForecastResponse)
def get_forecasting(horizon: int = 24, db: Session = Depends(get_db)):
    """
    Retrieve hourly demand and generation forecasts for the next X hours.
    Utilizes machine learning regressions over historical readings.
    """
    # Cap horizon to 48 hours max to prevent excessive computation
    horizon = min(horizon, 48)
    
    forecasts = get_grid_forecast(db, horizon)
    
    # Format forecast data points
    formatted_forecasts = []
    for f in forecasts:
        formatted_forecasts.append({
            "timestamp": f["timestamp"],
            "predicted_demand_kw": f["predicted_demand_kw"],
            "predicted_generation_kw": f["predicted_generation_kw"]
        })
        
    return {
        "generated_at": datetime.datetime.utcnow(),
        "horizon_hours": horizon,
        "forecasts": formatted_forecasts
    }
