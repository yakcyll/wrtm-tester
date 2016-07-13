import socket


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

        self.smAddress = address
        self.smPort = port
        self.smSocket = None
        
        self.sessionSocket = None

    def reverseProxy(self):
        serverSocket = socket.socket()
        serverSocket.bind("0.0.0.0:" + str(self.smPort))
        serverSocket.listen(1)
        self.smSocket, self.smAddress = self.socket.accept()
        serverSocket.shutdown(socket.SHUT_RDWR)
        serverSocket.close()

    def connect(self):
        raise NotImplementedError()
        
    def invoke(self, interfaceName, methodName, args):
        data = "invoke " + interfaceName + " " + methodName + " " + args;

        self._writeWrapper(data)
        result, output = self._readWrapper()

        if result != 0:
            raise RuntimeError('Error: "' + output + '" while executing command: ' + data)

        return output
        
    def _writeWrapper(self, socket, data):
        try:
            socket.sendall(data)
        except OSError:
            self.shutdown()

    def _readWrapper(self):
        
