// Minimal service worker so the page can be installed as a PWA on Android.
// Network-first; no aggressive caching while the app is still evolving.
const CACHE = "ngtp-web-bt-v18";
const ASSETS = [
    "./",
    "./index.html",
    "./app.js",
    "./style.css",
    "./manifest.webmanifest",
    "./icon.svg",
];

self.addEventListener("install", (event) => {
    event.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)));
    self.skipWaiting();
});

self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))
        )
    );
    self.clients.claim();
});

self.addEventListener("fetch", (event) => {
    const req = event.request;
    event.respondWith(
        fetch(req)
            .then((res) => {
                const copy = res.clone();
                caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => { });
                return res;
            })
            .catch(() => caches.match(req))
    );
});
