import os
from configparser import SafeConfigParser


class TestPlanParser(object):

    def __init__(self):
        super(TestPlanParser, self).__init__()
        self.parser = SafeConfigParser()
        self.loaded = False
        self.loadedPath = None

    def load(self, path):
        if len(self.parser.read(path)) <= 1:
            raise RuntimeError("Unable to load the specified file.")
        self.loaded = True
        self.loadedPath = path

    def getListOfTests(self):
        if self.loaded:
            return self.parser.sections()
        return None
        
    def getTestPlan(self, name):
        if self.loaded:
            return self.parser[name]['plan']
        return None
        
    def getTestLoops(self, name):
        if self.loaded:
            return self.parser[name]['loops']
        return None
