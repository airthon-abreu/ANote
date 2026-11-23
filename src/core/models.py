from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid

@dataclass
class Term:
    document_id: str
    term_text: str       # A palavra grifada (ex: "Protocolo CAN")
    anchor_key: str      # O identificador único inserido no texto (ex: "can_bus_01")
    note_content: str   # O texto explicativo que abre no painel lateral
    color: str = "#89b4fa"  # Cor padrão da marcação
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: Optional[str] = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class Document:
    title: str
    content: str        # Texto completo do documento com as tags de âncora
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: Optional[str] = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: Optional[str] = field(default_factory=lambda: datetime.now().isoformat())