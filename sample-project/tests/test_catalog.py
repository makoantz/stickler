import unittest

from shelfkeep.catalog import Book, Catalog


class CatalogTest(unittest.TestCase):
    def setUp(self):
        self.catalog = Catalog()
        self.catalog.add(Book("111", "Dune", "Frank Herbert"))
        self.catalog.add(Book("222", "Emma", "Jane Austen"))

    def test_get(self):
        self.assertEqual(self.catalog.get("111").title, "Dune")

    def test_get_unknown(self):
        with self.assertRaises(KeyError):
            self.catalog.get("999")

    def test_duplicate_rejected(self):
        with self.assertRaises(ValueError):
            self.catalog.add(Book("111", "Other", "Someone"))

    def test_blank_isbn_rejected(self):
        with self.assertRaises(ValueError):
            self.catalog.add(Book("  ", "Blank", "Nobody"))

    def test_search_title_and_author_case_insensitive(self):
        self.assertEqual([b.isbn for b in self.catalog.search("AUSTEN")], ["222"])
        self.assertEqual([b.isbn for b in self.catalog.search("e")], ["111", "222"])

    def test_len(self):
        self.assertEqual(len(self.catalog), 2)
