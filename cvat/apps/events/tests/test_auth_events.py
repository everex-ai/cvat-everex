# Copyright (C) CVAT.ai Corporation
#
# SPDX-License-Identifier: MIT

import unittest
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_logged_out

from cvat.apps.events.event import AllEvents
from cvat.apps.webhooks.event_type import AllEvents as WebhookEvents


class _StubUser(SimpleNamespace):
    # django.contrib.auth connects update_last_login to user_logged_in, which saves the user
    def save(self, **kwargs):
        pass


class AuthEventsTestCase(unittest.TestCase):
    @staticmethod
    def _user(**overrides):
        return _StubUser(
            **{
                "id": 42,
                "username": "annotator",
                "email": "annotator@example.com",
                **overrides,
            }
        )

    @staticmethod
    def _send(signal, user) -> mock.Mock:
        with mock.patch("cvat.apps.events.handlers.record_server_event") as recorder:
            signal.send(sender=get_user_model(), request=None, user=user)

        return recorder

    def test_login_is_recorded(self):
        recorder = self._send(user_logged_in, self._user())

        recorder.assert_called_once()
        kwargs = recorder.call_args.kwargs
        self.assertEqual(kwargs["scope"], "login:user")
        self.assertEqual(kwargs["user_id"], 42)
        self.assertEqual(kwargs["user_name"], "annotator")
        self.assertEqual(kwargs["user_email"], "annotator@example.com")

    def test_logout_is_recorded(self):
        recorder = self._send(user_logged_out, self._user())

        recorder.assert_called_once()
        self.assertEqual(recorder.call_args.kwargs["scope"], "logout:user")

    def test_blank_email_is_normalized_to_none(self):
        recorder = self._send(user_logged_in, self._user(email=""))

        self.assertIsNone(recorder.call_args.kwargs["user_email"])

    def test_anonymous_logout_is_ignored(self):
        # django.contrib.auth.logout() sends user=None when nobody was authenticated
        recorder = self._send(user_logged_out, None)

        recorder.assert_not_called()

    def test_scopes_are_registered(self):
        self.assertIn("login:user", AllEvents.events)
        self.assertIn("logout:user", AllEvents.events)

    def test_auth_scopes_are_not_webhook_events(self):
        # webhooks keep their own event list; auth events must not leak into it
        self.assertNotIn("login:user", WebhookEvents.events)
        self.assertNotIn("logout:user", WebhookEvents.events)
