import json

from posthog.clickhouse.client.execute import sync_execute
from posthog.test.base import BaseTest, ClickhouseTestMixin
from products.editor.backend.models.codebase import Codebase

from ..codebase_sync import CodebaseSyncService, SerializedArtifact


class TestCodebaseSync(ClickhouseTestMixin, BaseTest):
    def setUp(self):
        super().setUp()
        self.branch = "main"
        self.codebase = Codebase.objects.create(team=self.team, user=self.user)
        self.service = CodebaseSyncService(self.team, self.user, self.codebase, self.branch)

        """
        Root
            dir_1
                dir_2
                    dir_3
                    file_1
                    file_2
            dir_4
                file_3
                file_4
            file_5
        """
        self.server_tree: list[SerializedArtifact] = [
            {"id": "root", "type": "dir", "parent_id": None},
            {"id": "dir_1", "type": "dir", "parent_id": "root"},
            {"id": "dir_2", "type": "dir", "parent_id": "dir_1"},
            {"id": "dir_3", "type": "dir", "parent_id": "dir_2"},
            {"id": "file_1", "type": "file", "parent_id": "dir_2"},
            {"id": "file_2", "type": "file", "parent_id": "dir_2"},
            {"id": "dir_4", "type": "dir", "parent_id": "root"},
            {"id": "file_3", "type": "file", "parent_id": "dir_4"},
            {"id": "file_4", "type": "file", "parent_id": "dir_4"},
            {"id": "file_5", "type": "file", "parent_id": "root"},
        ]

    def _create_artifacts(self, tree: list[SerializedArtifact]):
        query = "INSERT INTO codebase_embeddings (team_id, user_id, codebase_id, artifact_id, chunk_id, vector, properties) VALUES "
        rows: list[str] = []

        args = {
            "team_id": self.team.id,
            "user_id": self.user.id,
            "codebase_id": self.codebase.id,
            "chunk_id": 0,
            "vector": [0.5, 0.5],
            "properties": json.dumps(
                {
                    "lineStart": 0,
                    "lineEnd": 30,
                    "path": "obfuscated_path",
                }
            ),
        }

        for idx, node in enumerate(tree):
            if node["type"] == "file":
                args.update(
                    {
                        f"artifact_id_{idx}": node["id"],
                    }
                )
                rows.append(
                    f"(%(team_id)s, %(user_id)s, %(codebase_id)s, %(artifact_id_{idx})s, %(chunk_id)s, %(vector)s, %(properties)s)"
                )

        sync_execute(query + ", ".join(rows), args, team_id=self.team.id)

    def _create_tree(self, server_tree):
        self._create_artifacts(server_tree)
        return self.service.sync(server_tree)

    def _query_server_tree(self):
        response = self.service._retrieve_server_tree()
        return [{"id": item.id, "type": item.type, "parent_id": item.parentId, "synced": False} for item in response]

    def test_sync_new_codebase(self):
        pass

    def test_sync_new_codebase_with_existing_artifacts(self):
        pass

    def test_sync_new_codebase_verifies_tree(self):
        """Broken tree should raise an error."""
        client_tree = [
            {"id": "root", "type": "dir", "parent_id": None},
            {"id": "dir", "type": "dir", "parent_id": "root2"},
        ]
        with self.assertRaises(ValueError):
            self.service.sync(client_tree)

    def test_sync_replaces_leaf_node(self):
        """
        Root
            dir_1
                file_1
                file_2 - R
                file_3 - A
        """
        self._create_tree(
            [
                {"id": "root", "type": "dir", "parent_id": None},
                {"id": "dir", "type": "dir", "parent_id": "root"},
                {"id": "file_1", "type": "file", "parent_id": "dir"},
                {"id": "file_2", "type": "file", "parent_id": "dir"},
            ]
        )

        client_tree = [
            {"id": "root_new", "type": "dir", "parent_id": None, "synced": True},
            {"id": "dir_new", "type": "dir", "parent_id": "root_new", "synced": True},
            {"id": "file_1", "type": "file", "parent_id": "dir_new", "synced": True},
            {"id": "file_3", "type": "file", "parent_id": "dir_new", "synced": False},
        ]

        diverging_nodes = self.service.sync(client_tree)
        self.assertEqual(diverging_nodes, ["file_3"])

        self.assertListEqual(self._query_server_tree(), client_tree)
