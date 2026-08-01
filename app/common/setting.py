# coding: utf-8
import sys
from datetime import datetime
from pathlib import Path
from PyQt5.QtCore import QStandardPaths

# change DEBUG to False if you want to compile the code to exe
DEBUG = "__compiled__" not in globals()

YEAR = 2026
AUTHOR = "XiaoshuDeXiaowo"
VERSION = "0.0.1"
APP_NAME = "GitHub NetDisk"
APP_ID = "GitHub-NetDisk"
# Fill these values after the GitHub App has been registered.  Only the
# OAuth client id and public app slug belong in a desktop build.  Never ship
# the GitHub App client secret or a private key with the application.
GITHUB_APP_ID = "4420492"
GITHUB_APP_CLIENT_ID = "Iv23liBKEF8tukx5CajW"
GITHUB_APP_SLUG = "gh-netdisk"
HELP_URL = "https://github-netdisk.top/"
REPO_URL = "https://github.com/XiaoshuDeXiaowo/GitHub-NetDisk"
RELEASE_URL = f"{REPO_URL}/releases"
AUTHOR_URL = "https://github.com/XiaoshuDeXiaowo"
LICENSE_URL = f"{REPO_URL}/blob/main/LICENSE"
FEEDBACK_URL = "https://github.com/XiaoshuDeXiaowo/GitHub-NetDisk/issues"
DOC_URL = "https://github-netdisk.top/"


def localizedWebsiteUrl(locale_name=''):
    """Return the documentation root matching the current UI language."""
    locale = str(locale_name or '').lower().replace('-', '_')
    if locale.startswith(('zh_cn', 'zh_sg')):
        return 'https://github-netdisk.top/zh/'
    if locale.startswith(('zh_hk', 'zh_tw', 'zh_mo')):
        return 'https://github-netdisk.top/zh-hk/'
    return 'https://github-netdisk.top/'

APP_FOLDER = Path('config').parent.absolute()

if sys.platform == "win32" and not DEBUG:
    APP_FOLDER = Path(QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)) / APP_ID

CONFIG_FOLDER = APP_FOLDER / "config"
CONFIG_FOLDER.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = CONFIG_FOLDER / "config.json"
TRANSFER_TASK_FILE = CONFIG_FOLDER / "transfer_tasks.json"

LOG_FOLDER = APP_FOLDER / "logs"
LOG_FOLDER.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_FOLDER / f"Log_{datetime.now():%Y%m%d_%H%M%S}.log"

if sys.platform == "win32":
    EXE_SUFFIX = ".exe"
else:
    EXE_SUFFIX = ""

# Static snapshot of ghproxy-next's public node list:
# https://github.com/hubporg/ghproxy-next/raw/refs/heads/main/components/nodes.ts
GITHUB_MIRRORS = [
    "gh.dpik.top",
    "github.tbap.top",
    "ghfile.geekertao.top",
    "ghproxy.net",
    "gh-proxy.com",
    "gh-proxy.net",
    "cdn.gh-proxy.com",
    "github.dpik.top",
    "j.1lin.dpdns.org",
    "github.starrlzy.cn",
    "github-proxy.memory-echoes.cn",
    "git.yylx.win",
    "ghm.078465.xyz",
    "gh.927223.xyz",
    "ghf.无名氏.top",
    "gh.felicity.ac.cn",
    "gh.bugdey.us.kg",
    "cdn.akaere.online",
    "jiashu.1win.eu.org",
    "tvv.tw",
    "j.1win.ggff.net",
    "gitproxy.127731.xyz",
    "gh.inkchills.cn",
    "gh.catmak.name",
    "gh.b52m.cn",
    "down.mxw.xx.kg",
    "down.mxw.qzz.io",
    "github.mxw.qzz.io",
    "gh.acmsz.top",
    "gh.jjj.gv.uy",
    "slink.ltd",
    "github.tmby.shop",
    "ghpr.cc",
    "gh.tryxd.cn",
    "gitproxy.click",
    "github.chenc.dev",
    "gh.ddlc.top",
    "gitproxy.mrhjx.cn",
    "gh.sixyin.com",
    "gh.monlor.com",
    "ghpxy.hwinzniej.top",
    "git.669966.xyz",
    "ghfast.top",
    "gh.jasonzeng.dev",
    "github.geekery.cn",
    "gp.zkitefly.eu.org",
    "fastgit.cc",
    "ghproxy.1888866.xyz",
    "ghp.arslantu.xyz",
    "github.ednovas.xyz",
    "ghproxy.imciel.com",
    "ghproxy.cxkpro.top",
    "github.xxlab.tech",
    "gh.idayer.com",
    "free.cn.eu.org",
    "gh.chjina.com",
    "ghp.keleyaa.com",
    "proxy.yaoyaoling.net",
    "ghproxy.monkeyray.net",
    "gh.noki.icu",
    "g.blfrp.cn",
    "githubdog.com",
    "gh.meali.top",
    "777.z321.cc.cd",
    "gg.z321.cc.cd",
    "g.z321.cc.cd",
    "js.jiangss.shop",
    "gap.andyjin.website",
    "gh.my-website.ccwu.cc",
    "github.ikgy.top",
    "gh.07150721.xyz",
    "cfgh.ikgy.top",
    "xsadwsd.kdns.fr",
    "gh.ruan.dpdns.org",
]

