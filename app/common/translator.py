# coding:utf-8
import json
import traceback
from loguru import logger
from typing import List, Tuple, Optional, Union, Any
from PyQt5.QtCore import QLocale, pyqtProperty, QFile, QTextStream, QIODevice, QDir, QJsonDocument
from PyQt5.QtWidgets import QApplication

class JsonTranslator:

    _lang: QLocale = None
    _trDict: dict = None
    _enTrDict: dict = None
    _basePath: str = None

    def __init__(self, _lang: QLocale, _basePath: str):
        self._lang = _lang
        self._basePath = _basePath
        self.reload()

    def getLang(self):
        return self._lang

    def setLang(self, _lang: QLocale):
        self._lang = _lang

    lang = pyqtProperty(QLocale, getLang, setLang)

    def getBasePath(self):
        return self._basePath

    def setBasePath(self, _basePath: str):
        self._basePath = _basePath

    basePath = pyqtProperty(str, getBasePath, setBasePath)

    def reload(self):
        lang_file_path = QFile(f'{self._basePath}/{self._lang.name().lower()}.json')
        en_file_path = QFile(f'{self._basePath}/en_us.json')

        # check if the file exists
        lang_file_exists = QFile.exists(lang_file_path.fileName())
        en_file_exists = QFile.exists(en_file_path.fileName())

        if lang_file_exists and en_file_exists:
            # read the contents of the language file
            lang_file = QFile(lang_file_path.fileName())
            if lang_file.open(QIODevice.ReadOnly | QIODevice.Text):
                stream = QTextStream(lang_file)
                stream.setCodec("UTF-8")
                content = stream.readAll()
                self._trDict = json.loads(content)
                lang_file.close()

            en_file = QFile(en_file_path.fileName())
            if en_file.open(QIODevice.ReadOnly | QIODevice.Text):
                stream = QTextStream(en_file)
                stream.setCodec("UTF-8")
                content = stream.readAll()
                self._enTrDict = json.loads(content)
                en_file.close()

        elif en_file_exists:
            # only read the contents of the english language file
            en_file = QFile(en_file_path.fileName())
            if en_file.open(QIODevice.ReadOnly | QIODevice.Text):
                stream = QTextStream(en_file)
                stream.setCodec("UTF-8")
                content = stream.readAll()
                data = json.loads(content)
                self._trDict = data
                self._enTrDict = data
                en_file.close()

        else:
            self._trDict = {}
            self._enTrDict = {}

    def tr(self, i18nKeyName: str, formatList: Union[tuple, Any] = ()) -> str:
        assert isinstance(i18nKeyName, str), type(i18nKeyName)

        try:
            res = self._trDict[i18nKeyName]
        except:
            try:
                res = self._enTrDict[i18nKeyName]
            except:
                res = i18nKeyName
        try:
            if formatList:
                res %= formatList
        except Exception as e:
            if not str(e):
                res = repr(type(e))[8:-2]
            else:
                res = f'{repr(type(e))[8:-2]}: {e!s}'
        return res

class JsonTranslatorManager:
    _translatorsList: Tuple[JsonTranslator] = ()
    def __init__(self, *_translatorsList: JsonTranslator):
        self._translatorsList = _translatorsList
        QApplication.instance().trManager = self

    def tr(self, i18nKeyName: str, formatList: tuple = ()) -> str:
        for i in self._translatorsList[::-1]:
            if (res := i.tr(i18nKeyName, formatList)) != i18nKeyName:
                return res
        return i18nKeyName

    def addTranslator(self, *_translator: JsonTranslator):
        self._translatorsList += _translator

    def removeTranslator(self, *_translator: JsonTranslator):
        self._translatorsList -= _translator

    def translators(self) -> Tuple[JsonTranslator]:
        return self._translatorsList

def translate(i18nKeyName: str, formatList: Union[Tuple, Any] = ()) -> str:
    if QApplication.instance() and hasattr(QApplication.instance(), 'trManager'):
        return QApplication.instance().trManager.tr(i18nKeyName, formatList)
    else:
        return i18nKeyName

# the built-in file reader version
# def getTranslateNamesList(_basePath: str) -> Optional[List[str]]:
#     if not _basePath: return
#     try:
#         res = []
#         for file in os.listdir(_basePath):
#             if not file.endswith(".json"): continue
#             if d := json.load(open(f"{_basePath}/{file}")):
#                 res.append(f'{d.get("language.name")}({d.get("language.region")})')
#         return res
#     except Exception as e:
#         return [f'{repr(type(e))[8:-2]}: {e!s}']

def getTranslateNamesList(_basePath: str) -> Optional[List[str]]:
    if not _basePath:
        return None

    try:
        res = []
        dir = QDir(_basePath)

        # get files list
        files = dir.entryList(QDir.Files)

        for file_name in files:
            if not file_name.endswith(".json"):
                continue

            file_path = dir.filePath(file_name)
            file = QFile(file_path)

            if not file.open(QIODevice.ReadOnly | QIODevice.Text):
                continue

            # read the contents of the file
            content = file.readAll().data().decode('utf-8')
            file.close()

            if not content:
                continue

            d = json.loads(content)

            if d:
                language_name = d.get("language.name", "")
                language_region = d.get("language.region", "")
                if language_name or language_region:
                    res.append(f'{language_name} ({language_region})')

        return res

    except BaseException as e:
        logger.error(translate(
            'Log.Event.Failed',
            (translate('Log.Action.Application'), traceback.format_exc()),
        ))
        return [f'{repr(type(e))[8:-2]}: {e!s}']

# def getTranslateQLocalesList(_basePath: str) -> Optional[List[QLocale]]:
#     if not _basePath: return
#     try:
#         res = []
#         for file in os.listdir(_basePath):
#             if not file.endswith(".json"): continue
#             res.append(QLocale(file[:-5]))
#     except Exception as e:
#         print(f'{repr(type(e))[9:-2]}: {e!s}')


def getTranslateQLocalesList(_basePath: str) -> Optional[List[QLocale]]:
    if not _basePath:
        return None

    try:
        res = []
        dir_obj = QDir(_basePath)

        json_files = dir_obj.entryList(["*.json"], QDir.Files, QDir.Name)

        for file in json_files:
            locale_name = file[:-5]
            res.append(QLocale(locale_name))

        return res
    except BaseException as e:
        logger.error(translate(
            'Log.Event.Failed',
            (translate('Log.Action.Application'), traceback.format_exc()),
        ))
