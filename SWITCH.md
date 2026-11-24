# 一次换档的错峰签报

夜班可以按指定的乙台源时刻换一次错峰档。时间、档位和覆盖均以秒计。前档对应切点之前的乙台有效时段，后档对应从切点起的乙台有效时段。跨切点的有效段分属两侧，读值沿用该段原值。切点可以落在空档或有效时段之外。甲台原时段保持原位。

## 签发与领取

通过 `analysis.request.review_switch(intake, publication, a_receipt, b_receipt, cut, before_window, after_window, max_change, minimum_coverage)` 签发。两个窗各以长度为二的元组或列表传入，依次给下界、上界。沿用 `README.md` 的精确有理数、实收选件和错误规则。闭窗可以是单点，`max_change` 可为零，`minimum_coverage` 必须为正。

用前后档位 `(s1, s2)` 分别平移对应的乙台时段，要求 `0 <= s2 - s1 <= max_change`。各侧用自身与甲台有效时段的交叠计算覆盖与差平方积分。先分别合计两侧覆盖和两侧积分，再按总覆盖判资格并计算均方差。覆盖恰等于下限时合格，一侧覆盖为零时仍以合计结果判定。

签发返回含 `report_no`、`request`、`decision`、`parents`、`receipt` 的报告。`request` 保留调用中两枚实收号及 `cut`、`before_window`、`after_window`、`max_change`、`minimum_coverage`，读回数值为 `Fraction`，窗口端点用与旧报告相同的 `start`、`end` 访问。`decision.minimum_mse` 是 `Fraction` 或 `None`。`decision.regions` 提供有限个闭有理凸集，具体表示由实现决定并随交付说明。`decision.contains(s1, s2)` 接受与签发参数相同的有理数类型，返回该档位对是否在最优集合中。表示可分片，语义取并集。空裁决的 `regions` 为空，`minimum_mse` 为 `None`，任意合法档位对的成员判定为假。

签发沿用原有父件次序和首执口径。提交失败时，报告、父件和首执均无部分记录，旧报告照常领取。`publication.history.get_report(publication, report_no)` 只依赖发布库，按原号领回签发时的完整请求、裁决、父件及首执。原有 `review` 和单档报告继续使用原接口和口径。

## 样例与核验

`samples/switch.json` 的每组 `a_rows`、`b_rows` 均可用现有原测登记与发行流程独立提交和实收。取实际实收号，把该组 `request` 作为其余参数送给 `review_switch`。样例中的 `hulls` 用点的闭凸包列出期望集合，每项分别取凸包后求并集。这是样例的对照写法，交付可以使用其他等价表示。

- `LC-switch-limit` 的最优线段含两端及 `(1/4, 3/4)`，排除 `(0, 1)` 和 `(0, 0)`。
- `LC-split-coverage` 在乙台单个原段内切分。最优线段上覆盖恰为 `3/2` 秒。只把合计覆盖下限改为 `2` 时，应签发空集。
- `LC-separated` 仅含 `(0, 0)` 与 `(3, 3)`，排除 `(3/2, 3/2)`。`LC-flat` 则包含二维区域，含 `(1/4, 1/2)`。
- `LC-weighted` 按两侧各自的共同有效时长加权。`LC-one-side` 中后侧无共同覆盖，前侧恰好补足总覆盖下限。

沿用 `.pointwise-runtime.json` 的版本 1 CLI 清单接通交付。`setup` 列准备命令的参数数组，`verify` 和 `demo` 各取一个命令的参数数组。核验继续运行完整原回归，并断言换档签发结果以及关实收、重开发布库后的领取结果，失败时以非零退出。演示用超幅样例在关站后签发，关闭实收库并重开发布库，展示按原号领回的精确裁决和出处。
