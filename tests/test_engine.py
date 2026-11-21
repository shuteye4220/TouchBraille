import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "addon", "globalPlugins", "touchBraille"))
from engine import TouchBrailleEngine, assignSlots, DOT_ORDERS

events = []
e = TouchBrailleEngine(
    onDots=lambda d, sp: events.append(("dots", d) if not sp else ("spdots", d)),
    onSwipe=lambda dr, n: events.append(("swipe", dr, n)),
    onCalibrated=lambda xs: events.append(("cal", xs)),
    onCalibrationFailed=lambda a, b: events.append(("calfail", a, b)),
    onRejected=lambda n: events.append(("rej", n)),
)
W = 1920
e.configure(6, W * 0.06, [], W)

def dots(*nums):
    m = 0
    for n in nums: m |= 1 << (n - 1)
    return m

def tap(xs, t=0.0):
    for i, x in enumerate(xs):
        e.handle(i, x, 500, False, now=t)
    for i, x in enumerate(xs):
        e.handle(i, x + 3, 502, True, now=t + 0.1)

slots = [W * (i + 0.5) / 6 for i in range(6)]  # 3 2 1 4 5 6
# letter a = dot 1 (third from left)
tap([slots[2]]); assert events[-1] == ("dots", dots(1)), events[-1]
# dots 1+4, slightly off-center
tap([slots[2] + 40, slots[3] - 40]); assert events[-1] == ("dots", dots(1, 4)), events[-1]
# all six
tap(slots); assert events[-1] == ("dots", dots(1,2,3,4,5,6))
# two fingers both near dot 1 slot: order preserved, distinct dots
tap([slots[2] - 10, slots[2] + 10]); assert events[-1] == ("dots", dots(2, 1)), bin(events[-1][1])
# 7 fingers in 6-dot -> reject
tap(slots + [W - 5]); assert events[-1] == ("rej", 7)
# swipe right one finger
e.handle(1, 900, 500, False, now=1); e.handle(1, 1100, 505, False, now=1.1); e.handle(1, 1150, 505, True, now=1.2)
assert events[-1] == ("swipe", "right", 1)
# two finger swipe down, one finger lags
e.handle(1, 900, 300, False, now=2); e.handle(2, 1000, 300, False, now=2)
e.handle(1, 900, 600, True, now=2.2); e.handle(2, 1000, 340, True, now=2.3)
assert events[-1] == ("swipe", "down", 2)
# rolling chord: finger 1 lifts before 2 lands -> two separate chords? no: 1 lifts while none else down -> chord ends
e.handle(5, slots[2], 500, False, now=3); e.handle(6, slots[3], 500, False, now=3.05)
e.handle(5, slots[2], 500, True, now=3.1); e.handle(6, slots[3], 500, True, now=3.15)
assert events[-1] == ("dots", dots(1, 4))
# ID reuse inside chord
e.handle(7, slots[0], 500, False, now=4); e.handle(8, slots[5], 500, False, now=4)
e.handle(7, slots[0], 500, True, now=4.1); e.handle(7, slots[1], 500, False, now=4.15)
e.handle(8, slots[5], 500, True, now=4.2); e.handle(7, slots[1], 500, True, now=4.25)
assert events[-1] == ("dots", dots(3, 2, 6)), bin(events[-1][1])
# stale chord reset
e.handle(9, 100, 100, False, now=5)
e.handle(10, slots[2], 500, False, now=20); e.handle(10, slots[2], 500, True, now=20.1)
assert events[-1] == ("dots", dots(1))
# calibration
e.startCalibration()
tap([100, 200, 300], t=30); assert events[-1] == ("calfail", 6, 3)
cal = [300, 450, 600, 1100, 1250, 1400]
tap(cal, t=31); assert events[-1][0] == "cal"
tap([600], t=32); assert events[-1] == ("dots", dots(1))
tap([1100], t=33); assert events[-1] == ("dots", dots(4))
tap([300, 1400], t=34); assert events[-1] == ("dots", dots(3, 6))
# 8 dot
e.configure(8, 115, [], W)
s8 = [W * (i + 0.5) / 8 for i in range(8)]
tap([s8[0]], t=40); assert events[-1] == ("dots", dots(7))
tap([s8[7]], t=41); assert events[-1] == ("dots", dots(8))
tap(s8, t=42); assert events[-1] == ("dots", 0xFF)
# assignSlots exhaustive check vs brute force
import itertools, random
random.seed(1)
for _ in range(2000):
    n = random.choice([6, 8]); k = random.randint(1, n)
    sx = sorted(random.uniform(0, 1920) for _ in range(n))
    tx = sorted(random.uniform(0, 1920) for _ in range(k))
    got = assignSlots(tx, sx)
    gc = sum(abs(t - sx[j]) for t, j in zip(tx, got))
    assert got == sorted(got) and len(set(got)) == k
    best = min(sum(abs(t - sx[j]) for t, j in zip(tx, c)) for c in itertools.combinations(range(n), k))
    assert abs(gc - best) < 1e-6

# space bar: 8 dot, bottom 20% of a 1080 tall screen
e.configure(8, 115, [], W, spaceTop=1080 * 0.8)
def touch(points, t):
    for i, (x, y) in enumerate(points): e.handle(100 + i, x, y, False, now=t)
    for i, (x, y) in enumerate(points): e.handle(100 + i, x, y, True, now=t + 0.1)
touch([(960, 1000)], 50); assert events[-1] == ("spdots", 0), events[-1]
touch([(s8[3], 500), (960, 1000)], 51); assert events[-1] == ("spdots", dots(1)), events[-1]
touch([(s8[2], 500), (s8[3], 500), (s8[4], 500), (900, 1000)], 52); assert events[-1] == ("spdots", dots(2, 1, 4))
touch([(s8[3], 500)], 53); assert events[-1] == ("dots", dots(1))
# all 8 fingers + thumb on space
touch([(x, 500) for x in s8] + [(960, 1050)], 54); assert events[-1] == ("spdots", 0xFF)
# calibration ignores a thumb on the space bar
e.startCalibration()
touch([(x, 500) for x in s8] + [(960, 1050)], 55); assert events[-1][0] == "cal" and len(events[-1][1]) == 8
# swipe with resting thumb counts as 1 finger
e.handle(1, 900, 500, False, now=60); e.handle(2, 960, 1000, False, now=60)
e.handle(1, 1150, 500, True, now=60.2); e.handle(2, 962, 1001, True, now=60.3)
assert events[-1] == ("swipe", "right", 1), events[-1]
print("all tests passed")
