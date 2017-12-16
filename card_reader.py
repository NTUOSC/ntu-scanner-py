import ctypes


C_PORT_USB = 100
C_BAUD_RATE = 115200

# TODO: set proper block here to retrieve the correct block ^.<
# C_TARGET_BLOCK = 1048
C_TARGET_SECTOR = C_TARGET_BLOCK // 4


class CardReaderException(Exception):
    def __init__(self, func_name, ret, help=None):
        msg = '{} fails with return value {}'.format(func_name, ret)
        if help is not None:
            msg += '; ' + help
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

        self.last_snr = None
        self._icdev = None
        self._strSize = None

        if doInitDevice:
            self.initDevice()

    def initDevice(self):
        icdev = CardReader.library.dc_init(C_PORT_USB, C_BAUD_RATE)
        if icdev == 0:
            raise RuntimeError('Failed to get the descriptor of the device.')

        self._strSize = ctypes.create_string_buffer(8)
        ret = CardReader.library.dc_getver(icdev, self._strSize)
        if ret != 0:
            raise CardReaderException('dc_getver', ret)

        self._icdev = icdev

    def getDescriptor(self):
        return self._icdev

    def loadKey(self, key, slot=0, type=0):
        keyPtr = ctypes.c_char_p(key)
        ret = CardReader.library.dc_load_key(self._icdev, slot, type, keyPtr)
        if ret != 0:
            raise CardReaderException('dc_load_key', ret)

    def scanCard(self, returnStr=False):
        icdev = self._icdev
        lib = CardReader.library

        if _icdev is None:
            raise RuntimeError('Device is not initialized yet!')

        ret = lib.dc_reset(icdev, 0)
        if ret != 0:
            raise CardReaderException('dc_reset', ret)

        tagtype = ctypes.c_uint()
        ret = lib.dc_request(icdev, 0, ctypes.byref(tagtype))
        if ret != 0:
            raise CardReaderException('dc_request', ret, 'is the card on the tray?')

        card_snr = ctypes.c_uint()
        if lib.dc_anticoll(icdev, 0, ctypes.byref(card_snr)) != 0:
            raise CardReaderException('dc_anticoll', ret)
        # not knowing what this is for; save it anyways
        self.last_snr = card_snr.value

        ret = lib.dc_select(icdev, card_snr, self._strSize)
        if ret != 0:
            raise CardReaderException('dc_select', ret)

        ret = lib.dc_authentication(icdev, 0, C_TARGET_SECTOR)
        if ret != 0:
            raise CardReaderException('dc_authentication', ret, 'check if the card is a valid ID card')

        data = ctypes.create_string_buffer(16)
        ret = lib.dc_read(icdev, C_TARGET_BLOCK, data)
        if ret != 0:
            raise CardReaderException('dc_read', ret, 'check if the card is a valid ID card')

        if returnStr:
            return data.value.decode('utf-8')
        return data
