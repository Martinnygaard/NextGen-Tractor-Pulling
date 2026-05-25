# Hub Code

Pybricks MicroPython scripts til SPIKE Prime hubs.

## Upload files for Pybricks

Når filsystemet ikke understøtter mapper, brug unikke filnavne for hver hub:

- `master.py` - master hub eller Control+ broadcaster
- `master_broadcaster.py` - ren broadcaster uden knaplogik (PC/remote-styret setup)
- `display_1.py` - venstre display-hub
- `display_2.py` - midterste display-hub
- `display_3.py` - højre display-hub
- `scoreboard_display.py` - fælles display-logik til alle tre display-hubs

### Troubleshooting hub detection

If `master.py` raises an ImportError about a missing hub class when running on your hub, open `hubs/master.py` and set the `PrimeHub` name manually. Example:

```python
from pybricks.hubs import PrimeHub
# or
from pybricks.hubs import ControlPlusHub as PrimeHub
```

Save and re-run the script on the hub.

## Ren broadcaster-variant

Hvis du ikke vil bruge knapper på master-hubben, kan du i stedet køre
`master_broadcaster.py`.

- broadcaster ud på kanal `1` (som display-hubs lytter på)
- valgfri incoming kommandoer på kanal `2`
- live stdin-kommandoer fra PC bridge via Pybricks BLE
- ingen knaplogik

## Mapper

- `master/` - separat master-hub, der broadcaster scoreboard-state.
- `display_1/` - venstre display-hub, globale matrixer `0..5`.
- `display_2/` - midterste display-hub, globale matrixer `6..11`.
- `display_3/` - højre display-hub, globale matrixer `12..17`.

## Port-layout på hver display-hub

Samme lokale layout på alle tre display-hubs:

```text
[A][C][E]
[B][D][F]
```

Lokale matrix-index:

```text
[0][1][2]
[3][4][5]
```

På det samlede 18-matrix display antages de tre display-hubs at stå side by side.

