#  *******************************************************************************
#  Copyright (c) 2023-2024 Eclipse Foundation and others.
#  This program and the accompanying materials are made available
#  under the terms of the Eclipse Public License 2.0
#  which is available at http://www.eclipse.org/legal/epl-v20.html
#  SPDX-License-Identifier: EPL-2.0
#  *******************************************************************************

from __future__ import annotations

from abc import ABC
from datetime import datetime
from functools import cached_property
from typing import Optional

from otterdog.providers.github.auth import AuthStrategy

from .requester import Requester


class RestApi:
    # use a fixed API version
    _GH_API_VERSION = "2022-11-28"
    _GH_API_URL_ROOT = "https://api.github.com"

    def __init__(self, auth_strategy: AuthStrategy):
        self._auth_strategy = auth_strategy
        self._requester = Requester(auth_strategy, self._GH_API_URL_ROOT, self._GH_API_VERSION)

    @property
    def token(self) -> Optional[str]:
        from otterdog.providers.github.auth.token import TokenAuthStrategy

        if isinstance(self._auth_strategy, TokenAuthStrategy):
            return self._auth_strategy.token
        else:
            return None

    def close(self) -> None:
        self._requester.close()

    @property
    def requester(self) -> Requester:
        return self._requester

    @cached_property
    def app(self):
        from .app_client import AppClient

        return AppClient(self)

    @cached_property
    def commits(self):
        from .commits_client import CommitsClient

        return CommitsClient(self)

    @cached_property
    def content(self):
        from .content_client import ContentClient

        return ContentClient(self)

    @cached_property
    def issue(self):
        from .issue_client import IssueClient

        return IssueClient(self)

    @cached_property
    def pull_request(self):
        from .pull_request_client import PullRequestClient

        return PullRequestClient(self)

    @cached_property
    def repo(self):
        from .repo_client import RepoClient

        return RepoClient(self)

    @cached_property
    def org(self):
        from .org_client import OrgClient

        return OrgClient(self)

    @cached_property
    def user(self):
        from .user_client import UserClient

        return UserClient(self)


class RestClient(ABC):
    def __init__(self, rest_api: RestApi):
        self.__rest_api = rest_api

    @property
    def rest_api(self) -> RestApi:
        return self.__rest_api

    @property
    def requester(self) -> Requester:
        return self.__rest_api.requester


def encrypt_value(public_key: str, secret_value: str) -> str:
    """
    Encrypt a Unicode string using a public key.
    """
    from base64 import b64encode

    from nacl import encoding, public

    public_key_obj = public.PublicKey(public_key.encode("utf-8"), encoding.Base64Encoder)
    sealed_box = public.SealedBox(public_key_obj)
    encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
    return b64encode(encrypted).decode("utf-8")


_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def parse_date_string(date: str) -> datetime:
    return datetime.strptime(date, _FORMAT)
