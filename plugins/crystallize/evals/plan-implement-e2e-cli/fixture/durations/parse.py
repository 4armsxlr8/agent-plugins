import re

_UNITS = {"h": 3600, "m": 60, "s": 1}
_TOKEN = re.compile(r"(\d+)([hms])")
_ORDER = "hms"


def parse_duration(text):
    """所要時間の文字列 (例: 1h30m) を秒数で返す。不正な文字列は ValueError。"""
    pos = 0
    total = 0
    last = -1
    for match in _TOKEN.finditer(text):
        rank = _ORDER.index(match.group(2))
        if match.start() != pos or rank <= last:
            raise ValueError(f"invalid duration: {text!r}")
        total += int(match.group(1)) * _UNITS[match.group(2)]
        pos = match.end()
        last = rank
    if pos == 0 or pos != len(text):
        raise ValueError(f"invalid duration: {text!r}")
    return total
