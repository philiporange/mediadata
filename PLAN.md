# PLAN.md

A pragmatic, future-proof plan for laying out immutable media and defining precise XML NFO sidecars that are **compatible with the Kodi/Jellyfin family** while remaining rich enough for books/audiobooks and advanced use-cases.

---

## 0) Goals & Principles

**Goals**

* Keep media files **immutable** (no embedded tags required).
* Coexist with **multiple metadata sources** per item without conflicts.
* Be **interoperable** with Kodi/Jellyfin (NFO conventions) while extending cleanly for gaps (books/audiobooks/collections).
* Support **all common topologies**: single / multi-file torrents, multi-edition movies, TV seasons, multi-disc audiobooks, anthologies, etc.
* Deterministic, scriptable discovery and merging.

**Principles**

* **Sidecars over embedded**: all mutable metadata lives in sidecars.
* **Locality**: “consumed” sidecars sit next to the item they describe; “archival/provenance” sidecars can live higher.
* **Namespacing**: every sidecar declares its **source**; we never lose provenance.
* **Stable filenames**: two canonical patterns:

  * Folder-level: `source.ext` (e.g., `tmdb.nfo`)
  * File-level: `<mediafilename>.source.ext` (e.g., `Movie.2024.mkv.tmdb.nfo`)
* **Interoperability first**: the XML vocabulary mirrors **Kodi NFO** (movie/tvshow/episode/artist/album/musicvideo), with additive, non-breaking extensions for books/audiobooks/collections.

---

## 1) Directory Layout (Immutable Payloads, Hash Parents)

Top-level items are directories named by **info hash (lowercase)**:

```
/library/
  └── <infohash>/
       ├── data/                     # exact torrent payload (immutable)
       │    ├── <files...>           # single-file or multi-file contents
       │    └── (optional) sidecars  # only the "consumed" ones (see §3)
       ├── source.torrent            # original torrent file
       └── metadata/                 # archival sidecars (all sources, any formats)
            ├── tmdb.nfo / imdb.json / tvdb.json / openlib.json / manual.json ...
            └── audit/ (fetch logs, checksums, proofs)
```

### 1.1 Virtual Library (optional)

* Present a **virtual view** (symlinks/hardlinks) that re-organizes items into human-friendly or app-friendly trees (e.g., Movies/TV/Books), without moving the immutable payload. This lets you point off-the-shelf apps to the virtual tree while your own app reads the canonical hash layout.

---

## 2) Discovery Rules (Deterministic Sidecar Resolution)

**Folder-level item** (movie folder, series folder, book folder, audiobook folder, album folder):

1. Load all `*.nfo` and `*.json` in the folder whose base name **does not** prefix a media filename:

   * e.g., `tmdb.nfo`, `manual.nfo`, `openlibrary.json`.
2. If present, also ingest interoperability names (Kodi/Jellyfin):

   * `movie.nfo`, `tvshow.nfo`, `season.nfo`, `artist.nfo`, `album.nfo`.

**File-level item** (episode file, track file, single-file movie, single-file audiobook part):

1. Load all `<mediafilename>.*.(nfo|json)`, after stripping the media extension:

   * `Episode.S01E03.mkv.tmdb.nfo`, `Track 01.flac.manual.json`.
2. Interop name: `<mediafilename>.nfo` (Kodi/Jellyfin).

**Merging order (default; overrideable per library)**
`override.*` > `manual.*` > `local.nfo` (interoperability names) > `tmdb.*`/`tvdb.*`/`imdb.*`/`audible.*`/`openlibrary.*` > `scanners.*` (auto-extracted).

**Provenance**: Persist all raw sidecars (any format) in `metadata/`. Only copy/symlink the **one “active”** interop NFO into `data/` when you need third-party apps to consume it.

---

## 3) Media Types & File/Folder Conventions

### 3.1 Movies

* **Single movie per folder** (recommended):

  * `data/Movie (Year).mkv`, `data/movie.nfo` (or `Movie (Year).mkv.tmdb.nfo`), posters/fanart.
* **Multiple movies in one folder**:

  * Per-file NFO: `Movie A.mkv.tmdb.nfo`, `Movie B.mkv.tmdb.nfo`.
* **Alternate cuts / editions** (e.g., Director’s Cut):

  * Same folder: separate per-file NFOs with `<edition>` tag (see schema).
  * Or subfolders per edition, each with its own `movie.nfo`.

### 3.2 TV Series

```
data/
  tvshow.nfo               # series-level
  Season 01/
    season.nfo             # season-level (optional)
    Show.S01E01.mkv
    Show.S01E01.mkv.tmdb.nfo
    ...
  Season 00/               # specials
```

* **Specials ordering**: use `airsbefore_season`, `airsbefore_episode`, `airsafter_season` in episode NFO.

### 3.3 Music

```
data/
  artist.nfo               # artist-level
  Album Title/
    album.nfo              # album-level
    01 - Track.flac
    01 - Track.flac.nfo    # optional per-track
```

### 3.4 Music Videos

* Treated like movies (`<musicvideo>` root). Per-file NFO when many.

### 3.5 Books (text/ebooks)

```
data/
  Book Title.ext           # epub/pdf/azw3 etc. (immutable)
  book.nfo                 # folder-level NFO (see schema)
  cover.jpg
```

* Multiple formats (epub+pdf): either one folder-level `book.nfo` or per-file sidecars (filename-prefixed).

### 3.6 Audiobooks

**Single-file audiobook (e.g., `.m4b`)**

```
data/
  Book Title.m4b
  Book Title.m4b.audible.nfo     # file-level
  chapters.txt / cuesheet.cue    # optional raw chapter exports
```

**Multi-file / multi-disc audiobook**

```
data/
  Book Title/
    audiobook.nfo                # folder-level (roll-up)
    Disc 1/
      01 - Intro.m4a
      01 - Intro.m4a.nfo
    Disc 2/
      ...
```

* Chapters can be encoded at the **folder level** (roll-up) even when the media is split.

### 3.7 Collections / Boxsets

* Represent as a **virtual entity** with its own NFO in parent folder or `collections/` tree:

```
data/
  collection.nfo    # <collection> root, lists members by uniqueid/path
```

---

## 4) XML NFO Standard (Precise Vocabulary)

The XML mirrors **Kodi NFO** where possible. Roots:

* Movies: `<movie>`
* TV Series: `<tvshow>`; Episodes: `<episode>`; Seasons (optional roll-up file): `<season>`
* Music: `<artist>`, `<album>`, optional `<song>`
* Music videos: `<musicvideo>`
* **Extensions defined here**:

  * Books: `<book>`
  * Audiobooks: `<audiobook>`
  * Collections: `<collection>`

> Encoding: UTF-8.
> Whitespace: insignificant except inside text nodes.
> Dates: ISO-8601 (`YYYY-MM-DD`).
> Durations: integer minutes unless otherwise specified; optional `PT…` ISO-8601 duration strings allowed.
> URLs: absolute (`http(s):`) or `file:` URIs for local art.

### 4.1 Common Elements (shared across roots)

* **Identity**

  * `uniqueid` (repeatable):
    `<uniqueid type="tmdb" default="true">12345</uniqueid>`
    `<uniqueid type="imdb">tt1234567</uniqueid>`
    Accept common types: `tmdb`, `imdb`, `tvdb`, `musicbrainz`, `audible`, `openlibrary`, `isbn`, `asin`, `goodreads`, `catalog` (freeform).
* **Titles**

  * `<title>` (1), `<originaltitle>` (0..1), `<sorttitle>` (0..1), `<alternate_title>` (0..N)
* **People**

  * Flat (interop-friendly, **repeatable**):

    * `<director>`, `<writer>`, `<credits>` (writers), `<actor>` (contains `<name>`, `<role>`, optional `<thumb>`), `<artist>`, `<author>`, `<narrator>`, `<editor>`, `<translator>`
  * Structured (rich, optional):

    ```xml
    <contributors>
      <contributor>
        <name>…</name>
        <role>author|narrator|director|actor|writer|editor|translator|producer|composer|conductor|arranger|illustrator|photographer|reader|guest</role>
        <character>…</character>      <!-- for actors -->
        <order>0</order>               <!-- display/order hint -->
        <thumb>http://…</thumb>
      </contributor>
      …
    </contributors>
    ```
* **Ratings**

  ```xml
  <ratings>
    <rating name="tmdb" max="10" default="true">
      <value>7.4</value>
      <votes>1234</votes>
    </rating>
    <rating name="imdb" max="10">
      <value>7.8</value><votes>56789</votes>
    </rating>
  </ratings>
  ```
* **Art**

  ```xml
  <art>
    <poster>file:poster.jpg</poster>
    <fanart>file:fanart.jpg</fanart>
    <banner>http://…/banner.jpg</banner>
    <thumbnail>http://…</thumbnail>
    <logo>file:logo.png</logo>
    <disc>file:disc.png</disc>
    <!-- extensible: any <art><key>url</key> -->
  </art>
  ```
* **Classification & Facts**

  * `<genre>` (repeatable), `<tag>` (repeatable), `<studio>` / `<publisher>` / `<label>` (repeatable), `<collection>` (name; for a member item), `<country>`, `<language>`, `<mpaa>` (content rating).
* **Dates & Numbers**

  * `<year>`, `<premiered>` / `<aired>` / `<released>` / `<published>`, `<runtime>` (minutes or ISO8601), `<episode>` / `<season>` (integers), `<track>` / `<disc>` (music/audiobook).
* **Story**

  * `<plot>`, `<outline>`, `<tagline>`
* **Links**

  * `<homepage>`, `<trailer>`, `<sample>`, `<external>http…</external>` (repeatable)

### 4.2 Movies (`<movie>`) — Required & Optional

* **Required**: `<title>`, one of `<year>` or `<premiered>`, at least one `<uniqueid>` (recommended)
* **Optional**: all common elements, plus `<edition>` (e.g., “Director’s Cut”), `<set>` (boxset name), `<sorttitle>`

### 4.3 TV Series (`<tvshow>`)

* **Required**: `<title>`
* **Optional**: `<status>` (`Continuing|Ended|Pilot|Unknown`), `<seasoncount>`, `<episodeguide>` (URL), `<studio>`, common fields, `<uniqueid>`s, `<art>`

### 4.4 Season Roll-up (`<season>`)

* **Fields**: `<season>`, `<title>`, `<plot>`, `<art>`; used only as a season-level summary sidecar.

### 4.5 Episodes (`<episode>`)

* **Required**: `<title>`, `<season>`, `<episode>` **or** `<displayseason>`/`<displayepisode>` with proper special ordering helpers.
* **Airing/Ordering Helpers** (for specials/scene order):

  * `<airsbefore_season>`, `<airsbefore_episode>`, `<airsafter_season>`
* **Optional**: `<aired>`, `<runtime>`, `<plot>`, cast/crew, ratings, art.

### 4.6 Music: Artist (`<artist>`) / Album (`<album>`) / Track (`<song>`)

* **Artist**: `<artist>`, `<genre>`, `<style>`, `<mood>`, `<formed>`, `<born>`, `<disbanded>`, `<biography>`
* **Album**: `<title>`, `<artist>` (repeatable for compilations), `<year>`, `<label>`, `<genre>`, `<musicbrainzreleasegroupid>`
* **Song**: `<title>`, `<artist>` (repeatable), `<album>`, `<track>`, `<disc>`, `<year>`, `<lyrics>`

### 4.7 Music Video (`<musicvideo>`)

* Aligns with movie + music fields: `<artist>`, `<album>`, `<track>`, `<director>`, etc.

### 4.8 Book (`<book>`)  *(extension)*

* **Required**: `<title>`, at least one `<author>`
* **Recommended**: `<series>`, `<series_index>`, `<publisher>`, `<published>`, `<language>`, `<plot>`
* **IDs**: `openlibrary`, `isbn`, `goodreads`, `asin`
* **People**:

  * Flat: repeat `<author>`, `<editor>`, `<translator>`, `<illustrator>`
  * Structured: `<contributors>` per §4.1
* **Art**: `<art><cover>…</cover>…</art>`
* **Formats (optional)**: `<format>EPUB</format>` (repeatable if multiple representations)
* **Pages**: `<pages>310</pages>` (optional)

**Example skeleton**

```xml
<book>
  <title>…</title>
  <author>…</author>     <!-- repeatable -->
  <series>…</series>
  <series_index>1</series_index>
  <publisher>…</publisher>
  <published>YYYY-MM-DD</published>
  <language>en</language>
  <plot>…</plot>
  <uniqueid type="openlibrary" default="true">…</uniqueid>
  <uniqueid type="isbn">…</uniqueid>
  <ratings>…</ratings>
  <art>…</art>
  <contributors>…</contributors>
</book>
```

### 4.9 Audiobook (`<audiobook>`)  *(extension)*

* **Required**: `<title>`, at least one `<author>` **or** `<contributors>` with role=author
* **Recommended**: `<narrator>` (repeatable), `<publisher>`, `<released>`, `<runtime>`
* **IDs**: `audible`, `isbn`, `asin`, `openlibrary`
* **Structure for parts/discs** (optional):

  ```xml
  <parts>
    <part>
      <disc>1</disc> <track>1</track>
      <filename>Disc 1/Track 01.m4a</filename>     <!-- or a stable ID -->
      <runtime>PT08M32S</runtime>
    </part>
    …
  </parts>
  ```
* **Chapters** (timestamps relative to the **concatenated** program unless `@relative="part"`):

  ```xml
  <chapters relative="program">
    <chapter><number>1</number><title>Intro</title><start>PT00H00M00S</start></chapter>
    <chapter><number>2</number><title>…</title><start>PT00H27M15S</start></chapter>
  </chapters>
  ```
* **Art**: `<cover>`, `<fanart>` optional.
* **People**:

  * Flat repeatables: `<author>`, `<narrator>`, `<editor>`, `<translator>`
  * Structured: `<contributors>` per §4.1

**Example skeleton**

```xml
<audiobook>
  <title>…</title>
  <author>…</author>        <!-- repeatable -->
  <narrator>…</narrator>    <!-- repeatable -->
  <series>…</series><series_index>…</series_index>
  <publisher>…</publisher>
  <released>YYYY-MM-DD</released>
  <runtime>PT11H20M</runtime>
  <plot>…</plot>
  <uniqueid type="audible" default="true">…</uniqueid>
  <ratings>…</ratings>
  <chapters relative="program">…</chapters>
  <parts>…</parts>
  <art>…</art>
  <contributors>…</contributors>
</audiobook>
```

### 4.10 Collection / Boxset (`<collection>`)  *(extension)*

Represents a logical set of items (movies, seasons, books, audiobooks, albums).

* **Fields**: `<title>` (required), `<plot>`, `<art>`, `<uniqueid>` (e.g., TMDB collection ID), `<members>` list
* **Members**: reference by **uniqueid** (preferred) or by **path** (stable relative path)

```xml
<collection>
  <title>The Middle Earth Saga</title>
  <uniqueid type="tmdb" default="true">121938</uniqueid>
  <members>
    <member>
      <type>movie</type>
      <uniqueid type="tmdb">335984</uniqueid>
    </member>
    <member>
      <type>audiobook</type>
      <path>../<infohash>/data/Book Title.m4b</path>
    </member>
  </members>
  <art>…</art>
</collection>
```

---

## 5) Edge Cases & How to Represent Them

* **Multiple authors / narrators / artists**: repeat flat tags and/or enumerate in `<contributors>`.
* **Name disambiguation**: allow optional `<id>` within `<contributor>` for MusicBrainz/ORCID/ISNI.
* **Alternate cuts/editions**: `<edition>` on `<movie>`; separate per-file NFOs when distinct video files coexist.
* **Anthologies / split works**: prefer a **collection** NFO; for a single container file representing multiple works, represent each work as a `<chapter>` with a `<work>` child (optional extension).
* **Multi-language audio/subs**: list in `<tracks>` (optional extension):

  ```xml
  <tracks>
    <audio><lang>en</lang><codec>AAC</codec><channels>2</channels></audio>
    <subtitle><lang>en</lang><format>SRT</format><external>true</external></subtitle>
  </tracks>
  ```

  (Purely descriptive; playback apps read media streams directly.)
* **Scene order vs Aired order (TV)**: use the `airs*` helpers on `<episode>` as in §4.5.
* **Compilations (music)**: repeat `<artist>` per track; album-level `<albumartist>` distinguishes various-artists releases.
* **Multiple simultaneous metadata sources**: keep them all; merge per §6 with per-field precedence and provenance.

---

## 6) Merging Strategy (Multi-Source, Lossless)

**Canonical internal model** is JSON with 1:1 mapping to the XML fields above. On ingest:

1. **Collect** all candidate sidecars per §2.
2. **Normalize** (trim, dedupe, normalize people names, IDs).
3. **Merge** by field with precedence:

   * `override` > `manual` > interop `*.nfo` > curated APIs (tmdb/tvdb/imdb/openlibrary/audible) > scanner-derived.
4. **Arrays**: merge by **stable key**:

   * People: `name + role (+ character)`
   * Art: `key + url`
   * IDs: set union keyed by `(type,value)`
5. **Conflicts**: retain **provenance**:

   ```json
   "title": {
     "value": "Good Omens",
     "sources": [{"src":"manual","value":"Good Omens"},{"src":"openlibrary","value":"Good Omens: The Nice and Accurate..."}]
   }
   ```
6. **Round-trip**: exporter can emit a **clean interop NFO** (minimal, Kodi-compatible) to `data/` and keep enriched XML/JSON in `metadata/`.

---

## 7) Validation & Conformance

* **Well-formed XML**; enforce UTF-8.
* **Datatype checks**: dates ISO-8601; integers non-negative; durations minutes or ISO-8601 `PT…`.
* **Cardinality**:

  * Movie: require `<title>` + one of `<year|premiered>`; **recommend** one `<uniqueid>`.
  * Episode: require `<title>` & `<season>` & `<episode>` (or display variants).
  * Book/Audiobook: require `<title>` + at least one author (flat or structured).
* **Linter rules**:

  * Warn on deprecated single `<rating>` pattern without `<ratings>`.
  * Warn on duplicate `<uniqueid>` of same `type` with different values.
  * Warn if chapters exist but runtime missing.
* **Security**: refuse external entities (XXE); ignore DTDs; strip scripts in text nodes.

---

## 8) File Naming & Paths (Interoperability)

* **Interop names** (Kodi/Jellyfin): `movie.nfo`, `tvshow.nfo`, `season.nfo`, `<episode>.nfo`, `artist.nfo`, `album.nfo`, `<musicvideo>.nfo`.
* **Namespaced sidecars**:

  * Folder-level: `tmdb.nfo`, `tvdb.json`, `openlibrary.json`, `audible.nfo`, `manual.nfo`, `override.json`
  * File-level: `<mediafilename>.tmdb.nfo`, `<mediafilename>.manual.json`
* **Art files** (preferred local): `poster.jpg`, `fanart.jpg`, `banner.jpg`, `cover.jpg`, `logo.png`, `disc.png`.

---

## 9) Minimal Reference Examples

### 9.1 Movie (single file; interoperable)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<movie>
  <title>Blade Runner 2049</title>
  <year>2017</year>
  <uniqueid type="tmdb" default="true">335984</uniqueid>
  <ratings><rating name="tmdb" max="10" default="true"><value>7.5</value></rating></ratings>
  <director>Denis Villeneuve</director>
  <actor><name>Ryan Gosling</name><role>K</role></actor>
  <art><poster>file:poster.jpg</poster><fanart>file:fanart.jpg</fanart></art>
</movie>
```

### 9.2 TV Episode (special ordering)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<episode>
  <title>Christmas Special</title>
  <season>0</season>
  <episode>1</episode>
  <airsbefore_season>2</airsbefore_season>
  <airsbefore_episode>1</airsbefore_episode>
  <aired>2015-12-25</aired>
</episode>
```

### 9.3 Book (multi-author, translator)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<book>
  <title>Example Anthology</title>
  <author>Alice Author</author>
  <author>Bob Writer</author>
  <translator>Chris Translator</translator>
  <series>Great Stories</series><series_index>3</series_index>
  <publisher>Fiction House</publisher><published>2020-05-01</published>
  <uniqueid type="openlibrary" default="true">OL12345M</uniqueid>
  <art><cover>file:cover.jpg</cover></art>
  <contributors>
    <contributor><name>Alice Author</name><role>author</role></contributor>
    <contributor><name>Bob Writer</name><role>author</role></contributor>
    <contributor><name>Chris Translator</name><role>translator</role></contributor>
  </contributors>
</book>
```

### 9.4 Audiobook (single-file m4b, chapters)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<audiobook>
  <title>Sample Book (Unabridged)</title>
  <author>Jane Doe</author>
  <narrator>Pat Reader</narrator>
  <publisher>AudioPub</publisher>
  <released>2023-04-15</released>
  <runtime>PT11H20M</runtime>
  <uniqueid type="audible" default="true">B012345678</uniqueid>
  <chapters relative="program">
    <chapter><number>1</number><title>Prologue</title><start>PT0H0M0S</start></chapter>
    <chapter><number>2</number><title>Chapter 1</title><start>PT0H12M30S</start></chapter>
  </chapters>
  <art><cover>file:cover.jpg</cover></art>
</audiobook>
```

### 9.5 Collection (boxset)

```xml
<?xml version="1.0" encoding="UTF-8"?>
<collection>
  <title>Example Trilogy</title>
  <uniqueid type="tmdb" default="true">999999</uniqueid>
  <members>
    <member><type>movie</type><uniqueid type="tmdb">111111</uniqueid></member>
    <member><type>movie</type><uniqueid type="tmdb">222222</uniqueid></member>
    <member><type>movie</type><uniqueid type="tmdb">333333</uniqueid></member>
  </members>
  <art><poster>file:poster.jpg</poster></art>
</collection>
```

---

## 10) Operational Guidance

* **What lives in `data/`?** Only the **consumed** sidecars needed by external players/indexers (e.g., `movie.nfo`, `<episode>.nfo`, `album.nfo`, or your chosen `<media>.manual.nfo`). Everything else stays in `metadata/`.
* **Write-back (third-party servers)**: if you enable “NFO saver” in external servers, make the files read-only or disable saver to prevent overwrite churn.
* **Chapters**: prefer program-relative timestamps for portability; allow optional `relative="part"` if you’re authoring per-file chapters in multi-part audiobooks.
* **IDs first**: always include **at least one** `<uniqueid>` with `default="true"` to guarantee stable cross-referencing and collection membership.

---

## Metadata File Naming Specification v2

### Core Principles

1. **Deterministic**: Same input always produces same metadata filename
2. **Collision-free**: Guarantees unique names even with duplicate filenames
3. **Reversible**: Can determine which media file a metadata file belongs to
4. **Filesystem-safe**: Works across all major filesystems
5. **Human-parseable**: Remains somewhat readable for debugging

### Naming Structure

```
/archive/<infohash>/
  ├── data/                    # immutable payload
  │   └── [torrent contents]
  └── metadata/
      ├── _torrent.source.nfo  # torrent-level metadata
      ├── _index.json          # metadata index/manifest
      └── items/               # per-file metadata
          └── <hash8>_<sanitized_name>.source.ext
```

### The Three-Tier System

#### 1. Torrent-Level Metadata
Files prefixed with `_` are torrent-level:
- `_torrent.tmdb.nfo` - metadata for the entire torrent
- `_collection.manual.nfo` - when torrent is treated as collection
- `_index.json` - manifest mapping files to metadata

#### 2. Single-Entity Torrents
When torrent contains one logical entity (most movies, single-book torrents):
- Use simplified names in `metadata/` root
- `movie.tmdb.nfo`, `book.goodreads.nfo`, etc.
- Detected by: single video file, or single book file, or explicit `_index.json` declaration

#### 3. Multi-Entity Torrents (your 1000 epub case)
Use the `items/` subdirectory with collision-resistant naming:

```python
def generate_metadata_filename(relative_path: str, source: str, ext: str) -> str:
    """
    Generate collision-free metadata filename.

    Args:
        relative_path: Path relative to torrent root (e.g., "books/sci-fi/foundation.epub")
        source: Metadata source (e.g., "goodreads", "manual")
        ext: Extension (e.g., "nfo", "json")

    Returns:
        Metadata filename like "a3f2c891_foundation.goodreads.nfo"
    """
    # Generate stable hash from full path
    path_hash = hashlib.sha256(relative_path.encode('utf-8')).hexdigest()[:8]

    # Extract and sanitize the filename
    filename = Path(relative_path).stem
    sanitized = re.sub(r'[^a-zA-Z0-9._-]', '_', filename)[:50]  # Limit length

    return f"items/{path_hash}_{sanitized}.{source}.{ext}"
```

### The Index Manifest

The `_index.json` file maps between torrent files and their metadata:

```json
{
  "version": "2.0",
  "type": "multi",  // or "single"
  "items": [
    {
      "path": "books/sci-fi/foundation.epub",
      "hash": "a3f2c891",
      "metadata": {
        "goodreads": "items/a3f2c891_foundation.goodreads.nfo",
        "manual": "items/a3f2c891_foundation.manual.json"
      }
    },
    {
      "path": "books/sci-fi/extras/foundation.epub",  // Same filename, different path
      "hash": "b7d4e2a5",
      "metadata": {
        "goodreads": "items/b7d4e2a5_foundation.goodreads.nfo"
      }
    }
  ]
}
```

### Implementation Details

#### Path Resolution Algorithm

```python
class MetadataResolver:
    def resolve_metadata_path(self, torrent_path: Path, file_path: str, source: str) -> Path:
        """Resolve metadata file path for a given torrent file."""

        index_file = torrent_path / 'metadata' / '_index.json'

        # Check if index exists
        if index_file.exists():
            index = json.loads(index_file.read_text())

            if index['type'] == 'single':
                # Simple naming for single-entity torrents
                media_type = self._detect_media_type(file_path)
                return torrent_path / 'metadata' / f'{media_type}.{source}.nfo'

            else:  # multi
                # Use hash-based naming
                path_hash = hashlib.sha256(file_path.encode()).hexdigest()[:8]
                stem = Path(file_path).stem
                sanitized = self._sanitize_filename(stem)[:50]
                return torrent_path / 'metadata' / 'items' / f'{path_hash}_{sanitized}.{source}.nfo'

        else:
            # Auto-detect based on torrent contents
            return self._auto_detect_naming(torrent_path, file_path, source)
```

#### Collision Example

Given a torrent with:
```
data/
  ├── classics/
  │   └── pride_and_prejudice.epub
  └── romance/
      └── pride_and_prejudice.epub  # Same name, different book
```

Generates metadata as:
```
metadata/
  ├── _index.json
  └── items/
      ├── 3a8f2c91_pride_and_prejudice.goodreads.nfo  # classics version
      └── 7b2d4ea5_pride_and_prejudice.goodreads.nfo  # romance version
```

### Special Cases

#### 1. Season Packs (TV)
```
metadata/
  ├── _torrent.tmdb.nfo          # series-level
  └── items/
      ├── 2a3b4c5d_s01e01.tmdb.nfo
      ├── 3b4c5d6e_s01e02.tmdb.nfo
      └── ...
```

#### 2. Discographies (Music)
```
metadata/
  ├── _artist.musicbrainz.nfo
  └── items/
      ├── albums/
      │   ├── 4c5d6e7f_album1.musicbrainz.nfo
      │   └── 5d6e7f8g_album2.musicbrainz.nfo
      └── tracks/
          └── [track-level metadata if needed]
```

#### 3. Nested Collections
For torrents containing multiple complete works:
```
metadata/
  ├── _collection.manual.nfo
  └── items/
      ├── 6e7f8a9b_harry_potter_1.tmdb.nfo
      ├── 7f8a9b0c_harry_potter_2.tmdb.nfo
      └── ...
```

### Migration Path

For existing libraries, provide a migration tool:

```python
def migrate_metadata_v1_to_v2(torrent_path: Path):
    """Migrate from simple naming to collision-resistant naming."""
    # 1. Scan existing metadata files
    # 2. Determine if multi-entity torrent
    # 3. Generate _index.json
    # 4. Move files to items/ with new names if needed
    # 5. Update any internal references
```

### Benefits

1. **Handles edge cases**: 1000 epubs with potential collisions work perfectly
2. **Progressive enhancement**: Simple cases stay simple, complex cases are handled
3. **Debuggable**: Hash prefix + sanitized name makes files identifiable
4. **Extensible**: New metadata sources just follow the pattern
5. **Tooling-friendly**: The index makes it easy to build tools that understand the structure

This specification scales from simple single-movie torrents to complex thousand-file ebook collections while maintaining consistency and preventing collisions.
