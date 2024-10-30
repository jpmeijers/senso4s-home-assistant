import asyncio
import binascii
import datetime
import pprint
import struct
import time

from bleak import BleakClient, BleakGATTCharacteristic

DEVICE_MAC = "DE:AD:BE:EF:00:11"
BASIC_SERVICE = "00007081-a20b-4d4d-a4de-7f071dbbc1d8"
MASS_CHARACTERISTIC_UUID_READ = "00007082-a20b-4d4d-a4de-7f071dbbc1d8"
PARAMS_CHARACTERISTIC_UUID_READWRITE = "00007083-a20b-4d4d-a4de-7f071dbbc1d8"
HISTORY_CHARACTERISTIC_UUID_NOTIFYWRITE = "00007085-a20b-4d4d-a4de-7f071dbbc1d8"
SETUPTIME_CHARACTERISTIC_UUID_READ = "00007087-a20b-4d4d-a4de-7f071dbbc1d8"

# We should be storing notification data under a device identifier, but that is not available in the callback
notify_data = []


def notification_handler(characteristic: BleakGATTCharacteristic, data: bytearray):
    # Ex: a006800988064a0172068c01
    if len(data) % 4 != 0:
        print("Message length not multiple of 4")
    entries = struct.iter_unpack("<HH", data)
    for entry in entries:
        notify_data.append((entry[0], entry[1]))


async def main():
    print("Connecting...")
    async with BleakClient(DEVICE_MAC) as client:
        print(f"Connected: {client.is_connected}")

        for service in client.services:
            if service.uuid == BASIC_SERVICE:
                for char in service.characteristics:

                    if char.uuid == MASS_CHARACTERISTIC_UUID_READ:
                        try:
                            value = await client.read_gatt_char(char)
                            if value[0] == 0xFE:
                                status2 = "BATTERY_EMPTY"
                            elif value[0] == 0xFC:
                                status2 = "SETUP_UNSUCCESSFUL"
                            elif value[0] == 0xFF:
                                status2 = "NOT_SET"
                            else:
                                status2 = "OK"
                                mass_percentage = value[0]
                        except Exception as e:
                            print(f"Error: {e}")

                    if char.uuid == PARAMS_CHARACTERISTIC_UUID_READWRITE:
                        try:
                            value = await client.read_gatt_char(char)
                            params = struct.unpack("<HHB", value)
                            cylinder_weight = params[0]
                            cylinder_capacity = params[1]
                        except Exception as e:
                            print(f"Error: {e}")

                    if char.uuid == SETUPTIME_CHARACTERISTIC_UUID_READ:
                        try:
                            value = await client.read_gatt_char(char)
                            timeparts = struct.unpack("<HBBBBB", value)
                            setup_time = datetime.datetime(year=timeparts[0], month=timeparts[1], day=timeparts[2],
                                                           hour=timeparts[3], minute=timeparts[4])
                        except Exception as e:
                            print(f"Error: {e}")

                    if char.uuid == HISTORY_CHARACTERISTIC_UUID_NOTIFYWRITE:
                        global notify_data
                        notify_data = []

                        await client.start_notify(HISTORY_CHARACTERISTIC_UUID_NOTIFYWRITE, notification_handler)
                        await client.write_gatt_char(HISTORY_CHARACTERISTIC_UUID_NOTIFYWRITE, b'\x00\x00')
                        await asyncio.sleep(5.0)
                        await client.stop_notify(HISTORY_CHARACTERISTIC_UUID_NOTIFYWRITE)

        print(f"Status2: {status2}")
        print(f"Mass: {mass_percentage}%")
        print(f"Total gas capacity: {cylinder_capacity / 100}kg")
        print(f"Empty cylinder weight: {cylinder_weight / 100}kg")
        print(f"Setup date: {setup_time}")

        # The interpretation of the history is different than I think
        if len(notify_data) > 0:
            print(
                f"{setup_time}: {notify_data[0][0] / 100}kg / {round(notify_data[0][0] * 100 / cylinder_capacity, 1)}%")

        time_offset = 0
        for data in notify_data:
            time_offset += data[1]
            start_time = setup_time + datetime.timedelta(minutes=time_offset * 15)
            duration = datetime.timedelta(minutes=data[1] * 15)
            print(f"{start_time}: {data[0] / 100}kg / {round(data[0] * 100 / cylinder_capacity, 1)}% for {duration}")


if __name__ == "__main__":
    asyncio.run(main())
