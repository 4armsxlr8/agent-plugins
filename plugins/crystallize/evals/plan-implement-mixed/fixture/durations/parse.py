import re

_UNITS = {"h": 3600, "m": 60, "s": 1}
_PATTERN = re.compile(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+)s)?")


def parse_duration(text):
    """所要時間の文字列 (例: "1h30m") を秒数で返す。"""
    match = _PATTERN.fullmatch(text)
    if not text or match is None:
        raise ValueError(f"invalid duration: {text!r}")
    hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
    return hours * _UNITS["h"] + minutes * _UNITS["m"] + seconds * _UNITS["s"]
