"""
Code grounding for MIMIC-III (Figure 2, between S3 and S4).

For each coded concept from S2 (a diagnosis, procedure, lab, ICU item,
medication, or microbiology value), finds the codes that actually occur in the
dataset:

    S2 lookup terms + UMLS synonyms/codes
        -> read-only lookups in the dictionary tables (d_icd_*, d_labitems, d_items)
        -> candidates ranked by how often each code is used in its event table

Code systems whose event table is not loaded are skipped. For a private
profile (credentialed MIMIC-III), usage counts stay local: they rank the
candidates but are not shown in the prompt.

S4 must pick codes from these candidates, and verify_filter_values() checks
afterwards that every chosen value occurs in the data. These are schema/value
lookups for grounding, not query execution for answering the question.
"""
import re
from dataclasses import dataclass, field
from logging import Logger
from typing import Any

from pneumarx.shared.database import DBAPI
from pneumarx_intent_understanding.mimic_profile import CodeSystem, MimicProfile
from pneumarx_intent_understanding.umls import UMLSClient
from pneumarx.shared.logger import formatted_log
from pneumarx.contracts.intent import Concept


@dataclass
class CodeCandidates:
    term: str
    code_system: str
    event_table: str
    code_columns: tuple[str, ...]
    available: bool = True  # False when the event table is not loaded
    truncated: bool = False  # More codes match than are listed
    family_sizes: dict[str, int] = field(default_factory=dict)  # 3-character ICD family -> codes in the dictionary
    alternative: bool = False  # Exact ICD title match outside the code system S2 chose (advisory)
    meaning: str = ""  # What a code of this system denotes (shown in the prompt)
    matches: list[dict[str, Any]] = field(default_factory=list)
    umls_concepts: list[dict[str, str]] = field(default_factory=list)
    search_terms: list[str] = field(default_factory=list)


class CodeLookup:
    def __init__(
        self,
        user_id: str,
        chat_id: str,
        logger: Logger,
        db_api: DBAPI,
        umls: UMLSClient | None = None,
        max_matches: int = 25,
        max_icd_matches: int = 40,
    ):
        self.user_id = user_id
        self.chat_id = chat_id
        self.logger = logger
        self.db_api = db_api
        self.umls = umls
        self.max_matches = max_matches
        self._title_cache: dict[tuple[str, str], list[tuple[str, str, str]]] = {}
        self.max_icd_matches = max_icd_matches

    # ------------------------------------------------------------------
    # Candidate lookup
    # ------------------------------------------------------------------
    def lookup(
        self,
        dataset_name: str,
        profile: MimicProfile,
        concepts: list[dict[str, Any]],
        available_tables: set[str],
        question: str = "",
    ) -> list[CodeCandidates]:
        """Candidates for every S2 concept that names a code system."""
        results: list[CodeCandidates] = []
        for concept in concepts:
            system = profile.code_systems.get(str(concept.get("code_system") or ""))
            term = str(concept.get("term") or "").strip()
            if system is None or not term:
                continue
            loaded = [table for table in system.event_tables if table in available_tables]
            candidates = CodeCandidates(
                term=term,
                code_system=system.name,
                event_table=(loaded or system.event_tables)[0],
                code_columns=system.event_code_columns,
                meaning=system.description,
            )
            if not loaded:
                candidates.available = False
                results.append(candidates)
                continue
            terms = [term] + [str(t) for t in concept.get("lookup_terms") or [] if t]
            umls_codes: dict[str, list[str]] = {}
            if self.umls is not None and self.umls.enabled:
                for umls_concept in self.umls.lookup(term, system.umls_sources):
                    candidates.umls_concepts.append({"cui": umls_concept.cui, "name": umls_concept.name})
                    terms += umls_concept.synonyms
                    for source, codes in umls_concept.codes.items():
                        umls_codes.setdefault(source, []).extend(codes)
            candidates.search_terms = _usable_terms(terms)
            try:
                candidates.matches = self._query(
                    dataset_name, system, candidates.search_terms, umls_codes, available_tables
                )
                candidates.truncated = len(candidates.matches) >= self._limit(system)
                if candidates.truncated and system.name in ("diagnosis", "procedure"):
                    candidates.family_sizes = self._family_sizes(dataset_name, system, candidates.matches)
            except Exception as exc:
                self.__log(f"Code lookup failed for '{term}': {exc}")
            if profile.private:  # Counts are derived from patient records: rank only, never pass on
                candidates.matches = [{k: v for k, v in m.items() if k != "uses"} for m in candidates.matches]
            results.append(candidates)
        results += self._exact_icd_titles(dataset_name, profile, concepts, results, available_tables)
        if question:
            results += self._spot_titles(dataset_name, profile, question, results, available_tables)
        return results

    def _spot_titles(
        self,
        dataset: str,
        profile: MimicProfile,
        question: str,
        found: list[CodeCandidates],
        available_tables: set[str],
        max_titles: int = 5,
    ) -> list[CodeCandidates]:
        """
        ICD titles that appear verbatim in the question. Clinicians write abbreviated short
        titles ("nonrupt cerebral aneurym"), which S2 may rewrite into full words that no
        dictionary search matches; the question text keeps them. Whole-word, case-insensitive
        matches of at least 8 characters; a title inside a longer matched title is dropped.
        """
        text = " " + " ".join(question.lower().split()) + " "
        known = {str(m["code"]) for c in found for m in c.matches if m.get("title_match")}
        extra: list[CodeCandidates] = []
        for name in ("diagnosis", "procedure"):
            system = profile.code_systems.get(name)
            if system is None or system.event_tables[0] not in available_tables:
                continue
            hits: dict[str, list[dict[str, Any]]] = {}
            for code, short_title, long_title in self._titles(dataset, system):
                for title in {short_title.lower().strip(), long_title.lower().strip()}:
                    if len(title) >= 8 and title in text and re.search(
                        r"(?<![a-z0-9])" + re.escape(title) + r"(?![a-z0-9])", text
                    ):
                        hits.setdefault(title, []).append(
                            {"code": code, "label": long_title, "short_title": short_title, "title_match": True})
            kept = [t for t in hits if not any(t != other and t in other for other in hits)]
            for title in sorted(kept, key=len, reverse=True)[:max_titles]:
                rows = [row for row in hits[title] if row["code"] not in known]
                if rows:
                    extra.append(CodeCandidates(
                        term=title, code_system=name, event_table=system.event_tables[0],
                        code_columns=system.event_code_columns, matches=rows, search_terms=[title],
                        alternative=True, meaning=system.description,
                    ))
        return extra

    def _titles(self, dataset: str, system: CodeSystem) -> list[tuple[str, str, str]]:
        """(code, short_title, long_title) of dictionary codes that occur in the event table; cached."""
        key = (dataset, system.name)
        if key not in self._title_cache:
            rows = self._execute(f"""
                SELECT DISTINCT d.icd9_code AS code, d.short_title, d.long_title
                FROM {dataset}."{system.dictionary}" d
                WHERE d.icd9_code IN (SELECT DISTINCT icd9_code FROM {dataset}."{system.event_tables[0]}")""", [])
            self._title_cache[key] = [(str(r["code"]), str(r["short_title"] or ""), str(r["long_title"] or "")) for r in rows]
        return self._title_cache[key]

    def _exact_icd_titles(
        self,
        dataset: str,
        profile: MimicProfile,
        concepts: list[dict[str, Any]],
        found: list[CodeCandidates],
        available_tables: set[str],
    ) -> list[CodeCandidates]:
        """
        Codes whose title (or stored value) equals a concept's term although S2 gave that
        concept another (or no) code system, e.g. "cont inv mec ven 96+ hrs" read as an ICU
        item but being the short title of an ICD-9 procedure, or "MRSA screen" read as a lab
        test but being a microbiology specimen type. Exact matches only, offered as alternatives.
        """
        extra: list[CodeCandidates] = []
        for concept in concepts:
            term = str(concept.get("term") or "").strip()
            if len(term) < 4:
                continue
            for name, system in profile.code_systems.items():
                if system.dictionary is None and system.event_tables[0] in available_tables \
                        and not any(c.code_system == name and _same_concept(c.term, term) for c in found):
                    column = system.event_code_columns[0]
                    rows = self._execute(f"""
                        SELECT "{column}" AS code, COUNT(*) AS uses, TRUE AS title_match
                        FROM {dataset}."{system.event_tables[0]}" WHERE LOWER("{column}") = ?
                        GROUP BY 1 ORDER BY uses DESC LIMIT 5""", [term.lower()])
                    if rows:
                        if profile.private:
                            rows = [{k: v for k, v in row.items() if k != "uses"} for row in rows]
                        extra.append(CodeCandidates(
                            term=term, code_system=name, event_table=system.event_tables[0],
                            code_columns=system.event_code_columns, matches=rows, search_terms=[term],
                            alternative=True, meaning=system.description,
                        ))
            for name in ("diagnosis", "procedure"):
                system = profile.code_systems.get(name)
                if system is None or system.event_tables[0] not in available_tables:
                    continue
                if any(c.code_system == name and _same_concept(c.term, term) for c in found):
                    continue  # Already looked up in this system
                event, dictionary = system.event_tables[0], system.dictionary
                rows = self._execute(f"""
                    SELECT d.icd9_code AS code, d.long_title AS label, d.short_title, COUNT(*) AS uses,
                           TRUE AS title_match
                    FROM {dataset}."{dictionary}" d JOIN {dataset}."{event}" e ON e.icd9_code = d.icd9_code
                    WHERE LOWER(d.short_title) = ? OR LOWER(d.long_title) = ?
                    GROUP BY 1, 2, 3 ORDER BY uses DESC LIMIT 5""", [term.lower(), term.lower()])
                if not rows:
                    continue
                if profile.private:
                    rows = [{k: v for k, v in row.items() if k != "uses"} for row in rows]
                extra.append(CodeCandidates(
                    term=term, code_system=name, event_table=event, code_columns=system.event_code_columns,
                    matches=rows, search_terms=[term], alternative=True, meaning=system.description,
                ))
        return extra

    def _query(
        self,
        dataset: str,
        system: CodeSystem,
        terms: list[str],
        umls_codes: dict[str, list[str]],
        available_tables: set[str],
    ) -> list[dict[str, Any]]:
        q = lambda table: f'{dataset}."{table}"'  # noqa: E731
        patterns = [f"%{term}%" for term in terms]
        if system.name in ("diagnosis", "procedure"):  # ICD-9 only, one code column
            # Clinicians often use the abbreviated short_title (e.g. 'chf nos'), so search both titles.
            event, dictionary = system.event_tables[0], system.dictionary
            title_clause = " OR ".join(["d.long_title ILIKE ? OR d.short_title ILIKE ?"] * len(patterns)) or "FALSE"
            exact_clause = " OR ".join(["LOWER(d.long_title) = ? OR LOWER(d.short_title) = ?"] * len(terms)) or "FALSE"
            exact_params = [term.lower() for term in terms for _ in range(2)]
            codes = [part for source_codes in umls_codes.values() for code in source_codes if code
                     for part in _expand_code_range(code)]
            codes = [c for c in dict.fromkeys(c.replace(".", "").upper() for c in codes) if len(c) >= 2 and "-" not in c]
            code_clause = " OR ".join(["d.icd9_code LIKE ?"] * len(codes)) or "FALSE"
            code_params = [f"{code}%" for code in codes]
            sql = f"""
                SELECT d.icd9_code AS code, d.long_title AS label, d.short_title,
                       COUNT(*) AS uses, BOOL_OR({exact_clause}) AS title_match,
                       BOOL_OR({code_clause}) AS umls_match
                FROM {q(dictionary)} d
                JOIN {q(event)} e ON e.icd9_code = d.icd9_code
                WHERE ({title_clause}) OR ({code_clause})
                GROUP BY 1, 2, 3 ORDER BY title_match DESC, uses DESC LIMIT {self._limit(system)}"""
            params = exact_params + code_params + [p for pattern in patterns for p in (pattern, pattern)] + code_params
        elif system.name == "lab":
            clause = " OR ".join(["d.label ILIKE ?"] * len(patterns)) or "FALSE"
            loincs = list(dict.fromkeys(umls_codes.get("LNC", [])))
            has_loinc = "loinc_code" in self._columns(dataset, "d_labitems")
            loinc_clause = (" OR ".join(["d.loinc_code = ?"] * len(loincs)) if has_loinc and loincs else "FALSE")
            loinc_params = loincs if has_loinc else []
            sql = f"""
                SELECT d.itemid AS code, d.label, d.fluid, d.category{", d.loinc_code" if has_loinc else ""},
                       COUNT(*) AS uses, BOOL_OR({loinc_clause}) AS umls_match
                FROM {q("d_labitems")} d JOIN {q("labevents")} e ON e.itemid = d.itemid
                WHERE ({clause}) OR ({loinc_clause})
                GROUP BY ALL ORDER BY uses DESC LIMIT {self.max_matches}"""
            params = loinc_params + patterns + loinc_params
        elif system.name == "icu_item":
            clause = " OR ".join(["label ILIKE ?"] * len(patterns))
            items = self._execute(
                f"""SELECT itemid AS code, label, category, unitname, linksto FROM {q("d_items")}
                    WHERE {clause} LIMIT 60""",
                patterns,
            )
            matches = []
            for linksto in sorted({str(row["linksto"]).lower() for row in items if row.get("linksto")}):
                if linksto not in available_tables or "itemid" not in self._columns(dataset, linksto):
                    continue
                ids = [int(row["code"]) for row in items if str(row.get("linksto")).lower() == linksto]
                counts = self._execute(
                    f"SELECT itemid, COUNT(*) AS uses FROM {q(linksto)} WHERE itemid IN ({', '.join(map(str, ids))}) GROUP BY 1",
                    [],
                )
                uses = {int(row["itemid"]): int(row["uses"]) for row in counts}
                matches += [{**row, "uses": uses[int(row["code"])]} for row in items
                            if str(row.get("linksto")).lower() == linksto and int(row["code"]) in uses]
            return sorted(matches, key=lambda row: -row["uses"])[: self.max_matches]
        else:  # free text in the event table: drug names, organisms, specimens, antibiotics
            column = system.event_code_columns[0]
            clause = " OR ".join([f'"{column}" ILIKE ?'] * len(patterns)) or "FALSE"
            sql = f"""
                SELECT "{column}" AS code, COUNT(*) AS uses FROM {q(system.event_tables[0])}
                WHERE {clause} GROUP BY 1 ORDER BY uses DESC LIMIT {self.max_matches}"""
            params = patterns
        return self._execute(sql, params)

    # ------------------------------------------------------------------
    # Verification of S4 output
    # ------------------------------------------------------------------
    def verify_filter_values(self, dataset_name: str, profile: MimicProfile, concepts: list[Concept]) -> list[str]:
        """
        Issues for filter values that do not occur in their column: text values and
        LIKE patterns, and any value on a code column (icd9_code, itemid, org_name, ...).
        Values on other non-text columns (timestamps, numbers) are range bounds such as
        "admittime >= 2104-01-01", not stored values, so they are not checked. Issues
        name only the chosen values, never other data.
        """
        code_columns = profile.code_columns | {"itemid"}
        issues: list[str] = []
        for concept in concepts:
            if not (concept.table and concept.column and concept.filter_values):
                continue
            is_code = concept.column in code_columns
            column_type = self._column_types(dataset_name, concept.table).get(concept.column, "")
            if not is_code and column_type and column_type != "VARCHAR":
                continue
            missing = []
            for value in concept.filter_values[:12]:
                if isinstance(value, bool) or value is None:
                    continue
                if isinstance(value, (int, float)) and not is_code:
                    continue  # A threshold, not a stored value
                text = str(value)
                is_pattern = isinstance(value, str) and ("%" in text or (is_code and "_" in text))
                operator = "ILIKE" if is_pattern else "="
                sql = (f'SELECT 1 FROM {dataset_name}."{concept.table}" '
                       f'WHERE CAST("{concept.column}" AS VARCHAR) {operator} ? LIMIT 1')
                try:
                    if not self._execute(sql, [text]):
                        missing.append(text)
                except Exception as exc:
                    self.__log(f"Value check failed for {concept.table}.{concept.column}: {exc}")
            if missing:
                issues.append(
                    f"Concept '{concept.term}': filter values {missing} do not occur in "
                    f"{concept.table}.{concept.column}"
                )
        return issues

    def pattern_qualifier_issues(
        self, dataset_name: str, profile: MimicProfile, question: str, concepts: list[Concept]
    ) -> list[str]:
        """
        Issues for code patterns (e.g. '250%') that are broader than a qualifier in the
        question: the question says "type 2 diabetes", some codes the pattern matches are
        titled "type II" and others "type I". A qualifier is a two-word phrase of the
        question that occurs in the titles of some matched codes while others pair its
        first word with a different one ("type I"). Uses dictionary titles only.
        """
        phrases = _phrases(question)
        issues: list[str] = []
        for concept in concepts:
            system = next((s for s in profile.code_systems.values() if concept.table in s.event_tables
                           and concept.column in s.event_code_columns and s.dictionary), None)
            if system is None or system.label_column != "long_title":
                continue
            for value in concept.filter_values:
                if not (isinstance(value, str) and "%" in value):
                    continue
                titles = [(code, long) for code, _, long in self._titles(dataset_name, system) if _like(value, code)]
                for phrase in phrases:
                    with_phrase = [code for code, title in titles if phrase in _normalize(title)]
                    # Only a contrasting qualifier counts: "type ii" against titles saying "type i"
                    first, second = phrase.split()
                    contrast = re.compile(rf" {first} (?!{second} )[a-z0-9]+ ")
                    without = [(code, title) for code, title in titles
                               if phrase not in _normalize(title) and contrast.search(_normalize(title))]
                    if with_phrase and without:
                        with_phrase, shown = sorted(with_phrase), phrase.strip()
                        examples = "; ".join(f"{code}: {title}" for code, title in without[:3])
                        issues.append(
                            f"Concept '{concept.term}': pattern '{value}' also matches {len(without)} codes "
                            f"whose titles do not say '{shown}' (e.g. {examples}). The question asks for "
                            f"'{shown}': list only the matching codes ({', '.join(with_phrase[:40])}"
                            f"{', ...' if len(with_phrase) > 40 else ''})")
                        break
        return issues

    def check_against_candidates(
        self, profile: MimicProfile, concepts: list[Concept], candidates: list[CodeCandidates]
    ) -> list[str]:
        """
        Issues for codes chosen for a coded concept that are not among that concept's
        candidates. A code can exist in the data and still be wrong (e.g. itemid 51277
        is a real lab, but not HbA1c), so existence alone is not enough.
        """
        code_columns = profile.code_columns
        issues: list[str] = []
        for concept in concepts:
            if not concept.filter_values or concept.column not in code_columns:
                continue
            match = next((c for c in candidates if c.event_table == concept.table and c.matches
                          and concept.column in c.code_columns and _same_concept(c.term, concept.term)), None)
            if match is None:
                continue
            known = {str(m["code"]).upper() for m in match.matches}
            unknown = []
            for value in concept.filter_values:
                if not any(_like(str(value), code) for code in known):
                    unknown.append(str(value))
            if unknown:
                issues.append(
                    f"Concept '{concept.term}': codes {unknown} are not among the code candidates for "
                    f"'{match.term}' ({', '.join(str(m['code']) for m in match.matches[:8])}, ...)"
                )
        # Every coded concept with candidates needs a filter on its code column somewhere.
        for candidate in candidates:
            if not candidate.matches or candidate.alternative:
                continue
            covered = any(
                c.table == candidate.event_table and c.column in candidate.code_columns and c.filter_values
                for c in concepts
            )
            if not covered:
                examples = ", ".join(str(m["code"]) for m in candidate.matches[:3])
                issues.append(
                    f"'{candidate.term}' is a coded {candidate.code_system}: add a concept filtering "
                    f"{candidate.event_table}.{candidate.code_columns[0]} with codes from its candidates "
                    f"(e.g. {examples}); a value column alone does not identify the item"
                )
        return issues

    def umls_coverage_notes(
        self, profile: MimicProfile, concepts: list[Concept], candidates: list[CodeCandidates]
    ) -> list[str]:
        """
        Advisory only (never sent back for repair): codes that UMLS links to the concept
        but the chosen codes do not cover. UMLS mappings can be broader than the concept
        (e.g. it links sepsis to meningococcemia), so the choice stays with S4.
        """
        notes: list[str] = []
        for concept in concepts:
            if not concept.filter_values or concept.column not in profile.code_columns:
                continue
            match = next((c for c in candidates if c.event_table == concept.table and c.matches
                          and concept.column in c.code_columns and _same_concept(c.term, concept.term)), None)
            if match is None:
                continue
            chosen = [str(v) for v in concept.filter_values]
            uncovered = [str(m["code"]) for m in match.matches if m.get("umls_match")
                         and not any(_like(c, str(m["code"])) for c in chosen)]
            if uncovered:
                notes.append(f"Concept '{concept.term}': UMLS also links codes {uncovered[:10]}, not chosen")
        return notes

    def _family_sizes(self, dataset: str, system: CodeSystem, matches: list[dict[str, Any]]) -> dict[str, int]:
        """How many codes each 3-character ICD family has in the dictionary (dictionary only, no patient data)."""
        prefixes = sorted({str(m["code"])[:3] for m in matches})
        rows = self._execute(
            f"""SELECT SUBSTR(icd9_code, 1, 3) AS family, COUNT(*) AS n FROM {dataset}."{system.dictionary}"
                WHERE SUBSTR(icd9_code, 1, 3) IN ({", ".join("?" for _ in prefixes)}) GROUP BY 1 ORDER BY 1""",
            prefixes,
        )
        return {str(row["family"]): int(row["n"]) for row in rows}

    def _limit(self, system: CodeSystem) -> int:
        return self.max_icd_matches if system.name in ("diagnosis", "procedure") else self.max_matches

    def _columns(self, dataset: str, table: str) -> set[str]:
        return set(self._column_types(dataset, table))

    def _column_types(self, dataset: str, table: str) -> dict[str, str]:
        rows = self._execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = ? AND (table_schema = ? OR table_catalog = ?)",
            [table, dataset, dataset],
        )
        return {str(row["column_name"]): str(row["data_type"]).upper() for row in rows}

    def _execute(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        frame = self.db_api.execute_query(self.user_id, self.chat_id, sql, tuple(params) if params else None)
        return [
            {key: (value.item() if hasattr(value, "item") else value) for key, value in row.items()}
            for row in frame.to_dict(orient="records")
        ]

    def __log(self, message: str) -> None:
        formatted_log(self.logger, "CodeLookup", message)


def _expand_code_range(code: str, max_span: int = 10) -> list[str]:
    """'E08-E13' -> ['E08', ..., 'E13']; wide ranges (whole chapters) are dropped."""
    match = re.fullmatch(r"([A-Z]?)(\d{2,3})-([A-Z]?)(\d{2,3})", code.strip().upper())
    if not match:
        return [code]
    letter, start, end_letter, end = match.groups()
    if letter != end_letter or len(start) != len(end) or not 0 <= int(end) - int(start) <= max_span:
        return []
    return [f"{letter}{number:0{len(start)}d}" for number in range(int(start), int(end) + 1)]


def refusal_title_issues(grounding: dict[str, Any], candidates: list[CodeCandidates]) -> list[str]:
    """
    An "unanswerable" verdict for a concept whose phrase exactly matches a code title or a
    stored value that occurs in the data (e.g. "long-term use anticoagul" read as a
    medication, although it is the short title of diagnosis V58.61): worth one S4 repair round.
    """
    if grounding.get("answerable") is not False:
        return []
    missing = [str(m) for m in grounding.get("missing_concepts") or []]
    reason = str(grounding.get("unanswerable_reason") or "").lower()
    issues = []
    for c in candidates:
        exact = [m for m in c.matches if m.get("title_match")]
        if not exact:
            continue
        named = (any(_same_concept(c.term, m) or _word_overlap(c.term, m) for m in missing)
                 or c.term.lower() in reason or not missing)
        if not named:
            continue
        codes = ", ".join(
            f"{m['code']} ({m.get('short_title') or m.get('label')})" if m.get("short_title") or m.get("label")
            else f"'{m['code']}'" for m in exact[:5]
        )
        issues.append(
            f"'{c.term}' exactly matches {c.code_system} value(s) {codes}, which occur in "
            f"{c.event_table}.{c.code_columns[0]}: map the concept there instead of declaring it missing, "
            "then re-check whether the request is answerable."
        )
    return issues


def _word_overlap(title: str, phrase: str, threshold: float = 0.6) -> bool:
    """True if most words of `title` start like a word of `phrase` ("aneurym" ~ "aneurysm")."""
    stems = lambda text: {w[:4] for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) >= 3}  # noqa: E731
    title_stems = stems(title)
    return bool(title_stems) and len(title_stems & stems(phrase)) / len(title_stems) >= threshold


_ROMAN = {"1": "i", "2": "ii", "3": "iii", "4": "iv", "5": "v"}
_STOPWORDS = {"a", "an", "the", "of", "in", "on", "with", "without", "and", "or", "to", "for", "by", "at",
              "is", "was", "were", "are", "be", "been", "who", "what", "which", "how", "many", "much", "that",
              "patients", "patient", "had", "has", "have", "did", "do", "does", "any", "all"}


def _normalize(text: str) -> str:
    """Lowercase words, with 'type 2' / 'stage 3' written as roman numerals as in ICD-9 titles."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return " " + " ".join(_ROMAN.get(w, w) if i and words[i - 1] in ("type", "stage", "grade") else w
                          for i, w in enumerate(words)) + " "


def _phrases(question: str) -> list[str]:
    """Two-word phrases of the question without stopwords, padded for whole-word matching."""
    words = _normalize(question).split()
    return [f" {a} {b} " for a, b in zip(words, words[1:]) if a not in _STOPWORDS and b not in _STOPWORDS]


def _like(pattern: str, value: str) -> bool:
    """Case-insensitive SQL LIKE ('%' and '_' wildcards); a plain value must match exactly."""
    regex = "".join(".*" if ch == "%" else "." if ch == "_" else re.escape(ch) for ch in pattern.upper())
    return re.fullmatch(regex, value.upper()) is not None


def _same_concept(a: str, b: str) -> bool:
    a, b = a.lower().strip(), b.lower().strip()
    return a == b or a in b or b in a


def _usable_terms(terms: list[str], limit: int = 12) -> list[str]:
    """Deduplicated search phrases; very short tokens (e.g. 'DM') would match too broadly."""
    usable: list[str] = []
    for term in terms:
        cleaned = " ".join(term.replace("%", " ").replace("_", " ").split())
        if len(cleaned) >= 4 and cleaned.lower() not in {u.lower() for u in usable}:
            usable.append(cleaned)
    return usable[:limit]


def format_candidates(candidates: list[CodeCandidates], show_counts: bool = True) -> str:
    """Renders candidates for the S4 prompt; without counts for credentialed data."""
    if not candidates:
        return "(none)"
    blocks = []
    for c in candidates:
        note = "; exact title/value match - an alternative to the code system first assumed" if c.alternative else ""
        meaning = f": {c.meaning}" if c.meaning else ""
        lines = [
            f"## '{c.term}' ({c.code_system}{meaning}; filter {c.event_table}.{'+'.join(c.code_columns)}{note})",
            f"Searched: {', '.join(c.search_terms)}",
        ]
        if not c.available:
            lines.append(f"{c.event_table} is not loaded in this dataset: this concept cannot be answered from it.")
            blocks.append("\n".join(lines))
            continue
        if c.umls_concepts:
            lines.append("UMLS concepts: " + "; ".join(f"{u['cui']} {u['name']}" for u in c.umls_concepts))
        if c.matches:
            lines.append("Codes present in this dataset (most used first):")
            if c.truncated:
                lines.append(
                    f"(Only the first {len(c.matches)} matching codes are listed; more exist. To cover a code "
                    "family, use LIKE patterns on the code column: '%' = any characters, '_' = exactly one, "
                    "e.g. '250%' or '410_1'.)"
                )
                if c.family_sizes:
                    lines.append("Code families among the matches (codes per family in the dictionary): "
                                 + ", ".join(f"{family}: {n}" for family, n in c.family_sizes.items()))
            for m in c.matches:
                details = ", ".join(f"{k}={v}" for k, v in m.items() if k not in ("code", "uses") and v not in (None, ""))
                lines.append(f"- {m['code']} | {details}" + (f" | uses={m['uses']}" if show_counts and 'uses' in m else ""))
        else:
            lines.append("No matching codes found in this dataset.")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)
