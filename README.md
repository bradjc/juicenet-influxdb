Juicenet to InfluxDB 1.x
========================

This python script pulls data from the Juicenet API and then pushes to InfluxDB
1.x.

I used the API documentation from
[here](https://github.com/jesserockz/python-juicenet/blob/master/JuiceNet%20API_client_12_11_2017.docx.pdf).

Scripts
-------

- `juicenet-influxdb.py`: This pulls historical charge session data including
  the timeseries of power measurements. The intention is this runs once per day.

- `juicenet-status-influxdb.py`: This fetches the current charging state and
  lifetime energy use. I run this one per minute.

Configuration
-------------

`/etc/swarm-gateway/influx.conf`:

```
url=
port=
username=
password=
database=
```

`/etc/swarm-gateway/juicenet.conf`:

```
api_key=
location_general=
location_specific=
```
