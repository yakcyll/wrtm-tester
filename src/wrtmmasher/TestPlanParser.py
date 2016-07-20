from configparser import SafeConfigParser


class TestPlanParser(object):
    
    """WRTM Test Plan Parser
    
       Accepts INI style files describing tests in separate sections, with each test 
       described in a separate line of a 'plan' option of a section. Each such line 
       has a format of:

           test-id interface-identifier test-length address/offset mask

       Address/offset can either be an immediate value or a difference from the last
       returned value (in the form of +x or -x).

       Additionally the 'main' section specifies the address of the device under test 
       ('dut') and the address of the N2X probe ('n2x'). Comments are allowed in separate 
       lines starting with a # (hashtag) or a ; (semicolon).
    """

    def __init__(self):
        self.parser = SafeConfigParser()
        self.loaded = False
        self.loadedPath = None
        self.testTypes = {}

    def load(self, path):
        if len(self.parser.read(path)) <= 1:
            raise RuntimeError("Unable to load the specified file.")
        self.loaded = True
        self.loadedPath = path

    def loadTestTypes(self, fileName):
        testsFile = open(fileName)
        for testType in testsFile:
            splitarray = testType.split(' ')
            testId = int(splitarray[0])
            testContinuous = int(splitarray[1])
            testDescription = ' '.join(splitarray[2:])
            self.testTypes[testId] = (testContinuous, testDescription)

    def getListOfTests(self):
        if self.loaded:
            return self.parser.sections()
        return None

    def getTestGenerator(self, name=None):
        if self.parser.has_option(name, 'loop'):
            loops = self.parser.getint(name, 'loop')
        else:
            loops = 1

        tests = self.parser[name]['plan'].split('\n')[1:]
        offset = 0

        for it in range(0, loops):
            for i in range(0, len(tests)):
                testTuple = tests[i].split(' ')
                if testTuple[3][0] == '+' or testTuple[3][0] == '-':
                    offset += int(testTuple[3][0])
                else:
                    offset = int(testTuple[3][0])
                
                testTuple[3] = offset

                yield self.parseTestLine(i+1, testTuple)
    
        return None
    
    def parseTestLine(self, testIter, testTuple):
        testSplit = testTuple.split(' ')
        return [testIter,
                int(testSplit[0]),  # testId 
                testSplit[1],       # interfaceName
                int(testSplit[2]),  # testDuration
                int(testSplit[3]),  # address/offset
                int(testSplit[4])]  # mask
