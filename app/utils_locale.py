from fastapi import Request
from app.lang import translations

def get_lang_for_request(request: Request):
    lang = getattr(request, "session", {}).get("lang")
    if not lang:
        cookie_lang = request.cookies.get('lang')
        if cookie_lang in translations:
            lang = cookie_lang
    if not lang:
        acceptlang = request.headers.get("accept-language", "").lower()
        if "tr" in acceptlang:
            lang = "tr"
        elif "en" in acceptlang:
            lang = "en"
    if lang not in translations:
        lang = "en"
    return lang

def L(key, lang):
    return translations.get(lang, translations["en"]).get(key, key)