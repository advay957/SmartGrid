from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.models.meter import Meter
from app.models.grid_metric import GridMetric, Telemetry
from app.core.config import settings
import datetime

def calculate_current_metrics(db: Session, battery_soc_kwh: float, battery_charge_kw: float) -> GridMetric:
    """
    Query the latest telemetry for all active meters, aggregate results,
    calculate grid stability score, detect alerts, and save to DB.
    """
    # 1. Get all online meters
    online_meters = db.query(Meter).filter(Meter.status == "online").all()
    
    if not online_meters:
        # Fallback metrics when no meters are active
        metric = GridMetric(
            timestamp=datetime.datetime.utcnow(),
            total_demand_kw=0.0,
            total_generation_kw=0.0,
            net_load_kw=0.0,
            average_voltage=settings.GRID_NOMINAL_VOLTAGE,
            average_frequency=settings.GRID_NOMINAL_FREQUENCY,
            battery_soc_kwh=battery_soc_kwh,
            battery_charge_kw=battery_charge_kw,
            grid_stability_score=100.0,
            status="stable"
        )
        db.add(metric)
        db.commit()
        db.refresh(metric)
        return metric

    total_demand = 0.0
    total_generation = 0.0
    voltages = []
    frequencies = []
    
    # 2. Get the latest telemetry for each online meter from the last 2 minutes
    cutoff_time = datetime.datetime.utcnow() - datetime.timedelta(minutes=2)
    
    for meter in online_meters:
        latest_telemetry = (
            db.query(Telemetry)
            .filter(Telemetry.meter_id == meter.id)
            .filter(Telemetry.timestamp >= cutoff_time)
            .order_by(desc(Telemetry.timestamp))
            .first()
        )
        
        if latest_telemetry:
            power = latest_telemetry.active_power_kw
            if power > 0:
                total_demand += power
            else:
                total_generation += abs(power)
                
            voltages.append(latest_telemetry.voltage_v)
            frequencies.append(latest_telemetry.frequency_hz)
        else:
            # If no telemetry, assume default state based on meter type and capacity
            # Consumers consume 20% of capacity, generators produce 20%
            if meter.type == "consumer":
                total_demand += meter.max_capacity_kw * 0.2
            elif meter.type == "generator":
                total_generation += meter.max_capacity_kw * 0.2
            elif meter.type == "prosumer":
                total_demand += meter.max_capacity_kw * 0.1
            voltages.append(settings.GRID_NOMINAL_VOLTAGE)
            frequencies.append(settings.GRID_NOMINAL_FREQUENCY)

    avg_voltage = sum(voltages) / len(voltages) if voltages else settings.GRID_NOMINAL_VOLTAGE
    avg_frequency = sum(frequencies) / len(frequencies) if frequencies else settings.GRID_NOMINAL_FREQUENCY
    
    # Net load is demand - generation (from meters) + battery charging (acting as demand)
    # If battery_charge_kw is positive (charging), it increases net load. If negative (discharging), it reduces net load.
    net_load = total_demand - total_generation + battery_charge_kw
    
    # 3. Calculate grid stability score (out of 100)
    # Base voltage deviation (nominal 230V)
    v_dev = abs(avg_voltage - settings.GRID_NOMINAL_VOLTAGE) / settings.GRID_NOMINAL_VOLTAGE
    # Base frequency deviation (nominal 50Hz)
    f_dev = abs(avg_frequency - settings.GRID_NOMINAL_FREQUENCY) / settings.GRID_NOMINAL_FREQUENCY
    
    # Penalize deviations
    v_penalty = v_dev * 500  # 2% dev = 10 points penalty
    f_penalty = f_dev * 2000 # 0.1Hz dev = 0.002 * 2000 = 4 points penalty
    
    # Grid loading penalty (high net load relative to online capacity)
    total_capacity = sum(m.max_capacity_kw for m in online_meters) or 1.0
    load_ratio = net_load / total_capacity
    load_penalty = max(0.0, (load_ratio - 0.75) * 40) # penalize load above 75% capacity
    
    stability_score = max(0.0, min(100.0, 100.0 - v_penalty - f_penalty - load_penalty))
    
    # 4. Status determination & alerts
    status = "stable"
    if stability_score < 60.0 or avg_frequency < 49.7 or avg_frequency > 50.3 or avg_voltage < 215.0 or avg_voltage > 245.0:
        status = "critical"
    elif stability_score < 80.0 or avg_frequency < 49.9 or avg_frequency > 50.1 or avg_voltage < 225.0 or avg_voltage > 235.0:
        status = "warning"
        
    metric = GridMetric(
        timestamp=datetime.datetime.utcnow(),
        total_demand_kw=round(total_demand, 2),
        total_generation_kw=round(total_generation, 2),
        net_load_kw=round(net_load, 2),
        average_voltage=round(avg_voltage, 2),
        average_frequency=round(avg_frequency, 4),
        battery_soc_kwh=round(battery_soc_kwh, 2),
        battery_charge_kw=round(battery_charge_kw, 2),
        grid_stability_score=round(stability_score, 1),
        status=status
    )
    
    db.add(metric)
    db.commit()
    db.refresh(metric)
    return metric

def get_recent_metrics(db: Session, limit: int = 100):
    return (
        db.query(GridMetric)
        .order_by(desc(GridMetric.timestamp))
        .limit(limit)
        .all()
    )[::-1] # return in chronological order
