import time
import json
import re
import os
import sys
import random
import threading
import subprocess
import webbrowser
import urllib.parse
import winsound
import wave
import shutil
import queue
import ctypes
import ctypes.wintypes as wt
from collections import deque
from functools import lru_cache

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    HAS_PYCAW = True
except ImportError:
    HAS_PYCAW = False

if sys.version_info[:2] != (3, 12):
    print("[WARN] Рекомендован Python 3.12. Сейчас: %s" % sys.version.split()[0])

# ============================================================
# TOAST-УВЕДОМЛЕНИЯ (левый нижний угол, отдельный поток)
# ============================================================
class ToastNotifier:
    def __init__(self):
        self._queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def show(self, title, message, duration=2.5, color="#1e1e1e", text_color="#ffffff"):
        self._queue.put((title, message, duration, color, text_color))

    def _run(self):
        try:
            import tkinter as tk
        except Exception:
            return
        while True:
            try:
                title, message, duration, color, text_color = self._queue.get(timeout=1.0)
            except queue.Empty:
                continue
            try:
                root = tk.Tk()
                root.withdraw()
                win = tk.Toplevel(root)
                win.overrideredirect(True)
                win.attributes("-topmost", True)
                win.attributes("-alpha", 0.92)
                win.configure(bg=color)
                sw = root.winfo_screenwidth()
                sh = root.winfo_screenheight()
                w_w, w_h = 320, 70
                win.geometry("%dx%d+%d+%d" % (w_w, w_h, 20, sh - w_h - 60))
                tk.Label(win, text=title, font=("Segoe UI", 9, "bold"),
                         bg=color, fg="#00bfff", anchor="w").pack(fill="x", padx=10, pady=(8, 0))
                tk.Label(win, text=message, font=("Segoe UI", 10),
                         bg=color, fg=text_color, anchor="w", justify="left").pack(
                    fill="both", expand=True, padx=10, pady=(2, 8))
                win.after(int(duration * 1000), lambda: (win.destroy(), root.destroy()))
                root.mainloop()
            except Exception as e:
                print("[TOAST ERR]", e)

toast = ToastNotifier()

# ============================================================
# ПУТИ (относительные: проект переносим на любой диск)
# ============================================================
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIO_BASE = os.path.join(_BASE_DIR, "audio")
FUNCTION_DIRS = [os.path.join(AUDIO_BASE, "dialoge")]
WAKE_DIR = os.path.join(AUDIO_BASE, "yes_sir")
FAIL_DIR = os.path.join(AUDIO_BASE, "fail")
WAKE_SOUND_FILE = os.path.join(AUDIO_BASE, "yes_sir", "yes_sir.wav")
AUDIO_EXT = (".wav",)

MODEL_PATH_VOSK = os.path.join(_BASE_DIR, "vosk-model-small-ru-0.22")
SAMPLE_RATE = 16000
BLOCK_SIZE = 1280
WAKE_COOLDOWN = 1.5
TIMEOUT_LISTEN = 6.0

# KWS-словарь пробуждения: БЕЗ [unk] и БЕЗ английских слов
WAKE_KWS_GRAMMAR = '["джарвис", "джервис"]'
WAKE_KWS_WORDS = {"джарвис", "джервис"}

SELF_MUTE_PAD = 1.2
SELF_MUTE_MIN = 1.0
SELF_MUTE_MAX = 4.0

PENDING_BROWSER_TTL = 8.0
CLOSE_WAIT_TIMEOUT = 3.0
CLOSE_BROWSER_WAIT_TIMEOUT = 2.0
CLOSE_POLL = 0.2
CLOSE_QUEUE_DELAY = 0.25
FUZZY_MIN_LEN = 3
MATCH_ACCEPT = 0.72
BARE_MATCH_ACCEPT = 0.85
AMBIGUITY_MARGIN = 0.05

YANDEX_MUSIC_EXE = "яндекс музыка.exe"

# Голосовые числа -> цифры
NUM_WORDS = {
    "один": "1", "два": "2", "три": "3", "четыре": "4", "пять": "5",
    "шесть": "6", "семь": "7", "восемь": "8", "девять": "9", "десять": "10",
    "одиннадцать": "11", "двенадцать": "12", "тринадцать": "13",
    "четырнадцать": "14", "пятнадцать": "15", "шестнадцать": "16",
    "семнадцать": "17", "восемнадцать": "18", "девятнадцать": "19",
    "двадцать": "20", "тридцать": "30", "сорок": "40", "пятьдесят": "50",
    "шестьдесят": "60", "семьдесят": "70", "восемьдесят": "80",
    "девяносто": "90", "сто": "100", "полста": "50",
}

# ============================================================
# САЙТЫ / ПРИЛОЖЕНИЯ
# ============================================================
TELEGRAM_EXE = os.path.join(os.environ.get("APPDATA", ""), "Telegram Desktop", "Telegram.exe")

PROGRAMS_RAW = [
    (["стим", "steam"], "Steam"),
    (["дискорд", "discord"], "Discord"),
    (["спотифай", "spotify"], "Spotify"),
    (["телеграм", "тг", "telegram", "tg", "телега", "тэга", "тега", "тэ га"], "Telegram"),
    (["яндекс музыка", "яндекс музыке", "яндекс музыку", "яму", "yandex music"], "Яндекс Музыка"),
    (["яндекс браузер", "яндекс браузере", "yandex browser"], "Yandex Browser"),
]

PROGRAM_PROCESSES = {
    "Yandex Browser": ["browser.exe"],
    "Яндекс Музыка": ["яндекс музыка.exe"],
}

LAUNCH_COMMANDS = {
    "Steam": [["steam.exe"], [r"C:\Program Files (x86)\Steam\steam.exe"], [r"C:\Program Files\Steam\steam.exe"]],
    "Discord": [[r"%LOCALAPPDATA%\Discord\Update.exe", "--processStart", "Discord.exe"], ["Discord.exe"]],
    "Spotify": [[r"%APPDATA%\Spotify\Spotify.exe"], [r"%LOCALAPPDATA%\Spotify\Spotify.exe"], ["Spotify.exe"]],
    "Telegram": [[TELEGRAM_EXE]],
    "Яндекс Музыка": [[r"C:\Users\egire\AppData\Local\Programs\YandexMusicMod\Яндекс Музыка.exe"]],
    "Yandex Browser": [[r"%LOCALAPPDATA%\Yandex\YandexBrowser\Application\browser.exe"], ["browser.exe"]],
}

SITES_RAW = [
    (["вк видео", "видео вк", "vk video", "vkvideo", "вквидео", "вака видео", "вэка видео", "вэ ка видео"], "https://vkvideo.ru", "VK Видео"),
    (["вк", "vk", "vkontakte", "вконтакте", "вака", "вэка", "вэ ка", "века"], "https://vk.com", "VK"),
    (["икс", "x", "твиттер", "twitter", "экс"], "https://x.com/", "X"),
    (["гугл", "google"], "https://www.google.com", "Google"),
    (["яндекс", "yandex"], "https://ya.ru", "Яндекс"),
    (["ютуб", "youtube"], "https://www.youtube.com", "YouTube"),
    (["твич", "twitch"], "https://www.twitch.tv", "Twitch"),
    (["модсинт", "modrinth"], "https://modrinth.com", "Modrinth"),
    (["гитхаб", "github"], "https://github.com", "GitHub"),
    (["вики", "wikipedia", "википедия"], "https://ru.wikipedia.org", "Wikipedia"),
    (["стим сайт", "steam site", "store steam"], "https://store.steampowered.com", "Steam Store"),
    (["браузер", "browser", "хром", "chrome", "edge", "фаерфокс", "firefox"], "https://www.google.com", "Браузер/Google"),
]

BROWSER_PROCS = ["chrome.exe", "msedge.exe", "firefox.exe", "opera.exe", "brave.exe", "browser.exe", "yandex_browser.exe"]

APP_VOLUME_ALIASES = {
    "дискорд": ["discord.exe"], "discord": ["discord.exe"],
    "браузер": ["chrome.exe", "msedge.exe", "browser.exe", "firefox.exe"],
    "хром": ["chrome.exe"], "chrome": ["chrome.exe"], "edge": ["msedge.exe"],
    "телеграм": ["telegram.exe"], "тг": ["telegram.exe"], "telegram": ["telegram.exe"],
    "стим": ["steam.exe"], "steam": ["steam.exe"],
    "спотифай": ["spotify.exe"], "spotify": ["spotify.exe"],
    "яндекс музыка": ["яндекс музыка.exe"], "яму": ["яндекс музыка.exe"],
}

# ============================================================
# ПОЛЬЗОВАТЕЛЬСКИЙ CONFIG (config.json)
# ============================================================
CONFIG_PATH = os.path.join(_BASE_DIR, "config.json")
_DEFAULT_CONFIG = {
    "programs": [{"label": "Блокнот", "aliases": ["блокнот", "нотпад", "notepad"], "processes": ["notepad.exe"], "launch": [["notepad.exe"]]}],
    "sites": [{"label": "Хабр", "aliases": ["хабр", "habr"], "url": "https://habr.com"}]
}

def _load_config():
    if not os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(_DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
            print("Jarvis: создан config.json — добавляй туда свои программы и сайты.")
        except Exception as e:
            print("[WARN] не удалось создать config.json:", e)
        return _DEFAULT_CONFIG
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print("[WARN] config.json повреждён, использую встроенный список:", e)
        return {}

# ============================================================
# ЛЕКСИКА И НОРМАЛИЗАЦИЯ
# ============================================================
WAKE_WORDS = {"джарвис", "jarvis", "хей", "хэй", "эй", "hey", "heyjarvis"}
FILLER_WORDS = {"мне", "пожалуйста", "теперь", "сейчас", "а", "ну", "давай", "хочу", "надо", "пожалуй", "please", "вот", "прям", "очень", "да", "нет", "не", "ни", "бы", "же", "ли", "б", "жь", "будь", "это", "этот", "эта", "эти", "эту", "этого", "этой", "тем", "том", "то", "те", "той", "того", "та", "тот", "такая", "такой", "такие", "и", "или", "но", "даже", "лишь", "именно", "просто", "всё", "все", "ничего", "что", "чтобы", "как", "где", "когда", "почему", "зачем"}
PREPOSITION_WORDS = {"в", "на", "по", "у", "к", "о", "об", "с", "со", "из", "за", "над", "под", "для", "про", "при", "без", "через", "около"}
BROWSER_WORDS = {"браузер", "browser", "хром", "chrome", "edge", "фаерфокс", "firefox", "интернет"}
BROWSER_STEMS = ("брауз", "chrom", "firefo", "интернет")
OPEN_WORDS = {"открой", "открыть", "открывай", "открыто", "открыв", "запусти", "запустить", "включи", "включить", "open", "launch", "start"}
OPEN_STEMS = ("откр", "запу", "включ", "open", "launch", "start")
CLOSE_WORDS = {"закрой", "закрыть", "закрывай", "закрыто", "закрыв", "выключи", "выключить", "останови", "остановить", "kill", "close"}
CLOSE_STEMS = ("закр", "выключ", "останов", "kill", "close")
SEARCH_WORDS = {"найди", "поищи", "поиск", "ищи", "find", "search", "погугли", "загугли"}
SEARCH_STEMS = ("найди", "поищи", "поиск", "ищи", "find", "search", "погугл", "загугл")
EXIT_WORDS = {"выход", "exit", "quit", "заверши", "завершить"}
STOP_LISTEN_WORDS = {"стоп", "хватит", "закройся", "перестань"}
SLEEP_WORDS = {"пока", "спи", "sleep", "бай", "прощай"}
SLEEP_PHRASES = ["спокойной ночи", "до свидания", "увидимся", "good night"]
MINIMIZE_WORDS = {"сверни", "свернуть", "сворачивай", "минимизируй", "minimize", "hide"}
MINIMIZE_STEMS = ("сверн", "сверт", "минимиз", "minimiz")
RESTORE_WORDS = {"разверни", "развернуть", "восстанови", "покажи", "restore"}
RESTORE_STEMS = ("разверн", "восстанов", "покаж", "restor")

def _norm(s):
    s = str(s).lower().replace("ё", "е")
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

WAKE_TOKENS = {_norm(x) for x in WAKE_WORDS}
FILLER_TOKENS = {_norm(x) for x in FILLER_WORDS}
PREPOSITION_TOKENS = {_norm(x) for x in PREPOSITION_WORDS}
IGNORE_TOKENS = WAKE_TOKENS | FILLER_TOKENS | PREPOSITION_TOKENS
NON_MEANINGFUL = IGNORE_TOKENS
BROWSER_TOKENS = {_norm(x) for x in BROWSER_WORDS}
BROWSER_STEMS_NORM = tuple(_norm(x) for x in BROWSER_STEMS)
OPEN_TOKENS = {_norm(x) for x in OPEN_WORDS}
OPEN_STEMS_NORM = tuple(_norm(x) for x in OPEN_STEMS)
CLOSE_TOKENS = {_norm(x) for x in CLOSE_WORDS}
CLOSE_STEMS_NORM = tuple(_norm(x) for x in CLOSE_STEMS)
SEARCH_TOKENS = {_norm(x) for x in SEARCH_WORDS}
SEARCH_STEMS_NORM = tuple(_norm(x) for x in SEARCH_STEMS)
VERB_TOKENS = OPEN_TOKENS | CLOSE_TOKENS | SEARCH_TOKENS
VERB_STEMS_NORM = OPEN_STEMS_NORM + CLOSE_STEMS_NORM + SEARCH_STEMS_NORM
EXIT_TOKENS = {_norm(x) for x in EXIT_WORDS}
STOP_LISTEN_TOKENS = {_norm(x) for x in STOP_LISTEN_WORDS}
SLEEP_TOKENS = {_norm(x) for x in SLEEP_WORDS}
SLEEP_PHRASES_NORM = [_norm(x) for x in SLEEP_PHRASES]
MINIMIZE_TOKENS = {_norm(x) for x in MINIMIZE_WORDS}
MINIMIZE_STEMS_NORM = tuple(_norm(x) for x in MINIMIZE_STEMS)
RESTORE_TOKENS = {_norm(x) for x in RESTORE_WORDS}
RESTORE_STEMS_NORM = tuple(_norm(x) for x in RESTORE_STEMS)
ALL_WINDOWS_WORDS = {"все", "всё", "всех"}
ALL_WINDOWS_TOKENS = {_norm(x) for x in ALL_WINDOWS_WORDS}
SKIP_WINDOW_TITLES = {"program manager", "programmanager"}

def _has_meaningful(norm):
    for tok in _norm(norm).split():
        if len(tok) >= 3 and tok not in NON_MEANINGFUL:
            return True
    return False

def _words_to_digits(norm):
    out = norm
    for word, digit in NUM_WORDS.items():
        out = re.sub(r"\b%s\b" % re.escape(word), digit, out)
    return out

# ============================================================
# ДАМЕРАУ-ЛЕВЕНШТЕЙН И МАТЧЕР
# ============================================================
_SIMILAR_PAIRS = {("и", "й"), ("с", "ш"), ("з", "с"), ("б", "п"), ("в", "ф"), ("д", "т"), ("г", "к"), ("е", "и"), ("о", "а"), ("у", "ю"), ("ы", "и"), ("э", "е"), ("к", "х"), ("т", "д"), ("п", "б"), ("ф", "в"), ("ш", "ж"), ("ц", "ч")}
_RUSSIAN_VOWELS = set("аеёиоуыэюя")
_RUSSIAN_CONSONANTS = set("бвгджзйклмнпрстфхцчшщ")

def _subst_cost(a, b):
    if a == b: return 0.0
    if (a, b) in _SIMILAR_PAIRS or (b, a) in _SIMILAR_PAIRS: return 0.65
    if a in _RUSSIAN_VOWELS and b in _RUSSIAN_VOWELS: return 0.80
    if a in _RUSSIAN_CONSONANTS and b in _RUSSIAN_CONSONANTS: return 0.90
    return 1.0

@lru_cache(maxsize=8192)
def _dl_distance(a, b):
    if a == b: return 0.0
    la, lb = len(a), len(b)
    if la == 0: return float(lb)
    if lb == 0: return float(la)
    prev2 = None
    prev = [float(i) for i in range(lb + 1)]
    for i in range(1, la + 1):
        cur = [float(i)] + [0.0] * lb
        ca = a[i - 1]
        for j in range(1, lb + 1):
            cb = b[j - 1]
            cost = 0.0 if ca == cb else _subst_cost(ca, cb)
            cur[j] = min(prev[j] + 1.0, cur[j - 1] + 1.0, prev[j - 1] + cost)
            if i > 1 and j > 1 and ca == b[j - 2] and a[i - 2] == cb:
                cur[j] = min(cur[j], prev2[j - 2] + 1.0)
        prev2 = prev
        prev = cur
    return prev[lb]

def _ratio(a, b):
    if not a and not b: return 1.0
    d = _dl_distance(a, b)
    m = max(len(a), len(b))
    if m == 0: return 1.0
    return max(0.0, 1.0 - (d / float(m)))

ALIAS_INDEX = []
def _add_candidate(kind, label, aliases, payload):
    cand = {"kind": kind, "label": label, "payload": payload}
    for alias in aliases:
        n = _norm(alias)
        if not n: continue
        compact = n.replace(" ", "")
        ALIAS_INDEX.append({"cand": cand, "norm": n, "compact": compact, "tokens": n.split(), "len": len(compact)})
    return cand

for _aliases, _label in PROGRAMS_RAW:
    _add_candidate("app", _label, _aliases, {"processes": PROGRAM_PROCESSES.get(_label, [_label.lower() + ".exe"])})
for _aliases, _url, _label in SITES_RAW:
    _add_candidate("site", _label, _aliases, {"url": _url})

_USER_CFG = _load_config()
for _cp in _USER_CFG.get("programs", []):
    _lbl = _cp.get("label")
    if not _lbl: continue
    _procs = [p.lower() for p in _cp.get("processes", [_lbl.lower() + ".exe"])]
    _add_candidate("app", _lbl, _cp.get("aliases", [_lbl]), {"processes": _procs})
    if _cp.get("launch"): LAUNCH_COMMANDS[_lbl] = _cp["launch"]
for _cs in _USER_CFG.get("sites", []):
    _lbl = _cs.get("label")
    if not _lbl or not _cs.get("url"): continue
    _add_candidate("site", _lbl, _cs.get("aliases", [_lbl]), {"url": _cs["url"]})

ALIAS_INDEX.sort(key=lambda x: x["len"], reverse=True)

def _min_ratio_for_len(n):
    if n <= 3: return 0.80
    if n == 4: return 0.72
    return 0.65

def _score_against_alias(text_norm, text_compact, text_tokens, entry):
    alias_norm, alias_compact = entry["norm"], entry["compact"]
    if text_compact == alias_compact: return 1.00
    if text_norm == alias_norm: return 0.99
    if len(entry["tokens"]) == 1 and any(t == alias_norm for t in text_tokens): return 0.97
    if len(text_compact) >= 3 and len(alias_compact) >= 3:
        if alias_compact.endswith(text_compact) or text_compact.endswith(alias_compact):
            shared = min(len(text_compact), len(alias_compact))
            return 0.70 + 0.25 * (shared / float(max(len(text_compact), len(alias_compact))))
        if alias_compact in text_compact or text_compact in alias_compact:
            return max(0.86, _ratio(text_compact, alias_compact) * 0.95)
    if len(alias_compact) < FUZZY_MIN_LEN or len(text_compact) < FUZZY_MIN_LEN: return 0.0
    min_r = _min_ratio_for_len(min(len(alias_compact), len(text_compact)))
    penalty = 1.0 if len(text_tokens) == 1 else 0.93
    best = 0.0
    if len(entry["tokens"]) == 1:
        for t in text_tokens:
            tc = t.replace(" ", "")
            if len(tc) >= FUZZY_MIN_LEN:
                r = _ratio(tc, alias_compact)
                if r >= min_r: best = max(best, r * penalty)
    r_full = _ratio(text_compact, alias_compact)
    if r_full >= min_r: best = max(best, r_full * penalty)
    return best

def match_target(text, kinds=None):
    norm = _norm(text)
    if not norm: return None
    compact = norm.replace(" ", "")
    tokens = norm.split()
    results = []
    for entry in ALIAS_INDEX:
        if kinds and entry["cand"]["kind"] not in kinds: continue
        s = _score_against_alias(norm, compact, tokens, entry)
        if s > 0.0: results.append((s, entry["cand"]))
    if not results: return None
    results.sort(key=lambda x: x[0], reverse=True)
    best_s, best_c = results[0]
    if best_s < MATCH_ACCEPT: return None
    if best_s < 0.98:
        for s, c in results[1:]:
            if c is not best_c and best_s - s < AMBIGUITY_MARGIN: return None
    return best_c, best_s

# ============================================================
# ТЕКСТ-ХЕЛПЕРЫ
# ============================================================
def _strip_wake(norm):
    return " ".join(t for t in norm.split() if t not in WAKE_TOKENS).strip()

def _is_verb_token(tok):
    if tok in VERB_TOKENS: return True
    for stem in VERB_STEMS_NORM:
        if stem and len(tok) >= max(4, len(stem)) and tok.startswith(stem): return True
    return False

def _is_browser_token(tok):
    if tok in BROWSER_TOKENS: return True
    for stem in BROWSER_STEMS_NORM:
        if stem and len(tok) >= max(5, len(stem)) and tok.startswith(stem): return True
    return False

def _has_browser_tokens(norm):
    return any(_is_browser_token(t) for t in _norm(norm).split())

def _has_all_windows(norm):
    return any(t in ALL_WINDOWS_TOKENS for t in _norm(norm).split())

def _browser_with_preposition(norm):
    toks = norm.split()
    for i, t in enumerate(toks):
        if i and toks[i - 1] in PREPOSITION_TOKENS and _is_browser_token(t): return True
    return False

def _has_action(tokens, exact_set, stems):
    for tok in tokens:
        if tok in exact_set: return True
        for stem in stems:
            if stem and len(tok) >= max(4, len(stem)) and tok.startswith(stem): return True
    return False

_MUSIC_CTX = {"музыка", "музыку", "музыке", "музыки", "яму", "трек", "трека", "треку", "треков"}
_MUSIC_APP = {"музыка", "музыку", "музыке", "музыки", "яму"}

def _find_app_alias_in_tokens(tokens):
    for app_alias in APP_VOLUME_ALIASES.keys():
        a = _norm(app_alias)
        for t in tokens:
            if a == t or (len(a) >= 4 and (a in t or t in a)): return app_alias
    return None

def detect_action(norm):
    tokens = norm.split()
    if not tokens: return None
    if any(t in EXIT_TOKENS for t in tokens): return "exit"
    if any(t in STOP_LISTEN_TOKENS for t in tokens): return "stop"
    for ph in SLEEP_PHRASES_NORM:
        if ph and ph in norm: return "sleep"
    if any(t in SLEEP_TOKENS for t in tokens): return "sleep"
    if _has_action(tokens, CLOSE_TOKENS, CLOSE_STEMS_NORM): return "close"
    if _has_action(tokens, MINIMIZE_TOKENS, MINIMIZE_STEMS_NORM): return "minimize"
    if _has_action(tokens, RESTORE_TOKENS, RESTORE_STEMS_NORM): return "restore"
    if any(t.startswith("громк") for t in tokens) or any(t in {"volume", "звук"} for t in tokens):
        if _find_app_alias_in_tokens(tokens): return "app_volume"
        if any(t in _MUSIC_APP for t in tokens): return "ym_volume"
        return "sys_volume"
    if any(t in _MUSIC_CTX for t in tokens):
        if any(t in {"след", "следующий", "next", "дальше", "вперед", "вперёд"} for t in tokens): return "ym_next"
        if any(t in {"пред", "предыдущий", "prev", "назад"} for t in tokens): return "ym_prev"
        if any(t in {"пауз", "пауза", "stop", "pause"} for t in tokens): return "ym_play"
        if any(t in {"играй", "продолжи", "продолжить", "play", "возобнови"} for t in tokens): return "ym_play"
        if any(t in {"найди", "поищи", "search"} for t in tokens): return "ym_search"
    if len(tokens) == 1:
        if tokens[0] == "дальше": return "ym_next"
        if tokens[0] in {"пауза", "продолжи", "играй"}: return "ym_play"
    if _has_action(tokens, SEARCH_TOKENS, SEARCH_STEMS_NORM): return "search"
    if _has_action(tokens, OPEN_TOKENS, OPEN_STEMS_NORM): return "open"
    return None

def _clean_for_match(norm, remove_verbs=False, remove_browser=False):
    out = []
    for tok in norm.split():
        if tok in IGNORE_TOKENS: continue
        if remove_verbs and _is_verb_token(tok): continue
        if remove_browser and _is_browser_token(tok): continue
        out.append(tok)
    return " ".join(out).strip()

def _clean_for_search(norm, remove_verbs=False, remove_browser=False):
    out = []
    for tok in norm.split():
        if tok in WAKE_TOKENS or tok in FILLER_TOKENS: continue
        if remove_verbs and _is_verb_token(tok): continue
        if remove_browser and _is_browser_token(tok):
            if out and out[-1] in PREPOSITION_TOKENS: out.pop()
            continue
        out.append(tok)
    return " ".join(out).strip()

# ============================================================
# СОСТОЯНИЕ / ЗВУК
# ============================================================
state = {"listening": False, "last_act": 0.0, "lock": threading.Lock()}
_voice_busy = {"flag": False}
_close_busy = {"browser": False}
_bg_queue = deque()
_stop_event = threading.Event()
_sleep_event = threading.Event()
_audio_mute_until = 0.0
_mute_lock = threading.Lock()
_pending_browser = {"until": 0.0}
CLIPS = {"function": [], "wake": [], "fail": []}

def _load_clips(folder):
    if not os.path.isdir(folder): return []
    return [os.path.join(folder, f) for f in os.listdir(folder) if f.lower().endswith(AUDIO_EXT)]

def _first_existing_dir(dirs):
    for d in dirs:
        if os.path.isdir(d): return d
    return dirs[0] if dirs else ""

def init_voice():
    CLIPS["function"] = _load_clips(_first_existing_dir(FUNCTION_DIRS))
    CLIPS["wake"] = _load_clips(WAKE_DIR)
    CLIPS["fail"] = _load_clips(FAIL_DIR)
    print("Jarvis: голос: function=%d wake=%d fail=%d" % (len(CLIPS["function"]), len(CLIPS["wake"]), len(CLIPS["fail"])))

def _probe_wav(path):
    try:
        with wave.open(path, "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            if rate <= 0 or w.getsampwidth() not in (1, 2): return 1.2, False
            return max(0.1, frames / float(rate)), True
    except Exception:
        return 1.2, False

def _mci_play(path):
    winmm = ctypes.windll.winmm
    alias = "jarvis_snd"
    winmm.mciSendStringW("close %s" % alias, None, 0, None)
    rc = winmm.mciSendStringW('open "%s" type waveaudio alias %s' % (path, alias), None, 0, None)
    if rc != 0: rc = winmm.mciSendStringW('open "%s" alias %s' % (path, alias), None, 0, None)
    if rc != 0: raise RuntimeError("MCI open rc=%d" % rc)
    try:
        rc = winmm.mciSendStringW("play %s wait" % alias, None, 0, None)
        if rc != 0: raise RuntimeError("MCI play rc=%d" % rc)
    finally:
        winmm.mciSendStringW("close %s" % alias, None, 0, None)

def _set_mute(seconds):
    global _audio_mute_until
    with _mute_lock:
        _audio_mute_until = max(_audio_mute_until, time.time() + max(0.0, seconds))

def _is_muted():
    with _mute_lock:
        return time.time() < _audio_mute_until

def _remaining_mute():
    with _mute_lock:
        return max(0.0, _audio_mute_until - time.time())

def _play_file(path):
    if not path or not os.path.exists(path): return 0.0
    dur, is_pcm = _probe_wav(path)
    mute = max(SELF_MUTE_MIN, min(SELF_MUTE_MAX, dur + SELF_MUTE_PAD))
    _set_mute(mute)
    def _p():
        try:
            if is_pcm: winsound.PlaySound(path, winsound.SND_FILENAME)
            else: _mci_play(path)
        except Exception as e:
            print("[ERR] звук: %s -> %s" % (path, e))
    threading.Thread(target=_p, daemon=True).start()
    return mute

def speak(category):
    clips = CLIPS.get(category)
    if not clips or _voice_busy["flag"]: return 0.0
    path = random.choice(clips)
    _voice_busy["flag"] = True
    mute = _play_file(path)
    threading.Timer(max(0.1, mute), lambda: _voice_busy.__setitem__("flag", False)).start()
    return mute

def _play_wake_sound():
    if WAKE_SOUND_FILE and os.path.exists(WAKE_SOUND_FILE): return _play_file(WAKE_SOUND_FILE)
    print("[WARN] yes_sir.wav не найден:", WAKE_SOUND_FILE)
    mute = speak("wake")
    return max(mute, 1.5)

# ============================================================
# ОКНО СЛУШАНИЯ
# ============================================================
def _activate():
    print("Jarvis: да, сэр.")
    toast.show("ДЖАРВИС", "Слышу тебя", duration=1.5)
    mute = _play_wake_sound()
    _sleep_event.clear()
    with state["lock"]:
        state["listening"] = True
        state["last_act"] = time.time() + mute + TIMEOUT_LISTEN

def _pause_listening():
    with state["lock"]:
        if not state["listening"]: return 0.0
        rem = TIMEOUT_LISTEN - (time.time() - state["last_act"])
        state["listening"] = False
        return rem if rem > 0 else 0.0

def _disable_listening():
    with state["lock"]:
        state["listening"] = False

def _is_listening():
    with state["lock"]:
        return state["listening"]

def _remaining():
    with state["lock"]:
        if not state["listening"]: return None
        r = TIMEOUT_LISTEN - (time.time() - state["last_act"])
        return r if r > 0 else None

def _resume_listening_full():
    mute = _remaining_mute()
    with state["lock"]:
        state["listening"] = True
        state["last_act"] = time.time() + mute + TIMEOUT_LISTEN

def _resume_listening_remaining(rem):
    if rem <= 0: return
    mute = _remaining_mute()
    with state["lock"]:
        state["listening"] = True
        state["last_act"] = time.time() + mute + max(0.3, rem)

# ============================================================
# WINAPI
# ============================================================
_WM_CLOSE = 0x0010
_TH32CS_SNAPPROCESS = 0x00000002
_kernel32 = ctypes.WinDLL("kernel32")
_user32 = ctypes.WinDLL("user32")

class _PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wt.DWORD), ("cntUsage", wt.DWORD), ("th32ProcessID", wt.DWORD), ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wt.DWORD), ("cntThreads", wt.DWORD), ("th32ParentProcessID", wt.DWORD), ("pcPriClassBase", ctypes.c_long), ("dwFlags", wt.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

_kernel32.CreateToolhelp32Snapshot.restype = wt.HANDLE
_kernel32.CreateToolhelp32Snapshot.argtypes = [wt.DWORD, wt.DWORD]
_kernel32.Process32FirstW.restype = wt.BOOL
_kernel32.Process32FirstW.argtypes = [wt.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
_kernel32.Process32NextW.restype = wt.BOOL
_kernel32.Process32NextW.argtypes = [wt.HANDLE, ctypes.POINTER(_PROCESSENTRY32W)]
_kernel32.CloseHandle.restype = wt.BOOL
_kernel32.CloseHandle.argtypes = [wt.HANDLE]

_WNDENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
_user32.EnumWindows.restype = wt.BOOL
_user32.EnumWindows.argtypes = [_WNDENUMPROC, wt.LPARAM]
_user32.GetWindowThreadProcessId.restype = wt.DWORD
_user32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
_user32.IsWindowVisible.restype = wt.BOOL
_user32.IsWindowVisible.argtypes = [wt.HWND]
_user32.GetWindowTextLengthW.restype = ctypes.c_int
_user32.GetWindowTextLengthW.argtypes = [wt.HWND]
_user32.GetWindowTextW.restype = ctypes.c_int
_user32.GetWindowTextW.argtypes = [wt.HWND, ctypes.c_wchar_p, ctypes.c_int]
_user32.SetForegroundWindow.restype = wt.BOOL
_user32.SetForegroundWindow.argtypes = [wt.HWND]
_user32.PostMessageW.restype = wt.BOOL
_user32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
_user32.ShowWindow.restype = wt.BOOL
_user32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
_user32.keybd_event.restype = None
_user32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, wt.DWORD, ctypes.c_void_p]

def _snapshot_procs():
    out = []
    snap = _kernel32.CreateToolhelp32Snapshot(_TH32CS_SNAPPROCESS, 0)
    try:
        pe = _PROCESSENTRY32W()
        pe.dwSize = ctypes.sizeof(_PROCESSENTRY32W)
        if _kernel32.Process32FirstW(snap, ctypes.byref(pe)):
            while True:
                out.append((pe.th32ProcessID, pe.th32ParentProcessID, pe.szExeFile.lower()))
                if not _kernel32.Process32NextW(snap, ctypes.byref(pe)): break
    finally:
        if snap is not None: _kernel32.CloseHandle(snap)
    return out

def _pids_for_name(procs, name):
    return [pid for pid, _ppid, n in procs if n == name and pid != os.getpid()]

def _window_map_by_pid():
    m = {}
    def _enum_cb(hwnd, lparam):
        if _user32.IsWindowVisible(hwnd) and _user32.GetWindowTextLengthW(hwnd) > 0:
            pid = wt.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value != os.getpid(): m.setdefault(pid.value, []).append(hwnd)
        return True
    proc = _WNDENUMPROC(_enum_cb)
    _user32.EnumWindows(proc, 0)
    return m

def _send_wm_close(hwnd):
    _user32.PostMessageW(hwnd, _WM_CLOSE, 0, 0)

def _show_windows_for_names(names, cmd):
    wmap = _window_map_by_pid()
    procs = _snapshot_procs()
    shown = 0
    for name in names:
        for pid in _pids_for_name(procs, name):
            for hwnd in wmap.get(pid, []):
                _user32.ShowWindow(hwnd, cmd)
                shown += 1
    return shown

_kernel32.GetConsoleWindow.restype = wt.HWND
_kernel32.GetConsoleWindow.argtypes = []

def _minimize_all_windows():
    try: console_hwnd = _kernel32.GetConsoleWindow()
    except Exception: console_hwnd = None
    our_pid = os.getpid()
    count = [0]
    def _cb(hwnd, lparam):
        try:
            if console_hwnd and hwnd == console_hwnd: return True
            if not _user32.IsWindowVisible(hwnd): return True
            length = _user32.GetWindowTextLengthW(hwnd)
            if length <= 0: return True
            buf = ctypes.create_unicode_buffer(length + 1)
            _user32.GetWindowTextW(hwnd, buf, length + 1)
            if _norm(buf.value) in SKIP_WINDOW_TITLES: return True
            pid = wt.DWORD()
            _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == our_pid: return True
            _user32.ShowWindow(hwnd, 6)
            count[0] += 1
        except Exception: pass
        return True
    proc = _WNDENUMPROC(_cb)
    _user32.EnumWindows(proc, 0)
    return count[0]

# ============================================================
# ГРОМКОСТЬ
# ============================================================
def _set_system_volume(percent):
    """Меняет ОБЩУЮ громкость Windows (динамики/наушники), 0-100."""
    try:
        from pycaw.pycaw import AudioUtilities
        devices = AudioUtilities.GetSpeakers()
        # Используем свойство EndpointVolume, которое мы нашли в диагностике
        volume_interface = devices.EndpointVolume
        volume_interface.SetMasterVolumeLevelScalar(max(0.0, min(1.0, percent / 100.0)), None)
        return True
    except Exception as e:
        print("[ERR] системная громкость:", e)
        return False

def _find_app_session(app_name):
    if not HAS_PYCAW: return None, None
    try: sessions = AudioUtilities.GetAllSessions()
    except Exception: return None, None
    exe_names = APP_VOLUME_ALIASES.get(app_name, [app_name + ".exe"])
    for session in sessions:
        proc = session.Process
        if proc:
            pname = proc.name().lower()
            for exe in exe_names:
                if exe.lower() in pname: return session, pname
    return None, None

def _app_volume(app_alias, percent):
    session, exe_name = _find_app_session(app_alias)
    if not session: return False, None
    volume = session.SimpleAudioVolume
    vol_float = max(0.0, min(1.0, percent / 100.0))
    volume.SetMasterVolume(vol_float, None)
    return True, exe_name

def _send_media_key(vk_code):
    _user32.keybd_event(vk_code, 0, 0, 0)
    time.sleep(0.05)
    _user32.keybd_event(vk_code, 0, 2, 0)

def _ym_media_control(action):
    keys = {"play": 0xB3, "next": 0xB0, "prev": 0xB1}
    vk = keys.get(action)
    if vk: _send_media_key(vk)

def _ym_set_volume(percent):
    ok, _ = _app_volume("яндекс музыка", percent)
    return ok

def _ym_find_yandex_music_hwnd():
    target_title = "яндекс музыка"
    def _cb(hwnd, lparam):
        if _user32.IsWindowVisible(hwnd) and _user32.GetWindowTextLengthW(hwnd) > 0:
            buf = ctypes.create_unicode_buffer(256)
            _user32.GetWindowTextW(hwnd, buf, 256)
            if target_title in buf.value.lower():
                _user32.SetForegroundWindow(hwnd)
                time.sleep(0.2)
                return False
        return True
    proc = _WNDENUMPROC(_cb)
    _user32.EnumWindows(proc, 0)

def _ym_search_track(query):
    _ym_find_yandex_music_hwnd()
    time.sleep(0.3)
    _user32.keybd_event(0x11, 0, 0, 0)
    _user32.keybd_event(0x4B, 0, 0, 0)
    time.sleep(0.05)
    _user32.keybd_event(0x4B, 0, 2, 0)
    _user32.keybd_event(0x11, 0, 2, 0)
    time.sleep(0.3)
    subprocess.run(["clip"], input=query.encode("utf-16le"), capture_output=True)
    _user32.keybd_event(0x11, 0, 0, 0)
    _user32.keybd_event(0x56, 0, 0, 0)
    time.sleep(0.05)
    _user32.keybd_event(0x56, 0, 2, 0)
    _user32.keybd_event(0x11, 0, 2, 0)
    time.sleep(0.1)
    _user32.keybd_event(0x0D, 0, 0, 0)
    _user32.keybd_event(0x0D, 0, 2, 0)

# ============================================================
# ЗАКРЫТИЕ ПРОЦЕССОВ
# ============================================================
_BROWSER_SET = {n.lower() for n in BROWSER_PROCS}

def _force_kill_roots(survivors):
    procs = _snapshot_procs()
    pm = {pid: ppid for pid, ppid, _n in procs}
    roots = [pid for pid in survivors if pm.get(pid) not in survivors]
    forced = 0
    for r in roots:
        try:
            subprocess.run(["taskkill", "/F", "/PID", str(r), "/T"], capture_output=True)
            forced += 1
        except Exception: pass
    return forced

def _close_worker(names, label, browser_close=False):
    t0 = time.perf_counter()
    try:
        wmap = _window_map_by_pid()
        closed = leftover = forced = 0
        for name in names:
            procs = _snapshot_procs()
            pids = set(_pids_for_name(procs, name))
            if not pids: continue
            for pid in pids:
                for hwnd in wmap.get(pid, []): _send_wm_close(hwnd)
            is_browser = name in _BROWSER_SET
            wait_timeout = CLOSE_BROWSER_WAIT_TIMEOUT if is_browser else CLOSE_WAIT_TIMEOUT
            deadline = time.perf_counter() + wait_timeout
            survivors = pids
            while time.perf_counter() < deadline:
                time.sleep(CLOSE_POLL)
                survivors = set(_pids_for_name(_snapshot_procs(), name))
                if not survivors: break
            if survivors:
                forced += _force_kill_roots(survivors)
                survivors = set(_pids_for_name(_snapshot_procs(), name))
            closed += len(pids) - len(survivors)
            leftover += len(survivors)
            time.sleep(CLOSE_QUEUE_DELAY)
        dt = time.perf_counter() - t0
        msg = "[close] %s: закрыто %d, принудительно %d, осталось %d (%.1f сек)" % (label, closed, forced, leftover, dt) if leftover else "[close] %s: закрыт полностью за %.1f сек" % (label, dt)
        _bg_queue.append(msg)
    finally:
        if browser_close: _close_busy["browser"] = False

def close_processes(names, label, browser_close=False):
    if not names: return "unknown", "Не понял, что закрывать."
    procs = _snapshot_procs()
    running = [n for n in names if _pids_for_name(procs, n)]
    if not running: return "unknown", "Не нашёл запущенных: %s" % label
    if browser_close:
        if _close_busy["browser"]: return "unknown", "Браузер уже закрывается, подожди."
        _close_busy["browser"] = True
    threading.Thread(target=_close_worker, args=(running, label, browser_close), daemon=True).start()
    return "ok", "Закрываю %s..." % label

# ============================================================
# ДЕЙСТВИЯ
# ============================================================
def launch_program(label):
    commands = LAUNCH_COMMANDS.get(label)
    if not commands: return "unknown", "Нет команды запуска для %s" % label
    last_err = ""
    for cmd in commands:
        expanded = [os.path.expandvars(os.path.expanduser(x)) for x in cmd]
        exe, args = expanded[0], expanded[1:]
        candidates = []
        if os.path.isabs(exe): candidates.append(exe)
        else:
            w = shutil.which(exe)
            if w: candidates.append(w)
            candidates.append(exe)
        for e in candidates:
            try:
                subprocess.Popen([e] + args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return "ok", "Запускаю %s." % label
            except Exception as ex: last_err = str(ex)
    if os.name == "nt":
        expanded = [os.path.expandvars(os.path.expanduser(x)) for x in commands[0]]
        quoted = " ".join('"%s"' % x for x in expanded)
        try:
            subprocess.Popen('start "" %s' % quoted, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return "ok", "Запускаю %s." % label
        except Exception as ex: last_err = str(ex)
    return "unknown", "Не найден %s. %s" % (label, last_err)

def do_search(query):
    q = _norm(query)
    if not q: return "ignored", ""
    webbrowser.open("https://yandex.ru/search/?text=" + urllib.parse.quote(q))
    return "ok", "Поиск: %s" % q

def open_candidate(cand, norm):
    if cand["kind"] == "site":
        webbrowser.open(cand["payload"]["url"])
        return "ok", "Открыл %s" % cand["label"]
    return launch_program(cand["label"])

def do_close(target_norm):
    target = _norm(target_norm)
    if not target: return "unknown", "Не понял, что закрывать."
    if _has_browser_tokens(target): return close_processes([n.lower() for n in BROWSER_PROCS], "браузер", browser_close=True)
    cand = match_target(target, kinds={"app"})
    if cand:
        c, _s = cand
        return close_processes([p.lower() for p in c["payload"]["processes"]], c["label"], browser_close=False)
    word = "".join(ch for ch in target if ch.isalnum())
    if word and len(word) >= 3: return close_processes([word + ".exe"], word, browser_close=False)
    return "unknown", "Не нашёл, что закрывать."

# ============================================================
# ПАРСЕР
# ============================================================
def _set_pending_browser():
    _pending_browser["until"] = time.time() + PENDING_BROWSER_TTL
    return "pending", "Жду запрос для браузера"

def _consume_pending_browser():
    if time.time() < _pending_browser["until"]:
        _pending_browser["until"] = 0.0
        return True
    return False

def parse_command(text):
    norm = _strip_wake(_norm(text))
    if not norm: return "ignored", ""
    action = detect_action(norm)
    if action == "exit": return "exit", "Выключаюсь"
    if action == "stop": return "stop", "Стоп"
    if action == "sleep": return "sleep", "Сплю. Скажи 'джарвис', когда понадоблюсь."
    if action is not None: _pending_browser["until"] = 0.0
    tokens = norm.split()
    has_browser = _has_browser_tokens(norm)

    if action == "close": return do_close(_clean_for_match(norm, remove_verbs=True))
    if action in ("minimize", "restore"):
        cmd = 6 if action == "minimize" else 9
        verb = "Сворачиваю" if action == "minimize" else "Разворачиваю"
        target = _clean_for_match(norm, remove_verbs=True)
        if action == "minimize" and _has_all_windows(norm):
            cnt = _minimize_all_windows()
            if not cnt: return "ok", "Всё и так свёрнуто."
            return "ok", "Свернул всё: %d окон." % cnt
        if _has_browser_tokens(norm):
            names = [n.lower() for n in BROWSER_PROCS]
            label = "браузер"
        else:
            cand = match_target(target, kinds={"app"})
            if not cand: return "unknown", "Не понял, что сворачивать."
            c, _s = cand
            names = [p.lower() for p in c["payload"]["processes"]]
            label = c["label"]
        shown = _show_windows_for_names(names, cmd)
        if not shown: return "unknown", "Не нашёл окон: %s" % label
        return "ok", "%s %s." % (verb, label)

    if action == "sys_volume":
        dig = _words_to_digits(norm)
        nums = re.findall(r"\d+", dig)
        if nums:
            vol = max(0, min(100, int(nums[0])))
            if _set_system_volume(vol): return "ok", "Системная громкость %d%%." % vol
            return "unknown", "Не удалось изменить громкость."
        return "unknown", "Скажи число, например 'громкость 50' или 'громкость десять'."

    if action == "app_volume":
        dig = _words_to_digits(norm)
        nums = re.findall(r"\d+", dig)
        if not nums: return "unknown", "Скажи число, например 'громкость дискорда 50'."
        vol = max(0, min(100, int(nums[0])))
        app_alias = _find_app_alias_in_tokens(tokens)
        if not app_alias: return "unknown", "Не понял, для какого приложения."
        ok, _exe = _app_volume(app_alias, vol)
        if ok: return "ok", "Громкость %s: %d%%." % (app_alias, vol)
        return "unknown", "%s не запущен." % app_alias

    if action == "ym_next":
        _ym_media_control("next"); return "ok", "Следующий трек."
    if action == "ym_prev":
        _ym_media_control("prev"); return "ok", "Предыдущий трек."
    if action == "ym_play":
        _ym_media_control("play"); return "ok", "Управляю воспроизведением."
    if action == "ym_volume":
        dig = _words_to_digits(norm)
        nums = re.findall(r"\d+", dig)
        if nums:
            vol = max(0, min(100, int(nums[0])))
            if _ym_set_volume(vol): return "ok", "Громкость музыки %d%%." % vol
            return "unknown", "Яндекс Музыка не запущена."
        return "unknown", "Скажи число, например 'громкость в музыке 50'."
    if action == "ym_search":
        query = _clean_for_search(norm, remove_verbs=True, remove_browser=True)
        for w in ("музыка", "музыку", "музыке", "музыки", "яму", "яндекс", "найди", "поищи", "трек", "включи", "search"):
            query = query.replace(w, " ")
        query = " ".join(query.split())
        if query:
            _ym_search_track(query)
            return "ok", "Ищу в музыке: %s" % query
        return "unknown", "Что найти в музыке?"

    if action in ("open", "search") or has_browser:
        target = _clean_for_match(norm, remove_verbs=True)
        if not _browser_with_preposition(norm):
            cand = match_target(target)
            if cand and cand[1] >= 0.90: return open_candidate(cand[0], norm)
        if has_browser or action == "search":
            query = _clean_for_search(norm, remove_verbs=True, remove_browser=True)
            if query and _has_meaningful(query): return do_search(query)
            if _browser_with_preposition(norm): return _set_pending_browser()
            webbrowser.open("https://www.google.com")
            return "ok", "Открыл Браузер/Google"
        cand = match_target(target)
        if cand: return open_candidate(cand[0], norm)
        return "unknown", "Не знаю '%s'. Для поиска скажи 'открой в браузере ...'." % target

    if _consume_pending_browser():
        query = _clean_for_search(norm)
        if query and _has_meaningful(query): return do_search(query)
        return "ignored", ""
    cand = match_target(norm)
    if cand and cand[1] >= BARE_MATCH_ACCEPT: return open_candidate(cand[0], norm)
    return "unknown", "Не понял команду. Скажи 'открой в браузере ...' или 'найди ...'."

def dispatch(text):
    t0 = time.perf_counter()
    norm = _strip_wake(_norm(text))
    action = detect_action(norm)
    print("\n" + "=" * 50)
    print("[DEBUG] СЫРОЙ ТЕКСТ (Vosk) : '%s'" % text)
    print("[DEBUG] НОРМАЛИЗОВАННЫЙ    : '%s'" % norm)
    print("[DEBUG] ОПРЕДЕЛЕННОЕ ДЕЙСТ.: '%s'" % action)
    print("=" * 50)
    status, msg = parse_command(text)
    dt = time.perf_counter() - t0
    if status in ("ok", "unknown", "exit", "stop", "sleep", "pending") and msg:
        print("[RESULT] %s | %.2f сек\n" % (msg, dt))
    if status == "ok":
        toast.show("ДЖАРВИС", msg, duration=2.5, color="#1e1e1e", text_color="#ffffff")
        speak("function")
    elif status == "unknown":
        toast.show("ДЖАРВИС", msg, duration=2.5, color="#3a1e1e", text_color="#ff6b6b")
        speak("fail")
    elif status in ("exit", "stop"):
        toast.show("ДЖАРВИС", msg, duration=2.0, color="#1e1e1e", text_color="#ffffff")
        speak("function")
    elif status == "sleep":
        toast.show("ДЖАРВИС", "Сплю...", duration=2.0, color="#1e2a3a", text_color="#88ccff")
    return status, msg

# ============================================================
# АУДИО-ДВИЖОК
# ============================================================
def run_audio():
    import numpy as np
    import sounddevice as sd
    from vosk import Model, KaldiRecognizer
    try:
        from vosk import SetLogLevel
        SetLogLevel(-1)
    except Exception: pass
    if not os.path.exists(MODEL_PATH_VOSK):
        print("[ERR] Не найдена модель Vosk:", MODEL_PATH_VOSK)
        sys.exit(1)
    print("Jarvis: загрузка Vosk...")
    t0 = time.time()
    vosk = Model(MODEL_PATH_VOSK)
    rec = KaldiRecognizer(vosk, SAMPLE_RATE)
    wake_rec = KaldiRecognizer(vosk, SAMPLE_RATE, WAKE_KWS_GRAMMAR)
    print("Jarvis: Vosk готов за %.1f сек. (KWS-словарь: %s)" % (time.time() - t0, ", ".join(sorted(WAKE_KWS_WORDS))))
    print("Jarvis: готов. Скажи 'джарвис'. Ctrl+C - выход.")

    mic_device = sd.default.device[0]
    if mic_device is None or mic_device < 0:
        inputs = [(i, d) for i, d in enumerate(sd.query_devices()) if d["max_input_channels"] > 0]
        if not inputs:
            print("[ERR] микрофоны не найдены.")
            sys.exit(1)
        mic_device = inputs[0][0]
    dev_info = sd.query_devices(mic_device)
    dev_name = dev_info["name"] if dev_info else "неизвестно"
    print("Jarvis: микрофон по умолчанию: %s (индекс %s)" % (dev_name, mic_device))

    cmd_q = queue.Queue()
    processing = [False]
    last_wake = [0.0]

    def _submit(txt, rem, timeout=False):
        processing[0] = True
        cmd_q.put((txt, rem, timeout))

    def _worker():
        while not _stop_event.is_set():
            try: item = cmd_q.get(timeout=0.2)
            except queue.Empty: continue
            txt, rem, timeout = item
            try:
                status, _ = dispatch(txt)
                if status == "exit":
                    _stop_event.set()
                    _disable_listening()
                elif status == "stop":
                    _disable_listening()
                    wake_rec.Reset()
                    print("[STATE] слушание остановлено вручную")
                elif status == "sleep":
                    _disable_listening()
                    wake_rec.Reset()
                    last_wake[0] = 0.0
                    print("[STATE] сплю. Скажи 'джарвис', чтобы разбудить.")
                elif timeout: pass
                elif status == "ignored": _resume_listening_remaining(rem)
                else:
                    _resume_listening_full()
                    print("Jarvis: слушаю.")
            finally: processing[0] = False

    threading.Thread(target=_worker, daemon=True).start()

    def _timeout_stop():
        rem = _pause_listening()
        wake_rec.Reset()
        last_wake[0] = 0.0
        print("[STATE] окно слушания закрыто по таймауту")
        try:
            final = json.loads(rec.FinalResult()).get("text", "").strip()
            if final: _submit(final, rem, True)
        except Exception: pass

    def cb(indata, frames, ti, status):
        data = bytes(indata)
        if _is_muted(): return
        now = time.time()
        if _is_listening():
            if _remaining() is None:
                _timeout_stop()
                return
            if rec.AcceptWaveform(data):
                txt = json.loads(rec.Result()).get("text", "").strip()
                if txt:
                    rem = _pause_listening()
                    _submit(txt, rem, False)
            return
        if processing[0]: return
        if wake_rec.AcceptWaveform(data):
            wtxt = json.loads(wake_rec.Result()).get("text", "")
        else:
            wtxt = json.loads(wake_rec.PartialResult()).get("partial", "")
        if not wtxt: return
        wtoks = set(_norm(wtxt).split())
        if wtoks & WAKE_KWS_WORDS and now - last_wake[0] > WAKE_COOLDOWN:
            print("[WAKE] услышано: '%s'" % wtxt)
            last_wake[0] = now
            wake_rec.Reset()
            rec.Reset()
            _activate()

    try:
        with sd.RawInputStream(samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE, dtype="int16", channels=1, device=mic_device, callback=cb):
            while not _stop_event.is_set():
                while _bg_queue: print(_bg_queue.popleft())
                time.sleep(0.1)
    except KeyboardInterrupt: print("\nJarvis: выход.")
    except Exception as e: print("[ERR] аудио:", e)
    finally: _stop_event.clear()

def main():
    init_voice()
    run_audio()

if __name__ == "__main__":
    main()