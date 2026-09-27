import unittest
from datetime import date

from shelfkeep.catalog import Book, Catalog
from shelfkeep.loans import LoanBook


class LoanBookTest(unittest.TestCase):
    def setUp(self):
        catalog = Catalog()
        catalog.add(Book("111", "Dune", "Frank Herbert"))
        catalog.add(Book("222", "Emma", "Jane Austen"))
        self.loans = LoanBook(catalog, loan_days=14)

    def test_checkout_sets_due_date(self):
        loan = self.loans.checkout("111", "ana", date(2026, 1, 1))
        self.assertEqual(loan.due, date(2026, 1, 15))

    def test_checkout_unknown_book(self):
        with self.assertRaises(KeyError):
            self.loans.checkout("999", "ana", date(2026, 1, 1))

    def test_double_checkout_rejected(self):
        self.loans.checkout("111", "ana", date(2026, 1, 1))
        with self.assertRaises(ValueError):
            self.loans.checkout("111", "ben", date(2026, 1, 2))

    def test_return_then_checkout_again(self):
        self.loans.checkout("111", "ana", date(2026, 1, 1))
        self.loans.return_book("111", date(2026, 1, 5))
        self.assertIsNone(self.loans.active_loan("111"))
        self.loans.checkout("111", "ben", date(2026, 1, 6))

    def test_return_not_on_loan(self):
        with self.assertRaises(ValueError):
            self.loans.return_book("222", date(2026, 1, 1))

    def test_overdue(self):
        self.loans.checkout("111", "ana", date(2026, 1, 1))
        self.loans.checkout("222", "ben", date(2026, 1, 10))
        self.assertEqual([l.isbn for l in self.loans.overdue(date(2026, 1, 16))], ["111"])
        self.assertEqual(self.loans.overdue(date(2026, 1, 15)), [])

    def test_loan_days_must_be_positive(self):
        with self.assertRaises(ValueError):
            LoanBook(Catalog(), loan_days=0)
