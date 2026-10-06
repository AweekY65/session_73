# jsondiffpatch — 本地结构化 JSON Diff / Patch / 三方 Merge

纯 Python 实现（仅标准库，Python ≥ 3.8），所有文档、patch 与冲突记录只存在于
**本地文件或内存** 中，不依赖数据库、云协作文档服务或任何外部服务。

## 功能概览

- `diff(a, b)`：生成结构化 patch，保证 `apply(a, diff(a, b)) == b`（round-trip）。
- `apply(doc, patch)`：应用 patch，返回新文档（不修改入参），严格校验路径与操作。
- `invert(patch)` / `rollback(doc, patch)`：逆向 patch 与回滚。
- `merge(base, left, right)`：三方合并，输出合并结果与明确的冲突列表。
- 命令行：`python -m jsondiffpatch <diff|apply|invert|merge> ...`（只读写本地文件）。

## 路径格式

采用 JSON Pointer（RFC 6901）：

- `""` 表示根文档；`/a/b/0` 表示 `doc["a"]["b"][0]`。
- key 中的 `~` 与 `/` 分别转义为 `~0`、`~1`。
- 数组用十进制下标（不允许负数）；`add` 操作的末尾可用 `/-` 表示追加。

## Patch 操作

```json
{"op": "add",     "path": "/cfg/port", "value": 8080}
{"op": "remove",  "path": "/tags/0",   "old": "a"}
{"op": "replace", "path": "/name",     "value": "app2", "old": "app"}
```

- `add`：对象上新增/覆盖 key；数组上在下标处插入（`/-` 追加）。
- `remove` / `replace` 携带 `old` 字段作为 **rollback 信息**；
  `apply` 默认校验 `old` 与当前值一致（可用 `validate_old=False` 关闭），
  防止把 patch 应用到错误的基线文档上。
- `invert(patch)` 生成逆 patch：`apply(apply(a, p), invert(p)) == a`。

### 校验与错误

所有非法情况抛出 `PatchError` 并带明确信息，包括：

- 路径不存在（缺失的 key、越界下标）；
- 类型不匹配（用 key 索引数组、用下标进入标量等）；
- 非法操作（未知 `op`、缺 `path`/`value`、根节点 `remove`、`old` 不匹配）。

## Diff 策略

- **对象按 key 比较**：key 的输入顺序变化不会产生任何 diff。
- **标量**：类型或值不同则产生一条 `replace`。
- **数组顺序敏感**：基于元素规范化序列的 LCS（`difflib.SequenceMatcher`）对齐，
  匹配上的元素两两递归比较（嵌套对象产生精确到子路径的修改），
  未匹配区段生成 `add`/`remove` 序列；元素重排会产生相应的删除+插入。
  生成的操作按下标从高到低应用，保证下标不漂移。

## 三方 Merge 规则

`merge(base, left, right)` 返回 `MergeResult(merged, conflicts)`，
`result.clean` 为 `True` 表示无冲突。规则：

- 两侧相同 → 取该值；仅一侧相对 base 变化 → 取变化侧。
- **对象** 逐 key 递归合并：
  - 一侧删除、另一侧未改 → 删除；
  - 一侧删除、另一侧修改 → 冲突；
  - 两侧新增同名 key 但值不同 → 冲突。
- **数组**：三者长度相等时按下标逐元素合并；否则若两侧都改了长度 → 冲突；
  仅一侧变化时取该侧（含插入/删除）。
- 其余双侧不兼容修改（如类型变更不一致）→ 冲突。

冲突不抛异常，记录为 `Conflict(path, reason, base, left, right)`；
合并结果中冲突位置确定性地保留 **left** 的值，冲突详情全部在
`result.conflicts` 中。

## 命令行用法

```bash
python -m jsondiffpatch diff  a.json b.json            # 输出 patch (JSON)
python -m jsondiffpatch apply doc.json patch.json      # 输出打补丁后的文档
python -m jsondiffpatch invert patch.json              # 输出逆向 patch
python -m jsondiffpatch merge base.json l.json r.json  # 合并；冲突写 stderr，退出码 1
```

## 运行测试

```bash
cd <项目根目录>
python3 -m unittest discover -s tests -v
```

测试全部在终端执行并输出逐项结果，覆盖：嵌套对象、数组插入/删除/修改/重排、
key 顺序无关性、非法 patch（路径不存在、类型不匹配、非法操作）、
三方冲突（同路径改删、双新增、数组长度冲突）、无冲突自动合并、
invert/rollback 以及 200 组随机文档的 diff→apply round-trip。

## 项目结构

```
jsondiffpatch/
  __init__.py    # 公共 API: diff/apply/invert/rollback/merge
  __main__.py    # 命令行入口
  paths.py       # JSON Pointer 解析/格式化
  diff.py        # 结构化 diff（对象按 key、数组按 LCS）
  patch.py       # apply / invert / rollback，严格校验
  merge.py       # 三方合并与冲突记录
  errors.py      # PatchError / PathError
tests/           # unittest 测试套件
```
