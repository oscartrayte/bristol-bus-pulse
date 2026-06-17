"""GTFS-Realtime data parser and ingestion."""
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
import aiohttp
import asyncio
from google.transit import gtfs_realtime_pb2
from geoalchemy2 import WKTElement

logger = logging.getLogger(__name__)


class GTFSRealtimeParser:
    """Parser for GTFS-Realtime Protocol Buffer feeds."""
    
    def __init__(self, feed_url: str, api_key: Optional[str] = None):
        self.feed_url = feed_url
        self.api_key = api_key
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def initialize(self) -> None:
        """Initialize HTTP session."""
        self.session = aiohttp.ClientSession()
    
    async def shutdown(self) -> None:
        """Close HTTP session."""
        if self.session:
            await self.session.close()
    
    async def fetch_feed(self) -> Optional[gtfs_realtime_pb2.FeedMessage]:
        """Fetch and parse GTFS-RT feed."""
        if not self.session:
            await self.initialize()
        
        try:
            headers = {}
            if self.api_key:
                headers["x-api-key"] = self.api_key
            
            async with self.session.get(
                self.feed_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status != 200:
                    logger.error(f"GTFS-RT feed error: {response.status}")
                    return None
                
                data = await response.read()
                feed = gtfs_realtime_pb2.FeedMessage()
                feed.ParseFromString(data)
                
                logger.info(f"Fetched GTFS-RT feed with {len(feed.entity)} entities")
                return feed
        
        except asyncio.TimeoutError:
            logger.error("GTFS-RT feed request timeout")
            return None
        except Exception as e:
            logger.error(f"Error fetching GTFS-RT feed: {e}")
            return None
    
    async def fetch_vehicle_positions(self) -> List[Dict[str, Any]]:
        """Fetch and parse vehicle position updates."""
        feed = await self.fetch_feed()
        if not feed:
            return []
        
        vehicles = []
        for entity in feed.entity:
            if entity.HasField('vehicle'):
                vehicle_data = self._parse_vehicle(entity)
                if vehicle_data:
                    vehicles.append(vehicle_data)
        
        return vehicles
    
    async def fetch_trip_updates(self) -> List[Dict[str, Any]]:
        """Fetch and parse trip update data."""
        feed = await self.fetch_feed()
        if not feed:
            return []
        
        updates = []
        for entity in feed.entity:
            if entity.HasField('trip_update'):
                update_data = self._parse_trip_update(entity)
                if update_data:
                    updates.append(update_data)
        
        return updates
    
    @staticmethod
    def _parse_vehicle(entity) -> Optional[Dict[str, Any]]:
        """Parse a single vehicle entity."""
        vehicle = entity.vehicle
        position = vehicle.position
        
        if not position.HasField('latitude') or not position.HasField('longitude'):
            return None
        
        return {
            'vehicle_id': vehicle.vehicle.id,
            'trip_id': vehicle.trip.trip_id if vehicle.trip.HasField('trip_id') else None,
            'route_id': vehicle.trip.route_id if vehicle.trip.HasField('route_id') else None,
            'latitude': float(position.latitude),
            'longitude': float(position.longitude),
            'heading': float(position.bearing) if position.HasField('bearing') else None,
            'speed': float(position.speed) if position.HasField('speed') else None,
            'occupancy_status': vehicle.occupancy_status,
            'timestamp': datetime.fromtimestamp(vehicle.timestamp) if vehicle.HasField('timestamp') else datetime.utcnow(),
            'congestion_level': vehicle.congestion_level,
            'stop_id': vehicle.stop_id if vehicle.HasField('stop_id') else None,
        }
    
    @staticmethod
    def _parse_trip_update(entity) -> Optional[Dict[str, Any]]:
        """Parse a single trip update entity."""
        trip_update = entity.trip_update
        
        trip = trip_update.trip
        if not trip.HasField('trip_id') or not trip.HasField('route_id'):
            return None
        
        vehicle_id = None
        if trip_update.vehicle.HasField('id'):
            vehicle_id = trip_update.vehicle.id
        
        # Parse stop time updates
        stop_time_updates = []
        for stu in trip_update.stop_time_update:
            stop_update = {
                'stop_id': stu.stop_id,
                'stop_sequence': stu.stop_sequence,
            }
            
            if stu.HasField('arrival'):
                stop_update['arrival_delay'] = stu.arrival.delay
                stop_update['arrival_time'] = stu.arrival.time
                stop_update['arrival_uncertainty'] = stu.arrival.uncertainty
            
            if stu.HasField('departure'):
                stop_update['departure_delay'] = stu.departure.delay
                stop_update['departure_time'] = stu.departure.time
                stop_update['departure_uncertainty'] = stu.departure.uncertainty
            
            stop_update['schedule_relationship'] = stu.schedule_relationship
            stop_time_updates.append(stop_update)
        
        # Use most recent stop update for current delay
        current_delay = None
        current_stop_sequence = None
        for stu in reversed(stop_time_updates):
            if 'arrival_delay' in stu:
                current_delay = stu['arrival_delay']
                current_stop_sequence = stu['stop_sequence']
                break
        
        return {
            'trip_id': trip.trip_id,
            'route_id': trip.route_id,
            'vehicle_id': vehicle_id,
            'current_stop_sequence': current_stop_sequence,
            'current_delay_seconds': current_delay,
            'current_status': trip_update.vehicle.current_status,
            'timestamp': datetime.fromtimestamp(trip_update.timestamp) if trip_update.HasField('timestamp') else datetime.utcnow(),
            'stop_time_updates': stop_time_updates,
        }
    
    @staticmethod
    def create_point(latitude: float, longitude: float) -> WKTElement:
        """Create WKT Point from coordinates."""
        return WKTElement(f'POINT({longitude} {latitude})', srid=4326)
