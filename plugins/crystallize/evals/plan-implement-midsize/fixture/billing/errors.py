"""このライブラリが送出する例外。"""


class BillingError(Exception):
    """このライブラリの例外の基底。"""


class ValidationError(BillingError, ValueError):
    """入力の値が不正。"""


class NotFound(BillingError, LookupError):
    """指定された請求書や明細が存在しない。"""


class InvalidTransition(BillingError):
    """請求書の今の状態では許されない操作。"""


class StoreError(BillingError):
    """保存ファイルを読み込めない。"""
