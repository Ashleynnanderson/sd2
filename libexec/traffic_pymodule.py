
import sys, os, inspect

# Allow interception of 'socket'
import socket as realsocket
del sys.modules["socket"]

class ModuleProxy:
    def __init__(self, name):
        self.name = name

    def __getattr__(self, attrname):
        return AttributeProxy(self.name, self, attrname).tryEvaluate()

    @staticmethod
    def createSocket():
        servAddr = os.getenv("TEXTTEST_MIM_SERVER")
        if servAddr:
            host, port = servAddr.split(":")
            serverAddress = (host, int(port))
            sock = realsocket.socket(realsocket.AF_INET, realsocket.SOCK_STREAM)
            sock.connect(serverAddress)
            return sock

    def handleResponse(self, response, cls):
        if response.startswith("raise "):
            rest = response.replace("raise ", "")
            raise self.handleResponse(rest, "ExceptionProxy")
        else:
            def Instance(className, instanceName):
                # Call separate function to avoid exec problems
                return self.makeInstance(className, instanceName, cls)
            def NewStyleInstance(className, instanceName):
                return self.makeInstance(className, instanceName, "NewStyleInstanceProxy")
            return self.evaluateResponse(response, cls, Instance, NewStyleInstance)

    def makeInstance(self, className, instanceName, baseClass):
        exec "class " + className + "(" + baseClass + "): pass"
        classObj = eval(className)
        setattr(self, className, classObj)
        return classObj(givenInstanceName=instanceName, moduleProxy=self)

    @staticmethod
    def evaluateResponse(response, cls, Instance, NewStyleInstance):
        try:
            return eval(response)
        except NameError: # standard exceptions end up here
            module = response.split(".", 1)[0]
            exec "import " + module
            return eval(response)



class FullModuleProxy(ModuleProxy):
    def __init__(self, name, importHandler):
        ModuleProxy.__init__(self, name)
        self.importHandler = importHandler
        self.realModule = None
        self.tryImport() # trigger a remote import to make sure we're connected to something
        
    def tryImport(self):
        sock = self.createSocket()
        text = "SUT_PYTHON_IMPORT:" + self.name
        sock.sendall(text)
        sock.shutdown(1)
        response = sock.makefile().read()
        if response:
            self.handleResponse(response, "InstanceProxy")

    def __getattr__(self, attrname):
        if self.importHandler.callStackChecker.callerExcluded():
            if self.realModule is None:
                self.realModule = self.importHandler.loadRealModule(self.name)
            return getattr(self.realModule, attrname)
        else:
            return ModuleProxy.__getattr__(self, attrname)
    

class InstanceProxy:
    moduleProxy = None
    def __init__(self, *args, **kw):
        self.name = kw.get("givenInstanceName")
        moduleProxy = kw.get("moduleProxy")
        if moduleProxy is not None:
            self.__class__.moduleProxy = moduleProxy
        if self.name is None:
            attrProxy = AttributeProxy(self.moduleProxy.name, self.moduleProxy, self.__class__.__name__)
            response = attrProxy.makeResponse(*args, **kw)
            def Instance(className, instanceName):
                return instanceName
            NewStyleInstance = Instance
            self.name = eval(response)

    def getRepresentationForSendToTrafficServer(self):
        return self.name

    def __getattr__(self, attrname):
        return AttributeProxy(self.name, self.moduleProxy, attrname).tryEvaluate()

    def __setattr__(self, attrname, value):
        self.__dict__[attrname] = value
        if attrname != "name":
            AttributeProxy(self.name, self.moduleProxy, attrname).setValue(value)

class NewStyleInstanceProxy(InstanceProxy, object):
    # Must intercept these as they are defined in "object"
    def __repr__(self):
        return self.__getattr__("__repr__")()

    def __str__(self):
        return self.__getattr__("__str__")()

class ExceptionProxy(InstanceProxy, Exception):
    def __str__(self):
        return self.__getattr__("__str__")()

    # Only used in Python >= 2.5 where Exception is a new-style class
    def __getattribute__(self, attrname):
        if attrname in [ "name", "moduleProxy", "__dict__", "__class__", "__getattr__" ]:
            return object.__getattribute__(self, attrname)
        else:
            return self.__getattr__(attrname)


class AttributeProxy:
    def __init__(self, modOrObjName, moduleProxy, attributeName, callStackChecker=None):
        self.modOrObjName = modOrObjName
        self.moduleProxy = moduleProxy
        self.attributeName = attributeName
        self.realVersion = None
        self.callStackChecker = callStackChecker
        
    def getRepresentationForSendToTrafficServer(self):
        return self.modOrObjName + "." + self.attributeName

    def tryEvaluate(self):
        sock = self.moduleProxy.createSocket()
        text = "SUT_PYTHON_ATTR:" + self.modOrObjName + ":SUT_SEP:" + self.attributeName
        sock.sendall(text)
        sock.shutdown(1)
        response = sock.makefile().read()
        if response:
            return self.moduleProxy.handleResponse(response, "InstanceProxy")
        else:
            return self

    def setValue(self, value):
        sock = self.moduleProxy.createSocket()
        text = "SUT_PYTHON_SETATTR:" + self.modOrObjName + ":SUT_SEP:" + self.attributeName + \
               ":SUT_SEP:" + repr(self.getArgForSend(value))
        sock.sendall(text)
        sock.shutdown(2)

    def __getattr__(self, name):
        return AttributeProxy(self.modOrObjName, self.moduleProxy, self.attributeName + "." + name).tryEvaluate()

    def __call__(self, *args, **kw):
        if self.realVersion is None or self.callStackChecker is None or not self.callStackChecker.callerExcluded(): 
            response = self.makeResponse(*args, **kw)
            if response:
                return self.moduleProxy.handleResponse(response, "InstanceProxy")
        else:
            return self.realVersion(*args, **kw)

    def makeResponse(self, *args, **kw):
        sock = self.createAndSend(*args, **kw)
        sock.shutdown(1)
        return sock.makefile().read()

    def createAndSend(self, *args, **kw):
        sock = self.moduleProxy.createSocket()
        text = "SUT_PYTHON_CALL:" + self.modOrObjName + ":SUT_SEP:" + self.attributeName + \
               ":SUT_SEP:" + repr(self.getArgsForSend(args)) + ":SUT_SEP:" + repr(self.getArgForSend(kw))
        sock.sendall(text)
        return sock

    def getArgForSend(self, arg):
        class ArgWrapper:
            def __init__(self, arg, moduleProxy):
                self.arg = arg
                self.moduleProxy = moduleProxy
            def __repr__(self):
                if hasattr(self.arg, "getRepresentationForSendToTrafficServer"):
                    # We choose a long and obscure name to avoid accident clashes with something else
                    return self.arg.getRepresentationForSendToTrafficServer()
                elif isinstance(self.arg, list):
                    return repr([ ArgWrapper(subarg, self.moduleProxy) for subarg in self.arg ])
                elif isinstance(self.arg, dict):
                    newDict = {}
                    for key, val in self.arg.items():
                        newDict[key] = ArgWrapper(val, self.moduleProxy)
                    return repr(newDict)
                else:
                    return repr(self.arg)
        return ArgWrapper(arg, self.moduleProxy)

    def getArgsForSend(self, args):
        return tuple(map(self.getArgForSend, args))


class CallStackChecker:
    def __init__(self, ignoreModuleCalls):
        # Always ignore our own command line interceptors
        self.ignoreModuleCalls = [ "traffic_intercepts" ] + ignoreModuleCalls

    def callerExcluded(self):
        # Don't intercept if we've been called from within the standard library
        stdlibDir = os.path.dirname(os.__file__)
        framerecord = inspect.stack()[2] # parent of parent. If you extract method you need to change this number :)
        fileName = framerecord[1]
        dirName = self.getDirectory(fileName)
        moduleName = self.getModuleName(fileName)
        return dirName == stdlibDir or os.path.basename(dirName) in self.ignoreModuleCalls or \
               moduleName in self.ignoreModuleCalls

    def getModuleName(self, fileName):
        given = inspect.getmodulename(fileName)
        if given == "__init__":
            return os.path.basename(os.path.dirname(fileName))
        else:
            return given

    def getDirectory(self, fileName):
        dirName, local = os.path.split(fileName)
        if local.startswith("__init__"):
            return self.getDirectory(dirName)
        else:
            return dirName



class ImportHandler:
    def __init__(self, moduleNames, callStackChecker):
        self.moduleNames = moduleNames
        self.callStackChecker = callStackChecker

    def shouldIntercept(self, name):
        if name in self.moduleNames:
            return True
        elif "." in name:
            for modName in self.moduleNames:
                if name.startswith(modName + "."):
                    return True
        return False
        
    def find_module(self, name, *args):
        if self.shouldIntercept(name):
            return self

    def load_module(self, name):
        if self.callStackChecker.callerExcluded():
            # return the real module, but don't put it in sys.modules so we trigger
            # a new import next time around
            return self.loadRealModule(name)
        else:
            return sys.modules.setdefault(name, FullModuleProxy(name, self))

    def loadRealModule(self, name):
        currentModule = sys.modules.get(name)
        if currentModule is not None:
            del sys.modules[name]
        sys.meta_path.remove(self)
        try:
            exec "import " + name + " as _realModule"
        finally:
            sys.meta_path.append(self)
            if currentModule is not None:
                sys.modules[name] = currentModule
            else:
                del sys.modules[name]
        return _realModule



def interceptPython(attributeNames, ignoreCallers):
    handler = InterceptHandler(attributeNames)
    handler.makeIntercepts(ignoreCallers)

class InterceptHandler:
    def __init__(self, attributeNames):
        self.fullIntercepts = []
        self.partialIntercepts = {}
        for attrName in attributeNames:
            if "." in attrName:
                moduleName, subAttrName = self.splitByModule(attrName)
                if moduleName:
                    if subAttrName:
                        self.partialIntercepts.setdefault(moduleName, []).append(subAttrName)
                    else:
                        del sys.modules[attrName] # We imported the real version, get rid of it again...
                        self.fullIntercepts.append(attrName)
            else:
                self.fullIntercepts.append(attrName)

    def makeIntercepts(self, ignoreCallers):
        callStackChecker = CallStackChecker(ignoreCallers)
        if len(self.fullIntercepts):
            sys.meta_path.append(ImportHandler(self.fullIntercepts, callStackChecker))
        for moduleName, attributes in self.partialIntercepts.items():
            proxy = PartialModuleProxy(moduleName)
            proxy.interceptAttributes(attributes, callStackChecker)

    def splitByModule(self, attrName):
        if self.canImport(attrName):
            return attrName, ""
        elif "." in attrName:
            parentName, localName = attrName.rsplit(".", 1)
            parentModule, parentAttr = self.splitByModule(parentName)
            if parentAttr:
                localName = parentAttr + "." + localName
            return parentModule, localName
        else:
            return "", "" # Cannot import any parent, so don't do anything

    def canImport(self, moduleName):
        try:
            exec "import " + moduleName
            return True
        except ImportError:
            return False
    

# Workaround for stuff where we can't do setattr
class TransparentProxy:
    def __init__(self, obj):
        self.obj = obj
        
    def __getattr__(self, name):
        return getattr(self.obj, name)


class PartialModuleProxy(ModuleProxy):
    def interceptAttributes(self, attrNames, callStackChecker):
        for attrName in attrNames:
            attrProxy = AttributeProxy(self.name, self, attrName, callStackChecker)
            self.interceptAttribute(attrProxy, sys.modules.get(self.name), attrName)
            
    def interceptAttribute(self, proxyObj, realObj, attrName):
        parts = attrName.split(".", 1)
        currAttrName = parts[0]
        if not hasattr(realObj, currAttrName):
            return # If the real object doesn't have it, assume the fake one doesn't either...

        currRealAttr = getattr(realObj, currAttrName)
        if len(parts) == 1:
            proxyObj.realVersion = currRealAttr
            setattr(realObj, currAttrName, proxyObj.tryEvaluate())
        else:
            try:
                self.interceptAttribute(proxyObj, currRealAttr, parts[1])
            except TypeError: # it's a builtin (assume setattr threw), so we hack around...
                realAttrProxy = TransparentProxy(currRealAttr)
                self.interceptAttribute(proxyObj, realAttrProxy, parts[1])
                setattr(realObj, currAttrName, realAttrProxy)

