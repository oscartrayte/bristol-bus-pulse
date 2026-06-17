"""Snapshot manager for historical replay functionality."""
import logging
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
import os

from models import Vehicle, RouteStatistic, StopStatistic, NetworkSnapshot

logger = logging.getLogger(__name__)


class SnapshotManager:
    """Manages historical snapshots for replay."""
    
    def __init__(self, db_path: str = "/tmp/bristol_snapshots.db"):
        self.db_path = db_path
        self._initialize_sqlite_db()
    
    def _initialize_sqlite_db(self) -> None:
        """Initialize SQLite database for snapshots."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Create snapshots table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY,
                    timestamp TIMESTAMP UNIQUE NOT NULL,
                    vehicle_count INTEGER,
                    delayed_vehicles INTEGER,
                    severely_delayed_vehicles INTEGER,
                    affected_routes INTEGER,
                    average_delay REAL,
                    vehicles_json TEXT NOT NULL,
                    routes_json TEXT NOT NULL,
                    stops_json TEXT NOT NULL,
                    heatmap_json TEXT
                )
            ''')
            
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON snapshots(timestamp)')
            
            conn.commit()
            conn.close()
            
            logger.info(f"Snapshot database initialized: {self.db_path}")
        except Exception as e:
            logger.error(f"Error initializing snapshot database: {e}")
    
    async def create_snapshot(
        self,
        session: AsyncSession,
        timestamp: Optional[datetime] = None
    ) -> bool:
        """Create and store a network snapshot."""
        
        if not timestamp:
            timestamp = datetime.utcnow()
        
        try:
            # Get current vehicle positions
            stmt = select(Vehicle).where(
                Vehicle.timestamp >= timestamp - timedelta(minutes=5)
            )
            result = await session.execute(stmt)
            vehicles = result.scalars().all()
            
            vehicle_data = [
                {
                    'vehicle_id': v.vehicle_id,
                    'route_id': v.route_id,
                    'latitude': v.latitude,
                    'longitude': v.longitude,
                    'heading': v.heading,
                    'delay_seconds': v.delay_seconds,
                    'timestamp': v.timestamp.isoformat(),
                }
                for v in vehicles
            ]
            
            # Get route statistics
            stmt = select(RouteStatistic).where(
                and_(
                    RouteStatistic.window_start >= timestamp - timedelta(hours=1),
                    RouteStatistic.window_end <= timestamp
                )
            ).order_by(RouteStatistic.average_delay.desc()).limit(100)
            result = await session.execute(stmt)
            routes = result.scalars().all()
            
            route_data = [
                {
                    'route_id': r.route_id,
                    'average_delay': r.average_delay,
                    'delayed_vehicles': r.delayed_vehicles,
                    'on_time_percentage': r.on_time_percentage,
                }
                for r in routes
            ]
            
            # Get stop statistics
            stmt = select(StopStatistic).where(
                and_(
                    StopStatistic.window_start >= timestamp - timedelta(hours=1),
                    StopStatistic.window_end <= timestamp
                )
            ).order_by(StopStatistic.average_arrival_delay.desc()).limit(100)
            result = await session.execute(stmt)
            stops = result.scalars().all()
            
            stop_data = [
                {
                    'stop_id': s.stop_id,
                    'average_arrival_delay': s.average_arrival_delay,
                    'reliability_score': s.reliability_score,
                }
                for s in stops
            ]
            
            # Store in SQLite
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            delayed_count = sum(1 for v in vehicles if v.delay_seconds and v.delay_seconds > 60)
            severely_delayed_count = sum(1 for v in vehicles if v.delay_seconds and v.delay_seconds > 600)
            avg_delay = sum(v.delay_seconds for v in vehicles if v.delay_seconds) / len(vehicles) if vehicles else 0
            
            cursor.execute('''
                INSERT OR REPLACE INTO snapshots 
                (timestamp, vehicle_count, delayed_vehicles, severely_delayed_vehicles,
                 affected_routes, average_delay, vehicles_json, routes_json, stops_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                timestamp.isoformat(),
                len(vehicles),
                delayed_count,
                severely_delayed_count,
                len(set(v.route_id for v in vehicles)),
                avg_delay,
                json.dumps(vehicle_data),
                json.dumps(route_data),
                json.dumps(stop_data),
            ))
            
            conn.commit()
            conn.close()
            
            logger.info(f"Snapshot created: {len(vehicles)} vehicles, {len(route_data)} routes")
            return True
        
        except Exception as e:
            logger.error(f"Error creating snapshot: {e}")
            return False
    
    def get_snapshots(
        self,
        start_time: datetime,
        end_time: datetime
    ) -> List[Dict]:
        """Get snapshots in time range."""
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT timestamp, vehicle_count, delayed_vehicles, severely_delayed_vehicles,
                       affected_routes, average_delay
                FROM snapshots
                WHERE timestamp BETWEEN ? AND ?
                ORDER BY timestamp ASC
            ''', (start_time.isoformat(), end_time.isoformat()))
            
            snapshots = []
            for row in cursor.fetchall():
                snapshots.append({
                    'timestamp': row[0],
                    'vehicle_count': row[1],
                    'delayed_vehicles': row[2],
                    'severely_delayed_vehicles': row[3],
                    'affected_routes': row[4],
                    'average_delay': row[5],
                })
            
            conn.close()
            return snapshots
        
        except Exception as e:
            logger.error(f"Error retrieving snapshots: {e}")
            return []
    
    def get_snapshot_detail(self, timestamp: datetime) -> Optional[Dict]:
        """Get detailed snapshot data."""
        
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT timestamp, vehicles_json, routes_json, stops_json
                FROM snapshots
                WHERE timestamp = ?
            ''', (timestamp.isoformat(),))
            
            row = cursor.fetchone()
            conn.close()
            
            if not row:
                return None
            
            return {
                'timestamp': row[0],
                'vehicles': json.loads(row[1]),
                'routes': json.loads(row[2]),
                'stops': json.loads(row[3]),
            }
        
        except Exception as e:
            logger.error(f"Error retrieving snapshot detail: {e}")
            return None
    
    def cleanup_old_snapshots(self, retention_days: int = 30) -> int:
        """Delete snapshots older than retention period."""
        
        try:
            cutoff = datetime.utcnow() - timedelta(days=retention_days)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute(
                'DELETE FROM snapshots WHERE timestamp < ?',
                (cutoff.isoformat(),)
            )
            
            deleted = cursor.rowcount
            conn.commit()
            conn.close()
            
            logger.info(f"Deleted {deleted} old snapshots")
            return deleted
        
        except Exception as e:
            logger.error(f"Error cleaning up snapshots: {e}")
            return 0
    
    def interpolate_snapshots(
        self,
        snapshot1: Dict,
        snapshot2: Dict,
        progress: float
    ) -> Dict:
        """
        Interpolate between two snapshots.
        
        Args:
            snapshot1: Earlier snapshot
            snapshot2: Later snapshot
            progress: Interpolation progress (0.0 to 1.0)
        
        Returns:
            Interpolated snapshot
        """
        
        # Interpolate vehicle positions
        vehicles1 = {v['vehicle_id']: v for v in snapshot1['vehicles']}
        vehicles2 = {v['vehicle_id']: v for v in snapshot2['vehicles']}
        
        interpolated_vehicles = []
        
        for vehicle_id in vehicles1:
            v1 = vehicles1[vehicle_id]
            v2 = vehicles2.get(vehicle_id)
            
            if not v2:
                # Vehicle not in second snapshot, keep first position
                interpolated_vehicles.append(v1)
                continue
            
            # Linear interpolation
            lat = v1['latitude'] + (v2['latitude'] - v1['latitude']) * progress
            lon = v1['longitude'] + (v2['longitude'] - v1['longitude']) * progress
            delay = v1['delay_seconds'] + (v2['delay_seconds'] - v1['delay_seconds']) * progress if v1['delay_seconds'] and v2['delay_seconds'] else v1['delay_seconds']
            
            interpolated_vehicles.append({
                'vehicle_id': vehicle_id,
                'route_id': v1['route_id'],
                'latitude': lat,
                'longitude': lon,
                'heading': v1.get('heading'),
                'delay_seconds': delay,
            })
        
        # Add vehicles that appear in snapshot2 but not snapshot1
        for vehicle_id in vehicles2:
            if vehicle_id not in vehicles1:
                interpolated_vehicles.append(vehicles2[vehicle_id])
        
        return {
            'vehicles': interpolated_vehicles,
            'routes': snapshot2['routes'],
            'stops': snapshot2['stops'],
        }
