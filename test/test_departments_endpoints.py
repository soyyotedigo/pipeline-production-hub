from __future__ import annotations

import sys
import uuid
from importlib import import_module
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

config_module = import_module("app.core.config")
security_module = import_module("app.core.security")
models_module = import_module("app.models")

create_access_token = security_module.create_access_token
hash_password = security_module.hash_password

Role = models_module.Role
RoleName = models_module.RoleName
User = models_module.User
UserRole = models_module.UserRole

department_module = import_module("app.models.department")
Department = department_module.Department

pytestmark = pytest.mark.departments


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_user(db_session: AsyncSession, email: str) -> User:
    user = User(
        id=uuid.uuid4(),
        email=email,
        hashed_password=hash_password("secret123"),
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _ensure_role(db_session: AsyncSession, role_name: RoleName) -> Role:
    result = await db_session.execute(select(Role).where(Role.name == role_name))
    role = result.scalar_one_or_none()
    if role is not None:
        return role
    role = Role(name=role_name, description=f"{role_name.value} role")
    db_session.add(role)
    await db_session.commit()
    await db_session.refresh(role)
    return role


async def _assign_role(
    db_session: AsyncSession,
    user_id: uuid.UUID,
    role_name: RoleName,
    project_id: uuid.UUID | None,
) -> None:
    role = await _ensure_role(db_session, role_name)
    db_session.add(UserRole(user_id=user_id, role_id=role.id, project_id=project_id))
    await db_session.commit()


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(subject=str(user.id))
    return {"Authorization": f"Bearer {token}"}


async def _create_dept_via_api(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    name: str,
    code: str | None = None,
    color: str | None = None,
    description: str | None = None,
) -> dict:
    payload: dict = {
        "name": name,
        "code": code or f"DEPT{uuid.uuid4().hex[:4].upper()}",
    }
    if color is not None:
        payload["color"] = color
    if description is not None:
        payload["description"] = description

    resp = await client.post("/departments", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _add_member_via_api(
    client: AsyncClient,
    dept_id: str,
    user_id: str,
    headers: dict[str, str],
) -> dict:
    resp = await client.post(
        f"/departments/{dept_id}/members",
        json={"user_id": user_id},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# CREATE
# ---------------------------------------------------------------------------


class TestCreateDepartment:
    async def test_create_returns_201_with_correct_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-create@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)

        resp = await client.post(
            "/departments",
            json={"name": "Compositing", "code": "COMP"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Compositing"
        assert data["code"] == "COMP"
        assert data["archived_at"] is None
        assert "id" in data
        assert "created_at" in data

    async def test_create_code_stored_uppercase(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-upper@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)

        resp = await client.post(
            "/departments",
            json={"name": "Animation", "code": "anim"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 201
        assert resp.json()["code"] == "ANIM"

    async def test_create_with_all_optional_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-full@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)

        resp = await client.post(
            "/departments",
            json={
                "name": "Lighting",
                "code": "LGHT",
                "color": "#FF8800",
                "description": "Handles lighting and rendering",
            },
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["color"] == "#FF8800"
        assert data["description"] == "Handles lighting and rendering"

    async def test_create_duplicate_name_returns_409(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-dupname@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        headers = _auth_headers(admin)

        await _create_dept_via_api(client, headers, name="FX", code="FX01")

        resp = await client.post(
            "/departments",
            json={"name": "FX", "code": "FX02"},
            headers=headers,
        )

        assert resp.status_code == 409

    async def test_create_duplicate_code_returns_409(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-dupcode@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        headers = _auth_headers(admin)

        await _create_dept_via_api(client, headers, name="Rigging A", code="RIG")

        resp = await client.post(
            "/departments",
            json={"name": "Rigging B", "code": "rig"},
            headers=headers,
        )

        assert resp.status_code == 409

    async def test_create_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        resp = await client.post(
            "/departments",
            json={"name": "No Auth", "code": "NA"},
        )

        assert resp.status_code == 401

    async def test_create_invalid_color_returns_422(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-color@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)

        resp = await client.post(
            "/departments",
            json={"name": "Color Test", "code": "CLR", "color": "not-a-color"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# LIST
# ---------------------------------------------------------------------------


class TestListDepartments:
    async def test_list_returns_200_with_departments(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-list@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        headers = _auth_headers(admin)

        await _create_dept_via_api(client, headers, name="Dept A", code="DA")
        await _create_dept_via_api(client, headers, name="Dept B", code="DB")

        resp = await client.get("/departments", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    async def test_list_excludes_archived_by_default(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-listarch@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        headers = _auth_headers(admin)

        active = await _create_dept_via_api(client, headers, name="Active Dept", code="ACT")
        archived = await _create_dept_via_api(client, headers, name="Archived Dept", code="ARC")
        await client.post(f"/departments/{archived['id']}/archive", headers=headers)

        resp = await client.get("/departments", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        ids = [d["id"] for d in data["items"]]
        assert active["id"] in ids
        assert archived["id"] not in ids

    async def test_list_with_include_archived_returns_all(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-inclarch@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        headers = _auth_headers(admin)

        active = await _create_dept_via_api(client, headers, name="Inc Active", code="IA")
        archived = await _create_dept_via_api(client, headers, name="Inc Archived", code="IR")
        await client.post(f"/departments/{archived['id']}/archive", headers=headers)

        resp = await client.get("/departments?include_archived=true", headers=headers)

        assert resp.status_code == 200
        ids = [d["id"] for d in resp.json()["items"]]
        assert active["id"] in ids
        assert archived["id"] in ids

    async def test_list_pagination(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-page@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        headers = _auth_headers(admin)

        for i in range(5):
            await _create_dept_via_api(client, headers, name=f"Paginated {i}", code=f"PG{i}")

        resp = await client.get("/departments?offset=0&limit=3", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) == 3
        assert data["total"] == 5
        assert data["limit"] == 3
        assert data["offset"] == 0

    async def test_list_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        resp = await client.get("/departments")

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET
# ---------------------------------------------------------------------------


class TestGetDepartment:
    async def test_get_returns_200_with_correct_data(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-get@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        headers = _auth_headers(admin)

        created = await _create_dept_via_api(
            client, headers, name="Get Me", code="GTM", description="A test department"
        )

        resp = await client.get(f"/departments/{created['id']}", headers=headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == created["id"]
        assert data["name"] == "Get Me"
        assert data["description"] == "A test department"

    async def test_get_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-get404@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)

        resp = await client.get(
            f"/departments/{uuid.uuid4()}",
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 404

    async def test_get_without_auth_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-getnoauth@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        headers = _auth_headers(admin)
        created = await _create_dept_via_api(client, headers, name="Secret", code="SEC")

        resp = await client.get(f"/departments/{created['id']}")

        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# UPDATE
# ---------------------------------------------------------------------------


class TestUpdateDepartment:
    async def test_update_name(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-upd@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        headers = _auth_headers(admin)
        created = await _create_dept_via_api(client, headers, name="Old Name", code="OLD")

        resp = await client.patch(
            f"/departments/{created['id']}",
            json={"name": "New Name"},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["name"] == "New Name"

    async def test_update_code_stored_uppercase(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-updcode@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        headers = _auth_headers(admin)
        created = await _create_dept_via_api(client, headers, name="Code Dept", code="CDT")

        resp = await client.patch(
            f"/departments/{created['id']}",
            json={"code": "newcode"},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["code"] == "NEWCODE"

    async def test_update_unarchives_department(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-unarch@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        headers = _auth_headers(admin)
        created = await _create_dept_via_api(client, headers, name="Was Archived", code="WAR")
        await client.post(f"/departments/{created['id']}/archive", headers=headers)

        resp = await client.patch(
            f"/departments/{created['id']}",
            json={"name": "Now Active"},
            headers=headers,
        )

        assert resp.status_code == 200
        assert resp.json()["archived_at"] is None
        assert resp.json()["name"] == "Now Active"

    async def test_update_duplicate_name_returns_409(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-updname409@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        headers = _auth_headers(admin)
        await _create_dept_via_api(client, headers, name="Taken Name", code="TKN")
        other = await _create_dept_via_api(client, headers, name="Other Dept", code="OTH")

        resp = await client.patch(
            f"/departments/{other['id']}",
            json={"name": "Taken Name"},
            headers=headers,
        )

        assert resp.status_code == 409

    async def test_update_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-upd404@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)

        resp = await client.patch(
            f"/departments/{uuid.uuid4()}",
            json={"name": "Ghost"},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# ARCHIVE
# ---------------------------------------------------------------------------


class TestArchiveDepartment:
    async def test_archive_sets_archived_at(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-archive@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        headers = _auth_headers(admin)
        created = await _create_dept_via_api(client, headers, name="To Archive", code="TAR")

        resp = await client.post(f"/departments/{created['id']}/archive", headers=headers)

        assert resp.status_code == 200
        assert resp.json()["archived_at"] is not None

    async def test_archived_excluded_from_default_list(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-archlist@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        headers = _auth_headers(admin)
        created = await _create_dept_via_api(client, headers, name="Hidden Dept", code="HID")
        await client.post(f"/departments/{created['id']}/archive", headers=headers)

        resp = await client.get("/departments", headers=headers)

        ids = [d["id"] for d in resp.json()["items"]]
        assert created["id"] not in ids

    async def test_archive_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-arch404@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)

        resp = await client.post(
            f"/departments/{uuid.uuid4()}/archive",
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE
# ---------------------------------------------------------------------------


class TestDeleteDepartment:
    async def test_delete_empty_department_returns_204(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-del@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        headers = _auth_headers(admin)
        created = await _create_dept_via_api(client, headers, name="Delete Me", code="DLT")

        resp = await client.delete(f"/departments/{created['id']}", headers=headers)

        assert resp.status_code == 204

        get_resp = await client.get(f"/departments/{created['id']}", headers=headers)
        assert get_resp.status_code == 404

    async def test_delete_department_with_members_returns_422(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-delmem@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        member = await _create_user(db_session, "member-delmem@dept.test")
        headers = _auth_headers(admin)
        created = await _create_dept_via_api(client, headers, name="Has Members", code="HMB")
        await _add_member_via_api(client, created["id"], str(member.id), headers)

        resp = await client.delete(f"/departments/{created['id']}", headers=headers)

        assert resp.status_code == 422

    async def test_delete_nonexistent_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-del404@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)

        resp = await client.delete(
            f"/departments/{uuid.uuid4()}",
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# MEMBERS
# ---------------------------------------------------------------------------


class TestDepartmentMembers:
    async def test_add_member_returns_201_with_correct_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-addmem@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        member = await _create_user(db_session, "member-add@dept.test")
        headers = _auth_headers(admin)
        dept = await _create_dept_via_api(client, headers, name="Add Member Dept", code="AMD")

        resp = await client.post(
            f"/departments/{dept['id']}/members",
            json={"user_id": str(member.id)},
            headers=headers,
        )

        assert resp.status_code == 201
        data = resp.json()
        assert data["user_id"] == str(member.id)
        assert data["department_id"] == dept["id"]
        assert "id" in data
        assert "created_at" in data

    async def test_add_duplicate_member_returns_409(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-dupmem@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        member = await _create_user(db_session, "member-dup@dept.test")
        headers = _auth_headers(admin)
        dept = await _create_dept_via_api(client, headers, name="Dup Member Dept", code="DMD")

        await _add_member_via_api(client, dept["id"], str(member.id), headers)
        resp = await client.post(
            f"/departments/{dept['id']}/members",
            json={"user_id": str(member.id)},
            headers=headers,
        )

        assert resp.status_code == 409

    async def test_add_nonexistent_user_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-addnouser@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        headers = _auth_headers(admin)
        dept = await _create_dept_via_api(client, headers, name="No User Dept", code="NUD")

        resp = await client.post(
            f"/departments/{dept['id']}/members",
            json={"user_id": str(uuid.uuid4())},
            headers=headers,
        )

        assert resp.status_code == 404

    async def test_add_member_to_nonexistent_department_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-addnodept@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        member = await _create_user(db_session, "member-nodept@dept.test")

        resp = await client.post(
            f"/departments/{uuid.uuid4()}/members",
            json={"user_id": str(member.id)},
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 404

    async def test_list_members_returns_correct_users(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-listmem@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        user_a = await _create_user(db_session, "user-a@dept.test")
        user_b = await _create_user(db_session, "user-b@dept.test")
        headers = _auth_headers(admin)
        dept = await _create_dept_via_api(client, headers, name="List Members Dept", code="LMD")

        await _add_member_via_api(client, dept["id"], str(user_a.id), headers)
        await _add_member_via_api(client, dept["id"], str(user_b.id), headers)

        resp = await client.get(f"/departments/{dept['id']}/members", headers=headers)

        assert resp.status_code == 200
        members = resp.json()
        assert len(members) == 2
        emails = {m["email"] for m in members}
        assert "user-a@dept.test" in emails
        assert "user-b@dept.test" in emails

    async def test_list_members_nonexistent_department_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-listmem404@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)

        resp = await client.get(
            f"/departments/{uuid.uuid4()}/members",
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 404

    async def test_remove_member_returns_204(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-remmem@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        member = await _create_user(db_session, "member-rem@dept.test")
        headers = _auth_headers(admin)
        dept = await _create_dept_via_api(client, headers, name="Remove Member Dept", code="RMD")
        membership = await _add_member_via_api(client, dept["id"], str(member.id), headers)

        resp = await client.delete(
            f"/department-members/{membership['id']}",
            headers=headers,
        )

        assert resp.status_code == 204

        # Member no longer listed
        members_resp = await client.get(f"/departments/{dept['id']}/members", headers=headers)
        assert members_resp.json() == []

    async def test_remove_nonexistent_member_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-remnoexist@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)

        resp = await client.delete(
            f"/department-members/{uuid.uuid4()}",
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# USER DEPARTMENTS
# ---------------------------------------------------------------------------


class TestUserDepartments:
    async def test_get_user_departments_returns_list(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-userdepts@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        member = await _create_user(db_session, "member-userdepts@dept.test")
        headers = _auth_headers(admin)

        dept_a = await _create_dept_via_api(client, headers, name="User Dept A", code="UDA")
        dept_b = await _create_dept_via_api(client, headers, name="User Dept B", code="UDB")
        await _add_member_via_api(client, dept_a["id"], str(member.id), headers)
        await _add_member_via_api(client, dept_b["id"], str(member.id), headers)

        resp = await client.get(f"/users/{member.id}/departments", headers=headers)

        assert resp.status_code == 200
        depts = resp.json()
        assert len(depts) == 2
        ids = {d["id"] for d in depts}
        assert dept_a["id"] in ids
        assert dept_b["id"] in ids

    async def test_get_user_departments_empty_when_no_memberships(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-usernomem@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)
        user = await _create_user(db_session, "user-nomem@dept.test")

        resp = await client.get(
            f"/users/{user.id}/departments",
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 200
        assert resp.json() == []

    async def test_get_departments_for_nonexistent_user_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ) -> None:
        admin = await _create_user(db_session, "admin-usernotfound@dept.test")
        await _assign_role(db_session, admin.id, RoleName.admin, None)

        resp = await client.get(
            f"/users/{uuid.uuid4()}/departments",
            headers=_auth_headers(admin),
        )

        assert resp.status_code == 404
