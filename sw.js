/* Service worker aplikacji Notatki: tylko powiadomienia z UPeL-a (.github/upel_watch.py wysyła Web Push). Niczego nie zapisuje w pamięci podręcznej. */
self.addEventListener("install", function () { self.skipWaiting(); });
self.addEventListener("activate", function (e) { e.waitUntil(self.clients.claim()); });
self.addEventListener("push", function (e) {
  var d = {};
  try { d = e.data ? e.data.json() : {}; } catch (x) { d = { body: e.data ? e.data.text() : "" }; }
  e.waitUntil(self.registration.showNotification(d.title || "UPeL", { body: d.body || "", tag: d.tag || undefined, icon: "icon.png", data: { url: d.url || "/notatki/" } }));
});
self.addEventListener("notificationclick", function (e) {
  e.notification.close();
  var url = (e.notification.data && e.notification.data.url) || "/notatki/";
  e.waitUntil(self.clients.openWindow(url));
});
