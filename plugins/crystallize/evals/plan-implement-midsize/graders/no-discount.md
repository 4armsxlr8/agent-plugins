---
type: regex
target: { source: file, path: billing/refunds.py }
pattern: discount|割引
flags: i
match: not_contains
---
用語集で「使わない語」とした discount / 割引 を、新しいモジュールの識別子・文言・コメントに持ち込んでいないか
