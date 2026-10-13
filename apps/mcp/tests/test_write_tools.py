"""Write and admin tools: names become ids, and batches go to the bulk endpoints."""

import json

from conftest import WS

ISSUE_12 = {"id": "t-12", "project": "p-iat", "sequence_id": 12, "name": "Offre MDM", "state": "s-todo"}


def body(route):
    return json.loads(route.calls.last.request.content)


async def test_create_tasks_resolves_names(api, call):
    api.get(f"{WS}/work-items/IAT-12/").respond(json=ISSUE_12)
    route = api.post(f"{WS}/projects/p-iat/work-items/bulk/").respond(
        201, json={"work_items": [{"sequence_id": 13, "name": "Chiffrer"}, {"sequence_id": 14, "name": "Relire"}]}
    )

    result = await call(
        "create_tasks",
        project="IAT",
        tasks=[
            {
                "name": "Chiffrer",
                "description": "Chiffrer l'offre\n\n- matériel\n- licences",
                "section": "à faire",
                "assignee": "kofi@infinity-africa.com",
                "due_date": "2026-10-20",
                "labels": ["client"],
                "parent": "IAT-12",
                "custom_fields": {"Budget": 1500, "Vague": "Vague 2"},
            },
            {"name": "Relire", "assignee": "me", "priority": "high"},
        ],
    )

    sent = body(route)["work_items"]
    assert sent[0] == {
        "name": "Chiffrer",
        "state": "s-todo",
        "description_html": "<p>Chiffrer l&#x27;offre</p><ul><li><p>matériel</p></li><li><p>licences</p></li></ul>",
        "assignees": ["u-kofi"],
        "labels": ["l-client"],
        "parent": "t-12",
        "target_date": "2026-10-20",
        "custom_fields": {"cf-budget": 1500, "cf-wave": "o-2"},
    }
    assert sent[1] == {"name": "Relire", "assignees": ["u-me"], "priority": "high"}
    assert result["created"][0] == {
        "identifier": "IAT-13",
        "name": "Chiffrer",
        "url": "https://plan.test/infinity/browse/IAT-13/",
    }


async def test_unknown_names_are_reported_before_any_write(api, call_error):
    route = api.post(f"{WS}/projects/p-iat/work-items/bulk/")

    message = await call_error("create_tasks", project="IAT", tasks=[{"name": "X", "section": "En cours"}])

    assert "No section 'En cours'" in message and "À faire" in message
    assert not route.called


async def test_update_tasks_completes_reassigns_and_clears(api, call):
    api.get(f"{WS}/work-items/IAT-12/").respond(json=ISSUE_12)
    route = api.patch(f"{WS}/projects/p-iat/work-items/bulk/").respond(
        json={"work_items": [{"sequence_id": 12, "name": "Offre MDM"}]}
    )

    result = await call(
        "update_tasks",
        changes=[
            {
                "task": "IAT-12",
                "completed": True,
                "assignee": "none",
                "due_date": "none",
                "labels": [],
                "custom_fields": {"Budget": None},
            }
        ],
    )

    assert body(route)["work_items"] == [
        {
            "id": "t-12",
            "state": "s-done",
            "assignees": [],
            "target_date": None,
            "labels": [],
            "custom_fields": {"cf-budget": None},
        }
    ]
    assert result["updated"][0]["identifier"] == "IAT-12"


async def test_steered_projects_get_their_steering_fields(api, call, call_error):
    route = api.post(f"{WS}/projects/p-iat/work-items/bulk/").respond(
        201, json={"work_items": [{"sequence_id": 13, "name": "Agrément"}]}
    )

    await call(
        "create_tasks",
        project="IAT",
        tasks=[
            {
                "name": "Agrément",
                "assignee": "me",
                "due_date": "2026-12-01",
                "category": "Réglementaire",
                "supervisor": "Kofi",
                "approver": "pdg@infinity-africa.com",
            }
        ],
    )

    assert body(route)["work_items"][0]["steering"] == {
        "category": "Réglementaire",
        "supervisor": "u-kofi",
        "approver": "pdg@infinity-africa.com",
    }
    message = await call_error("create_tasks", project="IAT", tasks=[{"name": "X", "supervisor": "Personne"}])
    assert "Personne" in message


async def test_postponing_carries_its_reason(api, call):
    api.get(f"{WS}/work-items/IAT-12/").respond(json=ISSUE_12)
    route = api.patch(f"{WS}/projects/p-iat/work-items/bulk/").respond(
        json={"work_items": [{"sequence_id": 12, "name": "Offre MDM"}]}
    )

    await call(
        "update_tasks",
        changes=[{"task": "IAT-12", "due_date": "2026-12-15", "due_date_reason": "Attente du client"}],
    )

    assert body(route)["work_items"] == [
        {"id": "t-12", "target_date": "2026-12-15", "deadline_comment": "Attente du client"}
    ]


async def test_reopening_goes_back_to_the_default_section(api, call):
    api.get(f"{WS}/work-items/IAT-12/").respond(json={**ISSUE_12, "state": "s-done"})
    route = api.patch(f"{WS}/projects/p-iat/work-items/bulk/").respond(json={"work_items": [ISSUE_12]})

    await call("update_tasks", changes=[{"task": "IAT-12", "completed": False}])

    assert body(route)["work_items"] == [{"id": "t-12", "state": "s-todo"}]


async def test_comments(api, call):
    api.get(f"{WS}/work-items/IAT-12/").respond(json=ISSUE_12)
    created = api.post(f"{WS}/projects/p-iat/work-items/t-12/comments/").respond(201, json={"id": "c-9"})
    deleted = api.delete(f"{WS}/projects/p-iat/work-items/t-12/comments/c-9/").respond(204)

    assert (await call("add_comment", task="IAT-12", text="Validé <b>ce matin</b>"))["comment_id"] == "c-9"
    assert body(created) == {"comment_html": "<p>Validé &lt;b&gt;ce matin&lt;/b&gt;</p>"}
    await call("delete_comment", task="IAT-12", comment_id="c-9")
    assert deleted.called


async def test_delete_task(api, call):
    api.get(f"{WS}/work-items/IAT-12/").respond(json=ISSUE_12)
    route = api.delete(f"{WS}/projects/p-iat/work-items/t-12/").respond(204)

    assert await call("delete_task", task="iat-12") == {"deleted": "IAT-12", "name": "Offre MDM"}
    assert route.called


async def test_create_section_with_its_kind_color(api, call):
    route = api.post(f"{WS}/projects/p-iat/states/").respond(
        201, json={"id": "s-new", "name": "En recette", "group": "started"}
    )

    result = await call("create_section", project="IAT", name="En recette", kind="started")

    assert body(route) == {"name": "En recette", "group": "started", "color": "#f59e0b"}
    assert result["kind"] == "started"


async def test_update_custom_field_keeps_existing_option_ids(api, call):
    api.get(f"{WS}/custom-fields/").respond(
        json=[
            {
                "id": "cf-wave",
                "name": "Vague",
                "field_type": "single_select",
                "options": [{"id": "o-1", "name": "Vague 1"}, {"id": "o-2", "name": "Vague 2"}],
            }
        ]
    )
    route = api.patch(f"{WS}/custom-fields/cf-wave/").respond(
        json={"id": "cf-wave", "name": "Vague", "field_type": "single_select", "options": []}
    )

    await call("update_custom_field", field="vague", options=["Vague 2", "Vague 3"])

    assert body(route) == {"options": [{"id": "o-2", "name": "Vague 2"}, {"name": "Vague 3"}]}


async def test_create_custom_field_and_add_it_to_projects(api, call):
    created = api.post(f"{WS}/custom-fields/").respond(
        201,
        json={
            "id": "cf-risk",
            "name": "Risque",
            "field_type": "single_select",
            "options": [{"id": "o-h", "name": "Haut"}],
        },
    )
    attached = api.post(f"{WS}/projects/p-iat/custom-fields/").respond(201, json={})

    result = await call(
        "create_custom_field", name="Risque", type="single_select", options=["Haut"], add_to_projects=["IAT"]
    )

    assert body(created)["options"] == [{"name": "Haut"}]
    assert body(attached) == {"custom_field_id": "cf-risk"}
    assert result["projects"] == ["IAT"]


async def test_member_roles_use_the_membership(api, call):
    route = api.patch(f"{WS}/projects/p-iat/members/m-kofi/").respond(json={})

    await call("set_project_member_role", project="IAT", person="Kofi", role="admin")

    assert body(route) == {"role": 20}


async def test_adding_someone_outside_the_project_needs_admin_rights(api, call_error):
    api.get(f"{WS}/members-lite/").respond(403, json={"error": "forbidden"})

    message = await call_error("add_project_member", project="IAT", person="moussa@infinity-africa.com")

    assert "organisation admin rights" in message
