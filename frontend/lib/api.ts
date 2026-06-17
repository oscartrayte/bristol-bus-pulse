/**
 * API utilities for Bristol Bus Pulse frontend.
 */
import axios, { AxiosInstance } from 'axios';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const api: AxiosInstance = axios.create({
  baseURL: `${API_URL}/api`,
  timeout: 10000,
});

// Types
export interface Position {
  latitude: number;
  longitude: number;
}

export interface LiveVehicle {
  vehicle_id: string;
  route_id: string;
  trip_id: string;
  operator_code: string;
  position: Position;
  heading?: number;
  delay_seconds?: number;
  next_stop_id?: string;
  occupancy_status?: string;
  timestamp: string;
}

export interface RouteStatistics {
  route_id: string;
  operator_code: string;
  active_vehicles: number;
  average_delay?: number;
  median_delay?: number;
  on_time_percentage: number;
  delayed_vehicles: number;
  severely_delayed_vehicles: number;
  window_start: string;
  window_end: string;
}

export interface StopDetail {
  stop_id: string;
  stop_code?: string;
  stop_name: string;
  position: Position;
  routes_serving: number;
  scheduled_arrivals: number;
  actual_arrivals: number;
  average_arrival_delay?: number;
  on_time_percentage: number;
  reliability_score: number;
  wheelchair_accessible?: boolean;
}

export interface NetworkStatus {
  timestamp: string;
  total_vehicles: number;
  delayed_vehicles: number;
  severely_delayed_vehicles: number;
  affected_routes: number;
  affected_stops: number;
  average_delay?: number;
  network_reliability_score: number;
}

export interface HeatmapCell {
  latitude: number;
  longitude: number;
  intensity: number;
  vehicle_count: number;
  delayed_vehicles: number;
  average_delay_seconds: number;
  affected_routes: string[];
}

export interface WorstPerformer {
  id: string;
  name?: string;
  average_delay?: number;
  on_time_percentage?: number;
  affected_count: number;
  severity: string;
}

export interface ReplaySnapshot {
  timestamp: string;
  vehicle_count: number;
  delayed_vehicles: number;
  severely_delayed_vehicles: number;
  affected_routes: number;
  average_delay?: number;
}

// API Functions

export const vehiclesAPI = {
  getLive: async (routeId?: string): Promise<LiveVehicle[]> => {
    const response = await api.get('/vehicles/live', {
      params: { route_id: routeId },
    });
    return response.data;
  },
};

export const routesAPI = {
  getRanked: async (limit: number = 10, minutes: number = 60): Promise<WorstPerformer[]> => {
    const response = await api.get('/routes/ranked', {
      params: { limit, minutes },
    });
    return response.data;
  },

  getDetail: async (routeId: string) => {
    const response = await api.get(`/routes/${routeId}`);
    return response.data;
  },
};

export const stopsAPI = {
  getRanked: async (limit: number = 10, minutes: number = 60): Promise<WorstPerformer[]> => {
    const response = await api.get('/stops/ranked', {
      params: { limit, minutes },
    });
    return response.data;
  },

  getDetail: async (stopId: string): Promise<StopDetail> => {
    const response = await api.get(`/stops/${stopId}`);
    return response.data;
  },

  getArrivals: async (stopId: string, limit: number = 20) => {
    const response = await api.get(`/stops/${stopId}/arrivals`, {
      params: { limit },
    });
    return response.data;
  },
};

export const networkAPI = {
  getOverview: async () => {
    const response = await api.get('/network/overview');
    return response.data;
  },
};

export const replayAPI = {
  getSnapshots: async (hours: number = 24): Promise<ReplaySnapshot[]> => {
    const response = await api.get('/replay/snapshots', {
      params: { hours },
    });
    return response.data;
  },

  getDetail: async (timestamp: string) => {
    const response = await api.get(`/replay/snapshots/${timestamp}`);
    return response.data;
  },
};

// WebSocket
export const createWebSocketConnection = (path: string = '/ws/live') => {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${window.location.host}${API_URL.replace(/^https?:\/\/[^/]+/, '')}/ws/live`;
  return new WebSocket(wsUrl);
};

export default api;
