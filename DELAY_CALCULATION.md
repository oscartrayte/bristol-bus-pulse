# Delay Calculation Methodology

## Overview

Bristol Bus Pulse calculates delays using real GTFS-RT data, with no estimation or approximation.

## Data Sources

### 1. GTFS Schedule (Static)
- **Source**: BODS (Bus Open Data Service)
- **Frequency**: Updated daily
- **Content**: Route definitions, stop sequences, scheduled times
- **File**: stop_times.txt in GTFS ZIP

### 2. GTFS-RT Trip Updates (Real-time)
- **Source**: BODS API - Trip Updates feed
- **Frequency**: Updated every 10-30 seconds
- **Content**: Current delays, stop predictions
- **Format**: Protocol Buffers (binary)

### 3. GTFS-RT Vehicle Positions (Real-time)
- **Source**: BODS API - Vehicle Positions feed
- **Frequency**: Updated every 10-30 seconds
- **Content**: Lat/lon, heading, current stop
- **Format**: Protocol Buffers (binary)

## Calculation

### For Individual Vehicle

```
delay_seconds = predicted_arrival_time - scheduled_arrival_time
```

### Data Points

**From GTFS Schedule** (stop_times.txt):
- trip_id
- stop_id
- stop_sequence
- scheduled_arrival_time (HH:MM:SS format)

**From GTFS-RT Trip Update**:
- trip_id (matches schedule)
- current_stop_sequence (which stop we're at)
- arrival.delay (seconds, can be negative)
- departure.delay (seconds, can be negative)

### Example

```
Trip 12345, Route 1, Stop 'Central Station'

Scheduled arrival: 10:30:00 (39000 seconds since midnight)
GTFS-RT reports delay: +120 seconds
Calculated arrival: 10:32:00 (39120 seconds since midnight)

delay_seconds = 120 (2 minutes late)
```

### Negative Delays

If `delay_seconds < 0`, vehicle is early:
- -60 means 1 minute early
- Treated as on-time (≤60 seconds threshold)

## Aggregation Levels

### Level 1: Per Vehicle (Instant)
Used for:
- Vehicle markers on map
- Vehicle detail popup
- Real-time tracking

```python
vehicle.delay_seconds = int(trip_update.delay)
```

### Level 2: Per Route (Rolling Window)
Calculated every 5 minutes for last 1 hour window:

```python
def calculate_route_delay(route_id, window_start, window_end):
    vehicles = db.query(Vehicle).filter(
        Vehicle.route_id == route_id,
        Vehicle.timestamp.between(window_start, window_end)
    )
    
    delays = [v.delay_seconds for v in vehicles if v.delay_seconds]
    
    return {
        'average_delay': mean(delays),
        'median_delay': median(delays),
        'on_time_percentage': sum(1 for d in delays if d ≤ 60) / len(delays) * 100,
        'delayed_vehicles': sum(1 for d in delays if d > 60),
        'severely_delayed': sum(1 for d in delays if d > 600),
    }
```

### Level 3: Per Stop (Rolling Window)
Calculated every 5 minutes for last 1 hour window:

```python
def calculate_stop_delay(stop_id, window_start, window_end):
    trip_updates = db.query(TripUpdate).filter(
        TripUpdate.timestamp.between(window_start, window_end)
    )
    
    arrival_delays = []
    for update in trip_updates:
        for stu in update.stop_time_updates:
            if stu['stop_id'] == stop_id:
                arrival_delays.append(stu['arrival_delay'])
    
    return {
        'average_arrival_delay': mean(arrival_delays),
        'on_time_percentage': sum(1 for d in arrival_delays if d ≤ 60) / len(arrival_delays) * 100,
        'reliability_score': max(0, 100 - (mean(arrival_delays) / 60)),
    }
```

### Level 4: Network (Aggregate)
Calculated every 5 minutes across all vehicles:

```python
def calculate_network_delay():
    all_vehicles = db.query(Vehicle).filter(
        Vehicle.timestamp >= now() - timedelta(hours=1)
    )
    
    delays = [v.delay_seconds for v in all_vehicles if v.delay_seconds]
    
    return {
        'total_vehicles': len(all_vehicles),
        'delayed_vehicles': sum(1 for d in delays if d > 60),
        'average_delay': mean(delays),
        'network_reliability': 100 - (mean(delays) / 600),
    }
```

## Classification

Delays are categorized for visualization:

```python
def get_delay_color(delay_seconds):
    if delay_seconds is None:
        return 'gray'      # Unknown
    elif delay_seconds <= 60:
        return 'green'     # 0-1 minute
    elif delay_seconds <= 300:
        return 'yellow'    # 1-5 minutes
    elif delay_seconds <= 600:
        return 'orange'    # 5-10 minutes
    else:
        return 'red'       # 10+ minutes
```

## Reliability Score

Calculated as percentage of arrivals within scheduled time:

```python
reliability_score = (on_time_count / total_arrivals) * 100
```

Capped at 100% even if some early arrivals.

## Heatmap Intensity

Geographic intensity normalized to delay:

```python
intensity = min(1.0, average_cell_delay / 600)
```

Where:
- 0.0 = no delay (green)
- 0.5 = 5 minute average delay (orange)
- 1.0 = 10+ minute average delay (red)

## Accuracy Considerations

### Source of Truth
- GTFS-RT Trip Updates are the authoritative source
- Schedule times are fallback if live data unavailable
- Vehicle positions are for visualization only

### Edge Cases

**Missing Delay Data**:
- Some vehicles don't report trip updates
- Treated as "unknown" - not included in calculations
- Dashboard shows count of vehicles with/without data

**Timezone**:
- All times stored in UTC internally
- Displayed in Europe/London timezone
- GTFS times converted to UTC on import

**Service Changes**:
- Extra trips added mid-day not in static GTFS
- Trip Updates handles real-time service changes
- Schedule updates downloaded daily

**Cancelled Trips**:
- GTFS-RT marks cancelled in schedule_relationship
- Not included in "on-time" calculation
- Counted separately as "missed service"

## Data Quality

### Validation

All incoming data validated:

```python
if not (vehicle.latitude and vehicle.longitude):
    skip_vehicle()  # Invalid position

if vehicle.delay_seconds > 3600:
    flag_as_outlier()  # More than 1 hour (likely data error)

if not trip_update.trip_id:
    skip_update()  # No trip reference
```

### Freshness

- Real-time data > 5 minutes old excluded from calculations
- Vehicles without position in last 10 minutes removed from map
- Historical data retained for 30 days

## Performance

### Calculation Frequency

- Per-vehicle: Continuous (on data arrival)
- Per-route: Every 5 minutes
- Per-stop: Every 5 minutes
- Network: Every 5 minutes
- Heatmap: Every 10 seconds

### Database Queries

```sql
-- Route statistics (indexed on route_id, timestamp)
SELECT route_id, AVG(delay_seconds), PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY delay_seconds)
FROM vehicles
WHERE route_id = $1 AND timestamp BETWEEN $2 AND $3
GROUP BY route_id;

-- Heatmap (indexed on position, timestamp)
SELECT ST_AsGeoJSON(position), COUNT(*), AVG(delay_seconds)
FROM vehicles
WHERE timestamp > now() - interval '30 minutes'
GROUP BY ST_SnapToGrid(position, 0.005)  -- ~500m grid
```

### Caching

- Route statistics cached for 5 minutes
- Stop statistics cached for 5 minutes
- Network metrics cached for 1 minute
- Heatmap cached for 2 minutes

## Validation

All calculations validated against expected ranges:

```python
assert average_delay >= -3600  # Can't be more than 1hr early
assert average_delay <= 3600   # Should rarely exceed 1hr late
assert on_time_percentage >= 0 and <= 100
assert reliability_score >= 0 and <= 100
assert heatmap_intensity >= 0 and <= 1.0
```

## History & Trends

### Snapshots

Network state captured every 5 minutes:
- Vehicle positions
- Route statistics
- Stop statistics
- Heatmap data
- Timestamp

Stored in SQLite for replay functionality.

### Historical Queries

Can retrieve delay trends:

```python
# Delay over time
SELECT timestamp, AVG(delay_seconds)
FROM historical_vehicle_positions
WHERE route_id = 'R1' AND timestamp > now() - interval '24 hours'
GROUP BY DATE_TRUNC('hour', timestamp)
ORDER BY timestamp;
```

---

**All calculations use real data from Bus Open Data Service.**
**No estimation. No assumptions. Pure calculation from live feeds.**
