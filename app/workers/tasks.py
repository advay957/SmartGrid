import asyncio
import datetime
import random
import numpy as np
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.core.config import settings
from app.models.meter import Meter
from app.models.grid_metric import Telemetry
from app.services.grid_metrics import calculate_current_metrics
from app.services.battery_dispatch import battery_system
from app.websocket.manager import manager
import logging

logger = logging.getLogger("smart-grid-simulator")

# Global simulation control parameters (can be adjusted via API)
simulation_controls = {
    "load_multiplier": 1.0,      # 1.0 = normal, 1.5 = high load spike, etc.
    "solar_multiplier": 1.0,     # 1.0 = sunny, 0.0 = complete cloud cover / night simulation
    "grid_fault_active": False,   # True = simulate voltage dip or frequency instability
}

def init_default_meters(db: Session):
    """Ensure a set of default smart meters exist in the database."""
    if db.query(Meter).count() > 0:
        return

    default_meters = [
        Meter(name="Residential Block A", type="consumer", max_capacity_kw=200.0, location="North Zone", status="online"),
        Meter(name="Residential Block B", type="consumer", max_capacity_kw=150.0, location="South Zone", status="online"),
        Meter(name="Industrial Facility C", type="consumer", max_capacity_kw=500.0, location="West Zone", status="online"),
        Meter(name="Substation Solar Farm", type="generator", max_capacity_kw=600.0, location="East Fields", status="online"),
        Meter(name="Wind Turbine Alpha", type="generator", max_capacity_kw=300.0, location="Ridge Line", status="online"),
        Meter(name="Smart Prosumer Home", type="prosumer", max_capacity_kw=15.0, location="North Zone", status="online"),
    ]
    
    db.add_all(default_meters)
    db.commit()
    logger.info("Initialized default smart meters in the database.")


def simulate_meter_telemetry(meter: Meter, hour: int, weekday: int) -> dict:
    """
    Generate simulated active and reactive power, voltage, and frequency.
    """
    global simulation_controls
    
    load_mult = simulation_controls["load_multiplier"]
    solar_mult = simulation_controls["solar_multiplier"]
    fault = simulation_controls["grid_fault_active"]
    
    # 1. Base voltage and frequency. Fault overrides cause stability degradation
    if fault:
        # Simulate voltage sag and frequency drop
        voltage = settings.GRID_NOMINAL_VOLTAGE * random.uniform(0.91, 0.94)
        frequency = settings.GRID_NOMINAL_FREQUENCY * random.uniform(0.990, 0.994)
    else:
        voltage = settings.GRID_NOMINAL_VOLTAGE * random.uniform(0.992, 1.008)
        frequency = settings.GRID_NOMINAL_FREQUENCY * random.uniform(0.999, 1.001)

    # 2. Simulate Active Power (kw)
    active_power = 0.0
    
    if meter.type == "consumer":
        if "Residential" in meter.name:
            # Peak residential usage at 8 AM and 7 PM
            peak1 = 0.7 * np.exp(-((hour - 8) ** 2) / 4.0)
            peak2 = 0.9 * np.exp(-((hour - 19) ** 2) / 6.0)
            baseload = 0.15
            load_factor = baseload + peak1 + peak2
            active_power = meter.max_capacity_kw * load_factor * random.uniform(0.85, 1.15) * load_mult
            
        elif "Industrial" in meter.name:
            # Steady high load during business hours (8 AM - 6 PM), low load at night
            if 8 <= hour <= 18:
                load_factor = random.uniform(0.65, 0.85)
            else:
                load_factor = random.uniform(0.15, 0.25)
            active_power = meter.max_capacity_kw * load_factor * load_mult
            
    elif meter.type == "generator":
        if "Solar" in meter.name:
            # Day-time solar curve, 0 at night
            if 6 <= hour <= 18:
                solar_factor = np.sin(np.pi * (hour - 6) / 12.0)
                # Apply cloud/efficiency multiplier
                active_power = -meter.max_capacity_kw * solar_factor * random.uniform(0.8, 1.0) * solar_mult
            else:
                active_power = 0.0
                
        elif "Wind" in meter.name:
            # Wind fluctuates based on a random walk
            # Average load factor is 40%
            active_power = -meter.max_capacity_kw * random.uniform(0.1, 0.8)
            
    elif meter.type == "prosumer":
        # Prosumer: Solar generation minus residential consumption
        # Consumer part:
        peak2 = 0.8 * np.exp(-((hour - 19) ** 2) / 6.0)
        baseload = 0.2
        demand = meter.max_capacity_kw * (baseload + peak2) * random.uniform(0.9, 1.1) * load_mult
        
        # Generator part:
        generation = 0.0
        if 6 <= hour <= 18:
            solar_factor = np.sin(np.pi * (hour - 6) / 12.0)
            generation = meter.max_capacity_kw * 1.5 * solar_factor * random.uniform(0.8, 1.0) * solar_mult
            
        # Net active power (+ is import, - is export)
        active_power = demand - generation
        
    # 3. Simulate Reactive Power (kvar)
    # Typically 10-30% of active power (lagging for consumer, leading/adjustable for generator)
    reactive_power = abs(active_power) * random.uniform(0.05, 0.25)
    
    return {
        "active_power_kw": round(active_power, 2),
        "reactive_power_kvar": round(reactive_power, 2),
        "voltage_v": round(voltage, 2),
        "frequency_hz": round(frequency, 4)
    }


async def simulation_loop():
    """
    Infinite asyncio loop that simulates telemetry data every X seconds,
    runs battery dispatch optimization, calculates aggregated metrics,
    and broadcasts the live state to WebSocket clients.
    """
    await asyncio.sleep(2.0)  # Wait for startup configuration
    logger.info("Smart Grid Simulation Loop started.")
    
    db = SessionLocal()
    init_default_meters(db)
    db.close()
    
    while True:
        try:
            db = SessionLocal()
            
            # Fetch active meters
            meters = db.query(Meter).filter(Meter.status == "online").all()
            now = datetime.datetime.utcnow()
            hour = now.hour
            weekday = now.weekday()
            
            meter_updates = []
            
            # 1. Generate and save telemetry for each meter
            total_meter_demand = 0.0
            total_meter_solar = 0.0
            
            for meter in meters:
                tel_data = simulate_meter_telemetry(meter, hour, weekday)
                
                # Bookkeep totals for battery optimization input
                power = tel_data["active_power_kw"]
                if power > 0:
                    total_meter_demand += power
                else:
                    total_meter_solar += abs(power)
                
                # Write to database
                telemetry = Telemetry(
                    meter_id=meter.id,
                    timestamp=now,
                    active_power_kw=tel_data["active_power_kw"],
                    reactive_power_kvar=tel_data["reactive_power_kvar"],
                    voltage_v=tel_data["voltage_v"],
                    frequency_hz=tel_data["frequency_hz"]
                )
                db.add(telemetry)
                
                meter_updates.append({
                    "id": meter.id,
                    "name": meter.name,
                    "type": meter.type,
                    "location": meter.location,
                    "status": meter.status,
                    "telemetry": tel_data
                })
            
            db.commit()
            
            # 2. Update battery energy storage state
            # Run battery system update using settings interval (seconds)
            interval = settings.SIMULATION_INTERVAL_SECONDS
            battery_system.update(total_meter_demand, total_meter_solar, interval)
            
            # Update battery status charge variable dynamically in the object
            # (In auto mode, the battery charge kw matches what is actually dispatched)
            # In manual charge, it charges from the grid up to limit, etc.
            
            # Fetch actual charge rate to aggregate into grid calculations
            # Determine battery_charge_kw
            battery_charge_kw = 0.0
            price = battery_system.get_electricity_price(hour)
            time_step_hours = interval / 3600.0
            
            if battery_system.mode == "idle":
                battery_charge_kw = 0.0
            elif battery_system.mode == "charge":
                power = battery_system.target_power_kw if battery_system.target_power_kw is not None else battery_system.max_power_kw
                max_charge_limit = (battery_system.capacity_kwh - battery_system.soc_kwh) / (time_step_hours * battery_system.efficiency)
                battery_charge_kw = min(power, max_charge_limit)
            elif battery_system.mode == "discharge":
                power = battery_system.target_power_kw if battery_system.target_power_kw is not None else battery_system.max_power_kw
                max_discharge_limit = battery_system.soc_kwh * battery_system.efficiency / time_step_hours
                battery_charge_kw = -min(power, max_discharge_limit)
            elif battery_system.mode == "auto":
                # Matches the charge rate calculated in auto mode:
                excess_solar = total_meter_solar - total_meter_demand
                if excess_solar > 0:
                    max_charge_limit = (battery_system.capacity_kwh - battery_system.soc_kwh) / (time_step_hours * battery_system.efficiency)
                    battery_charge_kw = min(excess_solar, battery_system.max_power_kw, max_charge_limit)
                elif price == 0.35 and (total_meter_demand - total_meter_solar) > 50.0:
                    net_load = total_meter_demand - total_meter_solar
                    max_discharge_limit = battery_system.soc_kwh * battery_system.efficiency / time_step_hours
                    battery_charge_kw = -min(net_load, battery_system.max_power_kw, max_discharge_limit)
                elif price == 0.10 and battery_system.soc_percent < 90.0:
                    max_charge_limit = (battery_system.capacity_kwh - battery_system.soc_kwh) / (time_step_hours * battery_system.efficiency)
                    battery_charge_kw = min(battery_system.max_power_kw, max_charge_limit)
            
            battery_system.current_charge_kw = battery_charge_kw
            
            # 3. Calculate grid metrics and write to DB
            grid_metrics = calculate_current_metrics(
                db, 
                battery_soc_kwh=battery_system.soc_kwh, 
                battery_charge_kw=battery_charge_kw
            )
            
            # 4. Broadcast live state to all active WebSocket clients
            # Map battery status response payload
            battery_status = battery_system.get_status(total_meter_demand, total_meter_solar)
            battery_status["current_charge_kw"] = round(battery_charge_kw, 2)
            
            broadcast_payload = {
                "type": "grid_update",
                "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                "grid_metrics": {
                    "total_demand_kw": grid_metrics.total_demand_kw,
                    "total_generation_kw": grid_metrics.total_generation_kw,
                    "net_load_kw": grid_metrics.net_load_kw,
                    "average_voltage": grid_metrics.average_voltage,
                    "average_frequency": grid_metrics.average_frequency,
                    "grid_stability_score": grid_metrics.grid_stability_score,
                    "status": grid_metrics.status
                },
                "battery": battery_status,
                "meters": meter_updates,
                "controls": simulation_controls
            }
            
            # Broadcast asynchronously
            await manager.broadcast(broadcast_payload)
            
            # Clean up old database entries (keep only last 1000 telemetry & grid metric records to avoid ballooning file)
            # This is a very neat house-keeping tip
            total_telemetries = db.query(Telemetry).count()
            if total_telemetries > 2000:
                oldest_telemetries = db.query(Telemetry).order_by(Telemetry.timestamp).limit(500).all()
                for ot in oldest_telemetries:
                    db.delete(ot)
                db.commit()
                
            db.close()
            
        except Exception as e:
            logger.error(f"Error in simulation loop iteration: {e}", exc_info=True)
            if 'db' in locals():
                db.close()
                
        # Sleep for simulation interval
        await asyncio.sleep(settings.SIMULATION_INTERVAL_SECONDS)
