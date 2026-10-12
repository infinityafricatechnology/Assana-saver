# Copyright (c) 2023-present Plane Software, Inc. and contributors
# SPDX-License-Identifier: AGPL-3.0-only
# See the LICENSE file for details.

"""The « Personnes » page: pre-registration, roles and profiles, projects, departures, import and export."""

import io
from unittest import mock

import pytest
from openpyxl import Workbook
from rest_framework import status
from rest_framework.test import APIClient

from plane.db.models import (
    APIToken,
    Branch,
    Entity,
    Issue,
    IssueActivity,
    IssueAssignee,
    Profile,
    Project,
    ProjectMember,
    ProjectUserProperty,
    SteeringProfile,
    State,
    User,
    WorkspaceMember,
)


@pytest.fixture(autouse=True)
def no_welcome_email():
    with mock.patch("plane.app.views.people.base.person_welcome_email.delay") as delay:
        yield delay


@pytest.fixture
def entity(workspace):
    branch = Branch.objects.create(workspace=workspace, name="Immobilier")
    return Entity.objects.create(workspace=workspace, branch=branch, name="SCI Infinity")


@pytest.fixture
def projects(workspace, create_user):
    created = []
    for identifier, name in (("LIC", "Licence"), ("TOUR", "Tour IAT")):
        project = Project.objects.create(name=name, identifier=identifier, workspace=workspace, created_by=create_user)
        ProjectMember.objects.create(workspace=workspace, project=project, member=create_user, role=20)
        State.objects.create(project=project, workspace=workspace, name="À faire", group="unstarted", default=True)
        created.append(project)
    return created


def _url(workspace, suffix=""):
    return f"/api/workspaces/{workspace.slug}/people/{suffix}"


def _add(client, workspace, **payload):
    data = {"email": "awa.diallo@infinity-africa.com", "first_name": "Awa", "last_name": "Diallo", **payload}
    return client.post(_url(workspace), data, format="json")


@pytest.mark.contract
@pytest.mark.django_db
class TestPreRegistration:
    def test_members_cannot_manage_people(self, workspace):
        member = User.objects.create(email="membre@example.com", username="membre")
        WorkspaceMember.objects.create(workspace=workspace, member=member, role=15)
        client = APIClient()
        client.force_authenticate(user=member)
        assert client.get(_url(workspace)).status_code == status.HTTP_403_FORBIDDEN
        assert _add(client, workspace).status_code == status.HTTP_403_FORBIDDEN

    def test_pre_register_with_role_profile_and_projects(
        self, session_client, workspace, entity, projects, no_welcome_email
    ):
        response = _add(
            session_client,
            workspace,
            email="  Awa.Diallo@Infinity-Africa.com ",
            role=15,
            profiles=[{"role": "entity_manager", "entity_id": str(entity.id)}],
            project_ids=[str(project.id) for project in projects],
        )
        assert response.status_code == status.HTTP_201_CREATED
        person = response.json()
        assert person["email"] == "awa.diallo@infinity-africa.com"
        assert person["status"] == "pending"
        assert person["profiles"][0]["entity_id"] == str(entity.id)
        assert {p["project_id"] for p in person["projects"]} == {str(p.id) for p in projects}

        user = User.objects.get(email="awa.diallo@infinity-africa.com")
        assert user.is_password_autoset and user.is_active
        profile = Profile.objects.get(user=user)
        assert profile.is_onboarded and profile.last_workspace_id == workspace.id
        assert ProjectUserProperty.objects.filter(user=user).count() == 2
        no_welcome_email.assert_called_once()

    def test_without_welcome_email(self, session_client, workspace, no_welcome_email):
        assert _add(session_client, workspace, send_email=False).status_code == 201
        no_welcome_email.assert_not_called()

    @pytest.mark.parametrize(
        "payload, code",
        [
            ({"email": "pas-une-adresse"}, "invalid_email"),
            ({"first_name": " "}, "missing_first_name"),
            ({"role": 5}, "invalid_role"),
            ({"profiles": [{"role": "branch_director"}]}, "profile_scope"),
            ({"profiles": [{"role": "pope"}]}, "invalid_profile"),
            ({"project_ids": ["0b6c3e1e-0000-4000-8000-000000000000"]}, "invalid_project"),
        ],
    )
    def test_rejects_invalid_people(self, session_client, workspace, payload, code):
        response = _add(session_client, workspace, **payload)
        assert response.status_code == 400
        assert response.json()["code"] == code

    def test_existing_members_and_accounts(self, session_client, workspace, create_user):
        assert _add(session_client, workspace, email=create_user.email).json()["code"] == "already_member"
        outsider = User.objects.create(email="deja@infinity-africa.com", username="deja", first_name="Déjà")
        response = _add(session_client, workspace, email="deja@infinity-africa.com")
        assert response.status_code == 201
        assert response.json()["id"] == str(outsider.id)


@pytest.mark.contract
@pytest.mark.django_db
class TestRolesAndProjects:
    def test_update_names_role_and_profiles(self, session_client, workspace, entity):
        person = _add(session_client, workspace).json()
        url = _url(workspace, f"{person['id']}/")
        response = session_client.patch(
            url, {"last_name": "Diallo-Koné", "role": 20, "profiles": [{"role": "cabinet"}]}, format="json"
        )
        body = response.json()
        assert body["last_name"] == "Diallo-Koné"
        assert body["role"] == 20
        assert [profile["role"] for profile in body["profiles"]] == ["cabinet"]
        cleared = session_client.patch(url, {"profiles": []}, format="json").json()
        assert cleared["profiles"] == []

    def test_the_organisation_keeps_an_administrator(self, session_client, workspace, create_user):
        response = session_client.patch(_url(workspace, f"{create_user.id}/"), {"role": 15}, format="json")
        assert response.json()["code"] == "self"

    def test_add_people_to_projects(self, session_client, workspace, projects):
        awa = _add(session_client, workspace).json()
        admin = _add(session_client, workspace, email="kofi@infinity-africa.com", first_name="Kofi", role=20).json()
        response = session_client.post(
            _url(workspace, "projects/"),
            {"user_ids": [awa["id"], admin["id"]], "project_ids": [str(p.id) for p in projects], "role": 15},
            format="json",
        )
        assert response.status_code == 200
        assert response.json()["added"] == 4
        roles = dict(ProjectMember.objects.filter(project=projects[0]).values_list("member_id", "role"))
        assert roles[User.objects.get(email="awa.diallo@infinity-africa.com").id] == 15
        # Organisation admins are always admins of their projects.
        assert roles[User.objects.get(email="kofi@infinity-africa.com").id] == 20


@pytest.mark.contract
@pytest.mark.django_db
class TestDeparture:
    def _open_issue(self, project, user):
        issue = Issue.objects.create(
            project=project, workspace=project.workspace, name="Dossier", state=State.objects.get(project=project)
        )
        IssueAssignee.objects.create(issue=issue, assignee=user, project=project, workspace=project.workspace)
        return issue

    def test_departure_hands_over_and_closes_access(self, session_client, workspace, projects, entity):
        awa = _add(
            session_client,
            workspace,
            profiles=[{"role": "entity_manager", "entity_id": str(entity.id)}],
            project_ids=[str(projects[0].id)],
        ).json()
        kofi = _add(session_client, workspace, email="kofi@infinity-africa.com", first_name="Kofi").json()
        awa_user = User.objects.get(pk=awa["id"])
        issue = self._open_issue(projects[0], awa_user)
        APIToken.objects.create(user=awa_user, label="Claude", token="claude-awa")

        url = _url(workspace, f"{awa['id']}/departure/")
        assert session_client.get(url).json() == {"open_work_items": 1}
        response = session_client.post(url, {"reassign_to": kofi["id"]}, format="json")
        assert response.status_code == 200
        body = response.json()
        assert body["reassigned"] == 1
        assert body["person"]["status"] == "departed"

        assert list(IssueAssignee.objects.filter(issue=issue).values_list("assignee_id", flat=True)) == [
            User.objects.get(pk=kofi["id"]).id
        ]
        assert IssueActivity.objects.filter(issue=issue, field="assignees").count() == 2
        assert ProjectMember.objects.get(project=projects[0], member_id=kofi["id"]).is_active
        awa_user.refresh_from_db()
        assert not awa_user.is_active and awa_user.last_logout_time is not None
        assert not ProjectMember.objects.get(project=projects[0], member=awa_user).is_active
        assert not APIToken.objects.get(user=awa_user).is_active
        assert not SteeringProfile.objects.filter(member=awa_user).exists()

    def test_departure_without_handover_and_reactivation(self, session_client, workspace, projects):
        awa = _add(session_client, workspace, project_ids=[str(projects[0].id)]).json()
        issue = self._open_issue(projects[0], User.objects.get(pk=awa["id"]))
        body = session_client.post(_url(workspace, f"{awa['id']}/departure/"), {}, format="json").json()
        assert body["unassigned"] == 1
        assert not IssueAssignee.objects.filter(issue=issue).exists()
        assert _add(session_client, workspace).json()["code"] == "departed"

        reactivated = session_client.post(_url(workspace, f"{awa['id']}/reactivation/"), {"role": 15}, format="json")
        assert reactivated.json()["status"] == "pending"
        assert ProjectMember.objects.get(project=projects[0], member_id=awa["id"]).is_active

    def test_departure_guards(self, session_client, workspace, create_user):
        awa = _add(session_client, workspace).json()
        assert session_client.post(_url(workspace, f"{create_user.id}/departure/"), {}).json()["code"] == "self"
        outsider = User.objects.create(email="outsider@example.com", username="outsider")
        response = session_client.post(
            _url(workspace, f"{awa['id']}/departure/"), {"reassign_to": str(outsider.id)}, format="json"
        )
        assert response.json()["code"] == "invalid_reassign"


@pytest.mark.contract
@pytest.mark.django_db
class TestImportExport:
    CSV = (
        "Prénom;Nom;E-mail;Rôle;Profil;Périmètre;Projets\n"
        "Awa;Diallo;awa.diallo@infinity-africa.com;Membre;Responsable d'entité;sci infinity;LIC\n"
        'Kofi;Mensah;kofi@infinity-africa.com;Admin;Directeur de pôle;Immobilier;"Licence; TOUR"\n'
        "Sans;Adresse;pas-une-adresse;Membre;;;\n"
        "Ama;Owusu;ama@infinity-africa.com;Membre;Responsable d'entité;Entité inconnue;\n"
        "Awa;Bis;AWA.DIALLO@infinity-africa.com;;;;\n"
        "Test;Admin;test@plane.so;;;;\n"
    )

    def _upload(self, client, workspace, content, name="personnes.csv", **extra):
        data = {"file": io.BytesIO(content), **extra}
        data["file"].name = name
        return client.post(_url(workspace, "import/"), data, format="multipart")

    def test_preview_then_import(self, session_client, workspace, entity, projects):
        preview = self._upload(session_client, workspace, self.CSV.encode()).json()
        errors = {row["line"]: row["errors"] for row in preview["rows"]}
        assert errors == {
            2: [],
            3: [],
            4: ["invalid_email"],
            5: ["unknown_entity"],
            6: ["duplicate_in_file"],
            7: ["already_member"],
        }
        assert preview["created"] == 0
        assert not User.objects.filter(email="awa.diallo@infinity-africa.com").exists()

        imported = self._upload(session_client, workspace, self.CSV.encode(), confirm="true").json()
        assert imported["created"] == 2
        kofi = User.objects.get(email="kofi@infinity-africa.com")
        assert WorkspaceMember.objects.get(workspace=workspace, member=kofi).role == 20
        assert ProjectMember.objects.filter(member=kofi).count() == 2
        assert SteeringProfile.objects.get(member=kofi).branch.name == "Immobilier"

    def test_excel_files(self, session_client, workspace):
        book = Workbook()
        sheet = book.active
        sheet.append(["Prénom", "Nom", "E-mail"])
        sheet.append(["Awa", "Diallo", "awa.diallo@infinity-africa.com"])
        content = io.BytesIO()
        book.save(content)
        body = self._upload(session_client, workspace, content.getvalue(), name="personnes.xlsx", confirm="1").json()
        assert body["created"] == 1

    def test_unreadable_files(self, session_client, workspace):
        assert self._upload(session_client, workspace, b"x", name="liste.pdf").json()["code"] == "unsupported_file"
        no_email = "Prénom;Nom\nAwa;Diallo\n".encode()
        assert self._upload(session_client, workspace, no_email).json()["code"] == "missing_columns"

    def test_export(self, session_client, workspace, entity, projects):
        _add(
            session_client,
            workspace,
            profiles=[{"role": "entity_manager", "entity_id": str(entity.id)}],
            project_ids=[str(projects[0].id)],
        )
        response = session_client.get(_url(workspace, "export/"))
        assert response.status_code == 200
        lines = response.content.decode("utf-8-sig").splitlines()
        assert lines[0] == "Prénom;Nom;E-mail;Rôle;Profil;Périmètre;Projets;Statut"
        assert (
            "Awa;Diallo;awa.diallo@infinity-africa.com;Membre;Responsable d'entité;SCI Infinity;LIC;Jamais connecté"
            in lines
        )
