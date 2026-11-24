# Legacy: the original notebook, verbatim

`dual_thrust_v1.py` is the single code cell of
`notebooks/DualThrust 信号.ipynb`, extracted without a single edit.

It is a straight-line script for one stock (`sh.600519`) against one benchmark
(`sh.000300`), 2022–2025, with baostock forward-adjusted daily bars. It prints
the summary and the trade list; it writes nothing to disk.

What this repo keeps exactly:

- the band construction (`HH/LC/HC/LL` over the prior *n* bars, `shift(1)`)
- the daily order: index stop → stock stop → band exit → band entry
- close-price fills
- the stop thresholds (−3% index, −6% / −8% stock)

What this repo adds around it: the engine split into pure functions, an
adapter + CLI, CSV output, and a synthetic demo with four figures.
