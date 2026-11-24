from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid

@dataclass
class Term:
    document_id: str
    term_text: str       # A palavra grifada (ex: "Mitocôndria")
    anchor_key: str      # O identificador único inserido no texto
    note_content: str   # O texto explicativo que abre no painel lateral
    color: str = "#ffe066"  # Cor padrão: amarelo marca-texto
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: Optional[str] = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class Document:
    title: str
    content: str        # Conteúdo em HTML
    category: str = "Geral"  # Categoria/Pasta simples
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: Optional[str] = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: Optional[str] = field(default_factory=lambda: datetime.now().isoformat())