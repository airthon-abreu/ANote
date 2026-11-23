import re
import html
from typing import Dict, Optional

ANCHOR_REGEX = re.compile(r"\[\[(.*?)\|(.*?)\]\]")

class TextParser:
    @staticmethod
    def to_html(
        raw_content: str,
        term_colors: Optional[Dict[str, str]] = None,
        font_size: int = 15,
        text_color: str = "#cdd6f4",
        bg_color: str = "#181825"
    ) -> str:
        if not raw_content:
            return ""

        term_colors = term_colors or {}
        paragraphs = raw_content.split("\n")
        html_paragraphs = []

        def replace_anchor(match):
            term_text = match.group(1)
            anchor_key = match.group(2)
            color = term_colors.get(anchor_key, "#89b4fa")
            return (
                f'<a href="anchor:{anchor_key}" style="background-color: {color}; color: #11111b; '
                f'padding: 2px 6px; border-radius: 4px; text-decoration: none; font-weight: bold;">{term_text}</a>'
            )

        for p in paragraphs:
            escaped = html.escape(p)
            formatted = ANCHOR_REGEX.sub(replace_anchor, escaped)
            html_paragraphs.append(f"<p style='margin: 6px 0; line-height: 1.6;'>{formatted}</p>")

        return f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: "Segoe UI", -apple-system, sans-serif;
                    font-size: {font_size}px;
                    color: {text_color};
                    background-color: {bg_color};
                }}
            </style>
        </head>
        <body>
            {''.join(html_paragraphs)}
        </body>
        </html>
        """

    @staticmethod
    def inject_anchor(raw_content: str, selected_text: str, anchor_key: str) -> str:
        target = f"[[{selected_text}|{anchor_key}]]"
        return raw_content.replace(selected_text, target, 1)