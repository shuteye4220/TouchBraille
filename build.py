"""Package the add-on: python build.py -> touchBraille-<version>.nvda-addon"""

import configparser
import os
import zipfile

ROOT = os.path.dirname(os.path.abspath(__file__))
ADDON = os.path.join(ROOT, "addon")


def main():
	with open(os.path.join(ADDON, "manifest.ini"), encoding="utf-8") as f:
		manifest = configparser.ConfigParser()
		manifest.read_string("[addon]\n" + f.read())
	version = manifest["addon"]["version"].strip()
	out = os.path.join(ROOT, f"touchBraille-{version}.nvda-addon")
	with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
		for folder, dirs, files in os.walk(ADDON):
			dirs[:] = [d for d in dirs if d != "__pycache__"]
			for name in files:
				if name.endswith(".pyc"):
					continue
				full = os.path.join(folder, name)
				z.write(full, os.path.relpath(full, ADDON))
	print(out)


if __name__ == "__main__":
	main()
