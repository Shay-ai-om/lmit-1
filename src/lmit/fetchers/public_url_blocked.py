from __future__ import annotations

BLOCKED_PUBLIC_URL_MARKERS = (
    "performing security verification",
    "enable javascript and cookies to continue",
    "verification successful. waiting for",
    "checking your browser",
    "just a moment...",
    "cloudflare ray id",
    "sign in to continue",
    "log in to continue",
    "mobile@digitimes.com",
    "百度安全验证",
    "请完成下方验证后继续操作",
    "点击按钮开始验证",
    "请向右滑动完成拼图",
    "扫码验证",
    "目前無法查看此內容，通常是因為擁有者僅與一小群用戶分享內容。",
    "目前無法查看此內容",
    "擁有者僅與一小群用戶分享內容",
    "變更了分享對象",
    "刪除了內容",
    "digitimes蝬脩???撠蝙?冽??函?撘之???雯??ip鈭誑撠?",
    "?桀??⊥??亦?甇文摰對??虜?臬??箸?????撠黎?冽?澈?批捆??",
    "?獢?????鈭????望?",
    "?蹓????????暺??踝??????寞?",
    "??謆???剜???",
    "??畸??哨??望?",
)


_CLOUDFLARE_CHALLENGE_MARKERS = (
    "cloudflare ray id",
    "cf-browser-verification",
    "cf-chl",
    "cf_chl",
    "__cf_chl",
    "cdn-cgi/challenge-platform",
    "challenges.cloudflare.com",
    "cf-turnstile",
    "turnstile.render",
    "checking if the site connection is secure",
    "needs to review the security of your connection",
    "verify you are human by completing the action below",
)


def is_blocked_public_url_text(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in BLOCKED_PUBLIC_URL_MARKERS)


def is_cloudflare_challenge_public_url_text(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _CLOUDFLARE_CHALLENGE_MARKERS)
