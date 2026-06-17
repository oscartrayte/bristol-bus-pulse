'use client';

import React, { useEffect, useState } from 'react';
import Map from '@/components/Map';
import Dashboard from '@/components/Dashboard';
import RouteRanking from '@/components/RouteRanking';
import ReplayControls from '@/components/ReplayControls';
import { networkAPI } from '@/lib/api';
import type { NetworkStatus } from '@/lib/api';

export default function Home() {
  const [networkStatus, setNetworkStatus] = useState<NetworkStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [showReplay, setShowReplay] = useState(false);
  const [selectedRoute, setSelectedRoute] = useState<string | null>(null);
  const [selectedStop, setSelectedStop] = useState<string | null>(null);

  // Fetch network overview
  useEffect(() => {
    const fetchData = async () => {
      try {
        setIsLoading(true);
        const overview = await networkAPI.getOverview();
        setNetworkStatus(overview.status);
      } catch (error) {
        console.error('Error fetching network status:', error);
      } finally {
        setIsLoading(false);
      }
    };

    fetchData();

    // Poll every 30 seconds
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex h-screen bg-gray-900">
      {/* Main map */}
      <div className="flex-1 relative">
        <Map
          selectedRoute={selectedRoute}
          selectedStop={selectedStop}
          onRouteSelect={setSelectedRoute}
          onStopSelect={setSelectedStop}
        />

        {/* Top-left controls */}
        <div className="absolute top-4 left-4 z-10 space-y-4">
          <button
            onClick={() => setShowReplay(!showReplay)}
            className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition"
          >
            {showReplay ? 'Close Replay' : 'View Replay'}
          </button>
        </div>

        {/* Replay controls */}
        {showReplay && (
          <div className="absolute bottom-4 left-4 z-10">
            <ReplayControls />
          </div>
        )}
      </div>

      {/* Right sidebar - Dashboard */}
      <div className="w-96 border-l border-gray-700 overflow-y-auto">
        <Dashboard
          networkStatus={networkStatus}
          selectedRoute={selectedRoute}
          selectedStop={selectedStop}
          onRouteSelect={setSelectedRoute}
          onStopSelect={setSelectedStop}
        />
      </div>

      {/* Routes ranking panel */}
      {selectedRoute && (
        <div className="absolute bottom-4 right-4 z-10 max-w-sm">
          <RouteRanking routeId={selectedRoute} />
        </div>
      )}
    </div>
  );
}
