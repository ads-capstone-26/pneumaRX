"""intent-understanding: interpretation, catalog/code grounding, bounded repair and decision.

No chat server, Postgres, embedding index or generic retriever is imported.
The clinical interpretation and decision rules are migrated from the original Figure 2.
"""
import re
from dataclasses import dataclass, field
from logging import Logger
from time import time
from typing import Any

from pneumarx.shared.database import DBAPI
from pneumarx.shared.llm import LanguageModelAPI
from pneumarx_intent_understanding.code_lookup import (
    CodeCandidates,
    CodeLookup,
    format_candidates,
    refusal_title_issues,
)
from pneumarx_intent_understanding.mimic_profile import MimicProfile, get_profile
from pneumarx_intent_understanding.prompt_factory import IntentPromptFactory
from pneumarx_intent_understanding.umls import UMLSClient
from pneumarx_intent_understanding.retrieval import TableCandidateRetriever
from pneumarx_intent_understanding.validator import (
    decide,
    drop_key_only_tables,
    repairable_issues,
    unsupported_refusal,
    validate_grounding,
)
from pneumarx.shared.config import Config
from pneumarx.shared.logger import formatted_log
from pneumarx.shared.parser import parse_json
from pneumarx.contracts.intent import (
    AdjustmentRequest,
    Figure2Result,
    JoinPath,
    ColumnInfo,
    IntentSpec,
    TableInfo,
)
from pneumarx.shared.messages import LLMMessage
from pneumarx.shared.options import LLMOption
from pneumarx.shared.roles import Role
from pneumarx.shared.names import clean_column_table_name


@dataclass
class PreparationContext:
    """Intermediate state of one prepare() call, kept for debugging, evaluation, and adjustment."""

    question: str
    dataset_name: str
    profile: MimicProfile | None = None
    available_tables: set[str] = field(default_factory=set)
    memory_entries: list[dict[str, Any]] = field(default_factory=list)
    interpretation: dict[str, Any] = field(default_factory=dict)
    search_queries: list[str] = field(default_factory=list)
    tables: list[TableInfo] = field(default_factory=list)
    families: dict[str, list[str]] = field(default_factory=dict)
    join_hints: str = ""
    join_paths: list[JoinPath] = field(default_factory=list)
    grounding: dict[str, Any] = field(default_factory=dict)
    code_candidates: list[CodeCandidates] = field(default_factory=list)
    repair_issues: list[str] = field(default_factory=list)
    timings: dict[str, float] = field(default_factory=dict)
    retrieval: dict[str, Any] = field(default_factory=dict)


class IntentPreparer:
    def __init__(
        self,
        user_id: str,
        chat_id: str,
        config: Config,
        logger: Logger,
        db_api: DBAPI,
        language_model_api: LanguageModelAPI,
        sample_size: int = 3,
        clarification_threshold: float = 0.7,
        umls: UMLSClient | None = None,
        allow_private_llm: bool = False,
        table_retrieval: str = "bm25",
        table_top_k: int = 5,
        dataset_definition=None,
    ):
        self.dataset_definition = dataset_definition
        self.user_id = user_id
        self.chat_id = chat_id
        self.config = config
        self.logger = logger
        self.db_api = db_api
        self.language_model_api = language_model_api
        self.sample_size = sample_size
        self.clarification_threshold = clarification_threshold
        self.allow_private_llm = allow_private_llm
        self.table_retriever = TableCandidateRetriever(table_retrieval, table_top_k)
        self._snapshot_checked: set[str] = set()

        self.prompt_factory = IntentPromptFactory()
        self.umls = umls if umls is not None else UMLSClient(logger)
        self.code_lookup = CodeLookup(user_id, chat_id, logger, db_api, self.umls)
        self.last_context: PreparationContext | None = None

    def prepare(
        self,
        question: str,
        dataset_name: str,
        history: list[LLMMessage] | None = None,
        memory_group_ids: list[str] | None = None,
        use_memory: bool = True,
        interactive: bool = False,
        adjustment_request: AdjustmentRequest | None = None,
        candidate_tables: list[str] | None = None,
    ) -> Figure2Result:
        """
        Runs the Figure 2 pipeline. With `adjustment_request`, reuses the previous
        interpretation for the same question and re-grounds with the requested adjustment.
        candidate_tables optionally restricts schema evidence and validation to a retrieved
        subset. Terminology tools still see actual database availability. None uses the
        configured retrieval mode (BM25 top-5 by default; all for catalog comparison).
        """
        question = question.strip()
        if not question:
            raise ValueError("No question provided.")
        history = history or []
        if self.dataset_definition is not None:
            from .dataset_profile import make_profile
            if self.dataset_definition.dataset != dataset_name:
                raise ValueError("Dataset configuration does not match requested dataset")
            self.dataset_definition.check_layout(self._table_layouts(dataset_name))
            profile = make_profile(self.dataset_definition)
        else:
            profile = get_profile(dataset_name)
        if profile is None:
            raise ValueError("Unsupported dataset profile")
        if profile is not None and profile.private and not self.allow_private_llm:
            raise PermissionError(
                f"{dataset_name} is credentialed {profile.name} data. Figure 2 sends the question, schema "
                "documentation, and dictionary entries to the configured LLM; set allow_private_llm=True only "
                "for an LLM endpoint approved under the PhysioNet data use agreement."
            )

        if self.dataset_definition is not None:
            from .dataset_profile import ConfiguredCodeLookup
            self.code_lookup = ConfiguredCodeLookup(self.user_id, self.chat_id, self.logger, self.db_api)
        elif dataset_name == "hospital":
            from .hospital_profile import bind_reference_date, HospitalCodeLookup
            profile = bind_reference_date(profile, self.db_api.db)
            if not isinstance(self.code_lookup, HospitalCodeLookup):
                self.code_lookup = HospitalCodeLookup(self.user_id, self.chat_id, self.logger, self.db_api)
        elif type(self.code_lookup) is not CodeLookup:
            self.code_lookup = CodeLookup(self.user_id, self.chat_id, self.logger, self.db_api, self.umls)
        previous = self.last_context
        reuse = (
            adjustment_request is not None
            and previous is not None
            and previous.question == question
            and previous.dataset_name == dataset_name
        )
        if dataset_name == "mimic_iii" and self.dataset_definition is None:
            self._check_snapshot(dataset_name)
        context = PreparationContext(question=question, dataset_name=dataset_name, profile=profile)
        context.available_tables = set(self._table_layouts(dataset_name)) if profile else set()

        # S1: memory
        start = time()
        if reuse:
            context.memory_entries = previous.memory_entries
        elif use_memory and self.config.ENABLE_MEMORY_LAYER:
            try:
                context.memory_entries = self.db_api.retrieve_memory_context(
                    self.user_id,
                    dataset_name,
                    memory_group_ids or [],
                    question,
                    self.config.MEMORY_RETRIEVAL_TOP_K,
                )
            except Exception as exc:
                self.__log(f"Memory retrieval failed, continuing without it: {exc}")
        context.timings["memory"] = time() - start

        # S2: interpret
        start = time()
        if reuse:
            context.interpretation = previous.interpretation
        else:
            context.interpretation = self._chat_json(
                self.prompt_factory.get_interpretation_sys_prompt(
                    {name: system.description for name, system in profile.code_systems.items()}
                    if profile else None
                ),
                self.prompt_factory.get_interpretation_user_prompt(
                    question, history, context.memory_entries
                ),
            )
        context.timings["interpret"] = time() - start

        # S3: retrieve
        start = time()
        context.search_queries = self._search_queries(question, context.interpretation, adjustment_request)
        self._retrieve(context, candidate_tables)
        context.timings["retrieve"] = time() - start

        # S3b: code grounding (MIMIC): codes that actually occur, from dictionaries + UMLS
        start = time()
        if profile:
            context.code_candidates = self.code_lookup.lookup(
                dataset_name, profile, context.interpretation.get("concepts") or [], context.available_tables,
                question=question,
            )
        context.timings["codes"] = time() - start

        # S4: ground
        start = time()
        messages = [
            LLMMessage(role=Role.SYSTEM.value, content=self.prompt_factory.get_grounding_sys_prompt()),
            LLMMessage(
                role=Role.USER.value,
                content=self.prompt_factory.get_grounding_user_prompt(
                    question,
                    context.interpretation,
                    context.tables,
                    context.families,
                    context.join_hints,
                    context.memory_entries,
                    adjustment_request,
                    domain_notes=self._domain_notes(context),
                    code_candidates=format_candidates(context.code_candidates, show_counts=not profile.private)
                    if profile else "",
                ),
            ),
        ]
        context.grounding, messages = self._converse_json(messages)
        context.timings["ground"] = time() - start

        # S5: validate; on failure, one repair round back to S4
        start = time()
        issues = self._validation_issues(context)
        if issues:
            context.repair_issues = issues
            self.__log(f"Repairing grounding: {issues}")
            messages.append(LLMMessage(role=Role.USER.value, content=self.prompt_factory.get_repair_prompt(issues)))
            repaired, messages = self._converse_json(messages)
            if repaired:
                context.grounding = repaired
        value_issues = []
        if profile:  # Remaining issues become notes in the spec, plus advisory UMLS coverage notes
            concepts, _, _, _ = validate_grounding(context.grounding, context.tables)
            value_issues = self._value_issues(context) + self.code_lookup.umls_coverage_notes(
                profile, concepts, context.code_candidates
            )
        context.timings["validate"] = time() - start

        # S6: decide
        self.last_context = context
        result = decide(
            question,
            dataset_name,
            context.interpretation,
            context.grounding,
            context.tables,
            context.join_paths,
            [entry["memory_id"] for entry in context.memory_entries if "memory_id" in entry],
            interactive,
            self.clarification_threshold,
            value_issues=value_issues,
        )
        if profile is not None and isinstance(result, IntentSpec):
            result = drop_key_only_tables(result, profile.key_only_tables)
            # Figure 3 follows the Figure 1 conventions that apply to the tables it will query
            result = result.model_copy(update={"query_conventions": profile.conventions_for(result.required_tables)})
        self.__log(f"Result: {result.status} (timings: { {k: round(v, 1) for k, v in context.timings.items()} })")
        return result

    # ------------------------------------------------------------------
    # S3 helpers
    # ------------------------------------------------------------------
    def _search_queries(
        self,
        question: str,
        interpretation: dict[str, Any],
        adjustment_request: AdjustmentRequest | None,
    ) -> list[str]:
        """The raw question plus the interpreter's queries (and missing concepts on adjustment)."""
        queries = [question]
        queries += [q for q in interpretation.get("search_queries") or [] if isinstance(q, str)]
        if adjustment_request is not None:
            queries += adjustment_request.missing_concepts
        return list(dict.fromkeys(q.strip() for q in queries if q and q.strip()))



    # --- Catalog path (MIMIC-III) ---------------------------------------

    # --- Search path (datasets without a MIMIC profile) ------------------
    # Not used on MIMIC-III: the hybrid index, partition families (e.g. one table
    # per year or state in legal), and value-overlap join discovery.



    # --- MIMIC helpers ---------------------------------------------------

    def _retrieve(self, context: PreparationContext, candidate_tables: list[str] | None = None) -> None:
        # Read only table/column metadata, never SELECT patient sample rows.
        context.tables = [_with_docs(t, context.profile)
                          for t in self.db_api.catalog(context.dataset_name)]
        if candidate_tables is None:
            candidate_tables, ranking = self.table_retriever.select(context.question, context.tables,
                profile={} if getattr(context.profile, "definition", None) is not None or context.dataset_name != "mimic_iii" else None)
            method = self.table_retriever.method
        else:
            ranking, method = [], 'explicit'
        context.retrieval = {'method': method, 'query': context.question,
                             'catalog_count': len(context.tables),
                             'top_k': self.table_retriever.top_k if method == 'bm25' else None,
                             'candidate_tables': list(candidate_tables), 'ranking': ranking,
                             'fallback_to_full_catalog': False}
        if candidate_tables is not None:
            if not candidate_tables or any(not isinstance(name, str) for name in candidate_tables):
                raise ValueError("Candidate tables must be a nonempty list of table names")
            wanted = set(candidate_tables)
            unknown = wanted - {table.name for table in context.tables}
            if unknown:
                raise ValueError(f"Unknown candidate tables: {sorted(unknown)}")
            # Preserve catalog ordering, so the intervention changes membership only.
            context.tables = [table for table in context.tables if table.name in wanted]
        columns = {t.name: {c.name for c in t.columns} for t in context.tables}
        context.join_paths = context.profile.key_join_paths(columns, list(columns))
        context.join_hints = "\n".join(
            f"- {p.left_table}.{p.left_column} = {p.right_table}.{p.right_column}"
            for p in context.join_paths)

    def _domain_notes(self, context: PreparationContext) -> str:
        if context.profile is None:
            return ""
        notes = [context.profile.domain_notes,
                 context.profile.conventions_notes(context.available_tables),
                 context.profile.unavailable_notes(context.available_tables)]
        return "\n\n".join(note for note in notes if note)

    def _check_snapshot(self, dataset_name: str) -> None:
        """Warns once per dataset if the local data differ from Figure 1's shared snapshot."""
        if dataset_name in self._snapshot_checked:
            return
        self._snapshot_checked.add(dataset_name)
        try:
            from pneumarx_data.snapshot import compare_with_snapshot
            result = compare_with_snapshot(self.db_api.database_path) if self.db_api.database_path else None
            if result is None:
                return
        except Exception as exc:  # Figure 1 module or snapshot not available
            self.__log(f"Snapshot check skipped: {exc}")
            return
        if result.status != "match":
            self.logger.warning(result.message())
        else:
            self.__log(result.message())

    def _table_layouts(self, dataset_name: str) -> dict[str, tuple[str, ...]]:
        """Ordered column names of every table in the dataset (one metadata query)."""
        try:
            self.db_api.link_dataset_tables(self.user_id, self.chat_id, dataset_name)
            columns = self.db_api.execute_query(
                self.user_id,
                self.chat_id,
                """
                SELECT table_name, column_name
                FROM information_schema.columns
                WHERE table_schema = ? OR table_catalog = ?
                ORDER BY table_name, ordinal_position
                """.strip(),
                (dataset_name, dataset_name),
            )
        except Exception as exc:
            self.__log(f"Could not read table layouts: {exc}")
            return {}
        layouts: dict[str, list[str]] = {}
        for table, column in zip(columns["table_name"], columns["column_name"]):
            layouts.setdefault(clean_column_table_name(str(table)), []).append(
                clean_column_table_name(str(column))
            )
        return {table: tuple(cols) for table, cols in layouts.items()}

    # ------------------------------------------------------------------
    # S5 helpers
    # ------------------------------------------------------------------
    def _validation_issues(self, context: PreparationContext) -> list[str]:
        issues = repairable_issues(context.grounding, context.tables)
        issues = issues or unsupported_refusal(context.grounding, context.tables)
        issues = issues or refusal_title_issues(context.grounding, context.code_candidates)
        if context.profile is not None and not issues:
            issues = self._value_issues(context)
        return issues

    def _value_issues(self, context: PreparationContext) -> list[str]:
        concepts, _, _, _ = validate_grounding(context.grounding, context.tables)
        return self.code_lookup.verify_filter_values(context.dataset_name, context.profile, concepts) + \
            self.code_lookup.check_against_candidates(context.profile, concepts, context.code_candidates) + \
            self.code_lookup.pattern_qualifier_issues(
                context.dataset_name, context.profile, context.question, concepts)

    # ------------------------------------------------------------------
    # LLM helpers
    # ------------------------------------------------------------------
    def _chat_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """One JSON-mode call, with a single retry when the output does not parse."""
        parsed, _ = self._converse_json([
            LLMMessage(role=Role.SYSTEM.value, content=system_prompt),
            LLMMessage(role=Role.USER.value, content=user_prompt),
        ])
        return parsed

    def _converse_json(self, messages: list[LLMMessage]) -> tuple[dict[str, Any], list[LLMMessage]]:
        """Continues a conversation in JSON mode; returns the parsed object and the extended messages."""
        messages = list(messages)
        response = ""
        for attempt in range(2):
            response = "".join(
                self.language_model_api.chat(messages, LLMOption(json_mode=True, stream=True))
            )
            messages.append(LLMMessage(role=Role.ASSISTANT.value, content=response))
            try:
                parsed = parse_json(response)
                if isinstance(parsed, dict):
                    return parsed, messages
                error = "the output is not a JSON object"
            except ValueError as exc:
                error = str(exc)
            self.__log(f"JSON parse failed (attempt {attempt + 1}): {error}")
            messages.append(
                LLMMessage(role=Role.USER.value, content=self.prompt_factory.get_json_retry_prompt(error))
            )
        return {}, messages

    def __log(self, message: str) -> None:
        formatted_log(self.logger, "IntentPreparer", message)


def _with_docs(table: TableInfo, profile: MimicProfile) -> TableInfo:
    """Fills missing table and column descriptions from the profile's public documentation."""
    docs = profile.table_docs.get(table.name)
    if docs is None:
        return table
    description, column_docs = docs
    return table.model_copy(update={
        "description": table.description or description,
        "columns": [
            column if column.description else ColumnInfo(
                name=column.name, type=column.type, description=column_docs.get(column.name, "")
            )
            for column in table.columns
        ],
    })


def main(argv=None):
    import argparse
    from pathlib import Path
    from pneumarx.shared.cli import add_table_retrieval_arguments, add_model_arguments, finish, failure
    from pneumarx_intent_understanding.session import preparation_session

    parser = argparse.ArgumentParser(description='Interpret a question and ground it to MIMIC schema and clinical codes.')
    add_model_arguments(parser)
    parser.add_argument('--dataset', default='mimic_iii')
    parser.add_argument('--dataset-config', type=Path)
    add_table_retrieval_arguments(parser)
    parser.add_argument('--question', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--non-interactive', action='store_true')
    args = parser.parse_args(argv)
    try:
        with preparation_session(args.db, env_file=args.env_file, model=args.model, dataset_name=args.dataset, dataset_config=args.dataset_config,
                                 allow_private_llm=args.allow_private_llm,
                              table_retrieval=args.table_retrieval, table_top_k=args.table_top_k) as (preparer, llm):
            result = preparer.prepare(args.question, args.dataset, use_memory=False,
                                      interactive=not args.non_interactive)
            return finish('intent-understanding', args.output, result.model_dump(mode='json'))
    except Exception as exc:
        return failure(exc)


if __name__ == '__main__':
    raise SystemExit(main())
