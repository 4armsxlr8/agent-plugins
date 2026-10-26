import re

_UNITS = {"h": 3600, "m": 60}
_TOKEN = re.compile(r"(\d+)([hm])")


def parse_duration(text):
    """所要時間の文字列を秒数で返す。単位のない数字は分として扱う。"""
    if text.isdigit():
        return int(text) * 60
    pos = 0
    total = 0
    for match in _TOKEN.finditer(text):
        if match.start() != pos:
            raise ValueError(f"invalid duration: {text!r}")
        total += int(match.group(1)) * _UNITS[match.group(2)]
        pos = match.end()
    if pos == 0 or pos != len(text):
        raise ValueError(f"invalid duration: {text!r}")
    return total
