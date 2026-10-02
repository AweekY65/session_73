# Local DPLL SAT Solver

一个完全本地、自包含的 SAT 求解器。所有 CNF 输入、求解状态、模型和测试数据只存在于本地文件或内存中；不调用 Z3、MiniSat、云求解服务或任何外部服务，核心算法（DPLL）完全由本项目自行实现，仅使用 Python 标准库。

## 项目结构

- `sat_solver/dimacs.py` — 严格的 DIMACS CNF 解析器
- `sat_solver/dpll.py` — DPLL 求解核心（unit propagation、pure literal elimination、分支启发式、统计）
- `sat_solver/__main__.py` — 命令行入口
- `tests/test_sat_solver.py` — 自动化测试（含穷举 oracle）

## DPLL 流程

`solve(nvars, clauses)` 的执行流程：

1. **预处理**：丢弃 tautology clause（同时含 `x` 与 `¬x`，恒真）；重复 literal 由集合表示自然去重；空 clause 直接判定 UNSAT。
2. **Unit propagation（单元传播）**：反复找出长度为 1 的 clause，将其唯一 literal 赋真并化简公式，直到不动点；若化简产生空 clause 则当前分支冲突。每次赋值计入 `propagations`。
3. **Pure literal elimination（纯文字消除）**：在剩余公式中只以单一极性出现的变量直接按该极性赋值并化简，随后回到第 2 步。每次赋值计入 `pure_literals`。
4. **变量选择（分支启发式）**：采用 Jeroslow–Wang 单边启发式——每个 literal 的得分为其出现的所有 clause 的 `2^-len(clause)` 之和；选择两极性得分总和最大的变量，并以得分较高的极性作为第一分支。每次分支计入 `decisions`。
5. **回溯**：第一分支失败（子树返回 UNSAT）时撤销该赋值、尝试相反极性；两个分支都失败则向上返回冲突。每次分支失败计入 `backtracks`。

求解保证终止（每次决策固定一个变量），UNSAT 结论来自完整的搜索树穷尽，不依赖任何超时猜测。

## 退化输入的确定语义

| 输入 | 语义 |
| --- | --- |
| 空公式（0 个 clause） | SAT，任意赋值都是模型；未受约束的变量默认赋 `False`，模型总是完整可直接验证 |
| 空 clause | UNSAT（根节点冲突） |
| clause 内重复 literal | 集合语义，自动去重 |
| tautology clause（含 `x` 与 `¬x`） | 恒真，加载时丢弃 |

SAT 结果通过 `verify(clauses, model)` 可再次逐条验证所有 clause。

## DIMACS 输入格式

```
c 注释行（可出现在任意位置）
p cnf <nvars> <nclauses>
1 -2 0
2 3 0
%
```

严格校验（违反即抛出 `DimacsError`）：

- 必须有且仅有一个 `p cnf` 头，且出现在任何 clause 之前；
- `nvars`、`nclauses` 必须是非负整数；
- 每个 literal `l` 满足 `1 <= |l| <= nvars`；
- 每个 clause 必须以 `0` 结尾（允许跨行）；
- clause 数量必须与头部声明一致；
- 可选的 `%` 结束标记必须独占一行，其后不允许出现任何非空内容。

## 使用方法

```bash
python3 -m sat_solver <file.cnf>
```

输出示例：

```
SAT
stats: decisions=1 propagations=2 pure_literals=0 backtracks=0
v 1 -2 3 0
```

退出码：`0` = SAT，`1` = UNSAT，`2` = 输入/解析错误。

库用法：

```python
from sat_solver import parse_dimacs_file, solve, verify

nvars, clauses = parse_dimacs_file("example.cnf")
result = solve(nvars, clauses)
print(result.status)          # "SAT" 或 "UNSAT"
print(result.stats)           # decisions / propagations / pure_literals / backtracks
if result.satisfiable:
    assert verify(clauses, result.model)
```

## 运行测试

所有测试直接在终端执行：

```bash
cd /mnt2/zjh/code/Goleta/session_73/b
python3 -m unittest discover -s tests -v
```

测试覆盖：SAT / UNSAT 基本用例、unit propagation 链、pure literal elimination、深度回溯（鸽笼原理 PHP(4,3)）、DIMACS 各类格式错误、空公式 / 空 clause / 重复 literal / tautology 的退化语义，以及 300 个随机小公式与穷举 oracle 的对拍验证。
