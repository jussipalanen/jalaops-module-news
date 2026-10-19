"""News feed module for JalaOps: news with tags and images.

JalaOps runs this program with a JSON object on stdin and reads a JSON object
from stdout. The input's "action" says what to do:

    {"action": "list", "tag": "huolto", "limit": 20, "offset": 0}
        → {"items": [...], "total": 3, "tags": [{"tag": "huolto", "count": 1}]}
    {"action": "get", "id": 3}
        → {"news": {"id": 3, "title": ..., "content": "<p>…</p>", "media": [...]}}
    {"action": "create", "title": ..., "short_description": ..., "content": "<p>…</p>",
     "tags": ["huolto"], "media": [{"image": "data:image/jpeg;base64,…", "thumbnail": "data:…", "alt": ""}]}
        → {"news": {...}}
    {"action": "update", "id": 3, "title": ..., "short_description": ..., "content": ..., "tags": [...],
     "media": [{"id": 7, "alt": "kept"}, {"image": "data:image/jpeg;base64,…", "alt": "new"}]}
        → {"news": {...}}
    {"action": "delete", "id": 3}
        → {"deleted": 3}
    {"action": "feed", "limit": 5}
        → {"items": [{"title": ..., "text": ..., "date": ..., "image": ..., "params": {"news": "3"}}]}

"feed" is the JalaOps dashboard's format ("dashboard" in module.json). The
news are kept in an SQLite database in the folder JALAOPS_DATA_DIR.

Try it: JALAOPS_DATA_DIR=/tmp/news python3 main.py <<< '{"action": "list"}'
"""

import base64
import binascii
import json
import os
import sys

import demo
from news_html import paragraphs, plain_text, sanitize
from news_store import NewsStore

MAX_TITLE = 150
MAX_SHORT_DESCRIPTION = 300
MAX_CONTENT = 50_000
MAX_TAGS = 10
MAX_TAG = 30
MAX_MEDIA = 6
MAX_IMAGE_BYTES = 1_500_000
MAX_THUMBNAIL_BYTES = 150_000
MAX_ALT = 200

# Image types and how their files start.
IMAGE_TYPES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/webp": (b"RIFF",),
}


class InputError(Exception):
    """A problem with the input; the message is shown to the user in Finnish."""


def fail(message):
    """Ends with an error; the app shows the message to the user."""
    print(message, file=sys.stderr)
    sys.exit(1)


def text(data, name, label, maximum, required=True):
    value = data.get(name)
    # An optional text can also be left out or null.
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise InputError(f"{label}: anna tekstiä.")
    value = value.strip()
    if required and not value:
        raise InputError(f"{label}: pakollinen tieto.")
    if len(value) > maximum:
        raise InputError(f"{label}: enintään {maximum} merkkiä.")
    return value


def whole_number(data, name, default, minimum, maximum):
    value = data.get(name, default)
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise InputError(f"{name}: anna kokonaisluku {minimum}–{maximum}.")
    return value


def news_id(data):
    value = data.get("id")
    # The id may come from a page address as text.
    if isinstance(value, str) and value.isdigit():
        value = int(value)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise InputError("Uutisen tunniste puuttuu tai on virheellinen.")
    return value


def tag_list(value):
    """Tags in lower case without repeats, in the given order."""
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(tag, str) for tag in value):
        raise InputError("Tunnisteet: anna lista tekstejä.")

    tags = []
    for tag in value:
        tag = " ".join(tag.split()).lower().lstrip("#")
        if not tag or tag in tags:
            continue
        if len(tag) > MAX_TAG or "," in tag:
            raise InputError(f"Tunniste ”{tag[:MAX_TAG]}…”: enintään {MAX_TAG} merkkiä, ei pilkkuja.")
        tags.append(tag)

    if len(tags) > MAX_TAGS:
        raise InputError(f"Tunnisteita voi olla enintään {MAX_TAGS}.")
    return tags


def image(value, label, maximum):
    """The type and bytes of a base64 data URL of an image."""
    if not isinstance(value, str) or not value.startswith("data:") or ";base64," not in value:
        raise InputError(f"{label}: kuvan pitää olla data-URL.")

    mime, encoded = value[5:].split(";base64,", 1)
    if mime not in IMAGE_TYPES:
        raise InputError(f"{label}: sallitut kuvat ovat JPEG, PNG, GIF ja WebP.")

    # The encoded size is about 4/3 of the bytes, so too big images are
    # turned away before decoding.
    if len(encoded) > maximum * 4 // 3 + 4:
        raise InputError(f"{label}: kuva on liian suuri (enintään {maximum // 1000} kt).")

    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise InputError(f"{label}: kuvan data on virheellistä.") from None

    if not data.startswith(IMAGE_TYPES[mime]) or (mime == "image/webp" and data[8:12] != b"WEBP"):
        raise InputError(f"{label}: tiedosto ei ole {mime.removeprefix('image/').upper()}-kuva.")
    return mime, data


def media_list(value, existing=False):
    """Images from the input. With existing=True (when updating), an item
    can also be {"id": 7, "alt": "…"}, an image the news item already has."""
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise InputError("Kuvat: anna lista kuvia.")
    if len(value) > MAX_MEDIA:
        raise InputError(f"Kuvia voi olla enintään {MAX_MEDIA}.")

    media = []
    for number, item in enumerate(value, start=1):
        label = f"Kuva {number}"

        if existing and "id" in item:
            media_id = item["id"]
            if not isinstance(media_id, int) or isinstance(media_id, bool) or media_id < 1:
                raise InputError(f"{label}: virheellinen kuvan tunniste.")
            media.append({"id": media_id, "alt": text(item, "alt", f"{label}: kuvateksti", MAX_ALT, required=False)})
            continue

        mime, data = image(item.get("image"), label, MAX_IMAGE_BYTES)

        if item.get("thumbnail") is not None:
            thumbnail_mime, thumbnail = image(item["thumbnail"], f"{label} (pienoiskuva)", MAX_THUMBNAIL_BYTES)
        elif len(data) <= MAX_THUMBNAIL_BYTES:
            thumbnail_mime, thumbnail = mime, data
        else:
            raise InputError(f"{label}: lisää pienoiskuva, kun kuva on yli {MAX_THUMBNAIL_BYTES // 1000} kt.")

        media.append({
            "mime": mime,
            "data": data,
            "thumbnail_mime": thumbnail_mime,
            "thumbnail": thumbnail,
            "alt": text(item, "alt", f"{label}: kuvateksti", MAX_ALT, required=False),
        })
    return media


def list_news(store, data):
    tag = data.get("tag")
    if tag is not None and not isinstance(tag, str):
        raise InputError("Tunniste: anna tekstiä.")

    items, total = store.newest(
        whole_number(data, "limit", 20, 1, 50),
        whole_number(data, "offset", 0, 0, 1_000_000),
        tag.strip().lower() if tag else None,
    )
    return {"items": items, "total": total, "tags": store.tags()}


def get_news(store, data):
    news = store.find(news_id(data))
    if news is None:
        raise InputError("Uutista ei löytynyt. Se on ehkä poistettu.")
    # Sanitized again, in case the allowlist has been tightened since it was saved.
    news["content"] = sanitize(news["content"])
    return {"news": news}


def news_fields(data):
    """The title, short description and content of a news item from the input."""
    title = text(data, "title", "Otsikko", MAX_TITLE)
    short_description = text(data, "short_description", "Lyhyt kuvaus", MAX_SHORT_DESCRIPTION)
    content = sanitize(paragraphs(text(data, "content", "Sisältö", MAX_CONTENT)))

    if not plain_text(content):
        raise InputError("Sisältö: kirjoita uutiseen tekstiä.")
    return title, short_description, content


def create_news(store, data):
    news_id = store.create(*news_fields(data), tag_list(data.get("tags")), media_list(data.get("media")))
    return {"news": store.find(news_id)}


def update_news(store, data):
    news_id_ = news_id(data)
    fields = news_fields(data)
    tags = tag_list(data.get("tags"))
    media = media_list(data.get("media"), existing=True)

    try:
        updated = store.update(news_id_, *fields, tags, media)
    except ValueError:
        raise InputError("Kuvaa ei löytynyt. Lataa sivu uudelleen ja yritä uudestaan.") from None

    if not updated:
        raise InputError("Uutista ei löytynyt. Se on ehkä poistettu.")
    return {"news": store.find(news_id_)}


def delete_news(store, data):
    news_id_ = news_id(data)
    if not store.delete(news_id_):
        raise InputError("Uutista ei löytynyt. Se on ehkä jo poistettu.")
    return {"deleted": news_id_}


def feed(store, data):
    """The newest news in the JalaOps dashboard's format."""
    items, _ = store.newest(whole_number(data, "limit", 5, 1, 10))
    return {
        "items": [
            {
                "title": item["title"],
                "text": item["short_description"],
                "date": item["created_at"],
                "image": item["thumbnail"],
                "tags": item["tags"],
                "params": {"news": str(item["id"])},
            }
            for item in items
        ]
    }


ACTIONS = {
    "list": list_news,
    "get": get_news,
    "create": create_news,
    "update": update_news,
    "delete": delete_news,
    "feed": feed,
    "tags": lambda store, data: {"tags": store.tags()},
}


def handle(store, data):
    """The output for an input object. Raises InputError for bad input."""
    if not isinstance(data, dict):
        raise InputError("Syötteen pitää olla JSON-objekti.")

    action = ACTIONS.get(data.get("action", "list"))
    if action is None:
        raise InputError(f"Tuntematon toiminto. Sallitut: {', '.join(ACTIONS)}.")
    return action(store, data)


def open_store():
    directory = os.environ.get("JALAOPS_DATA_DIR")
    if not directory:
        fail("Moduulilla ei ole tallennuskansiota (JALAOPS_DATA_DIR).")

    return NewsStore(directory, seed=demo.seed)


def main():
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        fail("Syöte ei ole kelvollista JSONia.")

    store = open_store()
    try:
        output = handle(store, data)
    except InputError as error:
        fail(str(error))
    finally:
        store.close()

    json.dump(output, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
