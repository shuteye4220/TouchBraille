# Touch Braille - type braille on a touchscreen with NVDA.
# Copyright (C) 2026 shuteye4220. Licensed under the GNU GPL v2.

import ctypes

import addonHandler
import brailleInput
import config
import globalPluginHandler
import inputCore
import keyboardHandler
import tones
import touchHandler
import touchTracker
import ui
import wx
from gui import guiHelper, nvdaControls
from gui.settingsDialogs import NVDASettingsDialog, SettingsPanel
from logHandler import log
from scriptHandler import script

from .engine import TouchBrailleEngine

addonHandler.initTranslation()

CONF_SECTION = "touchBraille"
config.conf.spec[CONF_SECTION] = {
	"dots": "integer(default=6, min=6, max=8)",
	"swipePercent": "integer(default=6, min=2, max=25)",
	"spaceBar": 'option("8dot", "always", "off", default="8dot")',
	"spaceBarPercent": "integer(default=20, min=10, max=40)",
	"calibration6": 'string(default="")',
	"calibration8": 'string(default="")',
}

TOUCH_MODE = "braille"

# (direction, number of fingers) -> action name
SWIPES = {
	("right", 1): "space",
	("right", 2): "enter",
	("left", 1): "backspace",
	("left", 2): "deleteWord",
	("up", 2): "calibrate",
	("down", 2): "exit",
}

SM_CXSCREEN = 0
SM_CYSCREEN = 1

# Settings values for the space bar, in the order shown in the settings panel.
SPACE_BAR_CHOICES = ("8dot", "always", "off")

_plugin = None


def _calibrationKey(numDots):
	return "calibration8" if numDots == 8 else "calibration6"


def _parseCalibration(text):
	try:
		return [int(v) for v in text.split(",") if v.strip()]
	except ValueError:
		return []


class TouchBrailleInputGesture(brailleInput.BrailleInputGesture):
	"""A braille keyboard gesture, run through NVDA's own braille input.

	This means your braille input table, contracted input and any bk: gesture
	bindings all apply, the same as typing on a braille display.
	"""

	def __init__(self, dots=0, space=False):
		super().__init__()
		self.dots = dots
		self.space = space


class TouchBrailleSettingsPanel(SettingsPanel):
	# Translators: title of the settings panel.
	title = _("Touch Braille")

	def makeSettings(self, settingsSizer):
		conf = config.conf[CONF_SECTION]
		helper = guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		self.dotsList = helper.addLabeledControl(
			# Translators: label for the 6 or 8 dot choice.
			_("Braille &keyboard:"),
			wx.Choice,
			choices=[_("6 dot"), _("8 dot")],
		)
		self.dotsList.SetSelection(1 if conf["dots"] == 8 else 0)
		self.swipeSpin = helper.addLabeledControl(
			# Translators: label for how far a finger must move to count as a swipe.
			_("&Swipe distance, percent of screen width:"),
			nvdaControls.SelectOnFocusSpinCtrl,
			min=2,
			max=25,
			initial=conf["swipePercent"],
		)
		self.spaceBarList = helper.addLabeledControl(
			# Translators: label for where the bottom-edge space bar is used.
			_("Space bar along the &bottom edge:"),
			wx.Choice,
			choices=[_("8 dot keyboard only"), _("Both keyboards"), _("Off")],
		)
		self.spaceBarList.SetSelection(SPACE_BAR_CHOICES.index(conf["spaceBar"]))
		self.spaceBarSpin = helper.addLabeledControl(
			# Translators: label for how tall the space bar strip is.
			_("Space bar &height, percent of screen height:"),
			nvdaControls.SelectOnFocusSpinCtrl,
			min=10,
			max=40,
			initial=conf["spaceBarPercent"],
		)
		# Translators: button that clears the saved finger positions.
		self.resetButton = helper.addItem(wx.Button(self, label=_("&Reset calibration for this keyboard")))
		self.resetButton.Bind(wx.EVT_BUTTON, self.onResetCalibration)

	def _selectedDots(self):
		return 8 if self.dotsList.GetSelection() == 1 else 6

	def onResetCalibration(self, evt):
		config.conf[CONF_SECTION][_calibrationKey(self._selectedDots())] = ""
		if _plugin:
			_plugin.loadConfig()
		# Translators: reported after the calibration is cleared.
		ui.message(_("Calibration reset"))

	def onSave(self):
		conf = config.conf[CONF_SECTION]
		conf["dots"] = self._selectedDots()
		conf["swipePercent"] = self.swipeSpin.GetValue()
		conf["spaceBar"] = SPACE_BAR_CHOICES[self.spaceBarList.GetSelection()]
		conf["spaceBarPercent"] = self.spaceBarSpin.GetValue()
		if _plugin:
			_plugin.loadConfig()


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	# Translators: input gestures category.
	scriptCategory = _("Touch Braille")

	def __init__(self):
		global _plugin
		super().__init__()
		_plugin = self
		self._userActive = False
		self._prevTouchMode = None
		self._modeRegistered = False
		self._originalUpdate = None
		self.engine = TouchBrailleEngine(
			onDots=self._onDots,
			onSwipe=self._onSwipe,
			onCalibrated=self._onCalibrated,
			onCalibrationFailed=self._onCalibrationFailed,
			onRejected=self._onRejected,
		)
		self.loadConfig()
		config.post_configProfileSwitch.register(self.loadConfig)
		NVDASettingsDialog.categoryClasses.append(TouchBrailleSettingsPanel)
		self._registerTouchMode()
		self._patchTracker()

	def terminate(self):
		global _plugin
		self._deactivate()
		self._unpatchTracker()
		self._unregisterTouchMode()
		try:
			NVDASettingsDialog.categoryClasses.remove(TouchBrailleSettingsPanel)
		except ValueError:
			pass
		config.post_configProfileSwitch.unregister(self.loadConfig)
		_plugin = None
		super().terminate()

	# Configuration

	def loadConfig(self, *args, **kwargs):
		conf = config.conf[CONF_SECTION]
		numDots = 8 if conf["dots"] == 8 else 6
		metrics = ctypes.windll.user32.GetSystemMetrics
		width = metrics(SM_CXSCREEN) or 1920
		height = metrics(SM_CYSCREEN) or 1080
		spaceBar = conf["spaceBar"]
		spaceTop = None
		if spaceBar == "always" or (spaceBar == "8dot" and numDots == 8):
			spaceTop = height * (100 - conf["spaceBarPercent"]) / 100
		self.engine.configure(
			numDots=numDots,
			swipeDistance=width * conf["swipePercent"] / 100,
			calibration=_parseCalibration(conf[_calibrationKey(numDots)]),
			screenWidth=width,
			spaceTop=spaceTop,
		)

	# Touch modes

	def _registerTouchMode(self):
		"""Add "braille keyboard mode" to the modes NVDA's 3-finger tap cycles through."""
		try:
			if TOUCH_MODE not in touchHandler.availableTouchModes:
				touchHandler.availableTouchModes.append(TOUCH_MODE)
			# Translators: announced when cycling to this touch mode.
			touchHandler.touchModeLabels[TOUCH_MODE] = _("braille keyboard mode")
			self._modeRegistered = True
		except Exception:
			log.debugWarning("Touch Braille: could not register a touch mode", exc_info=True)

	def _unregisterTouchMode(self):
		if not self._modeRegistered:
			return
		try:
			if self._currentTouchMode() == TOUCH_MODE:
				self._setTouchMode("object")
			touchHandler.availableTouchModes.remove(TOUCH_MODE)
			touchHandler.touchModeLabels.pop(TOUCH_MODE, None)
		except Exception:
			log.debugWarning("Touch Braille: could not unregister touch mode", exc_info=True)
		self._modeRegistered = False

	def _currentTouchMode(self):
		handler = touchHandler.handler
		return getattr(handler, "_curTouchMode", None) if handler else None

	def _setTouchMode(self, mode):
		handler = touchHandler.handler
		if not handler:
			return
		setter = getattr(handler, "setMode", None)
		try:
			if setter:
				setter(mode)
			else:
				handler._curTouchMode = mode
		except ValueError:
			# Mode not registered on this NVDA version; the add-on's own flag still works.
			pass

	def _isCapturing(self):
		return self._userActive or self._currentTouchMode() == TOUCH_MODE

	def _activate(self):
		mode = self._currentTouchMode()
		if mode != TOUCH_MODE:
			self._prevTouchMode = mode
		self.engine.reset()
		self._userActive = True
		if self._modeRegistered:
			self._setTouchMode(TOUCH_MODE)

	def _deactivate(self):
		self._userActive = False
		self.engine.reset()
		self.engine.calibrating = False
		if self._currentTouchMode() == TOUCH_MODE:
			self._setTouchMode(self._prevTouchMode or "object")
		self._prevTouchMode = None

	# Raw touch interception

	def _patchTracker(self):
		"""Read each finger's own position before NVDA merges fingers into gestures.

		NVDA's touch window passes every finger down, move and up event to
		TrackerManager.update. While the braille keyboard is on, those events
		go to the braille engine instead, so no other touch gestures fire.
		"""
		original = touchTracker.TrackerManager.update
		plugin = self

		def update(manager, ID, x, y, complete=False):
			if plugin._isCapturing():
				try:
					plugin.engine.handle(ID, x, y, complete)
				except Exception:
					log.error("Touch Braille: error handling touch, turning keyboard off", exc_info=True)
					plugin._userActive = False
					plugin.engine.reset()
					wx.CallAfter(plugin._deactivate)
				return
			return original(manager, ID, x, y, complete)

		update._touchBrailleOriginal = original
		touchTracker.TrackerManager.update = update
		self._originalUpdate = original

	def _unpatchTracker(self):
		current = touchTracker.TrackerManager.update
		if self._originalUpdate and getattr(current, "_touchBrailleOriginal", None) is self._originalUpdate:
			touchTracker.TrackerManager.update = self._originalUpdate
		self._originalUpdate = None

	# Engine callbacks. These run on NVDA's touch thread, so hand work to the main thread.

	def _onDots(self, dots, space):
		wx.CallAfter(self._executeBraille, dots, space)

	def _onSwipe(self, direction, fingers):
		action = SWIPES.get((direction, fingers))
		if action == "exit":
			self._userActive = False
			wx.CallAfter(self._exitFromSwipe)
		elif action == "calibrate":
			self.engine.startCalibration()
			wx.CallAfter(self._announceCalibration)
		elif action:
			wx.CallAfter(getattr(self, "_swipe_" + action))
		else:
			wx.CallAfter(tones.beep, 220, 60)

	def _onCalibrated(self, xs):
		wx.CallAfter(self._saveCalibration, list(xs))

	def _onCalibrationFailed(self, expected, got):
		# Translators: when the wrong number of fingers were placed during calibration.
		wx.CallAfter(ui.message, _("Got {got} fingers, need {expected}. Try again.").format(got=got, expected=expected))

	def _onRejected(self, fingers):
		wx.CallAfter(tones.beep, 220, 60)

	# Main-thread actions

	def _executeBraille(self, dots, space):
		try:
			inputCore.manager.executeGesture(TouchBrailleInputGesture(dots=dots, space=space))
		except inputCore.NoInputGestureAction:
			pass

	def _swipe_space(self):
		self._executeBraille(0, True)

	def _swipe_enter(self):
		brailleInput.handler.enter()

	def _swipe_backspace(self):
		brailleInput.handler.eraseLastCell()

	def _swipe_deleteWord(self):
		keyboardHandler.KeyboardInputGesture.fromName("control+backspace").send()

	def _exitFromSwipe(self):
		self._deactivate()
		# Translators: reported when the braille keyboard is turned off.
		ui.message(_("Braille keyboard off"))

	def _announceCalibration(self):
		ui.message(
			# Translators: calibration instructions.
			_("Calibrating. Place all {n} fingers on the screen, then lift them.").format(n=self.engine.numDots)
		)

	def _saveCalibration(self, xs):
		conf = config.conf[CONF_SECTION]
		conf[_calibrationKey(self.engine.numDots)] = ",".join(str(int(x)) for x in xs)
		try:
			config.conf.save()
		except Exception:
			log.debugWarning("Touch Braille: could not save configuration", exc_info=True)
		# Translators: reported when calibration succeeds.
		ui.message(_("Calibrated"))

	# Scripts

	@script(
		# Translators: input help for the toggle command.
		description=_("Turns the touch braille keyboard on or off"),
		gesture="ts:5finger_doubleTap",
	)
	def script_toggleTouchBraille(self, gesture):
		if self._isCapturing():
			self._deactivate()
			ui.message(_("Braille keyboard off"))
		else:
			self._activate()
			# Translators: reported when the braille keyboard is turned on.
			ui.message(_("Braille keyboard on"))

	@script(
		# Translators: input help for the calibrate command.
		description=_("Turns on the touch braille keyboard and starts calibrating finger positions"),
	)
	def script_calibrate(self, gesture):
		if not self._isCapturing():
			self._activate()
		self.engine.startCalibration()
		self._announceCalibration()
