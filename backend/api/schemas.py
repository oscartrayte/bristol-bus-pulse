"""Pydantic schemas for API validation."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class Position(BaseModel):
    """Geographic position."""
    latitude: float
    longitude: float


class LiveVehicle(BaseModel):
    """Live vehicle data."""
    vehicle_id: str
    route_id: str
    trip_id: str
    operator_code: str
    position: Position
    heading: Optional[float] = None
    delay_seconds: Optional[int] = None
    next_stop_id: Optional[str] = None
    occupancy_status: Optional[str] = None
    timestamp: datetime


class RouteStatistics(BaseModel):
    """Route performance statistics."""
    route_id: str
    operator_code: str
    active_vehicles: int
    average_delay: Optional[float] = None
    median_delay: Optional[float] = None
    min_delay: Optional[int] = None
    max_delay: Optional[int] = None
    on_time_percentage: float
    delayed_vehicles: int
    severely_delayed_vehicles: int
    trips_scheduled: int
    trips_completed: int
    window_start: datetime
    window_end: datetime


class StopDetail(BaseModel):
    """Bus stop detail information."""
    stop_id: str
    stop_code: Optional[str] = None
    stop_name: str
    position: Position
    routes_serving: int
    scheduled_arrivals: int
    actual_arrivals: int
    average_arrival_delay: Optional[float] = None
    median_arrival_delay: Optional[float] = None
    on_time_percentage: float
    reliability_score: float
    wheelchair_accessible: Optional[bool] = None


class NetworkStatus(BaseModel):
    """Network-wide status snapshot."""
    timestamp: datetime
    total_vehicles: int
    delayed_vehicles: int
    severely_delayed_vehicles: int
    affected_routes: int
    affected_stops: int
    average_delay: Optional[float] = None
    network_reliability_score: float
    worst_route: Optional[str] = None
    worst_stop: Optional[str] = None
    worst_corridor: Optional[str] = None


class HeatmapCell(BaseModel):
    """Single heatmap grid cell."""
    latitude: float
    longitude: float
    intensity: float = Field(ge=0, le=1)
    vehicle_count: int
    delayed_vehicles: int
    average_delay_seconds: float
    affected_routes: List[str]


class HeatmapData(BaseModel):
    """Disruption heatmap data."""
    timestamp: datetime
    grid: List[HeatmapCell]
    min_intensity: float
    max_intensity: float
    cell_size_meters: int
    vehicle_count: int
    cell_count: int


class Corridor(BaseModel):
    """Congestion corridor."""
    cell_count: int
    bounds: Dict[str, float]
    center: Position
    severity: float
    max_intensity: float
    vehicle_count: int
    affected_routes: List[str]


class ReplaySnapshot(BaseModel):
    """Network snapshot for replay."""
    timestamp: datetime
    vehicle_count: int
    delayed_vehicles: int
    severely_delayed_vehicles: int
    affected_routes: int
    average_delay: Optional[float] = None


class ReplayDetail(BaseModel):
    """Detailed replay data at specific time."""
    timestamp: datetime
    vehicles: List[LiveVehicle]
    routes: List[RouteStatistics]
    stops: List[StopDetail]


class WorstPerformer(BaseModel):
    """Worst performing route or stop."""
    id: str
    name: Optional[str] = None
    average_delay: Optional[float] = None
    on_time_percentage: Optional[float] = None
    affected_count: int
    severity: str  # minor, moderate, severe


class RankingResponse(BaseModel):
    """Route or stop ranking response."""
    timestamp: datetime
    window_minutes: int
    items: List[WorstPerformer]
    total_count: int


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    database: str
    timestamp: datetime


class FeedStatusResponse(BaseModel):
    """External feed status."""
    feed_name: str
    is_healthy: bool
    last_successful_update: Optional[datetime] = None
    last_attempted_update: Optional[datetime] = None
    error_message: Optional[str] = None
    update_frequency_seconds: int
    items_received: int
    items_processed: int


class StopArrival(BaseModel):
    """Stop arrival information."""
    trip_id: str
    route_id: str
    vehicle_id: Optional[str] = None
    scheduled_arrival: datetime
    predicted_arrival: Optional[datetime] = None
    delay_seconds: Optional[int] = None
    status: str  # SCHEDULED, SKIPPED, DELAYED


class StopArrivalsResponse(BaseModel):
    """List of upcoming arrivals at a stop."""
    stop_id: str
    stop_name: str
    timestamp: datetime
    next_arrivals: List[StopArrival] = Field(max_items=20)


class RouteDetailResponse(BaseModel):
    """Detailed route information."""
    route_id: str
    route_name: str
    operator_code: str
    timestamp: datetime
    active_vehicles: List[LiveVehicle]
    statistics: RouteStatistics
    worst_stop: Optional[StopDetail] = None


class NetworkOverviewResponse(BaseModel):
    """Network overview response."""
    timestamp: datetime
    status: NetworkStatus
    worst_routes: List[WorstPerformer]
    worst_stops: List[WorstPerformer]
    corridors: List[Corridor]
    heatmap: HeatmapData
