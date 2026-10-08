# Zephyr Home Hub Handbook

## Overview

The Zephyr Home Hub is a countertop smart-home controller released in 2024. It connects to lights, thermostats and
door locks over Thread, Zigbee and Wi-Fi, and exposes a local web dashboard so that automations keep working even
when the internet connection is down. The hub is designed to be set up in under ten minutes without an account.

## Setup

Plug the hub into the included 12V power adapter and wait for the ring light to pulse blue. Open the Zephyr app,
choose "Add hub", and hold the top button for five seconds until the ring turns white. The hub then joins your
Wi-Fi network using credentials passed from your phone over Bluetooth. If the ring stays red after two minutes,
power-cycle the hub and repeat the pairing steps.

## Factory reset

To erase all paired devices and settings, hold the rear recessed button with a paperclip for fifteen seconds
until the ring flashes amber three times. A factory reset does not delete firmware updates already installed.
After a reset the hub must be paired again from scratch, and any local automations are lost.

## Battery backup

An optional battery dock keeps the hub running during power cuts. A fully charged dock provides about four hours
of runtime with Thread and Zigbee radios active, or nine hours if Wi-Fi is the only radio in use. The dock
charges in roughly three hours and should be replaced after about 500 charge cycles.

## Supported protocols

The hub contains a Thread border router, a Zigbee 3.0 coordinator and a dual-band Wi-Fi radio. It does not
support Z-Wave, and there are no plans to add it. Matter devices are supported over both Thread and Wi-Fi,
and up to 128 devices can be paired at the same time.

## Voice control

Voice commands are processed on the device using a small speech model, so no audio leaves your home. The wake
word is "Hey Zephyr" and cannot be changed. Eight languages are available: English, Spanish, French, German,
Italian, Portuguese, Japanese and Korean. Voice control can be muted with the hardware switch on the back.

## Automations

Automations follow a trigger, condition, action pattern. A trigger can be a time, a sensor reading, or a device
state change. Conditions narrow when the automation may run, for example only after sunset or only when someone
is home. Each hub can store up to 200 automations. Automations run locally, and typically fire within 150
milliseconds of the trigger.

## Privacy and security

All traffic between the hub and the cloud is encrypted with TLS 1.3. Camera footage is never uploaded unless a
user enables cloud backup for that specific camera. Security patches are delivered monthly, and critical fixes
are pushed within 72 hours. The hub supports passkey sign-in and optional two-factor authentication.

## Firmware updates

Updates download in the background and install at 3 a.m. local time by default. You can change the install
window in Settings under "Maintenance". If an update fails, the hub automatically rolls back to the previous
version and retries after 24 hours. Release notes are published on the first Tuesday of each month.

## Troubleshooting

If devices show as offline, first check that the hub's ring light is solid white. A pulsing yellow ring means
the hub has lost its internet connection but local control still works. A solid red ring indicates a hardware
fault; contact support with the serial number printed under the base. Zigbee interference from busy 2.4 GHz
Wi-Fi channels is the most common cause of slow device responses, and moving the Wi-Fi router to channel 1 or
11 usually helps.

## Warranty

The hub carries a two-year limited warranty from the date of purchase. The battery dock is covered for one
year. Water damage and unauthorised modification are not covered. To claim, contact support with your proof
of purchase and the hub serial number; replacements normally ship within five business days.

## Specifications

The hub measures 98 mm in diameter and 41 mm in height and weighs 210 grams. It draws 4 watts on average and
a maximum of 9 watts. Operating temperature is 0 to 40 degrees Celsius. The enclosure is made of 60 percent
recycled plastic and the package is fully recyclable.
