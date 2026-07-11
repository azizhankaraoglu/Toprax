"""0001 -- Organizasyon Hiyerarsisi + Onay Zinciri + Case Management indexleri.

Bu modul(ler) (organization.py, approval.py, case_management.py) ilk
eklendiginde server.py'deki startup index blogu guncellenmemisti; bu
migration o eksigi gideriyor ve versiyonlu migration sisteminin (PR-04)
ilk gercek migration'i olarak hizmet ediyor.

NOT: `db` parametresi raw_db'dir (tenant filtresi yok) -- migration'lar
sema/index seviyesinde calisir, tenant'a ozel degildir.
"""

DESCRIPTION = "Organizasyon/Onay Zinciri/Case Management koleksiyonlarina index ekle"


async def up(db) -> None:
    await db.organization_units.create_index("id", unique=True)
    await db.organization_units.create_index("tenant_id")
    await db.organization_units.create_index("parent_id")

    await db.positions.create_index("id", unique=True)
    await db.positions.create_index("tenant_id")
    await db.positions.create_index("unit_id")

    await db.user_positions.create_index("id", unique=True)
    await db.user_positions.create_index("tenant_id")
    await db.user_positions.create_index("user_id")
    await db.user_positions.create_index("position_id")

    await db.approval_chain_rules.create_index("id", unique=True)
    await db.approval_chain_rules.create_index("tenant_id")
    await db.approval_chain_rules.create_index("process")

    await db.approval_instances.create_index("id", unique=True)
    await db.approval_instances.create_index("tenant_id")
    await db.approval_instances.create_index([("entity_type", 1), ("entity_id", 1)])
    await db.approval_instances.create_index("status")

    await db.cases.create_index("id", unique=True)
    await db.cases.create_index("tenant_id")
    await db.cases.create_index("status")
    await db.cases.create_index("assigned_to_user_id")

    await db.case_messages.create_index("id", unique=True)
    await db.case_messages.create_index("case_id")

    await db.case_categories.create_index("id", unique=True)
    await db.case_categories.create_index("tenant_id")


async def down(db) -> None:
    # create_index cagrilari idempotent oldugu gibi drop da oyle -- index
    # yoksa Mongo hata firlatir, bu yuzden tek tek yutuluyor (best-effort).
    drops = [
        ("organization_units", "id_1"), ("organization_units", "tenant_id_1"), ("organization_units", "parent_id_1"),
        ("positions", "id_1"), ("positions", "tenant_id_1"), ("positions", "unit_id_1"),
        ("user_positions", "id_1"), ("user_positions", "tenant_id_1"), ("user_positions", "user_id_1"), ("user_positions", "position_id_1"),
        ("approval_chain_rules", "id_1"), ("approval_chain_rules", "tenant_id_1"), ("approval_chain_rules", "process_1"),
        ("approval_instances", "id_1"), ("approval_instances", "tenant_id_1"), ("approval_instances", "entity_type_1_entity_id_1"), ("approval_instances", "status_1"),
        ("cases", "id_1"), ("cases", "tenant_id_1"), ("cases", "status_1"), ("cases", "assigned_to_user_id_1"),
        ("case_messages", "id_1"), ("case_messages", "case_id_1"),
        ("case_categories", "id_1"), ("case_categories", "tenant_id_1"),
    ]
    for coll, idx in drops:
        try:
            await db[coll].drop_index(idx)
        except Exception:
            pass
