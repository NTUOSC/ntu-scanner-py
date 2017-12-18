import sys
import os
import time
import json
import threading

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, Gio, GLib

from card_reader import CardReader, CardReaderException
import requests
from requests.exceptions import ConnectTimeout
# from requests_futures.sessions import FuturesSession
# from session.sessions import FuturesSession
from session import FuturesSession

session = FuturesSession()

G_API_PATH = 'https://home.ntuosc.org/go'
G_TOKEN_SAVE_PATH = './TOKEN.txt'

GC_VOTER_INFO_CAN_VOTE = '''<span color="#388e3c">學號 <b>{r[stuid]}</b>
身份別：<b>{r[stutype]}</b>
選區：<b>{r[college]}</b> {mod}
原學系代碼：{r[dptcode]}
驗證通過
</span>
'''
GC_VOTER_INFO_CANNOT_VOTE = '''<span color="#f44336">學號 <b>{r[stuid]}</b>
身份別：<b>{r[stutype]}</b>
選區：{r[college]}
原學系代碼：{r[dptcode]}
驗證失敗！"{msg}"
</span>
'''
GC_VOTER_INFO_ERROR = '<span color="red">不具投票身份：<b>{}</b></span>'

'''
Given the college (學院代碼), return the string (i.e. 選票別) that is attached
after the string...
'''
def getModifier(college):
    groupA = ['法學院', '文學院', '社會科學院', '生物資源暨農學院', '生命科學院']
    groupB = ['理學院', '醫學院', '工學院', '管理學院', '電機資訊學院']
    if college in groupA:
        return '(A)'
    if college in groupB:
        return '(B)'
    return ''

'''
API wrappers; should be wrapped as a class though
'''
def queryPing(token, callback=None, **kwargs):
    return session.get(G_API_PATH + '/ping',
        params={ 'token': token },
        background_callback=callback,
        **kwargs)

def queryQuery(params, callback=None, **kwargs):
    return session.get(G_API_PATH + '/query',
        params=params,
        background_callback=callback,
        **kwargs)

def queryCommit(paraPair, callback=None, **kwargs):
    token, tx = paraPair
    return session.post(G_API_PATH + '/commit',
        params={ 'token': token },
        data={ 'tx': tx },
        background_callback=callback,
        **kwargs)

'''
other thread; should be wrapped (ry
'''
def startHealthCheck(app):
    fstr = '%H:%M:%S'
    label = app.get('last_sync_ts')

    def setLoadStr():
        label.set_text('...' + label.get_text())

    def pingPeriodic():
        while True:
            if app._entryCode: break
            time.sleep(5)

        print('Health check started')

        while True:
            areq = queryPing(app._entryCode, None, timeout=3)
            GLib.idle_add(setLoadStr)

            try:
                resp = areq.result()
                timestr = time.strftime(fstr)
                data = resp.json()
                result = ''
                if data['ok']:
                    result = '成功'
                else:
                    result = '失敗: {}'.format(data['msg'])
                GLib.idle_add(label.set_text, timestr + ' ' + result)
            except ConnectTimeout:
                timestr = time.strftime(fstr)
                GLib.idle_add(label.set_text, timestr + ' 逾時')
            except:
                timestr = time.strftime(fstr)
                GLib.idle_add(label.set_text, timestr + ' 錯誤')

            # XXX: should add some randomness
            time.sleep(14)

    thr = threading.Thread(target=pingPeriodic)
    thr.daemon = True
    thr.start()
    return thr


'''
The main application
'''
class Application(Gtk.Application):
    builder = None
    cardReader = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args,
                         application_id='org.ntusc106vote.scanner',
                         flags=Gio.ApplicationFlags.FLAGS_NONE,
                         **kwargs)

        self.window = None
        self._generalStatusCtxId = None
        self._entryCode = ''
        self._clientInfo = None
        self._card_sec = None
        self._card_serial = None
        self._tx = None

    def do_startup(self, *args):
        Gtk.Application.do_startup(self)

        builder = Gtk.Builder()
        builder.add_from_file('ui.glade')
        builder.connect_signals(self)
        self.builder = builder

        screen = Gdk.Screen.get_default()
        provider = Gtk.CssProvider()
        provider.load_from_path('./scanner.css')
        Gtk.StyleContext.add_provider_for_screen(
            screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        settings = Gtk.Settings.get_for_screen(screen)
        settings.set_property('gtk-font-name', '微軟正黑體')

    def do_activate(self):
        window = self.get('app_window')
        window.show()
        self.window = window

        try:
            # use cred. saved locally
            with open(G_TOKEN_SAVE_PATH, 'r') as f:
                self._entryCode = f.read().strip()
            queryPing(self._entryCode, self.cbLoadClientInfo)

        except OSError as err:
            # ask to login
            loginDialog = self.get('login_dialog')
            response = loginDialog.run()
            if response <= 0:  # destroy = -4
                exit(0)
            loginDialog.close()

        timerThread = startHealthCheck(app)

        self._generalStatusCtxId = (self.get('general_status')
                                        .get_context_id('general'))
        self.setStuidEntryEditability(False)
        self.tryInitCardReader()

    # custom utility functions

    def get(self, name):
        return self.builder.get_object(name)

    def _updateStatus(self, text):
        self.get('general_status').push(self._generalStatusCtxId, text)

    # aux. functions / callbacks

    def cbLoadClientInfo(self, _, err, resp):
        try:
            if err:
                print(err)

            data = resp.json()
            if data['ok']:
                self._clientInfo = data['client']
            else:
                self._clientInfo = {}
            GLib.idle_add(self.updateClientInfo)
        except Exception as err:
            print('error in cbLoadClientInfo:', err)

    def cbLoadVoterInfo(self, _, err, resp):
        try:
            def recoverUI():
                self.get('entry_cardid').set_sensitive(True)
                self.get('button_start_auth').set_sensitive(True)

            if err:
                GLib.idle_add(self.get('status').set_text, '連線逾時')
                GLib.idle_add(recoverUI)
                return

            canVote = False
            data = resp.json()
            if data['ok']:
                if data['can_vote']:
                    voterInfo = GC_VOTER_INFO_CAN_VOTE
                    canVote = True
                    self._tx = data['tx']
                else:
                    voterInfo = GC_VOTER_INFO_CANNOT_VOTE
                voterInfo = voterInfo.format(
                    r=data['result'],
                    mod=getModifier(data['result']['college']),
                    msg=data['msg'])
            else:
                voterInfo = GC_VOTER_INFO_ERROR
                voterInfo = voterInfo.format(data['msg'])

            GLib.idle_add(recoverUI)
            GLib.idle_add(self.updateVoterInfo, canVote, voterInfo)
        except Exception as err:
            print('error in cbLoadVoterInfo:', err)

    def cbLoadCommitResult(self, _, err, resp):
        try:
            def recoverUI():
                self.get('button_commit').set_sensitive(True)
                self.get('button_forgive').set_sensitive(True)
            if err:
                GLib.idle_add(self._updateStatus, '領票失敗，請回報選務中心')
                GLib.idle_add(recoverUI)
                return

            data = resp.json()
            GLib.idle_add(self.updateCommitResult, data)
            GLib.idle_add(recoverUI)
        except Exception as err:
            print('error in cbLoadCommitResult:', err)

    def updateClientInfo(self):
        # set client name based on client info received
        text = '票點：' + self._clientInfo.get('name', '??')
        self.get('client_name').set_text(text)

    def setStuidEntryEditability(self, yes):
        inst = self.get('entry_cardid')
        inst.set_editable(yes)
        if yes:
            inst.set_icon_from_icon_name(
                Gtk.EntryIconPosition.PRIMARY, 'gtk-edit')
        else:
            inst.set_icon_from_icon_name(
                Gtk.EntryIconPosition.PRIMARY, 'emblem-readonly')

    def switchAuthMode(self, isAuthByCard):
        ctxB1 = self.get('button_scan_card').get_style_context()
        ctxB2 = self.get('button_manual_input').get_style_context()
        if isAuthByCard is None:
            # set back to initial state
            ctxB1.remove_class('active')
            ctxB2.remove_class('active')
            self.setStuidEntryEditability(False)
        elif isAuthByCard:
            ctxB1.add_class('active')
            ctxB2.remove_class('active')
            self.setStuidEntryEditability(False)
        else:
            ctxB1.remove_class('active')
            ctxB2.add_class('active')
            self.setStuidEntryEditability(True)
        self.get('entry_cardid').set_text('')
        self.get('entry_cardid').set_sensitive(True)
        self.get('status').set_text('')

    def tryInitCardReader(self):
        statusIcon = self.get('client_status')
        try:
            self.cardReader = CardReader()
        except RuntimeError:
            statusIcon.set_tooltip_markup('找不到讀卡機，請檢查是否妥善連接')
        except Exception as err:
            # discard the object QQ
            self.cardReader = None
            statusIcon.set_tooltip_markup('讀卡機初始化失敗，請關閉程式後再試一次')
            print('Card reader general failure', err)

        iconName = 'emblem-default'
        if self.cardReader is None:
            iconName = 'emblem-important'
        self.get('client_status').set_from_icon_name(iconName, -1)

    def updateVoterInfo(self, yes, info):
        self.get('voter_info').set_markup(info)
        self.get('button_commit').set_sensitive(yes)
        stack = self.get('view_stack')
        stack.set_visible_child(stack.get_children()[1])

    def updateCommitResult(self, data):
        if data['ok']:
            msgbox = Gtk.MessageDialog(self.window, Gtk.DialogFlags.MODAL,
                     Gtk.MessageType.INFO, Gtk.ButtonsType.OK,
                     '領票程序結束 (成功)')
            msgbox.format_secondary_text('真是謝天謝地 <(_ _)>')
            self._updateStatus('領票程序完成！')
        else:
            msgbox = Gtk.MessageDialog(self.window, Gtk.DialogFlags.MODAL,
                     Gtk.MessageType.ERROR, Gtk.ButtonsType.OK,
                     '領票失敗，請重新驗證')
            msgbox.format_secondary_text('{}\n若持續發生，請回報選務中心'.format(data['msg']))
            self._updateStatus('領票程序結束 (失敗)')

        msgbox.run()
        msgbox.close()

        self.onForgive(None)

    # event handlers

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

        def loginCallback(sess, err, resp):
            GLib.idle_add(dialog.set_sensitive, True)

            try:
                data = resp.json()
                print(data)
            except:
                GLib.idle_add(makeMsgbox,
                    '未預期的錯誤狀況', '請將以下文字回報選務中心：\n{}'.format(resp.text))
                return

            if data['ok']:
                self._clientInfo = data['client']
                self._entryCode = entryCode
                GLib.idle_add(self.updateClientInfo)
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
        self.switchAuthMode(True)
        if self.cardReader is None:
            self.tryInitCardReader()

        reader = self.cardReader
        if reader is None:
            self.get('status').set_text('讀卡失敗 QAQ')
            return

        try:
            data = reader.readCard()
        except CardReaderException as err:
            self._updateStatus(err.__repr__())
            self.get('status').set_text('讀卡失敗 QAQ')
            raise

        reader.beep(15)

        text = data.value.decode('utf-8')
        cardId, cardSerial = text[:9], text[9:11].strip()

        self._card_sec = str(reader.last_snr) + '|' + repr(data.raw)
        self.get('entry_cardid').set_text(cardId)
        self._card_serial = cardSerial

    def onStartBypass(self, *args):
        self.switchAuthMode(False)
        self.get('entry_cardid').grab_focus()

        self._card_serial = None

    def getVoterInfo(self, *args):
        cardId = self.get('entry_cardid').get_text()
        cardSerial = self._card_serial

        if not len(cardId):
            self.get('status').set_text('學號欄位為空')
            return

        self.get('status').set_text('驗證身份中')
        self.get('entry_cardid').set_sensitive(False)
        self.get('button_start_auth').set_sensitive(False)

        reqObj = {
            'token': self._entryCode,
            'stuid': cardId,
            'card_sec': self._card_sec
        }
        if cardSerial is None:
            reqObj['bypass_serial'] = '1'
        else:
            reqObj['serial'] = cardSerial

        req = queryQuery(reqObj, self.cbLoadVoterInfo, timeout=10)

    def onForgive(self, *args):
        stack = self.get('view_stack')
        stack.set_visible_child(stack.get_children()[0])
        self.switchAuthMode(None)

    def onCommit(self, *args):
        tx = self._tx
        self._tx = None

        self._updateStatus('送出領票請求...')
        self.get('button_commit').set_sensitive(False)
        self.get('button_forgive').set_sensitive(False)

        queryCommit((self._entryCode, tx), self.cbLoadCommitResult, timeout=20)


if __name__ == '__main__':
    import signal
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    app = Application()
    app.run(sys.argv)

    Gtk.main()
    # if the main loop exits (i.e. closing the main window),
    # give up all other threads
    exit(0)
