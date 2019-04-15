import sublime
import sublime_plugin
import os
from math import floor
import json
import time
import datetime
import pickle
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from json import JSONEncoder

from .innometrics_helper.networks import get_mac_addr, get_ip_addr

global IM
global countingInProgress
global timeoutInProgress
global inCount
IM = None
countingInProgress = False
timeoutInProgress = False
inCount = False


class Innometrics(sublime_plugin.WindowCommand):
    def __init__(self, view):
        global IM

        pluginSettings = sublime.load_settings('sublime-innometrics.sublime-settings')

        self.dirSep = str(os.sep)

        self.setting = {
            'debug': pluginSettings.get('debug'),
            'idle': pluginSettings.get('idle'),
            'date_format': pluginSettings.get('date_format'),
        }

        self.stopTimer = True
        self.fileName = None
        self.fileView = None
        self.base = {}
        self.finish = True
        self.CheckTime = datetime.datetime.fromtimestamp(0)

    def Measure(self):
        global countingInProgress
        global inCount
        if not inCount:
            return
        if self.stopTimer is False:
            countingInProgress = True
            timeSec = (datetime.datetime.now() - self.lastChangeTime).seconds

            if timeSec > self.setting['idle']:
                self.stopTimer = True
                return
            else:
                if self.fileName is None:
                    self.fileName = 'temp files'

                fp = self.fileName
                if fp in self.base:
                    if int(time.time()) > self.base[fp][-1]['EndTime'] + self.setting['idle']:
                        edit_lines = set()
                        edit_lines.add(self.fileView.rowcol(self.fileView.sel()[0].begin())[0])
                        self.base[fp].append({
                            'StartTime': int(time.time()),
                            'EndTime': int(time.time()),
                            "StartLines": self.fileView.rowcol(self.fileView.size())[0],
                            "EndLines": self.fileView.rowcol(self.fileView.size())[0],
                            "EditLines": edit_lines
                        })
                        if self.setting['debug']:
                            print('Innometrics: Started working on file', self.fileName, 'start time: ',
                                  self.base[fp][-1]['StartTime'], 'end time ',
                                  self.base[fp][-1]['EndTime'])

                    else:
                        self.base[fp][-1]['EndTime'] = int(time.time())
                        self.base[fp][-1]["EndLines"] = self.fileView.rowcol(self.fileView.size())[0]
                        self.base[fp][-1]["EditLines"].add(self.fileView.rowcol(self.fileView.sel()[0].begin())[0])
                        if self.setting['debug']:
                            print('Innometrics: Working on file', self.fileName, 'start time: ',
                                  self.base[fp][-1]['StartTime'], 'end time ',
                                  self.base[fp][-1]['EndTime'])
                else:
                    edit_lines = set()
                    edit_lines.add(self.fileView.rowcol(self.fileView.sel()[0].begin())[0])
                    self.base[fp] = [{
                        'StartTime': int(time.time()),
                        'EndTime': int(time.time()) + self.setting['idle'],
                        "StartLines": self.fileView.rowcol(self.fileView.size())[0],
                        "EndLines": self.fileView.rowcol(self.fileView.size())[0],
                        "EditLines": edit_lines
                    }]
                    if self.setting['debug']:
                        print('Innometrics: Started working on new file', self.fileName, 'start time: ',
                              self.base[fp][-1]['StartTime'], 'end time ',
                              self.base[fp][-1]['EndTime'])

                # sublime.set_timeout(lambda: self.Measure(), 5000)

    def WriteBaseToFile(self, data):
        if self.setting['debug']:
            print('Innometrics: Updating database data')
        activities = []
        try:
            file = open(os.path.join(sublime.packages_path(), 'User', 'innometrics.pkl'), "rb")
            activities = pickle.load(file)
            file.close()
        except:
            print("Pickle file not exists. Recreating")
            pass
        new_activities = self.TransformDataToActivities(data)
        for item in new_activities:
            activities.append(item)
        file = open(os.path.join(sublime.packages_path(), 'User', 'innometrics.pkl'), "wb")
        pickle.dump(activities, file)
        file.close()
        self.ClearBase()
        # json_data_file = open(self.setting['db_path'], "w+")
        # json_data_file.write(json.dumps(data, indent=4, sort_keys=True))
        # json_data_file.close()

    def TransformDataToActivities(self, data):
        ip = get_ip_addr()
        mac = get_mac_addr()
        activities = []
        for key, value in data.items():
            for act in value:
                act_type, value = self.GetActivityType(act)
                activity = Activity(key, ip, mac, act_type, act["StartTime"], act["EndTime"], value)
                activities.append(activity)
        return activities

    def GetActivityType(self, act):
        act_type = "subliem_lines_change"
        value = len(act["EditLines"])
        lines_change = act["EndLines"] - act["StartLines"]
        if lines_change < 0:
            act_type = "sublime_lines_delete"
            value = -lines_change
        elif lines_change > 0:
            act_type = "sublime_lines_insert"
            value = lines_change
        return act_type, value

    def ClearBase(self):
        self.base = {}


class InnometricsEventHandler(sublime_plugin.EventListener):
    def on_modified(self, view):
        # print(view.rowcol(view.size())[0]) для полуения текущего кол-ва строк
        global inCount
        if not inCount:
            return
        global IM
        global timeoutInProgress
        wasInit = False
        if IM is None:
            wasInit = True
            IM = Innometrics(view)
        if IM.setting["debug"]:
            print(IM.base)

        if IM.fileName is None:
            IM.fileName = view.file_name()
        if IM.fileView is None:
            IM.fileView = view

        IM.lastChangeTime = datetime.datetime.now()
        IM.stopTimer = False
        IM.Measure()

    def on_activated(self, view):
        global IM
        if IM is not None:
            IM.fileName = view.file_name()
            IM.fileView = view

    def on_post_save_async(self, view):
        if IM and IM.base:
            IM.WriteBaseToFile(IM.base)


class StartInnometricsCommand(sublime_plugin.ApplicationCommand):
    def run(self):
        global inCount
        if inCount:
            sublime.message_dialog("Already on")
            return
        inCount = True
        sublime.message_dialog("Started counting")


class StopInnometricsCommand(sublime_plugin.ApplicationCommand):
    def run(self):
        global inCount
        if not inCount:
            sublime.message_dialog("Already off")
            return
        global IM
        inCount = False
        IM.WriteBaseToFile(IM.base)
        sublime.message_dialog("Stopped counting")


class InnometricsInfoCommand(sublime_plugin.WindowCommand):
    def run(self):
        file = open(os.path.join(sublime.packages_path(), 'User', 'innometrics.pkl'), "rb")
        activities = pickle.load(file)
        file.close()
        file = open(os.path.join(sublime.packages_path(), 'User', 'innometrics.json'), "w")
        file.write(json.dumps([ob.__dict__ for ob in activities], sort_keys=True, indent=4))
        file.close()
        self.window.open_file(os.path.join(sublime.packages_path(), 'User', 'innometrics.json'))


class Activity():
    def __init__(self, executable_name, ip_address, mac_address, activity_type, start_time, end_time, value=None):
        self.executable_name = executable_name
        self.ip_address = ip_address
        self.mac_address = mac_address
        self.activity_type = activity_type
        self.start_time = str(start_time)
        self.end_time = str(end_time)
        self.value = str(value)
        self.id = None

    def add_id(self, id):
        self.id = id


class SendInnometricsCommand(sublime_plugin.ApplicationCommand):
    def run(self):
        global inCount
        if inCount:
            sublime.message_dialog("Stop innometrics counting first")
            return

        token = self.get_token()
        if token is None:
            return
        activities = self.load_activities()
        if activities is None:
            return
        new_activities = []
        for act in activities:
            if act.id is None:
                new_activities.append(act.__dict__)

        if len(new_activities) == 0:
            sublime.message_dialog("No new activities")
            return

        data = {"activity":
                    {"activities": new_activities
                     }
                }

        response, result = self.make_request("/activity", data=data, token=token)
        if not result or response["message"] != "Success":
            return

        sublime.message_dialog("Innometrics successfully sent")
        activity_ids = response["activity_id"]
        i = 0
        for act in activities:
            if act.id is None:
                act.id = activity_ids[i]
                i += 1

        self.dump_activities(activities)

    def load_activities(self):
        try:
            file = open(os.path.join(sublime.packages_path(), 'User', 'innometrics.pkl'), "rb")
            activities = pickle.load(file)
            file.close()
        except:
            sublime.error_message("Activities not exist")
            return None

        return activities

    def dump_activities(self, activities):
        file = open(os.path.join(sublime.packages_path(), 'User', 'innometrics.pkl'), "wb")
        pickle.dump(activities, file)
        file.close()

    def get_token(self):
        token = self.load_token()
        if token is None:
            print("Try to login and get token")
            if self.login():
                token = self.load_token()
                if token is None:
                    sublime.error_message("Get token error")
                    return None
        return token

    def login(self):
        pluginSettings = sublime.load_settings('sublime-innometrics.sublime-settings')

        email = pluginSettings.get('email')
        password = pluginSettings.get('password')
        data = {
            "email": email,
            "password": password
        }
        response, result = self.make_request('/login', data)
        if not result or response["message"] != "Success":
            sublime.error_message("Something wrong with the login data.\n"
                                  "Go to Tools.plugins.Innometrics.Settings and edit them.")
            return None
        token = response["token"]
        self.dump_token(token)
        return True

    def dump_token(self, token):
        file = open(os.path.join(sublime.packages_path(), 'User', 'token'), "w")
        json.dump({"token": token}, file)
        file.close()

    def load_token(self):
        try:
            file = open(os.path.join(sublime.packages_path(), 'User', 'token'), "r")
            data = json.load(file)
            file.close()
            return data["token"]
        except:
            print("Token missing")
            return None

    def make_request(self, endpoint, data, token=None):
        pluginSettings = sublime.load_settings('sublime-innometrics.sublime-settings')

        url = pluginSettings.get('server_url')
        url += endpoint
        data = json.dumps(data).encode('utf-8')
        request = Request(url, data)
        request.add_header("content-type", "application/json")
        if token is not None:
            request.add_header("authorization", "Token " + token)
        try:
            response = urlopen(request).read().decode('utf-8')
        except Exception as e:
            sublime.error_message("Make request to {} error\n{}".format(endpoint, e))
            return None, False
        response_json = json.loads(response)
        return response_json, True
