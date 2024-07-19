# Senso4s Home Assistant integration

![hacs workflow](https://github.com/jpmeijers/senso4s-home-assistant/actions/workflows/validate.yaml/badge.svg)

This integration adds support for the [Senso4s PLUS](https://www.senso4s.com/product/senso4s-plus/) and [Senso4s BASIC](https://www.senso4s.com/product/senso4s-basic/) smart gas level sensors to Home Assistant.
These sensors use Bluetooth to communicate, so your Home Assistant installation needs to have a [Bluetooth adapter or proxy attached](https://www.home-assistant.io/integrations/bluetooth/).
Setup is done using the [Senso4s Android App](https://play.google.com/store/apps/details?id=com.companyname.Senso4sProject&hl=en_ZA&pli=1) or [Senso4s iOS App](https://apps.apple.com/us/app/senso4s/id1447741983).
After setup is done, you can check the remain level of gas in your cylinder via either the app or this Home Assistant integration.

## Quick Install using HACS

You must have HACS installed: https://hacs.xyz/docs/configuration/basic/

Click the button below to add the Senso4s integration to your Home Assistant.

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jpmeijers&repository=senso4s-home-assistant&category=integration)

After adding it to HACS, you can click Download on the Senso4s repository. After this you will be requested to restart Home Assistant.

## Manual Installation

* Clone this repository
* Copy the directory `custom_components/senso4s` to the `custom_components` directory of your Home Assistant installation
* Restart Home Assistant

## Adding the device to Home Assistant

* In Home Assistant's web UI, go to Settings, Devices & Services
* In the bottom right hand corner, click on `+ Add integration`
* In the search box type `Senso4s`, and choose `Senso4s` in the list shown
** If nothing is found, review the installation steps
* The following screen will show all Bluetooth devices that have been recognised as manufactured by Senso4s
** If you do not see any devices listed, or the message "No devices found on the network", try going closer to your Senso4s device
* After selecting the device, Home Assistant will attempt to read data from it. When that is done you will be greeted by 'n screen asking in which area the device should be classified. You can choose a room, or skip it.


## View data

* After the device has been added, go to Settings, Devices & Services, and select Senso4s
* You should see the Senso4s device listed with its MAC address
* Under the device it should read "1 device and 10 entities"
* Click on the "1 device" hyperlink to see a summary of all the device's sensors
* You can click on any of the sensors to see a graph of its history

![device-summary](media/device-summary.png)

![gas-history](media/gas-history.png)
