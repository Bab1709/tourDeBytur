# Tour de Bytur

Et drukspil med bytur som tema. Brættet vises på en fælles skærm, og alle spiller fra deres egen telefon på samme wifi.

## Kom i gang

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

Åbn http://localhost:5001 på den fælles skærm, og scan QR-koden med telefonerne.

## Tilpas spillet

Barer, farvegrupper og antal tårer ligger i `data/board.json`. Brættet er en ring, så antallet af felter skal kunne deles med 4, og første felt skal være start.

Tallene for reglerne ligger i `data/settings.json`: `pass_start_sips` er antal tårer, man må uddele, når man passerer start, og `group_multiplier` er, hvor meget tårerne ganges med, når én spiller ejer hele farvegruppen.
