import io
import os
import tempfile
import unittest

from flask import Flask
from PIL import Image
from werkzeug.datastructures import FileStorage

from core.profile import get_profile_photo_filename, save_profile_photo


def png_bytes():
    image = Image.new("RGB", (2, 2), color="navy")
    contents = io.BytesIO()
    image.save(contents, format="PNG")
    return contents.getvalue()


class FailingUpload:
    filename = "replacement.png"

    def __init__(self):
        self.stream = io.BytesIO(png_bytes())

    def save(self, destination):
        raise OSError("simulated write failure")


class ProfilePhotoTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.app = Flask(__name__, static_folder=self.temporary_directory.name)
        self.app.config["UPLOAD_ALLOWED_EXTENSIONS"] = {"png", "jpg", "jpeg", "webp"}

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_failed_replacement_preserves_existing_photo_and_cleans_temp_file(self):
        with self.app.app_context():
            photo_directory = os.path.join(self.app.static_folder, "uploads", "profiles")
            os.makedirs(photo_directory)
            existing_photo = os.path.join(photo_directory, "user_42.jpg")
            with open(existing_photo, "wb") as photo_file:
                photo_file.write(b"existing photo")

            with self.assertRaises(OSError):
                save_profile_photo(42, FailingUpload())

            with open(existing_photo, "rb") as photo_file:
                self.assertEqual(photo_file.read(), b"existing photo")
            self.assertEqual(os.listdir(photo_directory), ["user_42.jpg"])

    def test_successful_replacement_installs_new_photo_before_removing_old_extension(self):
        with self.app.app_context():
            photo_directory = os.path.join(self.app.static_folder, "uploads", "profiles")
            os.makedirs(photo_directory)
            with open(os.path.join(photo_directory, "user_42.jpg"), "wb") as old_photo:
                old_photo.write(b"old photo")
            upload = FileStorage(stream=io.BytesIO(png_bytes()), filename="replacement.png")

            saved_name = save_profile_photo(42, upload)

            self.assertEqual(saved_name, "user_42.png")
            self.assertEqual(get_profile_photo_filename(42), "user_42.png")
            with Image.open(os.path.join(photo_directory, saved_name)) as saved_image:
                self.assertEqual(saved_image.size, (2, 2))
            self.assertEqual(os.listdir(photo_directory), ["user_42.png"])


if __name__ == "__main__":
    unittest.main()
