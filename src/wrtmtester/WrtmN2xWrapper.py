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
                                           "50 AGT_UNITS_PACKETS_PER_SEC")
            self.n2x.addStreamGroupToProfile(profile)

        self.n2x.setExpectedDestinations(self.n2x.streamGroups[0], self.n2x.ports[2])
        self.n2x.setExpectedDestinations(self.n2x.streamGroups[1], self.n2x.ports[3])

        for streamGroup in self.n2x.streamGroups[:2]:
            self.n2x.setPduHeaders(streamGroup, ['ethernet', 'ipv4', 'udp'])

        self.n2x.setIpv4SourceAddress(self.n2x.PDUs[0], "192.168.1.2")
        self.n2x.setIpv4SourceAddress(self.n2x.PDUs[1], "192.168.2.2")
        self.n2x.setIpv4DestinationAddress(self.n2x.PDUs[0], "192.168.1.1")
        self.n2x.setIpv4DestinationAddress(self.n2x.PDUs[1], "192.168.2.1")
        self.n2x.setUdpSourcePort(self.n2x.PDUs[0], 6478)
        self.n2x.setUdpSourcePort(self.n2x.PDUs[1], 6479)
        self.n2x.setUdpDestinationPort(self.n2x.PDUs[0], 6478)
        self.n2x.setUdpDestinationPort(self.n2x.PDUs[1], 6479)

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

        for port in self.n2x.ports:
            stats = self.n2x.createStatHandler()
            self.n2x.selectStats(stats, "AGT_IP_DATAGRAMS_TRANSMITTED " +
                                        "AGT_IP_DATAGRAMS_RECEIVED " +
                                        "AGT_IP_HEADER_CHECKSUM_ERRORS " +
                                        "AGT_MISDIRECTED_PACKETS_RECEIVED " +
                                        "AGT_PACKET_ERROR_RATE " +
                                        "AGT_ETHERNET_INVALID_FCS_FRAMES_RECEIVED")
            self.n2x.selectStatPorts(stats, port)
            self.n2x.setErroredFrameFilter(port, "AGT_STATISTICS_FILTER_INCLUDE_ALL_FRAMES")

        for stream in self.n2x.streamGroups:
            stats = self.n2x.createStatHandler()
            self.n2x.selectStats(stats, "AGT_STREAM_PACKET_LOSS " +
                                        "AGT_STREAM_AVERAGE_LATENCY " +
                                        "AGT_STREAM_MAXIMUM_LATENCY " +
                                        "AGT_STREAM_SEQUENCE_ERRORS " +
                                        "AGT_STREAM_PACKET_INTEGRITY_ERROR " +
                                        "AGT_STREAM_PACKET_ERROR_RATE " +
                                        "AGT_STREAM_PAYLOAD_BIT_ERROR_RATIO")
            self.n2x.selectStatStreamGroup(stats, stream)

        self.inited = True

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
        outlist = []
        for stats in self.n2x.stats:
            outlist.append(self.n2x.collectStats(stats))

        return outlist

    def shutdownN2X(self):
        if self.inited:
            if self.running:
                self._stopLoadStreams()
            self.inited = False
            self.n2x.closeSession()
            self.n2x.disconnectFromProxy()
