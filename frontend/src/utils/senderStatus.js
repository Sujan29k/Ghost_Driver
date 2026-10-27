const labels = {
  starting: 'Sender connected; starting',
  'loading-models': 'Loading YOLO and prediction models',
  'connecting-carla': 'Connecting to CARLA',
  'spawning-traffic': 'Spawning cars, bicycles and pedestrians',
  'waiting-camera': 'Waiting for the first processed camera frame',
  'camera-unavailable': 'Camera or AI frames stopped; controls stopped',
  error: 'Sender setup failed; check the GPU computer’s bridge logs',
};

export function senderStatus(vehicle) {
  if (vehicle.ready) return vehicle.mode === 'carla' ? 'CARLA ready' : 'Demo ready';
  return labels[vehicle.phase] || labels.starting;
}
