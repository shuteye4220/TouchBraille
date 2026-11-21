# Touch Braille - chord and swipe recognition.
# This module has no NVDA imports so it can be tested on its own.
# Copyright (C) 2026 shuteye4220. Licensed under the GNU GPL v2.

import time

# Dots listed from the left edge of the screen to the right edge, tabletop mode
# (screen facing up, hands side by side along the bottom).
DOT_ORDERS = {
	6: (3, 2, 1, 4, 5, 6),
	8: (7, 3, 2, 1, 4, 5, 6, 8),
}

# A chord with no events for this long is treated as abandoned (lost touch-up).
STALE_SECONDS = 5.0


class _Pointer:
	__slots__ = ("startX", "startY", "x", "y", "maxDist")

	def __init__(self, x, y):
		self.startX = self.x = x
		self.startY = self.y = y
		self.maxDist = 0

	def move(self, x, y):
		self.x = x
		self.y = y
		dist = max(abs(x - self.startX), abs(y - self.startY))
		if dist > self.maxDist:
			self.maxDist = dist


def assignSlots(touchXs, slotXs):
	"""Match sorted touch positions to sorted slot positions.

	Each touch gets a different slot, left-to-right order is preserved,
	and the total distance is as small as possible.
	Returns a list of slot indexes, one per touch, or None if there are
	more touches than slots.
	"""
	k = len(touchXs)
	n = len(slotXs)
	if k > n:
		return None
	if k == 0:
		return []
	inf = float("inf")
	# cost[i][j]: best cost placing the first i touches within the first j slots.
	cost = [[0.0] * (n + 1)] + [[inf] * (n + 1) for _ in range(k)]
	for i in range(1, k + 1):
		row = cost[i]
		prev = cost[i - 1]
		x = touchXs[i - 1]
		for j in range(i, n + 1):
			skip = row[j - 1]
			take = prev[j - 1] + abs(x - slotXs[j - 1])
			row[j] = take if take <= skip else skip
	# Walk back to recover which slot each touch took.
	result = [0] * k
	i, j = k, n
	while i > 0:
		if j > i and cost[i][j] == cost[i][j - 1]:
			j -= 1
		else:
			result[i - 1] = j - 1
			i -= 1
			j -= 1
	return result


class TouchBrailleEngine:
	"""Turns raw per-finger touch events into braille chords and swipes.

	Callbacks are called on the thread that calls handle(); the caller is
	responsible for moving work to its UI thread.
	- onDots(dotsBitmask, space)  space is True if the space bar was part of the chord
	- onSwipe(direction, fingerCount)  direction is "left", "right", "up" or "down"
	- onCalibrated(slotXs)  sorted x positions of the calibrated fingers
	- onCalibrationFailed(expected, got)
	- onRejected(fingerCount)  too many fingers for the current keyboard
	"""

	def __init__(self, onDots, onSwipe, onCalibrated, onCalibrationFailed, onRejected):
		self._onDots = onDots
		self._onSwipe = onSwipe
		self._onCalibrated = onCalibrated
		self._onCalibrationFailed = onCalibrationFailed
		self._onRejected = onRejected
		self._down = {}  # pointer ID -> _Pointer, fingers currently touching
		self._chord = []  # every pointer that has touched during this chord
		self._lastEvent = 0.0
		self.calibrating = False
		self.numDots = 6
		self.swipeDistance = 100
		self._order = DOT_ORDERS[6]
		self._slotXs = []
		self.spaceTop = None  # touches starting at or below this y are the space bar

	def configure(self, numDots, swipeDistance, calibration, screenWidth, spaceTop=None):
		numDots = 8 if numDots == 8 else 6
		order = DOT_ORDERS[numDots]
		if calibration and len(calibration) == numDots:
			slotXs = sorted(calibration)
		else:
			# Uncalibrated: spread the dots evenly across the screen.
			slotXs = [screenWidth * (i + 0.5) / numDots for i in range(numDots)]
		# Assign together so the touch thread never sees a mismatched pair.
		self._order, self._slotXs = order, slotXs
		self.numDots = numDots
		self.swipeDistance = max(10, swipeDistance)
		self.spaceTop = spaceTop

	def reset(self):
		self._down.clear()
		self._chord = []

	def startCalibration(self):
		self.reset()
		self.calibrating = True

	def handle(self, pointerId, x, y, complete, now=None):
		if now is None:
			now = time.monotonic()
		if self._chord and now - self._lastEvent > STALE_SECONDS:
			self.reset()
		self._lastEvent = now
		pointer = self._down.get(pointerId)
		if pointer is None:
			if complete:
				# Touch-up for a finger we never saw land; ignore it.
				return
			pointer = _Pointer(x, y)
			self._down[pointerId] = pointer
			self._chord.append(pointer)
			return
		pointer.move(x, y)
		if not complete:
			return
		del self._down[pointerId]
		if not self._down:
			chord = self._chord
			self._chord = []
			self._finishChord(chord)

	def _finishChord(self, chord):
		spaceTop = self.spaceTop
		if spaceTop is None:
			spaceKeys, fingers = [], chord
		else:
			spaceKeys = [p for p in chord if p.startY >= spaceTop]
			fingers = [p for p in chord if p.startY < spaceTop]
		threshold = self.swipeDistance
		swiped = [p for p in chord if p.maxDist >= threshold]
		if swiped:
			dx = sum(p.x - p.startX for p in swiped) / len(swiped)
			dy = sum(p.y - p.startY for p in swiped) / len(swiped)
			if abs(dx) >= abs(dy):
				direction = "right" if dx > 0 else "left"
			else:
				direction = "down" if dy > 0 else "up"
			# A thumb resting on the space bar doesn't count as a swiping finger.
			count = len(fingers) + sum(1 for p in spaceKeys if p.maxDist >= threshold)
			self._onSwipe(direction, count)
			return
		touchXs = sorted(p.startX for p in fingers)
		if self.calibrating:
			if len(fingers) == self.numDots:
				self.calibrating = False
				self._slotXs = touchXs
				self._onCalibrated(touchXs)
			else:
				self._onCalibrationFailed(self.numDots, len(fingers))
			return
		order, slotXs = self._order, self._slotXs
		slots = assignSlots(touchXs, slotXs)
		if slots is None:
			self._onRejected(len(fingers))
			return
		dots = 0
		for slot in slots:
			dots |= 1 << (order[slot] - 1)
		self._onDots(dots, bool(spaceKeys))
