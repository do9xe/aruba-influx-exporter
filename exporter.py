#!/usr/bin/python3

import json,requests
from aruba_api_caller.aruba_api_caller import *
from config import *
from influxdb import InfluxDBClient

apActivePerSwitch = {}
radioDataPerSwitch = {}
apData = {}

MM = api_session(MM_IP, USER, PASSWORD, False)
MM.login()
if DEBUG:
  print("requesting switch-data...")
switchList = MM.cli_command("show switches")
if DEBUG:
  print("requesting ap database...")
apDatabase = MM.cli_command("show ap database")
MM.logout()

if DEBUG:
  print("Goind through all the switches")
for switch in switchList["All Switches"]:
  if switch["Model"] != "ArubaMM-VA" and switch["Status"] == "up":
    tmpSession = api_session(switch["IP Address"], USER, PASSWORD, False)
    tmpSession.login()
    if DEBUG:
      print("requesting active APs from" + str(switch["IP Address"]))
    apActivePerSwitch[str(switch["IP Address"])] = tmpSession.cli_command("show ap active")
    if DEBUG:
      print("requesting Radio-summary from" + str(switch["IP Address"]))
    radioDataPerSwitch[str(switch["IP Address"])] = tmpSession.cli_command("show ap radio-summary")
    tmpSession.logout()

if DEBUG:
  print("calculating and merging all data")
for ap in apDatabase["AP Database"]:
  apData[ap["Name"]] = ap
  apData[ap["Name"]]["11g Clients"] = 0
  apData[ap["Name"]]["11a Clients"] = 0
  apData[ap["Name"]]["Status"] = apData[ap["Name"]]["Status"].split(" ")[0]
  apData[ap["Name"]]["Uptime"] = convertUptime(ap["Status"])
  if apData[ap["Name"]]["Status"] == "Down":
    apData[ap["Name"]]["Status_bin"] = 0
  else:
    apData[ap["Name"]]["Status_bin"] = 1 

for switch in apActivePerSwitch:
  for activeAP in apActivePerSwitch[switch]["Active AP Table"]:
    apData[activeAP["Name"]]["11g Clients"] += int(activeAP["11g Clients"])
    apData[activeAP["Name"]]["11a Clients"] += int(activeAP["11a Clients"])

for switch in radioDataPerSwitch:
  for thisRadio in radioDataPerSwitch[switch]["APs Radios information"]:
    apData[thisRadio["Name"]]["Noise"+thisRadio["Band"]] = int(thisRadio["NF/U/I"].split("/")[0])
    apData[thisRadio["Name"]]["Usage"+thisRadio["Band"]] = int(thisRadio["NF/U/I"].split("/")[1])
    apData[thisRadio["Name"]]["Interference"+thisRadio["Band"]] = int(thisRadio["NF/U/I"].split("/")[2])


json_body = []
for Name in apData:
  data = apData[Name]
  json_body.append({
                  "measurement": "AP_Data",
                  "fields": data,
                  "tags": {
                    "host": data["Name"],
                    "group":data["Group"],
                    "ap_type":data["AP Type"],
                    "status":data["Status"]
                  }})

if DEBUG:
  print("pushing Data to influxDB")

InfluxClient = InfluxDBClient(InfluxIp, InfluxPort, InfluxUser, InfluxPassword, InfluxDbName)
InfluxClient.write_points(json_body)


#for x in (y for y in daten["RADIO Stats"] if y["Parameter"] == "Tx Data Frames  12 Mbps  (Mon)"):
#  print (x["Value"])
