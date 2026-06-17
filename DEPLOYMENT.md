# Bristol Bus Pulse - Complete Setup & Deployment Guide

## Overview

This guide covers all aspects of setting up, developing, deploying, and maintaining Bristol Bus Pulse.

---

## Part 1: Local Development Setup

### Prerequisites

- **Docker & Docker Compose** (recommended) or:
  - Python 3.11+
  - Node.js 18+
  - PostgreSQL 15+
  - PostGIS 3.3+

### Option A: Quick Start with Docker Compose

```bash
# Clone repository
cd bristol-bus-pulse

# Copy environment files
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

# Edit backend/.env with your BODS API key
# BODS_API_KEY=your_actual_key_here

# Start all services
docker-compose up --build

# The application will be available at:
# Frontend: http://localhost:3000
# Backend API: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

### Option B: Manual Setup

#### Database Setup

```bash
# Create PostgreSQL database with PostGIS
createdb bristol_bus_pulse
psql bristol_bus_pulse -c "CREATE EXTENSION postgis;"

# Or using Docker
docker run -d \
  --name bristol-postgres \
  -e POSTGRES_USER=bristol_user \
  -e POSTGRES_PASSWORD=bristol_password \
  -e POSTGRES_DB=bristol_bus_pulse \
  -p 5432:5432 \
  postgis/postgis:15-3.3
```

#### Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env

# Edit .env with your settings
# - DATABASE_URL pointing to PostgreSQL
# - BODS_API_KEY from https://data.bus-data.dft.gov.uk/

# Start backend
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

#### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Create .env file
cp .env.example .env

# Start development server
npm run dev

# Open http://localhost:3000
```

---

## Part 2: Environment Configuration

### Backend Configuration (.env)

```bash
# Database
DATABASE_URL=postgresql+asyncpg://bristol_user:bristol_password@localhost:5432/bristol_bus_pulse
DB_ECHO=false

# BODS API (Required)
# Get your API key from: https://data.bus-data.dft.gov.uk/
BODS_API_KEY=your_api_key_here

# Data Feed URLs
GTFS_RT_FEED_URL=https://data.bus-data.dft.gov.uk/api/v1/gtfsrt
NAPTAN_FEED_URL=https://naptan.app.dft.gov.uk/data-download
GTFS_TIMETABLE_URL=https://data.bus-data.dft.gov.uk/api/v1/gtfs

# Operator Configuration
# First Bus: FBUS
# Stagecoach: MCR, SMC, etc.
OPERATOR_CODES=FBUS

# Ingestion Settings
INGESTION_INTERVAL_SECONDS=30  # How often to fetch GTFS-RT data
SNAPSHOT_INTERVAL_SECONDS=300  # How often to save snapshots (5 minutes)
HISTORICAL_RETENTION_DAYS=30   # Delete data older than this

# Processing
DELAY_THRESHOLDS_SECONDS=60,300,600  # Green, yellow, orange thresholds
HEATMAP_CELL_SIZE_METERS=500         # Geographic cell size
HEATMAP_DECAY_HOURS=2.0              # Time window for heatmap

# Server
ENVIRONMENT=development
LOG_LEVEL=INFO
DEBUG=true

# CORS
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:8000

# Performance tuning
MAX_WORKERS=4
BATCH_SIZE=1000
```

### Frontend Configuration (.env.local)

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_MAP_STYLE=dark
```

---

## Part 3: BODS API Registration

### Getting Your API Key

1. Visit: https://data.bus-data.dft.gov.uk/
2. Create a free account
3. Navigate to API section
4. Request API access (free tier available)
5. Copy your API key
6. Add to backend `.env` as `BODS_API_KEY`

### Data Feeds Available

- **GTFS Realtime (Vehicle Positions)**: Updated every 10-30 seconds
- **GTFS Realtime (Trip Updates)**: Updated every 10-30 seconds
- **GTFS Schedule Data**: Updated daily
- **NaPTAN Stops**: Updated regularly

---

## Part 4: Data Architecture

### Database Schema

#### vehicles table
Stores live vehicle positions updated every 30 seconds.

```sql
CREATE TABLE vehicles (
  id SERIAL PRIMARY KEY,
  vehicle_id VARCHAR(50) UNIQUE NOT NULL,
  operator_code VARCHAR(20) NOT NULL,
  route_id VARCHAR(50) NOT NULL,
  latitude FLOAT NOT NULL,
  longitude FLOAT NOT NULL,
  heading FLOAT,
  delay_seconds INTEGER,
  timestamp TIMESTAMP NOT NULL,
  INDEX idx_timestamp (timestamp),
  INDEX idx_position (position)
);
```

#### trip_updates table
Stores delay information from GTFS-RT Trip Updates.

```sql
CREATE TABLE trip_updates (
  id SERIAL PRIMARY KEY,
  trip_id VARCHAR(100) NOT NULL,
  vehicle_id VARCHAR(50) NOT NULL,
  route_id VARCHAR(50) NOT NULL,
  current_delay_seconds INTEGER,
  stop_time_updates JSONB,  -- Array of {stop_id, arrival_delay, departure_delay}
  timestamp TIMESTAMP NOT NULL
);
```

#### Indexes
- `idx_timestamp`: Query vehicles/updates in time windows
- `idx_route_delay`: Aggregate route statistics
- `idx_position`: Geographic queries for heatmaps

### Data Flow

```
GTFS-RT Vehicle Positions (every 30s)
                    ↓
    gtfs_rt_parser.py parses protobuf
                    ↓
    Upsert into vehicles table
                    ↓
    Background job calculates statistics
                    ↓
    WebSocket broadcasts to clients
```

---

## Part 5: Delay Calculation

### Algorithm

Delays are calculated using GTFS-RT Trip Updates:

```python
delay_seconds = predicted_arrival_time - scheduled_arrival_time
```

### Data Sources

1. **Scheduled times**: From GTFS static schedule
2. **Predicted times**: From GTFS-RT Trip Updates
3. **Calculation**: delay_calculator.py compares both

### Aggregation

#### Per Route (RouteStatistic)
- Average delay (all vehicles on route)
- Median delay
- Percentage on-time (≤60 seconds)
- Count of severely delayed vehicles

#### Per Stop (StopStatistic)
- Average arrival delay
- Service reliability score
- Percentage on-time arrivals
- Missed trip count

### Severity Bands

- **0-1 min**: Green (on-time)
- **1-5 min**: Yellow (minor delay)
- **5-10 min**: Orange (moderate delay)
- **10+ min**: Red (severe delay)

---

## Part 6: Real-Time Architecture

### WebSocket Connection

Frontend maintains persistent connection to `/ws/live` endpoint:

```
Client → WebSocket Connection
         ↓
Backend receives connection
         ↓
Ingestion loop fetches data every 30s
         ↓
ConnectionManager broadcasts to all clients
         ↓
Clients update map in real-time
```

### Message Format

```json
{
  "type": "vehicles_updated",
  "count": 245,
  "timestamp": "2024-01-15T12:30:00Z"
}
```

### Connection Management

- Automatic reconnection on disconnect
- Heartbeat/ping-pong every 30 seconds
- Graceful degradation if connection lost
- Falls back to polling (10 second intervals)

---

## Part 7: Replay System

### Snapshot Storage

Snapshots are stored in SQLite every 5 minutes:

```sql
CREATE TABLE snapshots (
  id INTEGER PRIMARY KEY,
  timestamp TIMESTAMP UNIQUE NOT NULL,
  vehicle_count INTEGER,
  delayed_vehicles INTEGER,
  vehicles_json TEXT,
  routes_json TEXT,
  stops_json TEXT,
  heatmap_json TEXT
);
```

### Interpolation

When replaying between snapshots:

```python
interpolated_vehicle = {
  'latitude': v1.lat + (v2.lat - v1.lat) * progress,
  'longitude': v1.lon + (v2.lon - v1.lon) * progress,
  'delay': v1.delay + (v2.delay - v1.delay) * progress,
}
```

### Retention Policy

- Keep snapshots for 30 days
- Delete older snapshots automatically
- Cleanup runs during statistics calculation

---

## Part 8: Heatmap Generation

### Algorithm

1. Divide Bristol into 500m × 500m grid cells
2. Group vehicles into cells by latitude/longitude
3. Calculate intensity = avg_delay / 600 (normalized to 10 min threshold)
4. Render as heatmap layer on map

### Cell Statistics

For each cell:
- Vehicle count
- Average delay
- Percentage delayed
- Affected routes
- Intensity (0.0-1.0)

### Corridor Detection

Connected components analysis identifies congestion corridors:

1. Find all "delayed" cells (intensity > 0.3)
2. Flood-fill to find connected groups
3. Calculate bounding box and center
4. Return sorted by severity

---

## Part 9: Production Deployment

### Kubernetes Deployment

See `k8s/deployment.yaml`:

```bash
# Build and push images
docker build -t your-registry/bristol-bus-pulse:1.0.0 ./backend
docker push your-registry/bristol-bus-pulse:1.0.0

# Deploy to cluster
kubectl apply -f k8s/

# Check status
kubectl get pods -n bristol
kubectl logs -f deployment/bristol-bus-pulse-backend -n bristol
```

### Docker Compose Deployment

For VPS/small instances:

```bash
docker-compose -f docker-compose.prod.yml up -d

# Monitor
docker-compose logs -f backend
```

### Environment for Production

```bash
# backend/.env.prod
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=WARNING

DATABASE_URL=postgresql+asyncpg://bristol_user:SECURE_PASSWORD@db.example.com:5432/bristol_bus_pulse

BODS_API_KEY=your_production_key

ALLOWED_ORIGINS=https://bristol-bus-pulse.example.com

# Enable rate limiting
RATE_LIMIT_REQUESTS=10000
RATE_LIMIT_PERIOD_SECONDS=3600
```

### Performance Tuning

```bash
# Database connection pooling
# Max connections: 20-50 (adjust based on load)

# Backend workers
# Gunicorn: 4-8 workers (CPU count + 1)
# Uvicorn: 4-8 workers

# Frontend
# Enable gzip compression
# Enable cache busting for assets
# Use CDN for static assets
```

---

## Part 10: Monitoring & Debugging

### Health Checks

```bash
# Backend health
curl http://localhost:8000/health

# Database connectivity
curl http://localhost:8000/health | jq .database

# API documentation
open http://localhost:8000/docs
```

### Logging

```bash
# View logs
docker-compose logs -f backend

# Filter by error
docker-compose logs backend | grep ERROR

# Export to file
docker-compose logs backend > logs.txt
```

### Performance Metrics

Monitor via Prometheus (if enabled):

```bash
curl http://localhost:8000/metrics | grep bristol_bus_pulse
```

### Common Issues

#### No vehicles appearing
- Check BODS API key is valid
- Verify GTFS-RT feed URL is accessible
- Check database connection in logs
- Confirm operator codes are correct

#### Delays not calculating
- Ensure GTFS schedule data downloaded successfully
- Check timezone configuration
- Verify Trip Updates feed contains data

#### Map rendering slowly
- Reduce vehicle update frequency
- Limit vehicles to single route
- Check browser performance in DevTools

#### High memory usage
- Reduce snapshot retention period
- Limit historical data queries
- Check for WebSocket connection leaks

---

## Part 11: GTFS-RT Ingestion Details

### Protobuf Parsing

```python
# Vehicle Position parsing
from google.transit import gtfs_realtime_pb2

feed = gtfs_realtime_pb2.FeedMessage()
feed.ParseFromString(protobuf_bytes)

for entity in feed.entity:
    if entity.HasField('vehicle'):
        vehicle = entity.vehicle
        latitude = vehicle.position.latitude
        longitude = vehicle.position.longitude
        bearing = vehicle.position.bearing  # 0-359 degrees
```

### Stop Time Updates

Each trip update contains an array of stop_time_updates:

```python
{
  'stop_id': 'xxx',
  'arrival_delay': 120,  # seconds
  'departure_delay': 120,
  'schedule_relationship': 'SCHEDULED'
}
```

### Frequency

- Updated every 10-30 seconds
- Each update contains current state
- No historical backfill
- Requires continuous polling

### Error Handling

```python
try:
    feed = await fetch_gtfs_rt_feed()
    vehicles = parse_vehicle_positions(feed)
    await db.upsert_vehicles(vehicles)
except TimeoutError:
    log.warning("Feed request timeout")
except ParseError:
    log.error("Failed to parse protobuf")
```

---

## Part 12: Maintenance

### Weekly Tasks

- Monitor disk usage (snapshots/logs)
- Check BODS API status
- Review error logs
- Verify data freshness

### Monthly Tasks

- Clean up old snapshots
- Update GTFS schedule data
- Review performance metrics
- Update dependencies (security patches)

### Annual Tasks

- Full backup/restore test
- Disaster recovery drill
- Architecture review
- Capacity planning

### Backup Strategy

```bash
# Database backup
pg_dump bristol_bus_pulse > backup.sql

# Restore
psql bristol_bus_pulse < backup.sql

# Backup snapshots
cp bristol_snapshots.db bristol_snapshots.db.backup
```

---

## Part 13: Extending the Application

### Adding New Operators

Edit `config.py`:

```python
OPERATOR_CODES=FBUS,MCR,SMC,MCTR
```

Backend will automatically ingest data for all operators.

### Adding New Routes

Routes are automatically discovered from GTFS-RT feeds. No configuration needed.

### Custom Alerts

Extend `processing/delay_calculator.py`:

```python
async def trigger_alert(route_id, severity):
    if severity == "severe_delay":
        await send_notification(f"Route {route_id} severely delayed")
```

### Integration with External Systems

Use REST API endpoints:
- `GET /api/network/overview` - Current network status
- `GET /api/routes/ranked` - Worst routes
- `GET /api/replay/snapshots` - Historical data

---

## Support & Troubleshooting

### Getting Help

- BODS Documentation: https://www.gov.uk/government/collections/bus-open-data-service
- GTFS Reference: https://gtfs.org/
- MapLibre GL Docs: https://maplibre.org/

### Reporting Issues

Include:
- BODS API key (redacted): ****
- Operator code: FBUS
- Timestamp of issue
- Error message from logs
- Network status at time of issue

---

## Architecture Decisions

### Why FastAPI?
- Async-first design for WebSocket connections
- Auto-generated API documentation
- Type safety with Pydantic
- High performance

### Why PostgreSQL + PostGIS?
- Efficient geographic queries for heatmaps
- Built-in indexing for time-series data
- ACID compliance for data integrity
- Mature, stable, well-documented

### Why Next.js?
- Type-safe React components
- Built-in optimization
- Edge deployment options
- Developer experience

### Why MapLibre GL?
- Open source, no vendor lock-in
- Excellent performance with WebGL
- Customizable styling
- Active community

---

**This application is production-ready. No mocks. No approximations. Real data only.**
