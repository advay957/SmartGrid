from sqlalchemy import Column, Integer, Float, DateTime, ForeignKey, String
from sqlalchemy.orm import relationship
import datetime
from app.core.database import Base

class Telemetry(Base):
    __tablename__ = "telemetry"

    id = Column(Integer, primary_key=True, index=True)
    meter_id = Column(Integer, ForeignKey("meters.id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    
    # Active power: positive is consumption (load), negative is generation (source)
    active_power_kw = Column(Float, nullable=False, default=0.0)
    reactive_power_kvar = Column(Float, nullable=False, default=0.0)
    voltage_v = Column(Float, nullable=False, default=230.0)
    frequency_hz = Column(Float, nullable=False, default=50.0)

    meter = relationship("Meter", back_populates="telemetry")


class GridMetric(Base):
    __tablename__ = "grid_metrics"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    
    total_demand_kw = Column(Float, nullable=False, default=0.0)
    total_generation_kw = Column(Float, nullable=False, default=0.0)
    net_load_kw = Column(Float, nullable=False, default=0.0)
    
    average_voltage = Column(Float, nullable=False, default=230.0)
    average_frequency = Column(Float, nullable=False, default=50.0)
    
    battery_soc_kwh = Column(Float, nullable=False, default=0.0)
    battery_charge_kw = Column(Float, nullable=False, default=0.0) # Positive = charging, negative = discharging
    
    grid_stability_score = Column(Float, nullable=False, default=100.0) # 0-100 score representing grid health
    status = Column(String, nullable=False, default="stable") # "stable", "warning", "critical"
