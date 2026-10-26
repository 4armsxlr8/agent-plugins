def _sort_desc(items):
    """スコアの降順に並べる共通処理。items をその場で並べ替えて返す。"""
    items.sort(key=lambda item: item["score"], reverse=True)
    return items


def leaderboard(items):
    """全件をスコアの降順で返す。画面側が同じ list を使い回すため、渡された list をその場で並べ替える。"""
    return _sort_desc(items)
