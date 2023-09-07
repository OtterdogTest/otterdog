# *******************************************************************************
# Copyright (c) 2023 Eclipse Foundation and others.
# This program and the accompanying materials are made available
# under the terms of the MIT License
# which is available at https://spdx.org/licenses/MIT.html
# SPDX-License-Identifier: MIT
# *******************************************************************************

from __future__ import annotations

import dataclasses
from typing import Any

from jsonbender import S, Forall, If, K  # type: ignore

from otterdog.models import ValidationContext, FailureType
from otterdog.models.workflow_settings import WorkflowSettings
from otterdog.providers.github import GitHubProvider
from otterdog.utils import is_set_and_valid


@dataclasses.dataclass
class OrganizationWorkflowSettings(WorkflowSettings):
    """
    Represents workflow settings defined on organization level.
    """

    enabled_repositories: str
    selected_repositories: list[str]

    @property
    def model_object_name(self) -> str:
        return "org_workflow_settings"

    def include_field_for_diff_computation(self, field: dataclasses.Field) -> bool:
        if self.enabled_repositories == "none":
            if field.name == "enabled_repositories":
                return True
            else:
                return False

        if field.name == "selected_repositories":
            if self.enabled_repositories == "selected":
                return True
            else:
                return False

        return super().include_field_for_diff_computation(field)

    def validate(self, context: ValidationContext, parent_object: Any) -> None:
        super().validate(context, parent_object)

        if is_set_and_valid(self.enabled_repositories):
            if self.enabled_repositories not in {"all", "none", "selected"}:
                context.add_failure(
                    FailureType.ERROR,
                    f"{self.get_model_header(parent_object)} has 'enabled_repositories' of value "
                    f"'{self.enabled_repositories}', "
                    f"only values ('all' | 'none' | 'selected') are allowed.",
                )

            if self.enabled_repositories != "selected" and len(self.selected_repositories) > 0:
                context.add_failure(
                    FailureType.WARNING,
                    f"{self.get_model_header(parent_object)} has 'enabled_repositories' set to "
                    f"'{self.enabled_repositories}', "
                    f"but 'selected_repositories' is set to '{self.selected_repositories}', "
                    f"setting will be ignored.",
                )

    @classmethod
    def get_mapping_from_provider(cls, org_id: str, data: dict[str, Any]) -> dict[str, Any]:
        mapping = super().get_mapping_from_provider(org_id, data)
        mapping.update(
            {
                "selected_repositories": If(
                    S("selected_repositories") == K(None),
                    K([]),
                    S("selected_repositories") >> Forall(lambda x: x["name"]),
                ),
            }
        )
        return mapping

    @classmethod
    def get_mapping_to_provider(cls, org_id: str, data: dict[str, Any], provider: GitHubProvider) -> dict[str, Any]:
        mapping = super().get_mapping_to_provider(org_id, data, provider)

        if "selected_repositories" in data:
            mapping.pop("selected_repositories")
            mapping["selected_repository_ids"] = K(provider.get_repo_ids(org_id, data["selected_repositories"]))

        return mapping
