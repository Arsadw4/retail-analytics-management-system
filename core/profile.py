"""Filesystem-backed profile photo helpers.

Profile photos are intentionally stored outside the database so this feature
can use the existing schema unchanged. Each authenticated user owns at most
one photo named from their immutable user_id.
"""
import os
import logging
import tempfile
from glob import glob

from flask import current_app
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)


def _profile_dir():
    path = os.path.join(current_app.static_folder, "uploads", "profiles")
    os.makedirs(path, exist_ok=True)
    return path


def get_profile_photo_filename(user_id):
    if not user_id:
        return None
    directory = _profile_dir()
    allowed = current_app.config.get("UPLOAD_ALLOWED_EXTENSIONS", {"png", "jpg", "jpeg", "webp"})
    candidates = []
    for ext in allowed:
        candidates.extend(glob(os.path.join(directory, f"user_{int(user_id)}.{ext.lower()}")))
    if not candidates:
        return None
    return os.path.basename(max(candidates, key=os.path.getmtime))


def _valid_image_signature(file_storage):
    """Reject obvious non-image uploads while keeping the existing extension allow-list."""
    stream = file_storage.stream
    position = stream.tell()
    header = stream.read(12)
    stream.seek(position)
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return True
    if header.startswith(b"\xff\xd8\xff"):
        return True
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return True
    return False


def save_profile_photo(user_id, file_storage):
    if not user_id or not file_storage or not file_storage.filename:
        raise ValueError("Please select a profile photo.")

    original = secure_filename(file_storage.filename)
    if not original or "." not in original:
        raise ValueError("Please select a valid JPG, PNG or WEBP image.")
    ext = original.rsplit(".", 1)[1].lower()
    allowed = current_app.config.get("UPLOAD_ALLOWED_EXTENSIONS", {"png", "jpg", "jpeg", "webp"})
    if ext not in allowed:
        raise ValueError("Unsupported image type. Allowed: " + ", ".join(sorted(allowed)))
    if not _valid_image_signature(file_storage):
        raise ValueError("The selected file is not a valid image.")

    stream = file_storage.stream
    position = stream.tell()
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(position)
    if size > 2 * 1024 * 1024:
        raise ValueError("Profile photo must be 2 MB or smaller.")

    directory = _profile_dir()
    filename = f"user_{int(user_id)}.{ext}"
    target = os.path.join(directory, filename)

    # Stage the new file next to the target and replace it atomically. Keep
    # the current photo intact if writing the replacement fails.
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=f".user_{int(user_id)}_", suffix=".tmp",
            dir=directory, delete=False,
        ) as temporary_file:
            temporary_path = temporary_file.name
            file_storage.save(temporary_file)
        os.replace(temporary_path, target)
        temporary_path = None
    except OSError:
        logger.exception("Could not save profile photo for user_id=%s.", user_id)
        raise
    finally:
        if temporary_path and os.path.exists(temporary_path):
            try:
                os.remove(temporary_path)
            except OSError:
                logger.exception("Could not remove temporary profile photo for user_id=%s.", user_id)

    # Remove an older file extension only after the replacement is safely in
    # place, so a failed upload never erases the user's current photo.
    for old in glob(os.path.join(directory, f"user_{int(user_id)}.*")):
        if os.path.abspath(old) == os.path.abspath(target):
            continue
        try:
            os.remove(old)
        except OSError:
            logger.exception("Could not remove an older profile photo for user_id=%s.", user_id)

    return filename


def remove_profile_photo(user_id):
    directory = _profile_dir()
    removed = False
    for path in glob(os.path.join(directory, f"user_{int(user_id)}.*")):
        try:
            os.remove(path)
            removed = True
        except OSError:
            logger.exception("Could not remove profile photo for user_id=%s.", user_id)
    return removed


def get_profile_photo_version(user_id):
    filename = get_profile_photo_filename(user_id)
    if not filename:
        return ""
    try:
        return str(int(os.path.getmtime(os.path.join(_profile_dir(), filename))))
    except OSError:
        return ""
