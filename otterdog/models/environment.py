# *******************************************************************************
# Copyright (c) 2023 Eclipse Foundation and others.
# This program and the accompanying materials are made available
# under the terms of the MIT License
# which is available at https://spdx.org/licenses/MIT.html
# SPDX-License-Identifier: MIT
# *******************************************************************************

from __future__ import annotations

import dataclasses
from typing import Any, Optional

from jsonbender import bend, S, OptionalS, K, F, Filter, Forall, If  # type: ignore

from otterdog.jsonnet import JsonnetConfig
from otterdog.models import (
    ModelObject,
    ValidationContext,
    FailureType,
    LivePatch,
    LivePatchType,
    LivePatchContext,
    LivePatchHandler,
)
from otterdog.providers.github import GitHubProvider
from otterdog.utils import (
    UNSET,
    is_unset,
    is_set_and_valid,
    IndentingPrinter,
    write_patch_object_as_json,
    associate_by_key,
    Change,
)


@dataclasses.dataclass
class Environment(ModelObject):
    """
    Represents a Deployment Environment of a Repository.
    """

    id: int = dataclasses.field(metadata={"external_only": True})
    node_id: str = dataclasses.field(metadata={"external_only": True})
    name: str = dataclasses.field(metadata={"key": True})
    wait_timer: int
    reviewers: list[str]
    deployment_branch_policy: str
    branch_policies: list[str]

    @property
    def model_object_name(self) -> str:
        return "environment"

    def validate(self, context: ValidationContext, parent_object: Any) -> None:
        if not is_unset(self.wait_timer) and not (0 <= self.wait_timer <= 43200):
            context.add_failure(
                FailureType.ERROR,
                f"{self.get_model_header(parent_object)} has 'wait_timer' of value '{self.wait_timer}' "
                f"outside of supported range (0, 43200).",
            )

        if is_set_and_valid(self.deployment_branch_policy):
            if self.deployment_branch_policy not in {"all", "protected", "selected"}:
                context.add_failure(
                    FailureType.ERROR,
                    f"{self.get_model_header(parent_object)} has 'deployment_branch_policy' of value "
                    f"'{self.deployment_branch_policy}', "
                    f"only values ('all' | 'protected' | 'selected') are allowed.",
                )

            if self.deployment_branch_policy != "selected" and len(self.branch_policies) > 0:
                context.add_failure(
                    FailureType.WARNING,
                    f"{self.get_model_header(parent_object)} has 'deployment_branch_policy' set to "
                    f"'{self.deployment_branch_policy}', "
                    f"but 'branch_policies' is set to '{self.branch_policies}', "
                    f"setting will be ignored.",
                )

    def include_field_for_diff_computation(self, field: dataclasses.Field) -> bool:
        if self.deployment_branch_policy != "selected":
            if field.name in ["branch_policies"]:
                return False

        return True

    def include_field_for_patch_computation(self, field: dataclasses.Field) -> bool:
        return True

    @classmethod
    def from_model_data(cls, data: dict[str, Any]) -> Environment:
        mapping = {k: OptionalS(k, default=UNSET) for k in map(lambda x: x.name, cls.all_fields())}
        return cls(**bend(mapping, data))

    @classmethod
    def from_provider_data(cls, org_id: str, data: dict[str, Any]) -> Environment:
        mapping = cls.get_mapping_from_provider(org_id, data)
        return cls(**bend(mapping, data))

    @classmethod
    def get_mapping_from_provider(cls, org_id: str, data: dict[str, Any]) -> dict[str, Any]:
        mapping = {k: OptionalS(k, default=UNSET) for k in map(lambda x: x.name, cls.all_fields())}

        def transform_reviewers(x):
            match x["type"]:
                case "User":
                    return f'@{x["reviewer"]["login"]}'

                case "Team":
                    return f'@{org_id}/{x["reviewer"]["slug"]}'

                case _:
                    raise RuntimeError("unexpected review type '{x[\"type\"]}'")

        def transform_policy(x):
            if x is None:
                return "all"
            else:
                if x.get("protected_branches", False) is True:
                    return "protected"
                elif x.get("custom_branch_policies", False) is True:
                    return "selected"
                else:
                    raise ValueError(f"unexpected deployment_branch_policy {x}")

        mapping.update(
            {
                "wait_timer": OptionalS("protection_rules", default=[])
                >> Filter(lambda obj: obj.get("type") == "wait_timer")
                >> OptionalS(0, default={})
                >> If(OptionalS("wait_timer") != K(None), S("wait_timer"), K(0)),
                "reviewers": OptionalS("protection_rules", default=[])
                >> Filter(lambda obj: obj.get("type") == "required_reviewers")
                >> OptionalS(0, default={})
                >> OptionalS("reviewers", default=[])
                >> Forall(lambda x: transform_reviewers(x)),
                "deployment_branch_policy": OptionalS("deployment_branch_policy") >> F(lambda x: transform_policy(x)),
                "branch_policies": OptionalS("branch_policies", default=[]) >> Forall(lambda x: x["name"]),
            }
        )
        return mapping

    @classmethod
    def get_mapping_to_provider(cls, org_id: str, data: dict[str, Any], provider: GitHubProvider) -> dict[str, Any]:
        mapping: dict[str, Any] = {
            field.name: S(field.name) for field in cls.provider_fields() if not is_unset(data.get(field.name, UNSET))
        }

        if "reviewers" in mapping:
            reviewers = data["reviewers"]
            reviewer_mapping = []
            for actor_type, (
                actor_id,
                actor_node_id,
            ) in provider.get_actor_ids_with_type(reviewers):
                reviewer_mapping.append({"type": actor_type, "id": actor_id})
            mapping["reviewers"] = reviewer_mapping

        if "deployment_branch_policy" in mapping:
            deployment_branch_policy = data["deployment_branch_policy"]

            match deployment_branch_policy:
                case "all":
                    deployment_branch_policy_mapping = None

                case "protected":
                    deployment_branch_policy_mapping = {
                        "protected_branches": True,
                        "custom_branch_policies": False,
                    }

                case "selected":
                    deployment_branch_policy_mapping = {
                        "protected_branches": False,
                        "custom_branch_policies": True,
                    }

                case _:
                    raise RuntimeError(f"unexpected deployment_branch_policy '{deployment_branch_policy}'")

            mapping["deployment_branch_policy"] = deployment_branch_policy_mapping

        return mapping

    def to_jsonnet(
        self,
        printer: IndentingPrinter,
        jsonnet_config: JsonnetConfig,
        extend: bool,
        default_object: ModelObject,
    ) -> None:
        patch = self.get_patch_to(default_object)
        patch.pop("name")
        printer.print(f"orgs.{jsonnet_config.create_environment}('{self.name}')")
        write_patch_object_as_json(patch, printer)

    @classmethod
    def generate_live_patch(
        cls,
        expected_object: Optional[ModelObject],
        current_object: Optional[ModelObject],
        parent_object: Optional[ModelObject],
        context: LivePatchContext,
        handler: LivePatchHandler,
    ) -> None:
        if current_object is None:
            assert isinstance(expected_object, Environment)
            handler(LivePatch.of_addition(expected_object, parent_object, expected_object.apply_live_patch))
            return

        if expected_object is None:
            assert isinstance(current_object, Environment)
            handler(LivePatch.of_deletion(current_object, parent_object, current_object.apply_live_patch))
            return

        assert isinstance(expected_object, Environment)
        assert isinstance(current_object, Environment)

        modified_env: dict[str, Change[Any]] = expected_object.get_difference_from(current_object)

        if len(modified_env) > 0:
            handler(
                LivePatch.of_changes(
                    expected_object,
                    current_object,
                    modified_env,
                    parent_object,
                    False,
                    expected_object.apply_live_patch,
                )
            )

    @classmethod
    def generate_live_patch_of_list(
        cls,
        expected_environments: list[Environment],
        current_environments: list[Environment],
        parent_object: Optional[ModelObject],
        context: LivePatchContext,
        handler: LivePatchHandler,
    ) -> None:
        expected_environments_by_name = associate_by_key(expected_environments, lambda x: x.name)

        from .repository import Repository

        assert isinstance(parent_object, Repository)

        for current_env in current_environments:
            env_name = current_env.name

            expected_env = expected_environments_by_name.get(env_name)
            if expected_env is None:
                # if it's a repo in the form of "<orgid>.github.io", ignore a missing github-pages environment
                # as it is automatically created, there is a validation rule to warn the user about it.
                if (
                    parent_object.name.lower() == f"{context.org_id}.github.io".lower()
                    and current_env.name == "github-pages"
                ):
                    continue
                # if it's a github-pages environment and gh pages are enabled, ignore it.
                # GitHub automatically creates it, a validation warning is output if it is missing
                # in the configuration.
                elif current_env.name == "github-pages" and parent_object.gh_pages_build_type != "disabled":
                    continue
                else:
                    cls.generate_live_patch(None, current_env, parent_object, context, handler)
                    continue

            cls.generate_live_patch(expected_env, current_env, parent_object, context, handler)

            expected_environments_by_name.pop(env_name)

        for env_name, env in expected_environments_by_name.items():
            cls.generate_live_patch(env, None, parent_object, context, handler)

    @classmethod
    def apply_live_patch(cls, patch: LivePatch, org_id: str, provider: GitHubProvider) -> None:
        from .repository import Repository

        match patch.patch_type:
            case LivePatchType.ADD:
                assert isinstance(patch.expected_object, Environment)
                assert isinstance(patch.parent_object, Repository)
                provider.add_repo_environment(
                    org_id,
                    patch.parent_object.name,
                    patch.expected_object.name,
                    patch.expected_object.to_provider_data(org_id, provider),
                )

            case LivePatchType.REMOVE:
                assert isinstance(patch.current_object, Environment)
                assert isinstance(patch.parent_object, Repository)
                provider.delete_repo_environment(org_id, patch.parent_object.name, patch.current_object.name)

            case LivePatchType.CHANGE:
                assert patch.changes is not None
                assert isinstance(patch.current_object, Environment)
                assert isinstance(patch.parent_object, Repository)
                provider.update_repo_environment(
                    org_id,
                    patch.parent_object.name,
                    patch.current_object.name,
                    cls.changes_to_provider(org_id, patch.changes, provider),
                )
