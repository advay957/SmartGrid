from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional
from datetime import datetime

# --- Meter Schemas ---
class MeterBase(BaseModel):
    name: str = Field(..., example="Residential Block A")
    type: str = Field(..., example="consumer", description="consumer, generator, or prosumer")
    max_capacity_kw: float = Field(10.0, example=10.0)
    status: str = Field("online", example="online")
    location: Optional[str] = Field(None, example="Substation 3")

class MeterCreate(MeterBase):
    pass

class MeterResponse(MeterBase):
    id: int

    class Config:
        from_attributes = True
        orm_mode = True  # For backwards compatibility with Pydantic v1

# --- Telemetry Schemas ---
class TelemetryBase(BaseModel):
    active_power_kw: float = Field(..., example=4.5, description="Positive for demand, negative for generation")
    reactive_power_kvar: float = Field(0.0, example=1.2)
    voltage_v: float = Field(230.0, example=230.1)
    frequency_hz: float = Field(50.0, example=49.98)

class TelemetryCreate(TelemetryBase):
    meter_id: int

class TelemetryResponse(TelemetryBase):
    id: int
    meter_id: int
    timestamp: datetime

    class Config:
        from_attributes = True
        orm_mode = True

# --- Grid Metric Schemas ---
class GridMetricResponse(BaseModel):
    timestamp: datetime
    total_demand_kw: float
    total_generation_kw: float
    net_load_kw: float
    average_voltage: float
    average_frequency: float
    battery_soc_kwh: float
    battery_charge_kw: float
    grid_stability_score: float
    status: str

    class Config:
        from_attributes = True
        orm_mode = True

# --- Battery Schemas ---
class BatteryStatusResponse(BaseModel):
    soc_kwh: float
    soc_percent: float
    capacity_kwh: float
    max_power_kw: float
    current_charge_kw: float  # + charging, - discharging
    mode: str  # "auto", "charge", "discharge", "idle"
    grid_demand_kw: float
    solar_gen_kw: float
    net_load_kw: float
    money_saved_today: float
    carbon_offset_kg: float

class BatteryControlRequest(BaseModel):
    mode: str = Field(..., example="auto", description="auto, charge, discharge, or idle")
    target_power_kw: Optional[float] = Field(None, example=100.0, description="Override charge/discharge power (kW)")

# --- Forecasting Schemas ---
class ForecastDataPoint(BaseModel):
    timestamp: datetime
    predicted_demand_kw: float
    predicted_generation_kw: float

class ForecastResponse(BaseModel):
    generated_at: datetime
    horizon_hours: int
    forecasts: List[ForecastDataPoint]
