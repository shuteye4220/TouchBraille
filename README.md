# Touch Braille Keyboard for NVDA

Type braille on a Windows touchscreen by tapping finger chords, the way braille screen input works on a phone. Built for the ROG Ally in tabletop mode (screen facing up), but it works on any touchscreen NVDA supports.

Input goes through NVDA's own braille input, so your input table and contracted or uncontracted setting come from NVDA's Braille settings.

## Install

Download `touchBraille-0.1.1.nvda-addon` from this repo and open it on the device to install. NVDA's touch support needs an installed copy of NVDA, not a portable one.

## Turning it on and off

- Five-finger double tap turns the keyboard on or off. You can change this in NVDA's Input Gestures dialog, under Touch Braille.
- Two-finger swipe down turns it off from inside the keyboard.

While the keyboard is on, all touches go to it; other NVDA touch gestures don't work until you turn it off.

## Layout

- 6 dot, left to right: dots 3, 2, 1, 4, 5, 6.
- 8 dot, left to right: dots 7, 3, 2, 1, 4, 5, 6, 8.
- Space bar: a strip along the bottom edge, nearest you. Tap it with a thumb for space, or hold it with dots for a space chord. On by default for the 8 dot keyboard.

As on a braille display, dot 7 alone erases and dot 8 alone is enter.

## Swipes

| Swipe | Action |
| --- | --- |
| One finger right | Space |
| Two fingers right | Enter |
| One finger left | Backspace |
| Two fingers left | Delete previous word |
| Two fingers up | Calibrate |
| Two fingers down | Turn keyboard off |

## Calibrating

Swipe up with two fingers, then place all 6 or 8 fingers where they rest naturally and lift them. A thumb on the space bar is ignored. Calibration is saved separately for the 6 and 8 dot keyboards. Until you calibrate, the dots are spread evenly across the screen.

## Space chord commands

Space chords are standard NVDA braille keyboard gestures, named like `bk:space+dot1`. Assign them in NVDA's Input Gestures dialog: choose a command, press Add, then type the chord. Bindings you make also apply to a braille display's keyboard.

## Settings

NVDA menu, Preferences, Settings, Touch Braille:

- 6 or 8 dot keyboard
- Swipe distance, as a percent of screen width
- Where the space bar is used (8 dot only, both, or off) and how tall it is
- Reset calibration

## How it works

NVDA normally merges fingers into gestures like "3-finger tap", losing where each finger landed. This add-on intercepts NVDA's raw per-finger touch events (`touchTracker.TrackerManager.update`) while the keyboard is on. Fingers that touch together, up to when the last one lifts, form one chord. Touches are matched to dot positions left to right, keeping their order, so two fingers can't land on the same dot.

The chord logic in `engine.py` has no NVDA imports, so it can be tested anywhere.

## Development

```
python tests/test_engine.py   # chord, swipe, space bar and calibration tests
python build.py               # builds touchBraille-<version>.nvda-addon
python build.py --check       # confirms the committed .nvda-addon matches the source
```

The built `.nvda-addon` file is committed to the repo, so rebuild it after changing the source. GitHub Actions runs the tests and the check on every push. To make a release, bump `version` in `addon/manifest.ini`, rebuild, commit, then push a tag such as `v0.2.0`; Actions creates the release with the add-on file attached.

## License

GNU General Public License version 2. See `LICENSE`.
