# Synthetic chart of accounts

`synthetic_chart.csv` is **made up** for test data. It is not the official Enotni kontni okvir (SIR), which has not been located yet (see `docs/research/ajpes.md`).

- Every konto's 2-digit group is one that the AJPES form allows for its AOP line (validated in `argus.chart`).
- `weight`: share of the AOP line amount allocated to the konto. Contra accounts (popravki vrednosti) have negative weights. The weights for each AOP line sum to 1.
- Pairs (068/069, 070/071) are mapped to the profit side. A negative amount moves to the loss side.
