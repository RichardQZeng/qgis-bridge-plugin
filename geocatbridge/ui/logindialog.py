import requests
import socket

from qgis.PyQt.QtWidgets import QDialog, QLineEdit, QPushButton, QVBoxLayout, QMessageBox, QLabel
from qgis.core import QgsApplication, QgsAuthMethodConfig

KEY_NAME = "geocatbridgenterprise" 
verifyUrl = "https://my.geocat.net/modules/servers/licensing/verify.php"

def verifyLicenseKey(key):
    params = {"license-key": key,                
                "ip": hostIp}
    ret = requests.post(verifyUrl, data=params)
    #TODO
    return "Mister Username"

def hostIp():
    try: 
        name = socket.gethostname()
        ip = socket.gethostbyname(host_name)
        return ip
    except: 
        return ""

class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super(LoginDialog, self).__init__(parent)
        self.registeredTo = None
        self.setWindowTitle("GeoCat Bridge Enterprise")
        self.label = QLabel("Enter your Bridge Enterprise licence key")
        self.textKey = QLineEdit(self)
        self.buttonLogin = QPushButton('Login', self)
        self.buttonLogin.clicked.connect(self.handleLogin)
        layout = QVBoxLayout(self)
        layout.addWidget(self.label)
        layout.addWidget(self.textKey)        
        layout.addWidget(self.buttonLogin)

    def handleLogin(self):
        key = self.textKey.text()
        username = verifyLicenseKey(key)
        if username:
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
            QMessageBox.warning(self, 'Error', 'Invalid license key')