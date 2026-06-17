"""API route handlers."""
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc
from geoalchemy2 import WKTElement

from database import get_db_session
from models import Vehicle, Stop, RouteStatistic, StopStatistic, TripUpdate
from api.schemas import (
    LiveVehicle, Position, RouteStatistics, StopDetail, NetworkStatus,
    HeatmapData, ReplaySnapshot, WorstPerformer, StopArrival, StopArrivalsResponse,
    RouteDetailResponse, NetworkOverviewResponse
)
from ingestion.gtfs_rt_parser import GTFSRealtimeParser
from processing.delay_calculator import DelayCalculator
from processing.heatmap_generator import HeatmapGenerator
from processing.snapshot_manager import SnapshotManager

logger = logging.getLogger(__name__)


def create_routes(
    gtfs_rt_parser: GTFSRealtimeParser,
    delay_calculator: DelayCalculator,
    heatmap_generator: HeatmapGenerator,
    snapshot_manager: SnapshotManager,
    connection_manager,
) -> APIRouter:
    """Create API routes."""
    
    router = APIRouter(prefix="/api", tags=["bristol-bus-pulse"])
    
    # Live vehicles
    @router.get("/vehicles/live", response_model=List[LiveVehicle])
    async def get_live_vehicles(
        route_id: Optional[str] = None,
        session: AsyncSession = Depends(get_db_session),
    ):
        """Get live vehicle positions."""
        
        # Get vehicles from last 5 minutes
        cutoff = datetime.utcnow() - timedelta(minutes=5)
        
        query = select(Vehicle).where(Vehicle.timestamp >= cutoff)
        
        if route_id:
            query = query.where(Vehicle.route_id == route_id)
        
        result = await session.execute(query)
        vehicles = result.scalars().all()
        
        return [
            LiveVehicle(
                vehicle_id=v.vehicle_id,
                route_id=v.route_id,
                trip_id=v.trip_id,
                operator_code=v.operator_code,
                position=Position(latitude=v.latitude, longitude=v.longitude),
                heading=v.heading,
                delay_seconds=v.delay_seconds,
                next_stop_id=v.next_stop_id,
                occupancy_status=v.occupancy_status,
                timestamp=v.timestamp,
            )
            for v in vehicles
        ]
    
    # Routes ranking
    @router.get("/routes/ranked", response_model=List[WorstPerformer])
    async def get_ranked_routes(
        limit: int = Query(10, ge=1, le=50),
        minutes: int = Query(60, ge=5, le=1440),
        session: AsyncSession = Depends(get_db_session),
    ):
        """Get routes ranked by delay."""
        
        window_start = datetime.utcnow() - timedelta(minutes=minutes)
        window_end = datetime.utcnow()
        
        stmt = select(RouteStatistic).where(
            and_(
                RouteStatistic.window_start >= window_start,
                RouteStatistic.window_end <= window_end,
            )
        ).order_by(desc(RouteStatistic.average_delay)).limit(limit)
        
        result = await session.execute(stmt)
        routes = result.scalars().all()
        
        return [
            WorstPerformer(
                id=r.route_id,
                average_delay=r.average_delay,
                on_time_percentage=r.on_time_percentage,
                affected_count=r.delayed_vehicles,
                severity=delay_calculator.get_delay_severity(
                    int(r.average_delay) if r.average_delay else None
                ),
            )
            for r in routes
        ]
    
    # Route detail
    @router.get("/routes/{route_id}", response_model=RouteDetailResponse)
    async def get_route_detail(
        route_id: str,
        session: AsyncSession = Depends(get_db_session),
    ):
        """Get detailed route information."""
        
        cutoff = datetime.utcnow() - timedelta(minutes=5)
        
        # Get vehicles
        stmt = select(Vehicle).where(
            and_(
                Vehicle.route_id == route_id,
                Vehicle.timestamp >= cutoff,
            )
        )
        result = await session.execute(stmt)
        vehicles = result.scalars().all()
        
        # Get statistics
        stmt = select(RouteStatistic).where(
            RouteStatistic.route_id == route_id
        ).order_by(desc(RouteStatistic.calculated_at)).limit(1)
        result = await session.execute(stmt)
        stats = result.scalar_one_or_none()
        
        if not stats:
            raise HTTPException(status_code=404, detail="Route not found")
        
        return RouteDetailResponse(
            route_id=route_id,
            route_name=route_id,  # Would populate from GTFS
            operator_code=vehicles[0].operator_code if vehicles else "UNKNOWN",
            timestamp=datetime.utcnow(),
            active_vehicles=[
                LiveVehicle(
                    vehicle_id=v.vehicle_id,
                    route_id=v.route_id,
                    trip_id=v.trip_id,
                    operator_code=v.operator_code,
                    position=Position(latitude=v.latitude, longitude=v.longitude),
                    heading=v.heading,
                    delay_seconds=v.delay_seconds,
                    next_stop_id=v.next_stop_id,
                    occupancy_status=v.occupancy_status,
                    timestamp=v.timestamp,
                )
                for v in vehicles
            ],
            statistics=RouteStatistics(
                route_id=stats.route_id,
                operator_code=stats.operator_code,
                active_vehicles=stats.active_vehicles,
                average_delay=stats.average_delay,
                median_delay=stats.median_delay,
                on_time_percentage=stats.on_time_percentage,
                delayed_vehicles=stats.delayed_vehicles,
                severely_delayed_vehicles=stats.severely_delayed_vehicles,
                trips_scheduled=stats.trips_scheduled,
                trips_completed=stats.trips_completed,
                window_start=stats.window_start,
                window_end=stats.window_end,
            ),
        )
    
    # Stops ranking
    @router.get("/stops/ranked", response_model=List[WorstPerformer])
    async def get_ranked_stops(
        limit: int = Query(10, ge=1, le=50),
        minutes: int = Query(60, ge=5, le=1440),
        session: AsyncSession = Depends(get_db_session),
    ):
        """Get stops ranked by delay."""
        
        window_start = datetime.utcnow() - timedelta(minutes=minutes)
        window_end = datetime.utcnow()
        
        stmt = select(StopStatistic).where(
            and_(
                StopStatistic.window_start >= window_start,
                StopStatistic.window_end <= window_end,
            )
        ).order_by(desc(StopStatistic.average_arrival_delay)).limit(limit)
        
        result = await session.execute(stmt)
        stops = result.scalars().all()
        
        return [
            WorstPerformer(
                id=s.stop_id,
                average_delay=s.average_arrival_delay,
                on_time_percentage=s.on_time_percentage,
                affected_count=s.scheduled_arrivals,
                severity=delay_calculator.get_delay_severity(
                    int(s.average_arrival_delay) if s.average_arrival_delay else None
                ),
            )
            for s in stops
        ]
    
    # Stop detail
    @router.get("/stops/{stop_id}", response_model=StopDetail)
    async def get_stop_detail(
        stop_id: str,
        session: AsyncSession = Depends(get_db_session),
    ):
        """Get detailed stop information."""
        
        # Get stop
        stmt = select(Stop).where(Stop.stop_id == stop_id)
        result = await session.execute(stmt)
        stop = result.scalar_one_or_none()
        
        if not stop:
            raise HTTPException(status_code=404, detail="Stop not found")
        
        # Get statistics
        stmt = select(StopStatistic).where(
            StopStatistic.stop_id == stop_id
        ).order_by(desc(StopStatistic.calculated_at)).limit(1)
        result = await session.execute(stmt)
        stats = result.scalar_one_or_none()
        
        return StopDetail(
            stop_id=stop.stop_id,
            stop_code=stop.stop_code,
            stop_name=stop.stop_name,
            position=Position(latitude=stop.latitude, longitude=stop.longitude),
            routes_serving=stats.routes_serving if stats else 0,
            scheduled_arrivals=stats.scheduled_arrivals if stats else 0,
            actual_arrivals=stats.actual_arrivals if stats else 0,
            average_arrival_delay=stats.average_arrival_delay if stats else None,
            median_arrival_delay=stats.median_arrival_delay if stats else None,
            on_time_percentage=stats.on_time_percentage if stats else 100.0,
            reliability_score=stats.reliability_score if stats else 100.0,
            wheelchair_accessible=stop.wheelchair_accessible,
        )
    
    # Stop arrivals
    @router.get("/stops/{stop_id}/arrivals", response_model=StopArrivalsResponse)
    async def get_stop_arrivals(
        stop_id: str,
        limit: int = Query(20, ge=1, le=100),
        session: AsyncSession = Depends(get_db_session),
    ):
        """Get upcoming arrivals at a stop."""
        
        # Get stop
        stmt = select(Stop).where(Stop.stop_id == stop_id)
        result = await session.execute(stmt)
        stop = result.scalar_one_or_none()
        
        if not stop:
            raise HTTPException(status_code=404, detail="Stop not found")
        
        # Get recent trip updates mentioning this stop
        cutoff = datetime.utcnow() - timedelta(minutes=30)
        stmt = select(TripUpdate).where(
            TripUpdate.timestamp >= cutoff
        ).limit(limit * 2)
        result = await session.execute(stmt)
        updates = result.scalars().all()
        
        arrivals = []
        for update in updates:
            if not update.stop_time_updates:
                continue
            
            for stu in update.stop_time_updates:
                if stu.get('stop_id') == stop_id:
                    arrivals.append(
                        StopArrival(
                            trip_id=update.trip_id,
                            route_id=update.route_id,
                            vehicle_id=update.vehicle_id,
                            scheduled_arrival=datetime.fromtimestamp(stu.get('arrival_time', 0)) if stu.get('arrival_time') else datetime.utcnow(),
                            predicted_arrival=datetime.fromtimestamp(stu.get('arrival_time', 0) + (stu.get('arrival_delay', 0) or 0)) if stu.get('arrival_time') else None,
                            delay_seconds=stu.get('arrival_delay'),
                            status="DELAYED" if stu.get('arrival_delay', 0) > 60 else "SCHEDULED",
                        )
                    )
        
        return StopArrivalsResponse(
            stop_id=stop_id,
            stop_name=stop.stop_name,
            timestamp=datetime.utcnow(),
            next_arrivals=arrivals[:limit],
        )
    
    # Network overview
    @router.get("/network/overview", response_model=NetworkOverviewResponse)
    async def get_network_overview(
        session: AsyncSession = Depends(get_db_session),
    ):
        """Get network-wide overview."""
        
        # Get network metrics
        metrics = await delay_calculator.calculate_network_metrics(
            session,
            datetime.utcnow() - timedelta(hours=1),
            datetime.utcnow(),
        )
        
        # Get worst routes
        worst_routes = await delay_calculator.identify_worst_performing_routes(session, limit=5)
        
        # Get worst stops
        worst_stops = await delay_calculator.identify_worst_performing_stops(session, limit=5)
        
        # Get heatmap
        heatmap = await heatmap_generator.generate_heatmap(session)
        corridors = await heatmap_generator.generate_corridor_heatmap(session)
        
        return NetworkOverviewResponse(
            timestamp=datetime.utcnow(),
            status=NetworkStatus(
                timestamp=datetime.utcnow(),
                total_vehicles=metrics['total_vehicles'],
                delayed_vehicles=metrics['delayed_vehicles'],
                severely_delayed_vehicles=metrics['severely_delayed_vehicles'],
                affected_routes=len(worst_routes),
                affected_stops=len(worst_stops),
                average_delay=metrics.get('average_delay'),
                network_reliability_score=metrics['network_reliability_score'],
            ),
            worst_routes=[
                WorstPerformer(
                    id=r['route_id'],
                    average_delay=r.get('average_delay'),
                    on_time_percentage=r.get('on_time_percentage'),
                    affected_count=r.get('delayed_vehicles', 0),
                    severity="severe" if r.get('average_delay', 0) > 600 else "moderate",
                )
                for r in worst_routes
            ],
            worst_stops=[
                WorstPerformer(
                    id=s['stop_id'],
                    average_delay=s.get('average_arrival_delay'),
                    on_time_percentage=s.get('on_time_percentage'),
                    affected_count=0,
                    severity="severe" if s.get('average_arrival_delay', 0) > 600 else "moderate",
                )
                for s in worst_stops
            ],
            corridors=corridors,
            heatmap=HeatmapData(
                timestamp=datetime.utcnow(),
                grid=[],  # Would populate from heatmap
                min_intensity=heatmap['min_intensity'],
                max_intensity=heatmap['max_intensity'],
                cell_size_meters=heatmap['cell_size_meters'],
                vehicle_count=heatmap['vehicle_count'],
                cell_count=heatmap['cell_count'],
            ),
        )
    
    # Replay snapshots
    @router.get("/replay/snapshots", response_model=List[ReplaySnapshot])
    async def get_replay_snapshots(
        hours: int = Query(24, ge=1, le=168),
    ):
        """Get available snapshots for replay."""
        
        end_time = datetime.utcnow()
        start_time = end_time - timedelta(hours=hours)
        
        snapshots = snapshot_manager.get_snapshots(start_time, end_time)
        
        return [
            ReplaySnapshot(
                timestamp=datetime.fromisoformat(s['timestamp']),
                vehicle_count=s['vehicle_count'],
                delayed_vehicles=s['delayed_vehicles'],
                severely_delayed_vehicles=s['severely_delayed_vehicles'],
                affected_routes=s['affected_routes'],
                average_delay=s.get('average_delay'),
            )
            for s in snapshots
        ]
    
    # Replay detail
    @router.get("/replay/snapshots/{timestamp}")
    async def get_replay_detail(timestamp: str):
        """Get detailed replay data at specific timestamp."""
        
        try:
            ts = datetime.fromisoformat(timestamp)
        except:
            raise HTTPException(status_code=400, detail="Invalid timestamp")
        
        detail = snapshot_manager.get_snapshot_detail(ts)
        
        if not detail:
            raise HTTPException(status_code=404, detail="Snapshot not found")
        
        return detail
    
    return router
