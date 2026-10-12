# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

from django.urls import path

from plane.app.views import (
    PeopleEndpoint,
    PeopleExportEndpoint,
    PeopleImportEndpoint,
    PeopleProjectsEndpoint,
    PersonDepartureEndpoint,
    PersonDetailEndpoint,
    PersonReactivationEndpoint,
)

urlpatterns = [
    path("workspaces/<str:slug>/people/", PeopleEndpoint.as_view(), name="people"),
    path("workspaces/<str:slug>/people/import/", PeopleImportEndpoint.as_view(), name="people-import"),
    path("workspaces/<str:slug>/people/export/", PeopleExportEndpoint.as_view(), name="people-export"),
    path("workspaces/<str:slug>/people/projects/", PeopleProjectsEndpoint.as_view(), name="people-projects"),
    path("workspaces/<str:slug>/people/<uuid:user_id>/", PersonDetailEndpoint.as_view(), name="person-detail"),
    path(
        "workspaces/<str:slug>/people/<uuid:user_id>/departure/",
        PersonDepartureEndpoint.as_view(),
        name="person-departure",
    ),
    path(
        "workspaces/<str:slug>/people/<uuid:user_id>/reactivation/",
        PersonReactivationEndpoint.as_view(),
        name="person-reactivation",
    ),
]
