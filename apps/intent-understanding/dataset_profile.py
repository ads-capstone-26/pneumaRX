"""Consume the data-preparation contract without MIMIC-specific naming assumptions."""
from dataclasses import dataclass

from pneumarx.contracts.dataset import DatasetDefinition
from pneumarx.contracts.intent import JoinPath
from .mimic_profile import MimicProfile, CodeSystem
from .code_lookup import CodeLookup, CodeCandidates


@dataclass(frozen=True)
class ConfiguredProfile(MimicProfile):
    definition: DatasetDefinition | None = None

    def key_join_paths(self, columns_by_table, tables):
        return [JoinPath(left_table=r.table, left_column=r.column,
                         right_table=r.parent_table, right_column=r.parent_column, score=1.0)
                for r in self.definition.relationships
                if r.table in tables and r.parent_table in tables
                and r.column in columns_by_table[r.table] and r.parent_column in columns_by_table[r.parent_table]]

    def unavailable_notes(self, available_tables):
        lines = [super().unavailable_notes(available_tables)]
        for name, cap in self.definition.capabilities.items():
            if not cap.supported or not set(cap.tables) <= available_tables:
                lines.append(f'Unavailable capability {name}: {cap.description}. Do not infer it from unrelated tables.')
        return '\n'.join(filter(None, lines))


def make_profile(definition):
    docs = {name: (table.description + (f' Row grain: {table.grain}.' if table.grain else ''),
                   {col: spec.description + (f' Role: {spec.role}.' if spec.role else '') + (f' Unit: {spec.unit}.' if spec.unit else '')
                    for col, spec in table.columns.items()}) for name, table in definition.tables.items()}
    conventions = [{'id': c.id, 'rule': c.rule, 'tables': set(c.tables or definition.tables)} for c in definition.conventions]
    if definition.reference_time:
        conventions.append({'id': 'dataset_reference_time', 'tables': set(definition.tables),
                            'rule': f'For this frozen dataset, current_time/today is {definition.reference_time}; use it instead of system time.'})
    systems = {name: CodeSystem(name, (s.event_table,), (s.code_column,), s.dictionary,
                                (s.dictionary_code_column,) if s.dictionary else (), s.label_column, (), s.description)
               for name, s in definition.terminology.items()}
    return ConfiguredProfile(name=definition.name, code_systems=systems, key_columns=(),
                             domain_notes=definition.domain_notes, private=definition.private, catalog=True,
                             table_docs=docs, conventions=tuple(conventions),
                             knowledge_source='Explicit dataset configuration', definition=definition)


class ConfiguredCodeLookup(CodeLookup):
    """Bounded parameterized lookup against configured code/label columns only."""
    def lookup(self, dataset_name, profile, concepts, available_tables, question=''):
        results = []
        for concept in concepts:
            system = profile.code_systems.get(str(concept.get('code_system') or ''))
            term = str(concept.get('term') or '').strip()
            if not system or not term:
                continue
            table = system.dictionary or system.event_tables[0]
            code = (system.dictionary_code_columns or system.event_code_columns)[0]
            label = system.label_column
            candidate = CodeCandidates(term=term, code_system=system.name, event_table=system.event_tables[0],
                                       code_columns=system.event_code_columns, meaning=system.description)
            results.append(candidate)
            if table not in available_tables or system.event_tables[0] not in available_tables:
                candidate.available = False
                continue
            terms = list(dict.fromkeys([term] + [str(t) for t in concept.get('lookup_terms', []) if t]))[:12]
            candidate.search_terms = terms
            clause = ' OR '.join([f'(CAST(d."{code}" AS VARCHAR) ILIKE ? OR CAST(d."{label}" AS VARCHAR) ILIKE ?)'] * len(terms))
            params = [f'%{t}%' for t in terms for _ in range(2)]
            exists = ''
            if system.dictionary:
                exists = (f' AND EXISTS (SELECT 1 FROM {dataset_name}."{system.event_tables[0]}" e '
                          f'WHERE e."{system.event_code_columns[0]}" = d."{code}")')
            rows = self._execute(f'SELECT DISTINCT d."{code}" AS code, d."{label}" AS label FROM '
                                 f'{dataset_name}."{table}" d WHERE ({clause}){exists} ORDER BY 1 LIMIT 41', params)
            candidate.matches, candidate.truncated = rows[:40], len(rows) > 40
        return results

    def _titles(self, dataset, system):
        # Reuse qualifier checks without ICD-9-specific dictionary column names.
        table = system.dictionary or system.event_tables[0]
        code = (system.dictionary_code_columns or system.event_code_columns)[0]
        label = system.label_column
        rows = self._execute(f'SELECT DISTINCT "{code}" AS code, "{label}" AS label FROM {dataset}."{table}"', [])
        return [(str(r['code']), str(r['label'] or ''), str(r['label'] or '')) for r in rows]
