helpDescription = """
The Matador configuration is based on the Carmen configuration. It will compile all static rulesets in the test
suite before running any tests, if the library file "matador.o" has changed since the static ruleset was last built.""" 

helpOptions = """-diag      - Run with diagnostics on. This will set the environment variables DIAGNOSTICS_IN and DIAGNOSTICS_OUT to
             both point at the subdirectory ./Diagnostics in the test case. It will also disable performance checking,
             as producing lots of text tends to slow down the program, and will tell the comparator to also
             compare the diagnostics found in the ./Diagnostics subdirectory.
"""

helpScripts = """matador.ImportTest         - Import new test cases and test users.
                             The general principle is to add entries to the "testsuite.<app>" file and then
                             run this action, typcally 'texttest -a <app> -s matador.ImportTest'. The action
                             will then find the new entries (as they have no corresponding subdirs) and
                             ask you for either new CARMUSR and CARMTMP (for new user) or new subplan
                             directory (for new tests). Also for new tests it is neccessary to have an
                             'APC_FILES' subdirectory created by Studio which is to be used as the
                             'template' for temporary subplandirs as created when the test is run.
                             The action will look for available subplandirectories under
                             CARMUSR and present them to you.
"""

import carmen, os, shutil, filecmp, optimization, string, plugins, comparetest

def getConfig(optionMap):
    return MatadorConfig(optionMap)

def getOption(options, optionVal):
    optparts = options.split()
    nextWanted = 0
    for option in optparts:
        if nextWanted:
            return option
        if option == optionVal:
            nextWanted = 1
        else:
            nextWanted = 0
    return None

class MatadorConfig(optimization.OptimizationConfig):
    def __init__(self, optionMap):
        optimization.OptimizationConfig.__init__(self, optionMap)
        if self.optionMap.has_key("diag"):
            os.environ["DIAGNOSTICS_IN"] = "./Diagnostics"
            os.environ["DIAGNOSTICS_OUT"] = "./Diagnostics"
        if os.environ.has_key("DIAGNOSTICS_IN"):
            print "Note: Running with Diagnostics on, so performance checking is disabled!"
    def __del__(self):
        if self.optionMap.has_key("diag"):
            del os.environ["DIAGNOSTICS_IN"]
            del os.environ["DIAGNOSTICS_OUT"]
    def getSwitches(self):
        switches = optimization.OptimizationConfig.getSwitches(self)
        switches["diag"] = "Use Matador Codebase diagnostics"
        return switches
    def checkPerformance(self):
        return not self.optionMap.has_key("diag")
    def getLibraryFile(self, test):
        return os.path.join("data", "crc", "MATADOR", carmen.getArchitecture(test.app), "matador.o")
    def _getSubPlanDirName(self, test):
        subPlan = self._subPlanName(test)
        fullPath = os.path.join(os.environ["CARMUSR"], "LOCAL_PLAN", subPlan)
        return os.path.normpath(fullPath)
    def _subPlanName(self, test):
        subPlan = getOption(test.options, "-s")            
        if subPlan == None:
            # print help information and exit:
            return ""
        return subPlan
    def getRuleSetName(self, test):
        outputFile = test.makeFileName("output")
        if os.path.isfile(outputFile):
            for line in open(outputFile).xreadlines():
                if line.find("Loading rule set") != -1:
                    finalWord = line.split(" ")[-1]
                    return finalWord.strip()
        return getOption(test.options, "-r")
    def printHelpDescription(self):
        print helpDescription
        optimization.OptimizationConfig.printHelpDescription(self)
    def printHelpOptions(self, builtInOptions):
        optimization.OptimizationConfig.printHelpOptions(self, builtInOptions)
        print helpOptions
    def printHelpScripts(self):
        optimization.OptimizationConfig.printHelpScripts(self)
        print helpScripts
    def setUpApplication(self, app):
        optimization.OptimizationConfig.setUpApplication(self, app)
        if os.environ.has_key("DIAGNOSTICS_IN"):
            app.addToConfigList("copy_test_path", "Diagnostics")
            app.addToConfigList("compare_extension", "diag")
        self.itemNamesInFile[optimization.memoryEntryName] = "Memory"
        self.itemNamesInFile[optimization.newSolutionMarker] = "Creating solution"
        self.itemNamesInFile[optimization.solutionName] = "Solution\."
        self.itemNamesInFile["unassigned slots"] = "slots \(unassigned\)"
        # Add here list of entries that should not increase, paired with the methods not to check
        self.noIncreaseExceptMethods[optimization.costEntryName] = [ "SolutionLegaliser", "initial" ]
        self.noIncreaseExceptMethods["crew with illegal rosters"] = []
        self.noIncreaseExceptMethods["broken hard trip constraints"] = [ "MaxRoster" ]
        self.noIncreaseExceptMethods["broken hard leg constraints"] = [ "MaxRoster" ]
        self.noIncreaseExceptMethods["broken hard global constraints"] = [ "MaxRoster" ]

class MatadorTestCaseInformation(optimization.TestCaseInformation):
    def isComplete(self):
        if not os.path.isdir(self.testPath()):
            return 0
        if not os.path.isfile(self.makeFileName("options")):
            return 0
        if not os.path.isfile(self.makeFileName("performance")):
            return 0
        return 1
    def makeImport(self):
        testPath = self.testPath()
        optionPath = self.makeFileName("options")
        perfPath = self.makeFileName("performance")
        outputPath = self.makeFileName("output")
        createdPath = 0
        if not os.path.isdir(testPath):
            os.mkdir(testPath)
            createdPath = 1
        if not os.path.isfile(optionPath):
            dirName = self.chooseSubPlan()
            if dirName == None:
                if createdPath == 1:
                    os.rmdir(testPath)
                return 0
            subPlanDir = os.path.join(dirName, "APC_FILES")
            ruleSet = self.getRuleSetName(subPlanDir)
            newOptions = "-s " + self.getOptionPart(dirName) + " -r " + ruleSet
            open(optionPath,"w").write(newOptions + os.linesep)

            logFile = os.path.join(subPlanDir, "matador.log")
            if not os.path.isfile(outputPath) and os.path.isfile(logFile):
                shutil.copyfile(logFile, outputPath)
        else:
            relPath = getOption(open(optionPath).readline().strip(), "-s")
            subPlanDir = os.path.join(os.environ["CARMUSR"], "LOCAL_PLAN", relPath, "APC_FILES")
        if not os.path.isfile(perfPath):
            perfContent = self.buildPerformance(subPlanDir)
            open(perfPath, "w").write(perfContent + os.linesep)
        return 1
    def getOptionPart(self, path):
        startPath = os.path.join(os.environ["CARMUSR"], "LOCAL_PLAN") + os.sep
        if path[0:len(startPath)] == startPath:
            return os.path.join(path[len(startPath) : len(path)])
        return os.path.normpath(path)
    def buildPerformance(self, subPlanDir):
        statusPath = os.path.join(subPlanDir, "status")
        if os.path.isfile(statusPath):
            lastLines = os.popen("tail -10 " + statusPath).xreadlines()
            for line in lastLines:
                if line.find("Total time:") == 0:
                    try:
                        timeparts = line.split(":")[-3:]
                        secs = int(timeparts[0]) * 60 * 60
                        secs += int(timeparts[1]) * 60
                        secs += int(timeparts[2])
                        return "CPU time   :     " + str(secs) + ".0 sec. on heathlands"
                    except:
                        pass
# Give some default that will not end it up in the short queue
        return "CPU time   :      2500.0 sec. on heathlands"

class MatadorTestSuiteInformation(optimization.TestSuiteInformation):
    def __init__(self, suite, name):
        optimization.TestSuiteInformation.__init__(self, suite, name)
        self.onlyEnvIsLacking = 0
    def isComplete(self):
        if not os.path.isdir(self.testPath()):
            return 0
        if not os.path.isfile(self.makeFileName("testsuite")):
            return 0
        self.onlyEnvIsLacking = 1
        if not os.path.isfile(self.makeFileName("environment")):
            return 0
        return 1
    def makeImport(self):
        if optimization.TestSuiteInformation.makeImport(self) == 0:
            return 0
        envPath = self.makeFileName("environment")
        stemEnvPath = self.filePath("environment")
        if envPath == stemEnvPath:
            return 1
        if not os.path.isfile(stemEnvPath):
            shutil.copyfile(envPath, stemEnvPath)
        if filecmp.cmp(envPath, stemEnvPath, 0) == 1:
            os.remove(envPath)
            if self.onlyEnvIsLacking == 1:
                return 0
        return 1
    
class ImportTest(optimization.ImportTest):
    def getTestCaseInformation(self, suite, name):
        return MatadorTestCaseInformation(suite, name)
    def getTestSuiteInformation(self, suite, name):
        return MatadorTestSuiteInformation(suite, name)
    def setUpSuite(self, suite):
        if suite.app.name == "cas":
            optimization.ImportTest.setUpSuite(self, suite)
        else:
            self.describe(suite, " failed: Can not import '" + suite.app.name + "' test suites!")

class PrintRuleValue(plugins.Action):
    def __repr__(self):
        return "Printing rule values for"
    def __call__(self, test):
        self.describe(test)
        rulesFile = os.path.join(os.environ["CARMUSR"], "LOCAL_PLAN", getOption(test.options, "-s"), "APC_FILES", "rules")
        for line in open(rulesFile).xreadlines():
            if line.find("index_group_generation TRUE") != -1:
                print test.getIndent() + "INDEX GROUPS"
    def setUpSuite(self, suite):
        self.describe(suite)

class CopyEnvironment(plugins.Action):
    def __repr__(self):
        return "Making environment.9 for"
    def setUpSuite(self, suite):
        targetFile = os.path.join(suite.abspath, "environment.9")
        if carmen.isUserSuite(suite) and os.path.isfile(targetFile):
            self.describe(suite)
            file = open(targetFile, "w")
            carmtmp = os.path.join("/carm/user_and_tmp/carmen_9.0_deliver/tmps_for_Matador_9", os.path.basename(os.path.normpath(os.environ["CARMTMP"])))
            print carmtmp
            file.write("CARMTMP:" + carmtmp + os.linesep)

