# *******************************************************************************
# Copyright (c) 2023 Eclipse Foundation and others.
# This program and the accompanying materials are made available
# under the terms of the MIT License
# which is available at https://spdx.org/licenses/MIT.html
# SPDX-License-Identifier: MIT
# *******************************************************************************

import os

import jq
from colorama import Fore, Style

import organization as org
from config import OtterdogConfig, OrganizationConfig
from operation import Operation
from utils import IndentingPrinter


class ValidateOperation(Operation):
    def __init__(self):
        self.config = None
        self.jsonnet_config = None
        self._printer = None

    @property
    def printer(self) -> IndentingPrinter:
        return self._printer

    def init(self, config: OtterdogConfig, printer: IndentingPrinter) -> None:
        self.config = config
        self.jsonnet_config = self.config.jsonnet_config
        self._printer = printer

        self.printer.print(f"Validating configuration at '{config.config_file}'")

    def execute(self, org_config: OrganizationConfig) -> int:
        github_id = org_config.github_id

        self.printer.print(f"Organization {Style.BRIGHT}{org_config.name}{Style.RESET_ALL}[id={github_id}]")
        self.printer.level_up()

        try:
            org_file_name = self.jsonnet_config.get_org_config_file(github_id)

            if not os.path.exists(org_file_name):
                self.printer.print_warn(f"configuration file '{org_file_name}' does not yet exist, run fetch first")
                return 1

            try:
                organization = org.load_from_file(github_id, self.jsonnet_config.get_org_config_file(github_id))
            except RuntimeError as ex:
                self.printer.print_error(f"Validation failed\nfailed to load configuration: {str(ex)}")
                return 1

            validation_errors = 0

            settings = organization.get_settings()

            # enabling dependabot implicitly enables the dependency graph,
            # disabling the dependency graph in the configuration will result in inconsistencies after
            # applying the configuration, warn the user about it.
            dependabot_alerts_enabled = \
                settings.get("dependabot_alerts_enabled_for_new_repositories") is True
            dependabot_security_updates_enabled = \
                settings.get("dependabot_security_updates_enabled_for_new_repositories") is True

            dependency_graph_disabled = \
                settings.get("dependency_graph_enabled_for_new_repositories") is False

            if (dependabot_alerts_enabled or dependabot_security_updates_enabled) and dependency_graph_disabled:
                self.printer.print_error(f"enabling dependabot also enables dependency graph")
                validation_errors += 1

            if dependabot_security_updates_enabled and not dependabot_alerts_enabled:
                self.printer.print_error(f"enabling dependabot_security_updates also enables dependabot_alerts")
                validation_errors += 1

            webhooks = organization.get_webhooks()

            for webhook in webhooks:
                secret = jq.compile('.config.secret // ""').input(webhook).first()
                if secret and all(ch == '*' for ch in secret):
                    url = jq.compile('.config.url // ""').input(webhook).first()
                    self.printer.print_error(f"webhook with url '{url}' uses a dummy secret '{secret}'")
                    validation_errors += 1

            if validation_errors == 0:
                self.printer.print(f"{Fore.GREEN}Validation succeeded{Style.RESET_ALL}")
            else:
                self.printer.print(f"{Fore.RED}Validation failed{Style.RESET_ALL}")

            return validation_errors

        finally:
            self.printer.level_down()
