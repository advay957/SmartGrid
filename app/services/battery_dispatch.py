import datetime
from typing import Optional
from app.core.config import settings
import logging

logger = logging.getLogger("smart-grid-battery")

class BatterySystem:
    def __init__(self):
        self.capacity_kwh: float = settings.BATTERY_CAPACITY_KWH
        self.max_power_kw: float = settings.BATTERY_MAX_POWER_KW
        self.soc_kwh: float = self.capacity_kwh * 0.5  # Start at 50% capacity
        self.efficiency: float = 0.90  # 90% charge/discharge efficiency
        self.mode: str = "auto"  # "auto", "charge", "discharge", "idle"
        self.target_power_kw: Optional[float] = None
        
        # Financial & Carbon tracking
        self.money_saved_today: float = 0.0
        self.carbon_offset_kg: float = 0.0
        
        # Historical charge tracking for arbitrage calculation
        self.average_charging_cost_per_kwh: float = 0.12  # Estimated default cost
        
    def get_electricity_price(self, hour: int) -> float:
        """
        Get peak, off-peak or standard energy pricing.
        - Peak ($0.35/kWh): 8 AM - 10 AM, 5 PM - 9 PM
        - Off-peak ($0.10/kWh): 10 PM - 6 AM
        - Standard ($0.18/kWh): All other times
        """
        if 8 <= hour < 10 or 17 <= hour < 21:
            return 0.35
        elif hour >= 22 or hour < 6:
            return 0.10
        else:
            return 0.18

    def update(self, demand_kw: float, solar_kw: float, time_step_seconds: float):
        """
        Update the battery state of charge (SoC) and calculate metrics based on the current mode and grid load.
        """
        now = datetime.datetime.utcnow()
        hour = now.hour
        price = self.get_electricity_price(hour)
        time_step_hours = time_step_seconds / 3600.0
        
        charge_rate = 0.0  # + is charging (acting as load), - is discharging (acting as generator)
        
        if self.mode == "idle":
            charge_rate = 0.0
            
        elif self.mode == "charge":
            # Manual charge at max power or target override
            power = self.target_power_kw if self.target_power_kw is not None else self.max_power_kw
            max_charge_limit = (self.capacity_kwh - self.soc_kwh) / (time_step_hours * self.efficiency)
            charge_rate = min(power, max_charge_limit)
            
        elif self.mode == "discharge":
            # Manual discharge at max power or target override
            power = self.target_power_kw if self.target_power_kw is not None else self.max_power_kw
            max_discharge_limit = self.soc_kwh * self.efficiency / time_step_hours
            charge_rate = -min(power, max_discharge_limit)
            
        elif self.mode == "auto":
            # 1. First Priority: Green Charging
            # If solar generation exceeds demand, store the excess solar
            excess_solar = solar_kw - demand_kw
            
            if excess_solar > 0:
                max_charge_limit = (self.capacity_kwh - self.soc_kwh) / (time_step_hours * self.efficiency)
                charge_rate = min(excess_solar, self.max_power_kw, max_charge_limit)
                # Charging with solar costs $0
                # Track that this portion of energy is green
                self.average_charging_cost_per_kwh = (
                    (self.average_charging_cost_per_kwh * self.soc_kwh) + (0.0 * charge_rate * time_step_hours)
                ) / (self.soc_kwh + charge_rate * time_step_hours + 1e-6)
                
            # 2. Second Priority: Load Shaving & Peak Arbitrage
            # If we are in peak price hours, and have positive net load, discharge to offset the grid
            elif price == 0.35 and (demand_kw - solar_kw) > 50.0:
                net_load = demand_kw - solar_kw
                max_discharge_limit = self.soc_kwh * self.efficiency / time_step_hours
                discharge_kw = min(net_load, self.max_power_kw, max_discharge_limit)
                charge_rate = -discharge_kw
                
            # 3. Third Priority: Off-Peak Charging
            # Charge during off-peak hours (cheap grid energy) to prepare for peak periods
            elif price == 0.10 and self.soc_percent < 90.0:
                max_charge_limit = (self.capacity_kwh - self.soc_kwh) / (time_step_hours * self.efficiency)
                charge_rate = min(self.max_power_kw, max_charge_limit)
                # Track charging cost
                self.average_charging_cost_per_kwh = (
                    (self.average_charging_cost_per_kwh * self.soc_kwh) + (price * charge_rate * time_step_hours)
                ) / (self.soc_kwh + charge_rate * time_step_hours + 1e-6)
                
            else:
                charge_rate = 0.0

        # Update State of Charge (SoC) based on charge rate
        if charge_rate > 0:
            # Charging: draw energy, apply efficiency loss
            actual_increase = charge_rate * time_step_hours * self.efficiency
            self.soc_kwh = min(self.capacity_kwh, self.soc_kwh + actual_increase)
            
            # If manual grid charging, subtract cost from savings
            if self.mode == "charge":
                self.money_saved_today -= charge_rate * time_step_hours * price
        elif charge_rate < 0:
            # Discharging: supply energy, draw more due to efficiency loss
            discharge_needed = abs(charge_rate) * time_step_hours / self.efficiency
            self.soc_kwh = max(0.0, self.soc_kwh - discharge_needed)
            
            # Calculate savings: offset peak prices
            # Saved = Energy Discharged * (Current Price - Cost of Charging)
            arbitrage_saving = abs(charge_rate) * time_step_hours * (price - self.average_charging_cost_per_kwh)
            self.money_saved_today += max(0.0, arbitrage_saving)
            
            # Calculate carbon offsets: offset standard coal/gas grid generation (approx 0.4kg CO2/kWh)
            # Higher offset if we discharge solar energy
            offset_factor = 0.6 if self.average_charging_cost_per_kwh < 0.05 else 0.4
            self.carbon_offset_kg += abs(charge_rate) * time_step_hours * offset_factor

    @property
    def soc_percent(self) -> float:
        return (self.soc_kwh / self.capacity_kwh) * 100.0

    def get_status(self, demand: float, solar: float) -> dict:
        net_load = demand - solar + (self.target_power_kw if self.mode == "charge" else 0.0) # approx
        return {
            "soc_kwh": round(self.soc_kwh, 2),
            "soc_percent": round(self.soc_percent, 1),
            "capacity_kwh": self.capacity_kwh,
            "max_power_kw": self.max_power_kw,
            "current_charge_kw": round(self.target_power_kw if self.mode in ["charge", "discharge"] and self.target_power_kw is not None else 0.0, 2), # dynamically overwritten by simulator
            "mode": self.mode,
            "grid_demand_kw": round(demand, 2),
            "solar_gen_kw": round(solar, 2),
            "net_load_kw": round(net_load, 2),
            "money_saved_today": round(self.money_saved_today, 2),
            "carbon_offset_kg": round(self.carbon_offset_kg, 2)
        }

# Global singleton representing the battery storage
battery_system = BatterySystem()
