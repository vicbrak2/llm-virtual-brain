"""Proveedores de contexto (enriquecimiento de datos para el LLM)."""

import json
from abc import ABC, abstractmethod
from typing import Dict, Optional
from pathlib import Path


class ContextProvider(ABC):
    """Base para proveedores de contexto."""

    @abstractmethod
    async def enrich(self, user_msg: str, current_data: Dict) -> Dict:
        """
        Enriquecer contexto con datos externos.

        Args:
            user_msg: Mensaje del usuario.
            current_data: Contexto actual (puede estar vacío).

        Returns:
            Dict enriquecido (se pasa al LLM).
        """
        pass


class NoContext(ContextProvider):
    """Sin contexto externo (identidad, para pruebas)."""

    async def enrich(self, user_msg: str, current_data: Dict) -> Dict:
        return current_data


class GoogleSheetsContext(ContextProvider):
    """Contexto desde Google Sheets (requiere gspread + service account)."""

    def __init__(self, sheet_id: str, service_account_json: str, worksheet_name: str = "Sheet1"):
        """
        Args:
            sheet_id: ID de la Sheet.
            service_account_json: Path al JSON de service account.
            worksheet_name: Nombre de la hoja a leer.
        """
        self.sheet_id = sheet_id
        self.worksheet_name = worksheet_name
        try:
            import gspread
            self.gc = gspread.service_account(filename=service_account_json)
            self.sheet = self.gc.open_by_key(sheet_id)
        except Exception as e:
            raise ImportError(f"GoogleSheetsContext require gspread: {e}")

    async def enrich(self, user_msg: str, current_data: Dict) -> Dict:
        """Leer datos de la sheet y añadir al contexto."""
        try:
            ws = self.sheet.worksheet(self.worksheet_name)
            rows = ws.get_all_records()
            current_data["sheet_data"] = rows
            current_data["sheet_row_count"] = len(rows)
        except Exception as e:
            print(f"[context] GoogleSheets error: {e}")
        return current_data


class SQLiteContext(ContextProvider):
    """Contexto desde SQLite local."""

    def __init__(self, db_path: str, queries: Optional[Dict[str, str]] = None):
        """
        Args:
            db_path: Path a la BD SQLite.
            queries: Dict de {nombre: SQL query} para ejecutar.
                     Si None, no ejecuta nada (pure retrieval).
        """
        self.db_path = db_path
        self.queries = queries or {}
        try:
            import sqlite3
            self.conn = sqlite3.connect(db_path)
        except Exception as e:
            raise ImportError(f"SQLiteContext require sqlite3: {e}")

    async def enrich(self, user_msg: str, current_data: Dict) -> Dict:
        """Ejecutar queries y añadir resultados al contexto."""
        try:
            cursor = self.conn.cursor()
            for query_name, sql in self.queries.items():
                cursor.execute(sql)
                rows = cursor.fetchall()
                current_data[query_name] = [dict(zip([d[0] for d in cursor.description], row)) for row in rows]
        except Exception as e:
            print(f"[context] SQLite error: {e}")
        return current_data


class PasswordVaultContext(ContextProvider):
    """
    Contexto para Password Manager: expone estructura sin contraseñas.

    Vault JSON: {categoria: [{name, username, hint}, ...]}
    """

    def __init__(self, vault_path: str):
        """
        Args:
            vault_path: Path a archivo JSON con la bóveda.
        """
        self.vault_path = Path(vault_path)
        try:
            with open(self.vault_path) as f:
                self.vault = json.load(f)
        except Exception as e:
            raise ImportError(f"PasswordVaultContext error loading vault: {e}")

    async def enrich(self, user_msg: str, current_data: Dict) -> Dict:
        """Exponer categorías y hints, NUNCA contraseñas."""
        safe_vault = {}
        for category, entries in self.vault.items():
            safe_vault[category] = [
                {
                    "name": e.get("name", ""),
                    "username": e.get("username", ""),
                    "hint": e.get("hint", "")
                }
                for e in entries
            ]
        current_data["vault_structure"] = safe_vault
        current_data["vault_note"] = "⚠️ Contraseñas NUNCA se exponen en chat"
        return current_data


class JSONFileContext(ContextProvider):
    """Contexto desde archivo JSON local."""

    def __init__(self, json_path: str, key_name: str = "data"):
        """
        Args:
            json_path: Path al archivo JSON.
            key_name: Clave bajo la cual insertar los datos en el contexto.
        """
        self.json_path = Path(json_path)
        self.key_name = key_name
        try:
            with open(self.json_path) as f:
                self.data = json.load(f)
        except Exception as e:
            raise ImportError(f"JSONFileContext error: {e}")

    async def enrich(self, user_msg: str, current_data: Dict) -> Dict:
        """Añadir datos del JSON al contexto."""
        current_data[self.key_name] = self.data
        return current_data


def context_from_dict(config: Dict) -> ContextProvider:
    """Construir ContextProvider desde dict de config."""
    ctx_type = config.get("type", "none").lower()

    if ctx_type == "gsheets":
        return GoogleSheetsContext(
            sheet_id=config.get("sheet_id", ""),
            service_account_json=config.get("service_account_json", ""),
            worksheet_name=config.get("worksheet_name", "Sheet1")
        )
    elif ctx_type == "sqlite":
        return SQLiteContext(
            db_path=config.get("db_path", ""),
            queries=config.get("queries", {})
        )
    elif ctx_type == "password_vault":
        return PasswordVaultContext(vault_path=config.get("vault_path", ""))
    elif ctx_type == "json":
        return JSONFileContext(
            json_path=config.get("json_path", ""),
            key_name=config.get("key_name", "data")
        )
    else:
        return NoContext()
