import argparse
import os
import select
import socket
import struct
import sys
import time

from wrtmtester import SerialReader
from wrtmtester import TestPlanParser
from wrtmtester import WrtmN2xWrapper
from wrtmtester.ping import ping_one


class WrtmTestError(RuntimeError):
    pass


class WrtmTimeoutError(RuntimeError):
    pass


class WrtmRebootError(RuntimeError):
    pass


def implode(thesis):
    sys.exit(1)


class WrtmTester(object):

    """WRTM Tester
    
       Main wrapper class used to initialize the testing environment, load and parse testing
       definitions and execute them on a remote system with WRTM modules.
    """

    ARGPARSE_DESCRIPTION = "WRTM Tester 0.13.37"

    INIT_PORT = 4094 
    TEST_PORT = 7999

    INIT_MAGIC = 0xFEE17357
    INIT_TIMEOUT = 120
    RCV_TIMEOUT = 10

    ERR_OK = 0
    ERR_RCV_TIMEOUT = 4

    def __init__(self):
        self.testParser = TestPlanParser()
        self.n2x = WrtmN2xWrapper()
        self.serial = SerialReader()

        self.routerSocket = None
        self.routerIp = None

    def executePlan(self, testName, verboseLog):
        self.routerIp = self.testParser.parser['main']['routerIp']
        testStartTime = 0
        testStopTime = 0
        testRunning = False
        timeStr = time.strftime("%d-%m-%Y_%H-%M-%S", time.gmtime())

        # init serial reader
        if self.testParser.parser.has_option('main', 'tty'):
            tty = self.testParser.parser['main']['tty']
        else:
            tty = '/dev/ttyAMA0'

        self.serial.init(tty, "wrt54gl-log-" + testName + "-" + timeStr + ".log")
        self.serial.setVerbose(verboseLog)

        # init router socket
        self.routerSocket = socket.socket(type=socket.SOCK_DGRAM, proto=socket.IPPROTO_UDP)
        self.routerSocket.bind(('', WrtmTester.TEST_PORT))

        # init init socket
        initSocket = socket.socket(type=socket.SOCK_DGRAM, proto=socket.IPPROTO_UDP)
        initSocket.bind(('', WrtmTester.INIT_PORT))

        # open result file
        resultsFile = open("results_" + timeStr + ".txt", "a+")

        # loop over tests:
        for test in self.testParser.getTestGenerator(testName):
            retCount = 0

            try:
                while True:
                    print("\r\tExecuting test #" + str(test[0]) + " (" + time.strftime("%H:%M:%S", time.gmtime()) + ")")
                    try:
                        # ping router
                        try:
                            ping_one(self.routerIp)
                        except socket.error:
                            self.shutdownN2X()
                            raise WrtmTestError("Router under test did not respond to the "
                                                + "initial ping request. Abandoning ship.")

                        # start load streams/send test definition (order depends on delay)
                        # receive acknowledgement
                        delay = int(self.testParser.parser[testName]['loadDelay'])
                        if delay < 0:
                            self.n2x._startLoadStreams()
                            time.sleep(-delay)
                            self._sendTest(test)
                            testRunning = True
                        else:
                            self._sendTest(test)
                            testRunning = True
                            time.sleep(delay)
                            self.n2x._startLoadStreams()

                        break

                    except WrtmTimeoutError:
                        retCount += 1
                        if retCount == 3:
                            raise WrtmTimeoutError("Test #" + str(test[0]) + " skipped "
                                                   + "due to excessive number of init retries.")
                        print("\r\tLink with the router timed out. Retrying...")

                testStartTime = time.time()

                # keep pinging for the duration of the test
                # if no response: fail the test

                for pingCount in range(0, test[3]):
                    time.sleep(1)
                    try:
                        ping_one(self.routerIp)
                    except socket.error:
                        self.shutdownN2X()
                        raise WrtmTimeoutError("Router under test did not respond to a ping request "
                                               + "during test #" + str(test[0]))

                testStopTime = time.time()
                testRunning = False

                # after pinging: send stop-test, wait for ack; if no response, fail the test
                self._sendTest(test, stop=True)

                # post-test:
                # stop load streams
                self.n2x._stopLoadStreams()

                # if test passed (no matter the result), save the result
                result = self._formResultString(test, WrtmTester.ERR_OK, 
                                               testStopTime - testStartTime, retCount)
                resultsFile.write(result + "\n")

                print("\r\tTest done. Waiting for the router to announce its readiness.")
                # check if the router is ready (by waiting for broadcast on router socket)
                # if it won't broadcast within 120 seconds, reboot through UPS
                # in case it doesn't broadcast after two reboots, cancel the test suite altogether
                rebootCounter = 0

                while rebootCounter < 3:
                    try:
                        timeoutCounter = 0
                        while(timeoutCounter < WrtmTester.INIT_TIMEOUT):
                            rsock, _, _ = select.select([initSocket], [], [], 1)
                            if rsock != []:
                                data, addr = rsock[0].recvfrom(4096)
                                if addr[0] != self.routerIp:
                                    continue
                                magic = struct.unpack("<II", data[2:10])
                                if magic[1] == 0xFFFFFFFF and \
                                   magic[0] == WrtmTester.INIT_MAGIC:
                                    if test[0] < self.testParser.getNumberOfTestCases(testName):
                                        print("\r\tResuming testing in 5 seconds...")
                                        time.sleep(5)
                                    break
                            timeoutCounter += 1
                        
                        if timeoutCounter == WrtmTester.INIT_TIMEOUT:
                            raise WrtmRebootError("Router did not initiate after " + 
                                                  str(WrtmTester.INIT_TIMEOUT) + " seconds, " + 
                                                  "preparing for a power cycle.")

                        break

                    except WrtmRebootError as re:
                        rebootCounter += 1
                        if rebootCounter == 3:
                            break

                        print("\r\t" + str(re))
                        os.system('upscmd -u admin -p asdf everwrt load.off')
                        print("\r\t** System powered down. Restoring power in 10...")
                        time.sleep(10)
                        os.system('upscmd -u admin -p asdf everwrt load.on')
                        continue

                if rebootCounter == 3:
                   raise WrtmTestError("Router did not initiate after three tries, " +
                                       "aborting testing.") 
        
                # flush init socket
                initSocket.close()
                initSocket = socket.socket(type=socket.SOCK_DGRAM, proto=socket.IPPROTO_UDP)
                initSocket.bind(('', WrtmTester.INIT_PORT))

            except WrtmTestError as te:
                print("\r\t" + str(te))
                self.serial.close()
                self.routerSocket.close()
                initSocket.close()
                return

            except WrtmTimeoutError as tme:
                # if test timed out on pings/second send-ack or test init, report failure and go next
                if testRunning:
                    testTime = testStopTime - testStartTime
                else:
                    testTime = 0
                
                print("\r\t" + str(tme))
                result = self._formResultString(test, WrtmTester.ERR_RCV_TIMEOUT, testTime, retCount) \
                         + " [" + str(tme) + "]"
                resultsFile.write(result + "\n")
                continue

        # testing done!
        print("\rTest suite done!")

        # close the serial reader and the result file
        self.serial.close()
        resultsFile.close()

        # close router socket
        initSocket.close()
        self.routerSocket.close()

    def _prepareTestPacket(self, test, stop=False):
        if stop:
            stop = 1
        else:
            stop = 0
        outPack = struct.pack("<IIILII128sII",
                              test[0],
                              test[0],
                              test[1],
                              136,
                              test[3],
                              stop,
                              bytes(test[2], 'utf-8') + bytes('\0', 'utf-8') * (128 - len(test[2])),
                              test[4],
                              test[5])
        return outPack

    def _sendTest(self, test, stop=False):
        timeDiff = 0

        outPack = self._prepareTestPacket(test, stop)
        self.routerSocket.sendto(outPack, (self.routerIp, WrtmTester.TEST_PORT))

        while timeDiff < WrtmTester.RCV_TIMEOUT:
            startTime = time.time()
            read,_,_ = select.select([self.routerSocket], [], [], WrtmTester.RCV_TIMEOUT - timeDiff)
            stopTime = time.time()
            #print("[:debug] timediff " + str(timeDiff))
            timeDiff += stopTime - startTime
            if read == []:
                raise WrtmTimeoutError()
            ackData = self.routerSocket.recv(10)
            #print("[:debug] ackData " + ":".join("{:02x}".format(c) for c in ackData))
            ackPack = struct.unpack("<2xiL", ackData)

            # code i dont understand
            if ackPack[1] == 0:
                if ackPack[0] != test[1]:
                    raise WrtmTestError("Got an ack for a wrong test?? " + str(test))
                return
            else:
                if ackPack[1] == 2:
                    continue
                elif ackPack[1] == 1:
                    raise WrtmTestError("Specified test type (" + str(test[1]) + ") "
                                        + "was not identified on RUT!")
                raise WrtmTestError("Received a NACK for test #" + str(test[0]) + " from RUT!")

    def _formResultString(self, test, errCode, testTime, retCount):
        timeStr = time.strftime("%d-%m-%Y %H-%M-%S", time.gmtime())
        result = "#" + str(test[0]) + " (" + timeStr \
                 + ") ret: " + str(errCode) \
                 + " id: " + str(test[1]) \
                 + " if: " + test[2] \
                 + " (o,m/c): (" + str(test[4]) + "," + str(test[5]) \
                 + ") time:  " + str(testTime) \
                 + "s rtr: " + str(retCount)
        return result
        
    def main(self, argv):
        # remove argv0
        argv = argv[1:]

        # parse args: filename and flags (--noload disables n2x)
        parser = argparse.ArgumentParser(description=WrtmTester.ARGPARSE_DESCRIPTION)
        parser.add_argument('filePath', type=str,
                            help='path to the test description file')
        parser.add_argument('-n', '--noload', action='store_true',
                            help='disable automatic N2X initialization',
                            required=False, default=False)
        parser.add_argument('-v', '--verboseLog', action='store_true',
                            help='print the serial output directly to console',
                            required=False, default=False)
        args = parser.parse_args(argv)

        # check if run with sudo (required for ping)
        try:
            pingSocket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        except socket.error as e:
            if e.errno == 1 or e.errno == 10013:
                raise socket.error('\n'.join((e.args[1],
                                           "WRTM Tester utilizes a raw ICMP socket to send "
                                           + "echo request (ping) packets and because of that, it "
                                           + "requires admin privileges (a.k.a. try sudo).")))
            raise

        # init test types?
        self.testParser.loadTestTypes('tests.txt')

        # load tests
        self.testParser.load(args.filePath)

        # init n2x
        if not args.noload:
            self.n2x.initN2X()

        # execute plan
        for testPlan in [x for x in self.testParser.sections() if x != 'main']:
            print("Starting test suite '" + testPlan + "'"
                  + " at " + time.strftime("%d-%m-%Y %H:%M:%S", time.gmtime()))
            self.executePlan(testPlan, args.verboseLog)
            print("***\n")

        # shutdown n2x
        if not args.noload:
            self.n2x.shutdownN2X()
