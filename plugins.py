
import os, log4py
from types import FileType

# Generic configuration class
class Configuration:
    def __init__(self, optionMap):
        self.optionMap = optionMap
    def getOptionString(self):
        return ""
    def getActionSequence(self):
        return []
    def getFilterList(self):
        return []
    def getVersions(self, app):
        return []
    def getExecuteCommand(self, binary, test):
        return binary + " " + test.options
    def printHelpText(self):
        pass
    
# Filter interface: all must provide these three methods
class Filter:
    def acceptsTestCase(self, test):
        return 1
    def acceptsTestSuite(self, suite):
        return 1
    def acceptsApplication(self, app):
        return 1

# Generic action to be performed: all actions need to provide these four methods
class Action:
    def __call__(self, test):
        pass
    def setUpSuite(self, suite):
        pass
    def setUpApplication(self, app):
        pass
    def getFilter(self):
        return None
    def processUnRunnable(self, test):
        pass
    def getCleanUpAction(self):
        return None
    # Useful for printing in a certain format...
    def describe(self, testObj, postText = ""):
        print testObj.getIndent() + repr(self) + " " + repr(testObj) + postText
    def __repr__(self):
        return "Doing nothing on"

# Simple handle to get diagnostics object. Better than using log4py directly,
# as it ensures everything appears by default in a standard place with a standard name.
def getDiagnostics(diagName):
    return log4py.Logger().get_instance(diagName)

# Exception to throw. It's generally good to throw this internally
class TextTestError(RuntimeError):
    pass

# Action composed of other sub-parts
class CompositeAction(Action):
    def __init__(self, subActions):
        self.subActions = subActions
    def __repr__(self):
        return "Performing " + repr(self.subActions) + " on"
    def __call__(self, test):
        for subAction in self.subActions:
            subAction(test)
    def setUpSuite(self, suite):
        for subAction in self.subActions:
            subAction.setUpSuite(suite)
    def setUpApplication(self, app):
        for subAction in self.subActions:
            subAction.setUpApplication(app)
    def processUnRunnable(self, test):
        for subAction in self.subActions:
            subAction.processUnRunnable(test)
    def getCleanUpAction(self):
        cleanUpSubActions = []
        for subAction in self.subActions:
            cleanUp = subAction.getCleanUpAction()
            if cleanUp != None:
                cleanUpSubActions.append(cleanUp)
        if len(cleanUpSubActions):
            return CompositeAction(cleanUpSubActions)
        else:
            return None

# Action for wrapping an executable that isn't Python, or can't be imported in the usual way
class NonPythonAction(Action):
    def __init__(self, actionText):
        self.script = os.path.abspath(actionText)
    def __repr__(self):
        return "Running script " + os.path.basename(self.script) + " for"
    def __call__(self, test):
        self.describe(test)
        self.callScript(test, "test_level")
    def setUpSuite(self, suite):
        self.describe(suite)
        os.chdir(suite.abspath)
        self.callScript(suite, "suite_level")
    def setUpApplication(self, app):
        print self, "application", app
        os.chdir(app.abspath)
        os.system(self.script + " app_level " + app.name)
    def callScript(self, test, level):
        os.system(self.script + " " + level + " " + test.name + " " + test.app.name)
