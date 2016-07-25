import serial
import time
import threading

class SerialReader(object):
    def __init__(self, verbose=False):
        self.handle = None
        self.doLoop = False
        self.thread = None
        self.outputFile = None
        self.verbose = verbose

    def setVerbose(self, verbose):
        self.verbose = verbose

    def init(self, device, outfile):
        sd = serial.Serial()
        sd.port = device
        sd.baudrate = 115200
        sd.bytesize = serial.EIGHTBITS
        sd.parity = serial.PARITY_NONE
        sd.stopbits = serial.STOPBITS_ONE
        sd.xonxoff = False
        sd.rtscts = False
        sd.dsrdtr = False
        sd.timeout = 1

        self.handle = sd
        self.doLoop = True

        timeStr = time.strftime("%d-%m-%Y_%H-%M-%S", time.gmtime())
        self.outputFile = open(outfile, "w+")
        logIntroLine1 = "WRTMasher Router Serial Log\n"
        logIntroLine2 = "Opened " + device + " @ " + timeStr + "\n"
        logIntroLine3 = "*" * (len(logIntroLine2) - 1) + "\n"
        logIntro = logIntroLine1 + logIntroLine2 + logIntroLine3
        self.outputFile.write(logIntro)

        self.handle.open()
        self.handle.flushInput()
        self.handle.flushOutput()

        self.thread = threading.Thread(target=self._threadFunc)
        self.thread.daemon = False
        self.thread.start()

    def close(self):
        self.doLoop = False
        self.thread.join()
        self.outputFile.close()

    def _threadFunc(self):
        x = bytes()
        while self.doLoop:
            x += self.handle.read()
            if len(x) == 0:
                continue

            try:
                xstr = x.decode('utf8')
            except UnicodeDecodeError:
                x = x[:-1]  # TODO: losing chars?
                continue

            if self.verbose:
                print(xstr, end="")

            self.outputFile.write(xstr)

            x = bytes()

        # read the rest
        self.handle.timeout = 2
        xstr = (x + self.handle.read()).decode('utf8')
        if self.verbose:
            print(xstr, end="")
        self.outputFile.write(xstr)
