from posthog.hogql import ast
from posthog.hogql.parser import parse_select
from posthog.hogql.printer import to_printed_hogql
from posthog.hogql.query import execute_hogql_query
from posthog.hogql_queries.query_runner import QueryRunner
from posthog.schema import (
    CachedSyncedArtifactsQueryResponse,
    SyncedArtifactsQuery,
    SyncedArtifactsQueryResponse,
    SyncedArtifactsResponseItem,
)


class SyncedArtifactsQueryRunner(QueryRunner):
    query: SyncedArtifactsQuery
    response: SyncedArtifactsQueryResponse
    cached_response: CachedSyncedArtifactsQueryResponse

    def calculate(self):
        query = self.to_query()
        hogql = to_printed_hogql(query, self.team)

        response = execute_hogql_query(
            query_type="SyncedArtifactsQuery",
            query=query,
            team=self.team,
            timings=self.timings,
            modifiers=self.modifiers,
            limit_context=self.limit_context,
        )

        results: list[SyncedArtifactsResponseItem] = []
        for row in response.results:
            results.append(SyncedArtifactsResponseItem(id=row[0]))

        return SyncedArtifactsQueryResponse(
            results=results,
            timings=response.timings,
            hogql=hogql,
            modifiers=self.modifiers,
        )

    def to_query(self) -> ast.SelectQuery | ast.SelectSetQuery:
        return parse_select(
            """
            SELECT
                argMax(DISTINCT artifact_id, timestamp) AS synced_artifact_id
            FROM
                codebase_embeddings
            WHERE
                user_id = {user_id} AND codebase_id = {codebase_id} AND artifact_id IN {artifact_ids}
            GROUP BY
                artifact_id
            """,
            placeholders={
                "user_id": ast.Constant(value=self.query.userId),
                "codebase_id": ast.Constant(value=self.query.codebaseId),
                "artifact_ids": ast.Array(
                    exprs=[ast.Constant(value=artifact_id) for artifact_id in self.query.artifactIds]
                ),
            },
        )
