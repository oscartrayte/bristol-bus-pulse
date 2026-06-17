"""GTFS static schedule parsing."""
import logging
import io
import zipfile
from datetime import datetime, time
from typing import Dict, List, Optional, Set, Tuple
import aiohttp
import csv
import asyncio

logger = logging.getLogger(__name__)


class GTFSParser:
    """Parser for static GTFS schedule data."""
    
    def __init__(self, gtfs_url: str, api_key: Optional[str] = None):
        self.gtfs_url = gtfs_url
        self.api_key = api_key
        self.session: Optional[aiohttp.ClientSession] = None
        self.data: Dict = {
            'routes': {},
            'stops': {},
            'trips': {},
            'stop_times': {},
            'calendar': {},
        }
    
    async def initialize(self) -> None:
        """Initialize HTTP session."""
        self.session = aiohttp.ClientSession()
    
    async def shutdown(self) -> None:
        """Close HTTP session."""
        if self.session:
            await self.session.close()
    
    async def download_and_parse(self) -> bool:
        """Download GTFS zip and parse all files."""
        if not self.session:
            await self.initialize()
        
        try:
            headers = {}
            if self.api_key:
                headers["x-api-key"] = self.api_key
            
            async with self.session.get(
                self.gtfs_url,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                if response.status != 200:
                    logger.error(f"GTFS download error: {response.status}")
                    return False
                
                data = await response.read()
                
                # Parse GTFS ZIP
                with zipfile.ZipFile(io.BytesIO(data)) as zip_file:
                    await self._parse_routes(zip_file)
                    await self._parse_stops(zip_file)
                    await self._parse_calendar(zip_file)
                    await self._parse_trips(zip_file)
                    await self._parse_stop_times(zip_file)
                
                logger.info(
                    f"Parsed GTFS: {len(self.data['routes'])} routes, "
                    f"{len(self.data['stops'])} stops, "
                    f"{len(self.data['trips'])} trips"
                )
                return True
        
        except Exception as e:
            logger.error(f"Error downloading/parsing GTFS: {e}")
            return False
    
    async def _parse_routes(self, zip_file: zipfile.ZipFile) -> None:
        """Parse routes.txt."""
        try:
            with zip_file.open('routes.txt') as f:
                reader = csv.DictReader(io.TextIOWrapper(f, 'utf-8'))
                for row in reader:
                    route_id = row['route_id']
                    self.data['routes'][route_id] = {
                        'route_id': route_id,
                        'agency_id': row.get('agency_id'),
                        'route_short_name': row.get('route_short_name'),
                        'route_long_name': row.get('route_long_name'),
                        'route_type': row.get('route_type'),
                        'route_url': row.get('route_url'),
                        'route_color': row.get('route_color'),
                        'route_text_color': row.get('route_text_color'),
                    }
        except KeyError:
            logger.warning("routes.txt not found in GTFS")
    
    async def _parse_stops(self, zip_file: zipfile.ZipFile) -> None:
        """Parse stops.txt."""
        try:
            with zip_file.open('stops.txt') as f:
                reader = csv.DictReader(io.TextIOWrapper(f, 'utf-8'))
                for row in reader:
                    stop_id = row['stop_id']
                    self.data['stops'][stop_id] = {
                        'stop_id': stop_id,
                        'stop_code': row.get('stop_code'),
                        'stop_name': row.get('stop_name'),
                        'stop_desc': row.get('stop_desc'),
                        'stop_lat': float(row['stop_lat']),
                        'stop_lon': float(row['stop_lon']),
                        'zone_id': row.get('zone_id'),
                        'stop_url': row.get('stop_url'),
                        'location_type': row.get('location_type', 0),
                        'parent_station': row.get('parent_station'),
                        'wheelchair_boarding': row.get('wheelchair_boarding'),
                    }
        except KeyError as e:
            logger.warning(f"stops.txt not found or missing field: {e}")
    
    async def _parse_calendar(self, zip_file: zipfile.ZipFile) -> None:
        """Parse calendar.txt for service dates."""
        try:
            with zip_file.open('calendar.txt') as f:
                reader = csv.DictReader(io.TextIOWrapper(f, 'utf-8'))
                for row in reader:
                    service_id = row['service_id']
                    self.data['calendar'][service_id] = {
                        'service_id': service_id,
                        'monday': int(row['monday']),
                        'tuesday': int(row['tuesday']),
                        'wednesday': int(row['wednesday']),
                        'thursday': int(row['thursday']),
                        'friday': int(row['friday']),
                        'saturday': int(row['saturday']),
                        'sunday': int(row['sunday']),
                        'start_date': row['start_date'],
                        'end_date': row['end_date'],
                    }
        except KeyError:
            logger.warning("calendar.txt not found")
    
    async def _parse_trips(self, zip_file: zipfile.ZipFile) -> None:
        """Parse trips.txt."""
        try:
            with zip_file.open('trips.txt') as f:
                reader = csv.DictReader(io.TextIOWrapper(f, 'utf-8'))
                for row in reader:
                    trip_id = row['trip_id']
                    self.data['trips'][trip_id] = {
                        'trip_id': trip_id,
                        'route_id': row['route_id'],
                        'service_id': row['service_id'],
                        'trip_headsign': row.get('trip_headsign'),
                        'direction_id': row.get('direction_id'),
                        'block_id': row.get('block_id'),
                        'shape_id': row.get('shape_id'),
                    }
        except KeyError:
            logger.warning("trips.txt not found")
    
    async def _parse_stop_times(self, zip_file: zipfile.ZipFile) -> None:
        """Parse stop_times.txt."""
        try:
            with zip_file.open('stop_times.txt') as f:
                reader = csv.DictReader(io.TextIOWrapper(f, 'utf-8'))
                for row in reader:
                    trip_id = row['trip_id']
                    if trip_id not in self.data['stop_times']:
                        self.data['stop_times'][trip_id] = []
                    
                    self.data['stop_times'][trip_id].append({
                        'trip_id': trip_id,
                        'arrival_time': row.get('arrival_time'),
                        'departure_time': row.get('departure_time'),
                        'stop_id': row['stop_id'],
                        'stop_sequence': int(row['stop_sequence']),
                        'stop_headsign': row.get('stop_headsign'),
                        'pickup_type': row.get('pickup_type', 0),
                        'drop_off_type': row.get('drop_off_type', 0),
                    })
                
                # Sort stop times by sequence
                for trip_id, stops in self.data['stop_times'].items():
                    stops.sort(key=lambda x: x['stop_sequence'])
        
        except KeyError:
            logger.warning("stop_times.txt not found")
    
    def get_stop_times_for_trip(self, trip_id: str) -> List[Dict]:
        """Get scheduled stop times for a trip."""
        return self.data['stop_times'].get(trip_id, [])
    
    def get_stop_by_id(self, stop_id: str) -> Optional[Dict]:
        """Get stop information by ID."""
        return self.data['stops'].get(stop_id)
    
    def get_route_by_id(self, route_id: str) -> Optional[Dict]:
        """Get route information by ID."""
        return self.data['routes'].get(route_id)
    
    def get_trip_by_id(self, trip_id: str) -> Optional[Dict]:
        """Get trip information by ID."""
        return self.data['trips'].get(trip_id)
    
    def get_next_scheduled_stop(self, trip_id: str, current_sequence: int) -> Optional[Dict]:
        """Get next scheduled stop for a trip given current stop sequence."""
        stop_times = self.get_stop_times_for_trip(trip_id)
        
        for st in stop_times:
            if st['stop_sequence'] > current_sequence:
                return st
        
        return None
    
    def time_to_seconds(self, time_str: str) -> Optional[int]:
        """Convert HH:MM:SS to seconds since midnight."""
        try:
            h, m, s = map(int, time_str.split(':'))
            return h * 3600 + m * 60 + s
        except:
            return None
