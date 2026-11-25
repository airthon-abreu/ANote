import re
from typing import Dict, Optional

ANCHOR_REGEX = re.compile(r"\[\[(.*?)\|(.*?)\]\]")
BODY_CONTENT_REGEX = re.compile(r"<body[^>]*>(.*?)</body>", re.DOTALL | re.IGNORECASE)
STYLE_BLOCK_REGEX = re.compile(r"<style[^>]*>.*?</style>", re.DOTALL | re.IGNORECASE)
ANCHOR_TAG_REGEX = re.compile(
    r'(<a\b[^>]*href=["\']anchor:[^"\']+["\'][^>]*>.*?</a>)',
    re.DOTALL | re.IGNORECASE
)

THEME_NEUTRAL_COLORS_REGEX = re.compile(
    r'(?<![a-zA-Z-])color:\s*#(?:1f2328|000000|000|11111b|181825|24273a|333333|1e1e2e|cdd6f4|ffffff|fff|f5c2e7|bac2de|a6adc8|9399b2|d9e0ee|f1f5f9|f8fafc)\b;?',
    re.IGNORECASE
)


class TextParser:
    @staticmethod
    def clean_legacy_tokens(raw_content: str, term_colors: Optional[Dict[str, str]] = None) -> str:
        if not raw_content:
            return ""

        term_colors = term_colors or {}

        def replace_anchor(match):
            term_text = match.group(1)
            anchor_key = match.group(2)
            color = term_colors.get(anchor_key, "#ffe066")
            return (
                f'<a href="anchor:{anchor_key}" style="background-color: {color}; color: #1e1e2e; '
                f'padding: 2px 4px; border-radius: 4px; text-decoration: none;">{term_text}</a>'
            )

        if "[[" in raw_content and "]]" in raw_content:
            raw_content = ANCHOR_REGEX.sub(replace_anchor, raw_content)

        return raw_content

    @staticmethod
    def extract_body_inner(html_content: str) -> str:
        if not html_content:
            return ""
        match = BODY_CONTENT_REGEX.search(html_content)
        inner = match.group(1).strip() if match else html_content
        return STYLE_BLOCK_REGEX.sub("", inner).strip()

    @staticmethod
    def sanitize_theme_colors(
        html_content: str,
        is_dark: bool,
        target_text_color: Optional[str] = None,
        strip_theme_defaults: bool = False
    ) -> str:
        """
        Normaliza cores de texto gravadas inline para evitar texto invisível ao alternar
        tema ou cor de card, sem corromper 'background-color' nem termos grifados.
        """
        if not html_content:
            return ""

        protected_anchors = []

        def _stash_anchor(match):
            idx = len(protected_anchors)
            protected_anchors.append(match.group(1))
            return f"__ANOTE_ANCHOR_STASH_{idx}__"

        sanitized = ANCHOR_TAG_REGEX.sub(_stash_anchor, html_content)

        if strip_theme_defaults:
            sanitized = THEME_NEUTRAL_COLORS_REGEX.sub("", sanitized)
        elif is_dark:
            fg = target_text_color or "#cdd6f4"
            dark_pattern = r'(?<![a-zA-Z-])color:\s*#(?:1f2328|000000|000|11111b|181825|24273a|333333|1e1e2e)\b;?'
            sanitized = re.sub(dark_pattern, f"color: {fg};", sanitized, flags=re.IGNORECASE)
        else:
            fg = target_text_color or "#1f2328"
            light_pattern = r'(?<![a-zA-Z-])color:\s*#(?:cdd6f4|ffffff|fff|f5c2e7|bac2de|a6adc8|9399b2|d9e0ee|f1f5f9|f8fafc)\b;?'
            sanitized = re.sub(light_pattern, f"color: {fg};", sanitized, flags=re.IGNORECASE)

        for idx, anchor_html in enumerate(protected_anchors):
            sanitized = sanitized.replace(f"__ANOTE_ANCHOR_STASH_{idx}__", anchor_html)

        return sanitized

    @staticmethod
    def wrap_in_page_style(
        html_body: str,
        font_size: int = 15,
        text_color: str = "#cdd6f4",
        bg_color: str = "#181825",
        canvas_bg: Optional[str] = None,
        border_color: Optional[str] = None,
        is_dark_surface: Optional[bool] = None
    ) -> str:
        clean_body = TextParser.extract_body_inner(html_body)

        is_dark = (bg_color == "#181825") if is_dark_surface is None else is_dark_surface
        resolved_canvas = canvas_bg or ("#11111b" if is_dark else "#eef0f4")
        resolved_border = border_color or ("#313244" if is_dark else "#d0d7de")

        clean_body = TextParser.sanitize_theme_colors(clean_body, is_dark, target_text_color=text_color)

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            background-color: {resolved_canvas};
            margin: 0;
            padding: 16px 8px;
            font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Roboto", sans-serif;
            font-size: {font_size}px;
            color: {text_color};
            word-wrap: break-word;
            overflow-wrap: break-word;
        }}
        .notebook-sheet {{
            background-color: {bg_color};
            padding: 28px 36px;
            border-radius: 10px;
            border: 1px solid {resolved_border};
            line-height: 1.7;
            color: {text_color};
            word-wrap: break-word;
            overflow-wrap: break-word;
        }}
        .notebook-sheet p, .notebook-sheet pre, .notebook-sheet li {{
            margin: 0 0 12px 0;
            white-space: pre-wrap;
        }}
        a {{ text-decoration: none; }}
    </style>
</head>
<body>
    <div class="notebook-sheet">
        {clean_body}
    </div>
</body>
</html>"""