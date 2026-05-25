# NGTP Web Bluetooth PoC

Statisk webapp der forbinder direkte til Puller Master via Web Bluetooth — uden
bridge_client.py og uden FastAPI-server. Tænkt som første skridt mod en
Android-only setup hvor en telefon kører hele kontrolpanelet.

## Hvad den kan (PoC)

- Forbinder til en hub hvis navn starter med `Puller` via Pybricks BLE-profilen.
- Sender `S <score>\n` til hubbens stdin via Pybricks `WRITE_STDIN` kommando.
- Modtager og viser hub stdout (linje-baseret) i en log.
- Kan installeres som PWA på Android via "Føj til startskærm".

## Hvad den IKKE kan (endnu)

- Den uploader **ikke** `master_broadcaster.py` til hubben. Programmet skal
  allerede være startet — fx via Pybricks Code, eller én gang med den eksisterende
  `bridge_client.py` der lukker BLE igen bagefter.
- Multi-hub multiplex (sled, displays) er ikke implementeret.
- Distance / ack-flow modtages som plain stdout — endnu ikke parset til UI-state.

## Kør lokalt

Web Bluetooth kræver et **sikkert kontekst** — HTTPS eller `http://localhost`.

### Variant A: via PC over LAN til telefon (HTTPS påkrævet)

Lettest hvis du bare vil teste fra PC'en selv:

```powershell
cd web-app
python -m http.server 5500
```

Åbn `http://localhost:5500` i Chrome på samme PC. Web Bluetooth virker fordi det
er localhost. Fra telefon på samme WiFi vil `http://<pc-ip>:5500` IKKE virke
fordi Chrome kræver HTTPS — brug i stedet Variant B.

### Variant B: deploy til GitHub Pages

1. Commit alt i `web-app/` plus `.github/workflows/pages.yml`.
2. Push til main:
   ```powershell
   git add web-app .github/workflows/pages.yml
   git commit -m "Add Web Bluetooth PoC"
   git push
   ```
3. På GitHub: **Settings → Pages → Source: GitHub Actions**.
4. Vent på første workflow-kørsel. URL'en vises i workflow-resultatet og under
   Settings → Pages — typisk `https://<bruger>.github.io/<repo>/web-app/` eller
   med custom subpath afhængigt af repo-opsætning.
5. Åbn URL'en i Chrome på Android, tryk menu → "Føj til startskærm".

## Test-procedure

1. Sørg for at `master_broadcaster.py` kører på Puller Master. Hurtigste vej:
   start den eksisterende bridge én gang og luk den når hubben siger "ready" i
   loggen — programmet bliver kørende på hubben efter Python-bridgen lukkes.
2. Åbn web-appen, tryk **Forbind til Puller Master**.
3. Chrome viser device-picker; vælg din hub.
4. Indtast en score og tryk **Send Score**.
5. Score-displayet bør reagere; hub stdout vises i loggen.

## Næste skridt for at erstatte bridge_client.py helt

1. **Upload+kør programmer fra browseren**: Pybricks BLE understøtter
   `WRITE_USER_PROGRAM_META` + `WRITE_USER_RAM` + `START_USER_PROGRAM`. Kræver
   at vi enten precompilerer `.mpy` (via `mpy-cross`) og committer binæren, eller
   bundler en WebAssembly-build af `mpy-cross` i appen.
2. **Multi-hub**: parallelle BLE-forbindelser til sled + displays. Samme
   protocol-parsing som bridge_client (D / A / ASSIGN linjer).
3. **Persistens**: state og historik i IndexedDB i stedet for FastAPI.
4. **Wake lock**: holde skærmen tændt under et træk (`navigator.wakeLock`).

## BLE-detaljer

- Service UUID: `c5f50001-8280-46da-89f4-6d8051e4aeef` (Pybricks)
- Command/Event characteristic: `c5f50002-8280-46da-89f4-6d8051e4aeef`
- Frame: `[cmd_id, ...payload]`. `WRITE_STDIN = 0x06`.
- Stdout kommer som notifications hvor byte 0 = event_id (`0x01 = WRITE_STDOUT`)
  og resten er rå bytes — vi splitter på `\n` i klienten.

Reference: https://github.com/pybricks/technical-info/blob/master/pybricks-ble-profile.md
