from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import asyncio
import os
import logging

# Set up logging format
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("smart-grid-main")

# Import database and models to ensure tables are generated
from app.core.database import Base, engine
from app.models.meter import Meter
from app.models.grid_metric import Telemetry, GridMetric

# Create database tables automatically
Base.metadata.create_all(bind=engine)

# Import routes and managers
from app.api import telemetry, grid, battery, forecast
from app.websocket.manager import manager
from app.workers.tasks import simulation_loop

app = FastAPI(
    title="Smart Grid Enterprise API",
    description="Enterprise API and Simulator for Smart Grid demand forecasting and battery dispatch optimization.",
    version="1.0.0"
)

# Enable CORS for local UI communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(telemetry.router)
app.include_router(grid.router)
app.include_router(battery.router)
app.include_router(forecast.router)

# WebSocket connection endpoint for real-time telemetry updates
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Keep connection open, wait for client messages if any
        while True:
            data = await websocket.receive_text()
            # Respond or ignore client messages as it is mostly a downstream broadcast
            await websocket.send_json({"type": "ping", "status": "alive"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)

# Start background simulator loop on FastAPI startup
@app.on_event("startup")
async def startup_event():
    # Make sure static UI directory exists
    os.makedirs("app/static", exist_ok=True)
    
    # Launch simulation loop in the background of the event loop
    asyncio.create_task(simulation_loop())
    logger.info("Application startup: background simulator thread spawned.")

# Serve static dashboard assets
# Important: Mount at the root AFTER api routes are registered to avoid matching collisions
app.mount("/", StaticFiles(directory="app/static", html=True), name="static")
