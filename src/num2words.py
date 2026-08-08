import re
import sys

_UNIDADES = [
    "cero", "uno", "dos", "tres", "cuatro", "cinco",
    "seis", "siete", "ocho", "nueve",
]

_DECENAS = [
    "", "", "veinte", "treinta", "cuarenta", "cincuenta",
    "sesenta", "setenta", "ochenta", "noventa",
]

_CENTENAS = [
    "", "ciento", "doscientos", "trescientos", "cuatrocientos",
    "quinientos", "seiscientos", "setecientos", "ochocientos", "novecientos",
]

_ESPECIALES = {
    10: "diez", 11: "once", 12: "doce", 13: "trece", 14: "catorce",
    15: "quince", 16: "dieciséis", 17: "diecisiete", 18: "dieciocho",
    19: "diecinueve",
}

_VEINTI = {
    1: "uno", 2: "dós", 3: "trés", 4: "cuatro", 5: "cinco",
    6: "séis", 7: "siete", 8: "ocho", 9: "nueve",
}

_TOKEN_RE = re.compile(
    r"\d{1,3}(?:\s\d{3})+"
    r"|\d+(?:[.,]\d+)+"
    r"|\d+"
)

_LETTERS = set(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "abcdefghijklmnopqrstuvwxyz"
    "ÁÉÍÓÚáéíóúÑñ"
)

_BLOCKED = _LETTERS | set("0123456789.,/%:@")

_PERCENT_RE = re.compile(r"[ \t]*%")
_TIME_DATE_RE = re.compile(r"[ \t]*[:/]")


def _cero_a_999(n: int) -> str:
    if n < 10:
        return _UNIDADES[n]
    if n < 20:
        return _ESPECIALES[n]
    if n < 30:
        return "veinte" if n == 20 else "veinti" + _VEINTI[n - 20]
    if n < 100:
        t, u = divmod(n, 10)
        return _DECENAS[t] if u == 0 else _DECENAS[t] + " y " + _UNIDADES[u]
    if n == 100:
        return "cien"
    c, r = divmod(n, 100)
    if r == 0:
        return _CENTENAS[c]
    return _CENTENAS[c] + " " + _cero_a_999(r)


def int_to_words(n: int) -> str:
    if n < 0:
        return "menos " + int_to_words(-n)
    if n < 1000:
        return _cero_a_999(n)
    if n < 1_000_000:
        m, r = divmod(n, 1000)
        head = "mil" if m == 1 else _cero_a_999(m) + " mil"
        return head + (" " + int_to_words(r) if r else "")
    if n < 1_000_000_000_000:
        m, r = divmod(n, 1_000_000)
        head = "un millón" if m == 1 else int_to_words(m) + " millones"
        return head + (" " + int_to_words(r) if r else "")
    m, r = divmod(n, 1_000_000_000_000)
    head = "un billón" if m == 1 else _cero_a_999(m) + " billones"
    return head + (" " + int_to_words(r) if r else "")


def _decimal_words(frac: str) -> str:
    if len(frac) <= 2 and not frac.startswith("0"):
        return _cero_a_999(int(frac))
    return " ".join(_UNIDADES[int(d)] for d in frac)


def number_to_words(token: str):
    token = token.strip(".,")
    if not token:
        return None
    token = token.replace(" ", "")
    if not re.fullmatch(r"\d+(?:[.,]\d+)*", token):
        return None
    if "," in token or "." in token:
        li = max(token.rfind(","), token.rfind("."))
        sep = token[li]
        integer, frac = token[:li], token[li + 1:]
        if (
            sep == "."
            and len(frac) == 3
            and re.fullmatch(r"\d{1,3}(?:\.\d{3})*", integer)
        ):
            return int(token.replace(".", "").replace(",", "")), None
        return int(integer.replace(".", "").replace(",", "")), frac
    return int(token), None


def numbers_to_words(text: str) -> str:
    out = []
    last = 0
    for m in _TOKEN_RE.finditer(text):
        if m.start() > 0 and text[m.start() - 1] in _BLOCKED:
            continue
        rest = text[m.end():]
        if _TIME_DATE_RE.match(rest):
            continue
        if m.end() < len(text) and text[m.end()] in _LETTERS:
            continue
        parsed = number_to_words(m.group())
        if parsed is None:
            continue
        integer, frac = parsed
        if frac is not None:
            words = int_to_words(integer) + " coma " + _decimal_words(frac)
        else:
            words = int_to_words(integer)
        out.append(text[last:m.start()])
        out.append(words)
        pm = _PERCENT_RE.match(rest)
        if pm:
            out.append(" por ciento")
            last = m.end() + pm.end()
        else:
            last = m.end()
    out.append(text[last:])
    return "".join(out)


def main(argv=None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    source = " ".join(argv) if argv else sys.stdin.read()
    print(numbers_to_words(source))


if __name__ == "__main__":
    main()
