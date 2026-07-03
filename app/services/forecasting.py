import datetime
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from app.models.grid_metric import GridMetric
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
import logging

logger = logging.getLogger("smart-grid-forecasting")

def generate_synthetic_forecast(start_time: datetime.datetime, hour_offset: int) -> tuple[float, float]:
    """
    Generate realistic synthetic demand and generation curves based on the hour of day.
    Demand has two peaks: morning (8 AM) and evening (7 PM).
    Generation (solar) has one peak at noon (12 PM) and is 0 during the night.
    """
    target_time = start_time + datetime.timedelta(hours=hour_offset)
    hour = target_time.hour
    
    # 1. Base demand (diurnal curve with morning and evening peaks)
    # Peak 1: 8 AM, Peak 2: 7 PM (19:00)
    base_demand = 300.0  # Base baseload (kW)
    morning_peak = 150.0 * np.exp(-((hour - 8) ** 2) / 6.0)
    evening_peak = 250.0 * np.exp(-((hour - 19) ** 2) / 8.0)
    
    # Add random noise
    np.random.seed(hour_offset + hour)
    noise_demand = np.random.normal(0, 15.0)
    predicted_demand = max(50.0, base_demand + morning_peak + evening_peak + noise_demand)
    
    # 2. Solar generation (peak at 12 PM, 0 before 6 AM and after 6 PM)
    if 6 <= hour <= 18:
        # Sine wave peak at noon
        solar_peak = 400.0  # Peak solar generation capacity
        predicted_gen = solar_peak * np.sin(np.pi * (hour - 6) / 12.0)
        noise_gen = np.random.normal(0, 10.0)
        predicted_gen = max(0.0, predicted_gen + noise_gen)
    else:
        predicted_gen = 0.0
        
    return round(predicted_demand, 2), round(predicted_gen, 2)


def get_grid_forecast(db: Session, horizon_hours: int = 24) -> list[dict]:
    """
    Predict grid demand and generation for the next horizon_hours.
    Tries to train a scikit-learn model if enough history is present,
    otherwise falls back to generating realistic synthetic curves.
    """
    now = datetime.datetime.utcnow()
    forecasts = []
    
    # Check if we have enough historical data in DB to train a simple model
    # We need at least 50 points of history for training a minimal model
    history_count = db.query(GridMetric).count()
    
    trained_model = False
    demand_model = None
    generation_model = None
    
    if history_count >= 50:
        try:
            # Load history
            history = db.query(GridMetric).order_by(GridMetric.timestamp).all()
            
            # Convert to pandas DataFrame
            data = [{
                "timestamp": h.timestamp,
                "hour": h.timestamp.hour,
                "dayofweek": h.timestamp.weekday(),
                "demand": h.total_demand_kw,
                "generation": h.total_generation_kw
            } for h in history]
            
            df = pd.DataFrame(data)
            
            # Prepare features (hour, dayofweek)
            X = df[["hour", "dayofweek"]]
            y_demand = df["demand"]
            y_gen = df["generation"]
            
            # Train model
            # Random Forest captures the non-linear solar curve and demand peak well
            demand_model = RandomForestRegressor(n_estimators=20, random_state=42)
            demand_model.fit(X, y_demand)
            
            generation_model = RandomForestRegressor(n_estimators=20, random_state=42)
            generation_model.fit(X, y_gen)
            
            trained_model = True
            logger.info("Successfully trained forecasting model using Random Forest Regressor")
        except Exception as e:
            logger.warning(f"Failed to train machine learning models: {e}. Falling back to seasonal model.")
            
    # Generate predictions
    for i in range(1, horizon_hours + 1):
        target_time = now + datetime.timedelta(hours=i)
        
        if trained_model and demand_model and generation_model:
            # Predict using trained models
            features = pd.DataFrame([{"hour": target_time.hour, "dayofweek": target_time.weekday()}])
            pred_demand = float(demand_model.predict(features)[0])
            pred_gen = float(generation_model.predict(features)[0])
            
            # Ensure no negative predictions and round
            pred_demand = round(max(10.0, pred_demand), 2)
            pred_gen = round(max(0.0, pred_gen), 2)
        else:
            # Use synthetic generator
            pred_demand, pred_gen = generate_synthetic_forecast(now, i)
            
        forecasts.append({
            "timestamp": target_time,
            "predicted_demand_kw": pred_demand,
            "predicted_generation_kw": pred_gen
        })
        
    return forecasts
