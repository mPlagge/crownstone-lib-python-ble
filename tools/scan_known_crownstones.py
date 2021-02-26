#!/usr/bin/env python3
import asyncio
import json, sys
import logging
from os import path

from crownstone_ble import CrownstoneBle, BleEventBus, BleTopics
from util.config import getToolConfig, loadKeysFromConfig, setupDefaultCommandLineArguments, macFilterPassed

parser = setupDefaultCommandLineArguments('Scan for any Crownstones continuously and print the results.')
parser.add_argument('--verbose', default=False,
                    help='Verbose will show the full advertisement content, not just a single line summary.')
parser.add_argument('--macFilter', default=None, type=str,
                    help='Optional mac filter to only show results for this mac address.')


try:
    file_path = path.dirname(path.realpath(__file__))
    [tool_config, args] = getToolConfig(file_path, parser)
except Exception as e:
    print("ERROR", e)
    quit()

# create the library instance
print(f'Initializing tool with hciIndex={tool_config["hciIndex"]}')
core = CrownstoneBle(hciIndex=tool_config["hciIndex"])

# load the encryption keys into the library
try:
    loadKeysFromConfig(core, tool_config)
except Exception as e:
    print("ERROR", e)
    core.shutDown()
    quit()


# this prints a small overview of all incoming scans.
def printAdvertisements(data):
    if macFilterPassed(args.macFilter, data["address"]):
        print(f'{data["address"]} CrownstoneId={data["id"]} RSSI={data["rssi"]} ')

# this CAN be used for more information. This is used when verbose is on.
def printFullAdvertisements(data):
    if macFilterPassed(args.macFilter, data["address"]):
        print("Scanned device:", json.dumps(data, indent=2))

if args.verbose:
    BleEventBus.subscribe(BleTopics.advertisement, printFullAdvertisements)
else:
    BleEventBus.subscribe(BleTopics.advertisement, printAdvertisements)

async def scan():
    await core.ble.scan(duration=60)

try:
    loop = asyncio.get_event_loop()
    loop.run_until_complete(scan())
except KeyboardInterrupt:
    print("Closing the test.")

core.shutDown()
