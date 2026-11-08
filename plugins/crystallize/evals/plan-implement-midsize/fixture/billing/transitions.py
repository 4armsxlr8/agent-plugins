"""請求書の状態遷移。

状態を変えるときは必ず transition を通す。invoice.status に直接代入すると
invoice.status_changed の監査イベントが残らない。
同じ状態への遷移は許されない (状態が変わらない操作では transition を呼ばない)。
"""

from .errors import InvalidTransition
from .models import DRAFT, ISSUED, PAID, PARTIALLY_PAID, VOID

ALLOWED = {
    DRAFT: {ISSUED, VOID},
    ISSUED: {PARTIALLY_PAID, PAID, VOID},
    PARTIALLY_PAID: {PAID},
    PAID: set(),
    VOID: set(),
}


def can_transition(from_status, to_status):
    return to_status in ALLOWED.get(from_status, set())


def transition(book, invoice, to_status, actor, on):
    """状態を変え、invoice.status_changed を記録する。許されない遷移は InvalidTransition"""
    from_status = invoice.status
    if not can_transition(from_status, to_status):
        raise InvalidTransition(f"{invoice.invoice_id}: {from_status} から {to_status} へは遷移できません")
    invoice.status = to_status
    book.audit.append(
        "invoice.status_changed",
        invoice.invoice_id,
        actor,
        on,
        {"from": from_status, "to": to_status},
    )
