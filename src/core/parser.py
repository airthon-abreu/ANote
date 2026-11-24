import re
import html
from typing import Dict, Optional

ANCHOR_REGEX = re.compile(r"\[\[(.*?)\|(.*?)\]\]")
BODY_CONTENT_REGEX = re.compile(r"<body[^>]*>(.*?)</body>", re.DOTALL | re.IGNORECASE)

class TextParser:
    @staticmethod
    def clean_legacy_tokens(raw_content: str, term_colors: Optional[Dict[str, str]] = None) -> str:
        """
        Converte tokens legados [[termo|ancora]] para HTML com tags âncora seguras.
        Caso o conteúdo já seja HTML, atualiza as cores inline conforme o dicionário.
        """
        if not raw_content:
            return ""

        term_colors = term_colors or {}

        def replace_anchor(match):
            term_text = match.group(1)
            anchor_key = match.group(2)
            color = term_colors.get(anchor_key, "#89b4fa")
            return (
                f'<a href="anchor:{anchor_key}" style="background-color: {color}; color: #11111b; '
                f'padding: 2px 6px; border-radius: 4px; text-decoration: none; font-weight: bold;">{term_text}</a>'
            )

        # Se possuir sintaxe legada, processa
        if "[[" in raw_content and "]]" in raw_content:
            raw_content = ANCHOR_REGEX.sub(replace_anchor, raw_content)

        return raw_content

    @staticmethod
    def extract_body_inner(html_content: str) -> str:
        """Extrai o conteúdo de dentro da tag <body> para evitar duplicação de tags <html>."""
        match = BODY_CONTENT_REGEX.search(html_content)
        if match:
            return match.group(1).strip()
        return html_content

    @staticmethod
    def wrap_in_page_style(html_body: str, font_size: int = 15, text_color: str = "#cdd6f4", bg_color: str = "#181825") -> str:
        """Envelopa estritamente o corpo limpo do documento com o tema do leitor."""
        clean_body = TextParser.extract_body_inner(html_body)

        return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{
            font-family: "Segoe UI", -apple-system, BlinkMacSystemFont, "Roboto", sans-serif;
            font-size: {font_size}px;
            color: {text_color};
            background-color: {bg_color};
            line-height: 1.6;
            margin: 12px;
        }}
        p {{
            margin: 0 0 10px 0;
        }}
        a {{
            text-decoration: none;
        }}
    </style>
</head>
<body>
    {clean_body}
</body>
</html>"""