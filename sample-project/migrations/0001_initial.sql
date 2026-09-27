CREATE TABLE book (isbn TEXT PRIMARY KEY, title TEXT NOT NULL, author TEXT NOT NULL);
CREATE TABLE loan (isbn TEXT NOT NULL REFERENCES book(isbn), member TEXT NOT NULL,
                   start DATE NOT NULL, due DATE NOT NULL, returned DATE);
