import time
import uuid
from sqlalchemy import LargeBinary, create_engine, event, String, Integer, Text, JSON, UniqueConstraint, Float, ForeignKeyConstraint, ForeignKey, BigInteger, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


def uid(): return str(uuid.uuid4())
def now(): return time.time()

CURRENT_SCHEMA = 12


class Base(DeclarativeBase): pass


class Organization(Base):
    __tablename__ = 'organizations'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)


class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(String, index=True)
    email: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String)
    password_hash: Mapped[str] = mapped_column(String, default='!')
    role: Mapped[str] = mapped_column(String)
    active: Mapped[int] = mapped_column(Integer, default=1)
    oidc_subject: Mapped[str | None] = mapped_column(String, nullable=True, unique=True)


user_organization_index = Index('uq_users_id_org_id',User.id,User.org_id,unique=True)


class WorkspaceEnvironment(Base):
    __tablename__ = 'workspace_environments'
    org_id: Mapped[str] = mapped_column(ForeignKey('organizations.id'), primary_key=True)
    key: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String, default='preparing')
    version: Mapped[int] = mapped_column(Integer, default=1)
    created: Mapped[float] = mapped_column(Float, default=now)
    updated: Mapped[float] = mapped_column(Float, default=now)


class EnvironmentAssignment(Base):
    __tablename__ = 'environment_assignments'
    __table_args__ = (ForeignKeyConstraint(['org_id','environment_key'],
                        ['workspace_environments.org_id','workspace_environments.key']),
                     ForeignKeyConstraint(['user_id','org_id'],['users.id','users.org_id']))
    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    org_id: Mapped[str] = mapped_column(String, primary_key=True)
    environment_key: Mapped[str] = mapped_column(String, primary_key=True)
    created: Mapped[float] = mapped_column(Float, default=now)


class SessionRecord(Base):
    __tablename__ = 'sessions'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String)
    csrf: Mapped[str] = mapped_column(String)
    expires: Mapped[float] = mapped_column(Float)


class OIDCTransaction(Base):
    __tablename__ = 'oidc_transactions'
    id: Mapped[str] = mapped_column(String, primary_key=True)
    binding_hash: Mapped[str] = mapped_column(String)
    nonce: Mapped[str] = mapped_column(String)
    verifier_ciphertext: Mapped[str] = mapped_column(Text)
    expires: Mapped[float] = mapped_column(Float, index=True)
    used_at: Mapped[float] = mapped_column(Float, default=0)


class SessionRuntimeContext(Base):
    __tablename__ = 'session_runtime_contexts'
    __table_args__ = (ForeignKeyConstraint(['user_id','org_id'],['users.id','users.org_id']),
                     ForeignKeyConstraint(['org_id','environment'],['workspace_environments.org_id','workspace_environments.key']))
    session_id: Mapped[str] = mapped_column(ForeignKey('sessions.id',ondelete='CASCADE'),primary_key=True)
    user_id: Mapped[str] = mapped_column(String)
    org_id: Mapped[str] = mapped_column(String)
    environment: Mapped[str] = mapped_column(String)
    revision: Mapped[int] = mapped_column(Integer,default=1)
    binding_id: Mapped[str] = mapped_column(String,default=uid)


class Scoped:
    id: Mapped[str] = mapped_column(String, primary_key=True, default=uid)
    org_id: Mapped[str] = mapped_column(String, index=True)
    env: Mapped[str] = mapped_column(String, default='staging')
    created: Mapped[float] = mapped_column(Float, default=now)


class Agent(Scoped, Base):
    __tablename__ = 'agents'
    __table_args__ = (UniqueConstraint('id', 'org_id', 'env'),)
    name: Mapped[str] = mapped_column(String)
    owner_id: Mapped[str] = mapped_column(String)
    framework: Mapped[str] = mapped_column(String, default='Python SDK')
    version: Mapped[str] = mapped_column(String, default='0.1.0')
    status: Mapped[str] = mapped_column(String, default='draft')
    risk: Mapped[str] = mapped_column(String, default='medium')
    generation: Mapped[int] = mapped_column(Integer, default=1)
    credential_hash: Mapped[str] = mapped_column(String, default='')


class Tool(Scoped, Base):
    __tablename__ = 'tools'
    __table_args__ = (UniqueConstraint('id', 'org_id', 'env'),)
    name: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    version: Mapped[str] = mapped_column(String, default='1.0')
    risk: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default='validated')
    schema_json: Mapped[dict] = mapped_column(JSON, default=dict)


class Grant(Scoped, Base):
    __tablename__ = 'grants'
    __table_args__ = (
        ForeignKeyConstraint(['agent_id', 'org_id', 'env'], ['agents.id', 'agents.org_id', 'agents.env']),
        ForeignKeyConstraint(['tool_id', 'org_id', 'env'], ['tools.id', 'tools.org_id', 'tools.env']),
        UniqueConstraint('agent_id', 'tool_id', 'scope'),
    )
    agent_id: Mapped[str] = mapped_column(String, index=True)
    tool_id: Mapped[str] = mapped_column(String)
    scope: Mapped[str] = mapped_column(String)


class Policy(Scoped, Base):
    __tablename__ = 'policies'
    __table_args__ = (UniqueConstraint('org_id', 'env', 'version'),)
    version: Mapped[int] = mapped_column(Integer)
    threshold: Mapped[str] = mapped_column(String, default='5000.00')
    maximum: Mapped[str] = mapped_column(String, default='25000.00')
    active: Mapped[int] = mapped_column(Integer, default=1)
    name: Mapped[str] = mapped_column(String, default='Business action guardrails')


class Action(Scoped, Base):
    __tablename__ = 'actions'
    __table_args__ = (
        ForeignKeyConstraint(['agent_id', 'org_id', 'env'], ['agents.id', 'agents.org_id', 'agents.env']),
        ForeignKeyConstraint(['tool_id', 'org_id', 'env'], ['tools.id', 'tools.org_id', 'tools.env']),
        UniqueConstraint('org_id', 'env', 'principal', 'idem_key'),
    )
    agent_id: Mapped[str] = mapped_column(String, index=True)
    tool_id: Mapped[str] = mapped_column(String)
    requester_id: Mapped[str] = mapped_column(String)
    principal: Mapped[str] = mapped_column(String)
    idem_key: Mapped[str] = mapped_column(String)
    request_digest: Mapped[str] = mapped_column(String)
    envelope: Mapped[dict] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String)
    policy_version: Mapped[int] = mapped_column(Integer)
    generation: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, index=True)
    trace_id: Mapped[str] = mapped_column(String, default=uid)
    external_ref: Mapped[str | None] = mapped_column(String, nullable=True)
    verification: Mapped[dict] = mapped_column(JSON, default=dict)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[float] = mapped_column(Float, default=0)
    updated: Mapped[float] = mapped_column(Float, default=now)


class Approval(Scoped, Base):
    __tablename__ = 'approvals'
    action_id: Mapped[str] = mapped_column(String, unique=True)
    payload_hash: Mapped[str] = mapped_column(String)
    policy_version: Mapped[int] = mapped_column(Integer)
    requester_id: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default='pending')
    version: Mapped[int] = mapped_column(Integer, default=1)
    expires: Mapped[float] = mapped_column(Float)
    approver_id: Mapped[str | None] = mapped_column(String, nullable=True)
    comment: Mapped[str] = mapped_column(Text, default='')


class Audit(Scoped, Base):
    __tablename__ = 'audit_events'
    event: Mapped[str] = mapped_column(String, index=True)
    actor: Mapped[str] = mapped_column(String)
    action_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    trace_id: Mapped[str | None] = mapped_column(String, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class Export(Scoped, Base):
    __tablename__ = 'audit_exports'
    owner_id: Mapped[str] = mapped_column(String)
    expires: Mapped[float] = mapped_column(Float)
    records: Mapped[list] = mapped_column(JSON)


class Evaluation(Scoped, Base):
    __tablename__ = 'evaluation_runs'
    suite: Mapped[str] = mapped_column(String)
    cases: Mapped[list] = mapped_column(JSON)
    passed: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)


class Incident(Scoped, Base):
    __tablename__ = 'incidents'
    agent_id: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String, default='high')
    status: Mapped[str] = mapped_column(String, default='open')
    reason: Mapped[str] = mapped_column(Text)


class DurableRun(Scoped, Base):
    __tablename__ = 'durable_runs'
    __table_args__ = (UniqueConstraint('id','org_id','env'),UniqueConstraint('org_id','env','author_id','idem_key',name='uq_durable_runs_runtime_key'))
    name: Mapped[str] = mapped_column(String)
    agent_id: Mapped[str] = mapped_column(String)
    generation: Mapped[int] = mapped_column(Integer)
    author_id: Mapped[str] = mapped_column(String)
    definition: Mapped[dict] = mapped_column(JSON)
    payload_hash: Mapped[str] = mapped_column(String)
    idem_key: Mapped[str] = mapped_column(String)
    request_digest: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String,index=True,default='queued')
    cursor: Mapped[int] = mapped_column(Integer,default=0)
    version: Mapped[int] = mapped_column(Integer,default=1)
    updated: Mapped[float] = mapped_column(Float,default=now)
    next_poll: Mapped[float] = mapped_column(Float,default=0,index=True)
    lease_until: Mapped[float] = mapped_column(Float,default=0)
    lease_token: Mapped[str] = mapped_column(String,default='')
    review_until: Mapped[float] = mapped_column(Float,default=0)
    cancel_requested: Mapped[int] = mapped_column(Integer,default=0)
    resume_state: Mapped[str] = mapped_column(String,default='queued')
    error: Mapped[str] = mapped_column(String,default='')
    recoveries: Mapped[int] = mapped_column(Integer,default=0)


class DurableStep(Scoped, Base):
    __tablename__ = 'durable_steps'
    __table_args__ = (ForeignKeyConstraint(['run_id','org_id','env'],['durable_runs.id','durable_runs.org_id','durable_runs.env']),UniqueConstraint('run_id','position'))
    run_id: Mapped[str] = mapped_column(String,index=True)
    position: Mapped[int] = mapped_column(Integer)
    label: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String,default='pending')
    action_id: Mapped[str | None] = mapped_column(String,nullable=True)
    result: Mapped[dict] = mapped_column(JSON,default=dict)
    updated: Mapped[float] = mapped_column(Float,default=now)


class KnowledgeDocument(Scoped, Base):
    __tablename__ = 'knowledge_documents'
    __table_args__ = (UniqueConstraint('id','org_id','env'),UniqueConstraint('org_id','env','author_id','idem_key',name='uq_knowledge_documents_runtime_key'))
    title: Mapped[str] = mapped_column(String)
    filename: Mapped[str] = mapped_column(String)
    author_id: Mapped[str] = mapped_column(String)
    language: Mapped[str] = mapped_column(String,default='English')
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String)
    byte_count: Mapped[int] = mapped_column(Integer)
    allowed_roles: Mapped[list] = mapped_column(JSON,default=list)
    allowed_users: Mapped[list] = mapped_column(JSON,default=list)
    version: Mapped[int] = mapped_column(Integer,default=1)
    status: Mapped[str] = mapped_column(String,default='indexed')
    updated: Mapped[float] = mapped_column(Float,default=now)
    idem_key: Mapped[str] = mapped_column(String)
    request_digest: Mapped[str] = mapped_column(String)


class DocumentChunk(Scoped, Base):
    __tablename__ = 'document_chunks'
    __table_args__ = (ForeignKeyConstraint(['document_id','org_id','env'],['knowledge_documents.id','knowledge_documents.org_id','knowledge_documents.env']),UniqueConstraint('document_id','position'))
    document_id: Mapped[str] = mapped_column(String,index=True)
    document_version: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(String)


class DocumentUpdate(Scoped, Base):
    __tablename__ = 'document_updates'
    __table_args__ = (ForeignKeyConstraint(['document_id','org_id','env'],['knowledge_documents.id','knowledge_documents.org_id','knowledge_documents.env']),UniqueConstraint('org_id','env','author_id','idem_key',name='uq_document_updates_runtime_key'))
    document_id: Mapped[str] = mapped_column(String,index=True)
    author_id: Mapped[str] = mapped_column(String)
    idem_key: Mapped[str] = mapped_column(String)
    request_digest: Mapped[str] = mapped_column(String)
    receipt: Mapped[dict] = mapped_column(JSON)


class RetrievalCheck(Scoped, Base):
    __tablename__ = 'retrieval_checks'
    __table_args__ = (UniqueConstraint('org_id','env','author_id','idem_key',name='uq_retrieval_checks_runtime_key'),)
    author_id: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    config: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    idem_key: Mapped[str] = mapped_column(String)
    request_digest: Mapped[str] = mapped_column(String)


class IngestionJob(Scoped, Base):
    __tablename__ = 'ingestion_jobs'
    __table_args__ = (UniqueConstraint('org_id','env','author_id','idem_key',name='uq_ingestion_jobs_runtime_key'),)
    author_id: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    filename: Mapped[str] = mapped_column(String)
    format: Mapped[str] = mapped_column(String)
    language: Mapped[str] = mapped_column(String)
    extraction_mode: Mapped[str] = mapped_column(String,default='auto')
    original_data: Mapped[bytes] = mapped_column(LargeBinary,default=bytes)
    original_sha256: Mapped[str] = mapped_column(String)
    original_bytes: Mapped[int] = mapped_column(Integer)
    extracted_text: Mapped[str] = mapped_column(Text,default='')
    extraction: Mapped[dict] = mapped_column(JSON,default=dict)
    allowed_roles: Mapped[list] = mapped_column(JSON,default=list)
    allowed_users: Mapped[list] = mapped_column(JSON,default=list)
    status: Mapped[str] = mapped_column(String,default='queued',index=True)
    version: Mapped[int] = mapped_column(Integer,default=1)
    attempts: Mapped[int] = mapped_column(Integer,default=0)
    error_code: Mapped[str] = mapped_column(String,default='')
    lease_token: Mapped[str] = mapped_column(String,default='')
    lease_until: Mapped[float] = mapped_column(Float,default=0)
    updated: Mapped[float] = mapped_column(Float,default=now)
    expires: Mapped[float] = mapped_column(Float,default=lambda:now()+86400)
    document_id: Mapped[str | None] = mapped_column(String,nullable=True)
    published_version: Mapped[int] = mapped_column(Integer,default=0)
    idem_key: Mapped[str] = mapped_column(String)
    request_digest: Mapped[str] = mapped_column(String)


class SchemaVersion(Base):
    __tablename__ = 'schema_versions'
    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied: Mapped[float] = mapped_column(Float, default=now)


class WorkspaceAsset(Scoped, Base):
    __tablename__ = 'workspace_assets'
    kind: Mapped[str] = mapped_column(String, index=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String, default='draft')
    version: Mapped[int] = mapped_column(Integer, default=1)
    config: Mapped[dict] = mapped_column(JSON)
    updated: Mapped[float] = mapped_column(Float, default=now)
    author_id: Mapped[str] = mapped_column(String)


class AssetRevision(Scoped, Base):
    __tablename__ = 'asset_revisions'
    __table_args__ = (UniqueConstraint('asset_id', 'version'),)
    asset_id: Mapped[str] = mapped_column(String, index=True)
    version: Mapped[int] = mapped_column(Integer)
    snapshot: Mapped[dict] = mapped_column(JSON)
    author_id: Mapped[str] = mapped_column(String)


class NeuralIndex(Scoped, Base):
    __tablename__ = 'neural_indexes'
    __table_args__ = (UniqueConstraint('id','org_id','env'),
                     UniqueConstraint('org_id','env','author_id','idem_key'),
                     ForeignKeyConstraint(['author_id','org_id'],['users.id','users.org_id']))
    author_id: Mapped[str] = mapped_column(String)
    name: Mapped[str] = mapped_column(String)
    model: Mapped[str] = mapped_column(String)
    model_digest: Mapped[str] = mapped_column(String)
    dimensions: Mapped[int] = mapped_column(Integer)
    entry_count: Mapped[int] = mapped_column(Integer)
    sources: Mapped[list] = mapped_column(JSON)
    content_hash: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String,default='ready')
    version: Mapped[int] = mapped_column(Integer,default=1)
    idem_key: Mapped[str] = mapped_column(String)
    request_digest: Mapped[str] = mapped_column(String)


class NeuralVector(Scoped, Base):
    __tablename__ = 'neural_vectors'
    __table_args__ = (ForeignKeyConstraint(['index_id','org_id','env'],['neural_indexes.id','neural_indexes.org_id','neural_indexes.env'],ondelete='CASCADE'),
                     ForeignKeyConstraint(['document_id','org_id','env'],['knowledge_documents.id','knowledge_documents.org_id','knowledge_documents.env']),
                     UniqueConstraint('index_id','document_id','position'))
    index_id: Mapped[str] = mapped_column(String,index=True)
    document_id: Mapped[str] = mapped_column(String,index=True)
    document_version: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)
    chunk_hash: Mapped[str] = mapped_column(String)
    vector: Mapped[list] = mapped_column(JSON)


class WorkbenchRun(Scoped, Base):
    __tablename__ = 'workbench_runs'
    asset_id: Mapped[str | None] = mapped_column(String, nullable=True)
    kind: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String)
    asset_version: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[float] = mapped_column(Float)
    result: Mapped[dict] = mapped_column(JSON)
    author_id: Mapped[str] = mapped_column(String)


class InferenceBudget(Scoped, Base):
    __tablename__ = 'inference_budgets'
    __table_args__ = (UniqueConstraint('org_id', 'period'),)
    period: Mapped[str] = mapped_column(String)
    held: Mapped[int] = mapped_column(BigInteger, default=0)
    spent: Mapped[int] = mapped_column(BigInteger, default=0)


class InferenceCall(Scoped, Base):
    __tablename__ = 'inference_calls'
    __table_args__ = (UniqueConstraint('org_id','env','key_hash',name='uq_inference_calls_runtime_key'),)
    key_hash: Mapped[str] = mapped_column(String)
    request_hash: Mapped[str] = mapped_column(String)
    author_id: Mapped[str] = mapped_column(String)
    asset_id: Mapped[str] = mapped_column(String)
    asset_version: Mapped[int] = mapped_column(Integer)
    period: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default='pending')
    reserved: Mapped[int] = mapped_column(BigInteger)
    charged: Mapped[int] = mapped_column(BigInteger, default=0)
    input_rate: Mapped[str] = mapped_column(String)
    output_rate: Mapped[str] = mapped_column(String)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    duration_ms: Mapped[float] = mapped_column(Float, default=0)
    result: Mapped[dict] = mapped_column(JSON, default=dict)


class ReadinessEvidence(Scoped, Base):
    __tablename__ = 'readiness_evidence'
    __table_args__ = (UniqueConstraint('org_id', 'env', 'gate'),)
    gate: Mapped[str] = mapped_column(String)
    outcome: Mapped[str] = mapped_column(String, default='not_tested')
    summary: Mapped[str] = mapped_column(Text)
    reference: Mapped[str] = mapped_column(String, default='')
    version: Mapped[int] = mapped_column(Integer, default=1)
    updated: Mapped[float] = mapped_column(Float, default=now)
    author_id: Mapped[str] = mapped_column(String)


def database(url):
    engine = create_engine(url, connect_args={'check_same_thread': False, 'timeout': 30} if url.startswith('sqlite') else {}, pool_pre_ping=True)
    if url.startswith('sqlite'):
        @event.listens_for(engine, 'connect')
        def sqlite_config(conn, _):
            conn.execute('PRAGMA foreign_keys=ON'); conn.execute('PRAGMA journal_mode=WAL')
    return engine, sessionmaker(engine, expire_on_commit=False)


def migrate(engine, factory):
    """Forward-only schema upgrades. Existing v1 data is preserved; unknown newer schemas refuse upgrade."""
    from sqlalchemy import select, func, text, inspect
    from .request_key_migration import migration_connection, migrate_request_keys
    with migration_connection(engine) as connection:
        if engine.dialect.name == 'postgresql':
            connection.execute(text('SELECT pg_advisory_xact_lock(782451201)'))
        SchemaVersion.__table__.create(connection, checkfirst=True)
        version = connection.scalar(select(func.max(SchemaVersion.version))) or 0
        if version > CURRENT_SCHEMA: raise RuntimeError('Database schema is newer than this application; upgrade the source first.')
        if version < 1:
            baseline = [t for t in Base.metadata.sorted_tables if t.name not in ('neural_indexes','neural_vectors','session_runtime_contexts','workspace_environments','environment_assignments','oidc_transactions', 'workspace_assets', 'asset_revisions', 'workbench_runs', 'inference_calls', 'inference_budgets', 'readiness_evidence','durable_runs','durable_steps','knowledge_documents','document_chunks','document_updates','retrieval_checks','ingestion_jobs')]
            Base.metadata.create_all(connection, tables=baseline)
            connection.execute(SchemaVersion.__table__.insert().values(version=1, applied=now()))
        if version < 2:
            OIDCTransaction.__table__.create(connection, checkfirst=True)
            connection.execute(SchemaVersion.__table__.insert().values(version=2, applied=now()))
        if version < 3:
            for model in (WorkspaceAsset, AssetRevision, WorkbenchRun):
                model.__table__.create(connection, checkfirst=True)
            connection.execute(SchemaVersion.__table__.insert().values(version=3, applied=now()))


        if version < 4:
            for model in (InferenceBudget, InferenceCall):
                model.__table__.create(connection, checkfirst=True)
            connection.execute(SchemaVersion.__table__.insert().values(version=4, applied=now()))


        if version < 5:
            ReadinessEvidence.__table__.create(connection, checkfirst=True)
            connection.execute(SchemaVersion.__table__.insert().values(version=5, applied=now()))

        if version < 6:
            for model in (DurableRun,DurableStep,KnowledgeDocument,DocumentChunk):
                model.__table__.create(connection,checkfirst=True)
            connection.execute(SchemaVersion.__table__.insert().values(version=6,applied=now()))

        if version < 7:
            for model in (DocumentUpdate,RetrievalCheck):
                model.__table__.create(connection,checkfirst=True)
            connection.execute(SchemaVersion.__table__.insert().values(version=7,applied=now()))

        if version < 8:
            IngestionJob.__table__.create(connection,checkfirst=True)
            connection.execute(SchemaVersion.__table__.insert().values(version=8,applied=now()))

        if version < 9:
            user_organization_index.create(connection,checkfirst=True)
            WorkspaceEnvironment.__table__.create(connection,checkfirst=True)
            EnvironmentAssignment.__table__.create(connection,checkfirst=True)
            # Add registry records only. Never rewrite existing business rows or grant
            # users access to non-staging environments discovered in legacy data.
            existing=set(connection.execute(select(WorkspaceEnvironment.org_id,WorkspaceEnvironment.key)).all())
            organizations=set(connection.scalars(select(Organization.id)))
            contexts={(org,'staging') for org in organizations}
            existing_tables=set(inspect(connection).get_table_names())
            for table in Base.metadata.sorted_tables:
                if table.name in existing_tables and 'org_id' in table.c and 'env' in table.c:
                    contexts.update((org,env) for org,env in connection.execute(select(table.c.org_id,table.c.env).distinct()) if org in organizations)
            for org,key in sorted(contexts-existing):
                connection.execute(WorkspaceEnvironment.__table__.insert().values(org_id=org,key=key,name='Staging' if key=='staging' else key,state='active' if key=='staging' else 'preparing',version=1,created=now(),updated=now()))
            assigned=set(connection.execute(select(EnvironmentAssignment.user_id,EnvironmentAssignment.org_id,EnvironmentAssignment.environment_key)).all())
            for user_id,org in connection.execute(select(User.id,User.org_id)):
                if org in organizations and (user_id,org,'staging') not in assigned:
                    connection.execute(EnvironmentAssignment.__table__.insert().values(user_id=user_id,org_id=org,environment_key='staging',created=now()))
            connection.execute(SchemaVersion.__table__.insert().values(version=9,applied=now()))

        if version < 10:
            SessionRuntimeContext.__table__.create(connection,checkfirst=True)
            existing=set(connection.scalars(select(SessionRuntimeContext.session_id)))
            # Legacy sessions never selected an environment. Preserve every
            # credential and add staging metadata only; grant no membership.
            for session_id,user_id,org in connection.execute(select(SessionRecord.id,User.id,User.org_id).join(User,User.id==SessionRecord.user_id)):
                if session_id not in existing:
                    connection.execute(SessionRuntimeContext.__table__.insert().values(session_id=session_id,user_id=user_id,org_id=org,environment='staging',revision=1,binding_id=uid()))
            connection.execute(SchemaVersion.__table__.insert().values(version=10,applied=now()))

        if version < 11:
            migrate_request_keys(connection,Base.metadata)
            connection.execute(SchemaVersion.__table__.insert().values(version=11,applied=now()))

        if version < 12:
            for model in (NeuralIndex,NeuralVector):model.__table__.create(connection,checkfirst=True)
            connection.execute(SchemaVersion.__table__.insert().values(version=12,applied=now()))


def public(row):
    hidden = {'vector', 'original_data', 'extracted_text', 'lease_token', 'password_hash', 'credential_hash', 'csrf', 'idem_key', 'request_digest', 'key_hash', 'request_hash'}
    return {col.name: getattr(row, col.name) for col in row.__table__.columns if col.name not in hidden}
