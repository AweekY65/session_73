# Local DPLL SAT Solver

一个纯 Python 实现的本地 SAT 求解器。所有 CNF 输入、求解状态、模型与测试
数据仅保存在本地文件或内存中；**不调用** Z3、MiniSat、云求解服务或任何
外部服务，核心 DPLL 算法完全自行实现，仅使用 Python 标准库。

## 文件结构

- `sat_solver.py` — DIMACS 解析器、DPLL 求解器、模型验证与 CLI 入口
- `tests/test_sat_solver.py` — 自动化测试（含穷举 oracle）
- `examples/sat.cnf` / `examples/unsat.cnf` — 示例输入

## 输入格式（DIMACS CNF，严格校验）

```
c 注释行以 c 开头
p cnf <nvars> <nclauses>
1 -2 0
2 3 0
%
0
```

解析器严格校验以下内容，任何违规都会抛出 `DimacsError`：

- 必须有且仅有一行 `p cnf <nvars> <nclauses>` 头部，且出现在所有子句之前；
- 每个子句由空白分隔的整数组成，以 `0` 结束，允许跨行书写；
- 每个文字 `L` 必须满足 `1 <= |L| <= nvars`；
- 实际书写的子句数必须与头部声明的 `<nclauses>` 一致
  （tautology 子句计入书写数量，在归一化阶段才被丢弃）；
- 子句区必须以单独一行 `%` 作为文件结束标记；其后仅允许空白和
  一个可选的 `0`，出现其他内容即报错；
- 文件结尾存在未以 `0` 终止的子句、或缺少 `%` 标记，均报错。

### 确定语义

- **空公式**（0 个子句）：恒为 SAT，所有变量按 don't-care 扩展为 `False`；
- **空子句**（单独的 `0`）：公式直接 UNSAT；
- **重复文字**：在子句内去重；
- **tautology 子句**（同时含 `x` 与 `-x`）：恒真，直接丢弃。

## DPLL 流程

`sat_solver.py` 中的 `SatSolver._dpll` 按以下顺序递归执行：

1. **Unit propagation（单元传播）**：反复找出长度为 1 的子句，将其文字
   赋值并化简公式，直到不动点；出现空子句或矛盾赋值即冲突，返回失败。
2. **Pure literal elimination（纯文字消除）**：扫描所有未赋值变量的极性，
   只以单一极性出现的变量直接按该极性赋值并化简，直到不动点。
3. **变量选择（decision）**：采用 max-occurrence（类 DLIS）启发式——
   选择在当前剩余子句中出现次数最多的变量，平局时取变量编号最小者；
   分支顺序固定为先 `True` 后 `False`。
4. **回溯**：某一分支失败时撤销该决策并尝试相反取值；两个分支都失败
   则向上返回冲突。UNSAT 结论完全由搜索空间穷尽得出，**不存在任何
   超时猜测逻辑**。

### 统计输出

`Stats` 记录并在 CLI 中打印：

- `propagations` — 单元传播产生的赋值次数；
- `pure_literals` — 纯文字消除产生的赋值次数；
- `decisions` — 分支决策次数；
- `backtracks` — 决策分支被撤销（回溯）的次数。

### 模型与验证

SAT 时返回覆盖全部 `1..nvars` 的完整赋值：搜索中未被约束的变量属于
don't-care，任意取值都满足公式，求解器确定性地扩展为 `False`
（`SatSolver.complete_model`）。`verify_model(num_vars, clauses, model)`
可对原始子句逐条重新验证模型，CLI 在输出前也会自动自检。

## 使用方法

```bash
python3 sat_solver.py examples/sat.cnf    # 输出 SAT、模型与统计，退出码 0
python3 sat_solver.py examples/unsat.cnf  # 输出 UNSAT 与统计，退出码 1
```

程序内调用：

```python
from sat_solver import SatSolver, parse_dimacs, verify_model

num_vars, clauses = parse_dimacs(open("examples/sat.cnf").read())
result = SatSolver(num_vars, clauses).solve()
assert result.sat and verify_model(num_vars, clauses, result.model)
print(result.stats)
```

## 运行测试

所有测试直接在终端执行，无需任何第三方依赖：

```bash
python3 -m unittest discover -s tests -v
```

测试覆盖：

- SAT / UNSAT 基本实例与模型再验证；
- 单元传播（零决策求解）、纯文字消除；
- 深度回溯（4 鸽 3 洞鸽笼原理 UNSAT 实例）与失败分支回溯；
- DIMACS 各类格式错误（缺头部、越界文字、子句数不符、缺少 `%` 等）；
- 空公式、空子句、重复文字、tautology 的确定语义；
- 500 组随机小公式（1–5 变量，含空子句/重复文字/tautology），
  以穷举全部赋值的暴力搜索作为 oracle 逐一比对求解结果。
