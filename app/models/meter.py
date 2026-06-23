from sqlalchemy import Column, Integer, String, Float
from sqlalchemy.orm import relationship
from app.core.database import Base

class Meter(Base):
    __tablename__ = "meters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    # "consumer" (uses electricity), "generator" (produces electricity, e.g., solar farm), "prosumer" (both, e.g., solar home)
    type = Column(String, nullable=False, default="consumer")
    max_capacity_kw = Column(Float, nullable=False, default=10.0)
    # "online", "offline", "maintenance"
    status = Column(String, nullable=False, default="online")
    location = Column(String, nullable=True)

    # Relationship to telemetry records
    telemetry = relationship("Telemetry", back_populates="meter", cascade="all, delete-orphan")
