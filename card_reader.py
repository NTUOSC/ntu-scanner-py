import ctypes

C_PORT_USB = 100
C_BAUD_RATE = 115200

class CardReaderException(Exception):
    def __init__(self, func_name, ret):
        msg = '{} fails with return value {}'.format(func_name, ret)
        super().__init__(msg)
        self.return_value = ret

class CardReader:
    library = None

    @staticmethod
    def initLibrary():
        if hasattr(ctypes, 'WinDLL'):
            CardReader.library = ctypes.WinDLL('dcrf32.dll')
        else:
            CardReader.library = ctypes.CDLL('Rf_linuxhidd8.o')

    def __init__(self, doInitDevice=True):
        if CardReader.library is None:
            CardReader.initLibrary()

        self._icdev = None

        if doInitDevice:
            self.initDevice()

    def initDevice(self):
        icdev = CardReader.library.dc_init(C_PORT_USB, C_BAUD_RATE)
        if icdev == 0:
            raise RuntimeError('Failed to get the descriptor of the device.')

        strSize = ctypes.create_string_buffer(8)
        ret = CardReader.library.dc_getver(icdev, strSize)
        if ret != 0:
            raise CardReaderException('dc_getver', ret)

        self._icdev = icdev
        return self._icdev

    def loadKey(self, key, slot=0, type=0):
        keyPtr = ctypes.c_char_p(key)
        ret = CardReader.library.dc_load_key(self._icdev, slot, type, keyPtr)
        if ret != 0:
            raise CardReaderException('dc_load_key', ret)

    def scanCard(self):
        pass
