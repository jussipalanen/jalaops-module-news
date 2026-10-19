"""The news, their tags and images in an SQLite database.

The database is a file in the module's data folder, which JalaOps gives the
module in JALAOPS_DATA_DIR ("storage": true in module.json). Images are kept
in the database as data, so deleting a news item deletes its images too.
"""

import base64
import os
import re
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone

SCHEMA_VERSION = 3

SCHEMA = """
CREATE TABLE news (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    short_description TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX news_newest ON news (created_at DESC, id DESC);

CREATE TABLE news_tags (
    news_id INTEGER NOT NULL REFERENCES news (id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY (news_id, tag)
);
CREATE INDEX news_tags_tag ON news_tags (tag);

CREATE TABLE news_media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    news_id INTEGER NOT NULL REFERENCES news (id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    mime TEXT NOT NULL,
    data BLOB NOT NULL,
    thumbnail_mime TEXT NOT NULL,
    thumbnail BLOB NOT NULL,
    alt TEXT NOT NULL DEFAULT ''
);
CREATE INDEX news_media_news ON news_media (news_id, position);
"""

MAX_SLUG = 80


def slugify(title):
    """A news item's address from its title: "Syyshuollot alkavat!" →
    "syyshuollot-alkavat". Never only digits, which would look like an id."""
    text = title.lower().translate(str.maketrans({"ä": "a", "ö": "o", "å": "a"}))
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:MAX_SLUG].rstrip("-") or "uutinen"
    return f"uutinen-{slug}" if slug.isdigit() else slug


def unique_slug(db, title):
    """slugify(title), with -2, -3… when another news item has it."""
    base = slugify(title)
    slug, number = base, 1
    while db.execute("SELECT 1 FROM news WHERE slug = ?", (slug,)).fetchone():
        number += 1
        slug = f"{base}-{number}"
    return slug


def add_slugs(db):
    """Gives the news that were saved before slugs one from their title, oldest first."""
    db.execute("ALTER TABLE news ADD COLUMN slug TEXT")
    for news_id, title in db.execute("SELECT id, title FROM news ORDER BY id").fetchall():
        db.execute("UPDATE news SET slug = ? WHERE id = ?", (unique_slug(db, title), news_id))
    db.execute("CREATE UNIQUE INDEX news_slug ON news (slug)")


# Changes to the schema after the first version, by the version they lead to:
# SQL, or a function that gets the database.
MIGRATIONS = {
    2: "ALTER TABLE news ADD COLUMN updated_at TEXT",
    3: add_slugs,
}


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def data_url(mime, data):
    return f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"


class NewsStore:
    def __init__(self, directory, seed=None, filename="news.sqlite3"):
        """seed(store) fills a database that was just created, e.g. with demo news."""
        os.makedirs(directory, exist_ok=True)
        self.db = sqlite3.connect(os.path.join(directory, filename), timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.migrate(seed)

    def migrate(self, seed):
        # The write lock is taken first, so two runs starting at the same time
        # can't both create the tables or save the demo news.
        self.db.execute("BEGIN IMMEDIATE")
        try:
            version = self.db.execute("PRAGMA user_version").fetchone()[0]
            if version < 1:
                for statement in SCHEMA.split(";"):
                    if statement.strip():
                        self.db.execute(statement)
            for target in range(max(version, 1) + 1, SCHEMA_VERSION + 1):
                migration = MIGRATIONS[target]
                migration(self.db) if callable(migration) else self.db.execute(migration)
            if version < SCHEMA_VERSION:
                self.db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            if version < 1 and seed:
                seed(self)
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        """Commits at the end, or rolls back on an error. Inside migrate()'s
        transaction (when seeding), migrate() commits instead."""
        if self.db.in_transaction:
            yield
            return
        with self.db:
            yield

    def create(self, title, short_description, content, tags, media, created_at=None):
        """Saves a news item and returns its id. media: dicts with mime, data,
        thumbnail_mime, thumbnail and alt. Its slug comes from the title and
        stays when the title changes, so links to it keep working."""
        with self.transaction():
            news_id = self.db.execute(
                "INSERT INTO news (title, slug, short_description, content, created_at) VALUES (?, ?, ?, ?, ?)",
                (title, unique_slug(self.db, title), short_description, content, created_at or now()),
            ).lastrowid
            self.db.executemany(
                "INSERT INTO news_tags (news_id, tag) VALUES (?, ?)",
                [(news_id, tag) for tag in tags],
            )
            self.db.executemany(
                "INSERT INTO news_media (news_id, position, mime, data, thumbnail_mime, thumbnail, alt)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (news_id, position, item["mime"], item["data"], item["thumbnail_mime"], item["thumbnail"], item["alt"])
                    for position, item in enumerate(media)
                ],
            )
        return news_id

    def update(self, news_id, title, short_description, content, tags, media):
        """Changes a news item. media is the new list of images in order:
        {"id", "alt"} keeps an image the item has, a dict like in create()
        adds one, and images left out are deleted. False when there was no
        such item; ValueError for an image id the item doesn't have."""
        with self.transaction():
            changed = self.db.execute(
                "UPDATE news SET title = ?, short_description = ?, content = ?, updated_at = ? WHERE id = ?",
                (title, short_description, content, now(), news_id),
            ).rowcount
            if not changed:
                return False

            existing = {row[0] for row in self.db.execute("SELECT id FROM news_media WHERE news_id = ?", (news_id,))}
            kept = {item["id"] for item in media if "id" in item}
            if not kept <= existing:
                raise ValueError("unknown image")

            self.db.executemany("DELETE FROM news_media WHERE id = ?", [(media_id,) for media_id in existing - kept])
            for position, item in enumerate(media):
                if "id" in item:
                    self.db.execute(
                        "UPDATE news_media SET position = ?, alt = ? WHERE id = ?",
                        (position, item["alt"], item["id"]),
                    )
                else:
                    self.db.execute(
                        "INSERT INTO news_media (news_id, position, mime, data, thumbnail_mime, thumbnail, alt)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (news_id, position, item["mime"], item["data"], item["thumbnail_mime"], item["thumbnail"], item["alt"]),
                    )

            self.db.execute("DELETE FROM news_tags WHERE news_id = ?", (news_id,))
            self.db.executemany("INSERT INTO news_tags (news_id, tag) VALUES (?, ?)", [(news_id, tag) for tag in tags])
        return True

    def delete(self, news_id):
        """Deletes a news item with its tags and images. False when there was none."""
        with self.transaction():
            return self.db.execute("DELETE FROM news WHERE id = ?", (news_id,)).rowcount > 0

    def find(self, key):
        """A news item with its content and full-size images, by its id (a
        number) or slug (a text), or None."""
        column = "id" if isinstance(key, int) else "slug"
        row = self.db.execute(f"SELECT * FROM news WHERE {column} = ?", (key,)).fetchone()
        if row is None:
            return None

        media = self.db.execute(
            "SELECT id, mime, data, thumbnail_mime, thumbnail, alt FROM news_media WHERE news_id = ? ORDER BY position",
            (row["id"],),
        ).fetchall()

        return {
            **self._summary(row),
            "content": row["content"],
            "media": [
                {
                    "id": item["id"],
                    "image": data_url(item["mime"], item["data"]),
                    "thumbnail": data_url(item["thumbnail_mime"], item["thumbnail"]),
                    "alt": item["alt"],
                }
                for item in media
            ],
        }

    def newest(self, limit, offset=0, tag=None):
        """The newest news first, without content, with the first image's
        thumbnail, and how many there are in all."""
        where, params = ("WHERE id IN (SELECT news_id FROM news_tags WHERE tag = ?)", [tag]) if tag else ("", [])
        total = self.db.execute(f"SELECT COUNT(*) FROM news {where}", params).fetchone()[0]
        rows = self.db.execute(
            f"SELECT * FROM news {where} ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
        return [self._summary(row) for row in rows], total

    def tags(self):
        """Every tag with how many news have it, the most used first."""
        rows = self.db.execute(
            "SELECT tag, COUNT(*) AS count FROM news_tags GROUP BY tag ORDER BY count DESC, tag"
        ).fetchall()
        return [{"tag": row["tag"], "count": row["count"]} for row in rows]

    def _summary(self, row):
        tags = [tag for (tag,) in self.db.execute("SELECT tag FROM news_tags WHERE news_id = ? ORDER BY tag", (row["id"],))]
        media = self.db.execute(
            "SELECT thumbnail_mime, thumbnail, alt, (SELECT COUNT(*) FROM news_media WHERE news_id = ?) AS count"
            " FROM news_media WHERE news_id = ? ORDER BY position LIMIT 1",
            (row["id"], row["id"]),
        ).fetchone()

        return {
            "id": row["id"],
            "slug": row["slug"],
            "title": row["title"],
            "short_description": row["short_description"],
            "tags": tags,
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "thumbnail": data_url(media["thumbnail_mime"], media["thumbnail"]) if media else None,
            "thumbnail_alt": media["alt"] if media else "",
            "media_count": media["count"] if media else 0,
        }
