# 砾川材料试验室双台架错峰复核

白班台架员把分段采测表录成固定修订。交班员按指定修订取件并独立实收。关站后，质控员以指定双件签发错峰报告。复测班按原号领取报告和出处，依孤立错峰或可选区间排班，空裁决时安排补测。更正另存修订和站件，可另签报告。

## 运行

使用 Python 3.11 标准库。在项目根目录执行平台提供的回归入口和隔离演示。

```sh
python3 -B check_project.py
python3 -B demo.py
```

直接运行完整 unittest 套件可使用 `python3 -B -m unittest discover -s tests -t .`。演示每次都在新临时目录建立四个 SQLite 库，从 `samples/shift.json` 读入样例，关站签发，更正后再次签发；再从 `samples/switch.json` 取超幅样例（`LC-switch-limit`）在关站后签发换档报告；最后关闭实收库、重开发布库，按原号核对旧报告、更正报告和换档报告。演示结束清理临时库。`POINTWISE_SCENARIO` 行包含实测裁决、换档裁决与重开后领取结果。

## 公开接口

- `station.storage.StationStore(path)` 持有登记和原测。`station.batches.register_batch(store, batch_id, a_bench, b_bench, unit)` 返回登记批号。相同定义可重登。`station.revisions.record_revision(store, batch_id, bench_id, rows)` 返回该台架的公开修订号。更正提交一份完整的新修订。
- `issue.archive.IssueArchive(path, issuer_id)` 持有已发行件。为每个独立发行库分配不同的发行方标识，重开沿用原标识。`issue.freeze.issue_piece(station, archive, batch_id, bench_id, revision_no)` 返回不可变 `FrozenPiece`。可通过 `issue.codec.encode_piece(piece)` 导出 UTF-8 JSON 字节，也可通过 `archive.load_piece(issue_id)` 领取归档件。
- `intake.storage.IntakeStore(path)` 持有中心实收。`intake.receive.receive_piece(store, piece_or_bytes)` 返回 `ReceivedPiece`，其中 `receipt_no` 和 `origin` 可用于后续复核。`intake.catalog.load_received_piece(store, receipt_no)` 按号取回该件。重送比较校验后的完整外层和有序正文，JSON 排版和等值有理数拼法归一化。相同发行号的出处或正文发生改变时拒收。
- `publication.storage.PublicationStore(path)` 持有签存报告。`analysis.request.review(intake, publication, a_receipt, b_receipt, lower, upper, minimum_coverage)` 校验参数、选择有序父件并签发。只需实收库和发布库。结果的 `decision.intervals` 为归并后的闭区间，`decision.minimum_mse` 为精确有理数或 `None`。`parents` 为有序实收号、发行号及出处，`receipt` 为本报告的唯一首执。
- `analysis.request.review_switch(intake, publication, a_receipt, b_receipt, cut, before_window, after_window, max_change, minimum_coverage)` 签发单次换档报告。两窗各为长度二的元组或列表，给下界、上界。按乙台源时刻 `cut` 切开乙台有效时段，前段用前档 `s1`、后段用后档 `s2` 平移甲台原时段不动，要求 `0 <= s2 - s1 <= max_change`。两侧覆盖与积分先各自合计再判资格。结果 `decision.minimum_mse` 为精确有理数或 `None`；`decision.regions` 为有限个闭有理凸集的并集，每项以凸包顶点序列表示（可含区域、线段、孤点与分离部分）；`decision.contains(s1, s2)` 判定任意档位对是否属于最优集合。请求读回时 `cut`、两窗端点、`max_change`、`minimum_coverage` 均为 `Fraction`。
- `publication.history.get_report(publication, report_no)` 按号领取固定的 `ReportRecord`，未知报告号返回 `None`。历史领取只使用发布库。

每个存储对象打开时初始化，也可调用 `initialize()` 重入。初始化保留现有数据和编号。使用完毕调用 `close()`。批次、台架、单位及发行方标识使用非空文本。公开修订号、实收号和报告号为各自存储范围内的正整数。

每个原测行是 `(start, end, value)`。时间单位为秒，读数使用登记时的共同单位。数值可为 `Fraction`、整数或 Python `Fraction` 接受的有理数字符串。`None` 表示缺测。所有时段左闭右开、起止严格递增，时段可以相接或留空档。有效零段有时长。站件公布带值有效时段以及批号、台架、角色、单位和公开修订号。原测行位置等内部信息保存在站端。

复核窗口 `[lower, upper]` 为闭区间，可以是单点。错峰 `s` 使乙台的时段整体加 `s`。共同覆盖达到正下限时才计为合格。均方差是共同有效时间上的差平方积分除以同一共同有效时长。连续错峰以端点差划分，在每一段内精确求覆盖边界并比较误差。覆盖等号、孤点和同分整段均保留。无合格错峰时空裁决也正式签存。

换档报告以乙台源时刻 `cut` 把乙台带值时段切成前、后两侧（跨切点的段按原值分属两段），前后档各在自身闭窗内平移。两段各自与甲台有效时段求交叠；先合计两侧覆盖再与下限比较，一侧覆盖为零时仍按合计判定。每个前段单元与前段档窗、每个后段单元与后段档窗的笛卡尔积内，覆盖与差平方积分都是 `(s1, s2)` 的仿射函数；在该单元的窗口矩形、`0 <= s2 - s1 <= max_change` 与 `覆盖 >= 下限` 的闭凸交上，均方差是仿射比，最小必在凸集的顶点或整集取到，水平集也是闭凸集，因而解集精确表达为有限个闭凸集的并。`decision.regions` 每项是一组闭凸包的顶点（逆时针、去共线内点）：单项为孤点、二项为线段、三项以上为（可能退化的）凸多边形，语义取并集。窗口外、跨窗或超出 `max_change` 的点任何 `region` 都不含。无合格对时 `regions` 为空、`minimum_mse` 为 `None`，`contains` 一律为假。

无效参数、登记冲突、非法件、同号异件及父件不相容抛出 `ValueError`。需要存在的批次、修订或实收号找不到时抛出 `LookupError`。SQLite 错误由存储层向上传递。签发在同一事务内写入报告、有序父件快照和首执，提交成功后才返回报告。历史领取可在实收库关闭后执行。
