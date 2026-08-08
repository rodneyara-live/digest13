import sys
import tempfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from seen_store import SeenStore  # noqa: E402

FAILURES = []


def check(name, got, expected):
    ok = got == expected
    if not ok:
        FAILURES.append((name, got, expected))
    print(f"{'OK ' if ok else 'FAIL'} {name}")


def item(url, title, source="The Guardian", section="MUNDO"):
    return SimpleNamespace(url=url, title=title, source=source, section=section)


TMP = tempfile.mkdtemp()
DB = str(Path(TMP) / "seen.sqlite3")

store = SeenStore(DB)
today = date.today().isoformat()

store.note_seen([item("https://example.com/a", "Tormenta en el Caribe")], today)
check("note_seen no bloquea", store.is_blocked("https://example.com/a", "Tormenta en el Caribe"), False)

store.mark_sent([item("https://example.com/a", "Tormenta en el Caribe")], today)
check("mark_sent bloquea por URL", store.is_blocked("https://example.com/a", "Tormenta en el Caribe"), True)

check("bloquea URL con query utm", store.is_blocked("https://example.com/a?utm_source=rss&utm_medium=feed", "Tormenta en el Caribe"), True)
check("bloquea URL con fragmento", store.is_blocked("https://example.com/a#main", "Tormenta en el Caribe"), True)
check("bloquea URL case/scheme/www", store.is_blocked("HTTP://WWW.EXAMPLE.COM/A/", "Tormenta en el Caribe"), True)
check("bloquea mismo título misma fuente otra URL", store.is_blocked("https://example.com/b/act", "Tormenta en el Caribe", "The Guardian"), True)
check("no bloquea mismo título otra fuente", store.is_blocked("https://example.com/b/act", "Tormenta en el Caribe", "BBC News"), False)
check("no bloquea otra noticia", store.is_blocked("https://example.com/other", "Reforma fiscal aprobada", "The Guardian"), False)
check("no bloquea con título vacío", store.is_blocked("https://example.com/unseen"), False)

store.mark_sent([item("https://example.com/dup", "Caso duplicado")], today)
store.mark_sent([item("https://example.com/dup", "Caso duplicado")], today)
cur = store._conn.execute("SELECT COUNT(*) FROM seen WHERE url = ?", ("https://example.com/dup",))
check("mark_sent idempotente (1 fila)", cur.fetchone()[0], 1)

store.mark_sent([item("", "Sin URL no se guarda")], today)
cur = store._conn.execute("SELECT COUNT(*) FROM seen WHERE url = ''")
check("item sin URL se omite", cur.fetchone()[0], 0)

old = item("https://example.com/old", "Noticia vieja")
store.mark_sent([old], today)
store._conn.execute("UPDATE seen SET last_seen = '2020-01-01' WHERE url = ?", ("https://example.com/old",))
store._conn.commit()
n = store.prune(days=30)
check("prune borra filas viejas", n >= 1, True)
check("noticia vieja ya no bloquea", store.is_blocked("https://example.com/old", "Noticia vieja"), False)
check("noticia reciente sigue bloqueando", store.is_blocked("https://example.com/a", "Tormenta en el Caribe"), True)

store.close()

store2 = SeenStore(DB)
check("persiste entre conexiones", store2.is_blocked("https://example.com/a", "Tormenta en el Caribe"), True)
store2.close()

print()
if FAILURES:
    print(f"{len(FAILURES)} FALLOS:")
    for name, got, expected in FAILURES:
        print(f"  - {name}\n      got:      {got!r}\n      expected: {expected!r}")
    sys.exit(1)
print("TODAS LAS PRUEBAS PASARON")
