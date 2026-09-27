"""Loans of catalog books to members."""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional


@dataclass
class Loan:
    isbn: str
    member: str
    start: date
    due: date
    returned: Optional[date] = None


class LoanBook:
    def __init__(self, catalog, loan_days):
        if loan_days <= 0:
            raise ValueError("loan_days must be positive")
        self._catalog = catalog
        self._loan_days = loan_days
        self._loans = []

    def checkout(self, isbn, member, today):
        self._catalog.get(isbn)
        if self.active_loan(isbn) is not None:
            raise ValueError(f"already on loan: {isbn}")
        loan = Loan(isbn, member, today, today + timedelta(days=self._loan_days))
        self._loans.append(loan)
        return loan

    def return_book(self, isbn, today):
        loan = self.active_loan(isbn)
        if loan is None:
            raise ValueError(f"not on loan: {isbn}")
        loan.returned = today
        return loan

    def active_loan(self, isbn):
        for loan in self._loans:
            if loan.isbn == isbn and loan.returned is None:
                return loan
        return None

    def overdue(self, today):
        return [l for l in self._loans if l.returned is None and l.due < today]
