# Bruno Collection

Open the repo collection at `bruno/` in Bruno.

## Local environment

Use `enviment.json` for persistent Bruno variables. The request flows also populate runtime vars such as `accessToken`, `refreshToken`, `projectId`, `episodeId`, and `shotId` as needed.

Persistent environment variables:

- `baseUrl`
- `email`
- `password`

Common runtime variables populated by the request flows:

- `accessToken`
- `refreshToken`
- `projectId`
- `shotId`
- `episodeId`
- `assetId`
- `sequenceId`

## Available flows

### `00 system`

- `auth-global`
- `metrics-global`

`auth-global` is the lightweight system auth flow: health, login, refresh, `me`, and logout.

`metrics-global` is the lightweight system observability flow: health plus `/metrics`.

### `01 project`

- `create project`
- `film`
- `series`
- `commercial`
- `game`
- `other`

Each folder is a self-contained Bruno collection that logs in, creates one project of that type, runs `/projects/{id}/scaffold`, validates the response, and deletes the created project.

### `01 project/create project`

1. Run `01 Health`
2. Run `02 Login`
3. Let `02 Login` store `accessToken` and `refreshToken` as Bruno runtime vars
4. Run `03 Me`
5. Run `04 Create Project`
6. Copy the returned project `id` into `projectId`
7. Run `06 Create Shot`
8. Let `06 Create Shot` store `shotId` as a Bruno runtime var and validate the response with Bruno tests
9. Run `07 Update Shot Status`

`05 List Projects` is useful to inspect data after login.

`accessToken` and `refreshToken` can still be copied into the environment if you want them to persist beyond the current Bruno session.
`shotId` can still be copied into the environment if you want it to persist beyond the current Bruno session.

### `02 shots`

- `film`
- `series`
- `commercial`
- `game`
- `other`

Each type folder creates a project for that `project_type`, creates a shot, runs `/projects/{id}/scaffold`, validates the created shot through the project shot list, deletes the shot, and deletes the project.

### `03 episodes`

- `film`
- `series`
- `commercial`
- `game`
- `other`

Each type folder creates a project for that `project_type`, creates an episode, runs `/projects/{id}/scaffold`, validates the created episode, deletes the episode, and deletes the project.

### `04 assets`

- `film`
- `series`
- `commercial`
- `game`
- `other`

Each type folder creates a project for that `project_type`, creates one asset, runs `/projects/{id}/scaffold`, validates the asset through the project asset list, deletes the asset, and deletes the project.

### `05 sequences`

- `film`
- `series`
- `commercial`
- `game`
- `other`

Each type folder creates a project for that `project_type`, creates one sequence, runs `/projects/{id}/scaffold`, validates the sequence, deletes the sequence, and deletes the project.

### `06 create series project`

- `create series project`

This collection is a full series happy-path setup. It logs in, creates a `series` project, creates multiple episodes, sequences, shots, and assets, runs `/projects/{id}/scaffold`, creates multiple pipeline tasks, submits versions, creates project and entity notes, creates a playlist and adds versions to it, creates departments, validates the created playlists, versions, and departments, deletes the temporary departments, and finally deletes the project with `force=True`.

### `07 files`

- `series`

This collection creates a `series` project context for files, creates one episode, one sequence, one shot, and one asset, runs `/projects/{id}/scaffold`, uploads two versions of the same shot file plus one asset file through `POST /projects/{id}/files/upload`, validates metadata and list endpoints, exercises the file versions and download endpoints, updates asset file metadata, deletes the uploaded file records, and finally deletes the project with `force=True`.

### `08 pipeline templates`

- `series`

This collection creates a `series` project context for pipeline templates and pipeline tasks, creates one pipeline template, validates get/list template endpoints, applies the template to a shot and an asset, validates the resulting task lists, creates standalone shot and asset tasks, validates get/update/status task endpoints, runs `/projects/{id}/scaffold` near the end to inspect the final project structure, deletes the standalone tasks and template, and finally deletes the project with `force=True`.

### `09 departments`

- `global`

Global departments flow: create, get, list, create a user, add a member, list members, list user departments, remove the member, and delete the department.

### `10 notes`

- `series`

Series notes flow: create project/shot/asset/task context, create notes on project, shot, asset, and task, reply to the project note, fetch the project note thread, archive the project note, then clean up.

### `11 users`

- `global`

Global users flow: create user, get user, update user, assign role, list roles, remove role, deactivate user.

### `12 notifications`

- `series`

Series notifications flow: create a secondary user, create project and shot context, create a task assigned to that user, log in as that user, list notifications, get unread count, mark one notification as read, and mark all notifications as read.

### `13 timelogs`

- `series`

Series timelogs flow: create project/shot/task context, create a timelog, get it, update it, list project timelogs, get the project summary, list task timelogs, then delete the timelog and project.

### `14 deliveries`

- `series`

Series deliveries flow: create project/shot/task/version context, create a delivery, add a delivery item, get and list deliveries, update delivery metadata, update delivery status, list delivery items, remove the item, then clean up.

### `15 tags`

- `series`

Series tags flow: create project/sequence/shot/asset context, create a project tag, attach it to shot, asset, and sequence, list tags for each entity, detach one entity-tag, delete the tag, then clean up.

### `16 versions`

- `series`

Series versions flow: create project/episode/sequence/shot/asset context, create shot and asset tasks, submit shot and asset versions, get and update a version, update version status, list shot, asset, and project versions, archive one version, then delete the project.

### `17 playlists`

- `series`

Series playlists flow: create project/shot/task/version context, create a playlist, add two versions, reorder playlist items, review one item with version propagation, get the playlist, list project playlists, remove one item, archive the playlist, and delete the project.

### `18 shot asset links`

- `series`

Series shot-asset-links flow: create project/shot/two-assets context, create a direct link, bulk-link assets to the shot, list shot assets, list asset shots, delete one link, and delete the project.

### `19 webhooks`

- `global`

Global webhooks flow: create a temporary project, create a project webhook, list all webhooks, list project webhooks, patch the webhook, archive it, restore it, hard-delete it with `force=True`, and finally delete the temporary project.
