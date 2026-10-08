"""Safe ZIP mass-import for Fightbase boxer portraits.

ZIP filenames map only to exact, unique boxer names (or explicit boxer IDs).
The import cannot determine who is depicted inside an image; an administrator
must ensure that each file actually shows the correct boxer and is licensed.
"""
from __future__ import annotations

import io
import os
import re
import unicodedata
import uuid
import warnings
import zipfile
from collections import Counter, defaultdict
from pathlib import PurePosixPath
from PIL import Image, ImageOps, UnidentifiedImageError
import boxing_feed as feed

MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_FILES = 250
MAX_SINGLE_IMAGE_BYTES = 5 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 120 * 1024 * 1024
MAX_PIXEL_COUNT = 16_000_000
EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class ImportValidationError(ValueError):
    """A fatal ZIP-level validation error; no photos should be imported."""


def name_key(name: str) -> str:
    """Forgive harmless filename punctuation, not mistaken identities."""
    value = unicodedata.normalize("NFKD", name).casefold()
    value = "".join(c for c in value if not unicodedata.combining(c))
    return re.sub(r"[\W_]+", " ", value, flags=re.UNICODE).strip()


def _image_name(archive_member):
    """Never extract ZIP paths. Use only safe basenames inside any folder."""
    raw = archive_member.filename
    if (not raw or "\x00" in raw or "\\" in raw or len(raw) > 320
            or raw.startswith("/") or
            any(part == ".." for part in PurePosixPath(raw).parts)):
        return None
    if archive_member.is_dir():
        return None
    path = PurePosixPath(raw)
    if any(part.startswith(".") or part == "__MACOSX" for part in path.parts):
        return None
    return path.name


def _target(filename: str, by_name, by_id):
    stem = PurePosixPath(filename).stem.strip()
    if "__" in stem:
        label, identifier = stem.rsplit("__", 1)
        boxer = by_id.get(identifier)
        if boxer and name_key(label) == name_key(boxer["name"]):
            return boxer, None
        return None, "Boxer-ID oder Name passt nicht: Name__profil-id.jpg"
    matches = by_name.get(name_key(stem), ())
    if len(matches) == 1:
        return matches[0], None
    if len(matches) > 1:
        alternatives = ", ".join(r["id"] for r in matches[:3])
        return None, ("Mehrere Boxerprofile mit diesem Namen. Bitte Dateiname als "
                      "Name__profil-id.jpg angeben (z. B. " + alternatives + ")")
    return None, "Kein Boxer mit diesem exakten Namen in Fightbase"


def _convert_photo(raw):
    """Verify image bytes, then re-encode to safe consistent WebP."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                image.verify()
            with Image.open(io.BytesIO(raw)) as image:
                if image.format not in ("JPEG", "PNG", "WEBP"):
                    raise ValueError("Nicht unterstütztes Bildformat")
                if image.width * image.height > MAX_PIXEL_COUNT:
                    raise ValueError("Bild zu hochauflösend (über 16 Megapixel)")
                image = ImageOps.exif_transpose(image)
                if min(image.width, image.height) < 250:
                    raise ValueError("Mindestgröße: 250 × 250 Pixel")
                image.thumbnail((1600, 1600), Image.Resampling.LANCZOS)
                output = io.BytesIO()
                image.convert("RGB").save(output, "WEBP", quality=86, method=5)
                return output.getvalue()
    except (UnidentifiedImageError, OSError, ValueError,
            Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Bild ungültig: " + str(exc)[:100]) from exc


def import_archive(upload_stream, *, overwrite=False, upload_folder=None):
    """Import one ZIP, returning a report with all skipped/ambiguous files.

    No archive file paths are written. Only generated random WebP filenames are
    stored, and database selection uses exact name matching or explicit ID.
    Individual corrupt images are skipped; invalid ZIP structure fails early.
    """
    from fightbase_admin import UPLOADS
    folder = upload_folder or UPLOADS

    raw_archive = upload_stream.read(MAX_ARCHIVE_BYTES + 1)
    if len(raw_archive) > MAX_ARCHIVE_BYTES:
        raise ImportValidationError("Die ZIP-Datei darf höchstens 64 MB groß sein.")
    if not raw_archive or not zipfile.is_zipfile(io.BytesIO(raw_archive)):
        raise ImportValidationError("Bitte eine gültige ZIP-Datei auswählen.")

    with zipfile.ZipFile(io.BytesIO(raw_archive)) as zf:
        members = [member for member in zf.infolist() if not member.is_dir()]
        if len(members) > MAX_FILES:
            raise ImportValidationError("Pro ZIP sind höchstens 250 Dateien erlaubt.")
        if sum(member.file_size for member in members) > MAX_UNCOMPRESSED_BYTES:
            raise ImportValidationError(
                "Die entpackten Dateien sind insgesamt zu groß (maximal 120 MB).")

        # IDs are authoritative. A repeated name is NEVER silently guessed.
        by_name = defaultdict(list)
        by_id = {}
        for fighter in feed.rows("SELECT id,name FROM hub_fighters ORDER BY id"):
            row = dict(fighter)
            by_id[row["id"]] = row
            by_name[name_key(row["name"])].append(row)

        existing = {
            r["fighter_id"]: r["filename"]
            for r in feed.rows("SELECT fighter_id,filename FROM hub_admin_photos")
        }
        results = []
        candidates = []
        for member in members:
            filename = _image_name(member)
            if not filename:
                results.append(dict(filename=member.filename[:180],
                                    status="skipped",reason="Ungültiger Dateipfad oder Systemdatei"))
                continue
            ext = PurePosixPath(filename).suffix.casefold()
            if ext not in EXTENSIONS:
                results.append(dict(filename=filename,status="skipped",
                                    reason="Kein unterstütztes Foto (JPG, PNG, WebP)"))
                continue
            if member.file_size > MAX_SINGLE_IMAGE_BYTES:
                results.append(dict(filename=filename,status="skipped",
                                    reason="Bild zu groß (maximal 5 MB)"))
                continue
            fighter, error = _target(filename, by_name, by_id)
            if error:
                results.append(dict(filename=filename,status="skipped",reason=error))
                continue
            candidates.append((member, filename, fighter))

        collisions = Counter(fighter["id"] for _, _, fighter in candidates)
        for member, filename, fighter in candidates:
            fid = fighter["id"]
            if collisions[fid] > 1:
                results.append(dict(filename=filename,boxer=fighter["name"],
                   status="skipped", reason="Mehrere Fotos in der ZIP für dasselbe Boxerprofil"))
                continue
            if fid in existing and not overwrite:
                results.append(dict(filename=filename,boxer=fighter["name"],
                   fighter_id=fid,status="skipped",
                   reason="Eigenes Foto bereits vorhanden; Ersetzen wurde nicht aktiviert"))
                continue
            try:
                with zf.open(member) as source:
                    data = source.read(MAX_SINGLE_IMAGE_BYTES + 1)
                if len(data) > MAX_SINGLE_IMAGE_BYTES:
                    raise ValueError("Bild größer als 5 MB")
                webp = _convert_photo(data)
                folder.mkdir(parents=True, exist_ok=True)
                random_file = uuid.uuid4().hex + ".webp"
                path = folder / random_file
                with open(path, "xb") as handle:
                    handle.write(webp)
                try:
                    with feed.connect() as db:
                        db.execute("""INSERT INTO hub_admin_photos(
                          fighter_id,filename,source_url,updated_at)
                          VALUES(?,?,NULL,?)
                          ON CONFLICT(fighter_id) DO UPDATE SET
                          filename=excluded.filename,
                          source_url=excluded.source_url,
                          updated_at=excluded.updated_at""",
                          (fid, random_file, feed.utcnow()))
                except Exception:
                    path.unlink(missing_ok=True)
                    raise
                previous = existing.get(fid)
                if previous and re.fullmatch(r"[0-9a-f]{32}\.webp", previous):
                    (folder / previous).unlink(missing_ok=True)
                results.append(dict(filename=filename, boxer=fighter["name"],
                    fighter_id=fid, status="replaced" if previous else "imported",
                    reason="Automatisch anhand des eindeutigen Boxerprofils zugeordnet"))
                existing[fid] = random_file
            except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as exc:
                results.append(dict(filename=filename,boxer=fighter["name"],
                    status="error",reason=str(exc)[:160]))

    counts = Counter(entry["status"] for entry in results)
    return {
        "files": len(members),
        "imported": counts["imported"],
        "replaced": counts["replaced"],
        "skipped": counts["skipped"],
        "errors": counts["error"],
        "entries": results,
    }
