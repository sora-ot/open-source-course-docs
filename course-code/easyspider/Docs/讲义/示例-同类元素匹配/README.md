# 示例 · 同类元素自动匹配

配套 [06.同类元素自动匹配](../06.同类元素自动匹配.md) 篇的可运行演示页。

## 怎么用

直接用浏览器打开 `index.html` 即可（不需要服务器，不需要构建）。

1. 点左侧任意一个「商品标题」
2. 右侧立刻打印：该元素的**绝对 XPath** → 拆出的「标签名数组 / 索引数组」
3. 点「下一步」逐层观察，或点「一次跑完」直接看结果
4. 每一步都会显示：去掉哪一层索引 → 生成的新路径 → 匹配到几个 → 成功 / 失败
5. 成功后，全部同类元素会被蓝色虚线框高亮

## 为什么要试三层才成功

模拟网页的结构是 `ul > li[1..6] > div > a`：

| 去掉哪一层 | 结果 | 原因 |
|---|---|---|
| `a` 的索引 | 匹配 1 个 ❌ | 每个 li 里只有一个 a |
| `div` 的索引 | 匹配 1 个 ❌ | 每个 li 里只有一个 div |
| `li` 的索引 | 匹配 6 个 ✅ | 一整层 6 个 li |

**真正区分同类的是 `li` 的索引**——这正是真实网页里最常见的情况，
也是算法必须"从右往左一层层试"而不能一步到位的原因。

## 与 EasySpider 源码的对应关系

| 本示例 | EasySpider |
|---|---|
| `getAbsoluteXPath` | `readXPath(element, 1)` |
| `splitXPath` | `findRelated()` 的第 ① 步 |
| `combineXpath` | `combineXpath(nameList, indexList)` |
| `countMatch` | `document.evaluate` + `iterateNext` |
| `buildPlan` | `findRelated()` 的第 ② 步 |
| 蓝色虚线高亮 | `pushToReadyList()`（用 `global.boxShadowColor`） |

> ⚠️ 一个刻意对齐的细节：本示例的 `getAbsoluteXPath` 与 ES 的 `readXPath` 一致——
> 递归到 `body` 就收尾，所以 **`html` / `body` 两层不带索引**（索引为 `-1`）。
> 这正是 `findRelated()` 里 `if (nodeIndexList[i] == -1) continue;` 这个 `-1` 分支的由来。

## 建议动手改一改

- 给某个 `<li>` 里多加一层 `<span>`，再看算法会不会失效（对应讲义 §16「深度不一致」）
- 把 `<ul>` 里的项数改成 1 个，看"一直试到根都没有同类"的情况
