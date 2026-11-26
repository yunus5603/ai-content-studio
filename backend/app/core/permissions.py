"""Workspace roles and what each one may do.

Roles are ordered: each role can do everything the roles below it can.
  viewer  - browse the gallery, jobs and members
  member  - also upload media and run generations
  admin   - also invite, remove and change roles of members and admins
  owner   - also rename/delete the workspace and manage billing; one per workspace
"""

import enum


class Role(enum.StrEnum):
    viewer = "viewer"
    member = "member"
    admin = "admin"
    owner = "owner"


_RANK = {Role.viewer: 0, Role.member: 1, Role.admin: 2, Role.owner: 3}


class Action(enum.StrEnum):
    view = "view"
    generate = "generate"
    upload = "upload"
    delete_own_asset = "delete_own_asset"
    delete_any_asset = "delete_any_asset"
    manage_members = "manage_members"
    manage_workspace = "manage_workspace"
    manage_billing = "manage_billing"


_REQUIRED: dict[Action, Role] = {
    Action.view: Role.viewer,
    Action.generate: Role.member,
    Action.upload: Role.member,
    Action.delete_own_asset: Role.member,
    Action.delete_any_asset: Role.admin,
    Action.manage_members: Role.admin,
    Action.manage_workspace: Role.owner,
    Action.manage_billing: Role.owner,
}


def at_least(role: Role, minimum: Role) -> bool:
    return _RANK[role] >= _RANK[minimum]


def can(role: Role, action: Action) -> bool:
    return at_least(role, _REQUIRED[action])


def can_assign(actor: Role, current: Role | None, new: Role) -> bool:
    """Whether `actor` may move a member from `current` (None = new invite) to `new`.

    Nobody assigns `owner` through this path (ownership transfer is separate),
    and admins cannot touch the owner.
    """
    if new == Role.owner or current == Role.owner:
        return False
    return can(actor, Action.manage_members)


def permissions_for(role: Role) -> list[str]:
    return [a.value for a in Action if can(role, a)]
