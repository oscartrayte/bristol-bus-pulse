/**
 * Color utilities for visualizing delays and status.
 */

export const DELAY_COLORS = {
  green: '#10b981',  // 0-1 min (on time)
  yellow: '#eab308', // 1-5 min (minor delay)
  orange: '#f97316', // 5-10 min (moderate delay)
  red: '#ef4444',    // 10+ min (severe delay)
  gray: '#6b7280',   // unknown
};

export const INTENSITY_COLORS = {
  0.0: '#10b981',    // green
  0.25: '#eab308',   // yellow
  0.5: '#f97316',    // orange
  0.75: '#dc2626',   // dark red
  1.0: '#7f1d1d',    // dark burgundy
};

export function getDelayColor(delaySeconds?: number): string {
  if (delaySeconds === null || delaySeconds === undefined) {
    return DELAY_COLORS.gray;
  }

  if (delaySeconds <= 60) {
    return DELAY_COLORS.green;
  } else if (delaySeconds <= 300) {
    return DELAY_COLORS.yellow;
  } else if (delaySeconds <= 600) {
    return DELAY_COLORS.orange;
  } else {
    return DELAY_COLORS.red;
  }
}

export function getIntensityColor(intensity: number): string {
  if (intensity <= 0.1) return '#10b981';
  if (intensity <= 0.3) return '#eab308';
  if (intensity <= 0.5) return '#f97316';
  if (intensity <= 0.7) return '#dc2626';
  return '#7f1d1d';
}

export function formatDelay(delaySeconds: number): string {
  if (delaySeconds < 0) {
    return `${Math.abs(delaySeconds) / 60 | 0}m early`;
  }
  const minutes = delaySeconds / 60 | 0;
  const seconds = delaySeconds % 60 | 0;
  return minutes > 0 ? `${minutes}m ${seconds}s late` : `${seconds}s late`;
}

export function getSeverity(delaySeconds?: number): string {
  if (!delaySeconds) return 'unknown';
  if (delaySeconds <= 60) return 'on_time';
  if (delaySeconds <= 300) return 'minor_delay';
  if (delaySeconds <= 600) return 'moderate_delay';
  return 'severe_delay';
}

export function getSeverityBadgeColor(severity: string): string {
  switch (severity) {
    case 'on_time':
      return 'bg-green-100 text-green-800';
    case 'minor_delay':
      return 'bg-yellow-100 text-yellow-800';
    case 'moderate_delay':
      return 'bg-orange-100 text-orange-800';
    case 'severe_delay':
      return 'bg-red-100 text-red-800';
    default:
      return 'bg-gray-100 text-gray-800';
  }
}
