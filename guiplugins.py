
import plugins, os, sys, shutil, string, log4py

# The class to inherit from if you want test-based actions that can run from the GUI
class InteractiveAction(plugins.Action):
    def __init__(self, test, optionName = ""):
        self.test = test
        self.processes = []
        self.optionGroup = plugins.OptionGroup(optionName)
    def getOptionGroups(self):
        return [ self.optionGroup ]
    def killProcesses(self):
        # Don't leak processes
        for process in self.processes:
            if not process.hasTerminated():
                guilog.info("Killing '" + process.program + "' interactive process")
                process.kill()
    def canPerformOnTest(self):
        return self.test
    def getTitle(self):
        return None
    def getScriptTitle(self):
        return self.getTitle()
    def startExternalProgram(self, commandLine, shellTitle = None):
        if shellTitle:
            commandLine = "xterm -bg white -T '" + shellTitle + "' -e " + commandLine
        process = plugins.BackgroundProcess(commandLine)
        self.processes.append(process)
        return process
    def viewFile(self, fileName, wait = 0):
        viewProgram = self.test.getConfigValue("view_program")
        guilog.info("Viewing file " + os.path.basename(fileName) + " using '" + viewProgram + "'")
        process = self.startExternalProgram(viewProgram + " " + fileName)
        if wait:
            process.waitForTermination()
    def getTextTestName(self):
        return "python " + sys.argv[0]
    def describe(self, testObj, postText = ""):
        guilog.info(testObj.getIndent() + repr(self) + " " + repr(testObj) + postText)
    
# Plugin for saving tests (standard)
class SaveTest(InteractiveAction):
    def __init__(self, test):
        InteractiveAction.__init__(self, test, "Saving")
        if self.canPerformOnTest():
            extensions = test.app.getVersionFileExtensions(forSave = 1)
            self.optionGroup.addOption("v", "Version to save", test.app.getFullVersion(forSave = 1), extensions)
            try:
                comparisonList = test.stateDetails.getComparisons()
                if self.hasPerformance(comparisonList):
                    exact = (len(comparisonList) != 1)
                    self.optionGroup.addSwitch("ex", "Exact Performance", exact, "Average Performance")
            except AttributeError:
                pass
    def __repr__(self):
        return "Saving"
    def canPerformOnTest(self):
        return self.test and self.test.state == self.test.FAILED
    def getTitle(self):
        return "Save"
    def hasPerformance(self, comparisonList):
        for comparison in comparisonList:
            if comparison.getType() != "difference" and comparison.hasDifferences():
                return 1
        return 0
    def getExactness(self):
        return self.optionGroup.getSwitchValue("ex", 1)
    def __call__(self, test):
        version = self.optionGroup.getOptionValue("v")
        self.describe(test, " - version " + version + ", exactness " + str(self.getExactness()))
        testComparison = test.stateDetails
        if testComparison:
            testComparison.save(self.getExactness(), version)

# Plugin for viewing files (non-standard). In truth, the GUI knows a fair bit about this action,
# because it's special and plugged into the tree view. Don't use this as a generic example!
class ViewFile(InteractiveAction):
    def __init__(self, test):
        InteractiveAction.__init__(self, test, "Viewing")
        try:
            if test.state >= test.RUNNING:
                self.optionGroup.addSwitch("rdt", "Include Run-dependent Text", 0)
                self.optionGroup.addSwitch("nf", "Show differences where present", 1)
            if test.state == test.RUNNING:
                self.optionGroup.addSwitch("f", "Follow file rather than view it", 1)
        except AttributeError:
            # Will get given applications too, don't need options there
            pass
    def __repr__(self):
        return "Viewing file"
    def canPerformOnTest(self):
        return 0
    def tmpFile(self, comparison):
        if self.optionGroup.getSwitchValue("rdt"):
            return comparison.tmpFile
        else:
            return comparison.tmpCmpFile
    def stdFile(self, comparison):
        if self.optionGroup.getSwitchValue("rdt"):
            return comparison.stdFile
        else:
            return comparison.stdCmpFile
    def followFile(self, fileName):
        baseName = os.path.basename(fileName)
        title = self.test.name + " (" + baseName + ")"
        followProgram = self.test.app.getConfigValue("follow_program")
        guilog.info("Following file " + title + " using '" + followProgram + "'")
        self.startExternalProgram(followProgram + " " + fileName, shellTitle=title)
    def view(self, comparison, fileName):
        if self.optionGroup.getSwitchValue("f"):
            return self.followFile(fileName)
        if not comparison:
            return self.viewFile(fileName)
        newFile = self.tmpFile(comparison)
        if comparison.newResult() or not self.optionGroup.getSwitchValue("nf"):
            self.viewFile(newFile)
        else:
            diffProgram = self.test.app.getConfigValue("diff_program")
            guilog.info("Comparing file " + os.path.basename(newFile) + "with previous version using '" + diffProgram + "'")
            self.startExternalProgram("tkdiff " + self.stdFile(comparison) + " " + newFile)

# And a generic import test. Note acts on test suites
class ImportTest(InteractiveAction):
    def __init__(self, suite):
        InteractiveAction.__init__(self, suite, "Adding " + self.testType())
        if self.canPerformOnTest():
            self.optionGroup.addOption("name", self.testType() + " Name")
            self.optionGroup.addOption("desc", self.testType() + " Description")
    def canPerformOnTest(self):
        return self.test and self.test.state == self.test.NOT_STARTED
    def getTitle(self):
        return "Add " + self.testType()
    def testType(self):
        return ""
    def setUpSuite(self, suite):
        testName = self.optionGroup.getOptionValue("name")
        guilog.info("Adding " + self.testType() + testName + " under test suite " + repr(suite))
        testDir = self.createTest(suite, testName, self.optionGroup.getOptionValue("desc"))
        self.createTestContents(suite, testDir)
        newTest = suite.addTest(testName, testDir)
        self.recordResults(newTest)
    def createTestContents(self, suite, testDir):
        pass
    def recordResults(self, newTest):
        pass
    def createTest(self, suite, testName, description):
        file = open(suite.testCaseFile, "a")
        file.write(os.linesep)
        file.write("# " + description + os.linesep)
        file.write(testName + os.linesep)
        testDir = os.path.join(suite.abspath, testName.strip())
        os.mkdir(testDir)
        return testDir
    
class ImportTestCase(ImportTest):
    def __init__(self, suite):
        ImportTest.__init__(self, suite)
        if self.canPerformOnTest():
            self.addOptionsFileOption()
            if self.appIsGUI():
                self.optionGroup.addSwitch("editsc", "Change user abilities (edit GUI script)")
            # Assume GUIs never deal with standard input
            if suite.app.getConfigValue("use_standard_input") and not self.appIsGUI():
                self.optionGroup.addSwitch("editin", "Create standard input file", not self.appIsGUI())
            self.optionGroup.addSwitch("runstd", "Collect standard results immediately", self.assumeShortTests())
            self.optionGroup.addSwitch("editlog", "Change system behaviour (edit log file)")
    def testType(self):
        return "Test"
    def assumeShortTests(self):
        return 1
    def appIsGUI(self):
        return 0
    def addOptionsFileOption(self):
        self.optionGroup.addOption("opt", "Command line options")
    def createTestContents(self, suite, testDir):
        self.writeOptionFile(suite, testDir)
        self.writeInputFile(suite, testDir)
    def recordResults(self, newTest):
        if self.appIsGUI():
            self.recordGUIActions(newTest)

        if self.optionGroup.getSwitchValue("runstd"):
            self.recordStandardResult(newTest)
    def recordGUIActions(self, test):
        print "Record your actions using the", test.app.fullName, "GUI..."
        test.app.makeWriteDirectory()
        test.makeBasicWriteDirectory()
        test.setUpEnvironment(parents=1)
        os.chdir(test.writeDirs[0])
        command = test.getExecuteCommand()
        recordCommand = self.getRecordCommand(command, test.abspath)
        os.system(recordCommand)
        test.tearDownEnvironment(parents=1)
        test.app.removeWriteDirectory()
        if self.optionGroup.getSwitchValue("editsc"):
            self.viewFile(os.path.join(test.abspath, "gui_script"), wait=1)
    def recordStandardResult(self, test):
        print "Running test", test, "to get standard behaviour..."
        commandLine = self.getTextTestName() + " -a " + test.app.name + " -o -t " + test.name + " -ts " + self.test.name \
                      + self.getStdResultOptions()
        stdout = os.popen(commandLine)
        for line in stdout.readlines():
            sys.stdout.write("> " + line)
        if self.optionGroup.getSwitchValue("editlog"):
            logFile = test.makeFileName(test.app.getConfigValue("log_file"))
            self.viewFile(logFile, wait=1)
    def getStdResultOptions(self):
        return ""
    def writeOptionFile(self, suite, testDir):
        optionString = self.getOptions()
        print "Using option string :", optionString
        optionFile = open(os.path.join(testDir, "options." + suite.app.name), "w")
        optionFile.write(optionString)
        if self.appIsGUI():
            optionFile.write(" " + self.getReplayOption())
        optionFile.write(os.linesep)
        return optionString
    def writeInputFile(self, suite, testDir):
        if not self.optionGroup.getSwitchValue("editin"):
            return
        inputFile = os.path.join(testDir, "input." + suite.app.name)
        file = open(inputFile, "w")
        file.write("<Enter standard input lines in this file>" + os.linesep)
        file.close()
        self.viewFile(inputFile, wait=1)
    def getOptions(self):
        return self.optionGroup.getOptionValue("opt")
    # We assume tested GUIs support record and replay. These default to command
    # line -replay and -record
    def getReplayOption(self):
        return "-replay gui_script"
    def getRecordCommand(self, command, testDir):
        return command.replace(self.getReplayOption(), "-record " + os.path.join(testDir, "gui_script"))

class ImportTestSuite(ImportTest):
    def __init__(self, suite):
        ImportTest.__init__(self, suite)
        if self.canPerformOnTest():
            self.addEnvironmentFileOptions()
    def testType(self):
        return "Suite"
    def createTestContents(self, suite, testDir):
        self.writeTestcasesFile(suite, testDir)
        self.writeEnvironmentFiles(suite, testDir)
    def writeTestcasesFile(self, suite, testDir):
        testCasesFile = os.path.join(testDir, "testsuite." + suite.app.name)        
        file = open(testCasesFile, "w")
        file.write("# Ordered list of tests in test suite. Add as appropriate" + os.linesep + os.linesep)
    def addEnvironmentFileOptions(self):
        self.optionGroup.addSwitch("env", "Add environment file")
    def writeEnvironmentFiles(self, suite, testDir):
        if self.optionGroup.getSwitchValue("env"):
            envFile = os.path.join(testDir, "environment")
            file = open(envFile, "w")
            file.write("# Dictionary of environment to variables to set in test suite" + os.linesep)

class SelectTests(InteractiveAction):
    def __init__(self, app):
        self.app = app
        self.test = app
        self.processes = []
        for group in app.optionGroups:
            if group.name.startswith("Select"):
                self.optionGroup = group
    def __repr__(self):
        return "Selecting"
    def canPerformOnTest(self):
        return 1
    def getTitle(self):
        return "Select"
    def getScriptTitle(self):
        return "Select indicated tests"
    def performOn(self, app, selTests):
        app.configObject.updateOptions(self.optionGroup)
        valid, testSuite = app.createTestSuite()
        guilog.info("Created test suite of size " + str(testSuite.size()))
        return testSuite

class ResetGroups(InteractiveAction):
    def getTitle(self):
        return "Reset"
    def getScriptTitle(self):
        return "Reset running options"
    def performOn(self, app, selTests):
        for group in app.optionGroups:
            group.reset()
    
class RunTests(InteractiveAction):
    def __init__(self, app):
        self.app = app
        self.test = app
        self.processes = []
        self.optionGroups = []
        for group in app.optionGroups:
            if group.name.startswith("Invisible"):
                self.invisibleGroup = group
            elif not group.name.startswith("Select"):
                self.optionGroups.append(group)
    def getOptionGroups(self):
        return self.optionGroups
    def __repr__(self):
        return "Running"
    def canPerformOnTest(self):
        return 1
    def getTitle(self):
        return "Run Tests"
    def getScriptTitle(self):
        return "Run selected tests"
    def performOn(self, app, selTests):
        if len(selTests) == 0:
            print "No tests selected - cannot run!"
            return
        ttOptions = string.join(self.getTextTestOptions(app, selTests))
        commandLine = self.getTextTestName() + " " + ttOptions
        print "Starting dynamic TextTest with options :", ttOptions
        shellTitle = app.fullName + " Tests"
        self.startExternalProgram(commandLine, shellTitle)
    def getTextTestOptions(self, app, selTests):
        ttOptions = [ "-a " + app.name ]
        ttOptions += self.invisibleGroup.getCommandLines()
        for group in self.optionGroups:
            ttOptions += group.getCommandLines()
        ttOptions.append("-t " + string.join(selTests, ","))
        return ttOptions

# Placeholder for all classes. Remember to add them!
class InteractiveActionHandler:
    def __init__(self):
        self.testClasses =  [ SaveTest ]
        self.suiteClasses = [ ImportTestCase, ImportTestSuite ]
        self.appClasses = [ SelectTests, RunTests, ResetGroups ]
    def getInstances(self, test):
        instances = []
        classList = self.getClassList(test)
        for intvActionClass in classList:
            instance = self.makeInstance(intvActionClass, test)
            instances.append(instance)
        return instances
    def getClassList(self, test):
        try:
            if test.classId() == "test-case":
                return self.testClasses
            else:
                return self.suiteClasses
        except AttributeError:
            return self.appClasses
    def makeInstance(self, className, test):
        module = test.getConfigValue("interactive_action_module")
        command = "from " + module + " import " + className.__name__ + " as realClassName"
        try:
            exec command
            return realClassName(test)
        except ImportError:
            return className(test)
        except:
            # If some invalid interactive action is provided, need to know which
            print "Error with interactive action", className.__name__
            raise sys.exc_type, sys.exc_value
        
interactiveActionHandler = InteractiveActionHandler()
guilog = None

def setUpGuiLog():
    global guilog
    guilog = plugins.getDiagnostics("GUI behaviour")
    if os.environ.has_key("TEXTTEST_NO_SPAWN"):
        guilog.set_loglevel(log4py.LOGLEVEL_NORMAL)
        guilog.set_target(os.path.abspath("gui_log.texttest"))
        guilog.set_formatstring("%M")
