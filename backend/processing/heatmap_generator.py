"""Generate disruption heatmap from vehicle delay data."""
import logging
import math
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from geoalchemy2 import WKTElement
import numpy as np

from models import Vehicle

logger = logging.getLogger(__name__)


class HeatmapGenerator:
    """Generate heatmaps from vehicle delay data."""
    
    def __init__(self, cell_size_meters: int = 500, decay_hours: float = 2.0):
        """
        Initialize heatmap generator.
        
        Args:
            cell_size_meters: Grid cell size in meters (~0.005 degrees at 51°N)
            decay_hours: Time decay window for historical data
        """
        self.cell_size_meters = cell_size_meters
        self.decay_hours = decay_hours
        # Approximate degrees per meter at 51°N latitude (Bristol)
        self.degrees_per_meter = 1 / 111320 * math.cos(math.radians(51.45))
        self.cell_size_degrees = cell_size_meters * self.degrees_per_meter
    
    async def generate_heatmap(
        self,
        session: AsyncSession,
        minutes_window: int = 30,
    ) -> Dict[str, any]:
        """
        Generate disruption heatmap grid.
        
        Returns grid of cells with:
        - intensity: delay-weighted cell value
        - vehicle_count: number of vehicles in cell
        - average_delay: mean delay in cell
        - affected_routes: unique routes in cell
        """
        
        # Get recent vehicles
        cutoff_time = datetime.utcnow() - timedelta(minutes=minutes_window)
        stmt = select(Vehicle).where(
            Vehicle.timestamp >= cutoff_time
        )
        result = await session.execute(stmt)
        vehicles = result.scalars().all()
        
        if not vehicles:
            return {
                'grid': [],
                'min_intensity': 0,
                'max_intensity': 0,
                'cell_size_meters': self.cell_size_meters,
            }
        
        # Group vehicles into cells
        cells: Dict[Tuple[int, int], List[Vehicle]] = {}
        
        for vehicle in vehicles:
            cell_key = self._get_cell_key(vehicle.latitude, vehicle.longitude)
            if cell_key not in cells:
                cells[cell_key] = []
            cells[cell_key].append(vehicle)
        
        # Calculate cell statistics
        grid = []
        intensities = []
        
        for (grid_x, grid_y), cell_vehicles in cells.items():
            cell_data = self._calculate_cell_statistics(grid_x, grid_y, cell_vehicles)
            grid.append(cell_data)
            
            if cell_data['intensity'] > 0:
                intensities.append(cell_data['intensity'])
        
        return {
            'grid': grid,
            'min_intensity': min(intensities) if intensities else 0,
            'max_intensity': max(intensities) if intensities else 0,
            'cell_count': len(grid),
            'vehicle_count': len(vehicles),
            'cell_size_meters': self.cell_size_meters,
            'generated_at': datetime.utcnow().isoformat(),
        }
    
    def _get_cell_key(self, latitude: float, longitude: float) -> Tuple[int, int]:
        """Get grid cell coordinates from lat/lon."""
        grid_x = int(longitude / self.cell_size_degrees)
        grid_y = int(latitude / self.cell_size_degrees)
        return (grid_x, grid_y)
    
    def _get_cell_center(self, grid_x: int, grid_y: int) -> Tuple[float, float]:
        """Get center coordinates of grid cell."""
        lon = grid_x * self.cell_size_degrees + self.cell_size_degrees / 2
        lat = grid_y * self.cell_size_degrees + self.cell_size_degrees / 2
        return (lat, lon)
    
    def _calculate_cell_statistics(
        self,
        grid_x: int,
        grid_y: int,
        vehicles: List[Vehicle]
    ) -> Dict:
        """Calculate statistics for a grid cell."""
        
        lat, lon = self._get_cell_center(grid_x, grid_y)
        
        # Calculate delay metrics
        delays = [
            v.delay_seconds for v in vehicles
            if v.delay_seconds is not None
        ]
        
        if delays:
            avg_delay = np.mean(delays)
            max_delay = np.max(delays)
            
            # Intensity: normalized weighted delay
            # Max out at 10 minutes (600 seconds) for intensity
            intensity = min(1.0, avg_delay / 600)
        else:
            avg_delay = 0
            max_delay = 0
            intensity = 0
        
        # Get unique routes
        routes = set(v.route_id for v in vehicles if v.route_id)
        
        # Count delayed vehicles
        delayed_count = sum(1 for v in vehicles if v.delay_seconds and v.delay_seconds > 60)
        
        return {
            'latitude': lat,
            'longitude': lon,
            'grid_x': grid_x,
            'grid_y': grid_y,
            'intensity': intensity,
            'vehicle_count': len(vehicles),
            'delayed_vehicles': delayed_count,
            'average_delay_seconds': avg_delay,
            'max_delay_seconds': max_delay,
            'affected_routes': list(routes),
            'affected_route_count': len(routes),
        }
    
    def _calculate_temporal_weight(self, timestamp: datetime) -> float:
        """Calculate weight based on age of data (decay function)."""
        age_minutes = (datetime.utcnow() - timestamp).total_seconds() / 60
        decay_window_minutes = self.decay_hours * 60
        
        # Linear decay: 1.0 at current, 0.0 after decay window
        weight = max(0, 1.0 - (age_minutes / decay_window_minutes))
        return weight
    
    async def generate_corridor_heatmap(
        self,
        session: AsyncSession,
        minutes_window: int = 30,
    ) -> List[Dict]:
        """
        Identify congestion corridors (sequences of delayed cells).
        
        Returns list of corridors with geographic extent and severity.
        """
        
        # First generate basic heatmap
        heatmap = await self.generate_heatmap(session, minutes_window)
        
        if not heatmap['grid']:
            return []
        
        # Find connected components of delayed cells
        # A cell is "delayed" if intensity > 0.3
        delayed_cells = {
            (c['grid_x'], c['grid_y']): c
            for c in heatmap['grid']
            if c['intensity'] > 0.3
        }
        
        if not delayed_cells:
            return []
        
        corridors = self._find_corridors(delayed_cells)
        return corridors
    
    def _find_corridors(self, cells: Dict[Tuple[int, int], Dict]) -> List[Dict]:
        """Find connected components of delayed cells."""
        
        visited = set()
        corridors = []
        
        def flood_fill(start_key):
            """Flood fill to find connected corridor."""
            to_visit = [start_key]
            corridor_cells = []
            
            while to_visit:
                key = to_visit.pop(0)
                if key in visited:
                    continue
                
                visited.add(key)
                corridor_cells.append(cells[key])
                
                # Check neighbors
                x, y = key
                for dx, dy in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    neighbor = (x + dx, y + dy)
                    if neighbor in cells and neighbor not in visited:
                        to_visit.append(neighbor)
            
            return corridor_cells
        
        # Find all corridors
        for key in cells:
            if key not in visited:
                corridor_cells = flood_fill(key)
                if len(corridor_cells) > 1:  # Only count as corridor if multiple cells
                    corridor = self._corridor_statistics(corridor_cells)
                    corridors.append(corridor)
        
        return sorted(corridors, key=lambda c: c['severity'], reverse=True)
    
    def _corridor_statistics(self, cells: List[Dict]) -> Dict:
        """Calculate statistics for a corridor."""
        
        lats = [c['latitude'] for c in cells]
        lons = [c['longitude'] for c in cells]
        intensities = [c['intensity'] for c in cells]
        
        return {
            'cell_count': len(cells),
            'bounds': {
                'north': max(lats),
                'south': min(lats),
                'east': max(lons),
                'west': min(lons),
            },
            'center': {
                'latitude': np.mean(lats),
                'longitude': np.mean(lons),
            },
            'severity': np.mean(intensities),
            'max_intensity': max(intensities),
            'vehicle_count': sum(c['vehicle_count'] for c in cells),
            'affected_routes': list(set(
                route for c in cells
                for route in c['affected_routes']
            )),
        }
