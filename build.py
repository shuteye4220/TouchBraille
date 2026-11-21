"""Package the add-on.

python build.py          -> writes touchBraille-<version>.nvda-addon
python build.py --check  -> fails if the committed .nvda-addon doesn't match the source
"""

import configparser
import io
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.join(ROOT, "addon")


def version():
	with open(os.path.join(ADDON, "manifest.ini"), encoding="utf-8") as f:
		manifest = configparser.ConfigParser()
		manifest.read_string("[addon]\n" + f.read())
	return manifest["addon"]["version"].strip()


def addonFiles():
	"""Yield (path inside the add-on, full path), in a stable order."""
	for folder, dirs, files in sorted(os.walk(ADDON)):
		dirs[:] = sorted(d for d in dirs if d != "__pycache__")
		for name in sorted(files):
			if not name.endswith(".pyc"):
				full = os.path.join(folder, name)
				yield os.path.relpath(full, ADDON).replace(os.sep, "/"), full


def build(target):
	with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
		for arcname, full in addonFiles():
			z.write(full, arcname)


def contents(zipSource):
	with zipfile.ZipFile(zipSource) as z:
		return {name: z.read(name) for name in z.namelist()}


def main():
	out = os.path.join(ROOT, f"touchBraille-{version()}.nvda-addon")
	if "--check" in sys.argv[1:]:
		fresh = io.BytesIO()
		build(fresh)
		if not os.path.exists(out):
			sys.exit(f"Missing {os.path.basename(out)}. Run: python build.py")
		if contents(out) != contents(fresh):
			sys.exit(f"{os.path.basename(out)} is out of date. Run: python build.py")
		print(f"{os.path.basename(out)} matches the source")
		return
	build(out)
	print(out)


if __name__ == "__main__":
	main()
