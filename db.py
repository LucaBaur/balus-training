"""SQLite-Datenhaltung fuer Balu's Training - Fassade.

Die eigentliche Arbeit steht im Paket `daten/`, nach Themen getrennt (spieler, termine,
todos, ...). Diese Datei reicht alles unter dem alten Namen `db` durch, damit
`import db` + `db.funktion(...)` ueberall unveraendert funktioniert (Routen, Cron-Skripte,
Tests). Neuer Code darf auch direkt `from daten import termine` benutzen.

Tests biegen `db.verbinde` um (Temp-Datenbank); die Routen rufen immer `db.verbinde()`
ueber diese Fassade, nicht ueber das Paket - so greift der Austausch.
"""

from daten.analysen import *      # noqa: F401,F403
from daten.benutzer import *      # noqa: F401,F403
from daten.chat import *          # noqa: F401,F403
from daten.clips import *         # noqa: F401,F403
from daten.core import *          # noqa: F401,F403
from daten.kommentare import *    # noqa: F401,F403
from daten.nachbereitung import * # noqa: F401,F403
from daten.nutzung import *       # noqa: F401,F403
from daten.push import *          # noqa: F401,F403
from daten.schema import *        # noqa: F401,F403
from daten.spiele import *        # noqa: F401,F403
from daten.spieler import *       # noqa: F401,F403
from daten.termine import *       # noqa: F401,F403
from daten.todos import *         # noqa: F401,F403
from daten.wiki import *          # noqa: F401,F403
from daten.zeit import *          # noqa: F401,F403

# Namen mit Unterstrich schliesst `import *` aus; diese hier nutzt anderer Code (Cron, Tests).
from daten.zeit import _berlin, _utc_z   # noqa: F401
