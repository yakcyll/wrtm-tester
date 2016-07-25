from wrtmtester import N2xInterface

class WrtmN2xWrapper(object):
    def __init__(self):
        self.n2x = N2xInterface()
        self.inited = False
        self.running = False

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

        for profile in self.n2x.profiles:
            self.n2x.setProfileMode(profile, "AgtConstantProfile", 
                                    "AGT_TRAFFIC_PROFILE_MODE_CONTINUOUS")
            self.n2x.setProfileAverageLoad(profile, "AgtConstantProfile",
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

        self.n2x.setCapturePorts([self.n2x.ports[2], self.n2x.ports[3]])

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
        if self.inited:
            self.n2x.startCapture()
            self.n2x.startTest()
            self.running = True

    def _stopLoadStreams(self):
        if self.inited:
            self.running = False
            self.n2x.stopTest()
            self.n2x.stopCapture()

    def collectLoadStats(self):
        pass

    def shutdownN2X(self):
        if self.inited:
            if self.running:
                self._stopLoadStreams()
            self.n2x.closeSession()
            self.n2x.disconnectFromProxy()
