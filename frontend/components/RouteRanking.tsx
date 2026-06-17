'use client';

import React, { useEffect, useState } from 'react';
import { routesAPI } from '@/lib/api';
import { getDelayColor } from '@/lib/colors';

interface RouteRankingProps {
  routeId?: string;
}

export default function RouteRanking({ routeId }: RouteRankingProps) {
  const [detail, setDetail] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!routeId) return;

    const fetchDetail = async () => {
      try {
        setLoading(true);
        const data = await routesAPI.getDetail(routeId);
        setDetail(data);
      } catch (error) {
        console.error('Error fetching route detail:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchDetail();
    const interval = setInterval(fetchDetail, 30000); // Update every 30 seconds

    return () => clearInterval(interval);
  }, [routeId]);

  if (!routeId || loading) {
    return (
      <div className="bg-gray-800 rounded-lg shadow-lg p-4">
        <div className="text-gray-400">Loading route details...</div>
      </div>
    );
  }

  if (!detail) {
    return (
      <div className="bg-gray-800 rounded-lg shadow-lg p-4">
        <div className="text-red-400">Route not found</div>
      </div>
    );
  }

  const { statistics, active_vehicles } = detail;

  return (
    <div className="bg-gray-800 rounded-lg shadow-lg p-4 max-w-sm">
      <h3 className="text-lg font-bold text-white mb-3">
        Route {routeId}
      </h3>

      <div className="space-y-3">
        <div className="bg-gray-700 rounded p-3">
          <div className="text-xs text-gray-400">Active Vehicles</div>
          <div className="text-2xl font-bold text-white">
            {statistics.active_vehicles}
          </div>
        </div>

        <div className="bg-gray-700 rounded p-3">
          <div className="text-xs text-gray-400">Average Delay</div>
          <div className="text-2xl font-bold" style={{ color: getDelayColor(statistics.average_delay) }}>
            {statistics.average_delay ? (statistics.average_delay / 60).toFixed(1) : 0} min
          </div>
        </div>

        <div className="bg-gray-700 rounded p-3">
          <div className="text-xs text-gray-400">On Time Percentage</div>
          <div className="text-2xl font-bold text-green-400">
            {statistics.on_time_percentage.toFixed(0)}%
          </div>
        </div>

        <div className="bg-gray-700 rounded p-3">
          <div className="text-xs text-gray-400">Delayed Vehicles</div>
          <div className="text-lg font-bold">
            <span className="text-orange-400">{statistics.delayed_vehicles}</span>
            {' '}
            <span className="text-red-400">{statistics.severely_delayed_vehicles}</span>
          </div>
          <div className="text-xs text-gray-400 mt-1">
            (delayed / severely delayed)
          </div>
        </div>

        {active_vehicles.length > 0 && (
          <div className="mt-4 pt-4 border-t border-gray-600">
            <h4 className="text-sm font-bold text-white mb-2">Vehicles</h4>
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {active_vehicles.slice(0, 5).map((v: any) => (
                <div key={v.vehicle_id} className="bg-gray-700 rounded p-2 text-xs">
                  <div className="text-white font-mono">{v.vehicle_id}</div>
                  {v.delay_seconds && (
                    <div style={{ color: getDelayColor(v.delay_seconds) }}>
                      {(v.delay_seconds / 60).toFixed(1)} min late
                    </div>
                  )}
                </div>
              ))}
              {active_vehicles.length > 5 && (
                <div className="text-xs text-gray-400 p-2">
                  +{active_vehicles.length - 5} more vehicles
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
