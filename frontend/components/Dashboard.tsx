'use client';

import React, { useEffect, useState } from 'react';
import { routesAPI, stopsAPI, networkAPI, type WorstPerformer, type NetworkStatus } from '@/lib/api';
import { getSeverityBadgeColor } from '@/lib/colors';

interface DashboardProps {
  networkStatus: NetworkStatus | null;
  selectedRoute?: string | null;
  selectedStop?: string | null;
  onRouteSelect?: (routeId: string | null) => void;
  onStopSelect?: (stopId: string | null) => void;
}

export default function Dashboard({
  networkStatus,
  selectedRoute,
  selectedStop,
  onRouteSelect,
  onStopSelect,
}: DashboardProps) {
  const [worstRoutes, setWorstRoutes] = useState<WorstPerformer[]>([]);
  const [worstStops, setWorstStops] = useState<WorstPerformer[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchRankings = async () => {
      try {
        setLoading(true);
        const [routes, stops] = await Promise.all([
          routesAPI.getRanked(10, 60),
          stopsAPI.getRanked(10, 60),
        ]);
        setWorstRoutes(routes);
        setWorstStops(stops);
      } catch (error) {
        console.error('Error fetching rankings:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchRankings();
    const interval = setInterval(fetchRankings, 60000); // Update every minute

    return () => clearInterval(interval);
  }, []);

  if (!networkStatus) {
    return (
      <div className="h-full bg-gray-800 flex items-center justify-center">
        <div className="text-gray-400">Loading...</div>
      </div>
    );
  }

  return (
    <div className="h-full bg-gray-800 overflow-y-auto flex flex-col">
      {/* Network Status Header */}
      <div className="sticky top-0 bg-gray-900 border-b border-gray-700 p-4">
        <h2 className="text-xl font-bold text-white mb-4">Network Status</h2>

        <div className="grid grid-cols-2 gap-3">
          <div className="bg-gray-700 rounded p-3">
            <div className="text-xs text-gray-400">Active Buses</div>
            <div className="text-2xl font-bold text-white">
              {networkStatus.total_vehicles}
            </div>
          </div>

          <div className="bg-gray-700 rounded p-3">
            <div className="text-xs text-gray-400">Delayed</div>
            <div className="text-2xl font-bold text-orange-400">
              {networkStatus.delayed_vehicles}
            </div>
          </div>

          <div className="bg-gray-700 rounded p-3">
            <div className="text-xs text-gray-400">Severely Delayed</div>
            <div className="text-2xl font-bold text-red-400">
              {networkStatus.severely_delayed_vehicles}
            </div>
          </div>

          <div className="bg-gray-700 rounded p-3">
            <div className="text-xs text-gray-400">Reliability</div>
            <div className="text-2xl font-bold text-blue-400">
              {networkStatus.network_reliability_score.toFixed(0)}%
            </div>
          </div>
        </div>

        {networkStatus.average_delay && (
          <div className="mt-3 p-3 bg-blue-900 rounded text-sm">
            <div className="text-blue-200">
              Average delay: {(networkStatus.average_delay / 60).toFixed(1)} min
            </div>
          </div>
        )}
      </div>

      {/* Worst Routes */}
      <div className="flex-1 overflow-y-auto p-4">
        <h3 className="text-lg font-bold text-white mb-3">Worst Routes</h3>

        {loading ? (
          <div className="text-gray-400 text-sm">Loading...</div>
        ) : worstRoutes.length === 0 ? (
          <div className="text-gray-400 text-sm">No route data available</div>
        ) : (
          <div className="space-y-2 mb-6">
            {worstRoutes.map((route) => (
              <button
                key={route.id}
                onClick={() => onRouteSelect?.(route.id)}
                className={`w-full p-3 rounded border transition cursor-pointer ${
                  selectedRoute === route.id
                    ? 'bg-blue-900 border-blue-500'
                    : 'bg-gray-700 border-gray-600 hover:border-gray-500'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="font-mono font-bold text-white">
                    Route {route.id}
                  </div>
                  <span className={`text-xs px-2 py-1 rounded-full ${getSeverityBadgeColor(route.severity)}`}>
                    {route.severity.replace(/_/g, ' ')}
                  </span>
                </div>
                {route.average_delay && (
                  <div className="text-xs text-gray-300 mt-1">
                    Avg delay: {(route.average_delay / 60).toFixed(1)} min
                  </div>
                )}
                {route.on_time_percentage && (
                  <div className="text-xs text-gray-300">
                    On time: {route.on_time_percentage.toFixed(0)}%
                  </div>
                )}
              </button>
            ))}
          </div>
        )}

        {/* Worst Stops */}
        <h3 className="text-lg font-bold text-white mb-3">Worst Stops</h3>

        {loading ? (
          <div className="text-gray-400 text-sm">Loading...</div>
        ) : worstStops.length === 0 ? (
          <div className="text-gray-400 text-sm">No stop data available</div>
        ) : (
          <div className="space-y-2">
            {worstStops.map((stop) => (
              <button
                key={stop.id}
                onClick={() => onStopSelect?.(stop.id)}
                className={`w-full p-3 rounded border transition cursor-pointer ${
                  selectedStop === stop.id
                    ? 'bg-blue-900 border-blue-500'
                    : 'bg-gray-700 border-gray-600 hover:border-gray-500'
                }`}
              >
                <div className="flex items-center justify-between">
                  <div className="font-mono font-bold text-white text-sm">
                    Stop {stop.id}
                  </div>
                  <span className={`text-xs px-2 py-1 rounded-full ${getSeverityBadgeColor(stop.severity)}`}>
                    {stop.severity.replace(/_/g, ' ')}
                  </span>
                </div>
                {stop.average_delay && (
                  <div className="text-xs text-gray-300 mt-1">
                    Avg delay: {(stop.average_delay / 60).toFixed(1)} min
                  </div>
                )}
                {stop.on_time_percentage && (
                  <div className="text-xs text-gray-300">
                    On time: {stop.on_time_percentage.toFixed(0)}%
                  </div>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="sticky bottom-0 bg-gray-900 border-t border-gray-700 p-4">
        <div className="text-xs text-gray-500">
          Last updated: {new Date(networkStatus.timestamp).toLocaleTimeString()}
        </div>
      </div>
    </div>
  );
}
