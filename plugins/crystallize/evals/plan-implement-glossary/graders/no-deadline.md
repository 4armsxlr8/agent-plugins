---
type: regex
target: { source: file, path: tasks/due.py }
pattern: deadline
flags: i
match: not_contains
---
用語集で「使わない語」とした deadline を、新しいモジュールの識別子・文言・コメントに持ち込んでいないか
