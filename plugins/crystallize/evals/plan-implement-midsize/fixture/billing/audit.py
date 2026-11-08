"""監査イベントの記録。

イベントは後から書き換えず、追記だけする。data は保存ファイルにそのまま JSON で
書き出されるので、値は文字列・数値・真偽値・None だけにする。金額は
money.format_amount で文字列にして入れる。at は日付の ISO 形式の文字列。
"""

from dataclasses import asdict, dataclass, field
from typing import Dict, List


@dataclass
class AuditEvent:
    """監査イベント 1 件。seq は帳簿全体で 1 から始まる連番。"""

    seq: int
    kind: str
    invoice_id: str
    actor: str
    at: str
    data: Dict = field(default_factory=dict)


class AuditLog:
    """監査イベントの列。"""

    def __init__(self):
        self.events: List[AuditEvent] = []

    def append(self, kind, invoice_id, actor, on, data=None):
        """イベントを 1 件追記して返す。on は datetime.date"""
        event = AuditEvent(
            seq=len(self.events) + 1,
            kind=kind,
            invoice_id=invoice_id,
            actor=actor,
            at=on.isoformat(),
            data=dict(data or {}),
        )
        self.events.append(event)
        return event

    def for_invoice(self, invoice_id):
        """その請求書のイベントを古い順に返す"""
        return [e for e in self.events if e.invoice_id == invoice_id]

    def of_kind(self, kind):
        """その種類のイベントを古い順に返す"""
        return [e for e in self.events if e.kind == kind]

    def to_list(self):
        return [asdict(e) for e in self.events]

    @classmethod
    def from_list(cls, items):
        log = cls()
        log.events = [AuditEvent(**item) for item in items]
        return log
