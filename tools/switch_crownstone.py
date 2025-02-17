#!/usr/bin/env python3
import asyncio
from os import path

from crownstone_ble import CrownstoneBle
from util.config import getToolConfig, loadKeysFromConfig, setupDefaultCommandLineArguments

parser = setupDefaultCommandLineArguments("Switch a Crownstone via connection.")
parser.add_argument('--bleAddress', required=True, help='The MAC address/handle of the Crownstone you want to switch')
parser.add_argument('--switchTo',      required=True, type=int, help='0 .. 100 || 255. Switch the Crownstone. 0 is off, 1 .. 99 is dimming, 100 is fully on, 255 is on to whatever behaviour thinks it should be.')


try:
    file_path = path.dirname(path.realpath(__file__))
    [tool_config, args] = getToolConfig(file_path, parser)
except Exception as e:
    print("ERROR", e)
    quit()

# create the library instance
print(f'Initializing tool with bleAdapterAddress={tool_config["bleAdapterAddress"]}')
core = CrownstoneBle(bleAdapterAddress=tool_config["bleAdapterAddress"])

# load the encryption keys into the library
try:
    loadKeysFromConfig(core, tool_config)
except Exception as e:
    print("ERROR", e)
    quit()

async def switch_crownstone():
    try:
        print("Connecting...")
        await core.connect(args.bleAddress)
        print("Connected. Writing...")
        await core.control.setSwitch(args.switchTo)
        print("Written. Disconnecting...")
        await core.disconnect()
        print("Disconnected.")
    except KeyboardInterrupt:
        print("Stopping switch action...")
    await core.shutDown()


try:
    # asyncio.run does not work here.
    loop = asyncio.get_event_loop()
    loop.run_until_complete(switch_crownstone())
except KeyboardInterrupt:
    print("Closing the test.")
