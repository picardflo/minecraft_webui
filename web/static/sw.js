// Minimal service worker — enables PWA installability without caching
// No cache: this is a real-time dashboard, stale data would be misleading
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
