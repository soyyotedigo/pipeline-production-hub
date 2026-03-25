# VFX Production Features

Documentation of the production-specific domains implemented on top of the projects/shots/assets foundation.

---

## 1. Pipeline Tasks

Pipeline tasks are the departmental unit of work. Each shot or asset passes through multiple steps (animation → lighting → compositing), each with its own status and assignee.

### Entities

```mermaid
erDiagram
    PIPELINE_TEMPLATES {
        uuid id PK
        string name
        PipelineStepAppliesTo applies_to
        uuid project_id FK
    }
    PIPELINE_TEMPLATE_STEPS {
        uuid id PK
        uuid template_id FK
        string step_name
        PipelineStepType step_type
        int order
    }
    PIPELINE_TASKS {
        uuid id PK
        uuid shot_id FK
        uuid asset_id FK
        uuid project_id FK
        string step_name
        PipelineStepType step_type
        PipelineTaskStatus status
        uuid assigned_to FK
        int bid_days
        datetime due_date
    }

    PIPELINE_TEMPLATES ||--o{ PIPELINE_TEMPLATE_STEPS : defines
    PIPELINE_TASKS }o--o| SHOTS : for_shot
    PIPELINE_TASKS }o--o| ASSETS : for_asset
```

### Key endpoints

```
GET/POST  /pipeline-templates
GET/POST  /shots/{id}/pipeline-tasks
GET/POST  /assets/{id}/pipeline-tasks
PATCH     /pipeline-tasks/{id}
PATCH     /pipeline-tasks/{id}/status
PATCH     /pipeline-tasks/{id}/assign
```

---

## 2. Notes / Feedback

The polymorphic feedback system allows leaving comments on any entity: shots, assets, versions, pipeline tasks, and projects. Supports threading via `parent_id`.

### Entity

```mermaid
erDiagram
    NOTES {
        uuid id PK
        uuid parent_id FK "threading"
        NoteEntityType entity_type
        uuid entity_id
        uuid project_id FK
        uuid author_id FK
        text body
        bool is_resolved
        datetime created_at
    }
```

### Feedback flow in dailies

```mermaid
sequenceDiagram
    participant S as Supervisor
    participant API as FastAPI
    participant NS as NoteService
    participant DB as PostgreSQL

    S->>API: POST /shots/{id}/notes {body: "Fix the shoulder pop at frame 42"}
    API->>NS: create(entity_type=shot, entity_id=shot_id)
    NS->>DB: INSERT notes
    API-->>S: NoteResponse

    S->>API: POST /notes/{id}/replies {body: "Fixed in v004"}
    API->>NS: create(parent_id=original_note_id)
    NS->>DB: INSERT notes (with parent_id)
    API-->>S: NoteResponse
```

### Key endpoints

```
POST   /shots/{id}/notes
POST   /assets/{id}/notes
POST   /pipeline-tasks/{id}/notes
POST   /projects/{id}/notes
POST   /notes/{id}/replies
GET    /notes/{id}
PATCH  /notes/{id}
PATCH  /notes/{id}/resolve
DELETE /notes/{id}
```

---

## 3. Versions / Publishes

A Version is an artist's reviewable delivery: "animation v003 of shot SH010". It groups the delivery metadata (review status, who submitted it, thumbnail) and is what gets presented in dailies.

### Review state machine

```mermaid
stateDiagram-v2
    [*] --> pending_review : artist publishes
    pending_review --> approved : supervisor approves
    pending_review --> revision_requested : supervisor requests changes
    revision_requested --> pending_review : artist re-submits
    approved --> final : marked as final
```

### Entity

```mermaid
erDiagram
    VERSIONS {
        uuid id PK
        uuid project_id FK
        uuid shot_id FK
        uuid asset_id FK
        uuid pipeline_task_id FK
        string code
        int version_number
        VersionStatus status
        uuid submitted_by FK
        uuid reviewed_by FK
        string thumbnail_url
        string media_url
    }
```

### Key endpoints

```
POST  /shots/{id}/versions
POST  /assets/{id}/versions
GET   /versions/{id}
PATCH /versions/{id}/status
GET   /pipeline-tasks/{id}/versions
```

---

## 4. Shot-Asset Links

Answers two key production questions: "What assets does shot SH010 use?" and "If I change this asset, which shots are affected?"

### Link types

| Type | Description |
|------|-------------|
| `uses` | Shot directly uses the asset |
| `references` | Shot references the asset (not a direct instance) |
| `instance_of` | Shot has a specific instance of the asset |

### Entity

```mermaid
erDiagram
    SHOT_ASSET_LINKS {
        uuid id PK
        uuid shot_id FK
        uuid asset_id FK
        LinkType link_type
        datetime created_at
    }
```

### Key endpoints

```
POST   /shots/{id}/assets           link asset to shot
DELETE /shots/{id}/assets/{asset_id}
GET    /shots/{id}/assets            assets used by the shot
GET    /assets/{id}/shots            shots that use the asset
```

---

## 5. Playlists / Review Sessions

Playlists organize versions for a dailies session. The supervisor can mark the review outcome per item.

### Session state machine

```mermaid
stateDiagram-v2
    [*] --> draft : create playlist
    draft --> in_review : start session
    in_review --> completed : finalize
    in_review --> draft : return to preparation
```

### Entities

```mermaid
erDiagram
    PLAYLISTS {
        uuid id PK
        uuid project_id FK
        string name
        PlaylistStatus status
        uuid created_by FK
        datetime scheduled_at
    }
    PLAYLIST_ITEMS {
        uuid id PK
        uuid playlist_id FK
        uuid version_id FK
        int order
        ReviewStatus review_status
        text review_note
    }

    PLAYLISTS ||--o{ PLAYLIST_ITEMS : contains
    PLAYLIST_ITEMS }o--|| VERSIONS : reviews
```

### Key endpoints

```
POST  /projects/{id}/playlists
GET   /playlists/{id}
POST  /playlists/{id}/items
PATCH /playlists/{id}/items/{item_id}/review
PATCH /playlists/{id}/status
```

---

## 6. Departments

Dynamic management of studio departments. Artists can belong to multiple departments.

### Entities

```mermaid
erDiagram
    DEPARTMENTS {
        uuid id PK
        string name
        string code
        string color
    }
    USER_DEPARTMENTS {
        uuid id PK
        uuid user_id FK
        uuid department_id FK
        bool is_primary
    }

    DEPARTMENTS ||--o{ USER_DEPARTMENTS : has
    USERS ||--o{ USER_DEPARTMENTS : member_of
```

### Key endpoints

```
POST   /departments
GET    /departments
PATCH  /departments/{id}
POST   /users/{id}/departments      assign user to department
DELETE /users/{id}/departments/{dept_id}
GET    /users/{id}/departments
```

---

## 7. Notifications

Internal notifications are auto-generated by system events: task assignments, received notes, approved versions.

### Event types

| Event | Description |
|-------|-------------|
| `task_assigned` | A pipeline task was assigned to the user |
| `task_status_changed` | Status changed on an assigned task |
| `note_created` | Someone left a note on the user's entity |
| `note_reply` | Someone replied to the user's note |
| `version_submitted` | An artist submitted a version for review |
| `version_reviewed` | The supervisor reviewed the artist's version |
| `mention` | The user was mentioned in a note |

### Flow

```mermaid
sequenceDiagram
    participant SVC as Any Service
    participant NS as NotificationService
    participant DB as PostgreSQL
    participant U as User

    SVC->>NS: create(user_id, event_type, entity_type, entity_id, title)
    NS->>DB: INSERT notifications
    U->>API: GET /notifications
    API-->>U: notification list
    U->>API: PATCH /notifications/{id}/read
    U->>API: POST /notifications/read-all
```

### Key endpoints

```
GET    /notifications
GET    /notifications/unread-count
PATCH  /notifications/{id}/read
POST   /notifications/read-all
DELETE /notifications/{id}
```

---

## 8. Tags

Polymorphic categorization system. Tags can be global (no `project_id`) or project-scoped.

### Entities

```mermaid
erDiagram
    TAGS {
        uuid id PK
        uuid project_id FK "nullable - null means global"
        string name
        string color "hex"
    }
    ENTITY_TAGS {
        uuid id PK
        uuid tag_id FK
        TagEntityType entity_type
        uuid entity_id
    }

    TAGS ||--o{ ENTITY_TAGS : applied_via
```

### Supported entity types

`project`, `episode`, `sequence`, `shot`, `asset`, `pipeline_task`, `version`

### Tagging flow

```mermaid
flowchart TD
    A[POST /tags] --> B[Create tag with scope]
    B --> C[POST /shots/id/tags - attach]
    C --> D[GET /projects/id/shots?tags=hero_shot - filter]
    D --> E[DELETE /shots/id/tags/tag_id - detach]
```

### Key endpoints

```
POST   /tags
GET    /tags?project_id=
GET    /tags/search?q=hero
PATCH  /tags/{id}
DELETE /tags/{id}

POST   /shots/{id}/tags
DELETE /shots/{id}/tags/{tag_id}
GET    /shots/{id}/tags

POST   /assets/{id}/tags
POST   /sequences/{id}/tags
```

---

## 9. TimeLogs

Hour tracking per artist and task. Allows comparing budgeted hours (`bid_days` on the shot) against actual hours worked.

### Validation rules

- `duration_minutes`: minimum 1, maximum 1440 (24h).
- `date`: cannot be in the future.
- Only the owner or admin can edit/delete a timelog.

### Entity

```mermaid
erDiagram
    TIME_LOGS {
        uuid id PK
        uuid project_id FK
        uuid pipeline_task_id FK "nullable"
        uuid user_id FK
        date date
        int duration_minutes
        text description
    }
```

### Bid vs Actual

```mermaid
flowchart TD
    A[GET /projects/id/timelogs/summary] --> B[SUM duration_minutes per user]
    B --> C[actual_days = minutes / 480]
    C --> D[SUM bid_days from project shots]
    D --> E[variance = bid_days - actual_days]
    E --> F{variance >= 0?}
    F -->|Yes| G[Under budget]
    F -->|No| H[Over budget]
```

### Key endpoints

```
POST   /timelogs
GET    /timelogs/{id}
PATCH  /timelogs/{id}
DELETE /timelogs/{id}

GET    /projects/{id}/timelogs
GET    /projects/{id}/timelogs/summary
GET    /pipeline-tasks/{id}/timelogs
GET    /users/{id}/timelogs?date_from=&date_to=
```

---

## 10. Deliveries

Tracks the full lifecycle of client deliveries — from preparation to client acceptance.

### Delivery state machine

```mermaid
stateDiagram-v2
    [*] --> preparing : create delivery
    preparing --> sent : send to client
    sent --> acknowledged : client confirms receipt
    acknowledged --> accepted : client approves
    acknowledged --> rejected : client rejects
    rejected --> preparing : correct and re-prepare

    note right of preparing
        Items can be added
        and removed
    end note

    note right of sent
        Items are locked
        (historical record)
    end note
```

### Entities

```mermaid
erDiagram
    DELIVERIES {
        uuid id PK
        uuid project_id FK
        string name
        date delivery_date
        string recipient
        DeliveryStatus status
        uuid created_by FK
    }
    DELIVERY_ITEMS {
        uuid id PK
        uuid delivery_id FK
        uuid version_id FK
        uuid shot_id FK "denormalized"
        text notes
    }

    DELIVERIES ||--o{ DELIVERY_ITEMS : contains
    DELIVERY_ITEMS }o--|| VERSIONS : delivers
    DELIVERY_ITEMS }o--o| SHOTS : for_shot
```

### Item locking rule

Items can only be added or removed when status is `preparing`. Once the delivery moves to `sent`, items are locked as a historical record.

### Key endpoints

```
POST   /projects/{id}/deliveries
GET    /projects/{id}/deliveries?status=sent
GET    /deliveries/{id}
PATCH  /deliveries/{id}
PATCH  /deliveries/{id}/status
DELETE /deliveries/{id}

POST   /deliveries/{id}/items
GET    /deliveries/{id}/items
DELETE /deliveries/{id}/items/{item_id}
```
