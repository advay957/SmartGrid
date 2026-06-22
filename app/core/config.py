import os

class Settings:
    PROJECT_NAME: str = "Smart Grid Enterprise API"
    
    # Database configuration
    # Default to a local SQLite database for easy zero-config execution
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./smart_grid.db")
    
    # Celery & Redis configuration
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CELERY_BROKER_URL: str = os.getenv("CELERY_BROKER_URL", REDIS_URL)
    CELERY_RESULT_BACKEND: str = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)
    
    # Simulation settings
    SIMULATION_INTERVAL_SECONDS: int = int(os.getenv("SIMULATION_INTERVAL_SECONDS", "5"))
    
    # Battery Energy Storage System (BESS) settings
    # Default to 1 MWh capacity, 250 kW peak power
    BATTERY_CAPACITY_KWH: float = float(os.getenv("BATTERY_CAPACITY_KWH", "1000.0"))
    BATTERY_MAX_POWER_KW: float = float(os.getenv("BATTERY_MAX_POWER_KW", "250.0"))
    
    # Grid Nominal Values
    GRID_NOMINAL_VOLTAGE: float = 230.0
    GRID_NOMINAL_FREQUENCY: float = 50.0

settings = Settings()
