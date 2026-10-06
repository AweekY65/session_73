# local-json-diff

本地结构化 JSON **Diff / Patch / 三方 Merge** 工具。纯 Node.js（>= 18，推荐 22）实现，零第三方依赖；所有文档、patch、冲突记录只存在于本地文件或内存中，不使用数据库、云协作文档服务或任何外部服务。

## 功能概览

- `diff(a, b)`：生成 JSON-Patch 风格补丁，`apply(a, patch).doc` 精确等于 `b`。
- `apply(doc, patch)`：应用补丁，返回 `{ doc, rollback }`，不修改输入文档。
- `invertPatch(patch)`：不执行即可生成逆向补丁（要求 remove/replace 携带 `prev`，`diff()` 生成的补丁自带）。
- `merge(base, left, right)`：三方合并，返回 `{ doc, conflicts }`。
- 支持 object 属性新增 / 删除 / 替换，array 元素插入 / 删除 / 修改。
- 应用补丁时校验路径存在性、容器类型与操作合法性，抛 `PatchError`（`code` 为 `PATH_NOT_FOUND` / `TYPE_MISMATCH` / `INVALID_OP`）。

## 路径格式

补丁中的 `path` 使用 **JSON Pointer（RFC 6901）**：

- 段与段之间以 `/` 分隔，空字符串 `""` 表示文档根（根节点只允许 `replace`）。
- object 的 key 原样作为路径段；key 中的 `~` 转义为 `~0`，`/` 转义为 `~1`（如 key `a/b` 的路径为 `/a~1b`）。
- array 下标为十进制数字（`0`、`1`、`2`…），必须落在合法范围内；`add` 允许下标等于数组长度（追加到末尾）。

## Patch 格式

```json
[
  { "op": "add",     "path": "/deps/c",  "value": "3.0" },
  { "op": "remove",  "path": "/deps/a",  "prev": "1.0" },
  { "op": "replace", "path": "/name",    "value": "app2", "prev": "app" }
]
```

- `add`：object 新增/覆盖 key，或向 array 指定下标插入元素。
- `remove`：删除存在的 key / 数组元素；`prev` 记录被删除的旧值。
- `replace`：替换存在的值；`prev` 记录旧值。
- `prev` 即 rollback 信息：`remove`/`replace` 必带，`diff()` 生成的补丁自动包含。

## Diff 策略

- **Object**：按 key 集合比较，与 key 的输入顺序无关——仅调整 key 顺序不会产生任何 diff。key 按字典序遍历，保证同一输入永远生成同一份补丁。
- **Array**：以“元素深相等”为基础做 LCS 对齐；对齐锚点之间的未匹配区段按位置配对：
  - 配对的元素生成原地修改（`replace` 或嵌套 diff）；
  - 多出的旧元素生成 `remove`，多出的新元素生成 `add`。
- **其他**（原始值变化、类型变化）：单个 `replace`。

### 数组顺序变化规则

数组是**有序**的：元素移动位置属于真实修改。重排数组会对被移动的元素生成 `remove` + `add`（LCS 保持最长稳定子序列不动），例如 `[1,2,3] → [3,1,2]` 生成 `add /0 = 3` 与 `remove /3`。

## 三方 Merge 规则

`merge(base, left, right)` 递归比较三方：

1. 仅一方修改（或双方修改结果相同）→ 自动采用，无冲突。
2. Object 按 key 递归合并：一方删除、另一方未动 → 删除；一方删除、另一方修改 → `delete-vs-modify` 冲突。
3. 双方各自新增同一个 key 但值不同 → `create-vs-create` 冲突。
4. Array：三方长度一致时按下标逐元素合并；双方都改变了数组结构（长度不一致）→ 整个数组报 `array-structure-conflict` 冲突；仅一方改变结构 → 自动采用该方。
5. 其他双方不兼容修改（含类型变化）→ `incompatible-modification` 冲突。

冲突记录格式：`{ path, reason, base, left, right }`。冲突路径在合并结果中**保留 base 值**（base 不存在该路径时保留 left 值），保证结果确定性。

## 使用

### 库

```js
import { diff, apply, invertPatch, merge } from './src/index.js';

const patch = diff(a, b);
const { doc, rollback } = apply(a, patch); // doc 深等于 b
const restored = apply(doc, rollback).doc; // 还原为 a
const inverse = invertPatch(patch);        // 不执行也可得到逆向补丁
const { doc: merged, conflicts } = merge(base, left, right);
```

### CLI

```bash
node cli.js diff   a.json b.json patch.json        # 生成补丁
node cli.js apply  a.json patch.json out.json      # 应用补丁（stderr 打印 rollback 信息）
node cli.js invert patch.json inverse.json         # 生成逆向补丁
node cli.js merge  base.json left.json right.json merged.json
# merge 有冲突时退出码为 1，冲突详情打印到 stderr
```

省略输出文件参数时结果打印到 stdout。

## 测试

```bash
npm test          # 等价于 node --test test/*.test.js
```

测试全部在终端运行（TAP 输出），覆盖：嵌套对象 diff、数组插入/删除/修改/重排、key 顺序无关性、RFC 6901 转义、非法补丁（路径不存在 / 类型不匹配 / 非法操作）、apply 不修改输入、rollback 与 invertPatch 还原、无冲突 merge、各类三方冲突、复杂文档 round-trip 等。
