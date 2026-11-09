// Sonar · tarayıcı bildirimleri (service worker). Bildirimleri worker/index.js (Cloudflare) gönderir.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('push', e => {
  let m = {};
  try { m = e.data ? e.data.json() : {}; } catch (_) { m = { title: 'Sonar', body: e.data && e.data.text() }; }
  e.waitUntil(self.registration.showNotification(m.title || 'Sonar', {
    body: m.body || '', tag: m.tag, data: { url: m.url || '/' },
    icon: '/marka/sonar-192.png', badge: '/marka/sonar-badge.png', lang: 'tr'
  }));
});
self.addEventListener('notificationclick', e => {
  e.notification.close();
  const url = (e.notification.data && e.notification.data.url) || '/';
  e.waitUntil(self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(ws => {
    for (const w of ws) if (w.url === url && 'focus' in w) return w.focus();
    return self.clients.openWindow(url);
  }));
});
