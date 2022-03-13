#!/usr/bin/env python3

from dateutil import tz
import datetime
import sys

import arrow
import influxdb
import requests

from juicenet_fetcher import JuicenetFetcher


CONFIG_FILE_PATH = "/etc/swarm-gateway/juicenet.conf"
INFLUX_CONFIG_FILE_PATH = "/etc/swarm-gateway/influx.conf"

# Get AP systems config.
juicenet_config = {}
with open(CONFIG_FILE_PATH) as f:
    for l in f:
        fields = l.split("=")
        if len(fields) == 2:
            juicenet_config[fields[0].strip()] = fields[1].strip()

# Get influxDB config.
influx_config = {}
with open(INFLUX_CONFIG_FILE_PATH) as f:
    for l in f:
        fields = l.split("=")
        if len(fields) == 2:
            influx_config[fields[0].strip()] = fields[1].strip()


last_run_timestamp = arrow.get("2010-01-01")
try:
    with open("last_run.txt") as f:
        last_run_timestamp = arrow.get(f.read())
except:
    pass

print("Looking for charging sessions after {}".format(last_run_timestamp))

# What we will set our last_run to after this completes.
new_last_run = last_run_timestamp


# Data fetcher
fetcher = JuicenetFetcher(juicenet_config["api_key"])


# Get all power data.
d = fetcher.get_plot(last_run_timestamp)
# d = fetcher.get_history(last_run_timestamp)


points = []

# Combine charging sessions. These are reverse sorted.
for unit in d:
    print("Unit: {}".format(unit["name"]))
    print("  got {} sessions".format(len(unit["sessions"])))

    # Metadata added to each point.
    metadata = {
        "location_general": juicenet_config["location_general"],
        "location_specific": juicenet_config["location_specific"],
        "description": "Juicebox EVSE",
    }

    metadata["device_id"] = "juicebox-{}".format(unit["unit_id"])
    metadata["name"] = unit["name"]

    concatenated_sessions = []

    combined_energy_wh = 0
    combined_end = None
    combined_start = arrow.now()

    for session in unit["sessions"]:
        t_start = (
            arrow.get(session["time_start"]).replace(tzinfo="US/Eastern").to("utc")
        )
        t_end = arrow.get(session["time_end"]).replace(tzinfo="US/Eastern").to("utc")

        gap = combined_start - t_end
        # Within 5 minutes we say its the same session.
        if gap.total_seconds() < (5 * 60):
            # Add to the running session.
            combined_energy_wh += session["wh_energy"]
            combined_start = t_start

            # print(
            #     "  including: {}-{}, energy: {} Wh".format(
            #         t_start,
            #         t_end,
            #         session["wh_energy"],
            #     )
            # )
        else:
            # This is a new session.
            # First, save the old session.
            if combined_end:
                concatenated_sessions.append(
                    {
                        "start": combined_start,
                        "end": combined_end,
                        "energy_Wh": combined_energy_wh,
                    }
                )
            combined_end = t_end
            combined_start = t_start
            combined_energy_wh = session["wh_energy"]
            # print(
            #     "START: {}-{}, energy: {} Wh".format(
            #         t_start,
            #         t_end,
            #         session["wh_energy"],
            #     )
            # )

    if combined_end:
        # Save the last session.
        concatenated_sessions.append(
            {
                "start": combined_start,
                "end": combined_end,
                "energy_Wh": combined_energy_wh,
            }
        )

    print("  got {} combined sessions".format(len(concatenated_sessions)))
    for session in concatenated_sessions:

        # print(
        #     "  session: {}-{}, energy: {} Wh".format(
        #         session["start"],
        #         session["end"],
        #         session["energy_Wh"],
        #     )
        # )

        duruation_s = int((session["end"] - session["start"]).total_seconds())
        duration_hours = duruation_s // 3600
        duration_minutes = (duruation_s % 3600) // 60
        duration_seconds = duruation_s % 60
        duration_hms = "{:02}:{:02}:{:02}".format(
            duration_hours, duration_minutes, duration_seconds
        )

        ts_start = int(session["start"].timestamp() * 1000 * 1000 * 1000)
        ts_end = int(session["end"].timestamp() * 1000 * 1000 * 1000)

        # Get start point.
        p = {
            "measurement": "evse_sessions",
            "fields": {
                "energy_Wh": session["energy_Wh"],
                "event": "start",
                "duration_s": duruation_s,
                "duration_hms": duration_hms,
            },
            "tags": metadata,
            "time": ts_start,
        }
        points.append(p)

        # Get End point.
        p = {
            "measurement": "evse_sessions",
            "fields": {
                "energy_Wh": 0,
                "event": "end",
                "duration_s": 0,
                "duration_hms": "",
            },
            "tags": metadata,
            "time": ts_end,
        }
        points.append(p)


for unit in d:
    print("Unit: {}".format(unit["name"]))
    print("  got {} sessions".format(len(unit["sessions"])))

    # Metadata added to each point.
    metadata = {
        "location_general": juicenet_config["location_general"],
        "location_specific": juicenet_config["location_specific"],
        "description": "Juicebox EVSE",
    }

    metadata["device_id"] = "juicebox-{}".format(unit["unit_id"])
    metadata["name"] = unit["name"]

    if len(unit["sessions"]) > 0:
        # Set the last run to the end of the most recent session we got.
        new_last_run = arrow.get(unit["sessions"][0]["time_end"])

    for session in unit["sessions"]:

        if not "points" in session:
            break

        print("    got {} points".format(len(session["points"])))
        for point in session["points"]:

            raw_ts = point["t"]
            power_watts = point["v"] * 1000

            t = arrow.get(raw_ts).replace(tzinfo="US/Eastern").to("utc")
            # Need nanosecond timestamp for influx.
            ts = int(t.timestamp() * 1000 * 1000 * 1000)

            p = {
                "measurement": "evse",
                "fields": {
                    "power_w": power_watts,
                },
                "tags": metadata,
                "time": ts,
            }
            points.append(p)

            p = {
                "measurement": "power_w",
                "fields": {
                    "value": power_watts,
                },
                "tags": metadata,
                "time": ts,
            }
            points.append(p)


print("Got {} points".format(len(points)))

if len(points) > 0:
    client = influxdb.InfluxDBClient(
        influx_config["url"],
        influx_config["port"],
        influx_config["username"],
        influx_config["password"],
        influx_config["database"],
        ssl=True,
        gzip=True,
        verify_ssl=True,
    )
    client.write_points(points)
    print("wrote points")


with open("last_run.txt", "w") as f:
    f.write("{}".format(new_last_run))
print("updated last run to {}".format(new_last_run))
