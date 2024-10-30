"""
Detection callback w/ scanner
--------------

Example showing what is returned using the callback upon detection functionality

Updated on 2020-10-11 by bernstern <bernie@allthenticate.net>

"""

import asyncio
import logging
import math
import sys
import binascii

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData

logger = logging.getLogger(__name__)


def simple_callback(device: BLEDevice, advertisement_data: AdvertisementData):
    # print("Data:", binascii.hexlify(advertisement_data.manufacturer_data))

    if advertisement_data.manufacturer_data is not None:
        if 0x09CC in advertisement_data.manufacturer_data:
            print("Senso4s device:", device.address)
            # print("Data:", binascii.hexlify(advertisement_data.manufacturer_data[0x09CC]))
            # print("Services:", advertisement_data.service_uuids)
            print("RSSI:", advertisement_data.rssi)

            # Looking for service 00007081-a20b-4d4d-a4de-7f071dbbc1d8
            #                     00001881-23b3-9a14-a4ae-71a713cb89a8 pro
            # Got service         00007081-0000-1000-8000-00805f9b34fb
            #                     00001883-0000-1000-8000-00805f9b34fb

            data = advertisement_data.manufacturer_data[0x09CC]
            if len(data) < 12:
                print("Advertising data too short")
                return
            if data[0] & 0b11110000 == 0b10000000:
                model = "BASIC"
            if data[0] & 0b10001111 == 0b00000011:
                model = "PLUS"
                movement = data[0] & 0b01000000
                inclination = data[0] & 0b00100000
                temperature_status = data[0] & 0b00010000
                if movement or inclination or temperature_status:
                    print("Motion:", movement)
                    print("High inclination:", inclination)
                    print("Low/high temperature:", temperature_status)
                    return

            if data[1] == 0xFE:
                status = "BATTERY_EMPTY"
            elif data[1] == 0xFC:
                status = "SETUP_UNSUCCESSFUL"
            elif data[1] == 0xFF:
                status = "NOT_SET"
            else:
                status = "OK"
                mass_percentage = data[1]

            prediction_minutes = ((data[3] << 8) + data[2]) * 15
            battery_percentage = data[4]
            not_used = data[5]
            mac_address = [data[6], data[7], data[8], data[9], data[10], data[11]]

            pred_months = math.floor(prediction_minutes / 60 / 24 / 30)
            pred_days = math.floor((prediction_minutes / 60 / 24) - (pred_months * 30))
            pred_hours = round((prediction_minutes / 60) - (pred_days * 24) - (pred_months * 30 * 24))

            print(f"Model: {model}")
            print(f"Status: {status}")
            print(f"Mass: {mass_percentage}%")
            print(f"Prediction: {prediction_minutes}m / {pred_months} months {pred_days} days {pred_hours} hours")
            print(f"Battery: {battery_percentage}%")
            # print(f"Not used: {not_used}")
            print("MAC Address:", binascii.hexlify(data[6:12]))
            print()


async def main():
    # while True:
    async with BleakScanner(simple_callback) as scanner:
        await asyncio.sleep(5.0)
        await scanner.stop()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)-15s %(name)-8s %(levelname)s: %(message)s",
    )
    service_uuids = sys.argv[1:]
    asyncio.run(main())
