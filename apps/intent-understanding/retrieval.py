"""Local metadata BM25 candidate selection for the intent-understanding component."""
from collections import Counter
import json
import math
from pathlib import Path
import re
from statistics import mean

from pneumarx.shared.paths import PROJECT_ROOT

STOP = set('a an the of in on at for to is are was were be been by with and or as what which how many much do does did than that this during from'.split())


def catalog_documents(profile):
    """Use metadata only; omit measured values, counts and question-specific labels."""
    return {name: '\n'.join([name, table.get('description', ''), table.get('kind', '')] + [
        ' '.join([column, info.get('type', ''), info.get('description', ''),
                  info.get('role', ''), info.get('references', '')])
        for column, info in sorted(table['columns'].items())])
        for name, table in sorted(profile['tables'].items())}


def tokens(text):
    return [word for word in re.findall(r'[a-z]+|[0-9]+', text.lower()) if word not in STOP]


class BM25:
    def __init__(self, documents, k1=1.5, b=0.75):
        if not documents:
            raise ValueError('Empty catalog')
        self.terms = {name: Counter(tokens(text)) for name, text in sorted(documents.items())}
        self.lengths = {name: sum(terms.values()) for name, terms in self.terms.items()}
        self.avg_length = mean(self.lengths.values()) or 1
        self.df = Counter(term for terms in self.terms.values() for term in terms)
        self.k1, self.b = k1, b

    def rank(self, question):
        query = set(tokens(question))
        scores = []
        for name, counts in self.terms.items():
            length = self.lengths[name]
            score = 0.0
            for term in query:
                frequency = counts[term]
                if frequency:
                    idf = math.log(1 + (len(self.terms) - self.df[term] + 0.5) / (self.df[term] + 0.5))
                    score += idf * frequency * (self.k1 + 1) / (
                        frequency + self.k1 * (1 - self.b + self.b * length / self.avg_length))
            scores.append({'table': name, 'score': score})
        return sorted(scores, key=lambda item: (-item['score'], item['table']))



def documents_for_tables(tables, profile):
    """Index only actual schema plus allowlisted documentation, never measured data."""
    metadata = profile.get('tables', {})
    actual = {}
    for table in tables:
        documented = metadata.get(table.name, {})
        columns = {}
        for column in table.columns:
            info = documented.get('columns', {}).get(column.name, {})
            columns[column.name] = {
                'type': column.type,
                'description': info.get('description', column.description),
                'role': info.get('role', ''), 'references': info.get('references', '')}
        actual[table.name] = {'description': documented.get('description', table.description),
                              'kind': documented.get('kind', ''), 'columns': columns}
    return catalog_documents({'tables': actual})


class TableCandidateRetriever:
    def __init__(self, method='bm25', top_k=5, *, profile_path=None):
        if method not in {'bm25', 'all'}:
            raise ValueError('Table retrieval must be bm25 or all')
        if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
            raise ValueError('Table top-k must be a positive integer')
        self.method, self.top_k = method, top_k
        path = Path(profile_path) if profile_path is not None else PROJECT_ROOT / 'docs/mimic3/mimic3_schema_profile.json'
        self.profile = json.loads(path.read_text()) if path.is_file() else {}
        self._documents = None
        self._ranker = None

    def select(self, question, tables, *, profile=None):
        if not tables:
            raise ValueError('No tables available for retrieval')
        if self.method == 'all':
            return [t.name for t in tables], []
        documents = documents_for_tables(tables, self.profile if profile is None else profile)
        # Reuse the index across questions; refresh if the actual schema changes.
        if documents != self._documents:
            self._ranker = BM25(documents)
            self._documents = documents
        ranked = self._ranker.rank(question)[:self.top_k]
        return [row['table'] for row in ranked], ranked
