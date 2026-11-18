-- Schema 2: run via nexus.cli migrate for transactional/version checks.

CREATE TABLE oidc_transactions (
	id VARCHAR NOT NULL, 
	binding_hash VARCHAR NOT NULL, 
	nonce VARCHAR NOT NULL, 
	verifier_ciphertext TEXT NOT NULL, 
	expires FLOAT NOT NULL, 
	used_at FLOAT NOT NULL, 
	PRIMARY KEY (id)
)

;
CREATE INDEX ix_oidc_transactions_expires ON oidc_transactions (expires);
