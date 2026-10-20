# Uutiset (JalaOps module)

A [JalaOps](https://github.com/jussipalanen/jalaops) Python module as a Composer package: a news feed. Users write news with a title, a short description, HTML content, tags and images, read them in a list or one by one, and edit and delete them. The newest news show on the JalaOps dashboard.

Version 2 is a class that uses the JalaOps module SDK (`class NewsFeedModule(Module)`, its actions are methods), so it needs **JalaOps 1.15.0 or later**. Version 1 works with JalaOps 1.11.0–1.14.x.

The module uses it uses the module data folder (`"storage": true`), a larger input for images (`"max_input_kb"`), page addresses (`jalaops.params`, `jalaops.navigate`) and a dashboard widget (`"widgets"`). With JalaOps 1.12.0 or later, its pages have addresses of their own (`/news`, `/news/<slug>`, from `"routes"`), and a news item's page has the item's title in the browser tab (`jalaops.setPage`). Older versions ignore these and use `/tools/modules/news`.

The module comes off, like every optional module: turn it on with its switch in **Työkalut → Moduulit**, or `./dev artisan modules:enable news`.

## Install

```bash
./dev composer config repositories.jalaops-module-news vcs https://github.com/jussipalanen/jalaops-module-news.git
./dev composer require jalaops/news:^2.0
./dev artisan modules:list
```

The module opens from **Työkalut → Moduulit → Uutiset** or at `/news`, and its widget "Uusimmat uutiset" shows on the dashboard after the counts. Move it with `./dev artisan modules:place news.latest dashboard.bottom` (for everyone) or from **Muokkaa etusivua** on the dashboard (in your own browser).

## Pages

The view (`view.html`, `assets/news.js`, `assets/news.css`) has three pages, each with its own address (the routes in `module.json`):

| Address | Page |
|---|---|
| `/news` | The news, newest first, filtered by a tag with `?tag=huolto` |
| `/news/syyshuollot-alkavat` | One news item with its images, and buttons to edit and delete it |
| `/news/new` | A new news item: HTML content with a toolbar and a preview, tags and up to 6 images |
| `/news/syyshuollot-alkavat/edit` | Editing a news item: its images can be kept, captioned, removed or added |

A news item's address has its slug, made from its title when it's saved (`Syyshuollot alkavat` → `syyshuollot-alkavat`; ä, ö and å become a, o and a, and a slug that's taken gets `-2`). The slug stays when the title is edited, so links keep working. An address with the item's id (`/news/3`, or `/tools/modules/news?news=3` from before 1.1.0) still opens it, and the address changes to the slug.

Each card in the list can also be edited or deleted. Deleting asks for confirmation in the page (the frame can't open the browser's dialogs).

Images are made smaller in the browser before they are sent (at most 1600 px, and a 480 px thumbnail), which also drops their metadata such as a phone photo's GPS location.

## Actions

JalaOps runs `main.py` with a JSON object on stdin; `action` says what to do. Errors are Finnish messages on stderr with exit code 1.

| Action | Input | Output |
|---|---|---|
| `list` (default) | `tag`, `limit` (1–50, default 20), `offset` | `items` (no content, the first image's thumbnail), `total`, `tags` with counts |
| `get` | `id` or `slug` | `news` with `slug`, `content` and `media` (full images and thumbnails as data URLs) |
| `create` | `title` (≤ 150), `short_description` (≤ 300), `content` (HTML, ≤ 50 000), `tags` (≤ 10), `media` (≤ 6: `image`, optional `thumbnail` and `alt`) | `news` |
| `update` | `id` and the fields of `create`; in `media`, `{"id": 7, "alt": "…"}` keeps an image the item has, new ones are added, and images left out are deleted | `news` (with `updated_at`) |
| `delete` | `id` | `deleted` |
| `feed` | `limit` (1–10, default 5) | `items` in the JalaOps widget format, linking with slugs |
| `tags` | | `tags` with counts |

Content without HTML tags becomes paragraphs (a blank line starts a new one). HTML is sanitized to an allowlist when saving and again when showing: headings, paragraphs, lists, emphasis, quotes, code, tables and links (`http`, `https`, `mailto`, `tel`, opened in a new tab). Scripts, styles, event attributes, images and frames are removed; images go in `media`. Images are JPEG, PNG, GIF or WebP, at most 1.5 MB each.

## Storage

The news are in an SQLite database, `news.sqlite3`, in the folder JalaOps gives the module in `JALAOPS_DATA_DIR` (`backend/storage/app/modules/news/`). Images are stored in the database, so deleting a news item deletes its images too. A new database gets six demo news. On Cloud Run the folder resets when the instance restarts, like the rest of the JalaOps demo data.

## Develop

The module imports the SDK, `jalaops_module`, which JalaOps puts on its `PYTHONPATH`. To run it on its own, put the SDK from a JalaOps checkout next to this one on the path:

```bash
export PYTHONPATH=../jalaops/backend/modules/sdk
python3 -m unittest                                       # tests
JALAOPS_DATA_DIR=/tmp/news python3 main.py <<< '{"action": "list", "limit": 2}'
```

CI gets the SDK from the JalaOps repository.

Release a new version by tagging it (`git tag -a v1.1.0 -m 1.1.0 && git push --tags`); JalaOps picks it up with `composer update jalaops/news`.

## License

MIT
