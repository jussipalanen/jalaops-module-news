"""Demo news, saved when the module's database is created.

The images are colour gradients drawn here as PNG files with the standard
library, so the module needs no image files or libraries.
"""

import struct
import zlib
from datetime import datetime, timedelta, timezone


def gradient_png(width, height, top, bottom):
    """A PNG image that fades from the colour top (r, g, b) to bottom."""
    rows = []
    for y in range(height):
        share = y / max(1, height - 1)
        pixel = bytes(round(a + (b - a) * share) for a, b in zip(top, bottom))
        rows.append(b"\x00" + pixel * width)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b"")


def banner(top, bottom, alt):
    return {
        "mime": "image/png",
        "data": gradient_png(960, 540, top, bottom),
        "thumbnail_mime": "image/png",
        "thumbnail": gradient_png(320, 180, top, bottom),
        "alt": alt,
    }


DEMO_NEWS = [
    {
        "hours_ago": 24 * 12,
        "title": "Tervetuloa JalaOpsin uutissyötteeseen",
        "short_description": "Täältä löydät huoltoyhtiön tiedotteet, vinkit ja ajankohtaiset asiat. Uusimmat näkyvät myös etusivulla.",
        "content": (
            "<p>Uutissyöte kokoaa yhteen kaikki tiedotteet. Uutiseen voi liittää kuvia ja tunnisteita, "
            "ja tunnisteella voi suodattaa listaa.</p>"
            "<h2>Näin kirjoitat uutisen</h2>"
            "<ol><li>Valitse <strong>Uusi uutinen</strong>.</li><li>Kirjoita otsikko, lyhyt kuvaus ja sisältö.</li>"
            "<li>Lisää tunnisteet ja kuvat, ja julkaise.</li></ol>"
        ),
        "tags": ["tiedote"],
        "media": [banner((16, 185, 129), (3, 105, 161), "Vihreästä siniseen vaihtuva liukuväri")],
    },
    {
        "hours_ago": 24 * 7,
        "title": "Pihavalaistus uusitaan LED-valaisimiin",
        "short_description": "Asunto Oy Koivurinteen pihavalaisimet vaihdetaan energiatehokkaisiin LED-valaisimiin viikolla 44.",
        "content": (
            "<p>Vanhat elohopealamput poistuvat käytöstä, ja tilalle tulee LED-valaisimet hämäräkytkimellä. "
            "Sähkönkulutus pienenee arviolta 60 %.</p>"
            "<table><thead><tr><th>Päivä</th><th>Työ</th></tr></thead>"
            "<tbody><tr><td>Ma</td><td>Vanhojen valaisimien purku</td></tr>"
            "<tr><td>Ti–ke</td><td>Asennus ja kytkentä</td></tr>"
            "<tr><td>To</td><td>Käyttöönotto ja tarkastus</td></tr></tbody></table>"
            "<p>Piha-alueella voi olla lyhyitä katkoja valaistuksessa iltaisin.</p>"
        ),
        "tags": ["sähkö", "huolto"],
        "media": [banner((253, 224, 71), (202, 138, 4), "Keltainen liukuväri")],
    },
    {
        "hours_ago": 24 * 4,
        "title": "Uusi asentaja aloitti tiimissämme",
        "short_description": "Uusi LVI-asentaja vahvistaa tiimiä Tampereen alueella lokakuusta alkaen.",
        "content": (
            "<p>Uudella asentajallamme on yli kymmenen vuoden kokemus putki- ja lämmitystöistä. Hän hoitaa jatkossa "
            "erityisesti Tampereen ja Pirkkalan kohteiden <em>LVI-huoltopyynnöt</em>.</p>"
            "<blockquote>Odotan innolla, että pääsen tutustumaan kohteisiin ja asukkaisiin.</blockquote>"
        ),
        "tags": ["tiedote", "lvi"],
        "media": [],
    },
    {
        "hours_ago": 50,
        "title": "Syyshuollot alkavat",
        "short_description": "Ilmanvaihdon suodattimet ja rännit tarkistetaan lokakuun aikana kaikissa kohteissa.",
        "content": (
            "<p>Syyshuoltokierros alkaa ensi viikolla. Käymme läpi kaikki sopimuskohteet lokakuun loppuun mennessä.</p>"
            "<h2>Mitä tarkistetaan</h2>"
            "<ul><li>Ilmanvaihtokoneiden suodattimet</li><li>Rännit ja syöksytorvet</li>"
            "<li>Ulkovalaistuksen hämäräkytkimet</li></ul>"
            "<p>Kirjaa huomatut viat suoraan <strong>huoltopyynnöksi</strong>, niin ne eivät unohdu.</p>"
        ),
        "tags": ["huolto", "syksy"],
        "media": [banner((251, 146, 60), (180, 83, 9), "Oranssi syksyinen liukuväri")],
    },
    {
        "hours_ago": 26,
        "title": "Työaikalaskuri on otettu käyttöön",
        "short_description": "Työkalut-sivun uusi moduuli laskee tehdyt tunnit, ylityön ja työn hinnan.",
        "content": (
            "<p>Työaikalaskuri löytyy kohdasta <em>Työkalut → Moduulit</em>. Anna alkamis- ja päättymisaika, "
            "tauot ja halutessasi tuntihinta.</p>"
            "<blockquote>Yli kahdeksan tunnin päivästä laskuri näyttää ylityön erikseen.</blockquote>"
        ),
        "tags": ["tiedote", "työkalut"],
        "media": [],
    },
    {
        "hours_ago": 3,
        "title": "Muista sulkea ulkovesipisteet ennen pakkasia",
        "short_description": "Jäätyvä vesi rikkoo ulkohanat ja putket. Tarkista kohteet ennen ensimmäisiä pakkasöitä.",
        "content": (
            "<p>Ennustettu ensimmäinen pakkasyö on ensi viikolla. Sulje ulkovesipisteiden sulkuventtiilit "
            "ja tyhjennä hanat.</p>"
            "<ol><li>Sulje sisäpuolen sulkuventtiili.</li><li>Avaa ulkohana ja anna veden valua pois.</li>"
            "<li>Jätä hana auki talveksi.</li></ol>"
            "<p>Lisätietoja: <a href=\"https://www.ilmatieteenlaitos.fi\">Ilmatieteen laitos</a>.</p>"
        ),
        "tags": ["talvi", "vinkit"],
        "media": [
            banner((56, 189, 248), (30, 64, 175), "Sininen talvinen liukuväri"),
            banner((226, 232, 240), (100, 116, 139), "Harmaa liukuväri"),
        ],
    },
]


def seed(store):
    """Saves the demo news, the oldest first."""
    for item in DEMO_NEWS:
        created_at = datetime.now(timezone.utc) - timedelta(hours=item["hours_ago"])
        store.create(
            item["title"],
            item["short_description"],
            item["content"],
            item["tags"],
            item["media"],
            created_at=created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        )
