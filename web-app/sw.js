// Minimal service worker so the page can be installed as a PWA on Android.
// Network-first; no aggressive caching while the app is still evolving.
// CACHE is stamped by tools/build_programs.py with the current git short SHA,
// so each CI deploy gets a fresh cache namespace and the SW activate step
// purges the previous one. The fallback "dev" name is used when running
// locally without the build step.
const CACHE = "ngtp-0b160be1";
const ASSETS = [
    "./",
    "./index.html",
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
    // Force a real network hit (bypass the browser HTTP cache) so newly
    // deployed app.js / style.css are picked up immediately. Fall back to
    // the SW cache only if the network is unreachable.
    event.respondWith(
        fetch(req, { cache: "no-store" })
            .then((res) => {
                const copy = res.clone();
                caches.open(CACHE).then((c) => c.put(req, copy)).catch(() => { });
                return res;
            })
            .catch(() => caches.match(req))
    );
});
