# ADR 002: Criptografia AES-256-GCM Local para Secrets

## Status
Aceito.

## Context
Credenciais SSH (usuário, senha, chave) e tokens de serviço precisam ser armazenados
em repouso. O projeto atual usa `.env` em texto plano para ambiente de laboratório.
Para produção/minimizar exposição, é necessário um esquema de criptografia que:
- Não dependa de serviços externos (Vault, KMS, AWS Secrets Manager)
- Seja auditável e de código aberto
- Permita fallback para texto plano em lab

## Decision
Implementar **`CryptoEnvBackend`** usando **AES-256-GCM** da biblioteca `cryptography`,
com chave mestra fornecida via variável de ambiente `SECRETS_KEY` ou keyring do sistema.

### Detalhes
- Algoritmo: AES-256-GCM (autenticado, com tag de integridade)
- Nonce: 12 bytes aleatórios (contra-replay)
- Chave: 32 bytes (256 bits) derivada de PBKDF2 ou fornecida diretamente
- Formato de armazenamento: JSON com campos `ciphertext`, `nonce`, `tag`, `version`
- Fallback: se `SECRETS_KEY` não estiver definida, usa texto plano (.env)
- Makefile targets: `make encrypt-env`, `make decrypt-env`

## Consequences
### Positivas
- Zero dependência de infraestrutura externa
- Auditorável: qualquer pessoa com a chave pode verificar o conteúdo
- GCM fornece autenticação + confidencialidade (tamper evidente)
- Keyring do sistema operacional como alternativa à env var
- Fallback transparente para lab (sem chave = texto plano)

### Negativas
- Chave mestra é SPOF: se perdida, dados irrecuperáveis
- Sem rotação automática de chave (responsabilidade do operador)
- PBKDF2 adiciona latência na inicialização (~100ms)
- Sem HSM para proteção adicional da chave

### Riscos
- Chave mestra exposta em environment dump (mitigação: keyring + processo com env var temporária)
- Sem revogação de chave (mitigação: backup da chave em local seguro, separado dos dados)
