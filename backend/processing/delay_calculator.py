"""Delay calculation engine using GTFS-RT and schedule data."""
import logging
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import numpy as np

from models import Vehicle, TripUpdate, RouteStatistic, StopStatistic, Stop
from ingestion.gtfs_parser import GTFSParser

logger = logging.getLogger(__name__)


class DelayCalculator:
    """Calculate delays from GTFS schedule and realtime data."""
    
    def __init__(self, gtfs_parser: GTFSParser):
        self.gtfs = gtfs_parser
    
    def calculate_vehicle_delay(
        self,
        trip_id: str,
        current_stop_sequence: int,
        current_delay_seconds: Optional[int] = None,
        vehicle_timestamp: Optional[datetime] = None
    ) -> Optional[int]:
        """
        Calculate delay for a vehicle given trip and current stop.
        
        Returns delay in seconds (negative = early, positive = late).
        """
        if not current_delay_seconds:
            return None
        
        return current_delay_seconds
    
    def categorize_delay(self, delay_seconds: Optional[int]) -> str:
        """Categorize delay into color bands."""
        if delay_seconds is None:
            return "unknown"
        
        if delay_seconds <= 60:  # 0-1 min
            return "green"
        elif delay_seconds <= 300:  # 1-5 min
            return "yellow"
        elif delay_seconds <= 600:  # 5-10 min
            return "orange"
        else:  # 10+ min
            return "red"
    
    def get_delay_severity(self, delay_seconds: Optional[int]) -> str:
        """Get severity level."""
        if delay_seconds is None:
            return "unknown"
        
        if delay_seconds <= 60:
            return "on_time"
        elif delay_seconds <= 300:
            return "minor_delay"
        elif delay_seconds <= 600:
            return "moderate_delay"
        else:
            return "severe_delay"
    
    async def calculate_route_statistics(
        self,
        session: AsyncSession,
        route_id: str,
        window_start: datetime,
        window_end: datetime
    ) -> Dict:
        """Calculate aggregate statistics for a route."""
        
        # Get all vehicles on this route in time window
        stmt = select(Vehicle).where(
            and_(
                Vehicle.route_id == route_id,
                Vehicle.timestamp >= window_start,
                Vehicle.timestamp <= window_end,
            )
        )
        result = await session.execute(stmt)
        vehicles = result.scalars().all()
        
        if not vehicles:
            return {
                'route_id': route_id,
                'active_vehicles': 0,
                'average_delay': None,
                'median_delay': None,
                'on_time_percentage': 0.0,
            }
        
        delays = [v.delay_seconds for v in vehicles if v.delay_seconds is not None]
        
        if not delays:
            on_time_pct = 100.0
            avg_delay = 0
            med_delay = 0
            delayed_count = 0
        else:
            on_time_count = sum(1 for d in delays if d <= 60)
            on_time_pct = (on_time_count / len(delays)) * 100
            avg_delay = np.mean(delays)
            med_delay = float(np.median(delays))
            delayed_count = sum(1 for d in delays if d > 60)
        
        severely_delayed = sum(1 for d in delays if d > 600) if delays else 0
        
        return {
            'route_id': route_id,
            'active_vehicles': len(vehicles),
            'average_delay': avg_delay,
            'median_delay': med_delay,
            'on_time_percentage': on_time_pct,
            'delayed_vehicles': delayed_count,
            'severely_delayed_vehicles': severely_delayed,
        }
    
    async def calculate_stop_statistics(
        self,
        session: AsyncSession,
        stop_id: str,
        window_start: datetime,
        window_end: datetime
    ) -> Dict:
        """Calculate aggregate statistics for a stop."""
        
        # Get all trip updates that serve this stop in time window
        stmt = select(TripUpdate).where(
            and_(
                TripUpdate.timestamp >= window_start,
                TripUpdate.timestamp <= window_end,
            )
        )
        result = await session.execute(stmt)
        trip_updates = result.scalars().all()
        
        # Filter for updates that mention this stop
        relevant_updates = []
        arrival_delays = []
        
        for update in trip_updates:
            if not update.stop_time_updates:
                continue
            
            for stu in update.stop_time_updates:
                if stu.get('stop_id') == stop_id:
                    relevant_updates.append(update)
                    if 'arrival_delay' in stu:
                        arrival_delays.append(stu['arrival_delay'])
        
        if not arrival_delays:
            return {
                'stop_id': stop_id,
                'scheduled_arrivals': len(relevant_updates),
                'average_arrival_delay': None,
                'on_time_percentage': 100.0,
                'reliability_score': 100.0,
            }
        
        on_time_count = sum(1 for d in arrival_delays if d <= 60)
        on_time_pct = (on_time_count / len(arrival_delays)) * 100
        avg_delay = np.mean(arrival_delays)
        med_delay = float(np.median(arrival_delays))
        
        # Reliability score: 100% on-time, declining for delays
        reliability_score = max(0, 100 - (avg_delay / 60))
        
        return {
            'stop_id': stop_id,
            'scheduled_arrivals': len(relevant_updates),
            'actual_arrivals': len(arrival_delays),
            'average_arrival_delay': avg_delay,
            'median_arrival_delay': med_delay,
            'on_time_percentage': on_time_pct,
            'reliability_score': reliability_score,
        }
    
    async def calculate_network_metrics(
        self,
        session: AsyncSession,
        window_start: datetime,
        window_end: datetime
    ) -> Dict:
        """Calculate network-wide metrics."""
        
        # Get all vehicles
        stmt = select(Vehicle).where(
            and_(
                Vehicle.timestamp >= window_start,
                Vehicle.timestamp <= window_end,
            )
        )
        result = await session.execute(stmt)
        vehicles = result.scalars().all()
        
        if not vehicles:
            return {
                'total_vehicles': 0,
                'delayed_vehicles': 0,
                'severely_delayed_vehicles': 0,
                'average_delay': 0,
                'network_reliability_score': 0,
            }
        
        delays = [v.delay_seconds for v in vehicles if v.delay_seconds is not None]
        
        delayed = sum(1 for v in vehicles if v.delay_seconds and v.delay_seconds > 60)
        severely_delayed = sum(1 for v in vehicles if v.delay_seconds and v.delay_seconds > 600)
        
        if delays:
            avg_delay = np.mean(delays)
            reliability_score = max(0, 100 - (avg_delay / 60))
        else:
            avg_delay = 0
            reliability_score = 100.0
        
        return {
            'total_vehicles': len(vehicles),
            'delayed_vehicles': delayed,
            'severely_delayed_vehicles': severely_delayed,
            'average_delay': avg_delay,
            'network_reliability_score': reliability_score,
        }
    
    async def identify_worst_performing_routes(
        self,
        session: AsyncSession,
        limit: int = 10
    ) -> List[Dict]:
        """Get worst performing routes by delay."""
        
        stmt = select(RouteStatistic).order_by(
            RouteStatistic.average_delay.desc()
        ).limit(limit)
        
        result = await session.execute(stmt)
        routes = result.scalars().all()
        
        return [
            {
                'route_id': r.route_id,
                'average_delay': r.average_delay,
                'delayed_vehicles': r.delayed_vehicles,
                'on_time_percentage': r.on_time_percentage,
            }
            for r in routes
        ]
    
    async def identify_worst_performing_stops(
        self,
        session: AsyncSession,
        limit: int = 10
    ) -> List[Dict]:
        """Get worst performing stops by delay."""
        
        stmt = select(StopStatistic).order_by(
            StopStatistic.average_arrival_delay.desc()
        ).limit(limit)
        
        result = await session.execute(stmt)
        stops = result.scalars().all()
        
        return [
            {
                'stop_id': s.stop_id,
                'average_arrival_delay': s.average_arrival_delay,
                'on_time_percentage': s.on_time_percentage,
                'reliability_score': s.reliability_score,
            }
            for s in stops
        ]
