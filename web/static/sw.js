self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));

self.addEventListener('push', e => {
    const data = e.data ? e.data.json() : {title: 'Minecraft WebUI', body: ''};
    e.waitUntil(
        self.registration.showNotification(data.title, {
            body: data.body,
            icon: '/pwa/icon',
            badge: '/pwa/icon',
        })
    );
});

self.addEventListener('notificationclick', e => {
    e.notification.close();
    e.waitUntil(clients.openWindow('/'));
});
