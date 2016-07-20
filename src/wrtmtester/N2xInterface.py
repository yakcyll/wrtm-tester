from socket import socket, SHUT_RDWR


def listFromReponse(response):
    return output[output.find("{")+1:output.rfind("}")].split(' ')

class N2xInterface(object):

    """WRTM N2X Interface Class

       Wrapper around the N2X connection, used to setup a testing session, configure
       statistics collection, activating and deactivating traffic generation and
       managing the proxy socket.
    """

    def __init__(self, address='0.0.0.0', port=9001):
        self.sessionId = -1
        self.ports = []
        self.profiles = []
        self.streamGroups = []
        self.PDUs = []
        self.frameMatchers = []
        self.stats = []

        self.readBuffer = ""

        self.proxyAddress = address
        self.proxyPort = port
        self.proxySocket = None

    def reverseProxy(self):
        serverSocket = socket.socket()
        serverSocket.bind("0.0.0.0:" + str(self.smPort))
        serverSocket.listen(1)
        self.proxySocket, self.proxyAddress = self.socket.accept()
        serverSocket.shutdown(socket.SHUT_RDWR)
        serverSocket.close()

    def connectToProxy(self):
        raise NotImplementedError()

    def disconnectFromProxy(self):
        self.proxySocket.shutdown(socket.SHUT_RDWR)
        self.proxySocket.close()

    def connectToSession(self, sessionId=None):
        output = self.smInvoke("AgtSessionManager", "ListOpenSessions")
        sessionList = map(int, listFromResponse(output))
        if sessionId is None or sessionId not in sessionList:
            sessionId = None
            for sId in sessionList:
                sessionLabel = self.getSessionLabel(sId)
                if sessionLabel != "SYSTEM":
                    sessionId = sId
                    break

        if sessionId is not None:
            sessionPort = self.getSessionPort(sessionId)
            self._writeWrapper(self.proxySocket, "connect " + str(sessionPort))
            result, output = self._readWrapper(self.proxySocket)
            if result != 0:
               raise RuntimeError("errorneous response in connectToSession: (" 
                                  + str(result) + ") " + output)

            self.sessionId = sesionId

    def disconnectFromSession(self):
        if self.sessionId < 1:
            return
        
        self._writeWrapper(self.proxySocket, "disconnect")
        result, output = self._readWrapper(self.proxySocket)
        if result != 0:
            raise RuntimeError("errorneous response in disconnectFromSession: (" 
                               + str(result) + ") " + output)

        self.sessionId = -1

    def smInvoke(self, interfaceName, methodName, args=""):
        return self.invoke("sm " + interfaceName, methodName, args)
        
    def invoke(self, interfaceName, methodName, args=""):
        data = "invoke " + interfaceName + " " + methodName + " " + str(args);

        self._writeWrapper(data, self.proxySsocket)
        result, output = self._readWrapper(self.proxySocket)

        if result != 0:
            raise RuntimeError('Error: "' + output + '" while executing command: ' + data)

        return output
        
    def _writeWrapper(self, socket, data):
        try:
            socket.sendall(data)

        except OSError:
            self.shutdown()
            raise

    def _readWrapper(self, socket):
        try:
            while "\r\n" not in self.readBuffer:
                self.readBuffer += str(socket.recv(4096))

            parts = self.readBuffer.partition("\r\n")
            self.readBuffer = parts[2]
            
            result = int(parts[0].partition(' ')[0])
            output = parts[0].partition(' ')[2]

            return result, output

        except OSError:
            self.shutdown()
            raise

    # N2X API session management wrappers
    def openSession(self, sessionType, sessionMode="AGT_SESSION_ONLINE"):
        args = sessionType + " " + sessionMode
        sessionId = int(self.smInvoke("AgtSessionManager", "OpenSession", args))
        self.connectToSession(sessionId)

    def closeSession(self):
        sessionId = self.sessionId
        if self.sessionId < 1:
            return

        self.disconnectFromSession()
        self.smInvoke("AgtSessionManager", "CloseSession", sessionId)

    def getSessionLabel(self, sessionId=None):
        if sessionId is None:
            sessionId = self.sessionId

        return self.smInvoke("AgtSessionManager", "GetSessionLabel", sessionId)

    def setSessionLabel(self, sessionLabel, sessionId=None):
        if sessionId is None:
            sessionId = self.sessionId

        args = str(sessionId) + " {" + sessionLabel + "}"
        self.smInvoke("AgtSessionManager", "SetSessionLabel", args)

    def listObjects(self, objType="AGT_ALL", fileName=""):
        if objType == "AGT_SAVEABLE":
            return self.invoke("AgtTestSession", "ListSaveableInterfaces")
        elif objType == "AGT_SAVED":
            return self.invoke("AgtTestSession", "ListSavedInterfaces", fileName)
        else:
            return self.invoke("AgtTestSession", "ListInterfaces")

    def resetSession(self, interfaceNames=None):
        if interfaceNames is not None:
            return self.invoke("AgtTestSession", "ResetInterfaces", ' '.join(interfaceNames))
        return self.invoke("AgtTestSession", "ResetSession")

    def saveSession(self, fileName, interfaceNames=None):
        if interfaceNames is not None:
            args = fileName + " " + ' '.join(interfaceNames)
            return self.invoke("AgtTestSession", "SaveInterfaces", args)
        return self.invoke("AgtTestSession", "SaveSession", fileName)

    def restoreSession(self, fileName, interfaceNames=None):
        if self.sessionId < 1:
            self.openSession("FcPerformance")

        if interfaceNames is not None:
            args = fileName + " " + ' '.join(interfaceNames)
            self.invoke("AgtTestSession", "RestoreInterfaces", args)
        else:
            self.invoke("AgtTestSession", "RestoreSession", fileName)

    # N2X API session specific wrappers
    def addPortsToSession(self, ports):
        if type(ports) is list:
            ports = "[list " + ' '.join(ports) + "]"
        self.ports = listFromResponse(self.invoke("AgtPortSelector", "AddPorts", ports))

    def listAddressPools(self, port):
        return listFromResponse(self.invoke("AgtEthernetAddresses", "ListAddressPools", str(port)))                
    def listSutIpAddresses(self, port):
        return listFromResponse(self.invoke("AgtEthernetAddresses", "ListSutIpAddresses", str(port)))                
    def modifySutIpAddress(self, port, oldip, ip):
        try:
            socket.inet_pton(oldip)
            socket.inet_pton(ip)
        except socket.error:
            raise RuntimeError("Malformed IP address supplied (oldip=" + oldip + ",ip=" + ip + ")")

        args = port + " " + oldip + " " + ip
        self.invoke("AgtEthernetAddresses", "ModifySutIpAddress", args)

    def setSutIpAddress(self, port, ip):
        self.modifySutIpAddress(port, self.listSutIpAddresses(port)[0], ip)

    def setTesterIpAddress(self, port, ip, mask, noaddr=1, step=1):
        try:
            socket.inet_pton(ip)
        except socket.error:
            raise RuntimeError("Malformed IP address supplied (ip=" + ip + ")")

        args = self.listAddressPools(port)[0] + " " + ip + " " + mask + " " \
               + str(noaddr) + " " + str(step)
        self.invoke("AgtEthernetAddressPool", "SetTesterIpAddresses", args)

    def addProfile(self, port, profileType):
        args = port + " " + profileType
        self.profiles.append(self.invoke("AgtProfileList", "AddProfile", args))

    def setProfileMode(self, profile, profileType, profileMode):
        args = profile + " " + profileMode
        self.invoke(profileType, "SetMode", args)

    def setProfileAverageLoad(self, profile, profileType, load):
        args = profile + " " + load
        self.invoke(profileType, "SetAverageLoad", args)

    def addStreamGroupToProfile(self, profile):
        args = profile + " AGT_PACKET_STREAM_GROUP 1"
        output = self.invoke("AgtStreamGroupList", "AddStreamGroupsWithExistingProfile", args)
        firstLBracket = output.find('{')
        firstRBracket = output.find('}', firstLBracket)
        secondLBracket = output.find('{', firstRBracket)
        secondRBracket = output.find('}', secondLBracket)

        self.streamGroups.append(output[firstLBracket+1:firstRBracket])
        self.PDUs.append(output[secondLBracket+1:secondRBracket])

    def setExpectedDestinations(self, streamGroup, ports): 
        if type(ports) is list:
            ports = "[list " + ' '.join(ports) + "]"

        args = streamGroup + " " + ports
        self.invoke("AgtStreamGroup", "SetExpectedDestinationPorts", args)

    def setPduHeaders(self, streamGroup, headerTypes):
        if type(headerTypes) is list:
            headerTypes = "[list " + ' '.join(headerTypes) + "]"

        args = streamGroup + " " + headerTypes
        self.invoke("AgtStreamGroup", "SetPduHeaders", args)

    def enableL2ErrorInjection(self, streamGroup, errorType):
        args = streamgroup + " AGT_L2_FCS_ERROR"
        self.invoke("AgtStreamGroup", "SetL2Error", args)

    def setFixedPDUFieldValue(self, pdu, protocol, field, value):
        args = pdu + " \"" + protocol + "\" 1 \"" + field + "\" " + value
        self.invoke("AgtPduHeader", "SetFieldFixedValue", args)

    def setIpv4SourceAddress(self, pdu, addr):
        self.setFixedPduFieldValue(pdu, "ipv4", "source_address", addr)

    def setIpv4DestinationAddress(self, pdu, addr):
        self.setFixedPduFieldValue(pdu, "ipv4", "destination_address", addr)

    def setTcpSourcePort(self, pdu, addr):
        self.setFixedPduFieldValue(pdu, "tcp", "source_port", addr)

    def setTcpDestinationPort(self, pdu, addr):
        self.setFixedPduFieldValue(pdu, "tcp", "destination_port", addr)

    def setUdpSourcePort(self, pdu, addr):
        self.setFixedPduFieldValue(pdu, "udp", "source_port", addr)

    def setUdpDestinationPort(self, pdu, addr):
        self.setFixedPduFieldValue(pdu, "udp", "destination_port", addr)

    def setPayloadFill(self, pdu, fillType, hexFill):
        args = pdu + " " + fillType + " " + hexFill
        self.invoke("AgtPduPayload", "SetPayloadFill", args)

    # N2X API capture configuration wrappers
    def setCapturePorts(self, ports):
        if type(ports) is list:
            ports = "[list " + ' '.join(ports) + "]"

        self.invoke("AgtCaptureControl", "SetPortGroup", ports)

    def clearFiltersOnPort(self, port):
        self.invoke("AgtCaptureFilter", "ClearAllFilters", port)

    def createFrameMatcher(self, port):
        self.frameMatchers.append(self.invoke("AgtFrameMatcherList", "AddFrameMatcher", port))

    def addMatcherFrameFlags(self, frameMatcher, frameFlag):
        args = frameMatcher + " " + frameFlag
        self.invoke("AgtFrameMatcher", "AddFrameFlags", args)

    def addMatcherFilter(self, port, frameMatcher, filter):
        args = port + " " + frameMatcher + " " + filter
        self.invoke("AgtCaptureFilter", "AddFrameMatcherFilterss", args)

    def setCaptureMode(self, capMode):
        self.invoke("AgtCaptureControl", "SetCaptureMode", capMode)

    def setErroredFrameFilter(self, port, filter):
        args = port + " " + filter
        self.invoke("AgtStatisticsControl", "SetErroredFrameFilter", args)

    # N2X API test/capture control wrappers
    def startCapture(self):
        self.invoke("AgtCaptureControl", "StartCapture")

    def getCaptureState(self):
        return self.invoke("AgtCaptureControl", "GetCaptureState")[12:]

    def stopCapture(self):
        self.invoke("AgtCaptureControl", "StopCapture")

    def startTest(self):
        self.invoke("AgtTestController", "StartTest")

    def getTestState(self):
        return self.invoke("AgtTestController", "GetTestState")[9:]

    def stopTest(self):
        self.invoke("AgtTestController", "StopTest")

    # N2X API statistics wrappers
    def createStatHandler(self):
        self.stats.append(self.invoke("AgtStatisticsList", "Add", "AGT_STATISTICS"))

    def selectStats(self, stats, statTypes):
        args = stats + " {" + statTypes + "}"
        self.invoke("AgtStatistics", "SelectStatistics", args)

    def selectStatPorts(self, stats, ports):
        if type(ports) is list:
            ports = "[list " + ' '.join(ports) + "]"

        args = stats + " " + ports
        self.invoke("AgtStatistics", "SelectPorts", args)

    def selectStatStreamGroup(self, stats, streamGroups):
        if type(streamGroups) is list:
            streamGroups = "[list " + ' '.join(streamGroups) + "]"

        args = stats + " " + streamGroups
        self.invoke("AgtStatistics", "SelectStreamGroups", args)

    def collectStats(self, stats, streamGroup):
        args = stats + " " + streamGroup
        return listFromResponse(self.invoke("AgtStatistics", "GetStreamGroupStatistics", args))
