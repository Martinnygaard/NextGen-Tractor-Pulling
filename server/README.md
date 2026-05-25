# PC Server (Phone Interface)

FastAPI webserver til scoreboardet. Kør den på din PC og brug telefonen
som interface via browser på samme Wi-Fi.

## 1) Start serveren på PC (Windows PowerShell)

```powershell
cd server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Serveren lytter nu på port 8000 på hele dit lokale netværk.

## 2) Find PC'ens lokale IP

Kør:

```powershell
ipconfig
```

Brug IPv4-adressen på dit aktive netkort (typisk noget som `192.168.x.x`).

## 3) Åbn fra Samsung-telefonen

På telefonen (samme Wi-Fi):

```text
http://DIN_PC_IP:8000
```

Eksempel:

```text
http://192.168.1.42:8000
```

## 4) Hvis telefonen ikke kan forbinde

- Tillad Python/uvicorn i Windows Firewall på private netværk.
- Bekræft at PC og telefon er på samme Wi-Fi.
- Test lokalt på PC først: `http://localhost:8000`.

## API (hurtig test)

- `GET /api/health` -> server alive
- `GET /api/state` -> nuværende scoreboard-state
- `GET /api/live` -> samlet live-state til dashboard
- `GET /api/history` -> historikliste
- `POST /api/history` -> tilføj historikpost (`tractor`, `result_m`)
- `DELETE /api/history` -> ryd historik
- `GET /api/distance` -> læs distance
- `POST /api/distance/{distance}` -> sæt distance (0..100)
- `POST /api/score/{score}` -> sæt score
- `POST /api/full-pull` -> vis FULL PULL
- `POST /api/reset` -> nulstil

## Remote command queue (til bridge/hardware)

Web-GUI sender kommandoer til køer for `sled` og `scoreboard`.
En bridge-klient kan hente og kvittere dem i rækkefølge:

- `POST /api/remote/sled` -> enqueue sled command
- `POST /api/remote/scoreboard` -> enqueue scoreboard command
- `GET /api/remote/{target}/next?after_id=...` -> næste kommando efter id
- `GET /api/remote/{target}/pending?after_id=...` -> batch af ventende kommandoer
- `POST /api/remote/{target}/ack/{id}` -> kvitter kommando(er) op til id

Typisk loop for bridge:

1. Læs `next` med seneste kendte id.
2. Udfør kommando på hardware.
3. Send `ack` med kommando-id.
4. Gentag.

## Bridge-klient (PC)

Der er nu en simpel bridge-klient i [server/bridge_client.py](server/bridge_client.py),
som poller kommando-køen og sender `ack` automatisk.

Start (nyt terminalvindue):

```powershell
cd server
python bridge_client.py
```

Miljovariabler:

- `NGTP_SERVER_URL` (default `http://127.0.0.1:8000`)
- `NGTP_BRIDGE_POLL_SECONDS` (default `0.25`)
- `NGTP_BRIDGE_MODE`:
	- `loopback` (default): scoreboard-kommandoer afspejles i server-state
	- `log`: logger kun kommandoer (ingen state-opdatering)
	- `pybricks`: sender scoreboard-kommandoer live til en kørende `master_broadcaster.py` hub via Pybricks BLE stdin
- `NGTP_SCOREBOARD_HUB` (hub-navn eller BLE-adresse til scoreboard/master hub)
- `NGTP_SLED_HUB` (reserveret til kommende sled-adapter)
- `NGTP_PYBRICKS_TIMEOUT_SECONDS` (default `20`)

Eksempel (PowerShell):

```powershell
cd server
$env:NGTP_BRIDGE_MODE = "pybricks"
$env:NGTP_SCOREBOARD_HUB = "DitHubNavn"
python bridge_client.py
```

Bemærk: nuværende bridge er klar til command-flow og integrationstest.
I `pybricks` mode er scoreboard-control hardware-live nu.
Denne mode forventer, at hubben allerede kører [hubs/master_broadcaster.py](hubs/master_broadcaster.py).
Sled-control er næste step og kræver en dedikeret on-hub command listener,
så vi ikke forstyrrer den kørende sled-runtime.

