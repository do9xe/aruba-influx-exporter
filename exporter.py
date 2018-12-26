#!/usr/bin/python3

import json,requests
from aruba_api_caller.aruba_api_caller import *
from config import *
from influxdb import InfluxDBClient

globalStats = {"Clients_count":{"total":0},"Clients_per_Band":{"11a":0,"11g":0}}
BandToFreq = {"1":"5GHz","2":"2.4GHz"}
RadioTemplate = {"Channel":0,"Band":"","channel_busy":0,"Interference":0,"Noise":0,"EIRP":0,"Clients":0,"BSSID":"00:00:00:00:00:00"}
bssidToAP = {}

##################
##   Section 1  ##
##################
# Requesting the basic information from the Mobility Master.

MM = api_session(MM_IP, USER, PASSWORD, check_ssl=CHECK_SSL)
MM.login()
#if DEBUG:
#  print("requesting switch-data")
#switchList = MM.cli_command("show switches")
if DEBUG:
  print("requesting ap database")
apDatabase = MM.cli_command("show ap database")
if DEBUG:
  print("requesting ap database")
radioDatabase = MM.cli_command("show ap radio-database")
if DEBUG:
  print("requesting data from the global shared memory")
gsmAPList = MM.cli_command("show gsm debug channel ap")
gsmRadioList = MM.cli_command("show gsm debug channel radio")
gsmSTAList = MM.cli_command("show gsm debug channel sta")
gsmBssidList = MM.cli_command("show gsm debug channel bss")

MM.logout()


##################
##   Section 2  ##
##################
# Calculation Section. The Collected Data gets merged into one usable Chunk
# Therefor we create a dict to store the data in:
apData = {}

if DEBUG:
  print("calculating and merging all data")

####################
##   Section 2.1  ##
####################
# Moving the AP-Database into a dict from which we can call the APs by name

for ap in apDatabase["AP Database"]:
  apData[ap["Name"]] = ap
  apData[ap["Name"]]["Uptime"] = convertUptime(ap["Status"])
  apData[ap["Name"]]["Status"] = apData[ap["Name"]]["Status"].split(" ")[0]
  if apData[ap["Name"]]["Status"] == "Down":
    apData[ap["Name"]]["Status_bin"] = 0
  else:
    apData[ap["Name"]]["Status_bin"] = 1 

####################
##   Section 2.2  ##
####################
# resorting the gsm radio data so we can select the radios/APs by BSSID
Bssid2radio = {}
for radio in gsmRadioList["radio Channel Table"]:
  Bssid2radio[radio["radio_bssid"]] = radio

Bssid2APname = {}
for bssid in gsmBssidList["bss Channel Table"]:
  Bssid2APname[bssid["bssid"]] = bssid

####################
##   Section 2.3  ##
####################
#we fetch the radio data from the BSSID-List with the BSS of the radios of each AP
#this has to happen twice as the BSS have different indexes.
for gsmAP in gsmAPList["ap Channel Table"]:
  apData[gsmAP["ap_name"]]["radio0"] = RadioTemplate.copy()
  apData[gsmAP["ap_name"]]["radio1"] = RadioTemplate.copy()

  if gsmAP["ap_wifi0_bss"] is not "00:00:00:00:00:00":
    try:
      apData[gsmAP["ap_name"]]["radio0"] = {
        "Channel":int(Bssid2radio[gsmAP["ap_wifi0_bss"]]["channel"]),
        "Band":BandToFreq[Bssid2radio[gsmAP["ap_wifi0_bss"]]["radio_phy_type"]],
        "channel_busy":int(Bssid2radio[gsmAP["ap_wifi0_bss"]]["rn_channel_busy"]),
        "Interference":int(Bssid2radio[gsmAP["ap_wifi0_bss"]]["rn_interference"]),
        "Noise":int(Bssid2radio[gsmAP["ap_wifi0_bss"]]["rn_noise_floor"]),
        "BSSID":gsmAP["ap_wifi0_bss"],
        "Clients":0
      }
    except:
      pass
  if gsmAP["ap_wifi1_bss"] is not "00:00:00:00:00:00":
    try:
      apData[gsmAP["ap_name"]]["radio1"] = {
        "Channel":int(Bssid2radio[gsmAP["ap_wifi1_bss"]]["channel"]),
        "Band":BandToFreq[Bssid2radio[gsmAP["ap_wifi1_bss"]]["radio_phy_type"]],
        "channel_busy":int(Bssid2radio[gsmAP["ap_wifi1_bss"]]["rn_channel_busy"]),
        "Interference":int(Bssid2radio[gsmAP["ap_wifi1_bss"]]["rn_interference"]),
        "Noise":int(Bssid2radio[gsmAP["ap_wifi1_bss"]]["rn_noise_floor"]),
        "BSSID":gsmAP["ap_wifi1_bss"],
        "Clients":0
      }
    except:
      pass

####################
##   Section 2.4  ##
####################
#fetch the TX-Power of the Radios and add them accordingly
for radio in radioDatabase["AP Radio Database"]:
  if radio["Radio 0 Mode/Chan/EIRP"] is not None:
    if radio["Radio 0 Mode/Chan/EIRP"].startswith("AP"):
      apData[radio["Name"]]["radio0"]["EIRP"] = int(radio["Radio 0 Mode/Chan/EIRP"].split("/")[2].split(".")[0])
  if radio["Radio 1 Mode/Chan/EIRP"] is not None:
    if radio["Radio 1 Mode/Chan/EIRP"].startswith("AP"):
      apData[radio["Name"]]["radio1"]["EIRP"] = int(radio["Radio 1 Mode/Chan/EIRP"].split("/")[2].split(".")[0])

####################
##   Section 2.5  ##
####################
# Count the clients
for sta in gsmSTAList["sta Channel Table"]:
  globalStats["Clients_count"]["total"] += 1
  if sta["radio_phy_type"] == "1":
    globalStats["Clients_per_Band"]["11a"] += 1
  else:
    globalStats["Clients_per_Band"]["11a"] += 1
  try:
    globalStats["Clients_count"][sta["essid"]] += 1
  except:
    globalStats["Clients_count"][sta["essid"]] = 1


  thisAPname = Bssid2APname[sta["bssid"]]["ap_name"]
  if Bssid2APname[sta["bssid"]]["radio_phy_type"] == "2":
    APradio = "radio1"
  else:
    APradio = "radio0"
  apData[thisAPname][APradio]["Clients"] += 1

##################
##   Section 3  ##
##################
# Push the data into a decent structure
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
json_body.append(globalStats)

if DEBUG:
  print("pushing Data to influxDB")

InfluxClient = InfluxDBClient(InfluxIp, InfluxPort, InfluxUser, InfluxPassword, InfluxDbName,ssl=False,verify_ssl=False)
InfluxClient.write_points(json_body)