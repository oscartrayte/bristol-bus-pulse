"""Bristol Bus Pulse - Main FastAPI Application."""
import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import json

from config import settings
from database import db_manager, get_db_session
from ingestion.gtfs_rt_parser import GTFSRealtimeParser
from ingestion.gtfs_parser import GTFSParser
from processing.delay_calculator import DelayCalculator
from processing.heatmap_generator import HeatmapGenerator
from processing.snapshot_manager import SnapshotManager
from api.routes import create_routes
from api.schemas import (
    LiveVehicle, RouteStatistics, StopDetail, NetworkStatus, 
    ReplaySnapshot, HeatmapData
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# Global components
gtfs_rt_parser: GTFSRealtimeParser = None
gtfs_parser: GTFSParser = None
delay_calculator: DelayCalculator = None
heatmap_generator: HeatmapGenerator = None
snapshot_manager: SnapshotManager = None

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
    
    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
    
    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)
    
    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass


connection_manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown."""
    
    # Startup
    logger.info("Starting Bristol Bus Pulse...")
    
    global gtfs_rt_parser, gtfs_parser, delay_calculator, heatmap_generator, snapshot_manager
    
    # Initialize database
    await db_manager.initialize()
    
    # Initialize parsers
    gtfs_rt_parser = GTFSRealtimeParser(
        feed_url=settings.gtfs_rt_feed_url,
        api_key=settings.bods_api_key
    )
    await gtfs_rt_parser.initialize()
    
    gtfs_parser = GTFSParser(
        gtfs_url=settings.gtfs_timetable_url or settings.gtfs_rt_feed_url.replace('gtfsrt', 'gtfs'),
        api_key=settings.bods_api_key
    )
    await gtfs_parser.initialize()
    
    # Download initial GTFS data
    logger.info("Downloading GTFS schedule data...")
    if not await gtfs_parser.download_and_parse():
        logger.warning("Failed to download GTFS data, proceeding with partial functionality")
    
    # Initialize processing components
    delay_calculator = DelayCalculator(gtfs_parser)
    heatmap_generator = HeatmapGenerator(
        cell_size_meters=settings.heatmap_cell_size_meters,
        decay_hours=settings.heatmap_decay_hours
    )
    snapshot_manager = SnapshotManager()
    
    # Start background tasks
    asyncio.create_task(ingestion_loop())
    asyncio.create_task(snapshot_loop())
    asyncio.create_task(statistics_loop())
    
    logger.info("Bristol Bus Pulse started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Bristol Bus Pulse...")
    
    await gtfs_rt_parser.shutdown()
    await gtfs_parser.shutdown()
    await db_manager.shutdown()
    
    logger.info("Bristol Bus Pulse shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Bristol Bus Pulse",
    description="Real-time visualization of Bristol's bus network health",
    version="1.0.0",
    lifespan=lifespan
)

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
api_router = create_routes(
    gtfs_rt_parser,
    delay_calculator,
    heatmap_generator,
    snapshot_manager,
    connection_manager
)
app.include_router(api_router)


# Background tasks

async def ingestion_loop():
    """Continuously ingest real-time data."""
    logger.info("Starting ingestion loop")
    
    while True:
        try:
            await asyncio.sleep(settings.ingestion_interval_seconds)
            
            # Fetch vehicle positions
            vehicles = await gtfs_rt_parser.fetch_vehicle_positions()
            
            # Fetch trip updates
            trip_updates = await gtfs_rt_parser.fetch_trip_updates()
            
            # Store in database
            async with db_manager.get_session() as session:
                from models import Vehicle, TripUpdate
                from sqlalchemy.orm import sessionmaker
                
                # Store vehicles
                for v_data in vehicles:
                    vehicle = Vehicle(
                        vehicle_id=v_data['vehicle_id'],
                        operator_code=settings.get_operator_codes[0],
                        route_id=v_data.get('route_id', 'UNKNOWN'),
                        trip_id=v_data.get('trip_id', 'UNKNOWN'),
                        latitude=v_data['latitude'],
                        longitude=v_data['longitude'],
                        position=GTFSRealtimeParser.create_point(
                            v_data['latitude'],
                            v_data['longitude']
                        ),
                        heading=v_data.get('heading'),
                        next_stop_id=v_data.get('stop_id'),
                        occupancy_status=v_data.get('occupancy_status'),
                    )
                    session.merge(vehicle)
                
                # Store trip updates
                for t_data in trip_updates:
                    trip = TripUpdate(
                        trip_id=t_data['trip_id'],
                        vehicle_id=t_data.get('vehicle_id', 'UNKNOWN'),
                        route_id=t_data['route_id'],
                        current_stop_sequence=t_data.get('current_stop_sequence'),
                        current_status=t_data.get('current_status', 'SCHEDULED'),
                        delay_seconds=t_data.get('current_delay_seconds'),
                        stop_time_updates=t_data.get('stop_time_updates'),
                    )
                    session.merge(trip)
                
                await session.commit()
            
            logger.info(f"Ingested {len(vehicles)} vehicles, {len(trip_updates)} trip updates")
            
            # Broadcast update to WebSocket clients
            await connection_manager.broadcast({
                'type': 'vehicles_updated',
                'count': len(vehicles),
                'timestamp': datetime.utcnow().isoformat(),
            })
        
        except Exception as e:
            logger.error(f"Error in ingestion loop: {e}")
            await asyncio.sleep(5)


async def snapshot_loop():
    """Periodically create network snapshots."""
    logger.info("Starting snapshot loop")
    
    while True:
        try:
            await asyncio.sleep(settings.snapshot_interval_seconds)
            
            async with db_manager.get_session() as session:
                if not await snapshot_manager.create_snapshot(session):
                    logger.warning("Failed to create snapshot")
                
                # Cleanup old snapshots
                snapshot_manager.cleanup_old_snapshots(
                    settings.historical_retention_days
                )
        
        except Exception as e:
            logger.error(f"Error in snapshot loop: {e}")


async def statistics_loop():
    """Periodically calculate route and stop statistics."""
    logger.info("Starting statistics calculation loop")
    
    while True:
        try:
            await asyncio.sleep(300)  # Calculate every 5 minutes
            
            async with db_manager.get_session() as session:
                from models import RouteStatistic, StopStatistic
                
                # Get recent vehicles for statistics window
                window_start = datetime.utcnow() - timedelta(hours=1)
                window_end = datetime.utcnow()
                
                # Get unique routes
                from sqlalchemy import select, distinct
                from models import Vehicle
                
                stmt = select(distinct(Vehicle.route_id)).where(
                    Vehicle.timestamp >= window_start
                )
                result = await session.execute(stmt)
                routes = result.scalars().all()
                
                # Calculate route statistics
                for route_id in routes:
                    stats = await delay_calculator.calculate_route_statistics(
                        session, route_id, window_start, window_end
                    )
                    
                    route_stat = RouteStatistic(
                        route_id=route_id,
                        operator_code=settings.get_operator_codes[0],
                        active_vehicles=stats['active_vehicles'],
                        average_delay=stats.get('average_delay'),
                        median_delay=stats.get('median_delay'),
                        on_time_percentage=stats.get('on_time_percentage', 0),
                        delayed_vehicles=stats.get('delayed_vehicles', 0),
                        severely_delayed_vehicles=stats.get('severely_delayed_vehicles', 0),
                        window_start=window_start,
                        window_end=window_end,
                    )
                    session.merge(route_stat)
                
                await session.commit()
                logger.info(f"Updated statistics for {len(routes)} routes")
        
        except Exception as e:
            logger.error(f"Error in statistics loop: {e}")


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    db_healthy = await db_manager.health_check()
    
    return {
        'status': 'healthy' if db_healthy else 'degraded',
        'database': 'ok' if db_healthy else 'error',
        'timestamp': datetime.utcnow().isoformat(),
    }


# WebSocket endpoint for live updates
@app.websocket("/ws/live")
async def websocket_live_updates(websocket: WebSocket):
    """WebSocket endpoint for live vehicle updates."""
    await connection_manager.connect(websocket)
    
    try:
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
            # Process any incoming messages if needed
    except WebSocketDisconnect:
        connection_manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        connection_manager.disconnect(websocket)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
    )
