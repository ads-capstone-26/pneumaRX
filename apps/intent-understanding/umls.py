"""
Minimal client for the UMLS Terminology Services (UTS) REST API, used by
Figure 2 to expand a clinical term into synonyms and standard codes.

    term --search--> CUI(s) --atoms--> synonyms + codes per vocabulary (ICD10CM, ICD9CM, LNC, ...)

Requires UMLS_API_KEY in the environment (from a UTS account under the UMLS
license). Without a key, or on any request error, lookups return nothing and
Figure 2 falls back to dictionary-only matching. Responses are cached in
memory and optionally in a JSON file. UMLS content is licensed: keep the cache
out of version control.
"""
import json
import os
import re
from dataclasses import dataclass, field
from logging import Logger
from pathlib import Path
from typing import Any

import httpx

from pneumarx.shared.logger import formatted_log

UTS_BASE_URL = "https://uts-ws.nlm.nih.gov/rest"


@dataclass
class UMLSConcept:
    cui: str
    name: str
    synonyms: list[str] = field(default_factory=list)
    codes: dict[str, list[str]] = field(default_factory=dict)  # vocabulary -> codes


class UMLSClient:
    def close(self):
        self._client.close()

    def __init__(
        self,
        logger: Logger,
        api_key: str | None = None,
        cache_path: str | None = None,
        timeout: float = 30.0,
    ):
        self.logger = logger
        self.api_key = api_key if api_key is not None else os.getenv("UMLS_API_KEY", "")
        self.cache_path = Path(cache_path) if cache_path else None
        self._cache: dict[str, Any] = {}
        if self.cache_path and self.cache_path.exists():
            try:
                self._cache = json.loads(self.cache_path.read_text())
            except json.JSONDecodeError:
                self._cache = {}
        self._client = httpx.Client(base_url=UTS_BASE_URL, timeout=httpx.Timeout(timeout, connect=30))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def lookup(
        self,
        term: str,
        sources: tuple[str, ...] = (),
        max_concepts: int = 2,
        max_synonyms: int = 10,
    ) -> list[UMLSConcept]:
        """Best-matching concepts for `term`, with English synonyms and codes in `sources`."""
        if not self.enabled or not term.strip():
            return []
        results = self._get(
            "/search/current",
            {"string": term, "searchType": "words", "pageSize": max_concepts * 3},
        )
        hits = ((results or {}).get("result") or {}).get("results") or []
        concepts: list[UMLSConcept] = []
        for hit in hits:
            cui = hit.get("ui")
            if not cui or cui == "NONE" or any(c.cui == cui for c in concepts):
                continue
            concept = UMLSConcept(cui=cui, name=hit.get("name", ""))
            atoms = self._atoms(cui)
            synonyms: list[str] = []
            for atom in atoms:
                name = (atom.get("name") or "").strip()
                if name and len(name) <= 60 and name.lower() not in {s.lower() for s in synonyms}:
                    synonyms.append(name)
                source = atom.get("rootSource")
                code = str(atom.get("code") or "").rstrip("/").split("/")[-1]
                if source in sources and code and code != "NOCODE":
                    concept.codes.setdefault(source, [])
                    if code not in concept.codes[source]:
                        concept.codes[source].append(code)
            concept.synonyms = synonyms[:max_synonyms]
            concepts.append(concept)
            if len(concepts) >= max_concepts:
                break
        return concepts

    def _atoms(self, cui: str) -> list[dict[str, Any]]:
        atoms: list[dict[str, Any]] = []
        for page in (1, 2):
            response = self._get(
                f"/content/current/CUI/{cui}/atoms",
                {"language": "ENG", "pageSize": 100, "pageNumber": page},
            )
            batch = (response or {}).get("result") or []
            atoms.extend(batch if isinstance(batch, list) else [])
            if len(batch) < 100:
                break
        return atoms

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any] | None:
        key = path + "?" + "&".join(f"{k}={params[k]}" for k in sorted(params))
        if key in self._cache:
            return self._cache[key]
        try:
            response = self._client.get(path, params={**params, "apiKey": self.api_key})
            if response.status_code == 404:  # No atoms or no match
                data: dict[str, Any] | None = {}
            else:
                response.raise_for_status()
                data = response.json()
        except Exception as exc:
            # Never log the key: httpx errors include the request URL.
            error = re.sub(r"apiKey=[^&\s]+", "apiKey=***", str(exc))
            self.__log(f"UMLS request failed for {path}: {error}")
            return None
        self._cache[key] = data
        if self.cache_path:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(json.dumps(self._cache))
        return data

    def __log(self, message: str) -> None:
        formatted_log(self.logger, "UMLS", message)
