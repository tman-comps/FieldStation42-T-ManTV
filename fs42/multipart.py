import os
import re

# T-ManTV: keep multi-part episodes together on random channels.
# A "part" is read from the title (Part 1, Part One, Part II, pt 2, Part 1 of 3, (2), 3 Of 4 ...).
# The next part is the next part-marked file in the same folder (sorted by path), looking
# at most LOOKAHEAD files ahead, so parts with different titles (Paradise Lost / Paradise
# Regained) still pair up and a stray Part 1 never grabs an unrelated Part 2 far away.

LOOKAHEAD = 3

_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6,
}
_NUM = r"(\d|one|two|three|four|five|six|iv|vi|v|iii|ii|i)"
_PATTERNS = [
    re.compile(r"\b(?:part|pt)[\s.\-_]*" + _NUM + r"\b", re.I),
    re.compile(r"\b(\d)\s+of\s+\d\b", re.I),
    re.compile(r"\((\d)\)"),
]


def part_number(title):
    """The part number in a title, or None. Titles naming two different parts
    (segment shows like "Devolver Part 1 ... Devolver Part 2") count as standalone."""
    found = set()
    for pat in _PATTERNS:
        for m in pat.finditer(title):
            word = m.group(1).lower()
            num = int(word) if word.isdigit() else _WORDS.get(word)
            if num:
                found.add(num)
    if len(found) == 1:
        return found.pop()
    return None


class MultipartIndex:
    """Per-tag chains of multi-part episodes, built lazily from the catalog."""

    def __init__(self, catalog):
        self.catalog = catalog
        self._next = {}   # tag -> {path: next entry}
        self._prev = {}   # tag -> {path: previous entry}

    def _build(self, tag):
        nxt, prv = {}, {}
        entries = self.catalog.get_all_by_tag(tag) or []
        by_dir = {}
        for e in entries:
            by_dir.setdefault(os.path.dirname(e.path), []).append(e)
        for files in by_dir.values():
            files.sort(key=lambda e: e.path)
            parts = [part_number(e.title) for e in files]
            for i, (entry, num) in enumerate(zip(files, parts)):
                if num is None:
                    continue
                for j in range(i + 1, min(i + 1 + LOOKAHEAD, len(files))):
                    if parts[j] is None:
                        continue
                    if parts[j] == num + 1:
                        nxt[entry.path] = files[j]
                        prv[files[j].path] = entry
                    break
        self._next[tag], self._prev[tag] = nxt, prv

    def _maps(self, tag):
        if tag not in self._next:
            self._build(tag)
        return self._next[tag], self._prev[tag]

    def chain_for(self, entry):
        """All parts of entry's story in order, starting from part 1. One item if standalone."""
        nxt, prv = self._maps(entry.tag)
        head = entry
        seen = {head.path}
        while head.path in prv and prv[head.path].path not in seen:
            head = prv[head.path]
            seen.add(head.path)
        chain = [head]
        seen = {head.path}
        while chain[-1].path in nxt and nxt[chain[-1].path].path not in seen:
            chain.append(nxt[chain[-1].path])
            seen.add(chain[-1].path)
        return chain
