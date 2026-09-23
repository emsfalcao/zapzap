"""Seletores de DOM do WhatsApp Web e geradores de JavaScript da automação.

Fork FalcaoNet: TODOS os seletores usados pela automação ficam aqui, em
constantes, para ajuste após validação no WhatsApp Web real. As funções
devolvem JavaScript que retorna strings de status estáveis:

- ``ok``
- ``nao-logado``        (sem ``#pane-side`` e sem compositor)
- ``sem-compositor``    (logado, mas nenhuma conversa aberta)
- ``sem-botao-enviar``  (compositor presente, botão enviar não encontrado)
- ``chat-nao-abriu``    (usado pelo runner quando o polling expira)
- ``numero-invalido``   (diálogo do WhatsApp sobre número inválido)
- ``grupo`` / ``individual`` / ``sem-cabecalho`` (detecção de grupo)

Qualquer dado vindo do Python entra no JS por ``json.dumps``; nunca por
interpolação. Nenhum script dispara Enter sintético: o envio é sempre um
``click()`` no botão de enviar do próprio WhatsApp Web.
"""

from __future__ import annotations

import json

# --- seletores -----------------------------------------------------------
LOGGED_IN_SELECTOR = "#pane-side"
COMPOSER_SELECTORS = (
    'footer div[contenteditable="true"][role="textbox"]',
    'footer div[contenteditable="true"]',
)
SEND_BUTTON_PRIMARY_SELECTOR = 'footer button:has(span[data-icon="send"])'
SEND_ICON_SELECTOR = 'footer [data-icon="send"]'
SEND_BUTTON_ARIA_SELECTOR = "footer button[aria-label]"
SEND_ARIA_LABEL_WORDS = ("enviar", "send")

CHAT_HEADER_SELECTOR = "#main header"
CHAT_HEADER_TITLE_SELECTORS = (
    "#main header span[title]",
    '#main header span[dir="auto"]',
)
GROUP_ICON_SELECTOR = '#main header [data-icon="default-group"]'
GROUP_PARTICIPANTS_SELECTOR = "#main header span[title]"

INVALID_NUMBER_DIALOG_SELECTOR = 'div[role="dialog"]'
INVALID_NUMBER_WORDS = ("invalid", "inválido", "invalido")

STATUS_OK = "ok"
STATUS_NOT_LOGGED = "nao-logado"
STATUS_NO_COMPOSER = "sem-compositor"
STATUS_NO_SEND_BUTTON = "sem-botao-enviar"
STATUS_CHAT_NOT_OPENED = "chat-nao-abriu"
STATUS_INVALID_NUMBER = "numero-invalido"
STATUS_GROUP = "grupo"
STATUS_INDIVIDUAL = "individual"
STATUS_NO_HEADER = "sem-cabecalho"


def _js_selector_list(selectors) -> str:
    return json.dumps(list(selectors))


def _composer_lookup_js() -> str:
    """JS expression that evaluates to the composer element or null."""
    return (
        "(function(){var s=%s;for(var i=0;i<s.length;i++){"
        "var e=document.querySelector(s[i]);if(e){return e;}}return null;})()"
        % _js_selector_list(COMPOSER_SELECTORS)
    )


def build_probe_script() -> str:
    """Return ``ok`` (chat open), ``sem-compositor`` (logged) or ``nao-logado``."""
    return (
        "(function(){"
        "var composer=%s;"
        "var pane=document.querySelector(%s);"
        "if(composer){return %s;}"
        "if(pane){return %s;}"
        "return %s;})();"
    ) % (
        _composer_lookup_js(),
        json.dumps(LOGGED_IN_SELECTOR),
        json.dumps(STATUS_OK),
        json.dumps(STATUS_NO_COMPOSER),
        json.dumps(STATUS_NOT_LOGGED),
    )


def build_chat_header_script() -> str:
    """Return the title of the open chat's header ('' when none)."""
    return (
        "(function(){var s=%s;for(var i=0;i<s.length;i++){"
        "var e=document.querySelector(s[i]);"
        "if(e){return (e.getAttribute('title')||e.textContent||'').trim();}}"
        "return '';})();"
    ) % _js_selector_list(CHAT_HEADER_TITLE_SELECTORS)


def build_invalid_number_dialog_script() -> str:
    """Return ``numero-invalido`` when WhatsApp shows its invalid-number dialog."""
    return (
        "(function(){var d=document.querySelectorAll(%s);"
        "var words=%s;"
        "for(var i=0;i<d.length;i++){var t=(d[i].textContent||'').toLowerCase();"
        "for(var j=0;j<words.length;j++){if(t.indexOf(words[j])>=0){return %s;}}}"
        "return %s;})();"
    ) % (
        json.dumps(INVALID_NUMBER_DIALOG_SELECTOR),
        json.dumps(list(INVALID_NUMBER_WORDS)),
        json.dumps(STATUS_INVALID_NUMBER),
        json.dumps(STATUS_OK),
    )


def build_chat_state_script() -> str:
    """Return one JSON string ``{"status","header","dialog"}`` for polling.

    ``status`` follows :func:`build_probe_script`, ``header`` the open chat
    title and ``dialog`` is ``numero-invalido`` or ``ok``. One round trip per
    poll instead of three.
    """
    return (
        "(function(){"
        "var composer=%s;"
        "var pane=document.querySelector(%s);"
        "var status=composer?%s:(pane?%s:%s);"
        "var header='';var hs=%s;for(var i=0;i<hs.length;i++){"
        "var e=document.querySelector(hs[i]);"
        "if(e){header=(e.getAttribute('title')||e.textContent||'').trim();break;}}"
        "var dialog=%s;var d=document.querySelectorAll(%s);var words=%s;"
        "for(var k=0;k<d.length;k++){var t=(d[k].textContent||'').toLowerCase();"
        "for(var j=0;j<words.length;j++){if(t.indexOf(words[j])>=0){dialog=%s;}}}"
        "return JSON.stringify({status:status,header:header,dialog:dialog});})();"
    ) % (
        _composer_lookup_js(),
        json.dumps(LOGGED_IN_SELECTOR),
        json.dumps(STATUS_OK),
        json.dumps(STATUS_NO_COMPOSER),
        json.dumps(STATUS_NOT_LOGGED),
        _js_selector_list(CHAT_HEADER_TITLE_SELECTORS),
        json.dumps(STATUS_OK),
        json.dumps(INVALID_NUMBER_DIALOG_SELECTOR),
        json.dumps(list(INVALID_NUMBER_WORDS)),
        json.dumps(STATUS_INVALID_NUMBER),
    )


def parse_chat_state(result) -> dict:
    """Decode the JSON produced by :func:`build_chat_state_script`."""
    fallback = {"status": STATUS_NOT_LOGGED, "header": "", "dialog": STATUS_OK}
    if not isinstance(result, str):
        return fallback
    try:
        data = json.loads(result)
    except ValueError:
        return fallback
    if not isinstance(data, dict):
        return fallback
    return {
        "status": str(data.get("status", STATUS_NOT_LOGGED)),
        "header": str(data.get("header", "") or ""),
        "dialog": str(data.get("dialog", STATUS_OK)),
    }


def build_is_group_script() -> str:
    """Best-effort group detection from the open chat header."""
    return (
        "(function(){"
        "var header=document.querySelector(%s);"
        "if(!header){return %s;}"
        "if(document.querySelector(%s)){return %s;}"
        "var spans=document.querySelectorAll(%s);"
        "for(var i=0;i<spans.length;i++){var t=spans[i].getAttribute('title')||'';"
        "if(t.indexOf(', ')>=0){return %s;}}"
        "return %s;})();"
    ) % (
        json.dumps(CHAT_HEADER_SELECTOR),
        json.dumps(STATUS_NO_HEADER),
        json.dumps(GROUP_ICON_SELECTOR),
        json.dumps(STATUS_GROUP),
        json.dumps(GROUP_PARTICIPANTS_SELECTOR),
        json.dumps(STATUS_GROUP),
        json.dumps(STATUS_INDIVIDUAL),
    )


def build_click_send_script() -> str:
    """Click WhatsApp Web's own send button. Never synthesizes Enter."""
    return (
        "(function(){"
        "if(!document.querySelector(%s)&&!%s){return %s;}"
        "var b=null;"
        "try{b=document.querySelector(%s);}catch(e){b=null;}"
        "if(!b){var icon=document.querySelector(%s);"
        "if(icon){b=icon.closest('button');}}"
        "if(!b){var words=%s;var all=document.querySelectorAll(%s);"
        "for(var i=0;i<all.length;i++){var l=(all[i].getAttribute('aria-label')||'').toLowerCase();"
        "for(var j=0;j<words.length;j++){if(l.indexOf(words[j])>=0){b=all[i];break;}}"
        "if(b){break;}}}"
        "if(!b){return %s;}"
        "b.click();"
        "return %s;})();"
    ) % (
        json.dumps(LOGGED_IN_SELECTOR),
        _composer_lookup_js(),
        json.dumps(STATUS_NOT_LOGGED),
        json.dumps(SEND_BUTTON_PRIMARY_SELECTOR),
        json.dumps(SEND_ICON_SELECTOR),
        json.dumps(list(SEND_ARIA_LABEL_WORDS)),
        json.dumps(SEND_BUTTON_ARIA_SELECTOR),
        json.dumps(STATUS_NO_SEND_BUTTON),
        json.dumps(STATUS_OK),
    )
