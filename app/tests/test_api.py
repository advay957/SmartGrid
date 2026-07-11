import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import datetime

from app.main import app
from app.core.database import Base, get_db
# Import all models to ensure they are registered with Base metadata
from app.models.meter import Meter
from app.models.grid_metric import Telemetry, GridMetric

# Use StaticPool to maintain a single connection for the in-memory SQLite DB
SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Override database dependency in FastAPI
def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db

@pytest.fixture(scope="module", autouse=True)
def setup_database():
    # Create all tables in the shared connection database
    Base.metadata.create_all(bind=engine)
    
    db = TestingSessionLocal()
    # Provision a mock meter for telemetry tests
    mock_meter = Meter(
        id=999,
        name="Test Meter A",
        type="consumer",
        max_capacity_kw=100.0,
        status="online",
        location="Zone Test"
    )
    db.add(mock_meter)
    db.commit()
    db.close()
    
    yield
    # Drop tables after tests finish
    Base.metadata.drop_all(bind=engine)

client = TestClient(app)

def test_read_meters():
    """Test retrieving meters list."""
    response = client.get("/api/telemetry/meters")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert data[0]["name"] == "Test Meter A"
    assert data[0]["type"] == "consumer"

def test_create_meter():
    """Test creating a new smart meter."""
    payload = {
        "name": "Substation Solar Panel Test",
        "type": "generator",
        "max_capacity_kw": 250.0,
        "status": "online",
        "location": "East Zone"
    }
    response = client.post("/api/telemetry/meters", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["id"] is not None
    assert data["name"] == payload["name"]
    assert data["max_capacity_kw"] == 250.0

def test_record_telemetry():
    """Test submitting manual telemetry for a meter."""
    payload = {
        "meter_id": 999,
        "active_power_kw": 45.5,
        "reactive_power_kvar": 12.1,
        "voltage_v": 231.2,
        "frequency_hz": 49.98
    }
    response = client.post("/api/telemetry/record", json=payload)
    assert response.status_code == 201
    data = response.json()
    assert data["meter_id"] == 999
    assert data["active_power_kw"] == 45.5
    assert data["voltage_v"] == 231.2

def test_record_telemetry_invalid_meter():
    """Test telemetry submission fails for non-existent meter."""
    payload = {
        "meter_id": 12345,
        "active_power_kw": 10.0,
        "reactive_power_kvar": 2.0,
        "voltage_v": 230.0,
        "frequency_hz": 50.0
    }
    response = client.post("/api/telemetry/record", json=payload)
    assert response.status_code == 404
    assert response.json()["detail"] == "Meter not found"

def test_grid_control_api():
    """Test updating and fetching simulation controls."""
    # Fetch controls
    res = client.get("/api/grid/control")
    assert res.status_code == 200
    controls = res.json()
    assert "load_multiplier" in controls
    
    # Update controls
    payload = {
        "load_multiplier": 1.4,
        "solar_multiplier": 0.8,
        "grid_fault_active": True
    }
    res_post = client.post("/api/grid/control", json=payload)
    assert res_post.status_code == 200
    updated = res_post.json()["controls"]
    assert updated["load_multiplier"] == 1.4
    assert updated["solar_multiplier"] == 0.8
    assert updated["grid_fault_active"] is True

def test_battery_control_and_status():
    """Test battery mode override API."""
    payload = {
        "mode": "charge",
        "target_power_kw": 125.0
    }
    response = client.post("/api/battery/control", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "charge"
    assert data["max_power_kw"] == 250.0
    
    # Fetch battery status
    res_status = client.get("/api/battery/status")
    assert res_status.status_code == 200
    assert res_status.json()["mode"] == "charge"

def test_forecast_api():
    """Test fetching time-series forecast."""
    response = client.get("/api/forecast?horizon=12")
    assert response.status_code == 200
    data = response.json()
    assert "horizon_hours" in data
    assert data["horizon_hours"] == 12
    assert len(data["forecasts"]) == 12
    assert "predicted_demand_kw" in data["forecasts"][0]
    assert "predicted_generation_kw" in data["forecasts"][0]
