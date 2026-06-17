"""SQLAlchemy models for Bristol Bus Pulse."""
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean, JSON,
    ForeignKey, Index, UniqueConstraint, Text
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from geoalchemy2 import Geometry

Base = declarative_base()


class Vehicle(Base):
    """Live bus vehicle positions and status."""
    __tablename__ = "vehicles"
    
    id = Column(Integer, primary_key=True)
    vehicle_id = Column(String(50), unique=True, nullable=False, index=True)
    operator_code = Column(String(20), nullable=False, index=True)
    route_id = Column(String(50), nullable=False, index=True)
    trip_id = Column(String(100), nullable=False, index=True)
    
    # Position
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    position = Column(Geometry('POINT', srid=4326), nullable=False, index=True)
    heading = Column(Float, nullable=True)  # Degrees, 0-359
    
    # Status
    delay_seconds = Column(Integer, nullable=True)
    next_stop_id = Column(String(50), nullable=True)
    occupancy_status = Column(String(50), nullable=True)  # EMPTY, MANY_SEATS_AVAILABLE, etc
    
    # Metadata
    timestamp = Column(DateTime, nullable=False, index=True, default=datetime.utcnow)
    update_timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_position', 'position'),
        Index('idx_timestamp', 'timestamp'),
        Index('idx_route_delay', 'route_id', 'delay_seconds'),
    )


class Stop(Base):
    """Bus stop information."""
    __tablename__ = "stops"
    
    id = Column(Integer, primary_key=True)
    stop_id = Column(String(50), unique=True, nullable=False, index=True)
    stop_code = Column(String(20), nullable=True)
    stop_name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    
    # Position
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    position = Column(Geometry('POINT', srid=4326), nullable=False, index=True)
    
    # Metadata
    wheelchair_accessible = Column(Boolean, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_position', 'position'),
    )


class TripUpdate(Base):
    """GTFS-RT Trip Updates for delay tracking."""
    __tablename__ = "trip_updates"
    
    id = Column(Integer, primary_key=True)
    trip_id = Column(String(100), nullable=False, index=True)
    vehicle_id = Column(String(50), nullable=False, index=True)
    route_id = Column(String(50), nullable=False, index=True)
    
    # Current status
    current_stop_sequence = Column(Integer, nullable=True)
    current_status = Column(String(50), nullable=False)  # SCHEDULED, SKIPPED, NO_DATA
    delay_seconds = Column(Integer, nullable=True)
    
    # Stop-level updates
    stop_time_updates = Column(JSON, nullable=True)  # Array of {stop_id, arrival, departure}
    
    # Metadata
    timestamp = Column(DateTime, nullable=False, index=True, default=datetime.utcnow)
    update_timestamp = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_timestamp', 'timestamp'),
        Index('idx_trip_route', 'trip_id', 'route_id'),
    )


class RouteStatistic(Base):
    """Aggregated route performance statistics."""
    __tablename__ = "route_statistics"
    
    id = Column(Integer, primary_key=True)
    route_id = Column(String(50), nullable=False, index=True)
    operator_code = Column(String(20), nullable=False)
    
    # Active status
    active_vehicles = Column(Integer, default=0)
    total_vehicles = Column(Integer, default=0)
    
    # Delay metrics (in seconds)
    average_delay = Column(Float, nullable=True)
    median_delay = Column(Float, nullable=True)
    min_delay = Column(Integer, nullable=True)
    max_delay = Column(Integer, nullable=True)
    
    # Reliability
    on_time_percentage = Column(Float, default=0.0)
    delayed_vehicles = Column(Integer, default=0)
    severely_delayed_vehicles = Column(Integer, default=0)  # 10+ min
    
    # Service
    trips_scheduled = Column(Integer, default=0)
    trips_completed = Column(Integer, default=0)
    
    # Metadata
    window_start = Column(DateTime, nullable=False, index=True)
    window_end = Column(DateTime, nullable=False, index=True)
    calculated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_route_window', 'route_id', 'window_start', 'window_end'),
    )


class StopStatistic(Base):
    """Aggregated stop performance statistics."""
    __tablename__ = "stop_statistics"
    
    id = Column(Integer, primary_key=True)
    stop_id = Column(String(50), nullable=False, index=True)
    
    # Service
    routes_serving = Column(Integer, default=0)
    scheduled_arrivals = Column(Integer, default=0)
    actual_arrivals = Column(Integer, default=0)
    missed_arrivals = Column(Integer, default=0)
    
    # Delay metrics (in seconds)
    average_arrival_delay = Column(Float, nullable=True)
    median_arrival_delay = Column(Float, nullable=True)
    
    # Reliability
    reliability_score = Column(Float, default=0.0)  # 0-100
    on_time_percentage = Column(Float, default=0.0)
    
    # Metadata
    window_start = Column(DateTime, nullable=False, index=True)
    window_end = Column(DateTime, nullable=False, index=True)
    calculated_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_stop_window', 'stop_id', 'window_start', 'window_end'),
    )


class NetworkSnapshot(Base):
    """Historical network snapshots for replay functionality."""
    __tablename__ = "network_snapshots"
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, unique=True, index=True)
    
    # Aggregate metrics
    total_vehicles = Column(Integer, default=0)
    delayed_vehicles = Column(Integer, default=0)
    severely_delayed_vehicles = Column(Integer, default=0)
    affected_routes = Column(Integer, default=0)
    affected_stops = Column(Integer, default=0)
    
    # Network metrics
    average_delay = Column(Float, nullable=True)
    network_reliability_score = Column(Float, default=0.0)
    
    # Snapshot data
    vehicle_positions = Column(JSON, nullable=True)  # Compressed vehicle data
    stop_metrics = Column(JSON, nullable=True)  # Compressed stop metrics
    route_metrics = Column(JSON, nullable=True)  # Compressed route metrics
    heatmap_data = Column(JSON, nullable=True)  # Heatmap grid data
    
    # Metadata
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_timestamp', 'timestamp'),
    )


class FeedStatus(Base):
    """Status of external data feeds."""
    __tablename__ = "feed_status"
    
    id = Column(Integer, primary_key=True)
    feed_name = Column(String(100), unique=True, nullable=False, index=True)
    
    # Status
    is_healthy = Column(Boolean, default=False)
    last_successful_update = Column(DateTime, nullable=True)
    last_attempted_update = Column(DateTime, nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Metrics
    update_frequency_seconds = Column(Integer, default=0)
    items_received = Column(Integer, default=0)
    items_processed = Column(Integer, default=0)
    
    # Metadata
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_feed_name', 'feed_name'),
    )


class HistoricalVehiclePosition(Base):
    """Historical vehicle positions for analytics and replay."""
    __tablename__ = "historical_vehicle_positions"
    
    id = Column(Integer, primary_key=True)
    vehicle_id = Column(String(50), nullable=False, index=True)
    operator_code = Column(String(20), nullable=False)
    route_id = Column(String(50), nullable=False, index=True)
    trip_id = Column(String(100), nullable=False)
    
    # Position
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    position = Column(Geometry('POINT', srid=4326), nullable=False, index=True)
    heading = Column(Float, nullable=True)
    
    # Status
    delay_seconds = Column(Integer, nullable=True)
    
    # Metadata
    timestamp = Column(DateTime, nullable=False, index=True)
    
    __table_args__ = (
        Index('idx_timestamp_vehicle', 'timestamp', 'vehicle_id'),
        Index('idx_timestamp_route', 'timestamp', 'route_id'),
    )
