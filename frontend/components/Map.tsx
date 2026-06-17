'use client';

import React, { useEffect, useRef, useState, useCallback } from 'react';
import maplibregl from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { vehiclesAPI, type LiveVehicle, type HeatmapCell } from '@/lib/api';
import { getDelayColor } from '@/lib/colors';

interface MapProps {
  selectedRoute?: string | null;
  selectedStop?: string | null;
  onRouteSelect?: (routeId: string | null) => void;
  onStopSelect?: (stopId: string | null) => void;
}

export default function Map({
  selectedRoute,
  selectedStop,
  onRouteSelect,
  onStopSelect,
}: MapProps) {
  const mapContainer = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const vehicleMarkersRef = useRef<Map<string, maplibregl.Marker>>(new Map());
  const [isLoading, setIsLoading] = useState(true);

  // Initialize map
  useEffect(() => {
    if (!mapContainer.current) return;

    map.current = new maplibregl.Map({
      container: mapContainer.current,
      style: 'https://demotiles.maplibre.org/style.json', // Open source style
      center: [-2.5879, 51.4545], // Bristol coordinates
      zoom: 11,
      pitch: 0,
      bearing: 0,
    });

    map.current.on('load', () => {
      setIsLoading(false);

      // Add vehicle positions layer
      if (map.current) {
        map.current.addSource('vehicles', {
          type: 'geojson',
          data: {
            type: 'FeatureCollection',
            features: [],
          },
        });

        // Vehicle points layer
        map.current.addLayer({
          id: 'vehicles-points',
          type: 'circle',
          source: 'vehicles',
          paint: {
            'circle-radius': 6,
            'circle-color': [
              'case',
              ['boolean', ['feature-state', 'hover'], false],
              '#ffffff',
              ['get', 'color'],
            ],
            'circle-stroke-width': 1,
            'circle-stroke-color': '#ffffff',
            'circle-opacity': 0.8,
          },
        });

        // Add stop layer
        map.current.addSource('stops', {
          type: 'geojson',
          data: {
            type: 'FeatureCollection',
            features: [],
          },
        });

        map.current.addLayer({
          id: 'stops-points',
          type: 'circle',
          source: 'stops',
          paint: {
            'circle-radius': 4,
            'circle-color': '#60a5fa',
            'circle-opacity': 0.5,
          },
        });

        // Heatmap layer
        map.current.addSource('heatmap', {
          type: 'geojson',
          data: {
            type: 'FeatureCollection',
            features: [],
          },
        });

        map.current.addLayer(
          {
            id: 'heatmap-layer',
            type: 'heatmap',
            source: 'heatmap',
            paint: {
              'heatmap-weight': ['interpolate', ['linear'], ['get', 'intensity'], 0, 0, 1, 1],
              'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 0, 1, 9, 3],
              'heatmap-color': [
                'interpolate',
                ['linear'],
                ['heatmap-density'],
                0,
                'rgba(16, 185, 129, 0)',
                0.2,
                'rgba(234, 179, 8, 0.5)',
                0.4,
                'rgba(249, 115, 22, 0.7)',
                0.6,
                'rgba(239, 68, 68, 0.8)',
                1,
                'rgba(127, 29, 29, 1)',
              ],
              'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 0, 2, 9, 20],
              'heatmap-opacity': ['interpolate', ['linear'], ['zoom'], 7, 1, 9, 0.5],
            },
          },
          'water',
        );
      }
    });

    return () => {
      // Cleanup is handled by MapLibre
    };
  }, []);

  // Update vehicle positions
  useEffect(() => {
    const updateVehicles = async () => {
      try {
        const vehicles = await vehiclesAPI.getLive(selectedRoute || undefined);

        if (!map.current) return;

        const features = vehicles.map((v) => ({
          type: 'Feature' as const,
          geometry: {
            type: 'Point' as const,
            coordinates: [v.position.longitude, v.position.latitude],
          },
          properties: {
            vehicle_id: v.vehicle_id,
            route_id: v.route_id,
            delay_seconds: v.delay_seconds,
            color: getDelayColor(v.delay_seconds),
            heading: v.heading,
          },
        }));

        const vehiclesSource = map.current.getSource('vehicles');
        if (vehiclesSource && vehiclesSource.type === 'geojson') {
          vehiclesSource.setData({
            type: 'FeatureCollection',
            features,
          });
        }

        // Update markers
        vehicles.forEach((v) => {
          const markerId = v.vehicle_id;
          const color = getDelayColor(v.delay_seconds);

          // Create or update marker (simplified - in production would use custom markers with rotation)
          if (!vehicleMarkersRef.current.has(markerId)) {
            const el = document.createElement('div');
            el.className = 'vehicle-marker';
            el.style.backgroundColor = color;
            el.style.width = '24px';
            el.style.height = '24px';
            el.style.borderRadius = '50%';
            el.style.cursor = 'pointer';
            el.title = `${v.route_id} - ${v.vehicle_id}`;

            const marker = new maplibregl.Marker(el)
              .setLngLat([v.position.longitude, v.position.latitude])
              .addTo(map.current!);

            vehicleMarkersRef.current.set(markerId, marker);

            el.addEventListener('click', () => {
              onRouteSelect?.(v.route_id);
            });
          } else {
            const marker = vehicleMarkersRef.current.get(markerId);
            if (marker) {
              marker.setLngLat([v.position.longitude, v.position.latitude]);
            }
          }
        });
      } catch (error) {
        console.error('Error fetching vehicles:', error);
      }
    };

    updateVehicles();
    const interval = setInterval(updateVehicles, 10000); // Update every 10 seconds

    return () => clearInterval(interval);
  }, [selectedRoute, onRouteSelect]);

  return (
    <div className="relative w-full h-full">
      <div
        ref={mapContainer}
        className="w-full h-full"
        style={{ position: 'relative' }}
      />

      {isLoading && (
        <div className="absolute inset-0 bg-black bg-opacity-50 flex items-center justify-center">
          <div className="text-white text-xl">Loading map...</div>
        </div>
      )}

      {/* Map controls overlay */}
      <div className="absolute top-4 right-4 z-10 bg-gray-800 rounded-lg p-2 shadow-lg">
        <button
          onClick={() => map.current?.fitBounds([[-2.8, 51.3], [-2.4, 51.6]])}
          className="px-3 py-2 text-sm text-white bg-gray-700 rounded hover:bg-gray-600"
        >
          Fit View
        </button>
      </div>
    </div>
  );
}
