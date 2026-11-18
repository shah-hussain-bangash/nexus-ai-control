-- Generated from SQLAlchemy metadata v1; not executed against PostgreSQL in this delivery.

CREATE TABLE organizations (
	id VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE users (
	id VARCHAR NOT NULL, 
	org_id VARCHAR NOT NULL, 
	email VARCHAR NOT NULL, 
	name VARCHAR NOT NULL, 
	password_hash VARCHAR NOT NULL, 
	role VARCHAR NOT NULL, 
	active INTEGER NOT NULL, 
	oidc_subject VARCHAR, 
	PRIMARY KEY (id), 
	UNIQUE (email), 
	UNIQUE (oidc_subject)
);

CREATE INDEX ix_users_org_id ON users (org_id);

CREATE TABLE sessions (
	id VARCHAR NOT NULL, 
	user_id VARCHAR NOT NULL, 
	csrf VARCHAR NOT NULL, 
	expires FLOAT NOT NULL, 
	PRIMARY KEY (id)
);

CREATE TABLE agents (
	name VARCHAR NOT NULL, 
	owner_id VARCHAR NOT NULL, 
	framework VARCHAR NOT NULL, 
	version VARCHAR NOT NULL, 
	status VARCHAR NOT NULL, 
	risk VARCHAR NOT NULL, 
	generation INTEGER NOT NULL, 
	credential_hash VARCHAR NOT NULL, 
	id VARCHAR NOT NULL, 
	org_id VARCHAR NOT NULL, 
	env VARCHAR NOT NULL, 
	created FLOAT NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (id, org_id, env)
);

CREATE INDEX ix_agents_org_id ON agents (org_id);

CREATE TABLE tools (
	name VARCHAR NOT NULL, 
	kind VARCHAR NOT NULL, 
	version VARCHAR NOT NULL, 
	risk VARCHAR NOT NULL, 
	status VARCHAR NOT NULL, 
	schema_json JSON NOT NULL, 
	id VARCHAR NOT NULL, 
	org_id VARCHAR NOT NULL, 
	env VARCHAR NOT NULL, 
	created FLOAT NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (id, org_id, env)
);

CREATE INDEX ix_tools_org_id ON tools (org_id);

CREATE TABLE policies (
	version INTEGER NOT NULL, 
	threshold VARCHAR NOT NULL, 
	maximum VARCHAR NOT NULL, 
	active INTEGER NOT NULL, 
	name VARCHAR NOT NULL, 
	id VARCHAR NOT NULL, 
	org_id VARCHAR NOT NULL, 
	env VARCHAR NOT NULL, 
	created FLOAT NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (org_id, env, version)
);

CREATE INDEX ix_policies_org_id ON policies (org_id);

CREATE TABLE approvals (
	action_id VARCHAR NOT NULL, 
	payload_hash VARCHAR NOT NULL, 
	policy_version INTEGER NOT NULL, 
	requester_id VARCHAR NOT NULL, 
	status VARCHAR NOT NULL, 
	version INTEGER NOT NULL, 
	expires FLOAT NOT NULL, 
	approver_id VARCHAR, 
	comment TEXT NOT NULL, 
	id VARCHAR NOT NULL, 
	org_id VARCHAR NOT NULL, 
	env VARCHAR NOT NULL, 
	created FLOAT NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (action_id)
);

CREATE INDEX ix_approvals_org_id ON approvals (org_id);

CREATE TABLE audit_events (
	event VARCHAR NOT NULL, 
	actor VARCHAR NOT NULL, 
	action_id VARCHAR, 
	trace_id VARCHAR, 
	detail JSON NOT NULL, 
	id VARCHAR NOT NULL, 
	org_id VARCHAR NOT NULL, 
	env VARCHAR NOT NULL, 
	created FLOAT NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_audit_events_event ON audit_events (event);

CREATE INDEX ix_audit_events_org_id ON audit_events (org_id);

CREATE INDEX ix_audit_events_action_id ON audit_events (action_id);

CREATE TABLE audit_exports (
	owner_id VARCHAR NOT NULL, 
	expires FLOAT NOT NULL, 
	records JSON NOT NULL, 
	id VARCHAR NOT NULL, 
	org_id VARCHAR NOT NULL, 
	env VARCHAR NOT NULL, 
	created FLOAT NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_audit_exports_org_id ON audit_exports (org_id);

CREATE TABLE evaluation_runs (
	suite VARCHAR NOT NULL, 
	cases JSON NOT NULL, 
	passed INTEGER NOT NULL, 
	total INTEGER NOT NULL, 
	id VARCHAR NOT NULL, 
	org_id VARCHAR NOT NULL, 
	env VARCHAR NOT NULL, 
	created FLOAT NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_evaluation_runs_org_id ON evaluation_runs (org_id);

CREATE TABLE incidents (
	agent_id VARCHAR NOT NULL, 
	title VARCHAR NOT NULL, 
	severity VARCHAR NOT NULL, 
	status VARCHAR NOT NULL, 
	reason TEXT NOT NULL, 
	id VARCHAR NOT NULL, 
	org_id VARCHAR NOT NULL, 
	env VARCHAR NOT NULL, 
	created FLOAT NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_incidents_org_id ON incidents (org_id);

CREATE TABLE schema_versions (
	version SERIAL NOT NULL, 
	applied FLOAT NOT NULL, 
	PRIMARY KEY (version)
);

CREATE TABLE grants (
	agent_id VARCHAR NOT NULL, 
	tool_id VARCHAR NOT NULL, 
	scope VARCHAR NOT NULL, 
	id VARCHAR NOT NULL, 
	org_id VARCHAR NOT NULL, 
	env VARCHAR NOT NULL, 
	created FLOAT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(agent_id, org_id, env) REFERENCES agents (id, org_id, env), 
	FOREIGN KEY(tool_id, org_id, env) REFERENCES tools (id, org_id, env), 
	UNIQUE (agent_id, tool_id, scope)
);

CREATE INDEX ix_grants_org_id ON grants (org_id);

CREATE INDEX ix_grants_agent_id ON grants (agent_id);

CREATE TABLE actions (
	agent_id VARCHAR NOT NULL, 
	tool_id VARCHAR NOT NULL, 
	requester_id VARCHAR NOT NULL, 
	principal VARCHAR NOT NULL, 
	idem_key VARCHAR NOT NULL, 
	request_digest VARCHAR NOT NULL, 
	envelope JSON NOT NULL, 
	payload_hash VARCHAR NOT NULL, 
	policy_version INTEGER NOT NULL, 
	generation INTEGER NOT NULL, 
	decision VARCHAR NOT NULL, 
	reason VARCHAR NOT NULL, 
	status VARCHAR NOT NULL, 
	trace_id VARCHAR NOT NULL, 
	external_ref VARCHAR, 
	verification JSON NOT NULL, 
	attempts INTEGER NOT NULL, 
	lease_until FLOAT NOT NULL, 
	updated FLOAT NOT NULL, 
	id VARCHAR NOT NULL, 
	org_id VARCHAR NOT NULL, 
	env VARCHAR NOT NULL, 
	created FLOAT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(agent_id, org_id, env) REFERENCES agents (id, org_id, env), 
	FOREIGN KEY(tool_id, org_id, env) REFERENCES tools (id, org_id, env), 
	UNIQUE (org_id, env, principal, idem_key)
);

CREATE INDEX ix_actions_status ON actions (status);

CREATE INDEX ix_actions_org_id ON actions (org_id);

CREATE INDEX ix_actions_agent_id ON actions (agent_id);
