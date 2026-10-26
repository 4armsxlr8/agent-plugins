# durations

所要時間の文字列を扱う小さなライブラリ。標準ライブラリだけで動く。

## 使い方

文字列を秒数に変換する。

```python
from durations import parse_duration

parse_duration("1h30m")  # => 5400
parse_duration("45s")    # => 45
```

不正な文字列 (`""`, `"10"`, `"5d"`, `"30m1h"` など) は `ValueError` を送出する。

## ライセンス

MIT
