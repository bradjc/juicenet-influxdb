#!/usr/bin/env python3

import influxdb

from juicenet_fetcher import JuicenetFetcher


CONFIG_FILE_PATH = "/etc/swarm-gateway/juicenet.conf"
INFLUX_CONFIG_FILE_PATH = "/etc/swarm-gateway/influx.conf"

# Get juicenet config.
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


# Data fetcher
fetcher = JuicenetFetcher(juicenet_config["api_key"])
d = fetcher.get_state()

points = []
for unit in d:
    metadata = {
        "location_general": juicenet_config["location_general"],
        "location_specific": juicenet_config["location_specific"],
        "description": "Juicebox EVSE",
    }

    metadata["device_id"] = "juicebox-{}".format(unit["unit_id"])
    metadata["name"] = unit["name"]

    p = {
        "measurement": "evse_status",
        "fields": unit["current_data"],
        "tags": metadata,
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
