import time

from crownstone_core.packets.ResultPacket import ResultPacket
from crownstone_core.protocol.BluenetTypes import ProcessType

from crownstone_ble.Exceptions import BleError
from crownstone_core.Exceptions import CrownstoneException, CrownstoneBleException
from crownstone_core.packets.SessionDataPacket import SessionDataPacket
from crownstone_core.protocol.Characteristics import CrownstoneCharacteristics
from crownstone_core.protocol.ControlPackets import ControlPacketsGenerator
from crownstone_core.protocol.Services import CSServices
from crownstone_core.util.EncryptionHandler import EncryptionHandler, CHECKSUM

from crownstone_core.packets.MicroappPacket import MicroappPacketInternal, MicroappRequestPacket, MicroappValidatePacket, MicroappEnablePacket

class ControlHandler:
    def __init__(self, bluetoothCore):
        self.core = bluetoothCore

    async def getAndSetSessionNone(self):
        # read the nonce
        rawNonce = await self.core.ble.readCharacteristicWithoutEncryption(CSServices.CrownstoneService, CrownstoneCharacteristics.SessionData)
        ProcessSessionNoncePacket(rawNonce, self.core.settings.basicKey, self.core.settings)

    async def setSwitch(self, switchVal: int):
        """
        :param switchVal: 0% .. 100% or special value (SwitchValSpecial).
        """
        await self._writeControlPacket(ControlPacketsGenerator.getSwitchCommandPacket(switchVal))

    async def setRelay(self, turnOn: bool):
        """
        :param turnOn: True to turn relay on.
        """
        await self._writeControlPacket(ControlPacketsGenerator.getRelaySwitchPacket(turnOn))

    async def setDimmer(self, intensity: int):
        """
         :param intensity: percentage [0..100]
        """
        await self._writeControlPacket(ControlPacketsGenerator.getDimmerSwitchPacket(intensity))

    async def commandFactoryReset(self):
        """
          If you have the keys, you can use this to put the crownstone back into factory default mode
        """
        await self._writeControlPacket(ControlPacketsGenerator.getCommandFactoryResetPacket())

    async def allowDimming(self, allow: bool):
        """
        :param allow: True to allow dimming
        """
        await self._writeControlPacket(ControlPacketsGenerator.getAllowDimmingPacket(allow))

    async def disconnect(self):
        """
        Force the Crownstone to disconnect from you.
        """
        try:
            #print("Send disconnect command")
            await self._writeControlPacket(ControlPacketsGenerator.getDisconnectPacket())
        except BTLEDisconnectError:
            print("Disconnect (expected)")
            pass
        except Exception as err:
            #print("Unknown error")
            raise err

        try:
            # Disconnect from this side as well.
            #print("Disconnect from this side as well")
            self.core.ble.disconnect()
        except BTLEDisconnectError:
            print("Disconnect (expected)")
            pass
        except Exception as err:
            #print("Unknown error")
            raise err


    async def lockSwitch(self, lock):
        """
        :param lock: bool
        """
        await self._writeControlPacket(ControlPacketsGenerator.getLockSwitchPacket(lock))


    async def reset(self):
        await self._writeControlPacket(ControlPacketsGenerator.getResetPacket())



    async def recovery(self, address):
        self.core.connect(address, ignoreEncryption=True)
        self._recoveryByFactoryReset()
        self._checkRecoveryProcess()
        self.core.disconnect()
        time.sleep(5)
        self.core.connect(address, ignoreEncryption=True)
        self._recoveryByFactoryReset()
        self._checkRecoveryProcess()
        self.core.disconnect()
        time.sleep(2)

    async def _recoveryByFactoryReset(self):
        packet = ControlPacketsGenerator.getFactoryResetPacket()
        return self.core.ble.writeToCharacteristicWithoutEncryption(
            CSServices.CrownstoneService,
            CrownstoneCharacteristics.FactoryReset,
            packet
        )

    async def _checkRecoveryProcess(self):
        result = self.core.ble.readCharacteristicWithoutEncryption(CSServices.CrownstoneService, CrownstoneCharacteristics.FactoryReset)
        if result[0] == 1:
            return True
        elif result[0] == 2:
            raise CrownstoneException(BleError.RECOVERY_MODE_DISABLED, "The recovery mechanism has been disabled by the Crownstone owner.")
        else:
            raise CrownstoneException(BleError.NOT_IN_RECOVERY_MODE, "The recovery mechanism has expired. It is only available briefly after the Crownstone is powered on.")

    async def sendMicroapp(self, data):
        """
        :param data: byte array
        """
        self._microapp = MicroappPacketInternal(data)
        self.sendMicroappInternal(True)

    async def sendMicroappInternal(self, firstTime, notificationResult=None):
        if not firstTime:

            if not self._microapp.nextAvailable():
                print("LOG: Finish stream")
                return ProcessType.FINISHED

            self._microapp.update()

        # logStr = "LOG: write part %i of %i (size = %i)\n" % (self._microapp.index + 1, self._microapp.count, self._microapp.data.size)
        # sys.stdout.write(logStr);

        if firstTime:
            timeout = self._microapp.count * 10
            print(f"LOG: Use (for the overall connection) a timeout of {timeout} for {self._microapp.count} chunks")

            self.core.ble.setupNotificationStream(
                CSServices.CrownstoneService,
                CrownstoneCharacteristics.Result,
                lambda: self._writeControlPacket(ControlPacketsGenerator.getMicroAppUploadPacket(
                    self._microapp.getPacket())),
                lambda notificationResult: self._handleResult(notificationResult),
                timeout
            )
        else:
            # Notification handler already set up, no need to do it again
            await self._writeControlPacket(ControlPacketsGenerator.getMicroAppUploadPacket(
                    self._microapp.getPacket()))
            return ProcessType.CONTINUE


    async def enableMicroapp(self, packet):
        self._packet = MicroappEnablePacket(packet)
        print("Enable microapp")
        await self._writeControlPacket(ControlPacketsGenerator.getMicroAppEnablePacket(self._packet))

    async def requestMicroapp(self, command):
        self._packet = MicroappRequestPacket(command)
        print("Send microapp request")
        await self._writeControlPacket(ControlPacketsGenerator.getMicroAppRequestPacket(self._packet))

#        # Get response
#        timeout = self._microapp.count * 10
#
#        self.core.ble.setupNotificationStream(
#            CSServices.CrownstoneService,
#            CrownstoneCharacteristics.Result,
#            lambda: await self._writeControlPacket(
#                ControlPacketsGenerator.getMicroAppMetaPacket(
#                    self._microapp.getMetaPacket(packet.param0)))
#            lambda notificationResult: self._handleResult(notificationResult),
#            timeout
#        )

    async def validateMicroapp(self, command):
        self._packet = MicroappValidatePacket(command)
        self._packet.calculateChecksum()
        print("Validate microapp")
        await self._writeControlPacket(ControlPacketsGenerator.getMicroAppValidatePacket(self._packet))

    def _handleResult(self, notificationResult):
        if notificationResult:
            print(notificationResult)
            resultPacket = ResultPacket(notificationResult)
            if not resultPacket.valid:
                print("Invalid result packet")
                return

            err_code = resultPacket.resultCode
            # Only print atypical error codes
            if err_code != 0x00 and err_code != 0x01:
                print("Err code" , err_code)

            # Display type of return code (error)
            if err_code == 0x20:
                print("LOG: ERR_WRONG_PAYLOAD_LENGTH")
            if err_code == 0x70:
                print("LOG: ERR_EVENT_UNHANDLED")
            if err_code == 0x10:
                print("LOG: NRF_ERROR_INVALID_ADDR")
            if err_code == 0x27:
                print("LOG: ERR_BUSY")
            if err_code == 0x22:
                print("LOG: ERR_INVALID_MESSAGE")

            # Normal error codes (first wait for success, then success)
            if err_code == 0x01:
                print("LOG: ERR_WAIT_FOR_SUCCESS")
            if err_code == 0x00:
                print("LOG: ERR_SUCCESS")
                return self.sendMicroappInternal(False, notificationResult)

    #  self.bleManager.readCharacteristic(CSServices.CrownstoneService, characteristicId: CrownstoneCharacteristics.FactoryReset)
    # {(result:[UInt8]) -> Void in
    # if (result[0] == 1)
    #     seal.fulfill(())
    # else if (result[0] == 2) {
    # seal.reject(CrownstoneError.RECOVER_MODE_DISABLED)
    # else {
    # seal.reject(CrownstoneError.NOT_IN_RECOVERY_MODE)
    # .catch{(err) -> Void in
    # seal.reject(CrownstoneError.CANNOT_READ_FACTORY_RESET_CHARACTERISTIC)


    # return self.bleManager.connect(uuid)}
    # .then
    # {(_) -> Promise < Void > in
    # return self._recoverByFactoryReset()}
    # .then
    # {(_) -> Promise < Void > in
    # return self._checkRecoveryProcess()}
    # .then
    # {(_) -> Promise < Void > in
    # return self.bleManager.disconnect()}
    # .then
    # {(_) -> Promise < Void > in
    # return self.bleManager.waitToReconnect()}
    # .then
    # {(_) -> Promise < Void > in
    # return self.bleManager.connect(uuid)}
    # .then
    # {(_) -> Promise < Void > in
    # return self._recoverByFactoryReset()}
    # .then
    # {(_) -> Promise < Void > in
    # return self._checkRecoveryProcess()}
    # .then
    # {(_) -> Promise < Void > in
    # self.bleManager.settings.restoreEncryption()
    # return self.bleManager.disconnect()



    """
    ---------------  UTIL  ---------------
    """




    async def _readControlPacket(self, packet):
        return await self.core.ble.readCharacteristic(CSServices.CrownstoneService, CrownstoneCharacteristics.Control)

    async def _writeControlPacket(self, packet):
        await self.core.ble.writeToCharacteristic(CSServices.CrownstoneService, CrownstoneCharacteristics.Control, packet)


def ProcessSessionNoncePacket(encryptedPacket, key, settings):
    # decrypt it
    decrypted = EncryptionHandler.decryptECB(encryptedPacket, key)

    packet = SessionDataPacket(decrypted)
    if packet.validation == CHECKSUM:
        # load into the settings object
        settings.setSessionNonce(packet.sessionNonce)
        settings.setValidationKey(packet.validationKey)
        settings.setCrownstoneProtocolVersion(packet.protocol)
    else:
        raise CrownstoneBleException(BleError.COULD_NOT_VALIDATE_SESSION_NONCE, "Could not validate the session nonce.")
