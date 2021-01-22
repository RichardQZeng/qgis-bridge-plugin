import fnmatch
import html
import os
import re
import shutil

root = os.path.dirname(os.path.dirname(__file__))
SRC_DIR = os.path.join(root, "geocatbridge")
DST_DIR = os.path.join(root, "geocatbridgeenterprise")
DOCS_SRC_DIR = os.path.join(root, "docs")
DOCS_DST_DIR = os.path.join(root, "docsenterprise")


class ReplaceAction:

    def __init__(self, old, new, use_regex=False):
        self.old = old
        self.new = new
        self._rex = use_regex

    def change(self, text):
        if self._rex:
            text = re.sub(self.old, self.new, text)
        else:
            text = text.replace(self.old, self.new)
        return text

    def run(self):
        for fpath in self.files():
            with open(fpath) as f:
                text = f.read()
            text = self.change(text)
            with open(fpath, "w") as f:
                f.write(text)

    @staticmethod
    def files():
        files = []
        for folder in [DST_DIR, DOCS_DST_DIR]:
            for root_, dirnames, filenames in os.walk(folder):
                for ext in ["*.txt", "*.rst", "*.py", "*.ui", "*.html", "*.ui"]:
                    for filename in fnmatch.filter(filenames, ext):
                        files.append(os.path.join(root_, filename))
        return files


class SetIsEnterpriseAsTrueAction:

    @staticmethod
    def run():
        code = "def isEnterprise():\n\treturn True"
        filepath = os.path.join(DST_DIR, "utils", "enterprise.py")
        with open(filepath, "w") as f:
            f.write(code)


brandingActions = [
    ReplaceAction(r'(\s)Bridge(\W)(?!Enterprise)', r'\1Bridge Enterprise\2', True),
    ReplaceAction("geocatbridge.", "geocatbridgeenterprise."),
    ReplaceAction("https://github.com/GeoCat/qgis-bridge-plugin/issues",
                  html.escape("https://my.geocat.net/submitticket.php?step=2&deptid=1&subject=Bridge")),
    SetIsEnterpriseAsTrueAction()
]


def doBranding():
    if os.path.exists(DST_DIR):
        shutil.rmtree(DST_DIR)
    shutil.copytree(SRC_DIR, DST_DIR)

    if os.path.exists(DOCS_DST_DIR):
        shutil.rmtree(DOCS_DST_DIR)
    shutil.copytree(DOCS_SRC_DIR, DOCS_DST_DIR)

    for action in brandingActions:
        action.run()
