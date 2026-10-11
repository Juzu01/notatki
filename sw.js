/* Service worker aplikacji Notatki: tylko powiadomienia z UPeL-a (.github/upel_watch.py wysyła Web Push). Niczego nie zapisuje w pamięci podręcznej.
   Każde powiadomienie zostaje też w historii (IndexedDB „notatki-push”, ostatnie 200), którą aplikacja pokazuje w Notatkach pod przedmiotami. */
self.addEventListener("install", function () { self.skipWaiting(); });
self.addEventListener("activate", function (e) { e.waitUntil(self.clients.claim()); });
function zapisz(d) {   // nigdy nie kończy się błędem – powiadomienie ma się pokazać tak czy inaczej
  return new Promise(function (ok) {
    try {
      var rq = indexedDB.open("notatki-push", 1);
      rq.onupgradeneeded = function () { rq.result.createObjectStore("h", { keyPath: "id", autoIncrement: true }); };
      rq.onerror = function () { ok(); };
      rq.onsuccess = function () {
        var db = rq.result, tx = db.transaction("h", "readwrite"), st = tx.objectStore("h");
        st.add({ t: Date.now(), title: d.title || "UPeL", body: d.body || "", url: d.url || "" });
        var c = st.count();
        c.onsuccess = function () {
          var n = c.result - 200;
          if (n > 0) st.openCursor().onsuccess = function (e) { var cur = e.target.result; if (cur && n-- > 0) { cur.delete(); cur.continue(); } };
        };
        tx.oncomplete = tx.onerror = tx.onabort = function () { db.close(); ok(); };
      };
    } catch (x) { ok(); }
  });
}
self.addEventListener("push", function (e) {
  var d = {};
  try { d = e.data ? e.data.json() : {}; } catch (x) { d = { body: e.data ? e.data.text() : "" }; }
  e.waitUntil(Promise.all([
    self.registration.showNotification(d.title || "UPeL", { body: d.body || "", tag: d.tag || undefined, icon: "icon.png", data: { url: d.url || "/notatki/" } }),
    zapisz(d).then(function () {   // otwarta aplikacja od razu dopisuje je do listy
      return self.clients.matchAll({ type: "window" }).then(function (cs) { cs.forEach(function (c) { c.postMessage({ upel: 1 }); }); });
    })
  ]));
});
self.addEventListener("notificationclick", function (e) {
  e.notification.close();
  var url = (e.notification.data && e.notification.data.url) || "/notatki/";
  e.waitUntil(self.clients.openWindow(url));
});
