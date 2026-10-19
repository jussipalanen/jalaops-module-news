"""Tests for the news module. Run them with: python3 -m unittest"""

import base64
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import demo  # noqa: E402
from news_html import paragraphs, plain_text, sanitize  # noqa: E402

PNG = demo.gradient_png(4, 3, (255, 0, 0), (0, 0, 255))
PNG_URL = "data:image/png;base64," + base64.b64encode(PNG).decode()


def run(data_dir, payload):
    """Runs main.py the way JalaOps does: JSON in on stdin, out on stdout."""
    result = subprocess.run(
        [sys.executable, "-E", "-s", "-B", "-X", "utf8", "main.py"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        cwd=ROOT,
        env={"PATH": os.environ.get("PATH", ""), "LANG": "C.UTF-8", "JALAOPS_DATA_DIR": data_dir},
        timeout=20,
    )
    if result.returncode != 0:
        return None, result.stderr.strip().splitlines()[-1]
    return json.loads(result.stdout), None


class SanitizeTest(unittest.TestCase):
    def test_it_keeps_formatting(self):
        html = '<h2>Otsikko</h2><p>Teksti <strong>lihava</strong> ja <em>kursiivi</em>.</p><ul><li>Yksi</li></ul>'
        self.assertEqual(sanitize(html), html)

    def test_it_removes_scripts_styles_and_event_handlers(self):
        self.assertEqual(
            sanitize('<p onclick="alert(1)" style="color:red">Hei</p><script>alert(1)</script><style>p{}</style>'),
            "<p>Hei</p>",
        )
        self.assertEqual(sanitize('<img src=x onerror="alert(1)"><svg><script>alert(1)</script></svg>Hei'), "Hei")
        self.assertEqual(sanitize("<iframe src='https://example.com'></iframe><p>ok</p>"), "<p>ok</p>")

    def test_links_open_in_a_new_tab_and_only_safe_schemes_stay(self):
        self.assertEqual(
            sanitize('<a href="https://example.com/?a=1&b=2">x</a>'),
            '<a href="https://example.com/?a=1&amp;b=2" target="_blank" rel="noopener noreferrer">x</a>',
        )
        for href in ["javascript:alert(1)", "java\tscript:alert(1)", " JAVASCRIPT:alert(1)", "data:text/html,x", "/relative"]:
            self.assertEqual(sanitize(f'<a href="{href}">x</a>'), '<a target="_blank" rel="noopener noreferrer">x</a>', href)

    def test_text_is_escaped_and_tags_are_closed(self):
        self.assertEqual(sanitize("<p>1 &lt; 2 & <b>3"), "<p>1 &lt; 2 &amp; <b>3</b></p>")
        self.assertEqual(sanitize("<ul><li>a<li>b</ul>"), "<ul><li>a<li>b</li></li></ul>")
        self.assertEqual(sanitize("</p>loppu"), "loppu")

    def test_headings_start_from_h2(self):
        self.assertEqual(sanitize("<h1>A</h1><h6>B</h6>"), "<h2>A</h2><h4>B</h4>")

    def test_unknown_tags_keep_their_text(self):
        self.assertEqual(sanitize("<article><p>Hei</p></article><form><input></form>"), "<p>Hei</p>")

    def test_plain_text_becomes_paragraphs(self):
        self.assertEqual(paragraphs("Eka <strong>rivi</strong>\n\nToinen"), "<p>Eka <strong>rivi</strong></p><p>Toinen</p>")
        self.assertEqual(paragraphs("1 < 2\n\n3 > 2"), "<p>1 &lt; 2</p><p>3 &gt; 2</p>")
        self.assertEqual(paragraphs("Eka rivi\ntoinen\n\n  \nUusi & kappale"), "<p>Eka rivi<br>toinen</p><p>Uusi &amp; kappale</p>")
        self.assertEqual(paragraphs("<p>Valmis</p>\n\n<ul><li>a</li></ul>"), "<p>Valmis</p>\n\n<ul><li>a</li></ul>")

    def test_plain_text(self):
        self.assertEqual(plain_text("<h2>Otsikko</h2><p>Hei&nbsp;<b>sinä</b></p><script>x</script>"), "Otsikko Hei sinä")
        self.assertEqual(plain_text("<p>&nbsp;</p>"), "")


class ModuleTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.data_dir = self.directory.name

    def tearDown(self):
        self.directory.cleanup()

    def create(self, **fields):
        payload = {"action": "create", "title": "Testi", "short_description": "Lyhyesti", "content": "<p>Sisältö</p>", **fields}
        return run(self.data_dir, payload)

    def test_a_new_database_has_the_demo_news_newest_first(self):
        output, error = run(self.data_dir, {"action": "list"})

        self.assertIsNone(error)
        self.assertEqual(output["total"], len(demo.DEMO_NEWS))
        self.assertEqual(output["items"][0]["title"], "Muista sulkea ulkovesipisteet ennen pakkasia")
        self.assertTrue(output["items"][0]["thumbnail"].startswith("data:image/png;base64,"))
        self.assertEqual(output["items"][0]["media_count"], 2)
        self.assertNotIn("content", output["items"][0])
        self.assertEqual(output["tags"][:2], [{"tag": "tiedote", "count": 3}, {"tag": "huolto", "count": 2}])

    def test_it_creates_shows_and_deletes_a_news_item(self):
        created, error = self.create(
            title="  Uusi uutinen ",
            content='<p onclick="x()">Hei <a href="javascript:x()">linkki</a></p>',
            tags=["Huolto", "#huolto", " LVI  työt "],
            media=[{"image": PNG_URL, "alt": "Kuva"}],
        )
        self.assertIsNone(error)
        news = created["news"]
        self.assertEqual(news["title"], "Uusi uutinen")
        self.assertEqual(news["tags"], ["huolto", "lvi työt"])
        self.assertEqual(news["content"], '<p>Hei <a target="_blank" rel="noopener noreferrer">linkki</a></p>')
        self.assertEqual(news["media"][0]["image"], PNG_URL)
        self.assertEqual(news["media"][0]["thumbnail"], PNG_URL)
        self.assertEqual(news["media"][0]["alt"], "Kuva")

        shown, _ = run(self.data_dir, {"action": "get", "id": str(news["id"])})
        self.assertEqual(shown["news"]["title"], "Uusi uutinen")

        listed, _ = run(self.data_dir, {"action": "list", "tag": "LVI työt"})
        self.assertEqual([item["id"] for item in listed["items"]], [news["id"]])

        deleted, _ = run(self.data_dir, {"action": "delete", "id": news["id"]})
        self.assertEqual(deleted, {"deleted": news["id"]})
        _, error = run(self.data_dir, {"action": "get", "id": news["id"]})
        self.assertEqual(error, "Uutista ei löytynyt. Se on ehkä poistettu.")
        _, error = run(self.data_dir, {"action": "delete", "id": news["id"]})
        self.assertEqual(error, "Uutista ei löytynyt. Se on ehkä jo poistettu.")

    def test_it_updates_a_news_item_and_its_images(self):
        created, _ = self.create(
            tags=["vanha"],
            media=[{"image": PNG_URL, "alt": "Eka"}, {"image": PNG_URL, "alt": "Toka"}],
        )
        news = created["news"]
        first, second = news["media"]
        self.assertIsNone(news["updated_at"])

        updated, error = run(self.data_dir, {
            "action": "update",
            "id": news["id"],
            "title": "Muokattu",
            "short_description": "Uusi kuvaus",
            "content": "Teksti\n\nToinen",
            "tags": ["uusi"],
            # The second image first with a new caption, the first one deleted, and a new one.
            "media": [{"id": second["id"], "alt": "Toka muokattu"}, {"image": PNG_URL, "alt": "Kolmas"}],
        })

        self.assertIsNone(error)
        news = updated["news"]
        self.assertEqual(news["title"], "Muokattu")
        self.assertEqual(news["content"], "<p>Teksti</p><p>Toinen</p>")
        self.assertEqual(news["tags"], ["uusi"])
        self.assertEqual([item["alt"] for item in news["media"]], ["Toka muokattu", "Kolmas"])
        self.assertEqual(news["media"][0]["id"], second["id"])
        self.assertRegex(news["updated_at"], r"^\d{4}-\d\d-\d\dT")

        listed, _ = run(self.data_dir, {"action": "list", "tag": "vanha"})
        self.assertEqual(listed["total"], 0)

    def test_an_update_is_checked(self):
        created, _ = self.create(media=[{"image": PNG_URL}])
        other, _ = self.create(media=[{"image": PNG_URL}])
        fields = {"action": "update", "title": "T", "short_description": "S", "content": "C"}

        self.assertEqual(run(self.data_dir, {**fields, "id": 9999})[1], "Uutista ei löytynyt. Se on ehkä poistettu.")
        self.assertEqual(run(self.data_dir, {**fields, "id": created["news"]["id"], "title": ""})[1], "Otsikko: pakollinen tieto.")

        # An image of another news item can't be taken over, and nothing changes.
        self.assertEqual(
            run(self.data_dir, {**fields, "id": created["news"]["id"], "media": [{"id": other["news"]["media"][0]["id"]}]})[1],
            "Kuvaa ei löytynyt. Lataa sivu uudelleen ja yritä uudestaan.",
        )
        shown, _ = run(self.data_dir, {"action": "get", "id": created["news"]["id"]})
        self.assertEqual(shown["news"]["title"], "Testi")
        self.assertEqual(len(shown["news"]["media"]), 1)

    def test_a_version_1_database_is_upgraded(self):
        import sqlite3

        from news_store import SCHEMA

        db = sqlite3.connect(os.path.join(self.data_dir, "news.sqlite3"))
        db.executescript(SCHEMA)
        db.execute("INSERT INTO news (title, short_description, content, created_at) VALUES ('Vanha', 'S', '<p>C</p>', '2026-01-01T00:00:00Z')")
        db.execute("PRAGMA user_version = 1")
        db.commit()
        db.close()

        output, error = run(self.data_dir, {"action": "list"})

        self.assertIsNone(error)
        # Upgrading doesn't add the demo news to an existing database.
        self.assertEqual([item["title"] for item in output["items"]], ["Vanha"])
        self.assertIsNone(output["items"][0]["updated_at"])

    def test_the_feed_is_in_the_dashboard_format(self):
        created, _ = self.create(title="Tuorein")
        output, error = run(self.data_dir, {"action": "feed", "limit": 2})

        self.assertIsNone(error)
        self.assertEqual(len(output["items"]), 2)
        self.assertEqual(output["items"][0]["title"], "Tuorein")
        self.assertEqual(output["items"][0]["text"], "Lyhyesti")
        self.assertEqual(output["items"][0]["params"], {"news": str(created["news"]["id"])})
        self.assertIsNone(output["items"][0]["image"])
        self.assertRegex(output["items"][0]["date"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_it_checks_the_input(self):
        cases = [
            ({"title": ""}, "Otsikko: pakollinen tieto."),
            ({"title": "x" * 151}, "Otsikko: enintään 150 merkkiä."),
            ({"short_description": 5}, "Lyhyt kuvaus: anna tekstiä."),
            ({"content": "<script>alert(1)</script>"}, "Sisältö: kirjoita uutiseen tekstiä."),
            ({"tags": "huolto"}, "Tunnisteet: anna lista tekstejä."),
            ({"tags": [f"t{n}" for n in range(11)]}, "Tunnisteita voi olla enintään 10."),
            ({"media": [{"image": "https://example.com/kuva.jpg"}]}, "Kuva 1: kuvan pitää olla data-URL."),
            ({"media": [{"image": "data:image/svg+xml;base64,PHN2Zz4="}]}, "Kuva 1: sallitut kuvat ovat JPEG, PNG, GIF ja WebP."),
            ({"media": [{"image": "data:image/jpeg;base64," + base64.b64encode(PNG).decode()}]}, "Kuva 1: tiedosto ei ole JPEG-kuva."),
            ({"media": [{"image": "data:image/png;base64,***"}]}, "Kuva 1: kuvan data on virheellistä."),
            ({"media": [{"image": PNG_URL}] * 7}, "Kuvia voi olla enintään 6."),
        ]
        for fields, message in cases:
            with self.subTest(fields=str(fields)[:60]):
                self.assertEqual(self.create(**fields), (None, message))

        self.assertEqual(run(self.data_dir, {"action": "publish"})[1], "Tuntematon toiminto. Sallitut: list, get, create, update, delete, feed, tags.")
        self.assertEqual(run(self.data_dir, {"action": "get", "id": True})[1], "Uutisen tunniste puuttuu tai on virheellinen.")
        self.assertEqual(run(self.data_dir, {"action": "list", "limit": 500})[1], "limit: anna kokonaisluku 1–50.")

    def test_it_needs_a_data_folder(self):
        result = subprocess.run(
            [sys.executable, "main.py"], input="{}", capture_output=True, text=True, cwd=ROOT,
            env={"PATH": os.environ.get("PATH", "")},
        )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr.strip(), "Moduulilla ei ole tallennuskansiota (JALAOPS_DATA_DIR).")


if __name__ == "__main__":
    unittest.main()
