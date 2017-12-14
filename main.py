import sys
import os
import time
import json
import threading
from functools import partial

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib

from card_reader import CardReader
import requests
from requests_futures.sessions import FuturesSession

session = FuturesSession()

G_API_PATH = 'https://home.ntuosc.org/go'
G_TOKEN_SAVE_PATH = './TOKEN.txt'

globalInfo = {
    'entryCode': '',
    'clientInfo': None
}

def queryPing(token, callback=None, **kwargs):
    return session.get(G_API_PATH + '/ping',
            params={ 'token': token },
            background_callback=callback,
            **kwargs)

def startHealthCheck():
    def pingPeriodic():
        while True:
            if globalInfo['entryCode']: break
            time.sleep(5)

        print('health check started')

        while True:
            areq = queryPing(globalInfo['entryCode'], None, timeout=3)

            try:
                resp = areq.result()
                data = resp.json()
                if data['ok']:
                    pass
                print('health check @ ', resp.json())
            except requests.exceptions.ConnectTimeout:
                print('health check timeouts')

            # XXX: should add some randomness
            time.sleep(20)

    thr = threading.Thread(target=pingPeriodic)
    thr.daemon = True
    thr.start()
    return thr

def setClientInfo(builder):
    # set client name based on client info received
    builder.get_object('client_name').set_text('票點：' + globalInfo['clientInfo'].get('name', '??'))


class Handler:
    builder = None
    application = None

    def __init__(self, inst):
        self.builder = inst

    def get(self, name):
        return self.builder.get_object(name)

    def appQuit(self, *args):
        Gtk.main_quit(*args)

    def dialogLogin(self, *args):
        dialog = self.get('login_dialog')

        def makeMsgbox(msgPri, msgSec=''):
            msgbox = Gtk.MessageDialog(dialog, Gtk.DialogFlags.MODAL,
                Gtk.MessageType.ERROR, Gtk.ButtonsType.OK,
                msgPri)
            msgbox.format_secondary_text(msgSec)
            msgbox.run()
            msgbox.close()

        def loginCallback(sess, resp):
            GLib.idle_add(dialog.set_sensitive, True)

            try:
                data = resp.json()
                print(data)
            except:
                GLib.idle_add(makeMsgbox,
                    '未預期的錯誤狀況', '請將以下文字回報選務中心：\n{}'.format(resp.text))
                return

            if data['ok']:
                globalInfo['clientInfo'] = data['client']
                globalInfo['entryCode'] = entryCode
                GLib.idle_add(setClientInfo, self.builder)
                with open(G_TOKEN_SAVE_PATH, 'w') as f:
                    f.write(entryCode)
                # close the window (>0: success)
                dialog.emit('response', 1)
            else:
                GLib.idle_add(makeMsgbox,
                    '認證失敗：{} ({})'.format(data['msg'], resp.status_code), '請再次確認授權碼')

        dialog.set_sensitive(False)
        entryCode = self.get('entry_code').get_text()
        queryPing(entryCode, loginCallback)

    def onStartReadCard(self, *args):
        pass

    def onStartBypass(self, *args):
        pass

    def getVoterInfo(self, *args):
        pass


def ui_start():
    builder = Gtk.Builder()
    builder.add_from_file('ui.glade')
    builder.connect_signals(Handler(builder))

    provider = Gtk.CssProvider()
    provider.load_from_path('./scanner.css')
    Gtk.StyleContext.add_provider_for_screen(
        Gdk.Screen.get_default(),
        provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    window = builder.get_object('app_window')

    settings = window.get_settings()
    settings.set_property('gtk-font-name', '微軟正黑體')

    window.show()

    def fillClientInfo(_, resp):
        data = resp.json()
        if data['ok']:
            globalInfo['clientInfo'] = data['client']
        else:
            globalInfo['clientInfo'] = {}
        GLib.idle_add(setClientInfo, builder)

    try:
        # use cred. saved locally
        with open(G_TOKEN_SAVE_PATH, 'r') as f:
            globalInfo['entryCode'] = f.read().strip()
        queryPing(globalInfo['entryCode'], fillClientInfo)

    except OSError as err:
        # ask to login
        loginDialog = builder.get_object('login_dialog')
        response = loginDialog.run()
        if response <= 0:  # destroy = -4
            return
        loginDialog.close()

    timerThread = startHealthCheck()

    return Gtk.main()

if __name__ == '__main__':
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    ui_start()
    exit(0)
