"""Card browser button: a fixed or user-chosen web page, never shell commands."""
from urllib.parse import urlsplit

WEB_TARGETS=(('chatgpt','GPT 网页'),('website','自定义网页'))
CHATGPT_URL='https://chatgpt.com/'

def website_url(value):
    value=str(value or '').strip()
    if not value or len(value)>2048 or any(ord(c)<32 for c in value):
        raise ValueError('请输入完整的 http:// 或 https:// 网页地址。')
    try:
        parts=urlsplit(value)
        if parts.scheme.lower() not in ('http','https') or not parts.hostname or parts.username or parts.password:
            raise ValueError()
        parts.port
    except ValueError:
        raise ValueError('只支持 http:// 或 https:// 网页地址，不支持命令、文件路径或带密码的地址。') from None
    return value

def target_url(settings):
    return website_url(settings.get('web_url')) if settings.get('web_button')=='website' else CHATGPT_URL
