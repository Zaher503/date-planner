"""Names and domains turned into comparable tokens."""
import re
from urllib.parse import urlsplit


def words(text: str) -> list[str]:
    """Every run of letters and digits, lower-cased."""
    return re.findall(r"[a-z0-9]+", text.lower())


def tokens(name: str) -> list[str]:
    """The words of a name that identify it: no 1-2 letter words, no "the" or "and"."""
    return [w for w in words(name) if len(w) > 2 and w not in ("the", "and")]


def squash(text: str) -> str:
    """Lower-cased letters and digits only, run together."""
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def host_label(url: str) -> str:
    """First label of the host name ("www." dropped), lower-cased, letters and digits only."""
    return squash(((urlsplit(url).hostname or "").removeprefix("www.").split(".") or [""])[0])


def mentions(text: str, name: str) -> bool:
    """All the identifying words of the name appear in the text (spaces and punctuation ignored)."""
    flat = squash(text)
    ws = tokens(name)
    return bool(ws) and all(w in flat for w in ws)


def domain_matches(url: str, name: str) -> bool:
    """The site's own domain is the venue's name (academymuseum.org for Academy Museum of Motion Pictures):
    the page text may not repeat the full name, but the domain says whose site it is."""
    label = host_label(url)
    ws = tokens(name)
    return len(label) >= 5 and label in {"".join(ws[:k]) for k in range(1, len(ws) + 1)}


def is_host_name(name: str | None, url: str) -> bool:
    """'Losangelesmuseumoflove' on losangelesmuseumoflove.com: the name is just the domain."""
    flat = squash(name or "")
    return bool(flat) and " " not in (name or "").strip() and flat == host_label(url)
