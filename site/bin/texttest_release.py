#!/usr/bin/env python

# texttest_release.py

# Extracts the code and tests from Jeppesen's source control into a zip file
# and removes everything that is Jeppesen-specific
# Not useful outside Jeppesen currently

# Usage texttest_release.py [ -v <release_name> ] [ -x ] [ -d <working_dir> ]

# <working_dir> indicates where temporary files are written and the final zip file will end up.
# It defaults to the current working directory.

# <release_name> defaults to "current" and should be overridden when making external releases

# The -x flag should be provided if the temporary files are to be left. Mostly useful for testing.

import os, sys, shutil
from glob import glob
from getopt import getopt

def exportDir(dirName, targetName, dest):
    destDir = os.path.join(dest, targetName)
    cmdLine = "bzr checkout --lightweight " + os.path.join(os.getenv("BZRROOT"), dirName, "branches/HEAD") + " " + destDir
    print cmdLine
    os.system(cmdLine)
    shutil.rmtree(os.path.join(destDir, ".bzr"))

def exportFromBzr(dest):
    exportDir("TextTest/source", "source", dest)
    os.mkdir(os.path.join(dest, "tests"))
    exportDir("TextTest/tests", "tests/texttest", dest)
    exportDir("PyUseCase/source", "PyUseCase", dest)
        
def createTests(testDir):
    fullName = os.path.join(testDir, "site")
    print "Removing", fullName
    shutil.rmtree(fullName)

def mergePyUseCase(reldir):    
    for fileName in glob(os.path.join(reldir, "PyUseCase/*.py")):
        print "Copying", fileName
        targetPath = fileName.replace("PyUseCase", "source/lib")
        shutil.copy(fileName, targetPath)
    shutil.rmtree(os.path.join(reldir, "PyUseCase"))

def createSource(reldir):
    mergePyUseCase(reldir)
    shutil.rmtree(os.path.join(reldir, "source", "site"))
    versionFile = os.path.join(reldir, "source", "lib", "texttest_version.py")
    updateVersionFile(versionFile, releaseName)
    os.rename(os.path.join(reldir, "source", "readme.txt"), os.path.join(reldir, "readme.txt"))
    
def updateVersionFile(versionFile, releaseName):
    newFileName = versionFile + ".new"
    newFile = open(newFileName, "w")
    for line in open(versionFile).xreadlines():
        newFile.write(line.replace("master", releaseName))
    newFile.close()
    os.rename(newFileName, versionFile)

def getCommandLine():
    options, leftovers = getopt(sys.argv[1:], "d:v:x")
    optDict = dict(options)
    return optDict.get("-d", os.getcwd()), optDict.get("-v", "current"), optDict.has_key("-x")
    
if __name__ == "__main__":
    rootDir, releaseName, leaveDir = getCommandLine()
    reldir = "texttest-" + releaseName
    actualRoot = os.path.join(rootDir, reldir)
    if os.path.isdir(actualRoot):
        shutil.rmtree(actualRoot)
    os.makedirs(actualRoot)
    
    exportFromBzr(actualRoot)
    createSource(actualRoot)
    createTests(os.path.join(actualRoot, "tests", "texttest"))
    
    os.chdir(rootDir)
    zipName = reldir + ".zip"
    if os.path.isfile(zipName):
        os.remove(zipName)
    print "Creating zip file", zipName
    os.system("zip -r " + zipName + " " + reldir)
    if not leaveDir:
        shutil.rmtree(reldir)