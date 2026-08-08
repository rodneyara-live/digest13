import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from num2words import int_to_words, numbers_to_words, number_to_words  # noqa: E402
from text_cleaner import strip_markdown  # noqa: E402

FAILURES = []


def check(name, got, expected):
    ok = got == expected
    if not ok:
        FAILURES.append((name, got, expected))
    print(f"{'OK ' if ok else 'FAIL'} {name}")


def check_int(n, expected):
    check(f"int_to_words({n})", int_to_words(n), expected)


check_int(0, "cero")
check_int(5, "cinco")
check_int(10, "diez")
check_int(11, "once")
check_int(15, "quince")
check_int(16, "dieciséis")
check_int(19, "diecinueve")
check_int(20, "veinte")
check_int(21, "veintiuno")
check_int(22, "veintidós")
check_int(23, "veintitrés")
check_int(26, "veintiséis")
check_int(29, "veintinueve")
check_int(30, "treinta")
check_int(31, "treinta y uno")
check_int(42, "cuarenta y dos")
check_int(99, "noventa y nueve")
check_int(100, "cien")
check_int(101, "ciento uno")
check_int(115, "ciento quince")
check_int(120, "ciento veinte")
check_int(121, "ciento veintiuno")
check_int(199, "ciento noventa y nueve")
check_int(200, "doscientos")
check_int(201, "doscientos uno")
check_int(500, "quinientos")
check_int(700, "setecientos")
check_int(900, "novecientos")
check_int(999, "novecientos noventa y nueve")
check_int(1000, "mil")
check_int(1001, "mil uno")
check_int(1100, "mil cien")
check_int(1101, "mil ciento uno")
check_int(2000, "dos mil")
check_int(2100, "dos mil cien")
check_int(4500, "cuatro mil quinientos")
check_int(10000, "diez mil")
check_int(100000, "cien mil")
check_int(100001, "cien mil uno")
check_int(999999, "novecientos noventa y nueve mil novecientos noventa y nueve")
check_int(1000000, "un millón")
check_int(2000000, "dos millones")
check_int(4000000, "cuatro millones")
check_int(1234567, "un millón doscientos treinta y cuatro mil quinientos sesenta y siete")
check_int(1000000000, "mil millones")
check_int(2500000000, "dos mil quinientos millones")
check_int(3700000000, "tres mil setecientos millones")
check_int(4000000000000, "cuatro billones")

check("parse 4,5 (decimal coma)", number_to_words("4,5"), (4, "5"))
check("parse 4.5 (decimal punto)", number_to_words("4.5"), (4, "5"))
check("parse 4.500 (miles)", number_to_words("4.500"), (4500, None))
check("parse 2.300.500 (miles)", number_to_words("2.300.500"), (2300500, None))
check("parse 2300500 (seguido)", number_to_words("2300500"), (2300500, None))
check("parse 2 300 500 (espacios)", number_to_words("2 300 500"), (2300500, None))
check("parse 1.234,56 (punto+coma)", number_to_words("1.234,56"), (1234, "56"))
check("parse 1,234.56 (coma+punto)", number_to_words("1,234.56"), (1234, "56"))
check("parse 0,05 (cero decimal)", number_to_words("0,05"), (0, "05"))

T = numbers_to_words

check("T 1,5 millones", T("1,5 millones de personas"), "uno coma cinco millones de personas")
check("T 82.000 muertes", T("causaron 82.000 muertes"), "causaron ochenta y dos mil muertes")
check("T 2.103 casos", T("registró 2.103 casos"), "registró dos mil ciento tres casos")
check("T 29,18%", T("aumento de 475 casos (29,18%)"), "aumento de cuatrocientos setenta y cinco casos (veintinueve coma dieciocho por ciento)")
check("T 59,4%", T("el 59,4% de los casos"), "el cincuenta y nueve coma cuatro por ciento de los casos")
check("T 100.000 habitantes", T("100.000 habitantes"), "cien mil habitantes")
check("T 40,3 por cada", T("los 40,3 casos por cada"), "los cuarenta coma tres casos por cada")
check("T 76,6", T("tasa de 76,6 por cada"), "tasa de setenta y seis coma seis por cada")
check("T 45,16 km", T("distancia de 45,16 km"), "distancia de cuarenta y cinco coma dieciséis km")
check("T 38,6 km", T("recorrido 38,6 km"), "recorrido treinta y ocho coma seis km")
check("T 4000000", T("4 seguido de 6 ceros es 4000000"), "cuatro seguido de seis ceros es cuatro millones")
check("T 4.000.000", T("4.000.000 de habitantes"), "cuatro millones de habitantes")
check("T 2 300 500", T("2 300 500 ciudadanos"), "dos millones trescientos mil quinientos ciudadanos")
check("T 10% pegado", T("El 10% subió"), "El diez por ciento subió")
check("T 10 % separado", T("El 10 % subió"), "El diez por ciento subió")
check("T 80% confianza", T("un 80% de confianza"), "un ochenta por ciento de confianza")
check("T 2026", T("en 2026"), "en dos mil veintiséis")
check("T 2021", T("febrero de 2021"), "febrero de dos mil veintiuno")
check("T hora no toca", T("a las 7:00"), "a las 7:00")
check("T fecha no toca", T("el 07/08/2026"), "el 07/08/2026")
check("T año tras slash no toca", T("acuerdo 2026/2027"), "acuerdo 2026/2027")
check("T 1 de mayo", T("el 1 de mayo"), "el uno de mayo")
check("T uno de cada", T("1 de cada 5"), "uno de cada cinco")
check("T número en palabra no toca", T("un smartphone 4G"), "un smartphone 4G")
check("T 12,5 millones", T("2.500 millones -> 12,5 millones"), "dos mil quinientos millones -> doce coma cinco millones")

check(
    "T strip_markdown ₡2.300.500",
    strip_markdown("### Cierre cambiario\n\nEl tipo de cambio subió a **₡2.300.500**"),
    "Cierre cambiario\n\nEl tipo de cambio subió a dos millones trescientos mil quinientos colones",
)
check(
    "T strip_markdown ₡12,50 con decimal",
    strip_markdown("Café a ₡12,50 la taza"),
    "Café a doce coma cincuenta colones la taza",
)
check(
    "T strip_markdown enlace markdown",
    strip_markdown("[Sífilis en Costa Rica: 2.103 casos](https://example.com)"),
    "Sífilis en Costa Rica: dos mil ciento tres casos",
)

print()
if FAILURES:
    print(f"{len(FAILURES)} FALLOS:")
    for name, got, expected in FAILURES:
        print(f"  - {name}\n      got:      {got!r}\n      expected: {expected!r}")
    sys.exit(1)
print("TODAS LAS PRUEBAS PASARON")
