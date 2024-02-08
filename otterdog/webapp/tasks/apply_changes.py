#  *******************************************************************************
#  Copyright (c) 2023-2024 Eclipse Foundation and others.
#  This program and the accompanying materials are made available
#  under the terms of the Eclipse Public License 2.0
#  which is available at http://www.eclipse.org/legal/epl-v20.html
#  SPDX-License-Identifier: EPL-2.0
#  *******************************************************************************

import dataclasses
from io import StringIO
from tempfile import TemporaryDirectory

from quart import render_template

from otterdog.operations.apply import ApplyOperation
from otterdog.utils import IndentingPrinter, LogLevel
from otterdog.webapp.db.models import TaskModel
from otterdog.webapp.db.service import get_organization_config_by_installation_id
from otterdog.webapp.tasks import Task
from otterdog.webapp.utils import (
    escape_for_github,
    fetch_config,
    get_organization_config,
    get_otterdog_config,
)
from otterdog.webapp.webhook.github_models import PullRequest, Repository


@dataclasses.dataclass(repr=False)
class ApplyChangesTask(Task[None]):
    """Applies changes from a merged PR and adds the result as a comment."""

    installation_id: int
    org_id: str
    repository: Repository
    pull_request: PullRequest

    def create_task_model(self):
        return TaskModel(
            type="ApplyChangesTask",
            org_id=self.org_id,
            repo_name=self.repository.name,
            pull_request=self.pull_request.number,
            status="created",
        )

    async def _execute(self) -> None:
        if self.pull_request.base.ref != self.repository.default_branch:
            self.logger.debug(
                "pull request merged into '%s' which is not the default branch '%s', ignoring",
                self.pull_request.base.ref,
                self.repository.default_branch,
            )
            return

        assert self.pull_request.merged is True
        assert self.pull_request.merge_commit_sha is not None

        self.logger.info(
            "applying merged pull request #%d of repo '%s'", self.pull_request.number, self.repository.full_name
        )

        otterdog_config = await get_otterdog_config()
        pull_request_number = str(self.pull_request.number)

        organization_config_model = await get_organization_config_by_installation_id(self.installation_id)
        if organization_config_model is None:
            raise RuntimeError(f"failed to find organization config for installation with id '{self.installation_id}'")

        rest_api = await self.get_rest_api(self.installation_id)

        with TemporaryDirectory(dir=otterdog_config.jsonnet_base_dir) as work_dir:
            assert rest_api.token is not None
            org_config = await get_organization_config(organization_config_model, rest_api.token, work_dir)

            jsonnet_config = org_config.jsonnet_config
            jsonnet_config.init_template()

            # get config from merge commit sha
            head_file = jsonnet_config.org_config_file
            await fetch_config(
                rest_api,
                self.org_id,
                self.org_id,
                otterdog_config.default_config_repo,
                head_file,
                self.pull_request.merge_commit_sha,
            )

            output = StringIO()
            printer = IndentingPrinter(output, log_level=LogLevel.ERROR)

            # let's create an apply operation that forces processing but does not update
            # any web UI settings and resources using credentials
            operation = ApplyOperation(
                force_processing=True,
                no_web_ui=True,
                update_webhooks=False,
                update_secrets=False,
                update_filter="",
                delete_resources=True,
                resolve_secrets=False,
                include_resources_with_secrets=False,
            )
            operation.init(otterdog_config, printer)

            await operation.execute(org_config)

            text = output.getvalue()
            self.logger.info(text)

            result = await render_template("comment/applied_changes_comment.txt", result=escape_for_github(text))

            await rest_api.issue.create_comment(
                self.org_id, otterdog_config.default_config_repo, pull_request_number, result
            )

    def __repr__(self) -> str:
        return f"ApplyChangesTask(repo={self.repository.full_name}, pull_request={self.pull_request.number})"
