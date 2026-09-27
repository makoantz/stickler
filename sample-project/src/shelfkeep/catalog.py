"""Book catalog."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Book:
    isbn: str
    title: str
    author: str


class Catalog:
    def __init__(self):
        self._books = {}

    def add(self, book):
        if not book.isbn.strip():
            raise ValueError("isbn is required")
        if book.isbn in self._books:
            raise ValueError(f"duplicate isbn: {book.isbn}")
        self._books[book.isbn] = book

    def get(self, isbn):
        try:
            return self._books[isbn]
        except KeyError:
            raise KeyError(f"unknown isbn: {isbn}") from None

    def search(self, text):
        needle = text.casefold()
        hits = (
            b for b in self._books.values()
            if needle in b.title.casefold() or needle in b.author.casefold()
        )
        return sorted(hits, key=lambda b: b.title)

    def __len__(self):
        return len(self._books)
