import os

import requests
import xml.etree.ElementTree as ET

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QLineEdit, QPushButton, QVBoxLayout, QMessageBox, QLabel
from qgis.PyQt.QtGui import QIcon
from qgis.core import QgsApplication, QgsAuthMethodConfig

KEY_NAME = "geocatbridgenterprise" 
verifyUrl = "https://my.geocat.net/modules/servers/licensing/verify.php"

def verifyLicenseKey(key):
    try:
        params = {"licensekey": key}
        ret = requests.post(verifyUrl, data=params)   
        root = ET.fromstring("<root>{}</root>".format(ret.text))
        print(ret.text)        
        statusNode = root.find("status")
        if statusNode is None:
            return None, "Wrong server response"
        status = statusNode.text        
        if status == "Active":
            name = root.find("registeredname").text
            return name, None
        elif status ==  "Invalid":
            return None, "License key is Invalid"
        elif status ==  "Expired":
            return None, "License key is Expired"
        elif status ==  "Suspended":
            return None, "License key is Suspended"        
        else:
            return None, "Invalid Response"
    except:
        return None, "Error when checking license validity"


def iconPath(icon):
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "icons", icon)

KEY_ICON = QIcon(iconPath("key.png"))
WIDGET, BASE = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'licensekeydialog.ui'))

class LoginDialog(BASE, WIDGET):
    def __init__(self, parent=None):
        super(LoginDialog, self).__init__(parent)
        self.setupUi(self)
        self.registeredTo = None
        self.buttonLogin.clicked.connect(self.handleLogin)
        pixmap = KEY_ICON.pixmap(KEY_ICON.availableSizes()[0]);
        self.labelLogo.setPixmap(pixmap)

    def handleLogin(self):
        key = self.txtLicenseKey.text()
        username, error = verifyLicenseKey(key)
        if error is None:
            authMgr = QgsApplication.authManager()        
            config = QgsAuthMethodConfig()
            config.setId(KEY_NAME)
            config.setName("GeoCat Bridge Enterprise key")
            config.setMethod("Basic")        
            config.setConfig("username", "")
            config.setConfig("password", "")
            config.setConfig("licensekey", key)
            authMgr.storeAuthenticationConfig(config)
            self.registeredTo = username
            self.accept()
        else:
            QMessageBox.warning(self, 'Error', error)