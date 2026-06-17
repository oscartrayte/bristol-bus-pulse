'use client';

import React, { useEffect, useState } from 'react';
import { replayAPI } from '@/lib/api';
import type { ReplaySnapshot } from '@/lib/api';

export default function ReplayControls() {
  const [snapshots, setSnapshots] = useState<ReplaySnapshot[]>([]);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentSnapshotIndex, setCurrentSnapshotIndex] = useState(0);
  const [playbackSpeed, setPlaybackSpeed] = useState(1);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchSnapshots = async () => {
      try {
        setLoading(true);
        const data = await replayAPI.getSnapshots(24); // Last 24 hours
        setSnapshots(data.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()));
      } catch (error) {
        console.error('Error fetching snapshots:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchSnapshots();
  }, []);

  useEffect(() => {
    if (!isPlaying) return;

    const interval = setInterval(() => {
      setCurrentSnapshotIndex((prev) => {
        if (prev >= snapshots.length - 1) {
          setIsPlaying(false);
          return prev;
        }
        return prev + 1;
      });
    }, 1000 / playbackSpeed);

    return () => clearInterval(interval);
  }, [isPlaying, playbackSpeed, snapshots.length]);

  const currentSnapshot = snapshots[currentSnapshotIndex];

  return (
    <div className="bg-gray-800 rounded-lg shadow-lg p-4 w-96">
      <h3 className="text-lg font-bold text-white mb-4">Network Replay</h3>

      {loading ? (
        <div className="text-gray-400">Loading snapshots...</div>
      ) : snapshots.length === 0 ? (
        <div className="text-gray-400">No replay data available</div>
      ) : (
        <div className="space-y-4">
          {/* Timeline */}
          <div>
            <label className="text-sm text-gray-400 block mb-2">
              Timeline ({currentSnapshotIndex + 1} / {snapshots.length})
            </label>
            <input
              type="range"
              min="0"
              max={snapshots.length - 1}
              value={currentSnapshotIndex}
              onChange={(e) => setCurrentSnapshotIndex(parseInt(e.target.value))}
              className="w-full"
            />
          </div>

          {currentSnapshot && (
            <div className="bg-gray-700 rounded p-3 space-y-2 text-sm">
              <div>
                <span className="text-gray-400">Time:</span>
                <span className="text-white ml-2">
                  {new Date(currentSnapshot.timestamp).toLocaleTimeString()}
                </span>
              </div>
              <div>
                <span className="text-gray-400">Vehicles:</span>
                <span className="text-white ml-2">{currentSnapshot.vehicle_count}</span>
              </div>
              <div>
                <span className="text-gray-400">Delayed:</span>
                <span className="text-orange-400 ml-2">{currentSnapshot.delayed_vehicles}</span>
              </div>
              <div>
                <span className="text-gray-400">Severely Delayed:</span>
                <span className="text-red-400 ml-2">{currentSnapshot.severely_delayed_vehicles}</span>
              </div>
              {currentSnapshot.average_delay && (
                <div>
                  <span className="text-gray-400">Avg Delay:</span>
                  <span className="text-white ml-2">
                    {(currentSnapshot.average_delay / 60).toFixed(1)} min
                  </span>
                </div>
              )}
            </div>
          )}

          {/* Controls */}
          <div className="flex gap-2">
            <button
              onClick={() => setIsPlaying(!isPlaying)}
              className="flex-1 px-3 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 transition text-sm font-medium"
            >
              {isPlaying ? 'Pause' : 'Play'}
            </button>
            <button
              onClick={() => setCurrentSnapshotIndex(0)}
              className="px-3 py-2 bg-gray-700 text-white rounded hover:bg-gray-600 transition text-sm"
            >
              Reset
            </button>
          </div>

          {/* Playback speed */}
          <div>
            <label className="text-sm text-gray-400 block mb-2">
              Speed: {playbackSpeed}x
            </label>
            <select
              value={playbackSpeed}
              onChange={(e) => setPlaybackSpeed(parseFloat(e.target.value))}
              className="w-full px-2 py-1 bg-gray-700 text-white rounded text-sm"
            >
              <option value="0.5">0.5x (Slow)</option>
              <option value="1">1x (Normal)</option>
              <option value="2">2x (Fast)</option>
              <option value="4">4x (Very Fast)</option>
            </select>
          </div>
        </div>
      )}
    </div>
  );
}
