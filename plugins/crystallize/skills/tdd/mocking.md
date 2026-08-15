# mock を使う場面

mock を当てるのは **システム境界** だけ:

- 外部 API（決済・メールなど）
- データベース（場合による — できればテスト用 DB を使う）
- 時刻・乱数
- ファイルシステム（場合による）

mock しないもの:

- 自分で書いたクラス / モジュール
- 内部の協力オブジェクト
- 自分がコントロールできるもの

## mock しやすい設計

システム境界では、mock しやすいインターフェースを設計する。

**1. dependency injection（依存性注入）を使う**

外部依存を内部で生成せず、外から渡す:

```typescript
// Easy to mock
function processPayment(order, paymentClient) {
  return paymentClient.charge(order.total);
}

// Hard to mock
function processPayment(order) {
  const client = new StripeClient(process.env.STRIPE_KEY);
  return client.charge(order.total);
}
```

**2. 汎用 fetcher より SDK 風のインターフェースを選ぶ**

条件分岐を抱えた汎用関数 1 つで済ませず、外部操作ごとに専用の関数を作る:

```typescript
// GOOD: Each function is independently mockable
const api = {
  getUser: (id) => fetch(`/users/${id}`),
  getOrders: (userId) => fetch(`/users/${userId}/orders`),
  createOrder: (data) => fetch('/orders', { method: 'POST', body: data }),
};

// BAD: Mocking requires conditional logic inside the mock
const api = {
  fetch: (endpoint, options) => fetch(endpoint, options),
};
```

SDK 方式なら:
- mock が返す形はそれぞれ 1 つに決まる
- テストのセットアップに条件分岐が要らない
- そのテストがどのエンドポイントを使っているか見やすい
- エンドポイント単位で型安全
