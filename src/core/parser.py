import re
import html
from typing import Dict, Optional

ANCHOR_REGEX = re.compile(r"\[\[(.*?)\|(.*?)\]\]")
BODY_CONTENT_REGEX = re.compile(r"<body[^>]*>(.*?)</body>", re.DOTALL | re.IGNORECASE)

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
        match = BODY_CONTENT_REGEX.search(html_content)
        return match.group(1).strip() if match else html_content

    @staticmethod
    def wrap_in_page_style(html_body: str, font_size: int = 15, text_color: str = "#cdd6f4", bg_color: str = "#181825") -> str:
        clean_body = TextParser.extract_body_inner(html_body)
        
        is_dark = (bg_color == "#181825")
        canvas_bg = "#11111b" if is_dark else "#eef0f4"
        sheet_bg = "#181825" if is_dark else "#ffffff"
        border_color = "#313244" if is_dark else "#d0d7de"

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            background-color: {canvas_bg};
            margin: 0;
            padding: 20px 10px;
            font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Roboto", sans-serif;
            font-size: {font_size}px;
            color: {text_color};
            word-wrap: break-word;
            overflow-wrap: break-word;
            word-break: break-word;
        }}
        .notebook-sheet {{
            max-width: 860px;
            margin: 0 auto;
            background-color: {sheet_bg};
            padding: 30px 42px;
            border-radius: 10px;
            border: 1px solid {border_color};
            line-height: 1.7;
            word-wrap: break-word;
            overflow-wrap: break-word;
            word-break: break-word;
        }}
        p, div, span, pre, code {{
            margin: 0 0 12px 0;
            word-wrap: break-word;
            overflow-wrap: break-word;
            word-break: break-word;
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