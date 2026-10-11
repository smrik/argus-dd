"""Tidy trial balance: one row per konto, amounts in integer cents, debit positive."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TbRow:
    konto: str
    name: str
    opening: int
    debit: int  # turnover in the period (promet v breme)
    credit: int  # turnover in the period (promet v dobro)
    closing: int


def column(rows, field):
    """{konto: amount} for 'opening' or 'closing'."""
    return {r.konto: getattr(r, field) for r in rows}
