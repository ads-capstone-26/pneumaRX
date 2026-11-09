"""Explicit dataset semantics shared by preparation and query components."""
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def identifier(value: str) -> str:
    if not re.fullmatch(r'[a-z][a-z0-9_]*', value):
        raise ValueError(f'Use a lower-case SQL identifier: {value!r}')
    return value


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ColumnDefinition(StrictModel):
    type: str = 'VARCHAR'
    description: str = ''
    role: str = ''
    unit: str | None = None

    @model_validator(mode='after')
    def valid_type(self):
        if not re.fullmatch(r'(VARCHAR|BOOLEAN|SMALLINT|INTEGER|BIGINT|DOUBLE|FLOAT|DATE|TIMESTAMP|DECIMAL\(\d+,\d+\))', self.type):
            raise ValueError('Unsupported column type: ' + self.type)
        return self


class TableDefinition(StrictModel):
    description: str = ''
    grain: str = ''
    columns: dict[str, ColumnDefinition]
    primary_key: list[str] = Field(default_factory=list)
    required: bool = True


class Relation(StrictModel):
    table: str
    column: str
    parent_table: str
    parent_column: str


class Convention(StrictModel):
    id: str
    rule: str
    tables: list[str] = Field(default_factory=list)


class Capability(StrictModel):
    description: str
    tables: list[str] = Field(default_factory=list)
    supported: bool = True


class Terminology(StrictModel):
    event_table: str
    code_column: str
    label_column: str
    dictionary: str | None = None
    dictionary_code_column: str | None = None
    description: str = ''


class DatasetDefinition(StrictModel):
    version: Literal[1] = 1
    dataset: str
    name: str
    private: bool = True
    domain_notes: str = ''
    reference_time: str | None = None
    tables: dict[str, TableDefinition]
    relationships: list[Relation] = Field(default_factory=list)
    conventions: list[Convention] = Field(default_factory=list)
    capabilities: dict[str, Capability] = Field(default_factory=dict)
    terminology: dict[str, Terminology] = Field(default_factory=dict)

    @model_validator(mode='after')
    def validate_references(self):
        identifier(self.dataset)
        if not self.tables:
            raise ValueError('At least one table is required')
        def ref(table, column=None):
            if table not in self.tables or (column is not None and column not in self.tables[table].columns):
                raise ValueError(f'Unknown configured reference: {table}.{column}')
        for table, spec in self.tables.items():
            identifier(table)
            if not spec.columns:
                raise ValueError('Empty column definition: ' + table)
            for column in spec.columns:
                identifier(column)
            for column in spec.primary_key:
                ref(table, column)
        for link in self.relationships:
            ref(link.table, link.column)
            ref(link.parent_table, link.parent_column)
        for item in self.conventions + list(self.capabilities.values()):
            for table in item.tables:
                ref(table)
        for system in self.terminology.values():
            ref(system.event_table, system.code_column)
            ref(system.dictionary or system.event_table, system.label_column)
            if system.dictionary:
                if not system.dictionary_code_column:
                    raise ValueError('Dictionary code column required')
                ref(system.dictionary, system.dictionary_code_column)
        if self.reference_time:
            from datetime import datetime
            datetime.fromisoformat(self.reference_time)
        return self

    @classmethod
    def load(cls, path):
        return cls.model_validate(json.loads(Path(path).read_text()))

    def check_layout(self, layout):
        """Optional tables may be absent; present tables must contain configured columns."""
        issues = []
        for name, spec in self.tables.items():
            if name not in layout:
                if spec.required:
                    issues.append(f'Missing required table: {name}')
            else:
                missing = set(spec.columns) - set(layout[name])
                if missing:
                    issues.append(f'Missing columns in {name}: {sorted(missing)}')
        if issues:
            raise ValueError('; '.join(issues))
