import re
import html
from typing import Dict, Optional

ANCHOR_REGEX = re.compile(r"\[\[(.*?)\|(.*?)\]\]")

class TextParser:
    @staticmethod
    def clean_legacy_tokens(raw_content: str, term_colors: Optional[Dict[str, str]] = None) -> str:
        """
        Converte documentos antigos com [[termo|ancora]] para HTML rico nativo,
        escondendo os códigos para sempre.
        """
        if not raw_content:
            return ""

        # Se já for HTML moderno, retorna direto
        if "<p" in raw_content or "<span" in raw_content or "<html" in raw_content:
            return raw_content

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
            html_paragraphs.append(f"<p style='margin: 4px 0;'>{formatted}</p>")

        return "".join(html_paragraphs)

    @staticmethod
    def wrap_in_page_style(html_body: str, font_size: int = 15, text_color: str = "#cdd6f4", bg_color: str = "#181825") -> str:
        """Envelopa o HTML com o tema e fontes do leitor."""
        return f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: "Segoe UI", -apple-system, sans-serif;
                    font-size: {font_size}px;
                    color: {text_color};
                    background-color: {bg_color};
                    line-height: 1.6;
                }}
            </style>
        </head>
        <body>
            {html_body}
        </body>
        </html>
        """