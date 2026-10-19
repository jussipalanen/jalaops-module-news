/*
 * The news module's pages: the list (?tag=… filters it), one news item
 * (?news=3), the form for a new one (?view=new) and for editing one
 * (?news=3&view=edit). Everything users type is
 * written with textContent; only a news item's content is HTML, and main.py
 * has already sanitized it to an allowlist.
 */
;(function () {
  'use strict'

  var PAGE_SIZE = 20
  var MAX_MEDIA = 6
  var MAX_INPUT_BYTES = 4000000
  var IMAGE_SIDE = 1600
  var THUMBNAIL_SIDE = 480

  var root, errorBox
  var params = {}
  // Outputs already fetched, so moving between pages doesn't run the module
  // again. Emptied when a news item is added or deleted.
  var cache = { lists: {}, news: {} }

  // ---- Helpers ---------------------------------------------------------

  // An element with attributes and children (texts or elements).
  function h(tag, attributes) {
    var element = document.createElement(tag)
    Object.keys(attributes || {}).forEach(function (name) {
      var value = attributes[name]
      if (value === null || value === undefined || value === false) return
      if (name === 'class') element.className = value
      else if (name.slice(0, 2) === 'on') element.addEventListener(name.slice(2), value)
      else element.setAttribute(name, value === true ? '' : value)
    })
    for (var i = 2; i < arguments.length; i++) append(element, arguments[i])
    return element
  }

  function append(element, child) {
    if (child === null || child === undefined || child === false) return
    if (Array.isArray(child)) child.forEach(function (item) { append(element, item) })
    else element.appendChild(typeof child === 'string' ? document.createTextNode(child) : child)
  }

  function showError(message) {
    errorBox.textContent = message
    errorBox.hidden = !message
  }

  function run(input) {
    return window.jalaops.run(input)
  }

  // Moves to another page. The app changes the page address and sends the
  // new parameters back ("jalaops:params"), which draws the page.
  function go(next) {
    var clean = {}
    Object.keys(next).forEach(function (key) {
      if (next[key] !== undefined && next[key] !== null && next[key] !== '') clean[key] = String(next[key])
    })
    if (window.jalaops.navigate) window.jalaops.navigate(clean)
    else render(clean)
  }

  var dateFormat = new Intl.DateTimeFormat('fi-FI', { day: 'numeric', month: 'numeric', year: 'numeric' })
  var timeFormat = new Intl.DateTimeFormat('fi-FI', { hour: '2-digit', minute: '2-digit' })
  var relative = new Intl.RelativeTimeFormat('fi', { numeric: 'auto' })

  // "3 tuntia sitten" for the last day, otherwise "19.10.2026 klo 14.05".
  function formatDate(iso) {
    var date = new Date(iso)
    var minutes = Math.round((date.getTime() - Date.now()) / 60000)
    if (minutes > -60) return relative.format(Math.min(minutes, 0), 'minute')
    if (minutes > -24 * 60) return relative.format(Math.round(minutes / 60), 'hour')
    return dateFormat.format(date) + ' klo ' + timeFormat.format(date)
  }

  function time(iso) {
    return h('time', { datetime: iso, title: dateFormat.format(new Date(iso)) + ' klo ' + timeFormat.format(new Date(iso)) }, formatDate(iso))
  }

  function tagList(tags, onTag) {
    if (!tags.length) return null
    return h('ul', { class: 'news-tags', 'aria-label': 'Tunnisteet' }, tags.map(function (tag) {
      return h('li', null, onTag
        ? h('button', { type: 'button', class: 'news-tag', onclick: function (event) { event.stopPropagation(); onTag(tag) } }, '#' + tag)
        : h('span', { class: 'news-tag' }, '#' + tag))
    }))
  }

  function thumbnail(item) {
    if (item.thumbnail) return h('img', { class: 'news-thumb', src: item.thumbnail, alt: item.thumbnail_alt || '' })
    return h('div', { class: 'news-thumb news-thumb-empty', 'aria-hidden': 'true' }, item.title.charAt(0).toUpperCase())
  }

  // ---- The list --------------------------------------------------------

  function listKey(tag) {
    return tag || ''
  }

  async function loadList(tag, more) {
    var key = listKey(tag)
    var cached = cache.lists[key]
    if (cached && !more) return cached

    var output = await run({ action: 'list', tag: tag || undefined, limit: PAGE_SIZE, offset: more ? cached.items.length : 0 })
    if (more) output.items = cached.items.concat(output.items)
    cache.lists[key] = output
    return output
  }

  async function renderList(tag) {
    var list = await loadList(tag)

    var page = h('div', { class: 'stack' },
      h('div', { class: 'news-toolbar' },
        h('h2', null, tag ? '#' + tag : 'Uutiset'),
        h('button', { type: 'button', onclick: function () { go({ view: 'new' }) } }, '+ Uusi uutinen')),
      tagFilter(list.tags, tag),
    )

    if (!list.items.length) {
      append(page, h('div', { class: 'news-empty' },
        h('p', null, tag ? 'Tällä tunnisteella ei ole uutisia.' : 'Uutisia ei vielä ole.'),
        tag ? null : h('p', null, h('small', null, 'Kirjoita ensimmäinen uutinen ”Uusi uutinen” -painikkeella.'))))
      return page
    }

    var cards = h('ul', { class: 'news-list' }, list.items.map(function (item) {
      return h('li', null, h('article', { class: 'news-card' },
        thumbnail(item),
        h('div', { class: 'news-card-body' },
          h('p', { class: 'news-meta' }, time(item.created_at),
            item.media_count > 1 ? h('span', null, ' · ' + item.media_count + ' kuvaa') : null),
          h('h3', null, h('button', { type: 'button', class: 'news-open', onclick: function () { go({ news: address(item) }) } }, item.title)),
          h('p', { class: 'news-summary' }, item.short_description),
          tagList(item.tags, function (next) { go({ tag: next }) })),
        // Beside the body, so on a phone the buttons can use the card's whole width.
        h('div', { class: 'news-card-actions' },
          h('button', { type: 'button', class: 'news-small', 'aria-label': 'Muokkaa: ' + item.title, onclick: function () { go({ news: address(item), view: 'edit' }) } }, 'Muokkaa'),
          // Deleted from the list, the list is drawn again for the same address.
          deleteButton(item, true, function () { render(params) }))))
    }))
    append(page, cards)

    if (list.items.length < list.total) {
      var more = h('button', {
        type: 'button',
        class: 'news-secondary',
        onclick: async function () {
          more.disabled = true
          try {
            await loadList(tag, true)
            await render(params)
          } catch (exception) {
            showError(exception.message)
            more.disabled = false
          }
        },
      }, 'Näytä lisää (' + (list.total - list.items.length) + ')')
      append(page, h('div', null, more))
    }

    return page
  }

  function tagFilter(tags, current) {
    if (!tags.length) return null
    var chips = [h('button', { type: 'button', class: 'news-chip', 'aria-pressed': String(!current), onclick: function () { go({}) } }, 'Kaikki')]
    tags.forEach(function (entry) {
      chips.push(h('button', {
        type: 'button',
        class: 'news-chip',
        'aria-pressed': String(entry.tag === current),
        onclick: function () { go(entry.tag === current ? {} : { tag: entry.tag }) },
      }, '#' + entry.tag + ' ', h('small', null, String(entry.count))))
    })
    return h('nav', { class: 'news-chips', 'aria-label': 'Suodata tunnisteella' }, chips)
  }

  // ---- One news item ---------------------------------------------------

  // A news item's part of the page address: its slug (/news/syyshuollot-alkavat).
  // Older addresses have its id (?news=3), which still works.
  function address(news) {
    return news.slug || String(news.id)
  }

  async function loadNews(key) {
    if (!cache.news[key]) {
      var news = (await run(/^\d+$/.test(key) ? { action: 'get', id: Number(key) } : { action: 'get', slug: key })).news
      cache.news[key] = cache.news[address(news)] = news
    }
    return cache.news[key]
  }

  // An item opened by its id (/news/3) gets its slug in the address
  // (/news/syyshuollot-alkavat) without a new history entry.
  function useSlug(news) {
    if (params.news !== address(news) && window.jalaops.navigate) {
      var next = Object.assign({}, params, { news: address(news) })
      window.jalaops.navigate(next, { replace: true })
    }
  }

  async function renderNews(key) {
    var news = await loadNews(key)

    var content = h('div', { class: 'news-content' })
    content.innerHTML = news.content

    return h('article', { class: 'stack news-article' },
      h('div', null, h('button', { type: 'button', class: 'news-back', onclick: function () { go({}) } }, '← Kaikki uutiset')),
      h('header', { class: 'news-article-header' },
        h('h2', { class: 'news-title' }, news.title),
        h('p', { class: 'news-meta' }, time(news.created_at), news.updated_at ? [' · muokattu ', time(news.updated_at)] : null),
        tagList(news.tags, function (tag) { go({ tag: tag }) })),
      gallery(news.media),
      h('p', { class: 'news-lead' }, news.short_description),
      content,
      h('div', { class: 'news-manage' },
        h('button', { type: 'button', class: 'news-secondary', onclick: function () { go({ news: address(news), view: 'edit' }) } }, 'Muokkaa'),
        deleteButton(news)))
  }

  function gallery(media) {
    if (!media.length) return null

    var main = h('img', { class: 'news-image', src: media[0].image, alt: media[0].alt })
    var caption = h('figcaption', null, media[0].alt)
    caption.hidden = !media[0].alt

    var figure = h('figure', { class: 'news-gallery' }, main, caption)
    if (media.length > 1) {
      append(figure, h('div', { class: 'news-gallery-thumbs', role: 'group', 'aria-label': 'Kuvat' }, media.map(function (item, index) {
        return h('button', {
          type: 'button',
          'aria-label': 'Näytä kuva ' + (index + 1) + (item.alt ? ': ' + item.alt : ''),
          'aria-current': index === 0 ? 'true' : null,
          onclick: function (event) {
            main.src = item.image
            main.alt = item.alt
            caption.textContent = item.alt
            caption.hidden = !item.alt
            figure.querySelectorAll('[aria-current]').forEach(function (button) { button.removeAttribute('aria-current') })
            event.currentTarget.setAttribute('aria-current', 'true')
          },
        }, h('img', { src: item.thumbnail, alt: '' }))
      })))
    }
    return figure
  }

  // Deleting asks for confirmation in the page itself: the frame can't open
  // the browser's confirm() dialog. small: the list's smaller button.
  // deleted: what happens next (by default, back to the list).
  function deleteButton(news, small, deleted) {
    var box = h('div', { class: 'news-delete' })

    function ask() {
      box.replaceChildren(small
        ? h('button', { type: 'button', class: 'news-small news-small-danger', 'aria-label': 'Poista: ' + news.title, onclick: confirm }, 'Poista')
        : h('button', { type: 'button', class: 'news-danger', onclick: confirm }, 'Poista uutinen'))
    }

    function confirm() {
      var yes = h('button', { type: 'button', class: 'news-danger', onclick: remove }, 'Kyllä, poista')
      box.replaceChildren(
        h('p', { role: 'alert' }, 'Poistetaanko ”' + news.title + '” kuvineen? Poistoa ei voi perua.'),
        h('div', { class: 'news-actions' }, yes, h('button', { type: 'button', class: 'news-secondary', onclick: ask }, 'Peruuta')))
      yes.focus()
    }

    async function remove(event) {
      event.currentTarget.disabled = true
      try {
        await run({ action: 'delete', id: news.id })
        cache = { lists: {}, news: {} }
        if (deleted) deleted()
        else go({})
      } catch (exception) {
        showError(exception.message)
        ask()
      }
    }

    ask()
    return box
  }

  // ---- The form --------------------------------------------------------

  // The form for a new news item, or for editing one (news). Images the item
  // already has are kept as { id, thumbnail, alt }; new ones have an image.
  function renderForm(news) {
    var editing = Boolean(news)
    var media = editing ? news.media.map(function (item) { return { id: item.id, thumbnail: item.thumbnail, alt: item.alt } }) : []
    var tags = editing ? news.tags.slice() : []

    var title = h('input', { id: 'news-title', maxlength: '150', required: true, autocomplete: 'off' })
    var short = h('textarea', { id: 'news-short', maxlength: '300', rows: '2', required: true })
    var shortCount = h('small', { 'aria-live': 'polite' }, '0 / 300')
    if (editing) {
      title.value = news.title
      short.value = news.short_description
      shortCount.textContent = short.value.length + ' / 300'
    }
    short.addEventListener('input', function () { shortCount.textContent = short.value.length + ' / 300' })

    var content = h('textarea', { id: 'news-content', rows: '10', required: true, class: 'news-code', spellcheck: 'true' })
    if (editing) content.value = news.content
    var preview = h('div', { class: 'news-content news-preview', hidden: true, 'aria-live': 'polite' })
    var previewButton = h('button', {
      type: 'button',
      class: 'news-secondary',
      'aria-pressed': 'false',
      onclick: function () {
        var showing = preview.hidden
        preview.hidden = !showing
        content.hidden = showing
        previewButton.setAttribute('aria-pressed', String(showing))
        previewButton.textContent = showing ? 'Muokkaa' : 'Esikatsele'
        if (showing) preview.replaceChildren(previewContent(content.value))
      },
    }, 'Esikatsele')

    // Buttons that put HTML tags around the selected text.
    function wrap(before, after, placeholder) {
      return function () {
        var start = content.selectionStart
        var end = content.selectionEnd
        var selected = content.value.slice(start, end) || placeholder
        content.setRangeText(before + selected + after, start, end, 'end')
        content.focus()
        content.setSelectionRange(start + before.length, start + before.length + selected.length)
      }
    }

    var tools = [
      ['Lihavoi', '<strong>', '</strong>', 'teksti', 'B'],
      ['Kursivoi', '<em>', '</em>', 'teksti', 'I'],
      ['Väliotsikko', '<h2>', '</h2>', 'Väliotsikko', 'H'],
      ['Kappale', '<p>', '</p>', 'Kappale', '¶'],
      ['Luettelo', '<ul>\n  <li>', '</li>\n</ul>', 'kohta', '•'],
      ['Lainaus', '<blockquote>', '</blockquote>', 'lainaus', '❝'],
      ['Linkki', '<a href="https://">', '</a>', 'linkin teksti', 'Linkki'],
    ]
    var toolbar = h('div', { class: 'news-editor-tools', role: 'toolbar', 'aria-label': 'Muotoilu' }, tools.map(function (tool) {
      return h('button', { type: 'button', class: 'news-tool', title: tool[0], 'aria-label': tool[0], onclick: wrap(tool[1], tool[2], tool[3]) }, tool[4])
    }), previewButton)

    // Tags: typed into a field, added with Enter or a comma.
    var tagInput = h('input', { id: 'news-tag', autocomplete: 'off', list: 'news-tag-options', enterkeyhint: 'enter' })
    var tagChips = h('ul', { class: 'news-tags', 'aria-label': 'Lisätyt tunnisteet' })
    var knownTags = h('datalist', { id: 'news-tag-options' })
    var cachedTags = (cache.lists[''] || {}).tags || []
    cachedTags.forEach(function (entry) { append(knownTags, h('option', { value: entry.tag })) })

    function addTags(text) {
      text.split(',').forEach(function (part) {
        var tag = part.trim().replace(/^#/, '').replace(/\s+/g, ' ').toLowerCase()
        if (tag && tags.indexOf(tag) < 0 && tags.length < 10) tags.push(tag.slice(0, 30))
      })
      drawTags()
    }

    function drawTags() {
      tagChips.replaceChildren.apply(tagChips, tags.map(function (tag) {
        return h('li', null, h('span', { class: 'news-tag' }, '#' + tag + ' ',
          h('button', { type: 'button', class: 'news-remove', 'aria-label': 'Poista tunniste ' + tag, onclick: function () {
            tags.splice(tags.indexOf(tag), 1)
            drawTags()
          } }, '×')))
      }))
    }

    tagInput.addEventListener('keydown', function (event) {
      if (event.key === 'Enter' || event.key === ',') {
        event.preventDefault()
        addTags(tagInput.value)
        tagInput.value = ''
      }
    })
    drawTags()

    tagInput.addEventListener('change', function () {
      // A choice from the suggestions.
      if (tagInput.value.trim()) {
        addTags(tagInput.value)
        tagInput.value = ''
      }
    })

    // Images: made smaller in the browser before sending (this also drops
    // their metadata, such as the GPS location of phone photos).
    var fileInput = h('input', { id: 'news-files', type: 'file', accept: 'image/*', multiple: true, class: 'news-file' })
    var mediaList = h('ul', { class: 'news-media-list' })
    var mediaNote = h('small', { 'aria-live': 'polite' })

    fileInput.addEventListener('change', async function () {
      var files = Array.prototype.slice.call(fileInput.files)
      fileInput.value = ''
      showError('')

      if (media.length + files.length > MAX_MEDIA) {
        showError('Kuvia voi olla enintään ' + MAX_MEDIA + '.')
        files = files.slice(0, MAX_MEDIA - media.length)
      }

      mediaNote.textContent = files.length ? 'Käsitellään kuvia…' : ''
      for (var i = 0; i < files.length; i++) {
        try {
          media.push(await prepareImage(files[i]))
        } catch (exception) {
          showError(files[i].name + ': kuvaa ei voitu lukea.')
        }
      }
      drawMedia()
    })

    function drawMedia() {
      // Only new images are sent.
      var bytes = media.reduce(function (sum, item) { return sum + (item.image ? item.image.length + item.thumbnail.length : 0) }, 0)
      mediaNote.textContent = media.length
        ? media.length + ' / ' + MAX_MEDIA + ' kuvaa, ' + Math.round(bytes / 1000) + ' kt'
        : 'Enintään ' + MAX_MEDIA + ' kuvaa. Kuvat pienennetään ennen tallennusta.'
      mediaList.replaceChildren.apply(mediaList, media.map(function (item, index) {
        var alt = h('input', { value: item.alt, maxlength: '200', 'aria-label': 'Kuvateksti, kuva ' + (index + 1), placeholder: 'Kuvateksti' })
        alt.addEventListener('input', function () { item.alt = alt.value })
        return h('li', { class: 'news-media-item' },
          h('img', { src: item.thumbnail, alt: '' }),
          alt,
          h('button', { type: 'button', class: 'news-remove', 'aria-label': 'Poista kuva ' + (index + 1), onclick: function () {
            media.splice(index, 1)
            drawMedia()
          } }, '×'))
      }))
    }
    drawMedia()

    var saveLabel = editing ? 'Tallenna muutokset' : 'Julkaise uutinen'
    var save = h('button', { type: 'submit' }, saveLabel)
    var back = editing ? { news: address(news) } : {}
    var backLabel = editing ? '← Takaisin uutiseen' : '← Kaikki uutiset'

    var form = h('form', { class: 'stack', novalidate: true },
      h('div', null, h('button', { type: 'button', class: 'news-back', onclick: function () { go(back) } }, backLabel)),
      h('h2', null, editing ? 'Muokkaa uutista' : 'Uusi uutinen'),
      h('label', { for: 'news-title' }, 'Otsikko', title),
      h('div', { class: 'news-field' }, h('label', { for: 'news-short' }, 'Lyhyt kuvaus'), short, shortCount),
      h('div', { class: 'news-field' },
        h('label', { for: 'news-content' }, 'Sisältö'),
        h('small', null, 'Kirjoita tekstiä tai HTML:ää. Tyhjä rivi aloittaa uuden kappaleen.'),
        toolbar, content, preview),
      h('div', { class: 'news-field' },
        h('label', { for: 'news-tag' }, 'Tunnisteet'),
        h('small', null, 'Lisää Enterillä tai pilkulla, esim. huolto, talvi.'),
        tagInput, knownTags, tagChips),
      h('div', { class: 'news-field' },
        h('label', { for: 'news-files' }, 'Kuvat'),
        fileInput, mediaNote, mediaList),
      h('div', { class: 'news-actions' }, save, h('button', { type: 'button', class: 'news-secondary', onclick: function () { go(back) } }, 'Peruuta')))

    form.addEventListener('submit', async function (event) {
      event.preventDefault()
      showError('')
      if (tagInput.value.trim()) {
        addTags(tagInput.value)
        tagInput.value = ''
      }

      var missing = [[title, 'Otsikko'], [short, 'Lyhyt kuvaus'], [content, 'Sisältö']].filter(function (field) {
        return !field[0].value.trim()
      })
      if (missing.length) {
        showError(missing.map(function (field) { return field[1] }).join(', ') + ': pakollinen tieto.')
        return
      }

      var input = {
        action: editing ? 'update' : 'create',
        id: editing ? news.id : undefined,
        title: title.value,
        short_description: short.value,
        content: content.value,
        tags: tags,
        media: media.map(function (item) {
          return item.id ? { id: item.id, alt: item.alt } : { image: item.image, thumbnail: item.thumbnail, alt: item.alt }
        }),
      }

      if (JSON.stringify(input).length > MAX_INPUT_BYTES) {
        showError('Kuvat ovat yhteensä liian suuria. Poista kuva tai kaksi.')
        return
      }

      save.disabled = true
      save.textContent = editing ? 'Tallennetaan…' : 'Julkaistaan…'
      try {
        var saved = (await run(input)).news
        cache = { lists: {}, news: {} }
        cache.news[address(saved)] = saved
        go({ news: address(saved) })
      } catch (exception) {
        showError(exception.message)
        save.disabled = false
        save.textContent = saveLabel
      }
    })

    setTimeout(function () { title.focus() })
    return form
  }

  // An image file as a smaller JPEG and a thumbnail, both data URLs.
  async function prepareImage(file) {
    var bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
    try {
      var image = draw(bitmap, IMAGE_SIDE, 0.85)
      if (image.length > 1900000) image = draw(bitmap, 1200, 0.75)
      return { image: image, thumbnail: draw(bitmap, THUMBNAIL_SIDE, 0.75), alt: '' }
    } finally {
      bitmap.close()
    }
  }

  function draw(bitmap, side, quality) {
    var scale = Math.min(1, side / Math.max(bitmap.width, bitmap.height))
    var canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(bitmap.width * scale))
    canvas.height = Math.max(1, Math.round(bitmap.height * scale))
    var context = canvas.getContext('2d')
    // JPEG has no transparency: transparent parts become white, not black.
    context.fillStyle = '#fff'
    context.fillRect(0, 0, canvas.width, canvas.height)
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    return canvas.toDataURL('image/jpeg', quality)
  }

  // ---- Preview: the same rules as news_html.py, for the form only -------

  var ALLOWED = {
    A: ['href', 'title'], B: [], BLOCKQUOTE: [], BR: [], CODE: [], DIV: [], EM: [], H2: [], H3: [], H4: [], HR: [],
    I: [], LI: [], MARK: [], OL: [], P: [], PRE: [], S: [], SMALL: [], SPAN: [], STRONG: [], SUB: [], SUP: [],
    TABLE: [], TBODY: [], TD: ['colspan', 'rowspan'], TH: ['colspan', 'rowspan'], THEAD: [], TR: [], U: [], UL: [],
  }
  var DROPPED = /^(SCRIPT|STYLE|IFRAME|OBJECT|EMBED|TEMPLATE|NOSCRIPT|SVG|MATH|TEXTAREA|SELECT|TITLE|HEAD)$/

  // Text becomes paragraphs unless it has block tags, like main.py does when saving.
  function paragraphs(text) {
    if (/<(p|div|h[1-6]|ul|ol|li|table|blockquote|pre|hr)\b/i.test(text)) return text
    if (!/<[a-z/!]/i.test(text)) text = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
    return text.trim().split(/\n\s*\n/).filter(function (part) { return part.trim() }).map(function (part) {
      return '<p>' + part.trim().replace(/\n/g, '<br>') + '</p>'
    }).join('')
  }

  function previewContent(html) {
    // DOMParser doesn't run scripts or load anything.
    var parsed = new DOMParser().parseFromString(paragraphs(html), 'text/html').body
    var fragment = document.createDocumentFragment()
    copyAllowed(parsed, fragment)
    return fragment
  }

  function copyAllowed(from, to) {
    from.childNodes.forEach(function (node) {
      if (node.nodeType === 3) {
        to.appendChild(document.createTextNode(node.textContent))
        return
      }
      if (node.nodeType !== 1 || DROPPED.test(node.nodeName)) return

      var name = { H1: 'H2', H5: 'H4', H6: 'H4' }[node.nodeName] || node.nodeName
      if (!ALLOWED[name]) {
        copyAllowed(node, to)
        return
      }

      var copy = document.createElement(name)
      ALLOWED[name].forEach(function (attribute) {
        var value = node.getAttribute(attribute)
        if (value === null) return
        if (attribute === 'href' && !/^(https?:|mailto:|tel:)/i.test(value.replace(/[\x00-\x20]/g, ''))) return
        copy.setAttribute(attribute, value)
      })
      if (name === 'A') {
        copy.target = '_blank'
        copy.rel = 'noopener noreferrer'
      }
      copyAllowed(node, copy)
      to.appendChild(copy)
    })
  }

  // ---- Pages -----------------------------------------------------------

  var drawing = 0

  // The browser tab's title and the page's description (JalaOps 1.12.0 and
  // later; older versions keep the module's name).
  function setPage(info) {
    if (window.jalaops.setPage) window.jalaops.setPage(info)
  }

  async function render(next) {
    params = next || {}
    var current = ++drawing
    showError('')
    root.setAttribute('aria-busy', 'true')

    try {
      var page
      var info = {}
      if (params.view === 'new') {
        page = renderForm()
        info = { title: 'Uusi uutinen' }
      } else if (params.news && params.view === 'edit') {
        var editing = await loadNews(params.news)
        page = renderForm(editing)
        info = { title: 'Muokkaa: ' + editing.title, news: editing }
      } else if (params.news) {
        var news = await loadNews(params.news)
        page = await renderNews(params.news)
        info = { title: news.title, description: news.short_description, news: news }
      } else {
        page = await renderList(params.tag)
        info = params.tag ? { title: 'Uutiset #' + params.tag } : {}
      }

      // A newer page was asked for while this one was loading.
      if (current !== drawing) return
      root.replaceChildren(page)
      setPage({ title: info.title, description: info.description })
      if (info.news) useSlug(info.news)
    } catch (exception) {
      if (current !== drawing) return
      root.replaceChildren(h('div', null, h('button', { type: 'button', class: 'news-back', onclick: function () { go({}) } }, '← Kaikki uutiset')))
      showError(exception.message)
    } finally {
      if (current === drawing) root.removeAttribute('aria-busy')
    }
  }

  window.NewsApp = {
    start: function (element, error) {
      root = element
      errorBox = error
      window.addEventListener('jalaops:params', function (event) { render(event.detail) })
      render(window.jalaops.params || {})
    },
    // For tests.
    previewContent: previewContent,
    paragraphs: paragraphs,
  }
})()
