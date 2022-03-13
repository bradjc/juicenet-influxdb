import arrow
import requests

# Main logic for downloading a daily report from the APsystems cloud.
class JuicenetFetcher:
    base_url = "https://jbv1-api.emotorwerks.com"

    def __init__(self, api_key):
        self._api_key = api_key
        self.units = None

    def get_devices(self):

        post_data = {
            "cmd": "get_account_units",
            "device_id": "juicenet-influxdb",
            "account_token": self._api_key,
        }

        result_data = requests.request(
            "POST",
            "{}/box_pin".format(self.base_url),
            json=post_data,
        )

        if result_data.status_code == 200:
            d = result_data.json()
            # 'units': [
            #   {'name': 'device name',
            #    'token': 'device token',
            #    'unit_id': 'unit id'
            #   }
            self.units = d["units"]
        else:
            print("ERROR getting devices")
            self.units = []

    def get_state(self):
        if self.units == None:
            self.get_devices()

        for unit in self.units:

            post_data = {
                "cmd": "get_state",
                "device_id": "juicenet-influxdb",
                "account_token": self._api_key,
                "token": unit["token"],
            }

            result_data = requests.request(
                "POST",
                "{}/box_api_secure".format(self.base_url),
                json=post_data,
            )

            d = result_data.json()

            unit["current_data"] = {
                "state": d["state"],
                "charging_limit_A": d["charging"]["amps_limit"],
                "charging_current_A": d["charging"]["amps_current"],
                "charging_voltage_V": d["charging"]["voltage"],
                "charging_energy_Wh": d["charging"]["wh_energy"],
                "charging_power_W": d["charging"]["watt_power"],
                "lifetime_energy_Wh": d["lifetime"]["wh_energy"],
                "temperature_°F": d["temperature"] * 1.8 + 32.0,
                "frequency_Hz": float(d["frequency"]) / 100.0,
            }

        return self.units

    def get_history(self, after, before=None):

        if self.units == None:
            self.get_devices()

        self.sessions = {}

        for unit in self.units:
            sessions = []

            # May need to call this multiple times to get the entire history.
            continuity_token = None
            finished = False
            while not finished:

                post_data = {
                    "cmd": "get_history",
                    "device_id": "juicenet-influxdb",
                    "account_token": self._api_key,
                    "token": unit["token"],
                }
                if continuity_token != None:
                    post_data["continuity_token"] = continuity_token

                result_data = requests.request(
                    "POST",
                    "{}/box_api_secure".format(self.base_url),
                    json=post_data,
                )

                if result_data.status_code == 200:
                    d = result_data.json()

                    for session in d["sessions"]:
                        start = session["time_start"]

                        if before:
                            if arrow.get(start) < before:
                                sessions.append(session)
                        else:
                            if arrow.get(start) > after:
                                # print(
                                #     "session {}: {}-{}, energy: {} Wh".format(
                                #         session["id"],
                                #         session["time_start"],
                                #         session["time_end"],
                                #         session["wh_energy"],
                                #     )
                                # )

                                sessions.append(session)
                            else:
                                print(arrow.get(start))
                                print(after)
                                finished = True
                                break

                    if "continuity_token" in d:
                        continuity_token = d["continuity_token"]
                    else:
                        finished = True

                else:
                    print("ERROR getting history")

            unit["sessions"] = sessions
            return self.units

    def get_plot(self, after, before=None):
        self.get_history(after, before)

        for unit in self.units:
            for session in unit["sessions"]:
                print(
                    "Getting points for session {}: {}-{}, energy: {} Wh".format(
                        session["id"],
                        session["time_start"],
                        session["time_end"],
                        session["wh_energy"],
                    )
                )
                post_data = {
                    "cmd": "get_plot",
                    "device_id": "juicenet-influxdb",
                    "account_token": self._api_key,
                    "token": unit["token"],
                    "attribute": "power",
                    "intervals": 1000000,  # just some large number to get all data
                    "session_id": session["id"],
                }

                result_data = requests.request(
                    "POST",
                    "{}/box_api_secure".format(self.base_url),
                    json=post_data,
                )

                d = result_data.json()
                session["points"] = []

                if len(d["points"]) == 0:
                    print("no points?!?")
                    continue

                # Put in a zero point if there isn't one at the beginning
                first_point = d["points"][0]
                if first_point["v"] != 0.0:
                    session["points"].append({"t": first_point["t"] - 1, "v": 0.0})

                session["points"] += d["points"]

                last_point = d["points"][-1]
                if last_point["v"] != 0.0:
                    session["points"].append({"t": last_point["t"] + 1, "v": 0.0})

        return self.units
