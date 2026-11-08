from .fees import quote


def export_row(order_id, parcel):
    """請求データの 1 行 (注文番号,基本料金,遠隔地料金,税額,合計)。経理の取り込みが列の順に依存している"""
    b = quote(parcel)["breakdown"]
    return f"{order_id},{b['base']},{b['remote']},{b['tax']},{b['base'] + b['remote'] + b['tax']}"
