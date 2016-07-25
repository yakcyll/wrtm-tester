import argparse
import os
import select
import socket
import struct
import sys
import time

from wrtmtester import N2xInterface
from wrtmtester import TestPlanParser
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
        self.n2x = N2xInterface()

        self.n2x.inited = False
        self.routerSocket = None
        self.routerIp = None

    def initN2X(self):
        print('Waiting for n2x proxy to connect...')
        self.n2x.reverseProxy()

        print('Establishing an N2X session...')
        self.n2x.openSession("RouterTester900")
        try:
            self.n2x.addPortsToSession(['101/1', '101/2', '101/3', '101/4'])
        except:
            print("Enabling probe ports failed. Check the probe's status.")
            self.n2x.closeSession()
            raise
        self.n2x.setSessionLabel("WRTMasher probing stream session")

        for port in self.n2x.ports:
            self.n2x.setSutIpAddress(port, "192.168." + port + ".1")
            self.n2x.setTesterIpAddress(port, "192.168." + port + ".2", "24")

        for port in self.n2x.ports[:2]:
            self.n2x.addProfile(port, "AGT_CONSTANT_PROFILE")

        for profiles in self.n2x.profiles:
            self.n2x.setProfileMode(profile, "AgtConstantProfile", 
                                    "AGT_TRAFFIC_PROFILE_MODE_CONTINUOUS")
            self.n2x.setProfielAverageLoad(profile, "AgtConstantProfile",
                                           "1 AGT_UNITS_MBITS_PER_SEC")
            self.n2x.addStreamGroupToProfile(profile)

        self.n2x.setExpectedDestinations(self.n2x.streamGroups[0], self.n2x.ports[2])
        self.n2x.setExpectedDestinations(self.n2x.streamGroups[1], self.n2x.ports[3])

        for streamGroup in self.n2x.streamGroups[:2]:
            self.n2x.setPduHeaders(streamGroup, ['ethernet', 'ipv4', 'tcp'])

        self.n2x.setIpv4SourceAddress(self.n2x.PDUs[0], "192.168.1.2")
        self.n2x.setIpv4SourceAddress(self.n2x.PDUs[1], "192.168.2.2")
        self.n2x.setIpv4DestinationAddress(self.n2x.PDUs[0], "192.168.3.2")
        self.n2x.setIpv4DestinationAddress(self.n2x.PDUs[1], "192.168.4.2")
        self.n2x.setTcpSourcePort(self.n2x.PDUs[0], 6478)
        self.n2x.setTcpSourcePort(self.n2x.PDUs[1], 6478)
        self.n2x.setTcpDestinationPort(self.n2x.PDUs[0], 6479)
        self.n2x.setTcpDestinationPort(self.n2x.PDUs[1], 6479)

        self.n2x.setPayloadFill(self.n2x.PDUs[0], "AGT_PAYLOAD_FILL_TYPE_REPEATING", "0xA5A53C3C")
        self.n2x.setPayloadFill(self.n2x.PDUs[1], "AGT_PAYLOAD_FILL_TYPE_REPEATING", "0x96965A5A")

        setCapturePorts([self.n2x.ports[2], self.n2x.ports[3]])

        for port in self.n2x.ports[2:]:
            self.n2x.clearFiltersOnPort(port)
            self.n2x.createFrameMatcher(port)
            self.n2x.createFrameMatcher(port)

        self.n2x.addMatcherFrameFlags(self.n2x.frameMatchers[0], 
                                      "AGT_FRAME_FLAG_IPV4_HEADER_CHECKSUM_ERROR")
        self.n2x.addMatcherFrameFlags(self.n2x.frameMatchers[1], 
                                      "AGT_FRAME_FLAG_ANY_L2_ERROR")
        self.n2x.addMatcherFrameFlags(self.n2x.frameMatchers[2], 
                                      "AGT_FRAME_FLAG_IPV4_HEADER_CHECKSUM_ERROR")
        self.n2x.addMatcherFrameFlags(self.n2x.frameMatchers[3], 
                                      "AGT_FRAME_FLAG_ANY_L2_ERROR")

        self.n2x.addMatcherFilter(self.n2x.ports[2], self.n2x.frameMatchers[0], 
                                  "AGT_FILTER_ACTION_STORE_PACKET")
        self.n2x.addMatcherFilter(self.n2x.ports[2], self.n2x.frameMatchers[1], 
                                  "AGT_FILTER_ACTION_STORE_PACKET")
        self.n2x.addMatcherFilter(self.n2x.ports[3], self.n2x.frameMatchers[2], 
                                  "AGT_FILTER_ACTION_STORE_PACKET")
        self.n2x.addMatcherFilter(self.n2x.ports[3], self.n2x.frameMatchers[3], 
                                  "AGT_FILTER_ACTION_STORE_PACKET")

        self.n2x.setCaptureMode("AGT_CAPTURE_CYCLIC")

        self.n2x.createStatHandler()
        self.n2x.createStatHandler()

        self.n2x.selectStats(self.n2x.stats[0], "AGT_PACKET_INTEGRITY_ERROR")
        self.n2x.selectStats(self.n2x.stats[1], "AGT_PACKET_INTEGRITY_ERROR")

        self.n2x.selectStatStreamGroup(self.n2x.stats[0], self.n2x.streamGroups[0])
        self.n2x.selectStatStreamGroup(self.n2x.stats[1], self.n2x.streamGroups[1])

        self.n2x.setErroredFrameFilter(self.n2x.ports[2], 
                                       "AGT_STATISTICS_FILTER_INCLUDE_ALL_FRAMES")
        self.n2x.setErroredFrameFilter(self.n2x.ports[3], 
                                       "AGT_STATISTICS_FILTER_INCLUDE_ALL_FRAMES")

        self.n2x.inited = True

    def _startLoadStreams(self):
        if self.n2x.inited:
            self.n2x.startCapture()
            self.n2x.startTest()

    def _stopLoadStreams(self):
        if self.n2x.inited:
            self.n2x.stopTest()
            self.n2x.stopCapture()

    def collectLoadStats(self):
        pass

    def shutdownN2X(self):
        if self.n2x.inited:
            self.n2x.closeSession()
            self.n2x.disconnectFromProxy()

    def executePlan(self, testName):
        self.routerIp = self.testParser.parser['main']['routerIp']
        testStartTime = 0
        testStopTime = 0
        testRunning = False
        timeStr = time.strftime("%d-%m-%Y_%H-%M-%S", time.gmtime())

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

            if retCount >= 3:
                # if retry counter too high, skip test
                continue

            try:
                while True:
                    print("\tExecuting test #" + str(test[0]) + " (" + time.strftime("%H:%M:%S", time.gmtime()) + ")")
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
                            self._startLoadStreams()
                            time.sleep(-delay)
                            self._sendTest(test)
                            testRunning = True
                        else:
                            self._sendTest(test)
                            testRunning = True
                            time.sleep(delay)
                            self._startLoadStreams()

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
                self._stopLoadStreams()

                # if test passed (no matter the result), save the result
                result = self._formResultString(test, WrtmTester.ERR_OK, 
                                               testStopTime - testStartTime, retCount)
                resultsFile.write(result + "\n")

                print("\tTest done. Waiting for the router to announce its readiness.")
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
                                        print("\tResuming testing in 5 seconds...")
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

                        print("\t" + str(re))
                        # reboot here
                        continue

                if rebootCounter == 3:
                   raise WrtmTestError("Router did not initiate after three tries, " +
                                       "aborting testing.") 
        
                # flush init socket
                initSocket.close()
                initSocket = socket.socket(type=socket.SOCK_DGRAM, proto=socket.IPPROTO_UDP)
                initSocket.bind(('', WrtmTester.INIT_PORT))

            except WrtmTestError as te:
                print("\t" + str(te))
                self.routerSocket.close()
                initSocket.close()
                return

            except WrtmTimeoutError as tme:
                # if test timed out on pings/second send-ack or test init, report failure and go next
                if testRunning:
                    testTime = testStopTime - testStartTime
                else:
                    testTime = 0
                
                print("\t" + str(tme))
                result = self._formResultString(test, WrtmTester.ERR_RCV_TIMEOUT, testTime, retCount) \
                         + " [" + str(tme) + "]"
                resultsFile.write(result + "\n")
                continue

        # testing done!
        print("Test suite done!")

        # pkill minicom to close log file and close the result file
        #os.system("pkill minicom")
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
        parser.add_argument('--noload', action='store_true',
                            help='disable automatic N2X initialization',
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
            self.initN2X()

        # execute plan
        for testPlan in [x for x in self.testParser.sections() if x != 'main']:
            print("Starting test suite '" + testPlan + "'"
                  + " at " + time.strftime("%d-%m-%Y %H:%M:%S", time.gmtime()))
            self.executePlan(testPlan)
            print("***\n")

        # shutdown n2x
        if not args.noload:
            self.shutdownN2X()
